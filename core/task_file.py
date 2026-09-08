"""One file holds every dated task.

4.1 gave each day its own note in a Daily folder. That fragmented the work —
a folder filling with files named after dates, each carrying a date heading
nobody wrote — and it is not how the work was being kept by hand: there was
one file, with the tasks in it.

So there is one file. A task carries its day as a stamp, and the calendar
filters rather than owning anything:

    - [ ] فاکتور مروارید @۱۴۰۵/۰۶/۱۷
    - [x] تماس با حمید   @۱۴۰۵/۰۶/۱۷
    - [ ] تمدید هاست     @۱۴۰۵/۰۶/۲۰
"""
import logging
from datetime import date
from pathlib import Path

from core.file_service import read_text_file, write_text_file_atomic
from core.tasks import parse_task, set_stamp, stamp_span

log = logging.getLogger(__name__)

FILE_NAME = "کارها.md"
LEGACY_FOLDER = "Daily"
NEWLINE = chr(10)


def path_for(root: str | Path) -> Path:
    return Path(root) / FILE_NAME


def add_task(root: str | Path, day: date, text: str) -> Path:
    """Append one dated task, creating the file on first use."""
    path = path_for(root)
    line = set_stamp("- [ ] " + text.strip(), day)

    existing, encoding = "", "utf-8"
    if path.exists():
        loaded = read_text_file(path)
        existing, encoding = loaded.text, loaded.encoding
    else:
        path.parent.mkdir(parents=True, exist_ok=True)

    body = existing.rstrip()
    joined = (body + NEWLINE + line) if body else line
    write_text_file_atomic(path, joined + NEWLINE, encoding)
    return path


def _day_of(stem: str) -> date | None:
    """The Gregorian day a legacy file name stands for, or None."""
    from core.jalali import to_gregorian

    try:
        year, month, number = (int(part) for part in stem.split("-"))
        return to_gregorian(year, month, number)
    except (ValueError, TypeError):
        return None


def import_daily_notes(root: str | Path) -> int:
    """Fold the tasks out of a 4.1 Daily folder into the one file.

    A day file is deleted only when everything in it was taken — its own
    generated heading and the tasks. One that also holds prose is left
    where it is, because that prose is a note and losing it would be worse
    than leaving a stray file behind. Returns how many tasks moved.
    """
    folder = Path(root) / LEGACY_FOLDER
    if not folder.exists():
        return 0

    moved = 0
    for path in sorted(folder.glob("*.md")):
        day = _day_of(path.stem)
        if day is None:
            continue
        try:
            text = read_text_file(path).text
        except Exception:
            continue

        tasks, others = [], []
        for raw in text.splitlines():
            line = raw.rstrip()
            if parse_task(line) is not None:
                tasks.append(line)
            elif line.strip() and not line.lstrip().startswith("#"):
                others.append(line)

        for line in tasks:
            # A day file's tasks were dated by the file they sat in, so any
            # without a stamp of their own take that day now.
            _append_line(root, line if stamp_span(line) else set_stamp(line, day))
            moved += 1

        if not others:
            try:
                path.unlink()
            except OSError:
                log.warning("Could not remove %s", path, exc_info=True)

    if moved and not any(folder.iterdir()):
        try:
            folder.rmdir()
        except OSError:
            pass
    return moved


def _append_line(root: str | Path, line: str):
    """Add one already-formed task line to the file."""
    path = path_for(root)
    existing, encoding = "", "utf-8"
    if path.exists():
        loaded = read_text_file(path)
        existing, encoding = loaded.text, loaded.encoding
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
    body = existing.rstrip()
    joined = (body + NEWLINE + line) if body else line
    write_text_file_atomic(path, joined + NEWLINE, encoding)
