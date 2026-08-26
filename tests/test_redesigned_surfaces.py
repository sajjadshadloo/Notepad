"""The two surfaces the redesign restructured: the sidebar and My Tasks.

The sidebar became three panes behind a switch instead of four things
stacked in one column, and My Tasks grew three ways of reading the same
list. Both are wired to a folder scan, so the tests here care most about
what is shown and when the scan is allowed to happen.
"""
from datetime import datetime, timedelta

import pytest

from core.jalali import format_date
from core.tasks import parse_document
from ui.sidebar import PANES, Sidebar
from ui.today_view import MODES, TodayDialog, when_label


def _stamp(offset_days: int, time: str = "") -> str:
    day = (datetime.now() + timedelta(days=offset_days)).date()
    return "@" + format_date(day, persian_digits=False) + (f" {time}" if time else "")


@pytest.fixture
def notes(tmp_path):
    """A notes folder with one overdue task, one today, one undated."""
    (tmp_path / "Clients").mkdir()
    (tmp_path / "Clients" / "بامسما.md").write_text(
        f"# بامسما\n\n- [ ] ارسال فاکتور {_stamp(-3)}\n"
        f"- [ ] تمدید هاست {_stamp(9)} ↻\n",
        encoding="utf-8",
    )
    (tmp_path / "today.md").write_text(
        f"- [ ] تماس با مشتری {_stamp(0, '23:59')}\n"
        "- [ ] بدون تاریخ\n"
        f"- [x] انجام شده {_stamp(0, '08:00')}\n",
        encoding="utf-8",
    )
    return tmp_path


# The sidebar

def test_the_sidebar_offers_notes_tasks_and_calendar(qapp, notes):
    sidebar = Sidebar(str(notes))
    assert [key for key, _ in PANES] == ["notes", "tasks", "calendar"]
    assert set(sidebar._pane_buttons) == {"notes", "tasks", "calendar"}
    sidebar.deleteLater()


def test_notes_is_the_pane_you_land_on(qapp, notes):
    sidebar = Sidebar(str(notes))
    assert sidebar._pane_buttons["notes"].isChecked()
    assert sidebar._panes.currentIndex() == 0
    sidebar.deleteLater()


def test_switching_panes_checks_exactly_one_button(qapp, notes):
    sidebar = Sidebar(str(notes))
    sidebar.show_pane("calendar")
    checked = [k for k, b in sidebar._pane_buttons.items() if b.isChecked()]
    assert checked == ["calendar"]
    assert sidebar._panes.currentIndex() == 2
    sidebar.deleteLater()


def _count_scans(sidebar) -> list:
    """Stub out the folder read, keeping the staleness bookkeeping it does."""
    scans: list = []

    def fake_scan():
        sidebar._tasks_stale = False
        scans.append(1)

    sidebar._scan_tasks = fake_scan
    return scans


def test_the_notes_pane_does_not_scan_every_file_for_tasks(qapp, notes):
    """Reading every note is what the tasks pane costs; opening the sidebar
    on notes must not pay it."""
    sidebar = Sidebar(str(notes))
    scans = _count_scans(sidebar)
    sidebar.show_pane("notes")
    assert scans == []
    sidebar.show_pane("tasks")
    assert scans == [1]
    sidebar.deleteLater()


def test_a_second_look_at_tasks_reuses_the_last_scan(qapp, notes):
    sidebar = Sidebar(str(notes))
    scans = _count_scans(sidebar)
    sidebar.show_pane("tasks")
    sidebar.show_pane("notes")
    sidebar.show_pane("tasks")
    assert scans == [1], "the folder was rescanned without anything changing"
    sidebar.deleteLater()


def test_a_refresh_makes_the_task_list_stale_again(qapp, notes):
    """Saving a note can add a task, so the next look has to rescan."""
    sidebar = Sidebar(str(notes))
    scans = _count_scans(sidebar)
    sidebar.show_pane("tasks")
    sidebar._tasks_stale = True          # what refresh() sets
    sidebar.show_pane("notes")
    sidebar.show_pane("tasks")
    assert scans == [1, 1]
    sidebar.deleteLater()


