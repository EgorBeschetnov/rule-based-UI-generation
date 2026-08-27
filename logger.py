import json
from datetime import datetime
from pathlib import Path

SESSIONS_DIR = Path("sessions")
SESSIONS_DIR.mkdir(exist_ok=True)

# Обратная совместимость: если ещё есть старая папка logs/ — переносим файлы
_OLD_DIR = Path("logs")
if _OLD_DIR.exists():
    for old_file in _OLD_DIR.glob("*.json"):
        new_name = old_file.name.replace("log_", "session_", 1)
        new_path = SESSIONS_DIR / new_name
        if not new_path.exists():
            old_file.rename(new_path)
    try:
        _OLD_DIR.rmdir()  # удаляем если пустая
    except OSError:
        pass


def log_interaction(
    user_input: str,
    model: str,
    raw_response: str,
    parsed_json: dict,
    success: bool,
    html_file: str = "",
) -> Path:
    """
    Сохраняет сессию генерации в JSON-файл.
    Возвращает путь к созданному файлу.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    title = parsed_json.get("title", "—") if isinstance(parsed_json, dict) else "—"

    entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "model": model,
        "title": title,
        "success": success,
        "html_file": html_file,
        "user_input": user_input,
        "parsed_json": parsed_json,
        "raw_response": raw_response,
    }

    filename = SESSIONS_DIR / f"session_{timestamp}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(entry, f, ensure_ascii=False, indent=2)

    print(f"Сессия сохранена: {filename}")
    return filename


def update_session_html(session_path: Path, html_file: str) -> None:
    """Обновляет поле html_file в уже сохранённом файле сессии."""
    if not session_path or not session_path.exists():
        return
    try:
        with open(session_path, encoding="utf-8") as f:
            data = json.load(f)
        data["html_file"] = html_file
        with open(session_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Не удалось обновить html_file в сессии: {e}")
