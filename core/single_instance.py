import json
import logging
from pathlib import Path
from time import monotonic, sleep

from PyQt6.QtCore import QCoreApplication, QEventLoop, QLockFile, QObject, pyqtSignal
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

log = logging.getLogger(__name__)

SERVER_NAME = "Sajjad.NotepadPlus"


class SingleInstanceGuard(QObject):
    """One running app per user.

    The first launch takes a lock file and listens on a local socket; every
    later launch hands its file paths to that instance and exits. This also
    stops two simultaneous launches from fighting over the settings and
    note-index files (the WinError 32 startup crash).
    """

    files_received = pyqtSignal(list)

    def __init__(self, data_dir: Path | str, server_name: str = SERVER_NAME, parent=None):
        super().__init__(parent)
        self._server_name = server_name
        # tryLock detects and removes locks left behind by a crashed process,
        # so a crash never blocks the next launch. Stale-by-age must be off:
        # the default 30s would let a second launch steal the lock from a
        # perfectly healthy long-running instance.
        self._lock = QLockFile(str(Path(data_dir) / "instance.lock"))
        self._lock.setStaleLockTime(0)
        self._server: QLocalServer | None = None

    def acquire(self) -> bool:
        return self._lock.tryLock(0)

    def notify_running_instance(self, files: list[str], attempts: int = 10) -> bool:
        """Send file paths to the lock owner. Retries because the owner may
        still be starting up and not listening yet."""
        payload = json.dumps({"files": files}).encode("utf-8")
        for attempt in range(attempts):
            socket = QLocalSocket()
            socket.connectToServer(self._server_name)
            if socket.waitForConnected(250):
                socket.write(payload)
                socket.flush()
                # Qt6 on Windows completes local-socket writes through the
                # event loop, not flush()/waitForBytesWritten(), so pump
                # events until the payload has actually left the buffer —
                # otherwise destroying the socket drops it.
                deadline = monotonic() + 1.0
                while socket.bytesToWrite() > 0 and monotonic() < deadline:
                    QCoreApplication.processEvents(
                        QEventLoop.ProcessEventsFlag.AllEvents, 50
                    )
                socket.disconnectFromServer()
                if socket.state() != QLocalSocket.LocalSocketState.UnconnectedState:
                    socket.waitForDisconnected(500)
                return True
            if attempt < attempts - 1:
                sleep(0.2)
        return False

    def listen(self):
        QLocalServer.removeServer(self._server_name)
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._drain_connections)
        if not self._server.listen(self._server_name):
            log.warning(
                "Single-instance server could not listen: %s",
                self._server.errorString(),
            )

    def _drain_connections(self):
        while self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            # The payload usually arrived with the connection; on Windows
            # waitForReadyRead can report False even when data is already
            # buffered or still in flight, so poll briefly instead of
            # trusting a single wait.
            for _ in range(5):
                if socket.bytesAvailable() > 0:
                    break
                socket.waitForReadyRead(100)
            files: list[str] = []
            try:
                message = json.loads(bytes(socket.readAll().data()).decode("utf-8"))
                files = [f for f in message.get("files", []) if isinstance(f, str)]
            except (ValueError, AttributeError):
                log.warning("Ignoring malformed message from another instance.")
            socket.close()
            # Empty list still means "bring the window to the front".
            self.files_received.emit(files)

    def release(self):
        if self._server:
            self._server.close()
            self._server = None
        self._lock.unlock()
