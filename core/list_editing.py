"""Pure helpers for Markdown list editing and presentation.

The editor keeps standard Markdown in the document. These helpers describe
the list item so the UI can continue, indent and render it without converting
the user's file to rich text.
"""
from dataclasses import dataclass

from core.formatting import BULLET_RE, NUMBERED_RE, TODO_RE


@dataclass(frozen=True)
class ListItem:
    kind: str
    indent: str
    body: str
    marker_start: int
    marker_end: int
    prefix_end: int
    marker: str
    checked: bool = False
    number: int | None = None
    delimiter: str = "."

    @property
    def is_empty(self) -> bool:
        return not self.body.strip()

    def continuation_prefix(self) -> str:
        if self.kind == "todo":
            return f"{self.indent}- [ ] "
        if self.kind == "numbered":
            return f"{self.indent}{(self.number or 0) + 1}{self.delimiter} "
        return f"{self.indent}{self.marker} "


def parse_list_item(line: str) -> ListItem | None:
    """Parse a Markdown bullet, numbered item or GitHub-style to-do line."""
    todo = TODO_RE.match(line)
    if todo:
        start = len(todo.group(1))
        return ListItem(
            kind="todo",
            indent=todo.group(1),
            body=line[todo.end():],
            marker_start=start,
            marker_end=start + 5,
            prefix_end=todo.end(),
            marker="-",
            checked=todo.group(2) in "xX",
        )

    numbered = NUMBERED_RE.match(line)
    if numbered:
        start = len(numbered.group(1))
        marker = f"{numbered.group(2)}{numbered.group(3)}"
        return ListItem(
            kind="numbered",
            indent=numbered.group(1),
            body=line[numbered.end():],
            marker_start=start,
            marker_end=start + len(marker),
            prefix_end=numbered.end(),
            marker=marker,
            number=int(numbered.group(2)),
            delimiter=numbered.group(3),
        )

    bullet = BULLET_RE.match(line)
    if bullet:
        start = len(bullet.group(1))
        marker = line[start]
        return ListItem(
            kind="bullet",
            indent=bullet.group(1),
            body=line[bullet.end():],
            marker_start=start,
            marker_end=start + 1,
            prefix_end=bullet.end(),
            marker=marker,
        )

    return None


_PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def display_number_marker(marker: str, rtl: bool) -> str:
    """Presentation form of a numbered-list marker.

    The document keeps ASCII digits; an RTL paragraph just *shows* Persian
    digits. The delimiter goes in FRONT of the digits because the marker is
    painted in an explicitly LTR run: "۱." becomes ".۱", which puts the dot
    visually to the LEFT of the digit — the correct Persian reading order
    (digit first, then the dot, reading right-to-left). Confirmed by the
    user in 2.5.0: dot on the right of the digit is wrong.
    """
    if not rtl:
        return marker
    translated = marker.translate(_PERSIAN_DIGITS)
    if translated and translated[-1] in ".)":
        return translated[-1] + translated[:-1]
    return translated


def indent_list_line(line: str, width: int = 2) -> str:
    """Indent a list item by one visual level; leave normal text unchanged."""
    return " " * width + line if parse_list_item(line) else line


def outdent_list_line(line: str, width: int = 2) -> str:
    """Outdent a list item by one visual level; leave normal text unchanged."""
    item = parse_list_item(line)
    if not item or not item.indent:
        return line
    if line.startswith("\t"):
        return line[1:]
    remove = min(width, len(item.indent) - len(item.indent.lstrip(" ")))
    return line[remove:] if remove else line
