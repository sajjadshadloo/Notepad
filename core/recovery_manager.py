import json
import logging
from pathlib import Path
from uuid import uuid4

from core.file_service import replace_with_retry
from core.settings_manager import app_data_dir

log = logging.getLogger(__name__)


def recovery_dir() -> Path:
    path = app_data_dir() / "recovery"
    path.mkdir(parents=True, exist_ok=True)
    return path


def new_recovery_id() -> str:
    return uuid4().hex


def recovery_path(recovery_id: str) -> Path:
    return recovery_dir() / f"{recovery_id}.json"


def save_recovery(
    recovery_id: str,
    *,
    text: str,
    path: str | None,
    encoding: str,
    title: str,
    direction_mode: str,
):
    destination = recovery_path(recovery_id)
    temporary = destination.with_suffix(".tmp")
    payload = {
        "id": recovery_id,
        "text": text,
        "path": path,
        "encoding": encoding,
        "title": title,
        "direction_mode": direction_mode,
    }
    # Best effort: the snapshot timer fires every 10 seconds, so one missed
    # write is recovered by the next tick — never worth crashing over.
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
        replace_with_retry(temporary, destination)
    except OSError:
        log.warning("Could not write recovery snapshot %s", destination, exc_info=True)
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def remove_recovery(recovery_id: str):
    try:
        recovery_path(recovery_id).unlink()
    except FileNotFoundError:
        pass


def load_recoveries() -> list[dict]:
    recovered = []
    for path in recovery_dir().glob("*.json"):
        try:
            recovered.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            try:
                path.unlink()
            except OSError:
                pass
    return recovered


def clear_all():
    for path in recovery_dir().glob("*.json"):
        try:
            path.unlink()
        except OSError:
            pass
