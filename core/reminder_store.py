"""Which reminders have already been shown.

Without this a due task would be announced again every time the folder is
scanned, and again on every restart. Keyed by file path plus task text, so
editing an unrelated line never re-fires a reminder that already went out.
"""
import json
import logging

from core.file_service import replace_with_retry
from core.settings_manager import app_data_dir

log = logging.getLogger(__name__)

# Keep the file small: a task notified long ago cannot come due again unless
# its text or date changes, which gives it a different key anyway.
MAX_ENTRIES = 500


def store_file():
    return app_data_dir() / "reminders.json"


def load() -> set[str]:
    path = store_file()
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    return set(data.get("notified", []))


def save(notified: set[str]):
    """Best effort — re-showing one reminder beats crashing the app."""
    path = store_file()
    tmp = path.with_suffix(".tmp")
    trimmed = list(notified)[-MAX_ENTRIES:]
    try:
        tmp.write_text(
            json.dumps({"notified": trimmed}, ensure_ascii=False),
            encoding="utf-8",
        )
        replace_with_retry(tmp, path)
    except OSError:
        log.warning("Could not save reminder state to %s", path, exc_info=True)
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
