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
