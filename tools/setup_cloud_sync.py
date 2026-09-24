"""Pair this Windows installation with the Cloudflare Worker without printing keys."""

import json
import secrets
import subprocess
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from core.file_service import write_text_file_atomic
from core.settings_manager import app_data_dir


WORKER_URL = "https://notepad-plus-bot.sajadshadlloo23.workers.dev"


def main():
    app = QApplication([])
    app.setApplicationName("Notepad Plus")
    app.setOrganizationName("Sajjad")
    target = app_data_dir() / "cloud_sync.json"
    if target.exists():
        current = json.loads(target.read_text(encoding="utf-8"))
        key = current["key"]
    else:
        current = {}
        key = secrets.token_urlsafe(48)
    cloudflare_dir = Path(__file__).resolve().parents[1] / "cloudflare"
    result = subprocess.run(
        ["npx.cmd", "wrangler", "secret", "put", "DESKTOP_SYNC_KEY"],
        input=key + "\n", text=True, cwd=cloudflare_dir,
        capture_output=True, encoding="utf-8", errors="replace", timeout=120,
    )
    if result.returncode:
        raise RuntimeError("Could not configure the Worker secret: " + result.stderr[-500:])
    write_text_file_atomic(target, json.dumps({"url": WORKER_URL, "key": key,
                                              "enabled": bool(current.get("enabled"))}, indent=2))
    print("Desktop sync credential configured; existing activation preserved.")


if __name__ == "__main__":
    main()
