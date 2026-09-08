"""The three surfaces 4.1 added: the notes board, the month, the day widget.

All three are views over the same files, so what they must never do is
disagree with each other or invent state of their own.
"""
from datetime import date, timedelta

import pytest

from core import daily_notes
from core.note_library import load_library
from core.task_scan import scan_folder
from ui.day_widget import DayWidget
from ui.month_view import MonthView
from ui.notes_board import ALL_LABEL, NotesBoard


@pytest.fixture
def notes(tmp_path):
    root = tmp_path / "notes"
    (root / "Work").mkdir(parents=True)
    (root / "a.md").write_text("# یادداشت اول\n\nمتن\n", encoding="utf-8")
    (root / "Work" / "b.md").write_text("- [ ] کار کاری\n", encoding="utf-8")
    return root


@pytest.fixture
def dated(notes):
    """A folder with real dated work spread over three days."""
    today = date.today()
    daily_notes.add_task(notes, today, "فاکتور مروارید")
    daily_notes.add_task(notes, today, "تماس با حمید")
    daily_notes.add_task(notes, today + timedelta(days=2), "دیپلوی اطلس")
    return notes


# Notes board

def test_the_board_shows_every_note_under_the_all_tab(qapp, notes):
    board = NotesBoard(str(notes))
    board._show(load_library(notes))
    assert set(board.card_titles()) == {"یادداشت اول", "b"}
    board.deleteLater()


def test_the_board_offers_a_tab_per_folder(qapp, notes):
    board = NotesBoard(str(notes))
    board._show(load_library(notes))
    assert board.category_names() == [ALL_LABEL, "عمومی", "Work"]
    board.deleteLater()


def test_choosing_a_folder_narrows_the_cards(qapp, notes):
    board = NotesBoard(str(notes))
    board._show(load_library(notes))
    board.show_category("Work")
    assert board.card_titles() == ["b"]
    board.deleteLater()


def test_one_folder_alone_hides_the_tabs(qapp, tmp_path):
    """"همه" plus a single category is two buttons saying the same thing.

    Shown before asserting: isVisible() is False for any widget that was
    never shown, so an unshown board would pass this without meaning it.
    """
    root = tmp_path / "notes"
    root.mkdir()
    (root / "a.md").write_text("متن\n", encoding="utf-8")
    board = NotesBoard(str(root))
    board.show()
    board._show(load_library(root))
    qapp.processEvents()
    assert not board._tabs_holder.isVisible()

    (root / "Work").mkdir()
    (root / "Work" / "b.md").write_text("متن\n", encoding="utf-8")
    board._show(load_library(root))
    qapp.processEvents()
    assert board._tabs_holder.isVisible()
    board.close()
    board.deleteLater()


def test_an_empty_folder_says_so_instead_of_showing_a_blank_grid(qapp, tmp_path):
    root = tmp_path / "empty"
    root.mkdir()
    board = NotesBoard(str(root))
    board.show()
    board._show([])
    qapp.processEvents()
    assert board._empty.isVisible()
    assert not board.grid.isVisible()

    (root / "a.md").write_text("متن\n", encoding="utf-8")
    board._show(load_library(root))
    qapp.processEvents()
    assert board.grid.isVisible()
    assert not board._empty.isVisible()
    board.close()
    board.deleteLater()


def test_opening_a_card_reports_its_path(qapp, notes):
    board = NotesBoard(str(notes))
    board._show(load_library(notes))
    seen = []
    board.note_activated.connect(seen.append)
    board.grid._activate(board.grid.item(0))
    assert seen and seen[0].endswith(".md")
    board.deleteLater()


# Month

def test_the_month_shows_a_days_tasks_in_its_cell(qapp, dated):
    view = MonthView()
    view.set_tasks(scan_folder(str(dated)))
    today = date.today()
    assert {t.text for t in view.tasks_on(today)} == {
        "فاکتور مروارید",
        "تماس با حمید",
    }
    view.deleteLater()


def test_undated_tasks_never_reach_the_calendar(qapp, dated):
    """The folder has an undated task; a calendar has nowhere to put it."""
    view = MonthView()
    view.set_tasks(scan_folder(str(dated)))
    assert all(task.due is not None for task in view._tasks)
    assert "کار کاری" not in {t.text for t in view._tasks}
    view.deleteLater()


def test_selecting_a_day_fills_the_panel(qapp, dated):
    view = MonthView()
    view.set_tasks(scan_folder(str(dated)))
    view.select_day(date.today())
    assert "فاکتور مروارید" in view._list.texts()
    view.deleteLater()


