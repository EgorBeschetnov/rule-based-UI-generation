import json
import re
from pathlib import Path
import ollama
from logger import log_interaction

SYSTEM_PROMPT = """
Ты — эксперт по UI/UX дизайну. Создай JSON-спецификацию интерфейса по описанию.

ОБЯЗАТЕЛЬНЫЕ поля JSON:
1. title — название интерфейса (строка)
2. items — список пунктов главного меню (массив строк)
3. style — объект стиля со следующими полями:
   - bg_color, text_color, button_bg, button_hover — цвета в hex
   - font_family — шрифт
   - border_radius — скругление (например "8px")
   - box_shadow — тень (например "0 2px 8px rgba(0,0,0,0.4)")
   - layout — ОБЯЗАТЕЛЬНО одно из: "vertical" | "horizontal" | "grid" | "sidebar"
     * sidebar — для дашбордов с боковым меню (если в описании упоминается дашборд, панель управления, боковое меню)
     * grid — для плиточных интерфейсов (банки, файловые менеджеры)
     * horizontal — для горизонтальных меню (спорт, плееры)
     * vertical — для классических меню (игры, приложения)
4. screens — объект с вложенными экранами для КАЖДОГО пункта меню.
   Каждый экран: {"title": "...", "items": [...], "extra_components": [...]}
   extra_components — интерактивные элементы типов: slider, checkbox, select, input

Пример структуры screens:
"screens": {
  "settings": {"title": "Настройки", "items": [], "extra_components": [
    {"type": "slider", "label": "Громкость", "min": 0, "max": 100, "value": 50},
    {"type": "checkbox", "label": "Уведомления", "checked": true},
    {"type": "select", "label": "Язык", "options": ["Русский", "English"]}
  ]},
  "profile": {"title": "Профиль", "items": ["Редактировать", "Фото", "Выход"], "extra_components": []}
}

Верни ТОЛЬКО валидный JSON без пояснений и без markdown.
"""

# Ключевые слова → layout
_LAYOUT_HINTS: list[tuple[str, list[str]]] = [
    ("sidebar",     ["дашборд", "dashboard", "боков", "sidebar", "панель управления",
                     "admin panel", "аналитик", "analytics", "crm", "erp",
                     "file manager", "файловый менеджер", "управлени"]),
    ("horizontal",  ["горизонталь", "horizontal", "плеер", "player", "спорт",
                     "фитнес", "fitness", "navbar", "топ-меню"]),
    ("grid",        ["банк", "bank", "плитк", "tile", "grid", "сетк",
                     "каталог", "catalog", "магазин", "store"]),
]


def _detect_layout_from_text(text: str, title: str = "") -> str | None:
    """Определяет подходящий layout по тексту описания и заголовку."""
    combined = (text + " " + title).lower()
    for layout, keywords in _LAYOUT_HINTS:
        if any(kw in combined for kw in keywords):
            return layout
    return None


