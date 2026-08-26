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
from datetime import date, datetime, time

from core.jalali import to_ascii_digits, to_gregorian

# Below this, a year is a Jalali one. Jalali years are ~621 behind, so the
# two ranges cannot overlap for any date a person would actually write.
_JALALI_YEAR_CEILING = 1600

_TODO_RE = re.compile(r"^(\s*)- \[( |x|X)\]\s+(.*)$")
_STAMP_RE = re.compile(
    r"\s*@(\d{3,4})[/-](\d{1,2})[/-](\d{1,2})"       # date
    r"(?:\s+(\d{1,2}):(\d{2}))?\s*$"                  # optional time
)


@dataclass(frozen=True)
class Task:
    text: str
    done: bool
    due: datetime | None
    has_time: bool
    path: str = ""
    line_number: int = 0

    @property
    def overdue(self) -> bool:
        return bool(self.due and not self.done and self.due < datetime.now())

    def key(self) -> str:
        """Stable identity across edits elsewhere in the file."""
        return f"{self.path}::{self.text}"


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
                )
            )
    return found


def due_within(tasks: list[Task], now: datetime, ahead_minutes: int = 0) -> list[Task]:
    """Unfinished tasks whose moment has arrived (or is about to)."""
    from datetime import timedelta

    limit = now + timedelta(minutes=ahead_minutes)
    return [t for t in tasks if t.due and not t.done and t.due <= limit]


def sort_for_today(tasks: list[Task], now: datetime) -> list[Task]:
    """Overdue first, then today's by time, then the rest, then undated."""
    def rank(task: Task):
        if task.due is None:
            return (3, datetime.max)
        if task.due < now:
            return (0, task.due)
        if task.due.date() == now.date():
            return (1, task.due)
        return (2, task.due)

    return sorted([t for t in tasks if not t.done], key=rank)
