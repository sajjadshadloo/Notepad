"""Watches dated to-do items and raises a Windows notification when due.

Deliberately cheap: the notes folder is scanned on a slow timer in a worker
thread, never on the UI thread and never during startup, because neither
typing nor launching the app may pay for this.
"""
import logging
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QSystemTrayIcon

import core.reminder_store as reminder_store
from core.file_service import read_text_file
from core.tasks import Task, due_within, parse_document

log = logging.getLogger(__name__)

NOTE_EXTENSIONS = (".txt", ".md", ".markdown")
# Checked often enough that a reminder feels punctual, rarely enough that the
# folder scan is invisible.
CHECK_INTERVAL_MS = 60_000
# The first scan waits, so launching the app is never slowed by it.
FIRST_CHECK_DELAY_MS = 8_000
# Announce a task slightly early rather than slightly late.
LEAD_MINUTES = 1


def scan_folder(root: str) -> list[Task]:
    """Every task in the notes tree. Runs off the UI thread."""
    found: list[Task] = []
    root_path = Path(root)
    if not root_path.exists():
        return found
    for path in root_path.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in NOTE_EXTENSIONS:
            continue
        try:
            loaded = read_text_file(path)
        except Exception:
            continue
        found.extend(parse_document(loaded.text, str(path.resolve())))
    return found


class _ScanWorker(QThread):
    scanned = pyqtSignal(list)

    def __init__(self, root: str, parent=None):
        super().__init__(parent)
        self._root = root

    def run(self):
        try:
            self.scanned.emit(scan_folder(self._root))
        except Exception:
            log.warning("Reminder scan failed", exc_info=True)
            self.scanned.emit([])


class ReminderService(QObject):
    """Emits ``task_activated`` with (path, line) when a notification is clicked."""

    task_activated = pyqtSignal(str, int)

    def __init__(self, root: str, icon: QIcon, parent=None):
        super().__init__(parent)
        self._root = root
        self._notified = reminder_store.load()
        self._worker: _ScanWorker | None = None
        self._last_task: Task | None = None

        self._tray = QSystemTrayIcon(icon, self)
        self._tray.setToolTip("Notepad Plus")
        self._tray.messageClicked.connect(self._open_last)
        self._tray.show()

        self._timer = QTimer(self, interval=CHECK_INTERVAL_MS)
        self._timer.timeout.connect(self.check_now)

    def start(self):
        QTimer.singleShot(FIRST_CHECK_DELAY_MS, self.check_now)
        self._timer.start()

    def set_root(self, root: str):
        self._root = root

    def check_now(self):
        if self._worker is not None and self._worker.isRunning():
            return
        self._worker = _ScanWorker(self._root, self)
        self._worker.scanned.connect(self._handle_tasks)
        self._worker.start()

    def _handle_tasks(self, tasks: list):
        due = due_within(tasks, datetime.now(), ahead_minutes=LEAD_MINUTES)
        fresh = [task for task in due if task.key() not in self._notified]
        if not fresh:
            return
        for task in fresh:
            self._notified.add(task.key())
        reminder_store.save(self._notified)
        self._announce(fresh)

    def _announce(self, tasks: list):
        self._last_task = tasks[0]
        if len(tasks) == 1:
            title = "یادآوری"
            body = tasks[0].text
        else:
            title = f"{len(tasks)} کار سررسید شد"
            body = "\n".join(t.text for t in tasks[:4])
        self._tray.showMessage(title, body, QSystemTrayIcon.MessageIcon.Information, 10_000)

    def _open_last(self):
        if self._last_task is not None and self._last_task.path:
            self.task_activated.emit(self._last_task.path, self._last_task.line_number)

    def stop(self):
        self._timer.stop()
        if self._worker is not None and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(2000)
        self._tray.hide()