def test_a_day_with_nothing_on_it_says_so(qapp, dated):
    view = MonthView()
    view.set_tasks(scan_folder(str(dated)))
    view.select_day(date.today() + timedelta(days=5))
    assert view._list.texts() == ["کاری برای این روز نیست"]
    view.deleteLater()


def test_typing_a_task_reports_the_day_and_the_text(qapp, dated):
    view = MonthView()
    view.set_tasks(scan_folder(str(dated)))
    chosen = date.today() + timedelta(days=1)
    view.select_day(chosen)
    seen = []
    view.task_added.connect(lambda day, text: seen.append((day, text)))
    view._input.setText("کار تازه")
    view._submit()
    assert seen == [(chosen, "کار تازه")]
    # The field clears, or the next task starts with the last one's text.
    assert view._input.text() == ""
    view.deleteLater()


def test_an_empty_line_adds_nothing(qapp, dated):
    view = MonthView()
    seen = []
    view.task_added.connect(lambda day, text: seen.append(text))
    view._input.setText("   ")
    view._submit()
    assert seen == []
    view.deleteLater()


def test_moving_months_keeps_the_tasks(qapp, dated):
    view = MonthView()
    view.set_tasks(scan_folder(str(dated)))
    before = len(view._tasks)
    view.shift(1)
    view.shift(-1)
    assert len(view._tasks) == before
    assert view.tasks_on(date.today())
    view.deleteLater()


# Day widget

def test_the_widget_shows_only_today(qapp, dated):
    widget = DayWidget()
    widget.set_tasks(scan_folder(str(dated)))
    assert set(widget.task_texts()) == {"فاکتور مروارید", "تماس با حمید"}
    widget.deleteLater()


def test_the_widget_counts_what_is_done(qapp, notes):
    today = date.today()
    daily_notes.add_task(notes, today, "یک")
    daily_notes.add_task(notes, today, "دو")
    path = daily_notes.path_for(notes, today)
    path.write_text(
        path.read_text(encoding="utf-8").replace("- [ ] یک", "- [x] یک", 1),
        encoding="utf-8",
    )
    widget = DayWidget()
    widget.set_tasks(scan_folder(str(notes)))
    assert "۱" in widget.progress.text() and "۲" in widget.progress.text()
    widget.deleteLater()


def test_an_empty_day_says_so(qapp, notes):
    widget = DayWidget()
    widget.set_tasks(scan_folder(str(notes)))
    assert widget.task_texts() == []
    assert widget.list.texts() == ["امروز کاری ثبت نشده"]
    widget.deleteLater()


def test_ticking_a_box_on_the_widget_reports_the_line(qapp, dated):
    widget = DayWidget()
    widget.set_tasks(scan_folder(str(dated)))
    seen = []
    widget.task_toggled.connect(lambda p, line, done: seen.append((p, line, done)))
    item = widget.list.item(0)
    widget.list.task_toggled.emit(
        *widget.list.payload_of(item), True
    )
    assert seen and seen[0][2] is True
    widget.deleteLater()


# Launching straight onto a page
#
# The window restores its last page inside __init__, before the task watcher
# used to exist. Opening onto the calendar therefore crashed on launch, with
# no window ever shown — and the setting that caused it was written by the
# previous run, so it would have crashed every time until settings were
# cleared by hand.

@pytest.mark.parametrize("page", ["notes", "calendar", "editor"])
def test_the_window_can_open_on_any_page(qapp, tmp_path, monkeypatch, page):
    from core import settings_manager
    from ui.main_window import MainWindow

    data = tmp_path / "appdata"
    data.mkdir()
    monkeypatch.setattr(settings_manager, "app_data_dir", lambda: data)
    settings_manager.save({**settings_manager.DEFAULTS, "page": page})

    window = MainWindow([])
    assert window.pages.currentIndex() == window.PAGE_INDEX[page]

    for index in range(window.tabs.count()):
        window.tabs.widget(index).mark_clean()
    window._really_quitting = True
    window.close()
    window.deleteLater()


def test_an_unknown_saved_page_is_survivable(qapp, tmp_path, monkeypatch):
    """A setting from a future version must not take the window down."""
    from core import settings_manager
    from ui.main_window import MainWindow

    data = tmp_path / "appdata"
    data.mkdir()
    monkeypatch.setattr(settings_manager, "app_data_dir", lambda: data)
    settings_manager.save({**settings_manager.DEFAULTS, "page": "gallery"})

    window = MainWindow([])
    assert window.pages.currentIndex() in window.PAGE_INDEX.values()

    for index in range(window.tabs.count()):
        window.tabs.widget(index).mark_clean()
    window._really_quitting = True
    window.close()
    window.deleteLater()
