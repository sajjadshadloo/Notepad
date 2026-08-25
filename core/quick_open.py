"""Ranking for the Ctrl+P quick-open list.

Pure string logic, no Qt, so the matching rules can be tested directly.
Matching runs over the path *relative to the notes folder*, which means a
folder name is as good a way to find a note as its filename.
"""
from dataclasses import dataclass

# Score bands, best first. The gaps are wide enough that a weaker match can
# never overtake a stronger one on tie-breakers alone.
_EXACT = 0
_NAME_PREFIX = 100
_NAME_SUBSTRING = 200
_PATH_SUBSTRING = 300
_SUBSEQUENCE = 400


@dataclass(frozen=True)
class Candidate:
    path: str
    relative: str
    name: str


def _subsequence_span(query: str, text: str) -> int | None:
    """Length of text consumed to match every query character in order.

    A tighter span means the characters sat closer together, which is the
    difference between "notes/site.txt" and "n...o...t...e...s" noise.
    """
    position = 0
    first = None
    for char in query:
        found = text.find(char, position)
        if found == -1:
            return None
        if first is None:
            first = found
        position = found + 1
    return position - (first or 0)


def score(query: str, candidate: Candidate) -> tuple[int, int, int] | None:
    """Rank one candidate, or None when it does not match at all.

    The tuple sorts ascending: band first, then how tight the match was,
    then the length of the path so shorter names win an exact tie.
    """
    if not query:
        return (_SUBSEQUENCE, 0, len(candidate.relative))

    name = candidate.name.casefold()
    relative = candidate.relative.casefold()
    needle = query.casefold()

    if name == needle:
        return (_EXACT, 0, len(relative))
    if name.startswith(needle):
        return (_NAME_PREFIX, 0, len(relative))
    index = name.find(needle)
    if index != -1:
        return (_NAME_SUBSTRING, index, len(relative))
    index = relative.find(needle)
    if index != -1:
        return (_PATH_SUBSTRING, index, len(relative))
    # Last resort: the characters appear in order but not adjacently, which
    # is what makes "bmsm" find "بامسما" style abbreviations.
    span = _subsequence_span(needle, relative)
    if span is None:
        return None
    return (_SUBSEQUENCE, span, len(relative))


def rank(query: str, candidates: list[Candidate], limit: int = 50) -> list[Candidate]:
    scored = []
    for candidate in candidates:
        value = score(query, candidate)
        if value is not None:
            scored.append((value, candidate))
    scored.sort(key=lambda pair: (pair[0], pair[1].relative))
    return [candidate for _value, candidate in scored[:limit]]
