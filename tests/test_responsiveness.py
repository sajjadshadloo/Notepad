"""Regression scenarios: stalled disk/browser/network must leave editing usable."""
import json
import threading
import time
from datetime import datetime, date

import pytest
from PyQt6.QtCore import QCoreApplication, QEvent, QTimer
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QLineEdit, QWidget

from core import cloud_pairing, greeting, settings_manager
from core.cloud_config import SyncSettings
from core.cloud_sync import SyncError, sync_once
from core.note_library import NoteCard
from ui.notes_board import NotesBoard


def until(predicate, timeout=3000):
    end = time.monotonic() + timeout / 1000
    while not predicate() and time.monotonic() < end:
        QTest.qWait(10)
    assert predicate(), "Background operation did not finish"


def test_slow_disk_keeps_the_event_loop_and_typing_alive(qapp, tmp_path, monkeypatch):
    import ui.notes_board as module

    entered, release = threading.Event(), threading.Event()
    calls = []

    def slow(root, cancelled):
        calls.append(root)
        entered.set()
        release.wait(3)
        return [NoteCard(str(tmp_path / 'one.md'), 'One', '', 0)]

    monkeypatch.setattr(module, 'load_library', slow)
    board = NotesBoard(str(tmp_path))
    edit = QLineEdit()
    beats = []
    timer = QTimer(interval=10)
    timer.timeout.connect(lambda: beats.append(True))
    timer.start()
    try:
        started = time.monotonic()
        board.reload()
        assert time.monotonic() - started < 0.2
        until(entered.is_set)
        for _ in range(20):
            board.reload()
        QTest.keyClicks(edit, 'still responsive')
        QTest.qWait(80)
        assert edit.text() == 'still responsive' and len(beats) >= 3
        release.set()
        until(lambda: board._loader is None)
        assert len(calls) == 2, 'A burst should cause only one trailing scan'
        assert board.card_titles() == ['One']
    finally:
        release.set()
        timer.stop()
        board.stop_loading()
        board.deleteLater()
        edit.deleteLater()


def test_changing_root_discards_the_old_scan(qapp, tmp_path, monkeypatch):
    import ui.notes_board as module

    entered, release = threading.Event(), threading.Event()

    def slow(root, cancelled):
        if root == 'old':
            entered.set()
            release.wait(3)
        return [NoteCard(str(tmp_path / (root + '.md')), root, '', 0)]

    monkeypatch.setattr(module, 'load_library', slow)
    board = NotesBoard('old')
    try:
        board.reload()
        until(entered.is_set)
        board.set_root('new')
        release.set()
        until(lambda: board._loader is None)
        assert board.card_titles() == ['new']
    finally:
        release.set()
        board.deleteLater()


def test_destroying_a_board_during_a_disk_call_keeps_its_thread_safe(qapp, tmp_path, monkeypatch):
    import ui.notes_board as module
    from ui.background import _running

    entered, release = threading.Event(), threading.Event()

    def slow(*_):
        entered.set()
        release.wait(3)
        return []

    monkeypatch.setattr(module, 'load_library', slow)
    board = NotesBoard(str(tmp_path))
    board.reload()
    until(entered.is_set)
    worker = board._loader
    try:
        board.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        assert worker in _running and worker.isInterruptionRequested()
    finally:
        release.set()
        until(lambda: worker not in _running)


@pytest.fixture
def window(qapp):
    from ui.main_window import MainWindow

    settings_manager.save({**settings_manager.DEFAULTS, 'migration_checked': True,
                           'daily_cleanup_done': True, 'review_date': date.today().isoformat()})
    win = MainWindow()
    win._startup_prompts_shown = True
    win.show_page('editor')
    win.show()
    yield win
    win.notes_board.stop_loading()
    if win._links_worker:
        win._links_worker.requestInterruption()
    if win._tasks_watcher:
        win._tasks_watcher.stop()
    for index in range(win.tabs.count()):
        win.tabs.widget(index).mark_clean()
    win._really_quitting = True
    win.close()
    win.deleteLater()


def test_backlink_disk_reads_do_not_block_editor(window, monkeypatch):
    import core.links as links

    entered, release = threading.Event(), threading.Event()
    original = links.link_details

    def slow(*args):
        entered.set()
        release.wait(3)
        return original(*args)

    monkeypatch.setattr(links, 'link_details', slow)
    try:
        window.refresh_links_panel(force=True)
        until(entered.is_set)
        QTest.keyClicks(window.current_document().editor, 'Working while links load')
        assert window.current_document().text == 'Working while links load'
    finally:
        release.set()
        until(lambda: window._links_worker is None)


