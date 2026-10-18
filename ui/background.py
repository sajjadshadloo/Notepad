"""Keep read-only jobs alive until their threads have actually finished."""
import logging

from PyQt6.QtCore import QThread, pyqtSignal, pyqtSlot

log = logging.getLogger(__name__)
_running: set[QThread] = set()


def start_background(worker: QThread):
    # A window can close while a filesystem/browser call is blocked. A running
    # QThread must never be destroyed with that window, nor forcibly terminated.
    worker.setParent(None)
    _running.add(worker)
    worker.finished.connect(worker.deleteLater)
    worker.finished.connect(lambda: _running.discard(worker))
    worker.start()
    return worker


class ReadWorker(QThread):
    completed = pyqtSignal(object, str)

    def __init__(self, read):
        super().__init__()
        self._read = read

    @pyqtSlot()
    def cancel(self):
        self.requestInterruption()

    def run(self):
        try:
            result = self._read(self.isInterruptionRequested)
            if not self.isInterruptionRequested():
                self.completed.emit(result, "")
        except Exception:
            log.warning("Background read failed", exc_info=True)
            if not self.isInterruptionRequested():
                self.completed.emit(None, "خواندن اطلاعات انجام نشد؛ دوباره تلاش کن.")
