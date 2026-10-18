import io
import json
import logging
import queue
import threading
import time
import zipfile
from pathlib import Path
from urllib.error import HTTPError

import pytest
from PyQt6.QtCore import QCoreApplication, QEvent
from PyQt6.QtTest import QTest

from core import diagnostics, settings_manager
from core.cloud_sync import CloudApi, SyncError
from ui.diagnostics_panel import DiagnosticsPanel


def wait_for(predicate):
    end = time.monotonic() + 3
    while not predicate() and time.monotonic() < end:
        QTest.qWait(10)
    assert predicate()


@pytest.fixture
def service():
    names = ('notepad', 'core', 'ui', 'qt')
    levels = {name: logging.getLogger(name).level for name in names}
    instance = diagnostics.configure('4.5.0')
    yield instance
    diagnostics.shutdown()
    for name, level in levels.items():
        logging.getLogger(name).setLevel(level)


def events(service):
    service.flush_pending()
    return diagnostics.read_events(service.folder, limit=2000)


def test_debug_is_opt_in_and_expires_without_a_gui_timer(service):
    logger = logging.getLogger('notepad.test')
    logger.debug('hidden before opt in')
    service.set_verbose(True)
    logger.debug('visible during opt in')
    service.verbose_until = time.monotonic() - 1
    logger.debug('hidden after expiry')
    messages = [event['message'] for event in events(service)]
    assert 'visible during opt in' in messages
    assert 'hidden before opt in' not in messages and 'hidden after expiry' not in messages


def test_export_excludes_notes_credentials_legacy_logs_and_exception_values(service, tmp_path):
    secret, note = 'ab' * 32, 'UNIQUE PRIVATE NOTE CONTENT'
    root = settings_manager.app_data_dir()
    (root / 'note.md').write_text(note, encoding='utf-8')
    (root / 'cloud_sync.json').write_text(json.dumps({'enabled': True, 'key': secret,
        'device_id': 'my-private-device', 'notes_root': 'C:/Users/Secret/Private'}), encoding='utf-8')
    (service.folder / 'notepad.log').write_text(note + secret, encoding='utf-8')
    logger = logging.getLogger('notepad.test')
    logger.error('Authorization: Bearer %s https://example.test/?poll_key=%s', secret, secret)
    try:
        raise ValueError(note + secret)
    except ValueError:
        logger.exception('Sync operation failed')
    logging.getLogger('notepad.cloud_sync').info('Merged %s: kept %r, set aside %r',
        'Private/password.md', [note], [secret])
    destination = tmp_path / 'report.zip'
    diagnostics.export_report(destination, '4.5.0')
    with zipfile.ZipFile(destination) as archive:
        assert set(archive.namelist()) == {'environment.json', 'events.jsonl', 'README.txt'}
        combined = '\n'.join(archive.read(name).decode('utf-8') for name in archive.namelist())
        assert secret not in combined and note not in combined and 'my-private-device' not in combined
        assert 'password.md' not in combined and 'Secret/Private' not in combined
        saved = [json.loads(line) for line in archive.read('events.jsonl').decode().splitlines()]
        error = next(event for event in saved if event.get('error_type') == 'ValueError')
        assert error['stack'] and error['error_chain'] == ['ValueError']
        assert all('C:\\' not in row for row in error['stack'])


def test_redaction_handles_telegram_tokens_paths_and_dpapi():
    raw = 'https://t.me/Test?start=pair_' + 'a' * 32 + ' 123456:' + 'B' * 35 + \
          ' dpapi:' + 'C' * 90 + ' key=short-secret C:\\Users\\Name\\Private\\notes.md'
    result = diagnostics.redact(raw)
    assert 'short-secret' not in result and 'notes.md' not in result and 'Name' not in result
    assert 'B' * 35 not in result and 'C' * 90 not in result and 'a' * 32 not in result
    assert 'private words here' not in diagnostics.redact('password="private words here"')


