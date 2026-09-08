"""One note per day, kept in a Daily folder inside the notes tree.

The file name uses ASCII digits (``1405-06-04.md``) so it sorts correctly in
Explorer and in the sidebar; the heading inside uses Persian ones, which is
what you actually read.
"""
from datetime import date
from pathlib import Path

from core.jalali import format_long, from_gregorian, to_gregorian

FOLDER = "Daily"

NEWLINE = chr(10)
BLANK_LINE = NEWLINE * 2


def path_for(root: str | Path, day: date) -> Path:
    jy, jm, jd = from_gregorian(day)
    return Path(root) / FOLDER / f"{jy:04d}-{jm:02d}-{jd:02d}.md"


def starter_text(day: date) -> str:
    """What a brand-new daily note opens with."""
    return f"# {format_long(day)}\n\n- [ ] "


def is_daily_note(root: str | Path, path: str | Path) -> bool:
    try:
        relative = Path(path).resolve().relative_to(Path(root).resolve())
    except (ValueError, OSError):
        return False
    return relative.parent.name == FOLDER and relative.suffix.lower() == ".md"


def is_untouched(text: str, day: date) -> bool:
    """True when a daily note holds nothing but what we put there.

    The test is exact rather than a size or a heuristic: this decides whether
    a file may be deleted, so anything the user actually typed has to fail it.
    """
    return text.strip() in ("", starter_text(day).strip())


def prune_empty(root: str | Path) -> list[Path]:
    """Delete day notes that were opened and never written in.

    Up to 4.0 a note was created the moment a day was clicked, so browsing
    the calendar left one empty file per visit, and they collected in the
    sidebar forever. Creation is lazy now; this clears what the old
    behaviour left behind. Returns what it removed.
    """
    removed: list[Path] = []
    folder = Path(root) / FOLDER
    if not folder.exists():
        return removed
    for path in sorted(folder.glob("*.md")):
        try:
            year, month, day_number = (int(part) for part in path.stem.split("-"))
            day = to_gregorian(year, month, day_number)
        except (ValueError, TypeError):
            continue
        try:
            if not is_untouched(path.read_text(encoding="utf-8"), day):
                continue
            path.unlink()
        except OSError:
            continue
        removed.append(path)
    return removed


def existing_days(root: str | Path) -> set[str]:
    """Stems of the daily notes already written, e.g. {'1405-06-04'}."""
    folder = Path(root) / FOLDER
    if not folder.exists():
        return set()
    return {p.stem for p in folder.glob("*.md")}

def add_task(root: str | Path, day: date, text: str) -> Path:
    """Write one dated task into a day's note, creating the note if needed.

    This is what makes the Daily folder worth having. Until 4.1 a day note
    was created by *visiting* a day, so the folder filled with empty files
    and nothing ever put work in them. Now a file appears exactly when a task
    is put on that day, and the calendar reads them back.
    """
    from core.file_service import read_text_file, write_text_file_atomic
    from core.tasks import parse_task, set_stamp

    path = path_for(root, day)
    line = set_stamp("- [ ] " + text.strip(), day)

    existing = ""
    encoding = "utf-8"
    if path.exists():
        loaded = read_text_file(path)
        existing, encoding = loaded.text, loaded.encoding
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = starter_text(day)

    body = existing.rstrip()
    # starter_text ends with an empty checkbox, ready to type into. Filling it
    # is the point; leaving it above the new line would be a blank task.
    if body.endswith("- [ ]"):
        body = body[: -len("- [ ]")].rstrip()
    # Tasks stack directly under one another; only prose gets a blank
    # line between it and the first task.
    if not body:
        joined = line
    else:
        last = body.splitlines()[-1]
        gap = NEWLINE if parse_task(last) is not None else BLANK_LINE
        joined = body + gap + line
    write_text_file_atomic(path, joined + NEWLINE, encoding)
    return path
