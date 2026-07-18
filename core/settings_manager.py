import json
import logging
import os
from pathlib import Path

from PyQt6.QtCore import QStandardPaths

from core.file_service import replace_with_retry

log = logging.getLogger(__name__)


def _documents_dir() -> Path:
    """The user's real Documents folder (follows OneDrive/folder redirection)."""
    base = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.DocumentsLocation
    )
    return Path(base) if base else Path.home() / "Documents"


DEFAULT_SAVE_DIR = str(_documents_dir() / "Notepad")

# Default before 2.5.0; silently upgraded to the Documents default on load.
_LEGACY_SAVE_DIR = r"C:\Notepad"

DEFAULTS = {
    "font_family": "Inter",
    "font_size": 14,
    "theme": "system",
    "word_wrap": True,
    "recent_files": [],
    "migration_checked": False,
    "window_geometry": "",
    "sidebar_visible": False,
    "sidebar_on_right": False,
    "notes_root": "",
    "splitter_state": "",
    "default_save_dir": DEFAULT_SAVE_DIR,
    "show_line_numbers": True,
}


def resolve_save_dir(settings: dict) -> Path:
    """Return the default save folder, creating it if needed.

    Falls back to ~/Notepad when the configured folder (Documents\\Notepad
    by default) cannot be created, e.g. no permission.
    """
    candidate = Path(settings.get("default_save_dir") or DEFAULT_SAVE_DIR)
    try:
        candidate.mkdir(parents=True, exist_ok=True)
        return candidate
    except OSError:
        fallback = Path.home() / "Notepad"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def app_data_dir() -> Path:
    override = os.environ.get("NOTEPAD_DATA_DIR")
    if override:
        path = Path(override)
    else:
        base = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.AppDataLocation
        )
        path = Path(base or (Path.home() / "AppData" / "Local" / "Notepad"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def user_fonts_dir() -> Path:
    """Folder where user-installed custom fonts live; loaded at startup."""
    path = app_data_dir() / "fonts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def settings_file() -> Path:
    return app_data_dir() / "settings.json"


def load() -> dict:
    path = settings_file()
    if not path.exists():
        return dict(DEFAULTS)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(DEFAULTS)
    merged = {**DEFAULTS, **data}
    # Old default migration: Vazirmatn stays the Persian fallback either
    # way, so switching the primary family to Inter only upgrades how
    # Latin text renders — exactly what the new default is for.
    if merged.get("font_family") == "Vazirmatn":
        merged["font_family"] = "Inter"
    # Old default migration: users who never picked a folder themselves move
    # from C:\Notepad to the Documents default. A custom choice is kept as-is.
    stored_dir = str(merged.get("default_save_dir") or "")
    if os.path.normcase(stored_dir) == os.path.normcase(_LEGACY_SAVE_DIR):
        merged["default_save_dir"] = DEFAULT_SAVE_DIR
    return merged


def save(settings: dict):
    """Best effort: settings are rewritten on every toggle, so a transient
    lock is retried and a persistent one logged rather than crashing."""
    path = settings_file()
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(
            json.dumps({**DEFAULTS, **settings}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        replace_with_retry(tmp, path)
    except OSError:
        log.warning("Could not save settings to %s", path, exc_info=True)
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def add_recent_file(settings: dict, file_path: str, limit: int = 10) -> dict:
    normalized = str(Path(file_path).resolve())
    recent = [
        item
        for item in settings.get("recent_files", [])
        if os.path.normcase(item) != os.path.normcase(normalized)
    ]
    settings["recent_files"] = [normalized, *recent][:limit]
    save(settings)
    return settings
