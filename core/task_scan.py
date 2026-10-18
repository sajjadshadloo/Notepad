"""Finding every task in the notes tree.

Pure logic on purpose: the walk is the expensive part of every task surface
— the sidebar, the tasks window, Ctrl+P — and all three want the same answer,
so it lives in one place with no Qt attached and can be tested directly.
"""
import logging
from pathlib import Path

from core.file_service import read_text_file
from core.tasks import Task, parse_document

log = logging.getLogger(__name__)

NOTE_EXTENSIONS = (".txt", ".md", ".markdown")


def scan_folder(root: str, cancelled=lambda: False) -> list[Task]:
    """Every task in the notes tree. Meant to run off the UI thread."""
    found: list[Task] = []
    root_path = Path(root)
    if not root_path.exists():
        return found
    for path in root_path.rglob("*"):
        if cancelled():
            return []
        if not path.is_file() or path.suffix.lower() not in NOTE_EXTENSIONS:
            continue
        try:
            loaded = read_text_file(path)
        except Exception:
            continue
        found.extend(parse_document(loaded.text, str(path.resolve())))
    return found
