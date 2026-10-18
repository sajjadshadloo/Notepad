import hashlib
import json
import time
from dataclasses import replace

import pytest

from core import cloud_config, cloud_pairing
from core.cloud_config import SyncSettings
from core.cloud_pairing import PairingAttempt, SERVICE_URL
from core.cloud_sync import SyncError, sync_once
from tests.test_cloud_sync import FakeApi


def attempt():
    return PairingAttempt('pair-id', 'a' * 64, 'b' * 64,
                          'https://t.me/TestBot?start=pair_test', '123456', int(time.time() * 1000) + 60000)


def test_begin_sends_a_hash_of_the_device_key_and_keeps_the_raw_key_local(monkeypatch):
    sent = []

    class Api:
        def __init__(self, url, key, proxy):
            assert url == SERVICE_URL

        def call(self, path, method, body):
            sent.append(body)
            return dict(id='p', telegram_url='https://t.me/TestBot?start=pair_x',
                        confirm_code='123456', expires_at=123)

    monkeypatch.setattr(cloud_pairing, 'CloudApi', Api)
    result = cloud_pairing.begin()
    assert sent[0]['key_hash'] == hashlib.sha256(result.key.encode()).hexdigest()
    assert result.key not in json.dumps(sent)
    assert result.poll_key == sent[0]['poll_key']
    assert result.key != result.poll_key


def test_pairing_refuses_an_unexpected_browser_destination(monkeypatch):
    class Api:
        def __init__(self, *_):
            pass

        def call(self, *_):
            return {'telegram_url': 'https://t.me.attacker.invalid/'}

    monkeypatch.setattr(cloud_pairing, 'CloudApi', Api)
    with pytest.raises(SyncError, match='لینک'):
        cloud_pairing.begin()


def test_connected_settings_are_bound_to_the_account_device_and_confirmed_folder(tmp_path):
    result = cloud_pairing.connected_settings(attempt(), dict(status='approved', user_id='u', device_id='d'),
                                             SyncSettings(), str(tmp_path), ('Private',))
    assert result.enabled and result.url == SERVICE_URL
    assert result.user_id == 'u' and result.device_id == 'd'
    assert result.confirmed_root == str(tmp_path.resolve())
    assert result.excluded_paths == ('Private',)
    assert result.bot_token == ''


def test_reconnecting_the_previous_owner_is_compatible_but_account_switching_is_refused(tmp_path):
    previous = SyncSettings(enabled=True, url=SERVICE_URL, key='old-key')
    approved = dict(status='approved', user_id='legacy-owner', device_id='new-device')
    assert cloud_pairing.connected_settings(attempt(), approved, previous, str(tmp_path), ()).user_id == 'legacy-owner'
    with pytest.raises(SyncError, match='حساب دیگری'):
        cloud_pairing.connected_settings(attempt(), {**approved, 'user_id': 'someone-else'}, previous, str(tmp_path), ())
    with pytest.raises(SyncError, match='حساب دیگری'):
        cloud_pairing.connected_settings(attempt(), approved, replace(previous, url='https://personal.invalid'), str(tmp_path), ())


def test_new_fields_and_sealed_key_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv('NOTEPAD_DATA_DIR', str(tmp_path))
    settings = SyncSettings(enabled=True, url=SERVICE_URL, key='a' * 64, user_id='u', device_id='d',
                            confirmed_root=str(tmp_path), excluded_paths=('Private', 'Me/Secrets'))
    cloud_config.save(settings)
    assert cloud_config.load() == settings


def test_a_sync_journal_cannot_be_reused_for_another_account(tmp_path):
    journal = tmp_path / 'journal.json'
    journal.write_text(json.dumps({'account_id': 'alice', 'items': {}}), encoding='utf-8')
    api = FakeApi()
    api.account_id = 'mary'
    with pytest.raises(SyncError, match='حساب دیگری'):
        sync_once(tmp_path / 'notes', journal, api)
    assert json.loads(journal.read_text())['account_id'] == 'alice'
    assert not api.notes


def test_unknown_legacy_journals_do_not_upload_into_a_new_account(tmp_path):
    journal = tmp_path / 'journal.json'
    journal.write_text(json.dumps({'items': {'old': {'path': 'a.md'}}}), encoding='utf-8')
    api = FakeApi()
    api.account_id = 'new-user'
    with pytest.raises(SyncError, match='سابقه'):
        sync_once(tmp_path / 'notes', journal, api)
    assert not api.notes


def test_excluded_files_are_not_uploaded_downloaded_or_deleted(tmp_path, monkeypatch):
    root = tmp_path / 'notes'
    (root / 'Private').mkdir(parents=True)
    (root / 'Private/secret.md').write_text('keep-local', encoding='utf-8')
    (root / 'public.md').write_text('share', encoding='utf-8')
    api = FakeApi()
    api.account_id = 'alice'
    remote = api.call('/notes', 'POST', {'path': 'Private/secret.md', 'text': 'remote-secret'})['note']
    remote['deleted'] = 1
    api.call('/notes', 'POST', {'path': 'Private/other.md', 'text': 'never-download'})
    journal = tmp_path / 'state.json'
    result = sync_once(root, journal, api, excluded_paths=('private',))
    assert result.uploaded == 1 and result.deleted == 0 and result.downloaded == 0
    assert (root / 'Private/secret.md').read_text(encoding='utf-8') == 'keep-local'
    assert not (root / 'Private/other.md').exists()
    assert json.loads(journal.read_text())['account_id'] == 'alice'


def test_pairing_ui_requires_folder_consent_before_starting(tmp_path, monkeypatch, qapp):
    from PyQt6.QtWidgets import QWidget
    from ui.overlays import SettingsPanel

    host = QWidget()
    panel = SettingsPanel(host, '4.4.0')
    panel.open_with({'notes_root': str(tmp_path), 'sync': {}, 'sync_settings': SyncSettings()}, 'sync')
    monkeypatch.setattr(cloud_pairing, 'begin', lambda *_: pytest.fail('No consent'))
    panel._begin_pairing()
    assert panel._pairing is None
    assert 'پذیرش' in panel._pair_status.text()
    host.deleteLater()


def test_pairing_worker_and_ui_store_the_credential_then_start_sync(tmp_path, monkeypatch, qapp):
    from PyQt6.QtGui import QDesktopServices
    from PyQt6.QtWidgets import QWidget
    from ui.overlays import SettingsPanel

    monkeypatch.setenv('NOTEPAD_DATA_DIR', str(tmp_path / 'data'))
    monkeypatch.setattr(cloud_pairing, 'begin', lambda *_: attempt())
    monkeypatch.setattr(cloud_pairing, 'poll', lambda *_: dict(status='approved', user_id='alice', device_id='device'))
    monkeypatch.setattr(QDesktopServices, 'openUrl', lambda *_: True)
    host = QWidget()
    panel = SettingsPanel(host, '4.4.0')
    panel.open_with({'notes_root': str(tmp_path / 'notes'), 'sync': {}, 'sync_settings': SyncSettings()}, 'sync')
    changed = []
    panel.sync_settings_changed.connect(lambda: changed.append(True))
    panel._share_folder.on = True
    panel._begin_pairing()
    panel._pairing.wait(5000)
    for _ in range(10):
        qapp.processEvents()
    settings = cloud_config.load()
    assert settings.enabled and settings.user_id == 'alice'
    assert settings.device_id == 'device' and settings.excluded_paths == ('Private',)
    assert changed == [True]
    panel.wait_for_test()
    host.deleteLater()