def test_a_stalled_browser_launch_does_not_block_the_dashboard(window, monkeypatch):
    from PyQt6.QtGui import QDesktopServices

    entered, release = threading.Event(), threading.Event()

    def slow(_):
        entered.set()
        release.wait(3)
        return False

    monkeypatch.setattr(QDesktopServices, 'openUrl', slow)
    panel = window.settings_overlay
    panel.open_with(window._settings_state(), 'sync')
    panel._pair_link = 'https://t.me/TestBot?start=pair_test'
    panel._open_pair_link()
    try:
        until(entered.is_set)
        panel.close_overlay()
        QTest.keyClicks(window.current_document().editor, 'The dashboard still works')
        assert window.current_document().text == 'The dashboard still works'
    finally:
        release.set()
        until(lambda: panel._opener is None)


def test_pairing_recovers_from_temporary_network_loss_without_losing_its_key(tmp_path, monkeypatch):
    from tests.test_cloud_pairing import attempt
    from ui.cloud_sync_worker import PairingWorker

    original = attempt()
    seen, results = [], []

    def poll(current, _):
        seen.append(current)
        if len(seen) == 1:
            raise SyncError('temporary network outage')
        return dict(status='approved', user_id='owner', device_id='second-pc')

    monkeypatch.setattr(cloud_pairing, 'begin', lambda *_: original)
    monkeypatch.setattr(cloud_pairing, 'poll', poll)
    worker = PairingWorker(SyncSettings(), str(tmp_path), ())
    monkeypatch.setattr(worker, '_pause', lambda *_: None)
    worker.done.connect(lambda result, error: results.append((result, error)))
    worker.run()
    assert len(seen) == 2 and all(current is original for current in seen)
    assert results[0][0].key == original.key and results[0][1] == ''
    worker.deleteLater()


def test_pairing_does_not_retry_a_revoked_request(tmp_path, monkeypatch):
    from tests.test_cloud_pairing import attempt
    from ui.cloud_sync_worker import PairingWorker

    monkeypatch.setattr(cloud_pairing, 'begin', lambda *_: attempt())
    calls, results = [], []

    def refused(*_):
        calls.append(True)
        error = SyncError('revoked')
        error.status = 403
        raise error

    monkeypatch.setattr(cloud_pairing, 'poll', refused)
    worker = PairingWorker(SyncSettings(), str(tmp_path), ())
    worker.done.connect(lambda result, error: results.append((result, error)))
    worker.run()
    assert len(calls) == 1 and results == [(None, 'revoked')]
    worker.deleteLater()


def test_invalid_sync_settings_report_an_error_instead_of_silently_stopping(tmp_path):
    from ui.cloud_sync_worker import CloudSyncWorker

    worker = CloudSyncWorker(str(tmp_path / 'notes'), tmp_path / 'state.json', '', '', set())
    results = []
    worker.completed.connect(lambda result, error: results.append((result, error)))
    worker.run()
    assert results and results[0][0] is None and results[0][1]
    assert json.loads((tmp_path / 'cloud_sync_status.json').read_text())['state'] == 'error'
    worker.deleteLater()


def test_sync_still_completes_when_the_status_file_is_locked(tmp_path, monkeypatch):
    import ui.cloud_sync_worker as module

    def locked(*args, **kwargs):
        raise PermissionError('status file locked')

    monkeypatch.setattr(module, 'record_sync_status', locked)
    worker = module.CloudSyncWorker(str(tmp_path / 'notes'), tmp_path / 'state.json', '', '', set())
    results = []
    worker.completed.connect(lambda result, error: results.append((result, error)))
    worker.run()
    assert results and results[0][0] is None and results[0][1]
    worker.deleteLater()


def test_network_test_can_finish_after_leaving_its_settings_section(window):
    panel = window.settings_overlay
    panel.open_with(window._settings_state(), 'sync')
    panel.show_section('look')
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    panel._test_done(False, 'No network')
    assert panel._section == 'look' and not panel._busy


def test_two_computers_on_the_same_account_exchange_saved_notes(tmp_path):
    from tests.test_cloud_sync import FakeApi

    api = FakeApi()
    api.account_id = 'same-telegram-account'
    first, second = tmp_path / 'pc1', tmp_path / 'pc2'
    first.mkdir()
    second.mkdir()
    (first / 'note.md').write_text('# From first PC', encoding='utf-8')
    sync_once(first, tmp_path / 'pc1-state.json', api)
    sync_once(second, tmp_path / 'pc2-state.json', api)
    assert (second / 'note.md').read_text(encoding='utf-8') == '# From first PC'
    (second / 'note.md').write_text('# Edited on second PC', encoding='utf-8')
    sync_once(second, tmp_path / 'pc2-state.json', api)
    sync_once(first, tmp_path / 'pc1-state.json', api)
    assert (first / 'note.md').read_text(encoding='utf-8') == '# Edited on second PC'


@pytest.mark.parametrize('hour,expected', [(0, 'شب بخیر'), (4, 'شب بخیر'), (5, 'صبح بخیر'),
    (11, 'صبح بخیر'), (12, 'ظهر بخیر'), (14, 'ظهر بخیر'), (15, 'عصر بخیر'),
    (18, 'عصر بخیر'), (19, 'شب بخیر'), (23, 'شب بخیر')])
