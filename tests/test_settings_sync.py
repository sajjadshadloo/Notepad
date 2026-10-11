"""The sync section of the settings screen: what it shows and what it does."""
import pytest
from PyQt6.QtWidgets import QApplication, QLineEdit, QWidget

from core import cloud_config
from core.cloud_config import SyncSettings

KEY = "k" * 64


@pytest.fixture
def panel(tmp_path, monkeypatch, qapp):
    monkeypatch.setenv("NOTEPAD_DATA_DIR", str(tmp_path / "appdata"))
    from ui.overlays import SettingsPanel

    host = QWidget()
    host.resize(900, 720)
    host.show()
    settings_panel = SettingsPanel(host, "9.9.9")
    yield settings_panel
    settings_panel.wait_for_test()
    host.deleteLater()


def open_sync(panel, settings=None):
    panel.open_with({"sync": {}, "sync_settings": settings or SyncSettings()}, "sync")


def test_the_section_shows_the_saved_address_and_key(panel):
    open_sync(panel, SyncSettings(enabled=True, url="https://a.workers.dev", key=KEY))
    values = [edit.text() for edit in panel.findChildren(QLineEdit)]
    assert "https://a.workers.dev" in values and KEY in values


def test_the_key_button_makes_a_key_and_copies_it(panel):
    open_sync(panel)
    panel._make_key()
    assert len(panel._key.text()) == 64
    assert QApplication.clipboard().text() == panel._key.text()


def test_a_bad_address_is_refused_and_nothing_is_written(panel):
    open_sync(panel)
    panel._url.setText("http://nope.example")
    panel._key.setText(KEY)
    panel._save_sync()
    assert "https://" in panel._result.text()
    assert not cloud_config.path().exists()


def test_save_writes_then_tests_then_tells_the_window(panel, qapp, monkeypatch):
    monkeypatch.setattr(cloud_config, "check_all", lambda settings: (True, "به سرور وصل شد."))
    announced = []
    panel.sync_settings_changed.connect(lambda: announced.append(True))
    open_sync(panel)
    panel._enabled.on = True
    panel._url.setText("https://a.workers.dev")
    panel._key.setText(KEY)

    panel._save_sync()
    panel._test.wait(5000)
    for _ in range(50):
        qapp.processEvents()

    saved = cloud_config.load()
    assert saved.enabled and saved.url == "https://a.workers.dev" and saved.key == KEY
    assert "وصل شد" in panel._result.text()
    assert announced == [True]
