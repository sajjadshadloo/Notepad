from datetime import date

from core import daily_notes


def test_file_name_uses_ascii_digits_so_it_sorts(tmp_path):
    """Persian digits would scramble ordering in Explorer and the sidebar."""
    path = daily_notes.path_for(tmp_path, date(2026, 8, 25))
    assert path.name == "1405-06-03.md"
    assert path.parent.name == "Daily"


def test_starter_text_reads_in_persian():
    text = daily_notes.starter_text(date(2026, 8, 25))
    assert text.startswith("# ۳ شهریور ۱۴۰۵")
    assert text.endswith("- [ ] ")


def test_recognises_its_own_notes(tmp_path):
    inside = daily_notes.path_for(tmp_path, date(2026, 8, 25))
    inside.parent.mkdir(parents=True)
    inside.write_text("x", encoding="utf-8")
    other = tmp_path / "regular.md"
    other.write_text("x", encoding="utf-8")

    assert daily_notes.is_daily_note(tmp_path, inside)
    assert not daily_notes.is_daily_note(tmp_path, other)
    assert not daily_notes.is_daily_note(tmp_path, "C:/elsewhere/1405-06-03.md")


def test_existing_days_lists_what_was_written(tmp_path):
    assert daily_notes.existing_days(tmp_path) == set()
    for day in (date(2026, 8, 25), date(2026, 8, 26)):
        p = daily_notes.path_for(tmp_path, day)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x", encoding="utf-8")
    assert daily_notes.existing_days(tmp_path) == {"1405-06-03", "1405-06-04"}
