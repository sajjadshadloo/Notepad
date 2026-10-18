"""Release validation, interruption, UI responsiveness and safe install handoff."""
import hashlib
import io
import json
from pathlib import Path
import threading
import time
from urllib.error import HTTPError

import pytest
from PyQt6.QtCore import QTimer
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QLineEdit, QWidget

from core import app_updates as updates
from ui.app_updates import UpdateController, UpdatesPanel

PAYLOAD = b'MZ synthetic installer bytes'
DIGEST = hashlib.sha256(PAYLOAD).hexdigest()


def metadata(version='4.7.0'):
    name = f'NotepadPlus-Setup-{version}.exe'
    return {'tag_name': 'v' + version, 'draft': False, 'prerelease': False,
            'body': 'Changes\n<script>plain text only</script>', 'assets': [{
                'name': name, 'state': 'uploaded', 'size': len(PAYLOAD),
                'browser_download_url': f'https://github.com/{updates.REPOSITORY}/releases/download/v{version}/{name}',
                'digest': 'sha256:' + DIGEST}]}


def release():
    data = metadata()
    return updates.Release('4.7.0', data['body'], data['assets'][0]['browser_download_url'], len(PAYLOAD), DIGEST)


def respond(monkeypatch, data):
    monkeypatch.setattr(updates, '_open', lambda *args: io.BytesIO(data))


def until(predicate):
    deadline = time.monotonic() + 4
    while not predicate() and time.monotonic() < deadline:
        QTest.qWait(10)
    assert predicate()


def test_numeric_versions_never_downgrade_and_ignore_older_releases(monkeypatch):
    respond(monkeypatch, json.dumps(metadata('4.10.0')).encode())
    assert updates.check_latest('4.9.9').version == '4.10.0'
    assert updates.check_latest('4.10.0') is None
    assert updates.check_latest('5.0.0') is None


@pytest.mark.parametrize('change', [
    lambda d: d.update(tag_name='v4.7.0-beta'),
    lambda d: d.update(prerelease=True),
    lambda d: d.update(draft=True),
    lambda d: d.update(assets=[]),
    lambda d: d['assets'][0].update(size=updates.MAX_INSTALLER + 1),
    lambda d: d['assets'][0].update(browser_download_url='https://evil.example/setup.exe'),
    lambda d: d['assets'][0].update(digest=None),
])
def test_invalid_release_cannot_offer_an_install(monkeypatch, change):
    data = metadata()
    change(data)
    respond(monkeypatch, json.dumps(data).encode())
    with pytest.raises(updates.UpdateError):
        updates.check_latest('4.6.0')


def test_missing_release_is_not_reported_as_up_to_date(monkeypatch):
    def missing(*args):
        raise HTTPError(updates.API_URL, 404, 'Not Found', {}, None)
    monkeypatch.setattr(updates, '_open', missing)
    with pytest.raises(updates.UpdateError, match='هنوز نسخهٔ عمومی'):
        updates.check_latest('4.6.0')


def test_checksum_fallback_must_name_the_exact_installer(monkeypatch):
    data = metadata()
    asset = data['assets'][0]
    asset.pop('digest')
    sums = {**asset, 'name': asset['name'] + '.sha256',
            'browser_download_url': asset['browser_download_url'] + '.sha256'}
    data['assets'].append(sums)
    def response(url, *args):
        content = json.dumps(data).encode() if url == updates.API_URL else (DIGEST + '  ' + asset['name'] + '\n').encode()
        return io.BytesIO(content)
    monkeypatch.setattr(updates, '_open', response)
    assert updates.check_latest('4.6.0').sha256 == DIGEST
    monkeypatch.setattr(updates, '_open', lambda url, *args: io.BytesIO(
        json.dumps(data).encode() if url == updates.API_URL else (DIGEST + '  other.exe').encode()))
    with pytest.raises(updates.UpdateError):
        updates.check_latest('4.6.0')


@pytest.mark.parametrize('url', ['http://github.com/file', 'https://github.com.evil.example/file',
    'https://user:pass@github.com/file', 'https://127.0.0.1/file', 'file:///C:/file',
    'https://github.com:444/file'])
def test_redirect_cannot_leave_trusted_https_hosts(url):
    redirect = updates._Redirects(time.monotonic() + 10, lambda: False)
    with pytest.raises(updates.UpdateError):
        redirect.redirect_request(None, None, 302, '', {}, url)


def test_download_verified_cache_and_changed_file_are_checked_again(monkeypatch, tmp_path):
    respond(monkeypatch, PAYLOAD)
    progress = []
    downloaded = updates.download_release(release(), tmp_path, lambda *args: progress.append(args))
    assert downloaded.path.read_bytes() == PAYLOAD
    assert progress[-1] == (len(PAYLOAD), len(PAYLOAD))
    monkeypatch.setattr(updates, '_open', lambda *args: pytest.fail('Verified cache must not download again'))
    assert updates.download_release(release(), tmp_path) == downloaded
    assert updates.verify_download(downloaded, tmp_path) == downloaded
    downloaded.path.write_bytes(b'X' * len(PAYLOAD))
    with pytest.raises(updates.UpdateError):
        updates.verify_download(downloaded, tmp_path)
    assert not list(tmp_path.glob('*.part'))


