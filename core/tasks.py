"""Reading to-do lines as dated tasks.

A task is still an ordinary Markdown checkbox — the file stays plain text and
opens fine anywhere. A trailing ``@`` stamp is what turns it into something
with a deadline:

    - [ ] تحویل سایت بامسما @1405/06/05 10:00
    - [x] تماس با مشتری @1405/06/03

The year decides the calendar: below 1600 it is Jalali, otherwise Gregorian,
so both ``@1405/06/05`` and ``@2026-08-27`` work.
"""
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from core.jalali import to_ascii_digits, to_gregorian

# Below this, a year is a Jalali one. Jalali years are ~621 behind, so the
# two ranges cannot overlap for any date a person would actually write.
_JALALI_YEAR_CEILING = 1600

# A trailing ↻ after the stamp marks a task that comes back every week:
#
#     - [ ] بررسی سبد خرید @1405/06/04 14:30 ↻
#
# It stays a plain character in a plain text file, like the stamp itself.
REPEAT_MARK = "↻"
REPEAT_PERIOD = timedelta(days=7)

_TODO_RE = re.compile(r"^(\s*)- \[( |x|X)\]\s+(.*)$")
_STAMP_RE = re.compile(
    r"\s*@(\d{3,4})[/-](\d{1,2})[/-](\d{1,2})"       # date
    r"(?:\s+(\d{1,2}):(\d{2}))?"                      # optional time
    r"(?:\s*" + REPEAT_MARK + r")?\s*$"               # optional repeat mark
)


@dataclass(frozen=True)
class Task:
    text: str
    done: bool
    due: datetime | None
    has_time: bool
    path: str = ""
    line_number: int = 0
    repeats: bool = False

    @property
    def overdue(self) -> bool:
        """Past its moment and still open.

        A repeating task is judged on its next occurrence, so last week's
        instance does not leave it permanently red.
        """
        due = self.next_due()
        return bool(due and not self.done and due < datetime.now())

    def next_due(self, now: datetime | None = None) -> datetime | None:
        """The moment this task is next wanted.

        For a one-off that is simply its stamp. For a repeating task it is
        the first weekly occurrence that has not already passed — except
        when none has passed yet, where the stamp itself still stands.
        """
        if self.due is None or not self.repeats:
            return self.due
        moment = now or datetime.now()
        if self.due >= moment:
            return self.due
        elapsed = moment - self.due
        skipped = elapsed // REPEAT_PERIOD + 1
        return self.due + skipped * REPEAT_PERIOD

    def key(self) -> str:
        """Stable identity across edits elsewhere in the file."""
        return f"{self.path}::{self.text}"


def group_of(task: Task, now: datetime) -> str:
    """Which bucket a task belongs in — shared by every task surface."""
    due = task.next_due(now)
    if due is None:
        return "بدون تاریخ"
    if due < now:
        return "عقب‌افتاده"
    if due.date() == now.date():
        return "امروز"
    if (due.date() - now.date()).days == 1:
        return "فردا"
    return "بعداً"


def parse_task(line: str) -> Task | None:
    """Read one line as a task, or None when it is not a checkbox line."""
    match = _TODO_RE.match(line)
    if match is None:
        return None
    body = match.group(3).strip()
    done = match.group(2) in "xX"

    stamp = _STAMP_RE.search(to_ascii_digits(body))
    if stamp is None:
        return Task(text=body, done=done, due=None, has_time=False)

    year, month, day = int(stamp.group(1)), int(stamp.group(2)), int(stamp.group(3))
    try:
        day_part = (
            to_gregorian(year, month, day)
            if year < _JALALI_YEAR_CEILING
            else date(year, month, day)
        )
    except ValueError:
        # A malformed stamp is left as part of the text rather than dropped,
        # so a typo never silently loses the deadline.
        return Task(text=body, done=done, due=None, has_time=False)

    has_time = stamp.group(4) is not None
    moment = time(int(stamp.group(4)), int(stamp.group(5))) if has_time else time(9, 0)
    # The visible text loses the stamp; the deadline is carried structurally.
    text = to_ascii_digits(body)[: stamp.start()].strip() or body
    return Task(
        text=text,
        done=done,
        due=datetime.combine(day_part, moment),
        has_time=has_time,
        repeats=REPEAT_MARK in body,
    )


def parse_document(text: str, path: str = "") -> list[Task]:
    """Every task in one note, with its line number."""
    found = []
    for index, line in enumerate(text.splitlines()):
        task = parse_task(line)
        if task is not None:
            found.append(
                Task(
                    text=task.text,
                    done=task.done,
                    due=task.due,
                    has_time=task.has_time,
                    path=path,
                    line_number=index,
                    repeats=task.repeats,
                )
            )
    return found


# Rewriting a stamp is a separate pattern from reading one: it has to see
# the line exactly as written — Persian digits, whichever separator, and the
# original calendar — so that pushing a date forward changes the date and
# nothing else about how the line looks.
_ANY_DIGIT = r"[0-9۰-۹]"
_STAMP_REWRITE_RE = re.compile(
    r"@(?P<year>" + _ANY_DIGIT + r"{3,4})"
    r"(?P<sep>[/-])(?P<month>" + _ANY_DIGIT + r"{1,2})"
    r"[/-](?P<day>" + _ANY_DIGIT + r"{1,2})"
)


