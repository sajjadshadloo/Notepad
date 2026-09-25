"""The three surfaces: the notes board, the today rail, the day widget.

All three are views over the same files, so what they must never do is
disagree with each other or invent state of their own.
"""
from datetime import date, timedelta

import pytest

from core import task_file
from core.note_library import load_library
from core.task_scan import scan_folder
from ui.day_widget import DayWidget
from ui.notes_board import ALL_LABEL, NotesBoard
from ui.today_rail import TodayRail


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
    task_file.add_task(notes, today, "فاکتور مروارید")
    task_file.add_task(notes, today, "تماس با حمید")
    task_file.add_task(notes, today + timedelta(days=2), "دیپلوی اطلس")
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


def test_the_home_view_switches_between_cards_and_a_list(qapp, notes):
    """The design's grid/list toggle: the same notes, two layouts."""
    board = NotesBoard(str(notes))
    board.show()
    board._show(load_library(notes))
    board.set_view("list")
    qapp.processEvents()
    assert board.list.isVisible() and not board.grid.isVisible()
    board.set_view("grid")
    qapp.processEvents()
    assert board.grid.isVisible() and not board.list.isVisible()
    board.close()
    board.deleteLater()


def test_pinned_notes_come_first(qapp, notes):
    board = NotesBoard(str(notes))
    board._show(load_library(notes))
    pinned = next(c.path for c in board.shown_cards() if c.title == "b")
    board.set_pinned([pinned])
    assert board.card_titles()[0] == "b"
    board.deleteLater()


def test_an_empty_folder_shows_no_cards(qapp, tmp_path):
    root = tmp_path / "empty"
    root.mkdir()
    board = NotesBoard(str(root))
    board._show([])
    assert board.card_titles() == []
    board.deleteLater()


def test_opening_a_card_reports_its_path(qapp, notes):
    board = NotesBoard(str(notes))
    board._show(load_library(notes))
    seen = []
    board.note_activated.connect(seen.append)
    board.grid.activate(0)
    assert seen and seen[0].endswith(".md")
    board.deleteLater()


# The today rail

def test_the_rail_holds_a_days_tasks(qapp, dated):
    view = TodayRail()
    view.set_tasks(scan_folder(str(dated)))
    today = date.today()
    assert {t.text for t in view.tasks_on(today)} == {
        "فاکتور مروارید",
        "تماس با حمید",
    }
    view.deleteLater()


def test_undated_tasks_never_reach_the_rail(qapp, dated):
    """The folder has an undated task; a day list has nowhere to put it."""
    view = TodayRail()
    view.set_tasks(scan_folder(str(dated)))
    assert all(task.due is not None for task in view._tasks)
    assert "کار کاری" not in {t.text for t in view._tasks}
    view.deleteLater()


def test_selecting_a_day_fills_the_panel(qapp, dated):
    view = TodayRail()
    view.set_tasks(scan_folder(str(dated)))
    view.show_day(date.today())
    assert "فاکتور مروارید" in view.list.texts()
    view.deleteLater()


def test_a_day_with_nothing_on_it_says_so(qapp, dated):
    view = TodayRail()
    view.set_tasks(scan_folder(str(dated)))
    view.show_day(date.today() + timedelta(days=5))
    assert view.list.texts() == []
    assert view.list.empty_text() == "برای این روز کاری نیست."
    view.deleteLater()


def test_typing_a_task_reports_the_day_and_the_text(qapp, dated):
    view = TodayRail()
    view.set_tasks(scan_folder(str(dated)))
    chosen = date.today() + timedelta(days=1)
    view.show_day(chosen)
    seen = []
    view.task_added.connect(lambda day, text: seen.append((day, text)))
    view.input.setText("کار تازه")
    view._submit()
    assert seen == [(chosen, "کار تازه")]
    # The field clears, or the next task starts with the last one's text.
    assert view.input.text() == ""
    view.deleteLater()


