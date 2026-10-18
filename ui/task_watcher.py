"""Keeps the task counts fresh while the window is open.

What this is *not* any more: 3.x scanned the notes folder in order to raise
Windows notifications and mirror deadlines into Task Scheduler. 4.0 dropped
both — the app now stays in the tray, so the tasks you have are always a
click away and a notification is one interruption too many for something
already on screen.

What is left is the part that was always earning its keep: one folder walk on
a slow timer, off the UI thread, feeding the progress meter, the tasks button
and Ctrl+P.
"""
import logging
from datetime import datetime

from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal

from core.task_scan import scan_folder
from core.tasks import Task, sort_for_today, today_progress
from ui.background import start_background

log = logging.getLogger(__name__)

# Slow on purpose: nothing here is time-critical now that reminders are gone.
# It exists to keep a counter honest, not to catch a deadline to the minute.
RESCAN_INTERVAL_MS = 120_000
# The first walk waits, so launching the app never pays for it.
FIRST_SCAN_DELAY_MS = 8_000


class _ScanWorker(QThread):
    scanned = pyqtSignal(list)

    def __init__(self, root: str, parent=None):
        super().__init__(parent)
        self._root = root

    def run(self):
        try:
            tasks = scan_folder(self._root, self.isInterruptionRequested)
            if not self.isInterruptionRequested():
                self.scanned.emit(tasks)
        except Exception:
            log.warning("Task scan failed", exc_info=True)
            self.scanned.emit([])


class TaskWatcher(QObject):
    # (done, total) for today — drives the progress meter in the tab strip.
    progress_changed = pyqtSignal(int, int)
    # Open tasks due today or earlier — the badge on the rail's tasks button.
    open_count_changed = pyqtSignal(int)
    # A scan finished; whatever is on screen may now be stale.
    scanned = pyqtSignal()

    def __init__(self, root: str, parent=None):
        super().__init__(parent)
        self._root = root
        self._tasks: list[Task] = []
        self._worker: _ScanWorker | None = None
        self._stopped = False
        self._scan_again = False
        self._timer = QTimer(self, interval=RESCAN_INTERVAL_MS)
        self._timer.timeout.connect(self.check_now)

    def start(self):
        QTimer.singleShot(FIRST_SCAN_DELAY_MS, self.check_now)
        self._timer.start()

    def set_root(self, root: str):
        self._root = root
        self._tasks = []
        if self._worker is not None:
            self._worker.requestInterruption()
        self.check_now()

    def open_tasks(self) -> list[Task]:
        """Unfinished tasks from the last scan, most urgent first.

        Handed out rather than rescanned: Ctrl+P has to feel instant, and
        this is already in memory.
        """
        return sort_for_today(list(self._tasks), datetime.now())

    def all_tasks(self) -> list[Task]:
        """Everything from the last scan, finished included.

        The calendar wants the finished ones too: a day that shows only what
        is left looks empty by evening, which is the opposite of the point.
        """
        return list(self._tasks)

    def check_now(self):
        if self._stopped:
            return
        if self._worker is not None:
            self._scan_again = True
            return
        self._worker = _ScanWorker(self._root, self)
        self._worker.scanned.connect(self._handle_tasks)
        self._worker.finished.connect(self._scan_finished)
        start_background(self._worker)

    def _scan_finished(self):
        self._worker = None
        if self._scan_again:
            self._scan_again = False
            self.check_now()

    def _handle_tasks(self, tasks: list):
        sender = self.sender()
        if self._stopped or (isinstance(sender, _ScanWorker) and sender._root != self._root):
            return
        self._tasks = tasks
        done, total = today_progress(tasks, datetime.now())
        self.progress_changed.emit(done, total)
        # Due today or already late — what the rail badge and the greeting
        # mean by «کار برای امروز مانده». Undated work is not pressing.
        today = datetime.now().date()
        self.open_count_changed.emit(
            sum(1 for t in tasks if not t.done and t.due and t.due.date() <= today)
        )
        self.scanned.emit()

    # A cold first walk of a big notes folder can take seconds; a thread
    # destroyed while still walking aborts the whole process.
    STOP_WAIT_MS = 15_000

    def stop(self):
        self._stopped = True
        self._timer.stop()
        if self._worker is not None and self._worker.isRunning():
            if isinstance(self._worker, QThread):
                self._worker.requestInterruption()
            if not self._worker.wait(self.STOP_WAIT_MS):
                log.warning("Task scan still running at exit")
