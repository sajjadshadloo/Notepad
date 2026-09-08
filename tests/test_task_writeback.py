"""Changing a task from outside the editor has to reach the file.

The calendar, the day widget and the tasks window all edit lines they do not
own. A note that happens to be open with unsaved work is the case that loses
typing if this is done naively, so it is covered first.
"""
from datetime import date

import pytest

from core import daily_notes, settings_manager
from core.file_service import read_text_file
from core.tasks import parse_document
from ui.main_window import MainWindow


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    data = tmp_path / "appdata"
    data.mkdir()
    monkeypatch.setattr(settings_manager, "app_data_dir", lambda: data)
    notes = tmp_path / "notes"
    notes.mkdir()
    win = MainWindow([])
    win._cfg["notes_root"] = str(notes)
    yield win
    # A tab with unsaved edits raises a modal "save changes?" prompt on
    # close, which in a headless run blocks the session outright. Each tab
    # is marked clean immediately before it is closed, not all of them up
    # front, so nothing running in between can dirty one again.
    while win.tabs.count():
        win.tabs.widget(0).mark_clean()
        win.close_tab(0, create_replacement=False)
    win._really_quitting = True
    win.close()
    win.deleteLater()


def _tasks_in(path):
    return parse_document(read_text_file(path).text, str(path))


# Adding

def test_adding_a_task_creates_the_day_note(window):
    root = window._cfg["notes_root"]
    day = date(2026, 8, 27)
    assert window.add_task_to_day(day, "فاکتور مروارید")

    path = daily_notes.path_for(root, day)
    assert path.exists()
    texts = [t.text for t in _tasks_in(path)]
    assert texts == ["فاکتور مروارید"]


def test_a_task_added_from_the_calendar_carries_that_day(window):
    day = date(2026, 8, 27)
    window.add_task_to_day(day, "تماس با حمید")
    task = _tasks_in(daily_notes.path_for(window._cfg["notes_root"], day))[0]
    assert task.due.date() == day
    assert not task.has_time


def test_a_blank_task_is_refused(window):
    assert not window.add_task_to_day(date(2026, 8, 27), "   ")
    assert not daily_notes.path_for(
        window._cfg["notes_root"], date(2026, 8, 27)
    ).exists()


def test_two_tasks_on_one_day_share_the_note(window):
    day = date(2026, 8, 27)
    window.add_task_to_day(day, "یک")
    window.add_task_to_day(day, "دو")
    path = daily_notes.path_for(window._cfg["notes_root"], day)
    assert [t.text for t in _tasks_in(path)] == ["یک", "دو"]


# Ticking

def test_ticking_a_task_writes_it_to_a_closed_file(window):
    day = date(2026, 8, 27)
    window.add_task_to_day(day, "کار")
    path = daily_notes.path_for(window._cfg["notes_root"], day)
    task = _tasks_in(path)[0]

    window.set_task_done(str(path), task.line_number, True)
    assert _tasks_in(path)[0].done


def test_unticking_puts_it_back(window):
    day = date(2026, 8, 27)
    window.add_task_to_day(day, "کار")
    path = daily_notes.path_for(window._cfg["notes_root"], day)
    line = _tasks_in(path)[0].line_number

    window.set_task_done(str(path), line, True)
    window.set_task_done(str(path), line, False)
    assert not _tasks_in(path)[0].done


def test_ticking_a_task_that_is_already_done_changes_nothing(window):
    day = date(2026, 8, 27)
    window.add_task_to_day(day, "کار")
    path = daily_notes.path_for(window._cfg["notes_root"], day)
    line = _tasks_in(path)[0].line_number
    window.set_task_done(str(path), line, True)
    before = path.read_text(encoding="utf-8")

    window.set_task_done(str(path), line, True)
    assert path.read_text(encoding="utf-8") == before


