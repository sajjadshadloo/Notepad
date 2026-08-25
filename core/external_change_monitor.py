import os
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QFileSystemWatcher, QObject, pyqtSignal


@dataclass(frozen=True)
class FileStamp:
    modified_ns: int
    changed_ns: int
    size: int


def file_stamp(path: str | Path) -> FileStamp | None:
    """Return a cheap identity for the current on-disk version of a file."""
    try:
        stat = Path(path).stat()
    except OSError:
        return None
    return FileStamp(stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size)


class ExternalChangeMonitor(QObject):
    """Watch open documents and report changes not acknowledged by the app.

    QFileSystemWatcher can drop a watched path after an atomic replacement.
    The monitor therefore re-adds existing files after every event. A path is
    kept pending until the window has handled it, preventing duplicate prompts.
    """

    changed = pyqtSignal(str)
    missing = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._watcher = QFileSystemWatcher(self)
        self._watcher.fileChanged.connect(self._file_changed)
        self._known: dict[str, FileStamp | None] = {}
        self._pending: set[str] = set()

    @staticmethod
    def _normalize(path: str | Path) -> str:
        return os.path.normcase(str(Path(path).resolve()))

    def watched_paths(self) -> set[str]:
        return set(self._known)

    def watch(self, path: str | Path):
        normalized = self._normalize(path)
        stamp = file_stamp(normalized)
        self._known[normalized] = stamp
        self._pending.discard(normalized)
        if stamp is not None and normalized not in self._watcher.files():
            self._watcher.addPath(normalized)

    def unwatch(self, path: str | Path):
        normalized = self._normalize(path)
        self._known.pop(normalized, None)
        self._pending.discard(normalized)
        if normalized in self._watcher.files():
            self._watcher.removePath(normalized)

    def move(self, old_path: str | Path, new_path: str | Path):
        self.unwatch(old_path)
        self.watch(new_path)

    def acknowledge(self, path: str | Path):
        """Accept the current disk state after save, reload, or user choice."""
        normalized = self._normalize(path)
        if normalized not in self._known:
            return
        stamp = file_stamp(normalized)
        self._known[normalized] = stamp
        self._pending.discard(normalized)
        if stamp is not None and normalized not in self._watcher.files():
            self._watcher.addPath(normalized)

    def _file_changed(self, path: str):
        normalized = self._normalize(path)
        if normalized not in self._known:
            return

        current = file_stamp(normalized)
        if current is not None and normalized not in self._watcher.files():
            self._watcher.addPath(normalized)

        if current == self._known[normalized] or normalized in self._pending:
            return

        self._pending.add(normalized)
        if current is None:
            self.missing.emit(normalized)
        else:
            self.changed.emit(normalized)