def parse_with_template(text: str, template: dict, model: str = "llama3.2:3b") -> dict:
    """Адаптирует шаблон под описание пользователя через LLM."""
    template_clean = {k: v for k, v in template.items() if k != "meta"}
    template_json = json.dumps(template_clean, ensure_ascii=False, indent=2)

    prompt = f"""У тебя есть готовая JSON-спецификация интерфейса:
{template_json}

Пользователь хочет адаптировать этот интерфейс под своё описание:
{text}

Измени спецификацию согласно описанию: обнови название, пункты меню, стиль, вложенные экраны и компоненты. Сохрани общую структуру JSON. Верни ТОЛЬКО валидный JSON без пояснений."""

    raw_response = ""
    success = False
    parsed_data = {}

    try:
        response = ollama.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        raw_response = response["message"]["content"].strip()
        raw_response = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", raw_response)

        json_match = re.search(r"```json\s*(\{.*?\})\s*```", raw_response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_match = re.search(r"\{.*\}", raw_response, re.DOTALL)
            if json_match:
                json_str = json_match.group()
            else:
                raise ValueError("JSON не найден")

        parsed_data = normalize_spec(json.loads(json_str), source_text=text)
        success = True
        return parsed_data

    except Exception as e:
        print(f"LLM error (template mode): {e}. Использую шаблон как есть.")
        parsed_data = normalize_spec(template_clean, source_text=text)
        return parsed_data
    finally:
        log_interaction(text, model, raw_response, parsed_data, success)


def parse_with_vision(text: str, image_paths: list[str],
                      vision_model: str = "llava:7b",
                      text_model: str = "llama3.2:3b") -> dict:
    """
    Анализирует референсные скриншоты через llava и генерирует JSON-спецификацию,
    вдохновлённую их стилем и структурой.
    """
    raw_response = ""
    success = False
    parsed_data = {}

    vision_prompt = f"""Посмотри на эти скриншоты интерфейсов. Они служат референсом по стилю и структуре.

Пользователь хочет создать интерфейс: {text}

Проанализируй скриншоты и опиши:
1. Цветовую схему (фон, кнопки, текст — конкретные цвета)
2. Расположение элементов (вертикально / горизонтально / сетка)
3. Стиль (минималистичный, тёмный, яркий, корпоративный и т.д.)
4. Структуру навигации (какие разделы, подразделы)
5. Интерактивные элементы (слайдеры, переключатели, поля ввода)

Затем создай JSON-спецификацию нового интерфейса, сочетающую стиль референсов с запросом пользователя.
Верни ТОЛЬКО валидный JSON без пояснений."""

    try:
        response = ollama.chat(
            model=vision_model,
            messages=[{
                "role": "user",
                "content": vision_prompt,
                "images": image_paths,
            }]
        )
        raw_response = response["message"]["content"].strip()
        raw_response = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", raw_response)

        json_match = re.search(r"```json\s*(\{.*?\})\s*```", raw_response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_match = re.search(r"\{.*\}", raw_response, re.DOTALL)
            if json_match:
                json_str = json_match.group()
            else:
                # llava описала словами, но не дала JSON — передаём описание в текстовый LLM
                print("llava не вернул JSON, передаю описание в текстовый LLM...")
                combined = f"{text}\n\nВизуальный референс (описание стиля):\n{raw_response[:800]}"
                return parse_description(combined, model=text_model)

        parsed_data = normalize_spec(json.loads(json_str), source_text=text)
        success = True
        return parsed_data

    except Exception as e:
        print(f"Vision error: {e}. Fallback на текстовую генерацию.")
        parsed_data = parse_description(text, model=text_model)
        return parsed_data
    finally:
        log_interaction(text, vision_model, raw_response, parsed_data, success)


def parse_description(text: str, model: str = "llama3.2:3b") -> dict:
    prompt = f"{SYSTEM_PROMPT}\n\nТекст описания: {text}\n\nJSON:"

    raw_response = ""
    success = False
    parsed_data = {}

    try:
        response = ollama.chat(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Текст описания: {text}\n\nJSON:"},
            ],
        )
        raw_response = response["message"]["content"].strip()
        raw_response = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", raw_response)

        json_match = re.search(r"```json\s*(\{.*?\})\s*```", raw_response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_match = re.search(r"\{.*\}", raw_response, re.DOTALL)
            if json_match:
                json_str = json_match.group()
            else:
                raise ValueError("JSON не найден в ответе модели")

        parsed_data = json.loads(json_str)
        success = True
        parsed_data = normalize_spec(parsed_data, source_text=text)

        # Если LLM вернула заглушки (Пункт 1/2/3 или Item 1/2/3) — дополняем из текста
        if _items_are_placeholder(parsed_data.get("items", [])):
            print("LLM вернула заглушки для пунктов меню, дополняю из текста...")
            fallback = fallback_parse(text)
            if not _items_are_placeholder(fallback.get("items", [])):
                parsed_data["items"] = fallback["items"]
                # Добавляем экраны из fallback если LLM не дала своих
                if not parsed_data.get("screens"):
                    parsed_data["screens"] = fallback["screens"]

        return parsed_data

    except Exception as e:
        print(f"LLM error: {e}. Использую fallback.")
        parsed_data = fallback_parse(text)
        success = False
        return parsed_data
    finally:
        log_interaction(text, model, raw_response, parsed_data, success)


def _items_are_placeholder(items: list) -> bool:
    """Проверяет, являются ли пункты меню заглушками типа 'Пункт 1', 'Item 2'."""
    if not items:
        return True
    placeholder_re = re.compile(r"^(пункт|item|раздел|option|menu item)\s*\d+$", re.I)
    return all(placeholder_re.match(str(i).strip()) for i in items)


# Возможные имена полей которые LLM может придумать сама
_TITLE_KEYS    = ["title", "name", "heading", "label", "app_name", "menu_name", "interface_name"]
_ITEMS_KEYS    = ["items", "menu_items", "navigation", "navigationmenu", "nav_items", "navpoints",
                  "nav_points", "navlinks", "nav_links", "buttons", "options", "links", "entries",
                  "actions", "points", "menu", "menuitems", "main_items", "main_menu", "mainmenu",
                  "navbar", "nav", "menupoints", "navigationpoints", "menulinks",
                  "labels", "list", "menu_list"]
_STYLE_KEYS    = ["style", "theme", "design", "appearance", "styles", "visual", "ui_style", "styling",
                  "visuals", "css", "ui_style", "look", "colors_and_fonts", "design_system"]
_SCREENS_KEYS  = ["screens", "sub_screens", "pages", "sections", "subscreens", "submenus", "sub_menus", "children", "sub_pages", "routes"]
_COMPONENTS_KEYS = ["extra_components", "components", "controls", "inputs", "widgets", "elements",
                    "ui_elements", "fields", "interactivity", "interactive_elements", "form_elements"]


def _find_key(d: dict, candidates: list) -> object:
    """Ищет первый подходящий ключ в словаре, без учёта регистра."""
    d_lower = {k.lower(): v for k, v in d.items()}
    for c in candidates:
        if c.lower() in d_lower:
            return d_lower[c.lower()]
    return None


def _looks_like_main(d: dict) -> bool:
    """Проверяет, похож ли словарь на главный блок интерфейса (есть title + nav/items)."""
    if not isinstance(d, dict):
        return False
    has_title = _find_key(d, _TITLE_KEYS) is not None
    has_nav   = _find_key(d, _ITEMS_KEYS) is not None
    return has_title and has_nav


def normalize_spec(raw: dict, source_text: str = "") -> dict:
    """
    Приводит произвольный JSON от LLM к стандартной структуре генератора.
    Работает даже если LLM придумала нестандартные имена полей.
    source_text — оригинальный текст описания для определения layout'а.
    """
    # Случай 1: LLM обернула всё в один ключ-обёртку → разворачиваем
    # (ключ может быть "interface", "menu", или даже название приложения)
    if len(raw) == 1:
        only_val = next(iter(raw.values()))
        if isinstance(only_val, dict):
            raw = only_val
    else:
        # Случай 2: несколько ключей на верхнем уровне.
        # Один из них — главный блок (title + nav), остальные — вложенные экраны.
        # Пример: {"interface": {...nav...}, "settings": {...}, "characters": {...}}
        main_key = None
        for k, v in raw.items():
            if _looks_like_main(v):
                main_key = k
                break

        if main_key is not None:
            main_block = raw[main_key]
            # Собираем остальные dict-значения как дополнительные вложенные экраны
            extra_screens = {k: v for k, v in raw.items()
                             if k != main_key and isinstance(v, dict)}
            # Если в главном блоке уже есть screens — добавляем в них
            existing_screens_key = None
            for sk in _SCREENS_KEYS:
                if sk.lower() in {ek.lower() for ek in main_block}:
                    existing_screens_key = next(
                        ek for ek in main_block if ek.lower() == sk.lower()
                    )
                    break
            if existing_screens_key:
                if isinstance(main_block[existing_screens_key], dict):
                    main_block[existing_screens_key].update(extra_screens)
                # list-формат не трогаем — добавим ниже через _normalize_screens
            else:
                main_block["screens"] = extra_screens
            raw = main_block

    # --- title ---
    title = _find_key(raw, _TITLE_KEYS) or "Меню"
    if not isinstance(title, str):
        title = str(title)

    # --- items ---
    items_raw = _find_key(raw, _ITEMS_KEYS) or []
    items = _normalize_items(items_raw)
    if not items:
        items = ["Пункт 1", "Пункт 2", "Пункт 3"]

    # --- style ---
    style_raw = _find_key(raw, _STYLE_KEYS) or {}
    style = _normalize_style(style_raw) if isinstance(style_raw, dict) else {}

    # Если layout не задан или задан нераспознанным значением — определяем по тексту/заголовку
    known_layouts = {"vertical", "horizontal", "grid", "sidebar"}
    if style.get("layout", "").lower() not in known_layouts:
        detected = _detect_layout_from_text(source_text, title)
        if detected:
            style["layout"] = detected

    # --- screens ---
    id_map = _find_key(raw, ["identifiers", "ids", "screen_ids", "id_map"]) or {}
    screens_raw = _find_key(raw, _SCREENS_KEYS) or {}
    screens = _normalize_screens(screens_raw, id_map, parent=raw)

    # Нормализуем: если title экрана не совпадает ни с одним пунктом меню —
    # пробуем найти подходящий пункт через транслитерацию или словарь псевдонимов
    for screen_id, screen_data in screens.items():
        s_title_lower = screen_data["title"].lower()
        if not any(i.lower() == s_title_lower for i in items):
            matched = match_nav_item_to_screen(screen_id, items)
            if matched:
                screen_data["title"] = matched

    # Если экранов нет совсем — автогенерируем по пунктам меню
    if not screens and items:
        screens = _auto_stub_screens(items)

    # Нормализуем пункты меню чтобы совпадали с title экранов (для навигации)
    screen_titles = {s["title"].lower(): s["title"] for s in screens.values()}
    items = [screen_titles.get(i.lower(), i) for i in items]

    return {"title": title, "items": items, "style": style, "screens": screens}


# Шаблоны содержимого для типовых экранов (используются при автогенерации)
_SCREEN_TEMPLATES: dict[str, dict] = {
    "настройки":    {"items": [], "extra_components": [
        {"type": "slider",   "label": "Уведомления",  "min": 0, "max": 100, "value": 70},
        {"type": "checkbox", "label": "Тёмная тема",  "checked": True},
        {"type": "checkbox", "label": "Звук",         "checked": True},
        {"type": "select",   "label": "Язык",         "options": ["Русский", "English"]},
    ]},
    "параметры":    {"items": [], "extra_components": [
        {"type": "slider",   "label": "Яркость",      "min": 0, "max": 100, "value": 80},
        {"type": "checkbox", "label": "Автосохранение","checked": True},
        {"type": "select",   "label": "Тема",         "options": ["Светлая", "Тёмная", "Системная"]},
    ]},
    "профиль":      {"items": ["Редактировать", "Сменить фото", "Выход"], "extra_components": [
        {"type": "input",    "label": "Имя",          "placeholder": "Ваше имя"},
        {"type": "input",    "label": "Email",        "placeholder": "email@example.com"},
    ]},
    "аналитика":    {"items": ["За сегодня", "За неделю", "За месяц", "За год"], "extra_components": []},
    "события":      {"items": ["Сегодня", "Предстоящие", "Архив"], "extra_components": []},
    "задачи":       {"items": ["Активные", "Выполненные", "Просроченные", "Новая задача"], "extra_components": []},
    "хранилище":    {"items": ["Документы", "Изображения", "Видео", "Архив"], "extra_components": [
        {"type": "slider",   "label": "Использовано", "min": 0, "max": 100, "value": 30},
    ]},
    "проекты":      {"items": ["Активные", "Завершённые", "Черновики", "Создать"], "extra_components": []},
    "сообщения":    {"items": ["Входящие", "Отправленные", "Черновики"], "extra_components": []},
    "счета":        {"items": ["Текущий", "Сберегательный", "Кредитный"], "extra_components": []},
    "переводы":     {"items": ["По номеру карты", "По телефону", "Между счетами", "История"], "extra_components": []},
    "тренировки":   {"items": ["Силовые", "Кардио", "Растяжка", "HIIT"], "extra_components": []},
    "питание":      {"items": ["Завтрак", "Обед", "Ужин", "Перекус"], "extra_components": [
        {"type": "input",    "label": "Цель по калориям", "placeholder": "2000"},
    ]},
    "персонажи":    {"items": [], "extra_components": []},
    "галерея":      {"items": ["Все", "Избранное", "Альбомы"], "extra_components": []},
    "поддержка":    {"items": ["FAQ", "Чат", "Email"], "extra_components": [
        {"type": "input",    "label": "Описание проблемы", "placeholder": "Опишите проблему"},
    ]},
}


def _auto_stub_screens(items: list) -> dict:
    """
    Создаёт вложенные экраны для каждого пункта меню.
    Для известных типов экранов (настройки, профиль и т.д.) добавляет типовое содержимое.
    Для главной/обзора не создаёт sub-screen — они и есть главный экран.
    """
    skip_as_main = {"главная", "главный", "home", "main", "обзор", "overview", "dashboard"}
    result = {}
    for item in items:
        item_lower = item.lower()
        if item_lower in skip_as_main:
            continue
        screen_id = _to_latin_id(item)
        # Ищем шаблон по точному совпадению или вхождению ключа
        template = None
        for key, tmpl in _SCREEN_TEMPLATES.items():
            if key in item_lower or item_lower in key:
                template = tmpl
                break
        if template:
            result[screen_id] = {
                "title": item,
                "items": list(template["items"]),
                "extra_components": list(template["extra_components"]),
            }
        else:
            # Генерируем пустой экран — хотя бы навигация будет работать
            result[screen_id] = {"title": item, "items": [], "extra_components": []}
    return result


def _normalize_items(raw) -> list:
    """Превращает список любого вида в список строк."""
    if not isinstance(raw, list):
        return []
    result = []
    for item in raw:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict):
            label = _find_key(item, ["label", "name", "title", "text", "item"]) or ""
            result.append(str(label))
    return [i for i in result if i]


def _normalize_style(raw: dict) -> dict:
    """Нормализует поля стиля к именам которые знает генератор."""
    key_map = {
        "bg_color":      ["bg_color", "background", "background_color", "bg", "backgroundColor"],
        "text_color":    ["text_color", "color", "font_color", "textColor", "foreground"],
        "button_bg":     ["button_bg", "button_color", "btn_color", "button_background", "buttonBg"],
        "button_hover":  ["button_hover", "hover_color", "accent", "highlight", "buttonHover"],
        "font_family":   ["font_family", "font", "typeface", "fontFamily"],
        "layout":        ["layout", "arrangement", "orientation", "direction"],
        "border_radius": ["border_radius", "radius", "corner_radius", "borderRadius"],
        "text_transform":["text_transform", "case", "text_case", "textTransform"],
        "box_shadow":    ["box_shadow", "shadow", "boxShadow"],
        "animation":     ["animation", "hover_effect", "transition", "hoverAnimation"],
    }
    result = {}
    raw_lower = {k.lower(): v for k, v in raw.items()}
    for target, candidates in key_map.items():
        for c in candidates:
            if c.lower() in raw_lower:
                val = raw_lower[c.lower()]
                # font_family может прийти как {"family": "Arial", "size": 14}
                if target == "font_family" and isinstance(val, dict):
                    val = val.get("family", val.get("name", "Arial"))
                # layout может прийти как {"padding": 20} — берём только строки
                if target == "layout" and not isinstance(val, str):
                    break
                # border_radius может прийти как True (roundedCorners) — конвертируем
                if target == "border_radius" and isinstance(val, bool):
                    val = "8px" if val else "0px"
                if isinstance(val, str) or target in ("border_radius",):
                    result[target] = val
                elif isinstance(val, (int, float)):
                    result[target] = str(val)
                break
    return result


_TRANSLIT = {
    'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'yo','ж':'zh','з':'z',
    'и':'i','й':'y','к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r',
    'с':'s','т':'t','у':'u','ф':'f','х':'h','ц':'ts','ч':'ch','ш':'sh','щ':'sch',
    'ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya',
}

# Таблица соответствий: английский ID экрана → варианты русских названий
# Используется для поиска нужного пункта меню когда LLM даёт экранам английские ID
_EN_SCREEN_ALIASES: dict[str, list[str]] = {
    "settings":     ["настройки", "параметры", "конфигурация", "options", "preferences"],
    "characters":   ["персонажи", "герои", "character", "heroes", "roster"],
    "inventory":    ["инвентарь", "предметы", "снаряжение", "items"],
    "shop":         ["магазин", "покупки", "store", "market"],
    "profile":      ["профиль", "аккаунт", "account"],
    "map":          ["карта", "мир", "world"],
    "quests":       ["задания", "квесты", "missions"],
    "achievements": ["достижения", "awards"],
    "audio":        ["звук", "аудио", "музыка", "sound", "music"],
    "graphics":     ["графика", "видео", "отображение", "video", "display"],
    "controls":     ["управление", "клавиши", "bindings"],
    "gallery":      ["галерея", "фотографии"],
    "about":        ["о приложении", "about us", "информация"],
    "transfers":    ["переводы", "transfer"],
    "accounts":     ["счета", "счёта", "balance"],
    "credits":      ["кредиты", "loans"],
    "investments":  ["инвестиции"],
    "support":      ["поддержка", "помощь", "help"],
    "workouts":     ["тренировки", "упражнения"],
    "nutrition":    ["питание", "еда", "food"],
    "progress":     ["прогресс", "статистика"],
    "community":    ["сообщество", "community"],
    "database":     ["базы данных", "данные", "data"],
    "communication":["связь", "коммуникация"],
}


def _to_latin_id(s: str) -> str:
    """Превращает произвольную строку в безопасный latin id."""
    s = s.lower()
    s = "".join(_TRANSLIT.get(c, c) for c in s)
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s or "screen"


def match_nav_item_to_screen(screen_id: str, nav_items: list[str]) -> str | None:
    """
    Пытается найти в списке nav_items пункт, соответствующий английскому screen_id.
    Стратегии: 1) точное совпадение транслитерации, 2) словарь псевдонимов.
    Возвращает найденный пункт меню или None.
    """
    sid_lower = screen_id.lower()
    for item in nav_items:
        # Стратегия 1: транслитерация пункта совпадает с ID
        if _to_latin_id(item) == sid_lower:
            return item
        # Стратегия 2: пункт меню содержится в словаре псевдонимов
        aliases = _EN_SCREEN_ALIASES.get(sid_lower, [])
        if item.lower() in aliases or any(a in item.lower() for a in aliases):
            return item
    return None


# Ключевые слова для автоматического определения типа компонента по метке
_INFER_SLIDER = [
    "звук", "музык", "громкость", "яркость", "volume", "brightness",
    "скорость", "speed", "темп", "размер", "size", "качество сжатия",
    "частота", "масштаб", "scale", "прозрачность", "opacity",
]
_INFER_CHECKBOX = [
    "полный экран", "fullscreen", "full screen", "вибрация", "vibration",
    "уведомлен", "notification", "шифрован", "encrypt", "включ", "enable",
    "отключ", "disable", "голосов", "voice", "автосохранен", "autosave",
    "синхронизац", "sync", "тёмная тема", "dark mode", "скрыть", "hide",
    "показать", "show", "биометр",
]
_INFER_SELECT = [
    "язык", "language", "тема", "theme", "качество", "quality",
    "разрешение", "resolution", "протокол", "protocol", "валюта", "currency",
    "регион", "region", "формат", "format", "сортировка", "sort",
    "цвет", "color", "единицы", "units",
]
_INFER_INPUT = [
    "имя", "name пользователя", "email", "логин", "login", "пароль",
    "password", "поиск", "search", "кодовое", "цель", "никнейм", "nickname",
]


def _infer_component_from_label(label: str) -> dict | None:
    """
    Определяет тип компонента по метке.
    Используется когда LLM кладёт компоненты как обычные пункты меню.
    """
    ll = label.lower()
    for kw in _INFER_SLIDER:
        if kw in ll:
            return {"type": "slider", "label": label, "min": 0, "max": 100, "value": 50}
    for kw in _INFER_CHECKBOX:
        if kw in ll:
            return {"type": "checkbox", "label": label, "checked": False}
    for kw in _INFER_SELECT:
        if kw in ll:
            return {"type": "select", "label": label, "options": []}
    for kw in _INFER_INPUT:
        if kw in ll:
            return {"type": "input", "label": label, "placeholder": ""}
    return None


def _normalize_screens(raw, id_map: dict = None, parent: dict = None) -> dict:
    """
    Нормализует вложенные экраны.
    Поддерживает:
    - dict формат: {"settings": {"title": ..., "items": [...]}}
    - list формат: [{"id": "settings", "title": ...}, ...]
      (контент экрана ищется в parent по ключам settingsScreen, settings_screen и т.п.)
    """
    id_map = id_map or {}
    parent = parent or {}
    result = {}

    # Приводим list-формат к dict-формату
    if isinstance(raw, list):
        raw_dict = {}
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            sid = str(_find_key(entry, ["id", "key", "screen_id", "name"]) or "screen")
            raw_dict[sid] = entry
        raw = raw_dict

    if not isinstance(raw, dict):
        return {}

    for screen_key, screen_data in raw.items():
        if not isinstance(screen_data, dict):
            continue

        screen_id = id_map.get(screen_key, screen_key)
        screen_id = _to_latin_id(screen_id)

        s_title = _find_key(screen_data, ["title", "name", "heading", "label"]) or screen_key.capitalize()

        # Ищем контент экрана: сначала в самом объекте, потом в parent по шаблонам
        content = screen_data
        if not _find_key(screen_data, _ITEMS_KEYS) and not _find_key(screen_data, _COMPONENTS_KEYS):
            parent_lower = {k.lower(): v for k, v in parent.items()}
            for pattern in [f"{screen_id}screen", f"{screen_id}_screen",
                            f"screen_{screen_id}", f"{screen_key}screen",
                            f"{screen_key}_screen"]:
                if pattern.lower() in parent_lower:
                    content = parent_lower[pattern.lower()]
                    break

        s_items = _normalize_items(_find_key(content, _ITEMS_KEYS) or [])
        all_components = _normalize_components(_find_key(content, _COMPONENTS_KEYS) or [])
        # Кнопки из компонентов переносим в items
        s_extra = []
        for c in all_components:
            if c.get("type") == "button":
                s_items.append(c["label"])
            else:
                s_extra.append(c)

        # Если компонентов нет, но пункты выглядят как компоненты (звук, язык, полный экран...) —
        # автоматически конвертируем их из items в extra_components
        if not s_extra and s_items:
            inferred_items = []
            for item_label in s_items:
                inferred = _infer_component_from_label(item_label)
                if inferred:
                    s_extra.append(inferred)
                else:
                    inferred_items.append(item_label)
            s_items = inferred_items

        # Убираем из items дубли меток компонентов
        component_labels = {c["label"].lower() for c in s_extra if "label" in c}
        s_items = [i for i in s_items if i.lower() not in component_labels]

        # Убираем text-компоненты которые являются английскими дублями русских items
        if s_items:
            cyrillic_items = [i for i in s_items if any('\u0400' <= c <= '\u04ff' for c in i)]
            if cyrillic_items:
                s_extra = [c for c in s_extra if not (
                    c.get("type") == "text" and
                    all(ch.isascii() for ch in c.get("content", ""))
                )]

        result[screen_id] = {
            "title": str(s_title),
            "items": s_items,
            "extra_components": s_extra,
        }
    return result


def _normalize_components(raw) -> list:
    """Нормализует компоненты к известным типам (slider, checkbox, select, input, text)."""
    if not isinstance(raw, list):
        return []
    known_types = {"slider", "checkbox", "select", "input", "text",
                   "range", "toggle", "switch", "dropdown", "textfield", "text_field"}
    type_map = {"range": "slider", "toggle": "checkbox", "switch": "checkbox",
                "dropdown": "select", "textfield": "input", "text_field": "input",
                "list": "button", "item": "button", "link": "button", "action": "button"}
    result = []
    for comp in raw:
        if not isinstance(comp, dict):
            continue
        raw_type = str(_find_key(comp, ["type", "kind", "component_type"]) or "text").lower()
        comp_type = type_map.get(raw_type, raw_type if raw_type in known_types else "text")
        # label: ищем в стандартных полях, если нет — берём из id (убираем суффикс -slider/-checkbox и т.д.)
        raw_label = _find_key(comp, ["label", "name", "title", "text"])
        if not raw_label:
            raw_id = str(_find_key(comp, ["id", "key", "field_id"]) or "")
            raw_label = re.sub(r"[-_](slider|checkbox|radio|dropdown|button|input|text)$", "", raw_id, flags=re.I)
            raw_label = raw_label.replace("-", " ").replace("_", " ").strip().capitalize()
        label = str(raw_label)

        if comp_type == "button":
            result.append({"type": "button", "label": label})
        elif comp_type == "slider":
            result.append({"type": "slider", "label": label,
                           "min": comp.get("min", 0), "max": comp.get("max", 100),
                           "value": comp.get("value", comp.get("default", 50))})
        elif comp_type == "checkbox":
            result.append({"type": "checkbox", "label": label,
                           "checked": bool(comp.get("checked", comp.get("default", False)))})
        elif comp_type == "select":
            opts = comp.get("options", comp.get("choices", comp.get("values", [])))
            result.append({"type": "select", "label": label, "options": opts or []})
        elif comp_type == "input":
            result.append({"type": "input", "label": label,
                           "placeholder": comp.get("placeholder", comp.get("hint", ""))})
        else:
            result.append({"type": "text",
                           "content": str(_find_key(comp, ["content", "text", "value", "label"]) or label)})
    return result


SCREEN_MAP = {
    "настройках": ("Настройки", "settings"),
    "настройки":  ("Настройки", "settings"),
    "персонажах": ("Персонажи", "characters"),
    "персонажи":  ("Персонажи", "characters"),
    "магазине":   ("Магазин",   "shop"),
    "магазин":    ("Магазин",   "shop"),
    "профиле":    ("Профиль",   "profile"),
    "профиль":    ("Профиль",   "profile"),
    "видео":      ("Видео",     "video"),
    "управлении": ("Управление","controls"),
    "управление": ("Управление","controls"),
    "звуке":      ("Звук",      "audio"),
    "галерее":    ("Галерея",   "gallery"),
    "галерея":    ("Галерея",   "gallery"),
    "достижениях":("Достижения","achievements"),
}

COMPONENT_KEYWORDS = {
    "slider":   ["ползунок", "слайдер", "громкость", "яркость", "звук", "музык"],
    "checkbox": ["чекбокс", "флажок", "переключатель"],
    "select":   ["выбор", "выпадающий", "список"],
    "input":    ["ввод", "поле", "имя", "логин"],
}


def _detect_component(part: str) -> dict | None:
    part_lower = part.lower()
    for comp_type, keywords in COMPONENT_KEYWORDS.items():
        for kw in keywords:
            if kw in part_lower:
                label = re.sub(kw, "", part, flags=re.I).strip(" ,;") or part.strip()
                if comp_type == "slider":
                    return {"type": "slider", "label": label, "min": 0, "max": 100, "value": 50}
                if comp_type == "checkbox":
                    return {"type": "checkbox", "label": label, "checked": False}
                if comp_type == "select":
                    return {"type": "select", "label": label, "options": []}
                if comp_type == "input":
                    return {"type": "input", "label": label, "placeholder": ""}
    return None


def fallback_parse(text: str) -> dict:
    # Заголовок: первая строка в кавычках, после слова "название", или первое предложение
    title_match = re.search(r'[«""]([^»""]{2,40})[»""]', text)
    if not title_match:
        title_match = re.search(r"название\s*[\"']?([^\"',\.]{2,40})", text, re.I)
    if not title_match:
        # Берём первое предложение до точки/запятой как возможный заголовок
        first_sent = re.match(r"([^\.,:]{5,60})", text.strip())
        if first_sent:
            candidate = first_sent.group(1).strip()
            # Только если нет служебных слов (описательных)
            if not re.search(r"\b(создай|сделай|нужен|хочу|приложение для)\b", candidate, re.I):
                title_match = first_sent
    title = title_match.group(1).strip() if title_match else "Меню"

    # Главные пункты меню — ищем по множеству паттернов
    items: list[str] = []

    # Паттерн 1: "пункты/пунктами/разделы/вкладки [навигации]: А, Б, В"
    # Двоеточие обязательно, чтобы не захватить заголовок
    nav_word = r"(?:пункт(?:ы|ами|ов|ах)?|разделы?|вкладки?|навигац\w*)"
    items_match = re.search(nav_word + r"(?:\s+\w+)?\s*:\s*([^\.;]{5,200})", text, re.I)
    if items_match:
        items = [i.strip() for i in re.split(r"[,;]|\s+и\s+", items_match.group(1)) if i.strip()]

    # Паттерн 2: "с пунктами А, Б, В" или "включает А, Б, В"
    if not items:
        items_match = re.search(
            r"(?:с\s+(?:пунктами|разделами|вкладками)|включает(?:\s+в\s+себя)?|содержит)\s*:?\s*([^\.;]{5,200})",
            text, re.I
        )
        if items_match:
            items = [i.strip() for i in re.split(r"[,;]|\s+и\s+", items_match.group(1)) if i.strip()]
            # Убираем фрагменты начинающиеся с "аватар" — это не пункты меню
            items = [i for i in items if not re.match(r"аватар", i, re.I)]

    # Паттерн 3: "Навигационное меню: А, Б, В" или "Боковое меню: А, Б, В"
    if not items:
        items_match = re.search(r"(?:навигацион\w+|боков\w+)\s+\w+\s*:\s*([^\.;]{5,200})", text, re.I)
        if items_match:
            items = [i.strip() for i in re.split(r"[,;]|\s+и\s+", items_match.group(1)) if i.strip()]

    # Паттерн 4: ищем список с заглавных букв после двоеточия (общий случай)
    if not items:
        for colon_match in re.finditer(r":\s+([А-ЯЁA-Z][^\.]{3,150})", text):
            candidates = [i.strip() for i in re.split(r"[,;]|\s+и\s+", colon_match.group(1)) if i.strip()]
            # Берём только короткие фразы — не длинные предложения, не компоненты
            good = [c for c in candidates
                    if 2 <= len(c) <= 35
                    and not re.search(r"\b(ползунок|слайдер|чекбокс|поле|кнопка)\b", c, re.I)]
            if len(good) >= 2:  # минимум 2 пункта чтобы считать списком
                items = good
                break

    # Очищаем — убираем лишние слова-описания
    items = [re.sub(r"^(?:и|также|плюс)\s+", "", i, flags=re.I).strip() for i in items]
    items = [i for i in items if 2 <= len(i) <= 40][:8]  # максимум 8 пунктов

    if not items:
        items = ["Пункт 1", "Пункт 2", "Пункт 3"]

    # Подэкраны: «в X: ...» или «в X — ...»
    screens: dict = {}
    for m in re.finditer(r"[вВ]\s+([\w]+)\s*[:—]\s*([^\.]+)", text):
        key = m.group(1).lower()
        if key not in SCREEN_MAP:
            continue
        screen_title, screen_id = SCREEN_MAP[key]
        content = m.group(2).strip()

        extra_components: list[dict] = []
        sub_items: list[str] = []
        for part in re.split(r"[,;]", content):
            part = part.strip()
            if not part:
                continue
            comp = _detect_component(part)
            if comp:
                extra_components.append(comp)
            else:
                sub_items.append(part)

        screens[screen_id] = {
            "title": screen_title,
            "items": sub_items,
            "extra_components": extra_components,
        }

        # Нормализуем пункт главного меню чтобы совпадал с title экрана
        for i, item in enumerate(items):
            if item.lower() == screen_title.lower() or key in item.lower():
                items[i] = screen_title

    return {
        "title": title,
        "items": items,
        "style": {
            "bg_color": "#1e1e2f",
            "text_color": "#ffffff",
            "button_bg": "#3a3a5a",
            "button_hover": "#5a5a8a",
            "font_family": "Arial, sans-serif",
            "layout": "vertical",
            "border_radius": "8px",
            "text_transform": "uppercase",
        },
        "screens": screens,
    }
