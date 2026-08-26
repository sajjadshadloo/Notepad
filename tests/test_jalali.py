from datetime import date, timedelta

import pytest

from core.jalali import (
    format_date,
    format_long,
    from_gregorian,
    to_ascii_digits,
    to_gregorian,
    to_persian_digits,
)


@pytest.mark.parametrize(
    "gregorian,jalali",
    [
        (date(1979, 2, 11), (1357, 11, 22)),   # the revolution, a fixed anchor
        (date(2000, 1, 1), (1378, 10, 11)),
        (date(2024, 3, 20), (1403, 1, 1)),     # Nowruz 1403
        (date(2026, 3, 21), (1405, 1, 1)),     # Nowruz 1405
        (date(2026, 8, 25), (1405, 6, 3)),
        (date(2025, 3, 20), (1403, 12, 30)),   # last day of a leap Jalali year
    ],
)
def test_known_dates(gregorian, jalali):
    assert from_gregorian(gregorian) == jalali
    assert to_gregorian(*jalali) == gregorian


def test_round_trip_over_forty_years():
    """Off-by-one errors in this arithmetic hide in single days, so walk them."""
    day, end = date(1995, 1, 1), date(2035, 12, 31)
    while day <= end:
        assert to_gregorian(*from_gregorian(day)) == day, day
        day += timedelta(days=1)


def test_nowruz_always_lands_on_the_first_of_farvardin():
    for year in range(1390, 1420):
        first = to_gregorian(year, 1, 1)
        assert from_gregorian(first) == (year, 1, 1)
        assert from_gregorian(first - timedelta(days=1))[1] == 12


def test_invalid_dates_are_rejected():
    for bad in [(1405, 13, 1), (1405, 0, 1), (1405, 1, 32), (1405, 1, 0)]:
        with pytest.raises(ValueError):
            to_gregorian(*bad)


def test_digit_helpers():
    assert to_persian_digits("1405/06/05") == "۱۴۰۵/۰۶/۰۵"
    assert to_ascii_digits("۱۴۰۵/۰۶/۰۵") == "1405/06/05"
    assert to_ascii_digits("١٤٠٥") == "1405"  # Arabic-Indic too


def test_formatting():
    assert format_date(date(2026, 8, 25)) == "۱۴۰۵/۰۶/۰۳"
    assert format_date(date(2026, 8, 25), persian_digits=False) == "1405/06/03"
    assert format_long(date(2026, 8, 25)) == "۳ شهریور ۱۴۰۵"
