"""Leaving the app must not take the process down with it.

Qt aborts the whole process when a QThread is destroyed while it is still
running: quitting mid-sync did exactly that, and so did a slow first launch
whose startup sync began a moment before the quit.
"""
import pytest


@pytest.fixture
def window(tmp_path, monkeypatch, qapp):
    monkeypatch.setenv("NOTEPAD_DATA_DIR", str(tmp_path / "appdata"))
    from ui.main_window import MainWindow

    window = MainWindow()
    window._cfg["notes_root"] = str(tmp_path / "notes")
    yield window
    for index in range(window.tabs.count()):
        window.tabs.widget(index).mark_clean()
    window._sync_worker = None
    window.close()
    window.deleteLater()


class RunningSync:
    def __init__(self):
        self.waited = None

    def isRunning(self):
        return True

    def wait(self, ms):
        self.waited = ms
        return True


def test_quitting_waits_for_a_sync_in_flight(window):
    sync = RunningSync()
    window._sync_worker = sync
    window._finish_background_work()
    assert sync.waited == window.SYNC_EXIT_WAIT_MS
    assert not window._sync_timer.isActive()


def test_no_new_sync_starts_once_quitting(window):
    window._finish_background_work()
    window.sync_now()
    assert window._sync_worker is None


def test_quitting_waits_for_the_task_scan(window):
    """The folder walk is a thread too; a cold first one takes seconds."""
    scan = RunningSync()
    watcher = window._tasks_watcher
    # The window may have a real walk going already; it must not be orphaned.
    if watcher._worker is not None:
        watcher._worker.wait()
    watcher._worker = scan
    window._finish_background_work()
    assert scan.waited == watcher.STOP_WAIT_MS
    watcher._worker = None
    watcher.check_now()
    assert watcher._worker is None
