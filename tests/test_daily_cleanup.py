"""Day notes must stop leaving empty files behind.

Up to 3.11 clicking a day in the calendar wrote the file immediately, so
browsing the month left one note per visit containing only its own heading.
"""
from datetime import date

from core import daily_notes
from core.jalali import from_gregorian


def _write(root, day: date, text: str):
    path = daily_notes.path_for(root, day)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_a_note_holding_only_its_heading_counts_as_untouched():
    day = date(2026, 8, 27)
    assert daily_notes.is_untouched(daily_notes.starter_text(day), day)


def test_an_empty_file_counts_as_untouched():
    assert daily_notes.is_untouched("", date(2026, 8, 27))
    assert daily_notes.is_untouched("   \n\n", date(2026, 8, 27))


def test_a_note_with_anything_typed_in_it_is_kept():
    day = date(2026, 8, 27)
    written = daily_notes.starter_text(day) + "تماس با مشتری"
    assert not daily_notes.is_untouched(written, day)


def test_a_heading_from_a_different_day_is_kept(tmp_path):
    """Guards the comparison itself: it must be against *this* day's heading."""
    day = date(2026, 8, 27)
    other = daily_notes.starter_text(date(2026, 8, 28))
    assert not daily_notes.is_untouched(other, day)


def test_prune_removes_the_empty_ones_and_only_those(tmp_path):
    empty = _write(tmp_path, date(2026, 8, 27), daily_notes.starter_text(date(2026, 8, 27)))
    blank = _write(tmp_path, date(2026, 8, 28), "")
    real = _write(
        tmp_path,
        date(2026, 8, 29),
        daily_notes.starter_text(date(2026, 8, 29)) + "کار واقعی",
    )

    removed = daily_notes.prune_empty(tmp_path)

    assert set(removed) == {empty, blank}
    assert not empty.exists() and not blank.exists()
    assert real.exists()


def test_prune_ignores_files_that_are_not_day_names(tmp_path):
    folder = tmp_path / daily_notes.FOLDER
    folder.mkdir(parents=True)
    stray = folder / "notes.md"
    stray.write_text("", encoding="utf-8")

    assert daily_notes.prune_empty(tmp_path) == []
    assert stray.exists()


def test_prune_on_a_folder_that_does_not_exist_is_quiet(tmp_path):
    assert daily_notes.prune_empty(tmp_path / "nowhere") == []


def test_the_stem_round_trips_through_the_jalali_calendar(tmp_path):
    """prune_empty reads the day back out of the filename; that has to match."""
    day = date(2026, 8, 27)
    stem = daily_notes.path_for(tmp_path, day).stem
    year, month, number = (int(part) for part in stem.split("-"))
    assert (year, month, number) == from_gregorian(day)
