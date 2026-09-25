"""Links between notes: «[[اطلاعات هاست]]», the way Obsidian writes them.

A link names a note by its file name without the extension, or by its path
inside the notes folder («[[Projects/selta]]»); «[[target|label]]» shows the
label. Matching ignores case and the extension. The files stay plain
Markdown — a link is only text — so nothing here writes anything.
"""
import re
from dataclasses import dataclass
from pathlib import Path

from core.file_service import read_text_file

NOTE_EXTENSIONS = (".md", ".markdown", ".txt")
LINK_RE = re.compile(r"\[\[([^\[\]\n|]+?)(?:\|([^\[\]\n]+?))?\]\]")


@dataclass(frozen=True)
class Link:
    target: str
    label: str
    line: int      # 0-based line in the note
    start: int     # span of the whole «[[…]]» within that line
    end: int


def links_in(text: str) -> list[Link]:
    found = []
    for number, line in enumerate(text.splitlines()):
        for match in LINK_RE.finditer(line):
            target = match.group(1).strip()
            label = (match.group(2) or match.group(1)).strip()
            if target:
                found.append(Link(target, label, number, match.start(), match.end()))
    return found


def _key(text: str) -> str:
    text = text.strip().replace("\\", "/").casefold()
    for ext in NOTE_EXTENSIONS:
        if text.endswith(ext):
            return text[: -len(ext)]
    return text


class NoteIndex:
    """Every note under a folder, findable by name or by relative path."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.paths: list[Path] = []
        self._by_name: dict[str, Path] = {}
        self._by_rel: dict[str, Path] = {}
        if self.root.exists():
            for path in sorted(self.root.rglob("*")):
                if path.is_file() and path.suffix.lower() in NOTE_EXTENSIONS:
                    self.paths.append(path)
                    rel = path.relative_to(self.root).as_posix()
                    self._by_rel[_key(rel)] = path
                    # The first note with a name wins; a path link disambiguates.
                    self._by_name.setdefault(_key(path.name), path)

    def resolve(self, target: str) -> Path | None:
        key = _key(target)
        return self._by_rel.get(key) or self._by_name.get(key)

    def titles(self) -> list[str]:
        """Names to offer after «[[» — file names without their extension."""
        seen, names = set(), []
        for path in self.paths:
            if path.stem not in seen:
                seen.add(path.stem)
                names.append(path.stem)
        return names


@dataclass(frozen=True)
class Backlink:
    path: str
    title: str
    before: str
    link: str
    after: str


def note_title(text: str, path: Path) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip() or path.stem
        if stripped:
            break
    return path.stem


def backlinks(index: NoteIndex, target: Path, limit: int = 20) -> list[Backlink]:
    """Notes that link to `target`, each with the line the link sits in."""
    target = Path(target).resolve()
    found: list[Backlink] = []
    for path in index.paths:
        if path.resolve() == target:
            continue
        try:
            text = read_text_file(path).text
        except Exception:
            continue
        if "[[" not in text:
            continue
        lines = text.splitlines()
        for link in links_in(text):
            resolved = index.resolve(link.target)
            if resolved is None or resolved.resolve() != target:
                continue
            line = lines[link.line]
            before = line[: link.start].lstrip("-*[] xX").strip()
            found.append(Backlink(str(path), note_title(text, path), before,
                                  link.label, line[link.end:].rstrip()))
            break
        if len(found) >= limit:
            break
    return found
