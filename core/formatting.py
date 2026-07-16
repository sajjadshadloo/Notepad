"""Markdown-style line formatting helpers.

Pure string functions used by the Format menu. Each one toggles a prefix on a
single line and never touches the rest of the user's text.
"""
import re

HEADING_RE = re.compile(r"^(#{1,6})\s+")
BULLET_RE = re.compile(r"^(\s*)[-*]\s+(?!\[)")
TODO_RE = re.compile(r"^(\s*)- \[( |x|X)\]\s?")
NUMBERED_RE = re.compile(r"^(\s*)(\d+)([.)])\s+")


def toggle_heading(line: str, level: int) -> str:
    """Set the line to the given heading level; same level removes it."""
    match = HEADING_RE.match(line)
    body = line[match.end():] if match else line
    if match and len(match.group(1)) == level:
        return body
    return "#" * level + " " + body


def toggle_bullet(line: str) -> str:
    """Toggle a "- " bullet. Converts a todo line back to plain text first."""
    todo = TODO_RE.match(line)
    if todo:
        return todo.group(1) + "- " + line[todo.end():]
    match = BULLET_RE.match(line)
    if match:
        return match.group(1) + line[match.end():]
    stripped = len(line) - len(line.lstrip())
    return line[:stripped] + "- " + line[stripped:]


def toggle_todo(line: str) -> str:
    """Toggle a "- [ ] " todo prefix. Upgrades an existing bullet in place."""
    todo = TODO_RE.match(line)
    if todo:
        return todo.group(1) + line[todo.end():]
    bullet = BULLET_RE.match(line)
    if bullet:
        return bullet.group(1) + "- [ ] " + line[bullet.end():]
    stripped = len(line) - len(line.lstrip())
    return line[:stripped] + "- [ ] " + line[stripped:]


def toggle_numbered(line: str) -> str:
    """Toggle a numbered-list prefix, converting other list kinds in place."""
    numbered = NUMBERED_RE.match(line)
    if numbered:
        return numbered.group(1) + line[numbered.end():]

    todo = TODO_RE.match(line)
    if todo:
        return todo.group(1) + "1. " + line[todo.end():]

    bullet = BULLET_RE.match(line)
    if bullet:
        return bullet.group(1) + "1. " + line[bullet.end():]

    stripped = len(line) - len(line.lstrip())
    return line[:stripped] + "1. " + line[stripped:]


def toggle_done(line: str) -> str:
    """Flip the checked state of a todo line; other lines are unchanged."""
    match = TODO_RE.match(line)
    if not match:
        return line
    state = match.group(2)
    replacement = " " if state in "xX" else "x"
    start = match.start(2)
    return line[:start] + replacement + line[start + 1:]


def toggle_bold(text: str) -> str:
    """Wrap a snippet in ``**``, or unwrap it when already bold."""
    if text.startswith("**") and text.endswith("**") and len(text) > 4:
        return text[2:-2]
    return f"**{text}**" if text else text


def todo_checkbox_span(line: str) -> tuple[int, int] | None:
    """Column range of the "- [ ]" token, or None if not a todo line."""
    match = TODO_RE.match(line)
    if not match:
        return None
    start = len(match.group(1))
    return (start, start + 5)