def test_request_failure_has_http_status_timing_and_operation_correlation(service):
    service.set_verbose(True)
    api = CloudApi('https://example.invalid', 'd' * 64)

    def refused(*args, **kwargs):
        raise HTTPError('https://example.invalid?key=private', 429, 'private response body', {}, io.BytesIO())

    api._open = refused
    with pytest.raises(SyncError):
        with diagnostics.operation('sync-test'):
            api.call('/notes/11111111-1111-1111-1111-111111111111', 'PUT', {'text': 'must not be logged'})
    saved = events(service)
    request = next(event for event in saved if event['event'] == 'http.started')
    rejected = next(event for event in saved if event['event'] == 'http.rejected')
    assert request['request_id'] == rejected['request_id']
    assert request['operation_id'] == rejected['operation_id']
    assert rejected['http_status'] == 429 and rejected['duration_ms'] >= 0
    assert rejected['route'] == '/notes/{id}'
    assert 'must not be logged' not in json.dumps(saved)
    assert 'private response body' not in json.dumps(saved)


def test_queue_and_rotation_are_bounded_without_blocking_the_caller(service, monkeypatch):
    service.flush_pending()
    entered, release = threading.Event(), threading.Event()
    original = service._sink.flush

    def stalled():
        entered.set()
        release.wait(3)
        original()

    monkeypatch.setattr(service._sink, 'flush', stalled)
    logger = logging.getLogger('notepad.test')
    logger.info('disk stall begins')
    assert entered.wait(1)
    started = time.monotonic()
    try:
        for number in range(2020):
            logger.info('event %s', number)
        assert time.monotonic() - started < 2
        assert service._queue.qsize() <= 2000 and service.dropped > 0
    finally:
        release.set()
    service.flush_pending(timeout=3)


def test_rotation_retains_only_three_files(service):
    service.flush_pending()
    service._sink.maxBytes = 1200
    for number in range(20):
        logging.getLogger('notepad.test').info('rotation event %s', number)
    service.flush_pending()
    files = sorted(path.name for path in service.folder.glob('diagnostics.jsonl*'))
    assert files == ['diagnostics.jsonl', 'diagnostics.jsonl.1', 'diagnostics.jsonl.2']
    assert len(events(service)) < 20
    assert events(service)[-1]['message'] == 'rotation event 19'


def test_corrupt_or_partial_lines_do_not_break_the_view(tmp_path):
    path = tmp_path / diagnostics.FILE_NAME
    path.write_text('not json\n[]\n' + json.dumps({'time':'bad date','level':'ERROR','message':''}) + '\n{"partial":', encoding='utf-8')
    saved = diagnostics.read_events(tmp_path)
    assert len(saved) == 1 and saved[0]['message'] == ''


def test_panel_filters_copies_details_and_exports_asynchronously(service, tmp_path, qapp):
    logger = logging.getLogger('notepad.test')
    logger.info('normal event')
    logger.error('special error', extra={'event':'sync.failed', 'http_status':401})
    service.flush_pending()
    panel = DiagnosticsPanel('4.5.0')
    panel.show()
    try:
        wait_for(lambda: panel._reader is None)
        panel.level.setCurrentIndex(1)
        assert panel.events.topLevelItemCount() == 1
        panel.events.setCurrentItem(panel.events.topLevelItem(0))
        assert '401' in panel.details.toPlainText()
        panel._copy()
        assert 'special error' in qapp.clipboard().text()
        destination = tmp_path / 'ui-report.zip'
        panel.export_to(str(destination))
        wait_for(lambda: panel._exporter is None)
        assert zipfile.is_zipfile(destination)
        assert 'ذخیره شد' in panel.status.text()
    finally:
        panel.close()
        panel.deleteLater()


def test_slow_log_loading_does_not_block_search_input(tmp_path, monkeypatch, qapp):
    entered, release = threading.Event(), threading.Event()

    def slow(*_):
        entered.set()
        release.wait(3)
        return []

    monkeypatch.setattr(diagnostics, 'read_events', slow)
    panel = DiagnosticsPanel('4.5.0')
    try:
        wait_for(entered.is_set)
        QTest.keyClicks(panel.search, 'search while disk is slow')
        assert panel.search.text() == 'search while disk is slow'
    finally:
        release.set()
        wait_for(lambda: panel._reader is None)
        panel.deleteLater()


def test_failed_export_preserves_an_existing_report(service, tmp_path, monkeypatch):
    destination = tmp_path / 'report.zip'
    destination.write_bytes(b'previous report')

    def unavailable(_):
        raise OSError('disk unavailable')

    monkeypatch.setattr(diagnostics, 'environment_report', unavailable)
    with pytest.raises(OSError):
        diagnostics.export_report(destination, '4.5.0')
    assert destination.read_bytes() == b'previous report'
    assert list(tmp_path.glob('.notepad-report-*')) == []


