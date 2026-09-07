import os
import time

from PyQt6.QtCore import QEventLoop

import core.file_service as file_service
import core.note_index as note_index
from core.single_instance import SingleInstanceGuard


def test_second_instance_hands_files_to_the_first(tmp_path, qapp):
    server_name = f"NotepadTest-{os.getpid()}"
    first = SingleInstanceGuard(tmp_path, server_name=server_name)
    assert first.acquire()
    first.listen()
    received: list[str] = []
    first.files_received.connect(received.extend)

    second = SingleInstanceGuard(tmp_path, server_name=server_name)
    assert not second.acquire()
    assert second.notify_running_instance(["C:\\notes\\a.txt"], attempts=3)

    deadline = time.monotonic() + 3
    while not received and time.monotonic() < deadline:
        qapp.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
        time.sleep(0.02)
    assert received == ["C:\\notes\\a.txt"]
    first.release()


def test_lock_is_free_again_after_release(tmp_path, qapp):
    server_name = f"NotepadTest2-{os.getpid()}"
    first = SingleInstanceGuard(tmp_path, server_name=server_name)
    assert first.acquire()
    first.release()

    second = SingleInstanceGuard(tmp_path, server_name=server_name)
    assert second.acquire()
    second.release()


def test_notify_without_running_instance_reports_failure(tmp_path, qapp):
    guard = SingleInstanceGuard(tmp_path, server_name="NotepadTest-nobody-home")
    assert not guard.notify_running_instance(["x.txt"], attempts=1)


def test_replace_with_retry_rides_out_transient_locks(tmp_path, monkeypatch):
    calls = {"count": 0}
    real_replace = os.replace

    def flaky(source, target):
        calls["count"] += 1
        if calls["count"] < 3:
            raise OSError(0, "The process cannot access the file", None, 32)
        real_replace(source, target)

    monkeypatch.setattr(os, "replace", flaky)
    source = tmp_path / "a.tmp"
    source.write_text("payload", encoding="utf-8")
    target = tmp_path / "a.json"

    file_service.replace_with_retry(source, target, first_delay=0.001)

    assert target.read_text(encoding="utf-8") == "payload"
    assert calls["count"] == 3


def test_replace_with_retry_raises_other_errors_immediately(tmp_path, monkeypatch):
    calls = {"count": 0}

    def missing(source, target):
        calls["count"] += 1
        raise FileNotFoundError(2, "No such file")

    monkeypatch.setattr(os, "replace", missing)
    try:
        file_service.replace_with_retry(tmp_path / "a", tmp_path / "b", first_delay=0.001)
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("expected FileNotFoundError")
    assert calls["count"] == 1


def test_note_index_save_failure_does_not_crash(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTEPAD_DATA_DIR", str(tmp_path))
    note = tmp_path / "note.md"
    note.write_text("hello", encoding="utf-8")

    def locked(source, target, **_kwargs):
        raise OSError(0, "The process cannot access the file", None, 32)

    monkeypatch.setattr(note_index, "replace_with_retry", locked)

    index: dict = {}
    note_index.touch(index, str(note))  # must not raise

    assert str(note.resolve()) in index


# Message framing
#
# The reader used to stop as soon as any byte had arrived, so a payload that
# reached it in two pieces parsed as truncated JSON and its paths were
# silently dropped. That was rare while the app was usually closed; from 4.0
# it stays in the tray, so every file opened from Explorer takes this path.

class _FakeSocket:
    """Hands out a payload in pieces, the way a real local socket can."""

    def __init__(self, chunks, connected_after=True):
        self._chunks = list(chunks)
        self._connected_after = connected_after
        self.waits = 0

    def readAll(self):
        chunk = self._chunks.pop(0) if self._chunks else b""

        class _Data:
            def __init__(self, payload):
                self._payload = payload

            def data(self):
                return self._payload

        return _Data(chunk)

    def waitForReadyRead(self, _ms):
        self.waits += 1
        return bool(self._chunks)

    def state(self):
        from PyQt6.QtNetwork import QLocalSocket

        return (
            QLocalSocket.LocalSocketState.ConnectedState
            if self._connected_after
            else QLocalSocket.LocalSocketState.UnconnectedState
        )


def test_a_message_split_across_chunks_is_reassembled():
    from core.single_instance import TERMINATOR, _files_in, _read_message

    payload = b'{"files": ["C:/notes/a.txt", "C:/notes/b.txt"]}' + TERMINATOR
    socket = _FakeSocket([payload[:12], payload[12:30], payload[30:]])

    assert _files_in(_read_message(socket)) == ["C:/notes/a.txt", "C:/notes/b.txt"]


def test_a_message_arriving_whole_is_read_without_extra_waiting():
    from core.single_instance import TERMINATOR, _files_in, _read_message

    socket = _FakeSocket([b'{"files": ["C:/notes/a.txt"]}' + TERMINATOR])
    assert _files_in(_read_message(socket)) == ["C:/notes/a.txt"]
    assert socket.waits == 0


def test_an_unterminated_message_from_an_old_build_still_arrives():
    from core.single_instance import _files_in, _read_message

    socket = _FakeSocket([b'{"files": ["C:/notes/a.txt"]}'], connected_after=False)
    assert _files_in(_read_message(socket)) == ["C:/notes/a.txt"]


def test_a_peer_that_sends_nothing_yields_no_files():
    from core.single_instance import _files_in, _read_message

    socket = _FakeSocket([], connected_after=False)
    assert _files_in(_read_message(socket, timeout_ms=50)) == []


def test_junk_is_ignored_rather_than_raising():
    from core.single_instance import _files_in, _read_message

    socket = _FakeSocket([b"not json at all\n"])
    assert _files_in(_read_message(socket)) == []


def test_non_string_entries_are_dropped():
    from core.single_instance import _files_in, _read_message

    socket = _FakeSocket([b'{"files": ["ok.txt", 5, null]}\n'])
    assert _files_in(_read_message(socket)) == ["ok.txt"]


def test_the_sender_terminates_what_it_writes(tmp_path, monkeypatch):
    """The framing only works if both halves agree on it."""
    import core.single_instance as module

    written: list[bytes] = []

    class _Socket:
        def connectToServer(self, _name):
            pass

        def waitForConnected(self, _ms):
            return True

        def write(self, payload):
            written.append(payload)

        def flush(self):
            pass

        def bytesToWrite(self):
            return 0

        def disconnectFromServer(self):
            pass

        def state(self):
            from PyQt6.QtNetwork import QLocalSocket

            return QLocalSocket.LocalSocketState.UnconnectedState

    from PyQt6.QtNetwork import QLocalSocket as _Real

    _Socket.LocalSocketState = _Real.LocalSocketState
    monkeypatch.setattr(module, "QLocalSocket", _Socket)
    guard = module.SingleInstanceGuard(tmp_path, server_name="unused")
    assert guard.notify_running_instance(["a.txt"])
    assert written and written[0].endswith(module.TERMINATOR)