def test_the_task_pane_groups_by_urgency(qapp, notes):
    sidebar = Sidebar(str(notes))
    sidebar._tasks_scanned(parse_document(
        (notes / "today.md").read_text(encoding="utf-8"), str(notes / "today.md")
    ) + parse_document(
        (notes / "Clients" / "بامسما.md").read_text(encoding="utf-8"),
        str(notes / "Clients" / "بامسما.md"),
    ))
    headers = sidebar.task_list.header_texts()
    assert "عقب‌افتاده" in headers
    assert "امروز" in headers
    assert "بدون تاریخ" in headers
    sidebar.deleteLater()


def test_a_finished_task_is_not_listed(qapp, notes):
    sidebar = Sidebar(str(notes))
    path = str(notes / "today.md")
    sidebar._tasks_scanned(
        parse_document((notes / "today.md").read_text(encoding="utf-8"), path)
    )
    shown = sidebar.task_list.task_texts()
    assert not any("انجام شده" in text for text in shown)
    sidebar.deleteLater()


# My Tasks

def test_my_tasks_offers_three_readings_of_the_list(qapp, notes):
    dialog = TodayDialog(str(notes))
    assert [key for key, _ in MODES] == ["list", "split", "timeline"]
    dialog.set_mode("timeline")
    assert dialog._stack.currentIndex() == 2
    assert dialog._mode_buttons["timeline"].isChecked()
    assert not dialog._mode_buttons["list"].isChecked()
    dialog.deleteLater()


def test_my_tasks_opens_on_the_plain_list(qapp, notes):
    dialog = TodayDialog(str(notes))
    assert dialog._stack.currentIndex() == 0
    dialog.deleteLater()


def test_the_split_view_separates_today_from_what_is_ahead(qapp, notes):
    dialog = TodayDialog(str(notes))
    today = dialog._today_tree.task_texts()
    ahead = dialog._ahead_tree.task_texts()
    # The overdue one belongs with today's column, not with the future.
    assert any("فاکتور" in text for text in today)
    assert any("هاست" in text for text in ahead)
    dialog.deleteLater()


def test_the_summary_counts_what_is_open_and_what_is_late(qapp, notes):
    dialog = TodayDialog(str(notes))
    text = dialog.summary.text()
    assert "کار باز" in text and "عقب‌افتاده" in text
    dialog.deleteLater()


def test_nothing_is_selected_until_you_pick_something(qapp, notes):
    dialog = TodayDialog(str(notes))
    assert dialog._selected is None
    assert not dialog.snooze_button.isEnabled()
    dialog.deleteLater()


def test_an_undated_task_cannot_be_pushed_to_tomorrow(qapp, notes):
    dialog = TodayDialog(str(notes))
    undated = next(t for t in dialog._tasks if t.due is None)
    dialog._set_detail(undated)
    assert not dialog.snooze_button.isEnabled()
    dialog.deleteLater()


def test_a_dated_task_can_be_pushed_to_tomorrow(qapp, notes):
    dialog = TodayDialog(str(notes))
    dated = next(t for t in dialog._tasks if t.due is not None)
    dialog._set_detail(dated)
    assert dialog.snooze_button.isEnabled()
    dialog.deleteLater()


def test_snoozing_asks_the_window_rather_than_writing_the_file(qapp, notes):
    """The note may be open with unsaved edits; writing under it loses them."""
    dialog = TodayDialog(str(notes))
    dated = next(t for t in dialog._tasks if t.due is not None)
    dialog._set_detail(dated)
    seen = []
    dialog.snooze_requested.connect(lambda *args: seen.append(args))
    before = (notes / "Clients" / "بامسما.md").read_text(encoding="utf-8")
    dialog._snooze_selected()
    assert seen == [(dated.path, dated.line_number, 1)]
    assert (notes / "Clients" / "بامسما.md").read_text(encoding="utf-8") == before
    dialog.deleteLater()


# Labels

def test_a_repeating_task_shows_its_mark_in_the_label(qapp, notes):
    from core.tasks import parse_task

    task = parse_task("- [ ] x @1405/06/04 14:30 ↻")
    assert when_label(task).endswith("↻")


def test_an_undated_task_has_no_when_label(qapp, notes):
    from core.tasks import parse_task

    assert when_label(parse_task("- [ ] x")) == ""
