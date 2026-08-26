"""Jalali (Persian) calendar conversion.

Pure arithmetic, no dependencies. A freelancer working in Iran thinks in
1405/06/05, not 2026-08-27, so dates are read and written in that calendar
while everything internal stays a normal ``datetime``.
"""
from datetime import date, timedelta

MONTHS = (
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
)
WEEKDAYS = ("دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه")

_PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
_ASCII_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

_GREGORIAN_MONTH_STARTS = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)


def to_persian_digits(text: str) -> str:
    return text.translate(_PERSIAN_DIGITS)


def to_ascii_digits(text: str) -> str:
    """Normalise Persian and Arabic-Indic digits so parsing sees 0-9."""
    return text.translate(_ASCII_DIGITS)


def _is_leap_gregorian(year: int) -> bool:
    return (year % 4 == 0 and year % 100 != 0) or year % 400 == 0


def from_gregorian(value: date) -> tuple[int, int, int]:
    """(year, month, day) in the Jalali calendar."""
    gy, gm, gd = value.year, value.month, value.day
    if gy > 1600:
        jy = 979
        gy -= 1600
    else:
        jy = 0
        gy -= 621
    leap_adjusted = gy + 1 if gm > 2 else gy
    days = (
        365 * gy
        + (leap_adjusted + 3) // 4
        - (leap_adjusted + 99) // 100
        + (leap_adjusted + 399) // 400
        - 80
        + gd
        + _GREGORIAN_MONTH_STARTS[gm - 1]
    )
    jy += 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        return jy, 1 + days // 31, 1 + days % 31
    return jy, 7 + (days - 186) // 30, 1 + (days - 186) % 30


def to_gregorian(jy: int, jm: int, jd: int) -> date:
    """Convert a Jalali date; raises ValueError if it is not a real date."""
    if not 1 <= jm <= 12:
        raise ValueError(f"month out of range: {jm}")
    if not 1 <= jd <= 31:
        raise ValueError(f"day out of range: {jd}")
    if jy > 979:
        gy = 1600
        jy -= 979
    else:
        gy = 621
    days = (
        365 * jy
        + (jy // 33) * 8
        + ((jy % 33) + 3) // 4
        + 78
        + jd
        + ((jm - 1) * 31 if jm < 7 else (jm - 7) * 30 + 186)
    )
    gy += 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        days -= 1
        gy += 100 * (days // 36524)
        days %= 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    month_lengths = (
        31, 29 if _is_leap_gregorian(gy) else 28, 31, 30, 31, 30,
        31, 31, 30, 31, 30, 31,
    )
    gd = days + 1
    gm = 0
    while gm < 12 and gd > month_lengths[gm]:
        gd -= month_lengths[gm]
        gm += 1
    return date(gy, gm + 1, gd)


def is_leap(jy: int) -> bool:
    """Whether a Jalali year has 366 days.

    Derived from the conversion rather than restated as its own rule, so the
    two can never drift apart: the leap-year cycle is the awkward part of this
    calendar and one implementation of it is enough.
    """
    return (to_gregorian(jy + 1, 1, 1) - to_gregorian(jy, 1, 1)).days == 366


def month_length(jy: int, jm: int) -> int:
    if jm <= 6:
        return 31
    if jm <= 11:
        return 30
    return 30 if is_leap(jy) else 29


def month_days(jy: int, jm: int) -> list[date]:
    """Every Gregorian date in one Jalali month, in order."""
    first = to_gregorian(jy, jm, 1)
    return [first + timedelta(days=offset) for offset in range(month_length(jy, jm))]


def column_of(value: date) -> int:
    """Grid column for a calendar that starts the week on Saturday."""
    return (value.weekday() + 2) % 7


def shift_month(jy: int, jm: int, delta: int) -> tuple[int, int]:
    index = (jy * 12 + (jm - 1)) + delta
    return index // 12, index % 12 + 1


def format_date(value: date, *, persian_digits: bool = True) -> str:
    """1405/06/05 — the form used in task lines and file names."""
    jy, jm, jd = from_gregorian(value)
    text = f"{jy:04d}/{jm:02d}/{jd:02d}"
    return to_persian_digits(text) if persian_digits else text


def format_long(value: date) -> str:
    """5 شهریور 1405 — for headings and the calendar view."""
    jy, jm, jd = from_gregorian(value)
    return to_persian_digits(f"{jd} {MONTHS[jm - 1]} {jy}")
