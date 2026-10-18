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
    # Latin and Persian are chosen separately: one family rarely does both
    # well, and tying them together meant picking a good English face cost
    # you the Persian one. The editor builds a fallback chain from the pair.
    "font_family_latin": "Inter",
    "font_family_persian": "Vazirmatn",
    # CSS pixels since 4.3 ("font_size_unit": "px" marks a converted file;
    # it is deliberately not a default, so an older file is still converted).
    "font_size": 14.5,
    "close_to_tray": True,
    "home_view": "grid",
    "pinned_notes": [],
    "display_name": "",
    "theme": "system",
    # Which set of eleven colour tokens the theme picks its half from.
    # See ui.styles.PALETTES; an unknown name falls back to the default.
    "accent_palette": "graphite",
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
    # Documents open right-to-left. "auto" decides per paragraph, which reads
    # as the document jumping sides while you write; "rtl" keeps the whole
    # document on one side until you say otherwise. Code blocks stay LTR
    # either way, and a per-file override is remembered in the note index.
    "default_direction": "rtl",
    # The app stays in the tray when its window is closed. Explaining
    # that is useful exactly once, so the balloon is latched here.
    "tray_notice_shown": False,
    # One-time tidy-up of the empty day notes 3.x created on every
    # calendar click. Latched so it runs once, not every launch.
    "daily_cleanup_done": False,
    # Which page the window opens on: "home" (notes beside today) or
    # "editor". Whichever you left it on is the one you want back.
    "page": "home",
    # The small desktop panel showing today. Off until asked for.
    "day_widget": False,
    # Where the panel was dragged to. Empty means the default corner.
    "day_widget_position": [],
    "check_app_updates": True,
    "last_app_update_check": 0,
}

DIRECTION_MODES = ("rtl", "ltr", "auto")


def font_chain(settings: dict, *, extra: tuple[str, ...] = ()) -> list[str]:
    """Family fallback list for both scripts, most specific first.

    Qt resolves families per character, so the Latin choice leads and the
    Persian one picks up everything it lacks a glyph for. Segoe UI trails
    both on purpose: it *does* carry Arabic glyphs, so putting it earlier
    would quietly win Persian text away from the chosen Persian family.
    """
    families = [
        settings.get("font_family_latin") or DEFAULTS["font_family_latin"],
        settings.get("font_family_persian") or DEFAULTS["font_family_persian"],
        DEFAULTS["font_family_persian"],
        "Segoe UI",
        *extra,
    ]
    # Keep the first occurrence of each, drop blanks.
    return list(dict.fromkeys(name for name in families if name))


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
    if not isinstance(data, dict):
        return dict(DEFAULTS)
    merged = {**DEFAULTS, **data}
    # Pre-2.7.0 stored a single "font_family" that fronted a fixed fallback
    # chain. Carry it over as the Latin choice — Persian always came from
    # Vazirmatn behind it, which is exactly the new default for that half.
    legacy_family = merged.pop("font_family", None)
    if legacy_family and "font_family_latin" not in data:
        # "Vazirmatn" as the primary was the pre-2.4.0 default, and it only
        # ever affected Latin text; the 2.4.0 upgrade to Inter still applies.
        merged["font_family_latin"] = (
            DEFAULTS["font_family_latin"]
            if legacy_family == "Vazirmatn"
            else legacy_family
        )
    # Old default migration: users who never picked a folder themselves move
    # from C:\Notepad to the Documents default. A custom choice is kept as-is.
    stored_dir = str(merged.get("default_save_dir") or "")
    if os.path.normcase(stored_dir) == os.path.normcase(_LEGACY_SAVE_DIR):
        merged["default_save_dir"] = DEFAULT_SAVE_DIR
    if merged.get("default_direction") not in DIRECTION_MODES:
        merged["default_direction"] = DEFAULTS["default_direction"]
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
