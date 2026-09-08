"""The My Tasks window (Ctrl+T).

4.1 replaced the sidebar with the notes board and the calendar, so the
sidebar half of this file went with it. What is left is the window that
still exists.

My Tasks once grew three ways of reading the same list; 4.0 cut it back to
one. What it shows, and when it is allowed to scan the folder, is what these
tests care about.
"""
from datetime import datetime, timedelta

import pytest

from core.jalali import format_date
from ui.today_view import TodayDialog, when_label


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


# My Tasks

def test_my_tasks_is_one_grouped_list(qapp, notes):
    """4.0 dropped the split and timeline arrangements; this is what is left."""
    dialog = TodayDialog(str(notes))
    assert not hasattr(dialog, "_stack")
    assert not hasattr(dialog, "_mode_buttons")
    texts = dialog._list_tree.card_texts()
    assert any("فاکتور" in text for text in texts)
    assert any("هاست" in text for text in texts)
    dialog.deleteLater()


def test_my_tasks_groups_by_urgency(qapp, notes):
    dialog = TodayDialog(str(notes))
    headers = dialog._list_tree.header_texts()
    assert "عقب‌افتاده" in headers
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
