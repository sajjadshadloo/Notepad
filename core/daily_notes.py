"""One note per day, kept in a Daily folder inside the notes tree.

The file name uses ASCII digits (``1405-06-04.md``) so it sorts correctly in
Explorer and in the sidebar; the heading inside uses Persian ones, which is
what you actually read.
"""
from datetime import date
from pathlib import Path

from core.jalali import format_long, from_gregorian

FOLDER = "Daily"


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


def existing_days(root: str | Path) -> set[str]:
    """Stems of the daily notes already written, e.g. {'1405-06-04'}."""
    folder = Path(root) / FOLDER
    if not folder.exists():
        return set()
    return {p.stem for p in folder.glob("*.md")}
