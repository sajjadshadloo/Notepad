"""One file holds every dated task.

4.1 kept a note per day, which fragmented the work into a folder of files
named after dates, each carrying a heading nobody wrote. These cover the one
file that replaced it, and the migration out of the old folder.
"""
from datetime import date

from core import task_file
from core.tasks import parse_document


def _tasks_in(path):
    return parse_document(path.read_text(encoding="utf-8"), str(path))


# Adding

def test_the_file_is_created_on_the_first_task(tmp_path):
    path = task_file.add_task(tmp_path, date(2026, 8, 27), "فاکتور مروارید")
    assert path.name == "کارها.md"
    assert [t.text for t in _tasks_in(path)] == ["فاکتور مروارید"]


def test_a_task_carries_the_day_it_was_added_to(tmp_path):
    path = task_file.add_task(tmp_path, date(2026, 8, 27), "کار")
    task = _tasks_in(path)[0]
    assert task.due.date() == date(2026, 8, 27)
    assert not task.has_time


def test_tasks_stack_in_one_file_whatever_their_day(tmp_path):
    task_file.add_task(tmp_path, date(2026, 8, 27), "یک")
    task_file.add_task(tmp_path, date(2026, 8, 30), "دو")
    task_file.add_task(tmp_path, date(2026, 8, 27), "سه")
    path = task_file.path_for(tmp_path)
    assert [t.text for t in _tasks_in(path)] == ["یک", "دو", "سه"]


def test_there_is_no_heading_and_no_folder(tmp_path):
    """The date heading and the Daily folder are exactly what 4.2 removed."""
    path = task_file.add_task(tmp_path, date(2026, 8, 27), "کار")
    assert not path.read_text(encoding="utf-8").lstrip().startswith("#")
    assert not (tmp_path / "Daily").exists()


def test_existing_content_is_kept(tmp_path):
    path = task_file.path_for(tmp_path)
    path.write_text("- [x] کار قدیمی @۱۴۰۵/۰۶/۰۱\n", encoding="utf-8")
    task_file.add_task(tmp_path, date(2026, 8, 27), "کار تازه")
    assert [t.text for t in _tasks_in(path)] == ["کار قدیمی", "کار تازه"]


# Migrating out of the 4.1 Daily folder

def _day_note(root, stem, text):
    folder = root / "Daily"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / (stem + ".md")).write_text(text, encoding="utf-8")
    return folder / (stem + ".md")


def test_tasks_move_out_of_the_day_notes(tmp_path):
    _day_note(tmp_path, "1405-06-05", "# ۵ شهریور\n\n- [ ] کار یک\n- [x] کار دو\n")
    assert task_file.import_daily_notes(tmp_path) == 2
    assert [t.text for t in _tasks_in(task_file.path_for(tmp_path))] == [
        "کار یک",
        "کار دو",
    ]


def test_a_task_without_a_stamp_takes_the_day_of_its_file(tmp_path):
    _day_note(tmp_path, "1405-06-05", "- [ ] کار\n")
    task_file.import_daily_notes(tmp_path)
    task = _tasks_in(task_file.path_for(tmp_path))[0]
    assert task.due.date() == date(2026, 8, 27)


def test_a_task_that_already_had_a_stamp_keeps_it(tmp_path):
    _day_note(tmp_path, "1405-06-05", "- [ ] کار @۱۴۰۵/۰۶/۲۰\n")
    task_file.import_daily_notes(tmp_path)
    task = _tasks_in(task_file.path_for(tmp_path))[0]
    assert task.due.date() == date(2026, 9, 11)


def test_a_day_note_holding_only_tasks_is_removed(tmp_path):
    path = _day_note(tmp_path, "1405-06-05", "# ۵ شهریور\n\n- [ ] کار\n")
    task_file.import_daily_notes(tmp_path)
    assert not path.exists()


def test_a_day_note_holding_prose_is_kept(tmp_path):
    """Its tasks move, but the writing in it is a note and must survive."""
    path = _day_note(
        tmp_path, "1405-06-06", "# ۶ شهریور\n\nچیزی که نوشته‌ام\n- [ ] کار\n"
    )
    task_file.import_daily_notes(tmp_path)
    assert path.exists()
    assert "چیزی که نوشته‌ام" in path.read_text(encoding="utf-8")


def test_a_file_that_is_not_a_day_name_is_left_alone(tmp_path):
    path = _day_note(tmp_path, "notes", "- [ ] کار\n")
    assert task_file.import_daily_notes(tmp_path) == 0
    assert path.exists()


def test_no_daily_folder_is_not_an_error(tmp_path):
    assert task_file.import_daily_notes(tmp_path) == 0


def test_an_empty_daily_folder_is_removed(tmp_path):
    _day_note(tmp_path, "1405-06-05", "- [ ] کار\n")
    task_file.import_daily_notes(tmp_path)
    assert not (tmp_path / "Daily").exists()
