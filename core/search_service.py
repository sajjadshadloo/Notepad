from dataclasses import dataclass
from pathlib import Path

from core.file_service import read_text_file

DEFAULT_EXTENSIONS = (".txt", ".md", ".markdown")
SNIPPET_RADIUS = 40


@dataclass(frozen=True)
class SearchResult:
    path: str
    line_number: int
    snippet: str


def _snippet(line: str, index: int, needle_len: int) -> str:
    start = max(0, index - SNIPPET_RADIUS)
    end = min(len(line), index + needle_len + SNIPPET_RADIUS)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(line) else ""
    return f"{prefix}{line[start:end].strip()}{suffix}"


def search_notes(
    root: str,
    query: str,
    *,
    case_sensitive: bool = False,
    extensions=DEFAULT_EXTENSIONS,
) -> list[SearchResult]:
    """Match the query against note *titles* first, then note content.

    Title matches come back first (line_number 0, empty snippet) so the
    sidebar reads like a filename filter, with content hits below them.
    """
    if not query:
        return []
    needle = query if case_sensitive else query.casefold()
    title_results: list[SearchResult] = []
    content_results: list[SearchResult] = []
    root_path = Path(root)
    if not root_path.exists():
        return []

    for file_path in sorted(root_path.rglob("*")):
        if not file_path.is_file() or file_path.suffix.lower() not in extensions:
            continue
        resolved = str(file_path.resolve())
        title = file_path.stem if case_sensitive else file_path.stem.casefold()
        if needle in title:
            title_results.append(
                SearchResult(path=resolved, line_number=0, snippet="")
            )
            continue
        try:
            loaded = read_text_file(file_path)
        except Exception:
            continue
        for line_number, line in enumerate(loaded.text.splitlines(), start=1):
            haystack = line if case_sensitive else line.casefold()
            index = haystack.find(needle)
            if index != -1:
                content_results.append(
                    SearchResult(
                        path=resolved,
                        line_number=line_number,
                        snippet=_snippet(line, index, len(needle)),
                    )
                )
    return title_results + content_results
