from ui.main_window import MainWindow
from PyQt6.QtWidgets import QInputDialog


def test_switching_tabs_preserves_unsaved_text(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("NOTEPAD_DATA_DIR", str(tmp_path / "appdata"))
    window = MainWindow([])
    window._recovery_timer.stop()
    first = window.current_document()
    first.editor.setPlainText("متن ذخیره‌نشده")
    first.editor.document().setModified(True)

    window.new_document()
    second = window.current_document()
    second.editor.setPlainText("سند دوم")
    window.tabs.setCurrentWidget(first)

    assert first.text == "متن ذخیره‌نشده"
    assert first.modified
    assert second.text == "سند دوم"

    for index in range(window.tabs.count()):
        window.tabs.widget(index).editor.document().setModified(False)
    window._closing_application = True
    while window.tabs.count():
        window.close_tab(0, create_replacement=False)
    window.close()


def test_untitled_document_can_be_renamed(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("NOTEPAD_DATA_DIR", str(tmp_path / "appdata"))
    monkeypatch.setattr(
        QInputDialog,
        "getText",
        staticmethod(lambda *args, **kwargs: ("یادداشت جلسه", True)),
    )
    window = MainWindow([])
    window._recovery_timer.stop()

    window.rename_current_document()

    tab = window.current_document()
    assert tab.display_name == "یادداشت جلسه"
    assert "یادداشت جلسه" in window.tabs.tabText(window.tabs.currentIndex())
    assert tab.modified

    tab.editor.document().setModified(False)
    window._closing_application = True
    window.close_tab(0, create_replacement=False)
    window.close()


def test_saved_document_rename_changes_real_file(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("NOTEPAD_DATA_DIR", str(tmp_path / "appdata"))
    source = tmp_path / "old.txt"
    source.write_text("hello", encoding="utf-8")
    monkeypatch.setattr(
        QInputDialog,
        "getText",
        staticmethod(lambda *args, **kwargs: ("new-title", True)),
    )
    window = MainWindow([str(source)])
    window._recovery_timer.stop()

    window.rename_current_document()

    destination = tmp_path / "new-title.txt"
    assert not source.exists()
    assert destination.read_text(encoding="utf-8") == "hello"
    assert window.current_document().path == str(destination.resolve())
    assert window.current_document().display_name == "new-title.txt"
    # Renaming has to move the watch with the file, or an edit made
    # outside the editor afterwards goes unnoticed.
    assert window._file_monitor._normalize(source) not in window._file_monitor.watched_paths()
    assert window._file_monitor._normalize(destination) in window._file_monitor.watched_paths()

    window._closing_application = True
    window.close_tab(0, create_replacement=False)
    window.close()


def test_plus_button_opens_a_new_document(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("NOTEPAD_DATA_DIR", str(tmp_path / "appdata"))
    window = MainWindow([])
    window._recovery_timer.stop()
    initial_count = window.tabs.count()

    window.document_tab_bar.new_button.click()

    assert window.tabs.count() == initial_count + 1
    assert window.current_document().display_name == "Untitled"

    for index in range(window.tabs.count()):
        window.tabs.widget(index).editor.document().setModified(False)
    window._closing_application = True
    while window.tabs.count():
        window.close_tab(0, create_replacement=False)
    window.close()
