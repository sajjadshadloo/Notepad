"""Markdown tables as data.

A table in the file is a run of lines that start and end with "|". The editor
shows that run as a grid and edits it one cell at a time, so everything that
reads or rewrites a row lives here, away from Qt, where it can be tested.

The file keeps the plain text it always had. Nothing here invents syntax.
"""
import re

SEPARATOR_CELL_RE = re.compile(r"^:?-{1,}:?$")
BREAK_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)


def is_row(line: str) -> bool:
    """A table line: starts and ends with a pipe, with something between."""
    stripped = line.strip()
    return len(stripped) >= 3 and stripped.startswith("|") and stripped.endswith("|")


def split_cells(line: str) -> list[str]:
    """The cells of one row, outer pipes dropped and each cell trimmed."""
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def is_separator(line: str) -> bool:
    """The "| --- | :---: |" line under the header."""
    if not is_row(line):
        return False
    cells = split_cells(line)
    return bool(cells) and all(SEPARATOR_CELL_RE.match(cell) for cell in cells)


def join_cells(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def replace_cell(line: str, column: int, text: str) -> str:
    """The row with one cell swapped. A pipe typed in a cell would split it."""
    cells = split_cells(line)
    while len(cells) <= column:
        cells.append("")
    cells[column] = text.replace("|", "/").replace("\n", " ").strip()
    return join_cells(cells)


def empty_row(columns: int) -> str:
    return join_cells([""] * columns)


def new_table(columns: int = 3, body_rows: int = 2) -> list[str]:
    """Header, separator and empty rows, ready to be typed into."""
    header = join_cells([""] * columns)
    separator = join_cells(["---"] * columns)
    return [header, separator] + [empty_row(columns) for _ in range(body_rows)]


def add_column(lines: list[str]) -> list[str]:
    out = []
    for line in lines:
        cells = split_cells(line)
        cells.append("---" if is_separator(line) else "")
        out.append(join_cells(cells))
    return out


def remove_column(lines: list[str], column: int) -> list[str]:
    out = []
    for line in lines:
        cells = split_cells(line)
        if len(cells) > 1 and column < len(cells):
            del cells[column]
        out.append(join_cells(cells))
    return out


def column_alignments(separator: str) -> list[str]:
    """"left", "right" or "center" per column, from the colons."""
    result = []
    for cell in split_cells(separator):
        left, right = cell.startswith(":"), cell.endswith(":")
        result.append("center" if left and right else "right" if right else "left")
    return result


def cell_html(text: str) -> str:
    """One cell as the small HTML the grid paints: bold, code, line breaks."""
    escaped = (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    escaped = re.sub(r"&lt;br\s*/?&gt;", "<br>", escaped, flags=re.IGNORECASE)
    escaped = re.sub(r"\*\*(?!\s)(.+?)(?<!\s)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    return escaped