def test_log_write_failure_is_reported_without_raising_on_the_gui(service, monkeypatch):
    service.flush_pending()
    service._sink.close()
    service._sink.stream = None

    def denied():
        raise PermissionError('locked log file')

    monkeypatch.setattr(service._sink, '_open', denied)
    logging.getLogger('notepad.test').error('A real error still cannot crash the editor')
    service.flush_pending()
    assert service.write_errors > 0
    assert diagnostics.environment_report('4.5.0')['log_write_errors'] > 0


def test_native_crash_export_contains_only_safe_frame_names(service, tmp_path):
    raw = 'Windows fatal exception: access violation\n' + \
          '  File "C:\\Users\\PersonalName\\Private\\main.py", line 12 in main\n' + \
          'PRIVATE NOTE CONTENT and token=secret-that-must-not-leak\n'
    (service.folder / 'crash.log').write_text(raw, encoding='utf-8')
    destination = tmp_path / 'with-crash.zip'
    diagnostics.export_report(destination, '4.5.0')
    with zipfile.ZipFile(destination) as archive:
        text = archive.read('crash-stack.txt').decode()
        assert 'main.py:12 in main' in text
        assert 'PersonalName' not in text and 'Private' not in text
        assert 'NOTE CONTENT' not in text and 'secret-that-must-not-leak' not in text


def test_exception_chain_keeps_os_error_codes_without_exception_text(service):
    from urllib.error import URLError

    try:
        raise URLError(ConnectionRefusedError(10061, 'PRIVATE CONNECTION DETAILS'))
    except URLError:
        logging.getLogger('notepad.test').exception('Network connection failed')
    saved = next(event for event in events(service) if event.get('error_type') == 'URLError')
    assert saved['os_error'] == 10061
    assert saved['error_chain'] == ['URLError', 'ConnectionRefusedError']
    assert 'PRIVATE CONNECTION DETAILS' not in json.dumps(saved)


def test_document_io_errors_are_logged_without_names_or_contents(service, tmp_path):
    from core import file_service

    private_file = tmp_path / 'PRIVATE_FILENAME.md'
    with pytest.raises(FileNotFoundError):
        file_service.read_text_file(private_file)
    saved = next(event for event in events(service) if event['event'] == 'file.read.failed')
    assert saved['error_type'] == 'FileNotFoundError' and saved['os_error'] == 2
    assert 'PRIVATE_FILENAME' not in json.dumps(saved)
    service.set_verbose(True)
    file_service.write_text_file_atomic(private_file, 'PRIVATE FILE TEXT')
    saved = events(service)
    assert any(event['event'] == 'file.write.completed' for event in saved)
    assert 'PRIVATE FILE TEXT' not in json.dumps(saved) and 'PRIVATE_FILENAME' not in json.dumps(saved)


def test_inspecting_logs_does_not_cancel_a_pairing_in_progress(service, qapp):
    from PyQt6.QtWidgets import QWidget
    from ui.overlays import SettingsPanel

    class Pairing:
        interrupted = False
        def isRunning(self):
            return True
        def requestInterruption(self):
            self.interrupted = True

    host = QWidget()
    panel = SettingsPanel(host, '4.5.0')
    panel._pairing = Pairing()
    panel.open_with({'sync': {}}, 'diagnostics')
    assert not panel._pairing.interrupted
    wait_for(lambda: panel.diagnostics_panel._reader is None)
    panel.show_section('look')
    assert panel._pairing.interrupted
    host.deleteLater()


def test_sync_reason_is_preserved_without_copying_exception_values(service):
    try:
        raise SyncError('PRIVATE LOCAL DETAILS', code='journal_damaged')
    except SyncError:
        logging.getLogger('notepad.test').exception('Sync pass failed')
    saved = next(event for event in events(service) if event.get('error_type') == 'SyncError')
    assert saved['reason'] == 'journal_damaged'
    assert 'PRIVATE LOCAL DETAILS' not in json.dumps(saved)


def test_windows_error_is_more_specific_than_the_portable_errno(service):
    try:
        error = OSError(13, 'PRIVATE ERROR DETAILS')
        error.winerror = 32
        raise error
    except OSError:
        logging.getLogger('notepad.test').exception('File access failed')
    saved = next(event for event in events(service) if event.get('error_type'))
    assert saved['os_error'] == 32
