import json
import re
from pathlib import Path

from PyQt6.QtGui import QTextDocument

from core.file_service import write_text_file_atomic


INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def legacy_notes_path() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "notes.json"


def legacy_notes_available() -> bool:
    path = legacy_notes_path()
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(data.get("notes"))


def sanitize_filename(value: str) -> str:
    name = INVALID_FILENAME.sub("_", value).strip().rstrip(".")
    return name or "بدون عنوان"


def html_to_markdown(content: str) -> str:
    if not content.lstrip().startswith("<"):
        return content
    document = QTextDocument()
    document.setHtml(content)
    return document.toMarkdown().rstrip() + "\n"


def _unique_path(folder: Path, title: str) -> Path:
    candidate = folder / f"{sanitize_filename(title)}.md"
    counter = 2
    while candidate.exists():
        candidate = folder / f"{sanitize_filename(title)} ({counter}).md"
        counter += 1
    return candidate


def migrate_legacy_notes(destination: str | Path) -> list[Path]:
    source = legacy_notes_path()
    data = json.loads(source.read_text(encoding="utf-8"))
    root = Path(destination)
    root.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []

    for note in data.get("notes", []):
        if note.get("deleted"):
            folder = root / "حذف‌شده‌ها"
        else:
            folder = root / sanitize_filename(note.get("category") or "عمومی")
        folder.mkdir(parents=True, exist_ok=True)
        path = _unique_path(folder, note.get("title") or "بدون عنوان")
        write_text_file_atomic(path, html_to_markdown(note.get("content", "")), "utf-8")
        created.append(path)
    return created
