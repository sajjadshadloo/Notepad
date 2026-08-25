"""Paragraph-level bidi direction detection.

This runs for every paragraph of every layout pass, so it is written to let
a compiled regex answer the common questions in C and to fall back to a
per-character walk only when the text genuinely mixes both scripts.
"""
import re
import unicodedata
from functools import lru_cache

# Every character Unicode classifies as R, AL or AN lives in one of these
# ranges, so a miss here proves the text has no right-to-left character at
# all. Ranges are deliberately broader than the bidi classes themselves —
# this is only a presence test; the exact counting below stays authoritative.
_RTL_RE = re.compile(
    "["
    "֐-ࣿ"           # Hebrew, Arabic, Syriac, Thaana, NKo, Samaritan
    "יִ-﷿"           # Hebrew and Arabic presentation forms A
    "ﹰ-﻿"           # Arabic presentation forms B
    "‏‫‮⁧"  # RLM and the explicit RTL bidi controls
    "\U00010800-\U00010fff"   # Cypriot, Kharoshthi, Old South Arabian…
    "\U0001e800-\U0001efff"   # Mende Kikakui, Adlam, Arabic Mathematical
    "]"
)

# The overwhelmingly common left-to-right case: a hit proves at least one
# strong LTR character exists without walking the string in Python.
_ASCII_LETTER_RE = re.compile("[A-Za-z]")

# AN (Arabic-Indic digits) counts as right-to-left the way it reads on
# screen. EN (ASCII digits) is deliberately absent from both sets so a line
# of bare numbers keeps the caller's default instead of forcing a direction.
_RTL_BIDI = frozenset(("R", "AL", "AN", "RLE", "RLO", "RLI"))
_LTR_BIDI = frozenset(("L", "LRE", "LRO", "LRI"))

# Past this many characters the majority is settled in any real paragraph;
# the cap keeps one pathologically long line from stalling a layout pass.
_SCAN_LIMIT = 4096

# Per-character verdicts: 1 = RTL, -1 = LTR, 0 = neutral. Real text reuses a
# few dozen distinct characters, so this collapses to dict hits almost at once.
_WEIGHTS: dict[str, int] = {}


def _weight(ch: str) -> int:
    weight = _WEIGHTS.get(ch)
    if weight is None:
        try:
            bidi = unicodedata.bidirectional(ch)
        except Exception:
            bidi = ""
        weight = 1 if bidi in _RTL_BIDI else -1 if bidi in _LTR_BIDI else 0
        _WEIGHTS[ch] = weight
    return weight


def is_rtl_char(ch: str) -> bool:
    return _weight(ch) > 0


# A layout pass re-tests the same paragraphs over and over while only one of
# them is being edited, so the answer for a given line is worth keeping.
# Keys are immutable strings, which makes the cache safe to share globally.
@lru_cache(maxsize=4096)
def detect_direction(text: str, default: str = "rtl") -> str:
    """Direction of ``text`` by strong-character majority.

    Ties go to ``default``, and so does text with no strong character at all
    (an empty line, or a line of ASCII digits).
    """
    if not text:
        return default

    if _RTL_RE.search(text) is None:
        # No right-to-left character can exist, so the only open question is
        # whether any strong left-to-right one does.
        if _ASCII_LETTER_RE.search(text) is not None:
            return "ltr"
        return (
            "ltr"
            if any(_weight(ch) < 0 for ch in text[:_SCAN_LIMIT])
            else default
        )

    # Both scripts may be present: count them. ``balance`` is rtl minus ltr,
    # so ``>= 0`` is the same tie-goes-to-rtl rule as an explicit comparison.
    balance = 0
    strong = False
    for ch in text[:_SCAN_LIMIT]:
        weight = _weight(ch)
        if weight:
            balance += weight
            strong = True
    if not strong:
        return default
    return "rtl" if balance >= 0 else "ltr"
