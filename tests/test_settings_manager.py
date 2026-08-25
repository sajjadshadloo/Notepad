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


def test_legacy_font_family_becomes_the_latin_choice(tmp_path, monkeypatch):
    """Before 2.7.0 a single family fronted a fixed chain; Persian always came
    from Vazirmatn behind it, so the stored value was only ever the Latin one."""
    monkeypatch.setenv("NOTEPAD_DATA_DIR", str(tmp_path))
    (tmp_path / "settings.json").write_text(
        json.dumps({"font_family": "Georgia"}), encoding="utf-8"
    )

    loaded = settings_manager.load()
    assert loaded["font_family_latin"] == "Georgia"
    assert loaded["font_family_persian"] == "Vazirmatn"
    assert "font_family" not in loaded


def test_legacy_vazirmatn_primary_still_upgrades_to_inter(tmp_path, monkeypatch):
    """Vazirmatn as the primary family was the pre-2.4.0 default and only
    affected Latin text, so the 2.4.0 upgrade to Inter still applies."""
    monkeypatch.setenv("NOTEPAD_DATA_DIR", str(tmp_path))
    (tmp_path / "settings.json").write_text(
        json.dumps({"font_family": "Vazirmatn"}), encoding="utf-8"
    )

    assert settings_manager.load()["font_family_latin"] == "Inter"


def test_explicit_latin_choice_wins_over_the_legacy_key(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTEPAD_DATA_DIR", str(tmp_path))
    (tmp_path / "settings.json").write_text(
        json.dumps({"font_family": "Georgia", "font_family_latin": "Inter"}),
        encoding="utf-8",
    )

    assert settings_manager.load()["font_family_latin"] == "Inter"


def test_font_chain_puts_segoe_ui_last():
    """Segoe UI carries Arabic glyphs, so anywhere but last it would steal
    Persian text from the family the user actually picked."""
    chain = settings_manager.font_chain(
        {"font_family_latin": "Georgia", "font_family_persian": "Tahoma"}
    )
    assert chain[0] == "Georgia"
    assert chain[1] == "Tahoma"
    assert chain[-1] == "Segoe UI"
    assert len(chain) == len(set(chain)), chain


def test_font_chain_deduplicates_when_both_halves_match():
    chain = settings_manager.font_chain(
        {"font_family_latin": "Vazirmatn", "font_family_persian": "Vazirmatn"}
    )
    assert chain == ["Vazirmatn", "Segoe UI"]


def test_default_direction_is_rtl_and_bad_values_are_repaired(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTEPAD_DATA_DIR", str(tmp_path))
    assert settings_manager.load()["default_direction"] == "rtl"

    (tmp_path / "settings.json").write_text(
        json.dumps({"default_direction": "sideways"}), encoding="utf-8"
    )
    assert settings_manager.load()["default_direction"] == "rtl"

    (tmp_path / "settings.json").write_text(
        json.dumps({"default_direction": "ltr"}), encoding="utf-8"
    )
    assert settings_manager.load()["default_direction"] == "ltr"
