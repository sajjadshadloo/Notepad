"""The repeat mark, and the two edits that write task stamps.

These are the pieces of the redesign that change what lands in the file, so
they are pinned here: a stamp that is rewritten must come back in the same
calendar, with the same separator and the same digits it was written with.
"""
from datetime import date, datetime

import pytest

from core.tasks import (
    REPEAT_MARK,
    add_stamp,
    group_of,
    parse_task,
    shift_stamp,
    today_progress,
    toggle_repeat,
)


def test_the_repeat_mark_is_read_and_kept_out_of_the_text():
    task = parse_task("- [ ] بررسی سبد خرید @1405/06/04 14:30 ↻")
    assert task.repeats
    assert task.text == "بررسی سبد خرید"
    assert task.due == datetime(2026, 8, 26, 14, 30)


def test_a_task_without_the_mark_does_not_repeat():
    assert not parse_task("- [ ] تحویل سایت @1405/06/05 10:00").repeats


def test_a_repeating_task_rolls_forward_instead_of_staying_overdue():
    """Last week's instance is done with; what matters is the next one."""
    task = parse_task("- [ ] weekly @2026-08-01 09:00 ↻")
    now = datetime(2026, 8, 26, 12, 0)
    assert task.next_due(now) == datetime(2026, 8, 29, 9, 0)
    assert group_of(task, now) == "بعداً"


def test_a_repeating_task_still_pending_keeps_its_first_date():
    task = parse_task("- [ ] weekly @2026-09-10 09:00 ↻")
    now = datetime(2026, 8, 26, 12, 0)
    assert task.next_due(now) == datetime(2026, 9, 10, 9, 0)


def test_a_one_off_task_is_never_rolled_forward():
    task = parse_task("- [ ] once @2026-08-01 09:00")
    now = datetime(2026, 8, 26, 12, 0)
    assert task.next_due(now) == datetime(2026, 8, 1, 9, 0)
    assert group_of(task, now) == "عقب‌افتاده"


# Rewriting a stamp

def test_shifting_keeps_the_jalali_calendar_and_the_time():
    assert shift_stamp("- [ ] x @1405/06/04 14:30", 1) == "- [ ] x @1405/06/05 14:30"


def test_shifting_keeps_persian_digits_when_that_is_how_it_was_written():
    moved = shift_stamp("- [ ] x @۱۴۰۵/۰۶/۰۵ ۱۰:۰۰", 1)
    assert moved == "- [ ] x @۱۴۰۵/۰۶/۰۶ ۱۰:۰۰"


def test_shifting_a_gregorian_stamp_stays_gregorian():
    assert shift_stamp("- [ ] x @2026-08-27", 1) == "- [ ] x @2026-08-28"


def test_shifting_crosses_a_jalali_month_boundary():
    # 1405/06/31 is the last day of شهریور.
    assert shift_stamp("- [ ] x @1405/06/31", 1) == "- [ ] x @1405/07/01"


def test_shifting_a_line_with_no_stamp_reports_nothing_to_do():
    assert shift_stamp("- [ ] no date here", 1) is None


def test_the_repeat_mark_survives_a_shift():
    assert shift_stamp("- [ ] x @1405/06/04 ↻", 1) == "- [ ] x @1405/06/05 ↻"


# Toggling the mark

def test_toggling_adds_then_removes_the_mark():
    line = "- [ ] x @1405/06/04"
    with_mark = toggle_repeat(line)
    assert with_mark == "- [ ] x @1405/06/04 " + REPEAT_MARK
    assert toggle_repeat(with_mark) == line


def test_an_undated_task_cannot_repeat():
    """There is nothing for a week to be counted from."""
    assert toggle_repeat("- [ ] no date") == "- [ ] no date"


# Stamping

def test_stamping_writes_jalali_with_persian_digits():
    assert add_stamp("- [ ] کار", date(2026, 8, 26)) == "- [ ] کار @۱۴۰۵/۰۶/۰۴"


def test_stamping_never_moves_a_deadline_that_is_already_set():
    line = "- [ ] کار @1405/06/09"
    assert add_stamp(line, date(2026, 8, 26)) == line


def test_only_a_checkbox_line_gets_a_stamp():
    assert add_stamp("just a note", date(2026, 8, 26)) == "just a note"


# The progress meter

def test_progress_counts_only_todays_dated_work():
    now = datetime(2026, 8, 26, 12, 0)
    tasks = [
        parse_task("- [x] done today @1405/06/04"),
        parse_task("- [ ] open today @1405/06/04 16:00"),
        parse_task("- [ ] tomorrow @1405/06/05"),
        parse_task("- [ ] undated"),
    ]
    assert today_progress(tasks, now) == (1, 2)


def test_progress_is_zero_of_zero_on_an_empty_day():
    assert today_progress([], datetime(2026, 8, 26, 12, 0)) == (0, 0)


@pytest.mark.parametrize("days", [1, 7, 30])
def test_a_shift_always_lands_on_a_real_date(days):
    moved = shift_stamp("- [ ] x @1405/12/29", days)
    assert moved is not None and moved.startswith("- [ ] x @14")
