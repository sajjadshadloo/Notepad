"""4.0's two behavioural changes, checked on a real window.

* Closing the window hides it to the tray instead of ending the process.
* Opening a day writes nothing until there is something to write.
"""
from pathlib import Path

import pytest
from PyQt6.QtGui import QCloseEvent

from core import settings_manager, task_file
from ui.main_window import MainWindow, _app_icon
from ui.tray import Tray


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    """A window whose settings and notes folder are private to one test."""
    data = tmp_path / "appdata"
    data.mkdir()
    monkeypatch.setattr(settings_manager, "app_data_dir", lambda: data)
    notes = tmp_path / "notes"
    notes.mkdir()
    monkeypatch.setattr(
        settings_manager, "DEFAULT_SAVE_DIR", str(notes), raising=False
    )
    win = MainWindow([])
    win._cfg["notes_root"] = str(notes)
    yield win
    _shut_down(win)


def _shut_down(win):
    """Close a window without any chance of a modal prompt.

    A tab with unsaved changes asks "save changes?" on close, and in a
    headless run that dialog has nobody to answer it — the whole session
    stops there. Each tab is marked clean immediately before it is closed,
    rather than all of them up front, so nothing that runs in between can
    dirty one again.
    """
    while win.tabs.count():
        win.tabs.widget(0).mark_clean()
        win.close_tab(0, create_replacement=False)
    win._really_quitting = True
    win.close()
    win.deleteLater()


# The tasks file
#
# 4.1 opened a note per day; 4.2 opens the one file every dated task lives
# in. Neither writes anything until you save — that was the 4.0 fix for a
# folder filling with empty files, and it still holds.

def test_opening_the_tasks_file_writes_nothing_to_disk(window):
    root = Path(window._cfg["notes_root"])
    window.open_tasks_file()
    assert not task_file.path_for(root).exists()
    assert not (root / task_file.LEGACY_FOLDER).exists()


def test_it_opens_as_a_tab_named_after_the_file(window):
    window.open_tasks_file()
    tab = window.current_document()
    assert tab.path is None
    assert tab.pending_path.endswith(task_file.FILE_NAME)
    assert tab.display_name == task_file.FILE_NAME


def test_it_opens_empty_rather_than_prefilled(window):
    """No date heading: that is exactly what 4.2 took out."""
    window.open_tasks_file()
    assert window.current_document().text == ""


def test_opening_it_twice_reuses_the_tab(window):
    window.open_tasks_file()
    before = window.tabs.count()
    window.open_tasks_file()
    assert window.tabs.count() == before


def test_saving_needs_no_dialog_and_lands_on_its_path(window, monkeypatch):
    """The filename is already decided, so Ctrl+S must not ask for one."""
    monkeypatch.setattr(
        window, "save_current_as", lambda: pytest.fail("should not be asked")
    )
    window.open_tasks_file()
    tab = window.current_document()
    tab.editor.insertPlainText("- [ ] تماس با مشتری")

    assert window.save_current()
    assert Path(tab.path) == task_file.path_for(window._cfg["notes_root"])
    assert "تماس با مشتری" in Path(tab.path).read_text(encoding="utf-8")


def test_an_existing_tasks_file_is_opened_rather_than_replaced(window):
    root = window._cfg["notes_root"]
    path = task_file.path_for(root)
    path.write_text("- [ ] کار قدیمی @۱۴۰۵/۰۶/۰۱" + chr(10), encoding="utf-8")

    window.open_tasks_file()
    tab = window.current_document()
    assert tab.path == str(path.resolve())
    assert "کار قدیمی" in tab.text


# Tray
#
# The offscreen platform reports no system tray, so the window never installs
# one and the branch under test would be skipped everywhere it matters. The
# fixture below attaches one directly: QSystemTrayIcon constructs fine without
# a tray to sit in, and closeEvent only ever asks whether it has one.

@pytest.fixture
def trayed(window):
    window._tray = Tray(_app_icon(), window)
    return window


def test_closing_the_window_hides_it_rather_than_quitting(trayed):
    trayed.show()
    event = QCloseEvent()
    trayed.closeEvent(event)
    assert not event.isAccepted()
    assert not trayed.isVisible()


def test_closing_still_saves_the_window_geometry(trayed):
    trayed.show()
    trayed.closeEvent(QCloseEvent())
    assert trayed._cfg["window_geometry"]


def test_the_tray_menu_offers_a_real_way_out(trayed):
    labels = [action.text() for action in trayed._tray.contextMenu().actions()]
    assert "خروج" in labels
    assert "باز کردن" in labels


def test_the_tray_can_bring_the_window_back(trayed):
    trayed.show()
    trayed.closeEvent(QCloseEvent())
    assert not trayed.isVisible()
    trayed._tray.reveal()
    assert trayed.isVisible()


def test_the_tray_notice_is_shown_once_only(trayed):
    window = trayed
    window._cfg["tray_notice_shown"] = False
    window._announce_tray_once()
    assert window._cfg["tray_notice_shown"]
    # Second call must be a no-op, not a second balloon.
    window._announce_tray_once()
    assert window._cfg["tray_notice_shown"]


def test_quitting_deliberately_accepts_the_close(trayed):
    window = trayed
    window._really_quitting = True
    event = QCloseEvent()
    window.closeEvent(event)
    assert event.isAccepted()


def test_the_daily_folder_is_folded_in_once(window):
    """A 4.1 folder of day notes becomes rows in the one tasks file."""
    root = Path(window._cfg["notes_root"])
    folder = root / task_file.LEGACY_FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "1405-06-05.md").write_text(
        "# ۵ شهریور" + chr(10) * 2 + "- [ ] کار قدیمی" + chr(10), encoding="utf-8"
    )

    window._cfg["daily_cleanup_done"] = False
    window._import_legacy_daily_notes()

    assert "کار قدیمی" in task_file.path_for(root).read_text(encoding="utf-8")
    assert not folder.exists()
    assert window._cfg["daily_cleanup_done"]


def test_the_fold_in_does_not_run_a_second_time(window):
    root = Path(window._cfg["notes_root"])
    window._cfg["daily_cleanup_done"] = False
    window._import_legacy_daily_notes()

    folder = root / task_file.LEGACY_FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "1405-06-05.md").write_text("- [ ] بعدی" + chr(10), encoding="utf-8")
    window._import_legacy_daily_notes()
    assert (folder / "1405-06-05.md").exists()


def test_the_tasks_file_replaces_the_blank_starting_tab(window):
    """It used to open beside the empty "Untitled" the app starts with."""
    assert [
        window.tabs.tabText(i) for i in range(window.tabs.count())
    ] == ["Untitled"]

    window.open_tasks_file()

    assert [
        window.tabs.tabText(i) for i in range(window.tabs.count())
    ] == [task_file.FILE_NAME]


def test_it_does_not_displace_a_tab_you_were_using(window):
    """Only an untouched blank tab is a placeholder."""
    window.current_document().editor.insertPlainText("چیزی که نوشته‌ام")
    window.open_tasks_file()

    names = [window.tabs.tabText(i) for i in range(window.tabs.count())]
    assert task_file.FILE_NAME in names
    assert len(names) == 2