# The whole stamp, including its time and repeat mark — what the editor
# draws its capsule around.
_STAMP_SPAN_RE = re.compile(
    r"@" + _ANY_DIGIT + r"{3,4}[/-]" + _ANY_DIGIT + r"{1,2}[/-]"
    + _ANY_DIGIT + r"{1,2}"
    r"(?:\s+" + _ANY_DIGIT + r"{1,2}:" + _ANY_DIGIT + r"{2})?"
    r"(?:\s*" + REPEAT_MARK + r")?"
)


def stamp_span(line: str) -> tuple[int, int] | None:
    """Where the date stamp sits in a task line, as (start, end).

    Only checkbox lines count: an ``@`` in ordinary prose is not a deadline
    and must not be drawn as one.
    """
    if _TODO_RE.match(line) is None:
        return None
    found = _STAMP_SPAN_RE.search(line)
    return (found.start(), found.end()) if found else None


def shift_stamp(line: str, days: int) -> str | None:
    """Move a task line's date forward, or None when there is nothing to move.

    The calendar (Jalali or Gregorian), the separator, the time and the digit
    script are all preserved — only the day changes.
    """
    match = _STAMP_REWRITE_RE.search(line)
    if match is None:
        return None
    raw_year = match.group("year")
    year = int(to_ascii_digits(raw_year))
    month = int(to_ascii_digits(match.group("month")))
    day = int(to_ascii_digits(match.group("day")))
    jalali = year < _JALALI_YEAR_CEILING
    try:
        moved = (
            to_gregorian(year, month, day) if jalali else date(year, month, day)
        ) + timedelta(days=days)
    except ValueError:
        return None

    if jalali:
        from core.jalali import from_gregorian

        parts = from_gregorian(moved)
    else:
        parts = (moved.year, moved.month, moved.day)
    separator = match.group("sep")
    stamp = "@%04d%s%02d%s%02d" % (parts[0], separator, parts[1], separator, parts[2])
    # Persian digits in the year are what the stamp was written with; match it.
    if raw_year != to_ascii_digits(raw_year):
        from core.jalali import to_persian_digits

        stamp = to_persian_digits(stamp)
    return line[: match.start()] + stamp + line[match.end():]


def set_stamp(line: str, when: date, at: time | None = None) -> str:
    """Give a task line this deadline, replacing whatever it had.

    Unlike `add_stamp`, this is what the picker calls: the user chose the
    date on purpose, so an existing one is meant to be overwritten. A weekly
    repeat mark survives — changing when a task is due does not stop it
    repeating.
    """
    from core.jalali import from_gregorian, to_persian_digits

    if _TODO_RE.match(line) is None:
        return line
    year, month, day = from_gregorian(when)
    stamp = "@%04d/%02d/%02d" % (year, month, day)
    if at is not None:
        stamp += " %02d:%02d" % (at.hour, at.minute)
    stamp = to_persian_digits(stamp)

    span = stamp_span(line)
    if span is not None:
        if REPEAT_MARK in line[span[0]:span[1]]:
            stamp += " " + REPEAT_MARK
        return line[: span[0]] + stamp + line[span[1]:]
    stripped = line.rstrip()
    return stripped + " " + stamp + line[len(stripped):]


def add_stamp(line: str, when: date | None = None) -> str:
    """Give a checkbox line a date stamp, in Jalali with Persian digits.

    A line that is not a task, or that already carries a stamp, comes back
    unchanged — re-stamping would quietly move a deadline the user set.
    """
    from core.jalali import from_gregorian, to_persian_digits

    if _TODO_RE.match(line) is None:
        return line
    if _STAMP_REWRITE_RE.search(line) is not None:
        return line
    year, month, day = from_gregorian(when or date.today())
    stamp = to_persian_digits("@%04d/%02d/%02d" % (year, month, day))
    stripped = line.rstrip()
    return stripped + " " + stamp + line[len(stripped):]


def toggle_repeat(line: str) -> str:
    """Add or remove the weekly repeat mark on a task line.

    Only a dated task can repeat — without a stamp there is nothing for a
    week to be counted from — so an undated line comes back unchanged.
    """
    if _STAMP_REWRITE_RE.search(line) is None:
        return line
    stripped = line.rstrip()
    trailing = line[len(stripped):]
    if stripped.endswith(REPEAT_MARK):
        return stripped[: -len(REPEAT_MARK)].rstrip() + trailing
    return stripped + " " + REPEAT_MARK + trailing


def due_within(tasks: list[Task], now: datetime, ahead_minutes: int = 0) -> list[Task]:
    """Unfinished tasks whose moment has arrived (or is about to)."""
    limit = now + timedelta(minutes=ahead_minutes)
    return [t for t in tasks if t.due and not t.done and t.due <= limit]


def today_progress(tasks: list[Task], now: datetime) -> tuple[int, int]:
    """How much of today's dated work is done, as (done, total).

    A finished task is counted on the day it was actually due, not on the
    occurrence a repeat would roll it forward to — otherwise ticking one off
    would move it out of today and the bar would go backwards.
    """
    done = total = 0
    for task in tasks:
        due = task.due if task.done else task.next_due(now)
        if due is None or due.date() != now.date():
            continue
        total += 1
        done += bool(task.done)
    return done, total


def sort_for_today(tasks: list[Task], now: datetime) -> list[Task]:
    """Overdue first, then today's by time, then the rest, then undated."""
    def rank(task: Task):
        due = task.next_due(now)
        if due is None:
            return (3, datetime.max)
        if due < now:
            return (0, due)
        if due.date() == now.date():
            return (1, due)
        return (2, due)

    return sorted([t for t in tasks if not t.done], key=rank)
