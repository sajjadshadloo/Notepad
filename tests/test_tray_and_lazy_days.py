"""4.0's two behavioural changes, checked on a real window.

* Closing the window hides it to the tray instead of ending the process.
* Opening a day writes nothing until there is something to write.
"""
from datetime import date
from pathlib import Path

import pytest
from PyQt6.QtGui import QCloseEvent

from core import daily_notes, settings_manager
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
    win._really_quitting = True
    win.close()
    win.deleteLater()


# Day notes

def test_opening_a_day_writes_nothing_to_disk(window, tmp_path):
    root = Path(window._cfg["notes_root"])
    window.open_daily_note(date(2026, 8, 27))
    assert not daily_notes.path_for(root, date(2026, 8, 27)).exists()
    assert not (root / daily_notes.FOLDER).exists() or not list(
        (root / daily_notes.FOLDER).glob("*.md")
    )


def test_the_day_opens_as_a_tab_named_after_its_file(window):
    window.open_daily_note(date(2026, 8, 27))
    tab = window.current_document()
    assert tab.path is None
    assert tab.pending_path.endswith("1405-06-05.md")
    assert tab.display_name == "1405-06-05.md"


def test_the_day_opens_prefilled_with_its_heading(window):
    window.open_daily_note(date(2026, 8, 27))
    assert window.current_document().text == daily_notes.starter_text(
        date(2026, 8, 27)
    )


def test_visiting_the_same_day_twice_reuses_the_tab(window):
    window.open_daily_note(date(2026, 8, 27))
    before = window.tabs.count()
    window.open_daily_note(date(2026, 8, 27))
    assert window.tabs.count() == before


def test_saving_the_day_needs_no_dialog_and_lands_on_its_path(window, monkeypatch):
    """The filename is already decided, so Ctrl+S must not ask for one."""
    monkeypatch.setattr(
        window, "save_current_as", lambda: pytest.fail("should not be asked")
    )
    window.open_daily_note(date(2026, 8, 27))
    tab = window.current_document()
    tab.editor.insertPlainText("تماس با مشتری")

    assert window.save_current()
    assert Path(tab.path) == daily_notes.path_for(
        window._cfg["notes_root"], date(2026, 8, 27)
    )
    assert "تماس با مشتری" in Path(tab.path).read_text(encoding="utf-8")


def test_a_day_that_already_has_a_file_opens_that_file(window):
    root = window._cfg["notes_root"]
    path = daily_notes.path_for(root, date(2026, 8, 27))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# قبلا نوشته شده\n", encoding="utf-8")

    window.open_daily_note(date(2026, 8, 27))
    tab = window.current_document()
    assert tab.path == str(path.resolve())
    assert "قبلا نوشته شده" in tab.text


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


def test_the_empty_day_cleanup_runs_once(window):
    root = window._cfg["notes_root"]
    path = daily_notes.path_for(root, date(2026, 8, 27))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(daily_notes.starter_text(date(2026, 8, 27)), encoding="utf-8")

    window._cfg["daily_cleanup_done"] = False
    window._prune_empty_daily_notes()
    assert not path.exists()
    assert window._cfg["daily_cleanup_done"]

    # A second empty note is left alone: the tidy-up was a one-time repair.
    path.write_text("", encoding="utf-8")
    window._prune_empty_daily_notes()
    assert path.exists()
