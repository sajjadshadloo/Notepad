from core import recovery_manager


def test_recovery_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTEPAD_DATA_DIR", str(tmp_path))

    recovery_manager.save_recovery(
        "test-id",
        text="متن ذخیره‌نشده",
        path=None,
        encoding="utf-8",
        title="بدون عنوان",
        direction_mode="auto",
    )

    recovered = recovery_manager.load_recoveries()
    assert recovered == [
        {
            "id": "test-id",
            "text": "متن ذخیره‌نشده",
            "path": None,
            "encoding": "utf-8",
            "title": "بدون عنوان",
            "direction_mode": "auto",
        }
    ]

    recovery_manager.remove_recovery("test-id")
    assert recovery_manager.load_recoveries() == []


def test_startup_never_prompts_before_the_window_is_visible(tmp_path, monkeypatch, qapp):
    """A modal prompt raised from __init__ has no visible parent, so it never
    reaches the taskbar and can hide behind other windows — the app then looks
    like it failed to launch. Construction must therefore stay silent.
    """
    monkeypatch.setenv("NOTEPAD_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        "core.settings_manager.resolve_save_dir", lambda cfg: tmp_path
    )
    recovery_manager.save_recovery(
        "pending",
        text="کار ذخیره‌نشده",
        path=None,
        encoding="utf-8",
        title="بدون عنوان",
        direction_mode="rtl",
    )

    from ui import main_window as mw

    prompts: list[str] = []
    monkeypatch.setattr(
        mw.QMessageBox,
        "question",
        lambda *a, **k: prompts.append("asked")
        or mw.QMessageBox.StandardButton.No,
    )

    window = mw.MainWindow([])
    # Constructing the window must not have asked anything yet...
    assert prompts == []
    # ...and it must still be usable, with a document ready to type into.
    assert window.current_document() is not None

    window.show()
    qapp.processEvents()
    assert prompts == ["asked"]

    # Showing the window again must not re-ask and duplicate documents.
    window.hide()
    window.show()
    qapp.processEvents()
    assert prompts == ["asked"]

    window._closing_application = True
    window.close()


def test_recovered_documents_replace_the_blank_startup_tab(tmp_path, monkeypatch, qapp):
    monkeypatch.setenv("NOTEPAD_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        "core.settings_manager.resolve_save_dir", lambda cfg: tmp_path
    )
    recovery_manager.save_recovery(
        "pending",
        text="کار ذخیره‌نشده",
        path=None,
        encoding="utf-8",
        title="بدون عنوان",
        direction_mode="rtl",
    )

    from ui import main_window as mw

    monkeypatch.setattr(
        mw.QMessageBox, "question", lambda *a, **k: mw.QMessageBox.StandardButton.Yes
    )

    window = mw.MainWindow([])
    assert window.tabs.count() == 1  # the blank placeholder
    window.show()
    qapp.processEvents()

    # Exactly the recovered document, with no leftover "Untitled" beside it.
    assert window.tabs.count() == 1
    assert window.current_document().text == "کار ذخیره‌نشده"

    # Recovered tabs are dirty by design; mark clean so closing does not
    # raise the real "save changes?" box, which QMessageBox.question does
    # not cover (_confirm_close builds its own QMessageBox and exec()s it).
    for index in range(window.tabs.count()):
        window.tabs.widget(index).mark_clean()
    window._closing_application = True
    window.close()
