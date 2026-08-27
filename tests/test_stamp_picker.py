"""Scheduling a task from the @ button.

The button used to stamp today's date and say nothing about how to add a
time — you had to know you could type one after it. These cover the two
halves: what the picker hands back, and what that does to the line.
"""
from datetime import date, time

import pytest

from core.tasks import parse_task, set_stamp


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


def test_it_opens_with_no_time_chosen(picker):
    """"Later today" is the common case; an hour is opt-in."""
    assert picker._time is None


def test_it_opens_on_today_when_the_line_has_no_date(picker):
    assert picker._date == date.today()


def test_it_opens_on_the_date_the_line_already_has(tmp_path, qapp):
    from ui.stamp_picker import StampPicker

    picker = StampPicker(str(tmp_path), date(2026, 1, 15))
    assert picker._date == date(2026, 1, 15)
    picker.deleteLater()


def test_picking_a_preset_hour_selects_exactly_one_chip(picker):
    picker._pick_hour(16, 0)
    checked = [b.text() for values, b in picker._hour_buttons if b.isChecked()]
    assert checked == ["16:00"]
    assert picker._time == time(16, 0)


def test_a_custom_time_clears_the_presets(picker):
    from PyQt6.QtCore import QTime

    picker._pick_hour(16, 0)
    picker.time_edit.setTime(QTime(7, 45))
    assert picker._time == time(7, 45)
    assert not any(b.isChecked() for _v, b in picker._hour_buttons)


def test_confirming_without_a_time_reports_none(picker):
    seen = []
    picker.picked.connect(lambda day, at: seen.append((day, at)))
    picker._accept_without_time()
    assert seen == [(picker._date, None)]


def test_confirming_with_no_hour_chosen_falls_back_to_nine(picker):
    """The button says "ثبت", so it has to mean something."""
    seen = []
    picker.picked.connect(lambda day, at: seen.append((day, at)))
    picker._accept_with_time()
    assert seen == [(picker._date, time(9, 0))]


def test_every_preset_hour_fits_its_chip(picker):
    """Five chips did not fit the popup and Qt elided 09:00 to nonsense."""
    from PyQt6.QtGui import QFontMetrics

    for _values, button in picker._hour_buttons:
        needed = QFontMetrics(button.font()).horizontalAdvance(button.text())
        assert button.sizeHint().width() >= needed
