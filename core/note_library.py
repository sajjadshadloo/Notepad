"""Reading the notes folder as a set of cards, grouped by subfolder.

The folder *is* the category. Nothing is stored anywhere else: make a folder
in Explorer and it becomes a tab, move a file and it changes category. A
tagging scheme would have to be kept up by hand, and the 3.0 experiment with
one showed that in practice it never is.
"""
import logging
from dataclasses import dataclass
from pathlib import Path

from core.file_service import read_text_file
from core.tasks import parse_task, stamp_span

log = logging.getLogger(__name__)

NOTE_EXTENSIONS = (".txt", ".md", ".markdown")

# A card shows a handful of lines, so there is no reason to look at more of
# a long note than that. 39 KB notes exist in real folders.
PREVIEW_CHARS = 2000
PREVIEW_LINES = 3
PREVIEW_TASKS = 4

ROOT_LABEL = "عمومی"

# Folder names on disk are English so agents and scripts can find them; the
# app shows them in Persian. A folder not listed here shows as it is named.
FOLDER_LABELS = {
    "projects": "پروژه‌ها",
    "ideas": "ایده‌ها",
    "inbox": "ورودی‌ها",
    "me": "من",
    "private": "خصوصی",
    "archive": "بایگانی",
    "daily": "روزانه",
    "sites": "سایت‌ها",
    "personal": "شخصی",
}


def display_name(folder: str) -> str:
    """How a folder (or the root, as "") is labelled on screen."""
    if not folder:
        return ROOT_LABEL
    return FOLDER_LABELS.get(folder.casefold(), folder)


@dataclass(frozen=True)
class CardTask:
    done: bool
    text: str


@dataclass(frozen=True)
class NoteCard:
    path: str
    title: str
    folder: str
    modified: float
    lines: tuple[str, ...] = ()
    tasks: tuple[CardTask, ...] = ()
    open_tasks: int = 0

    @property
    def category(self) -> str:
        """The tab this card belongs under."""
        return display_name(self.folder)


def _strip_stamp(line: str) -> str:
    """A card shows what the task *is*; the date is drawn by the calendar."""
    span = stamp_span(line)
    return (line[: span[0]] + line[span[1]:]).strip() if span else line.strip()


def summarise(text: str, path: Path, folder: str, modified: float) -> NoteCard:
    """Turn one note's text into the few lines a card can show."""
    head = text[:PREVIEW_CHARS]
    title = path.stem
    lines: list[str] = []
    tasks: list[CardTask] = []

    for raw in head.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#") and title == path.stem and not lines and not tasks:
            # The first heading names the note better than its filename does.
            title = line.lstrip("#").strip() or title
            continue
        task = parse_task(raw)
        if task is not None:
            if len(tasks) < PREVIEW_TASKS:
                tasks.append(CardTask(done=task.done, text=_strip_stamp(task.text)))
            continue
        if len(lines) < PREVIEW_LINES:
            lines.append(line)

    # Counted over the whole note, not just the preview: the number on the
    # card would be a lie otherwise.
    open_tasks = sum(
        1
        for raw in text.splitlines()
        if (parsed := parse_task(raw)) is not None and not parsed.done
    )
    return NoteCard(
        path=str(path),
        title=title,
        folder=folder,
        modified=modified,
        lines=tuple(lines),
        tasks=tuple(tasks),
        open_tasks=open_tasks,
    )


def load_library(root: str | Path, cancelled=lambda: False) -> list[NoteCard]:
    """Every note under `root`, newest first.

    The tasks file is left out: it has the whole right-hand rail to itself,
    and a card repeating what is already on screen beside it is noise.
    """
    from core.task_file import FILE_NAME as TASKS_FILE

    root_path = Path(root)
    cards: list[NoteCard] = []
    if not root_path.exists():
        return cards
    for path in root_path.rglob("*"):
        if cancelled():
            return []
        if not path.is_file() or path.suffix.lower() not in NOTE_EXTENSIONS:
            continue
        # CLAUDE.md only points Claude Code at AGENTS.md; it is not a note.
        if path.parent == root_path and path.name in (TASKS_FILE, "CLAUDE.md"):
            continue
        try:
            loaded = read_text_file(path)
            modified = path.stat().st_mtime
        except Exception:
            continue
        relative = path.parent.relative_to(root_path)
        folder = "" if relative == Path(".") else relative.parts[0]
        cards.append(summarise(loaded.text, path, folder, modified))
    cards.sort(key=lambda card: card.modified, reverse=True)
    return cards


def edited_label(modified: float, now: float | None = None) -> str:
    """«۱۰ دقیقه پیش», «۲ ساعت پیش», «دیروز» — how long ago a note changed."""
    import time
    from datetime import date as _date, datetime as _datetime

    from core.jalali import MONTHS, from_gregorian, to_persian_digits

    now = time.time() if now is None else now
    seconds = max(0.0, now - modified)
    then = _datetime.fromtimestamp(modified)
    today = _datetime.fromtimestamp(now).date()
    days = (today - then.date()).days
    if seconds < 60:
        return "همین حالا"
    if seconds < 3600:
        return to_persian_digits(str(int(seconds // 60))) + " دقیقه پیش"
    if days == 0:
        return to_persian_digits(str(int(seconds // 3600))) + " ساعت پیش"
    if days == 1:
        return "دیروز"
    if days < 7:
        return to_persian_digits(str(days)) + " روز پیش"
    if days < 14:
        return "هفته‌ی پیش"
    _, month, day = from_gregorian(_date(then.year, then.month, then.day))
    return to_persian_digits(str(day)) + " " + MONTHS[month - 1]


def categories(cards: list[NoteCard]) -> list[str]:
    """Tab labels, in the order they should appear.

    Root notes lead — they are the ones without a home yet — and the rest
    follow alphabetically so the tabs do not reshuffle as files are touched.
    """
    names = {card.category for card in cards}
    ordered = sorted(name for name in names if name != ROOT_LABEL)
    return ([ROOT_LABEL] if ROOT_LABEL in names else []) + ordered


def in_category(cards: list[NoteCard], category: str) -> list[NoteCard]:
    """Cards for one tab; an empty category name means all of them."""
    if not category:
        return list(cards)
    return [card for card in cards if card.category == category]
