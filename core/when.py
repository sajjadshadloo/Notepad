"""Reading a day out of a task as it is typed: «تماس با حمید فردا».

The design's quick-add fields understand امروز, فردا, پس‌فردا, «هفته‌ی بعد»,
a weekday name (the next one to come — today's own name means next week),
and «۱۲ مهر» for any Jalali month. The words that named the day are taken
out of the task text; everything else is left exactly as typed.
"""
import re
from dataclasses import dataclass
from datetime import date, timedelta

from core.jalali import MONTHS, WEEKDAYS, from_gregorian, to_ascii_digits, to_gregorian, to_persian_digits

ZWNJ = "‌"

# Saturday-first names, the order a Persian week is read in.
_WEEK = ("شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه")
# Python's weekday(): Monday is 0.
_PY_WEEKDAY = {"شنبه": 5, "یکشنبه": 6, "دوشنبه": 0, "سه‌شنبه": 1,
               "چهارشنبه": 2, "پنجشنبه": 3, "جمعه": 4}


@dataclass(frozen=True)
class When:
    day: date
    text: str


def _spaced(word: str) -> str:
    """A word that may be written with a ZWNJ, a space, or nothing between parts."""
    return word.replace(ZWNJ, "[‌ ]?")


_B, _E = r"(^|\s)", r"(?=\s|$)"
_WEEKDAY_ALTERNATION = "|".join(
    sorted((_spaced(name) for name in _WEEK), key=len, reverse=True)
)
_MONTH_ALTERNATION = "|".join(_spaced(name) for name in MONTHS)


def _next_weekday(name: str, today: date) -> date:
    target = _PY_WEEKDAY[name]
    ahead = (target - today.weekday()) % 7 or 7
    return today + timedelta(days=ahead)


def _month_day(match: re.Match, today: date) -> date | None:
    number = int(to_ascii_digits(match.group("n")))
    month_name = re.sub(r"[‌ ]", "", match.group("m"))
    month = next(i for i, m in enumerate(MONTHS, 1) if m.replace(ZWNJ, "") == month_name)
    year, current_month, current_day = from_gregorian(today)
    # A date already gone this year means next year's.
    if (month, number) < (current_month, current_day):
        year += 1
    try:
        return to_gregorian(year, month, number)
    except (ValueError, IndexError):
        return None


_PATTERNS = (
    (_B + r"(?P<w>پس" + "[‌ ]?" + r"فردا)" + _E, lambda m, t: t + timedelta(days=2)),
    (_B + r"(?P<w>فردا)" + _E, lambda m, t: t + timedelta(days=1)),
    (_B + r"(?P<w>امروز)" + _E, lambda m, t: t),
    (_B + r"(?P<w>هفته(?:" + ZWNJ + r"ی|ی|ٔ|" + ZWNJ + r"ٔ)?\s*(?:بعد|آینده))" + _E,
     lambda m, t: t + timedelta(days=7)),
    (_B + r"(?P<w>(?P<n>[0-9۰-۹]{1,2})\s*(?P<m>" + _MONTH_ALTERNATION + r"))" + _E, _month_day),
    (_B + r"(?P<w>" + _WEEKDAY_ALTERNATION + r")" + _E,
     lambda m, t: _next_weekday(
         next(n for n in _WEEK if re.fullmatch(_spaced(n), m.group("w"))), t)),
)


def parse_when(raw: str, today: date | None = None) -> When | None:
    """The day a task names, and the task without those words — or None."""
    today = today or date.today()
    for pattern, resolve in _PATTERNS:
        match = re.search(pattern, raw)
        if not match:
            continue
        day = resolve(match, today)
        if day is None:
            return None
        start, end = match.span("w")
        text = re.sub(r"\s+", " ", raw[:start] + raw[end:]).strip()
        return When(day, text or raw.strip())
    return None


def day_label(day: date | None, today: date | None = None) -> str:
    """امروز / فردا / دیروز, otherwise «۱۲ مهر»."""
    if day is None:
        return ""
    today = today or date.today()
    delta = (day - today).days
    if delta == 0:
        return "امروز"
    if delta == 1:
        return "فردا"
    if delta == -1:
        return "دیروز"
    _, month, number = from_gregorian(day)
    return to_persian_digits(str(number)) + " " + MONTHS[month - 1]


def weekday_name(day: date) -> str:
    return WEEKDAYS[day.weekday()]


def long_label(day: date) -> str:
    """«شنبه ۴ مهر» — the weekday and the day of the month."""
    _, month, number = from_gregorian(day)
    return weekday_name(day) + " " + to_persian_digits(str(number)) + " " + MONTHS[month - 1]


def parse_preview(raw: str, today: date | None = None) -> tuple[str, str] | None:
    """The chip under a quick-add field: («فردا · شنبه ۴ مهر», «کار: «…»»)."""
    today = today or date.today()
    found = parse_when(raw, today) if raw.strip() else None
    if found is None:
        return None
    return (day_label(found.day, today) + " · " + long_label(found.day),
            "کار: «" + found.text + "»")
