from datetime import date, timedelta

from core.jalali import column_of, from_gregorian, is_leap, month_days, month_length, shift_month
from ui.calendar_panel import FRIDAY_COLUMN, WEEKDAY_INITIALS, CalendarPanel


def test_week_starts_on_saturday():
    """A Persian calendar's first column is Saturday, not Monday."""
    assert WEEKDAY_INITIALS[0] == "ش"
    saturday = date(2026, 8, 22)
    assert saturday.weekday() == 5
    assert column_of(saturday) == 0
    assert column_of(saturday + timedelta(days=6)) == FRIDAY_COLUMN


def test_month_lengths_follow_the_calendar():
    assert [month_length(1405, m) for m in range(1, 7)] == [31] * 6
    assert [month_length(1405, m) for m in range(7, 12)] == [30] * 5
    assert month_length(1403, 12) == 30  # leap
    assert month_length(1405, 12) == 29


def test_leap_years_match_the_conversion():
    assert is_leap(1403) and not is_leap(1404) and not is_leap(1405)


def test_month_days_are_contiguous_and_in_one_month():
    days = month_days(1405, 6)
    assert len(days) == 31
    assert all(from_gregorian(d)[1] == 6 for d in days)
    assert all((b - a).days == 1 for a, b in zip(days, days[1:]))


def test_shift_month_rolls_the_year():
    assert shift_month(1405, 12, 1) == (1406, 1)
    assert shift_month(1405, 1, -1) == (1404, 12)
    assert shift_month(1405, 6, 12) == (1406, 6)


def test_panel_shows_a_cell_per_day_and_marks_the_ones_it_is_told(tmp_path, qapp):
    """4.2: the grid no longer reads the folder — its owner says which days
    carry work, because there is no longer a file per day to look for."""
    written = date.today()
    panel = CalendarPanel(str(tmp_path))
    panel.set_marked_days({written})

    jy, jm, _ = from_gregorian(written)
    assert len(panel._cells) == month_length(jy, jm)
    marked = [c for c in panel._cells if c.property("written")]
    assert len(marked) == 1
    assert sum(1 for c in panel._cells if c.property("today")) == 1


def test_the_chosen_day_is_marked_apart_from_today(tmp_path, qapp):
    panel = CalendarPanel(str(tmp_path))
    panel.choose(date.today() + timedelta(days=1))
    chosen = [c for c in panel._cells if c.property("chosen")]
    assert len(chosen) == 1


def test_clicking_a_day_reports_that_date(tmp_path, qapp):
    panel = CalendarPanel(str(tmp_path))
    seen = []
    panel.day_activated.connect(seen.append)
    panel._cells[0].click()
    jy, jm, _ = from_gregorian(date.today())
    assert seen == [month_days(jy, jm)[0]]


def test_navigating_months_keeps_the_grid_valid(tmp_path, qapp):
    panel = CalendarPanel(str(tmp_path))
    start = (panel._year, panel._month)
    panel.shift(1)
    assert (panel._year, panel._month) == shift_month(*start, 1)
    assert len(panel._cells) == month_length(panel._year, panel._month)
    panel.shift(-1)
    assert (panel._year, panel._month) == start
