"""Record the desktop mirror's last pass locally and for the Mini App."""

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from core.file_service import write_text_file_atomic


def record_sync_status(path: Path, api, result=None, error: str = "") -> dict:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        previous = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, ValueError):
        previous = {}
    counts = asdict(result) if result is not None else {
        "downloaded": 0, "uploaded": 0, "deleted": 0, "conflicts": 0, "skipped": 0,
    }
    state = "error" if error else "attention" if counts["conflicts"] or counts["skipped"] else "ok"
    status = {
        "checked_at": now,
        "completed_at": previous.get("completed_at") if error else now,
        "state": state,
        **counts,
        "error": error[:160],
    }
    write_text_file_atomic(path, json.dumps(status, ensure_ascii=False, indent=2))
    try:
        api.call("/sync-status", "POST", {key: status[key] for key in
                 ("state", "downloaded", "uploaded", "deleted", "conflicts", "skipped", "error")})
    except Exception:
        # A local pass must remain successful if only the status report fails.
        pass
    return status
