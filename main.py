# main.py
import customtkinter as ctk
import webbrowser
import json
import threading
from pathlib import Path
from tkinter import filedialog
from PIL import Image
from parser import parse_description, parse_with_template, parse_with_vision
from generator import HTMLGenerator
from figma_export import export_to_svg
from logger import update_session_html

TEMPLATES_DIR   = Path("templates")
INSPIRATION_DIR = Path("inspiration")
INSPIRATION_DIR.mkdir(exist_ok=True)

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)
SESSIONS_DIR = Path("sessions")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Генератор UI с Llama 3.2 (Диплом)")
        self.geometry("960x800")
        ctk.set_appearance_mode("dark")
        self._current_spec: dict = {}
        self._selected_template: dict | None = None
        self._selected_refs: list[str] = []   # пути выбранных референс-изображений
        self._ref_buttons: dict[str, ctk.CTkFrame] = {}
        self._build_ui()

    def _build_ui(self):
        # --- Ввод описания ---
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(padx=20, pady=(15, 0), fill="x")

        lbl_row = ctk.CTkFrame(top, fg_color="transparent")
        lbl_row.pack(fill="x")
        ctk.CTkLabel(lbl_row, text="Описание интерфейса:", font=("Arial", 15)).pack(side="left")
        ctk.CTkButton(lbl_row, text="Вставить из буфера", width=150, height=26,
                      command=self._paste_to_textbox).pack(side="right")

        self.textbox = ctk.CTkTextbox(top, height=110, font=("Arial", 13))
        self.textbox.pack(fill="x", pady=(5, 0))
        self.textbox.bind("<Control-v>", self._paste_to_textbox)
        self.textbox._textbox.bind("<Control-v>", self._paste_to_textbox)
        self.textbox.insert(
            "0.0",
            'Меню RPG игры "Eclipse of Gods" в мрачном стиле. '
            "Пункты: Новая игра, Продолжить, Настройки, Персонажи, Выход. "
            "В настройках: ползунок Звук, ползунок Музыка, чекбокс Полный экран, выбор Язык. "
            "В персонажах: Воин, Маг, Лучник.",
        )

        # --- Панель управления ---
        ctrl = ctk.CTkFrame(self, fg_color="transparent")
        ctrl.pack(padx=20, pady=8, fill="x")

        self.model_var = ctk.StringVar(value="llama3.2:3b")
        ctk.CTkOptionMenu(
            ctrl,
            values=["llama3.2:3b", "llama3.2:8b", "gemma2:2b", "tinyllama"],
            variable=self.model_var,
            width=155,
        ).pack(side="left")

        self.btn_generate = ctk.CTkButton(ctrl, text="Сгенерировать", command=self.generate, width=140)
        self.btn_generate.pack(side="left", padx=6)
        ctk.CTkButton(ctrl, text="Обновить историю", command=self.load_history, width=140).pack(side="left")
        ctk.CTkButton(ctrl, text="Figma SVG", command=self.export_figma,
                      width=110, fg_color="#7c4dff", hover_color="#651fff").pack(side="left", padx=6)

        self.status = ctk.CTkLabel(ctrl, text="Готов к работе", font=("Arial", 12))
        self.status.pack(side="right")

        # --- Вкладки ---
        self.tabs = ctk.CTkTabview(self)
        self.tabs.pack(padx=20, pady=(0, 15), fill="both", expand=True)

        self._build_spec_tab(self.tabs.add("Спецификация JSON"))
        self._build_history_tab(self.tabs.add("История"))
        self._build_gallery_tab(self.tabs.add("Шаблоны"))
        self._build_refs_tab(self.tabs.add("Референсы"))

    # ── Tab: Спецификация JSON ─────────────────────────────────────────────

    def _build_spec_tab(self, parent):
        ctk.CTkLabel(
            parent,
            text="JSON-спецификация (можно редактировать и применить без повторного запроса LLM):",
            font=("Arial", 12),
        ).pack(anchor="w", pady=(0, 5))

        self.spec_editor = ctk.CTkTextbox(parent, font=("Courier New", 12))
        self.spec_editor.pack(fill="both", expand=True, pady=(0, 10))
        self.spec_editor.insert("0.0", "// Спецификация появится после генерации")

        ctk.CTkButton(
            parent, text="Создать HTML из текущего JSON", command=self.generate_from_spec,
        ).pack(anchor="e")

    # ── Tab: История ───────────────────────────────────────────────────────

    def _build_history_tab(self, parent):
        ctk.CTkLabel(parent, text="Последние 20 генераций:", font=("Arial", 12)).pack(
            anchor="w", pady=(0, 5)
        )
        self.history_frame = ctk.CTkScrollableFrame(parent)
        self.history_frame.pack(fill="both", expand=True)
        self.load_history()

    def load_history(self):
        for w in self.history_frame.winfo_children():
            w.destroy()

        sessions = sorted(SESSIONS_DIR.glob("session_*.json"), reverse=True) if SESSIONS_DIR.exists() else []

        if not sessions:
            ctk.CTkLabel(self.history_frame, text="История пуста", text_color="gray").pack(pady=20)
            return

        for session_path in sessions[:20]:
            try:
                with open(session_path, encoding="utf-8") as f:
                    entry = json.load(f)
                self._add_history_entry(entry)
            except Exception:
                pass

    def _add_history_entry(self, entry: dict):
        ts      = entry.get("timestamp", "?")
        model   = entry.get("model", "?")
        success = entry.get("success", False)
        spec    = entry.get("parsed_json", {})

        # title: сначала из корневого поля (новый формат), потом из parsed_json
        title   = entry.get("title") or (spec.get("title") if isinstance(spec, dict) else None) or "—"
        preview = entry.get("user_input", "")[:70].replace("\n", " ")

        # Ищем HTML: сначала поле html_file из записи, потом по имени
        html_path = None
        stored_html = entry.get("html_file", "")
        if stored_html:
            candidate = Path(stored_html)
            if candidate.exists():
                html_path = candidate
        if not html_path:
            candidate = OUTPUT_DIR / f"menu_{title.replace(' ', '_')}.html"
            if candidate.exists():
                html_path = candidate

        # Статистика из спецификации
        items_count   = len(spec.get("items", [])) if isinstance(spec, dict) else 0
        screens_count = len(spec.get("screens", {})) if isinstance(spec, dict) else 0
        stat_str = f"  •  {items_count} пунктов, {screens_count} экранов" if items_count else ""

        row = ctk.CTkFrame(self.history_frame, corner_radius=8)
        row.pack(fill="x", pady=3, padx=4)

        dot_color = "#4caf50" if success else "#f44336"
        ctk.CTkLabel(row, text="●", text_color=dot_color, width=18).pack(side="left", padx=(8, 0))

        info = ctk.CTkFrame(row, fg_color="transparent")
        info.pack(side="left", fill="x", expand=True, padx=8, pady=6)
        ctk.CTkLabel(info, text=f"{ts[:16]}  [{model}]  {title}{stat_str}",
                     font=("Courier New", 11), anchor="w").pack(anchor="w")
        ctk.CTkLabel(info, text=preview, font=("Arial", 10),
                     text_color="gray", anchor="w", wraplength=420).pack(anchor="w")

        btn_frame = ctk.CTkFrame(row, fg_color="transparent")
        btn_frame.pack(side="right", padx=8, pady=6)

        if html_path:
            ctk.CTkButton(btn_frame, text="Просмотр", width=85,
                          fg_color="#2a6496", hover_color="#1a4d7a",
                          command=lambda p=html_path: self._show_preview(p)).pack(side="left", padx=(0, 4))

        ctk.CTkButton(btn_frame, text="Загрузить", width=85,
                      command=lambda s=spec: self._load_spec_into_editor(s)).pack(side="left")

    def _show_preview(self, filepath: Path):
        """Открывает HTML-файл в браузере по умолчанию."""
        try:
            webbrowser.open(f"file://{Path(filepath).absolute()}")
        except Exception as e:
            self.status.configure(text=f"Не удалось открыть: {e}")

    def _load_spec_into_editor(self, spec: dict):
        self.spec_editor.delete("0.0", "end")
        self.spec_editor.insert("0.0", json.dumps(spec, ensure_ascii=False, indent=2))
        self.tabs.set("Спецификация JSON")
        self.status.configure(text="Спецификация загружена из истории")

    # ── Tab: Шаблоны (галерея) ─────────────────────────────────────────────

    def _build_gallery_tab(self, parent):
        top = ctk.CTkFrame(parent, fg_color="transparent")
        top.pack(fill="x", pady=(0, 8))

        self.template_status = ctk.CTkLabel(
            top, text="Выберите шаблон как основу (необязательно)",
            font=("Arial", 12), text_color="gray"
        )
        self.template_status.pack(side="left")

        ctk.CTkButton(top, text="Сбросить выбор", width=130, height=26,
                      command=self._clear_template).pack(side="right")

        self.gallery_frame = ctk.CTkScrollableFrame(parent)
        self.gallery_frame.pack(fill="both", expand=True)
        self._template_cards: dict[str, ctk.CTkFrame] = {}
        self._load_gallery()

    def _load_gallery(self):
        templates = sorted(TEMPLATES_DIR.glob("*.json")) if TEMPLATES_DIR.exists() else []
        for i, tpl_path in enumerate(templates):
            try:
                with open(tpl_path, encoding="utf-8") as f:
                    tpl = json.load(f)
                self._add_template_card(tpl, tpl_path, i)
            except Exception:
                pass

    def _add_template_card(self, tpl: dict, path: Path, idx: int):
        meta    = tpl.get("meta", {})
        name    = meta.get("name", tpl.get("title", path.stem))
        desc    = meta.get("description", "")
        style   = tpl.get("style", {})
        bg      = style.get("bg_color", "#1a1a2e")
        text_c  = style.get("text_color", "#ffffff")
        btn_c   = style.get("button_bg", "#333")
        items   = tpl.get("items", [])
        screens = tpl.get("screens", {})

        card = ctk.CTkFrame(self.gallery_frame, corner_radius=10, border_width=2,
                            border_color="#333")
        card.pack(fill="x", pady=5, padx=4)

        # Цветной превью-блок
        preview = ctk.CTkFrame(card, width=160, height=110, fg_color=bg, corner_radius=8)
        preview.pack(side="left", padx=10, pady=10)
        preview.pack_propagate(False)
        ctk.CTkLabel(preview, text=tpl.get("title", ""),
                     font=("Arial", 11, "bold"), text_color=text_c,
                     fg_color="transparent").pack(pady=(8, 4))
        for item in items[:3]:
            ctk.CTkLabel(preview, text=item, font=("Arial", 9),
                         text_color=text_c, fg_color=btn_c,
                         corner_radius=4, width=120, height=18).pack(pady=1)

        # Описание
        info = ctk.CTkFrame(card, fg_color="transparent")
        info.pack(side="left", fill="both", expand=True, padx=8, pady=8)
        ctk.CTkLabel(info, text=name, font=("Arial", 14, "bold"), anchor="w").pack(anchor="w")
        ctk.CTkLabel(info, text=desc, font=("Arial", 11), text_color="gray",
                     anchor="w", wraplength=380).pack(anchor="w", pady=(2, 6))

        scr_names = ", ".join(s.get("title", k) for k, s in screens.items())
        if scr_names:
            ctk.CTkLabel(info, text=f"Экраны: {scr_names}", font=("Arial", 10),
                         text_color="#888", anchor="w").pack(anchor="w")

        # Кнопки
        btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        btn_frame.pack(side="right", padx=10, pady=10)

        ctk.CTkButton(btn_frame, text="Открыть", width=100,
                      command=lambda t=tpl: self._preview_template(t)).pack(pady=(0, 6))
        ctk.CTkButton(btn_frame, text="Выбрать", width=100,
                      fg_color="#2a6496", hover_color="#1a4d7a",
                      command=lambda t=tpl, c=card, n=name: self._select_template(t, c, n)).pack()

        self._template_cards[path.stem] = card

    def _select_template(self, tpl: dict, card: ctk.CTkFrame, name: str):
        # Сбрасываем предыдущий выбор
        for c in self._template_cards.values():
            c.configure(border_color="#333")
        card.configure(border_color="#2a6496")
        self._selected_template = tpl
        self.template_status.configure(
            text=f"✓ Шаблон выбран: {name}  — опишите изменения и нажмите Сгенерировать",
            text_color="#4caf50"
        )

    def _clear_template(self):
        for c in self._template_cards.values():
            c.configure(border_color="#333")
        self._selected_template = None
        self.template_status.configure(
            text="Выберите шаблон как основу (необязательно)", text_color="gray"
        )

    def _preview_template(self, tpl: dict):
        tpl_clean = {k: v for k, v in tpl.items() if k != "meta"}
        html_content = HTMLGenerator(tpl_clean).generate()
        filename = f"preview_{tpl.get('title', 'template').replace(' ', '_')}.html"
        filepath = OUTPUT_DIR / filename
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html_content)
        webbrowser.open(f"file://{filepath.absolute()}")

    # ── Tab: Референсы ─────────────────────────────────────────────────────

    def _build_refs_tab(self, parent):
        top = ctk.CTkFrame(parent, fg_color="transparent")
        top.pack(fill="x", pady=(0, 8))

        self.refs_status = ctk.CTkLabel(
            top, text="Выберите до 3 скриншотов — llava:7b вдохновится их стилем",
            font=("Arial", 12), text_color="gray"
        )
        self.refs_status.pack(side="left")

        ctk.CTkButton(top, text="+ Добавить", width=110, height=26,
                      command=self._add_ref_images).pack(side="right", padx=(6, 0))
        ctk.CTkButton(top, text="Сбросить", width=90, height=26,
                      command=self._clear_refs).pack(side="right")

        self.refs_frame = ctk.CTkScrollableFrame(parent)
        self.refs_frame.pack(fill="both", expand=True)
        self._load_refs_gallery()

    def _load_refs_gallery(self):
        for w in self.refs_frame.winfo_children():
            w.destroy()
        self._ref_buttons.clear()

        images = []
        for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp", "*.bmp"):
            images.extend(INSPIRATION_DIR.glob(ext))

        if not images:
            ctk.CTkLabel(
                self.refs_frame,
                text='Папка inspiration/ пуста.\nНажмите "+ Добавить" чтобы загрузить скриншоты интерфейсов.',
                font=("Arial", 13), text_color="gray"
            ).pack(expand=True, pady=40)
            return

        grid = ctk.CTkFrame(self.refs_frame, fg_color="transparent")
        grid.pack(fill="both", expand=True)

        for i, img_path in enumerate(sorted(images)):
            self._add_ref_card(grid, img_path, i)

    def _add_ref_card(self, parent, img_path: Path, idx: int):
        col = idx % 3
        row = idx // 3

        try:
            img = Image.open(img_path)
            img.thumbnail((200, 140))
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img,
                                   size=(200, 140))
        except Exception:
            ctk_img = None

        card = ctk.CTkFrame(parent, corner_radius=8, border_width=2,
                            border_color="#333", width=220, height=185)
        card.grid(row=row, column=col, padx=8, pady=8, sticky="nw")
        card.grid_propagate(False)

        if ctk_img:
            ctk.CTkLabel(card, image=ctk_img, text="").pack(pady=(8, 4))
        else:
            ctk.CTkLabel(card, text="[нет превью]", text_color="gray",
                         height=140).pack(pady=(8, 4))

        ctk.CTkLabel(card, text=img_path.name[:28],
                     font=("Arial", 9), text_color="gray").pack()

        self._ref_buttons[str(img_path)] = card

        card.bind("<Button-1>", lambda e, p=str(img_path), c=card: self._toggle_ref(p, c))
        for child in card.winfo_children():
            child.bind("<Button-1>", lambda e, p=str(img_path), c=card: self._toggle_ref(p, c))

    def _toggle_ref(self, path: str, card: ctk.CTkFrame):
        if path in self._selected_refs:
            self._selected_refs.remove(path)
            card.configure(border_color="#333")
        elif len(self._selected_refs) < 3:
            self._selected_refs.append(path)
            card.configure(border_color="#e94560")
        else:
            self.refs_status.configure(
                text="Максимум 3 референса. Снимите выбор с одного.",
                text_color="#f44336"
            )
            return
        n = len(self._selected_refs)
        if n:
            self.refs_status.configure(
                text=f"✓ Выбрано {n} референс(а) — llava:7b учтёт их стиль при генерации",
                text_color="#4caf50"
            )
        else:
            self.refs_status.configure(
                text="Выберите до 3 скриншотов — llava:7b вдохновится их стилем",
                text_color="gray"
            )

    def _add_ref_images(self):
        paths = filedialog.askopenfilenames(
            title="Выберите скриншоты интерфейсов",
            filetypes=[("Изображения", "*.png *.jpg *.jpeg *.webp *.bmp")]
        )
        for src in paths:
            dst = INSPIRATION_DIR / Path(src).name
            if not dst.exists():
                import shutil
                shutil.copy2(src, dst)
        self._load_refs_gallery()

    def _clear_refs(self):
        self._selected_refs.clear()
        for card in self._ref_buttons.values():
            card.configure(border_color="#333")
        self.refs_status.configure(
            text="Выберите до 3 скриншотов — llava:7b вдохновится их стилем",
            text_color="gray"
        )

    # ── Figma экспорт ──────────────────────────────────────────────────────

    def export_figma(self):
        if not self._current_spec:
            self.status.configure(text="Сначала сгенерируйте интерфейс")
            return
        try:
            filepath = export_to_svg(self._current_spec)
            self.status.configure(text=f"Figma SVG сохранён: {filepath.name}")
            webbrowser.open(f"file://{filepath.parent.absolute()}")
        except Exception as e:
            self.status.configure(text=f"Ошибка экспорта: {e}")

    # ── Генерация ──────────────────────────────────────────────────────────

    def _paste_to_textbox(self, event=None):
        try:
            text = self.clipboard_get()
            self.textbox.delete("0.0", "end")
            self.textbox.insert("0.0", text)
        except Exception:
            pass
        return "break"

    def generate(self):
        text = self.textbox.get("0.0", "end").strip()
        if not text:
            self.status.configure(text="Введите описание!")
            return

        if self._selected_refs:
            self.status.configure(text=f"⏳ llava анализирует {len(self._selected_refs)} референс(а)... (20–60 сек)")
        elif self._selected_template:
            self.status.configure(text="⏳ LLM адаптирует шаблон... (10–30 сек)")
        else:
            self.status.configure(text="⏳ LLM анализирует описание... (10–30 сек)")

        self.btn_generate.configure(state="disabled", text="⏳ Генерация...")

        def _worker():
            try:
                if self._selected_refs:
                    spec = parse_with_vision(text, self._selected_refs,
                                             text_model=self.model_var.get())
                elif self._selected_template:
                    spec = parse_with_template(text, self._selected_template,
                                               model=self.model_var.get())
                else:
                    spec = parse_description(text, model=self.model_var.get())
                self.after(0, lambda: self._on_generate_done(spec))
            except Exception as e:
                self.after(0, lambda err=e: self._on_generate_error(err))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_generate_done(self, spec: dict):
        self.btn_generate.configure(state="normal", text="Сгенерировать")

        self._current_spec = spec
        self.spec_editor.delete("0.0", "end")
        self.spec_editor.insert("0.0", json.dumps(spec, ensure_ascii=False, indent=2))
        self._render_and_open(spec)
        self.load_history()

    def _on_generate_error(self, err: Exception):
        self.btn_generate.configure(state="normal", text="Сгенерировать")
        self.status.configure(text=f"Ошибка: {err}")

    def generate_from_spec(self):
        raw = self.spec_editor.get("0.0", "end").strip()
        try:
            spec = json.loads(raw)
        except json.JSONDecodeError as e:
            self.status.configure(text=f"Ошибка JSON: {e}")
            return
        self._current_spec = spec
        self._render_and_open(spec)

    def _render_and_open(self, spec: dict) -> Path | None:
        self.status.configure(text=f"Генерация HTML для «{spec.get('title')}»...")
        self.update()

        html_content = HTMLGenerator(spec).generate()
        # Безопасное имя файла (убираем символы которые нельзя в имени файла)
        import re as _re
        safe_title = _re.sub(r'[\\/:*?"<>|]', "_", spec.get("title", "output"))
        filename = f"menu_{safe_title.replace(' ', '_')}.html"
        filepath = OUTPUT_DIR / filename
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html_content)

        # Обновляем последнюю сессию — записываем путь к HTML
        sessions = sorted(SESSIONS_DIR.glob("session_*.json"), reverse=True) if SESSIONS_DIR.exists() else []
        if sessions:
            update_session_html(sessions[0], str(filepath))

        self.status.configure(text=f"Готово! Открываю {filename}")
        webbrowser.open(f"file://{filepath.absolute()}")
        return filepath


if __name__ == "__main__":
    app = App()
    app.mainloop()
