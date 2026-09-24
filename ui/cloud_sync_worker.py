"""Run network and disk sync away from the Qt event loop."""

from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from core.cloud_sync import CloudApi, sync_once
from core.cloud_sync_status import record_sync_status


class CloudSyncWorker(QThread):
    completed = pyqtSignal(object, str)

    def __init__(self, root: str, state_file: Path, url: str, key: str,
                 protected: set[str], parent=None):
        super().__init__(parent)
        self.root = Path(root)
        self.state_file = state_file
        self.url = url
        self.key = key
        self.protected = protected

    def run(self):
        api = CloudApi(self.url, self.key)
        try:
            result = sync_once(self.root, self.state_file, api, self.protected)
            record_sync_status(self.state_file.with_name("cloud_sync_status.json"), api, result)
            self.completed.emit(result, "")
        except Exception as exc:
            record_sync_status(self.state_file.with_name("cloud_sync_status.json"), api,
                               error=str(exc))
            self.completed.emit(None, str(exc))
