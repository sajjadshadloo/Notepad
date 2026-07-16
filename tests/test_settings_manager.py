import json

from core import settings_manager


def _write_settings(tmp_path, data: dict):
    (tmp_path / "settings.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )


def test_default_save_dir_is_under_documents():
    assert settings_manager.DEFAULT_SAVE_DIR.endswith("Notepad")
    assert "Documents" in settings_manager.DEFAULT_SAVE_DIR


def test_load_migrates_legacy_c_notepad_default(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTEPAD_DATA_DIR", str(tmp_path))
    _write_settings(tmp_path, {"default_save_dir": "c:\\notepad"})
    loaded = settings_manager.load()
    assert loaded["default_save_dir"] == settings_manager.DEFAULT_SAVE_DIR


def test_load_keeps_custom_save_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTEPAD_DATA_DIR", str(tmp_path))
    _write_settings(tmp_path, {"default_save_dir": "D:\\MyNotes"})
    loaded = settings_manager.load()
    assert loaded["default_save_dir"] == "D:\\MyNotes"


def test_resolve_save_dir_creates_configured_folder(tmp_path):
    target = tmp_path / "notes"
    resolved = settings_manager.resolve_save_dir(
        {"default_save_dir": str(target)}
    )
    assert resolved == target
    assert target.is_dir()