def test_an_open_note_is_edited_through_its_document_not_the_disk(window):
    """The case that loses work: the file is open and has unsaved edits.

    Writing to disk here would be overwritten by the next save, or would
    overwrite what is on screen. The edit has to go through the document.
    """
    day = date(2026, 8, 27)
    window.add_task_to_day(day, "کار")
    path = daily_notes.path_for(window._cfg["notes_root"], day)
    window.open_file(str(path))
    tab = window.current_document()

    cursor = tab.editor.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    cursor.insertText("\nیادداشت دست‌نویس که هنوز ذخیره نشده")
    assert tab.modified

    line = _tasks_in(path)[0].line_number
    window.set_task_done(str(path), line, True)

    assert "- [x]" in tab.text
    assert "یادداشت دست‌نویس که هنوز ذخیره نشده" in tab.text
    # Still untouched on disk: nothing was saved, and nothing was lost.
    assert "- [ ]" in path.read_text(encoding="utf-8")


def test_the_change_to_an_open_note_is_one_undo_step(window):
    day = date(2026, 8, 27)
    window.add_task_to_day(day, "کار")
    path = daily_notes.path_for(window._cfg["notes_root"], day)
    window.open_file(str(path))
    tab = window.current_document()
    before = tab.text

    window.set_task_done(str(path), _tasks_in(path)[0].line_number, True)
    assert tab.text != before
    tab.editor.undo()
    assert tab.text == before


def test_a_line_that_is_not_a_task_is_left_alone(window):
    root = window._cfg["notes_root"]
    path = root + "/prose.md"
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("یک خط معمولی\n")

    window.set_task_done(path, 0, True)
    with open(path, encoding="utf-8") as handle:
        assert handle.read() == "یک خط معمولی\n"


def test_a_line_number_past_the_end_is_survivable(window):
    day = date(2026, 8, 27)
    window.add_task_to_day(day, "کار")
    path = daily_notes.path_for(window._cfg["notes_root"], day)
    before = path.read_text(encoding="utf-8")

    window.set_task_done(str(path), 999, True)
    assert path.read_text(encoding="utf-8") == before


# What the day panel does the instant you press Enter
#
# Both of these looked like the app ignoring the click: the task was written
# but the day stayed empty, and the day-note button opened a tab behind the
# calendar where nothing could be seen.

def test_a_new_task_appears_in_the_panel_at_once(window):
    """No waiting for the background scan — that reads as a dead Enter key."""
    window.show_page("calendar")
    today = date.today()
    window.month_view.select_day(today)

    window.month_view._input.setText("فاکتور مروارید")
    window.month_view._submit()

    assert window.month_view._list.texts() == ["فاکتور مروارید"]
    assert [t.text for t in window.month_view.tasks_on(today)] == ["فاکتور مروارید"]


def test_a_second_task_joins_the_first_rather_than_replacing_it(window):
    window.show_page("calendar")
    today = date.today()
    window.month_view.select_day(today)
    for text in ("یک", "دو"):
        window.month_view._input.setText(text)
        window.month_view._submit()

    assert set(window.month_view._list.texts()) == {"یک", "دو"}


def test_opening_a_days_note_switches_to_the_editor(window):
    """The tab used to open behind the calendar, so the button looked dead."""
    window.show_page("calendar")
    window.open_daily_note(date(2026, 8, 27))

    assert window.pages.currentIndex() == window.PAGE_INDEX["editor"]
    assert window.current_document().display_name == "1405-06-05.md"


def test_a_day_with_no_note_offers_to_write_one(window):
    window.month_view.set_root(window._cfg["notes_root"])
    window.month_view.select_day(date(2026, 8, 27))
    assert window.month_view._open_note.text() == "نوشتن یادداشت این روز"


def test_once_the_day_has_a_note_the_button_says_open(window):
    window.month_view.set_root(window._cfg["notes_root"])
    day = date(2026, 8, 27)
    window.add_task_to_day(day, "کار")
    window.month_view.select_day(day)
    assert window.month_view._open_note.text() == "باز کردن یادداشت روز"
