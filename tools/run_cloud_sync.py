"""One sync pass for Task Scheduler while the installed editor is running."""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PyQt6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import cloud_config
from core.cloud_sync import CloudApi, sync_once
from core.cloud_sync_status import record_sync_status
from core.settings_manager import app_data_dir, load, resolve_save_dir


def main():
    app = QApplication([])
    app.setApplicationName("Notepad Plus")
    app.setOrganizationName("Sajjad")
    data = app_data_dir()
    config = cloud_config.load()
    if not config.enabled or not (config.url and config.key):
        return 0
    logger = logging.getLogger("notepad.cloud_sync")
    logger.setLevel(logging.INFO)
    logger.addHandler(RotatingFileHandler(data / "cloud_sync.log", maxBytes=100_000,
                                          backupCount=1, encoding="utf-8"))
    settings = load()
    root = Path(settings.get("notes_root") or resolve_save_dir(settings))
    api = CloudApi(config.url, config.key, config.proxy)
    try:
        result = sync_once(root, data / "cloud_sync_state.json", api)
        record_sync_status(data / "cloud_sync_status.json", api, result)
        logger.info("downloaded=%s uploaded=%s deleted=%s conflicts=%s skipped=%s",
                    result.downloaded, result.uploaded, result.deleted,
                    result.conflicts, result.skipped)
        return 0
    except Exception as exc:
        record_sync_status(data / "cloud_sync_status.json", api, error=str(exc))
        logger.warning("Sync pending: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
