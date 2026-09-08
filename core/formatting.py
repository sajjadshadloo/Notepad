"""Markdown-style line formatting helpers.

Pure string functions used by the Format menu. Each one toggles a prefix on a
single line and never touches the rest of the user's text.
"""
import re

HEADING_RE = re.compile(r"^(#{1,6})\s+")
BULLET_RE = re.compile(r"^(\s*)[-*]\s+(?!\[)")
TODO_RE = re.compile(r"^(\s*)- \[( |x|X)\]\s?")
NUMBERED_RE = re.compile(r"^(\s*)(\d+)([.)])\s+")


def strip_marker(line: str) -> tuple[str, str]:
    """Split a line into its indent and its text, dropping any block marker.

    A line is a heading, a bullet, a numbered item, a to-do or plain text —
    one of them, never several. Until 4.1.3 each toggle only knew its own
    marker, so pressing ☑ then H2 then • built "- ## - [ ] ", which renders
    as a painted bullet followed by the literal text "## - [ ]". Everything
    that sets a marker now clears the old one through here.
    """
    heading = HEADING_RE.match(line)
    if heading:
        # Headings carry no indent of their own.
        return "", line[heading.end():]
    # To-do before bullet: "- [ ] x" starts like a bullet, and BULLET_RE only
    # declines it by lookahead.
    for pattern in (TODO_RE, NUMBERED_RE, BULLET_RE):
        match = pattern.match(line)
        if match:
            return match.group(1), line[match.end():]
    indent = len(line) - len(line.lstrip())
    return line[:indent], line[indent:]


def toggle_heading(line: str, level: int) -> str:
    """Set the line to this heading level; the same level removes it."""
    match = HEADING_RE.match(line)
    if match and len(match.group(1)) == level:
        return line[match.end():]
    _indent, body = strip_marker(line)
    return "#" * level + " " + body


def toggle_bullet(line: str) -> str:
    """Toggle a "- " bullet, replacing whatever marker the line had."""
    indent, body = strip_marker(line)
    if BULLET_RE.match(line):
        return indent + body
    return indent + "- " + body


def toggle_todo(line: str) -> str:
    """Toggle a "- [ ] " to-do, replacing whatever marker the line had."""
    indent, body = strip_marker(line)
    if TODO_RE.match(line):
        return indent + body
    return indent + "- [ ] " + body


def toggle_numbered(line: str) -> str:
    """Toggle a "1. " prefix, replacing whatever marker the line had."""
    indent, body = strip_marker(line)
    if NUMBERED_RE.match(line):
        return indent + body
    return indent + "1. " + body


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
