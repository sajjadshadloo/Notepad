import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from core.file_service import replace_with_retry
from core.settings_manager import app_data_dir

log = logging.getLogger(__name__)


def index_file() -> Path:
    return app_data_dir() / "notes_index.json"


# Written by 2.6.0 and earlier. Tags and pins were removed in 3.0 — they had
# to be maintained by hand, so in practice they never were — and folders in
# the notes tree took over the job.
_RETIRED_FIELDS = ("tags", "pinned")


def load() -> dict:
    path = index_file()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    data = {key: value for key, value in data.items() if isinstance(value, dict)}
    for entry in data.values():
        if isinstance(entry, dict):
            for field in _RETIRED_FIELDS:
                entry.pop(field, None)
    return data


def save(index: dict):
    """Best effort: losing a timestamp beats crashing the app, so a
    persistent lock on the index file is logged instead of raised."""
    path = index_file()
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(
            json.dumps(index, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        replace_with_retry(tmp, path)
    except OSError:
        log.warning("Could not save the note index to %s", path, exc_info=True)
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def _normalize(path: str) -> str:
    return str(Path(path).resolve())


def _entry(index: dict, path: str) -> dict:
    key = _normalize(path)
    return index.setdefault(key, {"last_opened": ""})


def set_direction(index: dict, path: str, mode: str) -> dict:
    """Remember the text direction chosen for one file.

    Documents default to right-to-left, so an English file only has to be
    switched once — reopening it brings the choice back.
    """
    entry = _entry(index, path)
    if entry.get("direction") != mode:
        entry["direction"] = mode
        save(index)
    return index


def direction_for(index: dict, path: str) -> str | None:
    """The remembered direction for a file, or None when it has none."""
    entry = index.get(_normalize(path))
    return entry.get("direction") if entry else None


def touch(index: dict, path: str) -> dict:
    entry = _entry(index, path)
    entry["last_opened"] = datetime.now(timezone.utc).isoformat()
    save(index)
    return index


def prune(index: dict, existing_paths: set[str]) -> dict:
    normalized_existing = {_normalize(p) for p in existing_paths}
    stale = [key for key in index if key not in normalized_existing]
    if not stale:
        return index
    for key in stale:
        del index[key]
    save(index)
    return index
