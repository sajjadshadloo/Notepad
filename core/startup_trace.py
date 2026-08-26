"""Phase timing for application startup, off unless asked for.

Startup is dominated by work that only happens in the packaged build — Qt
loading plugins and fonts from disk — so timing it from source misleads.
Set ``NOTEPAD_TRACE_STARTUP=1`` and the log gets a breakdown of the run that
actually matters.
"""
import os
import time

STARTED_AT = time.perf_counter()
ENABLED = bool(os.environ.get("NOTEPAD_TRACE_STARTUP"))

_marks: list[tuple[str, float]] = []


def mark(label: str):
    if ENABLED:
        _marks.append((label, (time.perf_counter() - STARTED_AT) * 1000))


def marks() -> list[tuple[str, float]]:
    return list(_marks)


def elapsed_ms() -> float:
    return (time.perf_counter() - STARTED_AT) * 1000