def test_greeting_uses_local_time(hour, expected):
    assert greeting.greeting(datetime(2026, 10, 18, hour)) == expected


def test_review_greeting_updates_each_time_it_opens(qapp, monkeypatch):
    from ui.overlays import MorningReview

    host = QWidget()
    host.resize(1000, 700)
    host.show()
    review = MorningReview(host, 'علی')
    try:
        monkeypatch.setattr(greeting, 'greeting', lambda: 'ظهر بخیر')
        review.open()
        assert review._hello.text == 'ظهر بخیر، علی'
        review.close_overlay()
        monkeypatch.setattr(greeting, 'greeting', lambda: 'عصر بخیر')
        review.open()
        assert review._hello.text == 'عصر بخیر، علی'
    finally:
        host.deleteLater()


def test_automatic_review_does_not_cover_the_telegram_settings(window):
    window._cfg['review_date'] = ''
    window.settings_overlay.open_with(window._settings_state(), 'sync')
    window._maybe_morning_review()
    assert not window.review.isVisible()
    assert window._cfg['review_date'] == ''
    window.settings_overlay.close_overlay()
    window._maybe_morning_review()
    assert window.review.isVisible()
    assert window._cfg['review_date'] == date.today().isoformat()
    window.review.close_overlay()


def test_task_dialog_uses_the_background_snapshot(window, monkeypatch):
    import ui.today_view as module

    monkeypatch.setattr(module, 'scan_folder', lambda *_: pytest.fail('Disk scan on GUI thread'))
    monkeypatch.setattr(module.TodayDialog, 'exec', lambda *_: 0)
    window.show_today()


def test_invalid_local_metadata_cannot_prevent_startup(tmp_path, monkeypatch):
    from core import note_index, recovery_manager

    monkeypatch.setenv('NOTEPAD_DATA_DIR', str(tmp_path))
    (tmp_path / 'settings.json').write_text('[]', encoding='utf-8')
    (tmp_path / 'notes_index.json').write_text('{"broken": 1}', encoding='utf-8')
    recovery = recovery_manager.recovery_dir() / 'broken.json'
    recovery.write_text('[]', encoding='utf-8')
    assert settings_manager.load() == settings_manager.DEFAULTS
    assert note_index.load() == {}
    assert recovery_manager.load_recoveries() == []
    assert recovery.read_text(encoding='utf-8') == '[]'


def test_failed_recycle_keeps_the_file_and_unsaved_editor_text(window, tmp_path, monkeypatch):
    from core import trash
    from PyQt6.QtWidgets import QMessageBox

    path = tmp_path / 'keep.md'
    path.write_text('saved text', encoding='utf-8')
    window.open_file(str(path))
    tab = window.current_document()
    tab.editor.insertPlainText('unsaved addition')
    before = tab.text
    monkeypatch.setattr(trash, 'available', lambda: True)
    monkeypatch.setattr(trash, 'send_to_recycle_bin', lambda *_: False)
    monkeypatch.setattr(QMessageBox, 'question', lambda *_: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, 'critical', lambda *_: QMessageBox.StandardButton.Ok)
    window.delete_note(str(path))
    assert path.read_text(encoding='utf-8') == 'saved text'
    assert window._tab_for_path(str(path)) is tab
    assert tab.modified and tab.text == before


def test_remote_delete_waits_when_windows_recycle_bin_fails(tmp_path, monkeypatch):
    from core import trash
    from tests.test_cloud_sync import FakeApi

    api = FakeApi()
    root, state = tmp_path / 'notes', tmp_path / 'state.json'
    note = api.call('/notes', 'POST', {'path': 'keep.md', 'text': 'Keep this recoverable'})['note']
    sync_once(root, state, api)
    api.call('/notes/' + note['id'], 'DELETE', {'version': 1})
    monkeypatch.setattr(trash, 'available', lambda: True)
    monkeypatch.setattr(trash, 'send_to_recycle_bin', lambda *_: False)
    result = sync_once(root, state, api)
    assert result.deleted == 0 and result.skipped == 1
    assert (root / 'keep.md').read_text(encoding='utf-8') == 'Keep this recoverable'


def test_watchdog_records_one_stack_per_stall_without_document_values(qapp, caplog):
    from core.ui_watchdog import UiWatchdog

    watchdog = UiWatchdog()
    watchdog._heartbeat = time.monotonic() - 10
    with caplog.at_level('ERROR', logger='notepad.responsiveness'):
        watchdog._check()
        watchdog._check()
    assert len(caplog.records) == 1 and 'UI unresponsive' in caplog.text
    watchdog._beat()
    watchdog._check()
    assert len(caplog.records) == 1
    watchdog.deleteLater()
