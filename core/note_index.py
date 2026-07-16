import json
import os
from datetime import datetime, timezone
from pathlib import Path

from core.settings_manager import app_data_dir


def index_file() -> Path:
    return app_data_dir() / "notes_index.json"


def load() -> dict:
    path = index_file()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save(index: dict):
    path = index_file()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(index, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp, path)


def _normalize(path: str) -> str:
    return str(Path(path).resolve())


def _entry(index: dict, path: str) -> dict:
    key = _normalize(path)
    return index.setdefault(key, {"tags": [], "pinned": False, "last_opened": ""})


def touch(index: dict, path: str) -> dict:
    entry = _entry(index, path)
    entry["last_opened"] = datetime.now(timezone.utc).isoformat()
    save(index)
    return index


def set_pinned(index: dict, path: str, pinned: bool) -> dict:
    entry = _entry(index, path)
    entry["pinned"] = pinned
    save(index)
    return index


def add_tag(index: dict, path: str, tag: str) -> dict:
    tag = tag.strip()
    if not tag:
        return index
    entry = _entry(index, path)
    if tag not in entry["tags"]:
        entry["tags"].append(tag)
        save(index)
    return index


def remove_tag(index: dict, path: str, tag: str) -> dict:
    key = _normalize(path)
    entry = index.get(key)
    if entry and tag in entry.get("tags", []):
        entry["tags"].remove(tag)
        save(index)
    return index


def all_tags(index: dict) -> list[str]:
    tags = {tag for entry in index.values() for tag in entry.get("tags", [])}
    return sorted(tags)


def prune(index: dict, existing_paths: set[str]) -> dict:
    normalized_existing = {_normalize(p) for p in existing_paths}
    stale = [key for key in index if key not in normalized_existing]
    if not stale:
        return index
    for key in stale:
        del index[key]
    save(index)
    return index
