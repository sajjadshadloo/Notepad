"""Watches dated to-do items and raises a Windows notification when due.

Deliberately cheap: the notes folder is scanned on a slow timer in a worker
thread, never on the UI thread and never during startup, because neither
typing nor launching the app may pay for this.
"""
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QSystemTrayIcon

import core.reminder_store as reminder_store
import core.win_scheduler as win_scheduler
from core.settings_manager import app_data_dir
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
# Only the near future is handed to Windows; further out, the in-app check
# picks it up when the day arrives.
SCHEDULE_HORIZON_DAYS = 60


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
    scanned_once = pyqtSignal()

    def __init__(self, root: str, icon: QIcon, parent=None, schedule: bool = True):
        super().__init__(parent)
        self._root = root
        self._schedule = schedule
        self._by_id: dict[str, Task] = {}
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
        self._by_id = {win_scheduler.task_id(t.key()): t for t in tasks}
        self.scanned_once.emit()
        if self._schedule:
            self._sync_schedule(tasks)
        self._notify(due_within(tasks, datetime.now(), ahead_minutes=LEAD_MINUTES))

    def _notify(self, tasks: list) -> bool:
        """Announce whatever has not been announced yet, and record it.

        Both routes in — the periodic scan and a --remind launch — go through
        here. When they did not, a scheduled reminder announced itself
        without being recorded and the next scan, a minute later, said it all
        over again.
        """
        fresh = [task for task in tasks if task.key() not in self._notified]
        if not fresh:
            return False
        for task in fresh:
            self._notified.add(task.key())
        reminder_store.save(self._notified)
        self._announce(fresh)
        return True

    def _announce(self, tasks: list):
        # Logged so a missed reminder can be told apart from one that fired
        # into a disabled notification area.
        log.info(
            "Notifying: %s", ", ".join(repr(task.text) for task in tasks[:4])
        )
        self._last_task = tasks[0]
        if len(tasks) == 1:
            title = "یادآوری"
            body = tasks[0].text
        else:
            title = f"{len(tasks)} کار سررسید شد"
            body = "\n".join(t.text for t in tasks[:4])
        self._tray.showMessage(title, body, QSystemTrayIcon.MessageIcon.Information, 10_000)

    def _sync_schedule(self, tasks: list):
        """Mirror upcoming reminders into Windows Task Scheduler.

        Only what is not already registered gets created, and anything
        Windows still holds for a task that has been done, deleted or moved
        is removed — otherwise a finished task would keep firing forever.
        """
        if not win_scheduler.available():
            log.info(
                "Scheduling unavailable (frozen=%s platform=%s)",
                getattr(sys, "frozen", False),
                sys.platform,
            )
            return
        now = datetime.now()
        horizon = now + timedelta(days=SCHEDULE_HORIZON_DAYS)
        wanted = {
            win_scheduler.task_id(task.key()): task
            for task in tasks
            if task.due and not task.done and now < task.due <= horizon
        }
        wanted = dict(list(wanted.items())[: win_scheduler.MAX_TASKS])
        existing = win_scheduler.registered_ids()

        for identifier in existing - set(wanted):
            win_scheduler.unregister(identifier)
        temp_dir = app_data_dir() / "schedule"
        created = 0
        for identifier, task in wanted.items():
            if identifier in existing:
                continue
            if win_scheduler.register(task.key(), task.text, task.due, temp_dir):
                created += 1
            else:
                log.warning("Could not schedule %r for %s", task.text, task.due)
        log.info(
            "Reminders: %d upcoming, %d already scheduled, %d created, %d removed",
            len(wanted), len(existing & set(wanted)), created,
            len(existing - set(wanted)),
        )

    def show_by_id(self, identifier: str) -> bool:
        """Announce one scheduled reminder — the ``--remind`` entry point."""
        task = self._by_id.get(identifier)
        if task is None:
            return False
        # Returns True even when it was already announced: the caller only
        # needs to know the id was recognised, so it stops waiting for a scan.
        self._notify([task])
        return True

    def _open_last(self):
        if self._last_task is not None and self._last_task.path:
            self.task_activated.emit(self._last_task.path, self._last_task.line_number)

    def set_scheduling(self, enabled: bool):
        self._schedule = enabled

    def clear_schedule(self):
        win_scheduler.clear_all()

    def stop(self):
        self._timer.stop()
        if self._worker is not None and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(2000)
        self._tray.hide()
