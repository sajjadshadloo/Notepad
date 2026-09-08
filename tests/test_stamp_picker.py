"""Giving a task its date from the @ button.

3.11 added an hour to this; 4.1 took it back out, because nothing reads an
hour any more. These cover the two halves: what the picker hands back, and
what that does to the line.

set_stamp still accepts an hour and parse_task still reads one: notes written
by 3.x carry times, and those files have to keep meaning what they meant.
"""
from datetime import date, time

import pytest

from core.tasks import parse_task, set_stamp
from ui.stamp_picker import StampPicker


# Writing the stamp

def test_a_date_alone_is_written_in_jalali_with_persian_digits():
    assert set_stamp("- [ ] کار", date(2026, 8, 27)) == "- [ ] کار @۱۴۰۵/۰۶/۰۵"


def test_a_time_is_appended_when_one_was_chosen():
    line = set_stamp("- [ ] کار", date(2026, 8, 27), time(14, 30))
    assert line == "- [ ] کار @۱۴۰۵/۰۶/۰۵ ۱۴:۳۰"


def test_choosing_again_replaces_the_old_stamp():
    """The picker is an explicit choice, so it overwrites — unlike the plain
    stamp helper, which refuses to move a deadline you already set."""
    line = "- [ ] کار @۱۴۰۰/۰۱/۰۱ ۰۹:۰۰"
    assert set_stamp(line, date(2026, 8, 27), time(14, 30)) == (
        "- [ ] کار @۱۴۰۵/۰۶/۰۵ ۱۴:۳۰"
    )


def test_a_weekly_repeat_survives_a_reschedule():
    line = "- [ ] کار @۱۴۰۰/۰۱/۰۱ ↻"
    assert set_stamp(line, date(2026, 8, 27), time(9, 0)).endswith("۰۹:۰۰ ↻")


def test_dropping_the_time_leaves_only_a_date():
    line = set_stamp("- [ ] کار @۱۴۰۵/۰۶/۰۵ ۱۴:۳۰", date(2026, 8, 27), None)
    assert line == "- [ ] کار @۱۴۰۵/۰۶/۰۵"


def test_a_line_that_is_not_a_task_is_left_alone():
    assert set_stamp("یادداشت معمولی", date(2026, 8, 27)) == "یادداشت معمولی"


def test_the_written_stamp_reads_back_as_the_same_moment():
    """Round trip: what the picker writes is what the reminder will use."""
    line = set_stamp("- [ ] کار", date(2026, 8, 27), time(14, 30))
    task = parse_task(line)
    assert task.due.date() == date(2026, 8, 27)
    assert task.due.time() == time(14, 30)
    assert task.has_time


def test_a_stamp_with_no_time_is_read_as_nine_in_the_morning():
    task = parse_task(set_stamp("- [ ] کار", date(2026, 8, 27)))
    assert task.due.time() == time(9, 0)
    assert not task.has_time


# The picker itself

@pytest.fixture
def picker(tmp_path, qapp):
    from ui.stamp_picker import StampPicker

    picker = StampPicker(str(tmp_path))
    yield picker
    picker.deleteLater()


def test_it_opens_on_today_when_the_line_has_no_date(picker):
    assert picker._date == date.today()


def test_it_opens_on_the_date_the_line_already_has(tmp_path, qapp):
    from ui.stamp_picker import StampPicker

    picker = StampPicker(str(tmp_path), date(2026, 1, 15))
    assert picker._date == date(2026, 1, 15)
    picker.deleteLater()


# 4.1 removed the hour

def test_the_picker_emits_only_a_date(qapp, tmp_path):
    """No hour is asked for, so the signal carries one value, not two."""
    picker = StampPicker(str(tmp_path), date(2026, 8, 27))
    seen = []
    picker.picked.connect(seen.append)
    picker._accept()
    assert seen == [date(2026, 8, 27)]
    picker.deleteLater()


def test_no_hour_controls_remain(qapp, tmp_path):
    picker = StampPicker(str(tmp_path), date(2026, 8, 27))
    assert not hasattr(picker, "_hour_buttons")
    assert not hasattr(picker, "time_edit")
    picker.deleteLater()


def test_the_stamp_it_writes_carries_no_time():
    line = set_stamp("- [ ] تماس با مشتری", date(2026, 8, 27))
    task = parse_task(line)
    assert task is not None
    assert not task.has_time
    assert ":" not in line