@pytest.mark.parametrize('payload', [PAYLOAD[:-1], PAYLOAD + b'extra', b'X' * len(PAYLOAD)])
def test_partial_oversized_or_bad_hash_never_replaces_cached_file(monkeypatch, tmp_path, payload):
    old = tmp_path / release().filename
    old.write_bytes(b'old cache')
    respond(monkeypatch, payload)
    with pytest.raises(updates.UpdateError):
        updates.download_release(release(), tmp_path)
    assert old.read_bytes() == b'old cache'
    assert not list(tmp_path.glob('*.part'))


def test_cancel_removes_partial_download(monkeypatch, tmp_path):
    respond(monkeypatch, PAYLOAD)
    cancelled = []
    with pytest.raises(updates.Cancelled):
        updates.download_release(release(), tmp_path, lambda *_: cancelled.append(True), lambda: bool(cancelled))
    assert not list(tmp_path.glob('*.part'))
    assert not list(tmp_path.glob('*.exe'))


def test_manual_and_automatic_checks_have_bounded_scheduling(monkeypatch, qapp):
    cfg = {'last_app_update_check': time.time()}
    controller = UpdateController('4.6.0', cfg)
    monkeypatch.setattr(updates, 'check_latest', lambda *_: None)
    controller.auto_check()
    assert not controller.busy
    controller.check()
    until(lambda: not controller.busy)
    assert controller.phase == 'current'
    controller.set_automatic(False)
    cfg['last_app_update_check'] = 0
    controller.auto_check()
    assert not controller.busy
    assert updates.check_due('bad') and updates.check_due(time.time() + 100)
    controller.stop()
    controller.deleteLater()


def test_slow_network_and_settings_rebuild_leave_typing_usable(monkeypatch, qapp):
    entered, finish = threading.Event(), threading.Event()
    calls = []
    def slow(*args):
        entered.set()
        calls.append(True)
        finish.wait(3)
        return release()
    monkeypatch.setattr(updates, 'check_latest', slow)
    controller = UpdateController('4.6.0', {})
    panel = UpdatesPanel(controller)
    editor = QLineEdit()
    beats = []
    timer = QTimer(interval=10)
    timer.timeout.connect(lambda: beats.append(True))
    timer.start()
    try:
        controller.check()
        until(entered.is_set)
        for _ in range(10):
            controller.check()
        panel.deleteLater()
        replacement = UpdatesPanel(controller)
        QTest.keyClicks(editor, 'still fast')
        QTest.qWait(80)
        assert editor.text() == 'still fast' and len(beats) >= 3 and len(calls) == 1
        finish.set()
        until(lambda: not controller.busy)
        assert controller.phase == 'available'
        assert replacement.download_button.isHidden() is False
        assert '<script>' in replacement.notes.toPlainText()
        replacement.deleteLater()
    finally:
        finish.set()
        timer.stop()
        until(lambda: not controller.busy)
        controller.stop()
        controller.deleteLater()
        editor.deleteLater()


def test_update_page_is_lazy_and_does_not_interrupt_pairing(qapp):
    from ui.overlays import SettingsPanel
    host = QWidget()
    panel = SettingsPanel(host, '4.6.0')
    class Pairing:
        def isRunning(self): return True
        def requestInterruption(self): pytest.fail('Viewing update must not cancel pairing')
    panel._pairing = Pairing()
    panel.open_with({}, 'updates')
    assert panel._updates.phase == 'idle' and not panel._updates.busy
    panel._updates.stop()
    host.deleteLater()


def test_cancel_unsaved_document_exit_clears_pending_installer(monkeypatch, qapp):
    from ui.main_window import MainWindow
    window = MainWindow()
    window._startup_prompts_shown = True
    monkeypatch.setattr(window, 'close_tab', lambda *args, **kwargs: False)
    downloaded = updates.DownloadedUpdate(release(), Path('not-used.exe'))
    window._install_app_update(downloaded)
    assert window.updates.pending_install is None
    assert not window._closing_application
    window._finish_background_work()
    window.deleteLater()


def test_installer_is_launched_without_shell_only_after_verification(monkeypatch, tmp_path):
    import sys
    respond(monkeypatch, PAYLOAD)
    downloaded = updates.download_release(release(), tmp_path)
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'executable', str(tmp_path / 'installed' / 'NotepadPlus.exe'))
    calls = []
    monkeypatch.setattr(updates.subprocess, 'Popen', lambda args, **kw: calls.append((args, kw)))
    updates.launch_installer(downloaded, tmp_path)
    args, kwargs = calls[0]
    assert args[0] == str(downloaded.path) and '/NOTEPADUPDATE=1' in args
    assert args[-1] == '/DIR=' + str(tmp_path / 'installed')
    assert not kwargs.get('shell')
    downloaded.path.write_bytes(b'changed')
    with pytest.raises(updates.UpdateError):
        updates.launch_installer(downloaded, tmp_path)
    assert len(calls) == 1