def test_an_empty_line_adds_nothing(qapp, dated):
    view = TodayRail()
    seen = []
    view.task_added.connect(lambda day, text: seen.append(text))
    view.input.setText("   ")
    view._submit()
    assert seen == []
    view.deleteLater()


def test_moving_months_keeps_the_tasks(qapp, dated):
    view = TodayRail()
    view.set_tasks(scan_folder(str(dated)))
    before = len(view._tasks)
    view.calendar.shift(1)
    view.calendar.shift(-1)
    assert len(view._tasks) == before
    assert view.tasks_on(date.today())
    view.deleteLater()


def test_a_day_carrying_work_is_marked_on_the_month(qapp, dated):
    view = TodayRail()
    view.set_tasks(scan_folder(str(dated)))
    assert date.today() in view.calendar._busy
    assert date.today() + timedelta(days=1) not in view.calendar._busy
    view.deleteLater()


def test_returning_to_today_is_offered_only_when_you_have_left_it(qapp, dated):
    view = TodayRail()
    view.set_tasks(scan_folder(str(dated)))
    view.show_day(date.today())
    assert not view.today_button.isVisible() or view.selected_day() == date.today()
    view.show_day(date.today() + timedelta(days=3))
    assert view.selected_day() != date.today()
    view.deleteLater()


# Day widget

def test_the_widget_shows_only_today(qapp, dated):
    widget = DayWidget()
    widget.set_tasks(scan_folder(str(dated)))
    assert set(widget.task_texts()) == {"فاکتور مروارید", "تماس با حمید"}
    widget.deleteLater()


def test_the_widget_counts_what_is_done(qapp, notes):
    today = date.today()
    task_file.add_task(notes, today, "یک")
    task_file.add_task(notes, today, "دو")
    path = task_file.path_for(notes)
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

@pytest.mark.parametrize("page", ["home", "editor"])
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


def test_the_tasks_file_is_not_also_a_card(qapp, dated):
    """It owns the rail; a card repeating it beside the rail is noise."""
    titles = [card.title for card in load_library(dated)]
    assert "کارها" not in titles


# The desktop panel's manners
#
# 4.2.0 pinned it on top of every window and parked it bottom-left, which on
# Windows is where the desktop icons are. Both were wrong for something meant
# to sit quietly on the desktop.

def test_the_widget_stays_behind_other_windows(qapp):
    from PyQt6.QtCore import Qt

    widget = DayWidget()
    flags = widget.windowFlags()
    assert flags & Qt.WindowType.WindowStaysOnBottomHint
    assert not (flags & Qt.WindowType.WindowStaysOnTopHint)
    widget.deleteLater()


def test_it_defaults_to_the_corner_the_icons_are_not_in(qapp):
    widget = DayWidget()
    screen = qapp.primaryScreen()
    widget.place(screen)
    area = screen.availableGeometry()
    assert widget.x() > area.center().x(), "should be on the right, not over the icons"
    widget.deleteLater()


def test_a_remembered_position_is_used(qapp):
    widget = DayWidget()
    screen = qapp.primaryScreen()
    area = screen.availableGeometry()
    wanted = (area.left() + 120, area.top() + 90)
    widget.place(screen, wanted)
    assert (widget.x(), widget.y()) == wanted
    widget.deleteLater()


def test_a_position_off_every_screen_falls_back_to_the_corner(qapp):
    """Monitors get unplugged; the panel must not vanish with them."""
    widget = DayWidget()
    screen = qapp.primaryScreen()
    widget.place(screen, (-9000, -9000))
    area = screen.availableGeometry()
    assert area.contains(widget.pos())
    widget.deleteLater()


def test_dragging_it_reports_where_it_landed(qapp):
    from PyQt6.QtCore import QPoint

    widget = DayWidget()
    seen = []
    widget.moved.connect(seen.append)
    widget._drag_from = QPoint(0, 0)
    widget.move(300, 200)
    widget.mouseReleaseEvent(None)
    assert seen and (seen[0].x(), seen[0].y()) == (300, 200)
    widget.deleteLater()
