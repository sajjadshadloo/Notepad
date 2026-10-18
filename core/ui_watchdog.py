"""Record a stalled GUI's stack once, without reading document contents."""
import logging
import sys
import threading
import time
import traceback

from PyQt6.QtCore import QObject, QTimer
from pathlib import Path

log = logging.getLogger("notepad.responsiveness")


class UiWatchdog(QObject):
    def __init__(self, parent=None, threshold=8.0):
        super().__init__(parent)
        self._threshold = threshold
        self._thread_id = threading.get_ident()
        self._heartbeat = time.monotonic()
        self._reported = False
        self._stopped = threading.Event()
        self._timer = QTimer(self, interval=1000)
        self._timer.timeout.connect(self._beat)
        self._thread = None

    def start(self):
        self._beat()
        self._timer.start()
        self._thread = threading.Thread(target=self._watch, name="UI watchdog", daemon=True)
        self._thread.start()

    def _beat(self):
        self._heartbeat = time.monotonic()
        self._reported = False

    def _watch(self):
        while not self._stopped.wait(1):
            self._check()

    def _check(self):
        delay = time.monotonic() - self._heartbeat
        if delay >= self._threshold and not self._reported:
            self._reported = True
            frame = sys._current_frames().get(self._thread_id)
            if frame is not None:
                # No locals, editor text, cloud keys, or credentials.
                stack = [f'{Path(f.f_code.co_filename).name}:{line} in {f.f_code.co_name}'
                         for f, line in traceback.walk_stack(frame)]
                log.error("UI unresponsive for %.1f seconds\n%s", delay, "".join(traceback.format_stack(frame)),
                    extra={'event': 'ui.stalled', 'duration_ms': delay * 1000, 'diagnostic_stack': stack})

    def stop(self):
        self._timer.stop()
        self._stopped.set()
