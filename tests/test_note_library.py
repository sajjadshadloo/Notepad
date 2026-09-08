"""Reading the notes folder as cards grouped by subfolder.

The folder is the category, so these are mostly about what a card says about
a file and which tab it lands under.
"""
from core.note_library import (
    ROOT_LABEL,
    categories,
    in_category,
    load_library,
    summarise,
)


def _write(root, relative: str, text: str):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# Titles

def test_the_first_heading_names_the_card(tmp_path):
    _write(tmp_path, "a.md", "# برنامه توسعه\n\nمتن\n")
    assert load_library(tmp_path)[0].title == "برنامه توسعه"


def test_without_a_heading_the_filename_names_it(tmp_path):
    _write(tmp_path, "اطلاعات هاست.txt", "user: admin\n")
    assert load_library(tmp_path)[0].title == "اطلاعات هاست"


def test_a_heading_further_down_does_not_win(tmp_path):
    """Only a leading heading is the note's name; a later one is a section."""
    _write(tmp_path, "a.md", "خط اول\n\n# بخش دوم\n")
    assert load_library(tmp_path)[0].title == "a"


# Preview

def test_prose_lines_become_the_preview(tmp_path):
    _write(tmp_path, "a.md", "# عنوان\n\nخط یک\nخط دو\n")
    card = load_library(tmp_path)[0]
    assert card.lines == ("خط یک", "خط دو")
    assert card.tasks == ()


def test_tasks_become_checkbox_rows(tmp_path):
    _write(tmp_path, "a.md", "- [ ] یک\n- [x] دو\n")
    card = load_library(tmp_path)[0]
    assert [(t.done, t.text) for t in card.tasks] == [(False, "یک"), (True, "دو")]


def test_a_cards_task_loses_its_date_stamp(tmp_path):
    """The calendar shows when; the card only has room for what."""
    _write(tmp_path, "a.md", "- [ ] تماس با مشتری @۱۴۰۵/۰۶/۰۵\n")
    assert load_library(tmp_path)[0].tasks[0].text == "تماس با مشتری"


def test_the_open_count_covers_the_whole_note_not_the_preview(tmp_path):
    """The preview stops at six rows; the badge must not stop with it."""
    body = "".join("- [ ] کار %d\n" % index for index in range(20))
    _write(tmp_path, "a.md", body + "- [x] تمام‌شده\n")
    card = load_library(tmp_path)[0]
    assert len(card.tasks) == 6
    assert card.open_tasks == 20


def test_a_long_note_is_only_read_as_far_as_the_preview_needs(tmp_path):
    """A 39 KB note exists in the real folder; the card reads its head."""
    text = "# عنوان\n\n" + ("خط پرحرف\n" * 5000)
    card = summarise(text, tmp_path / "big.md", "", 0.0)
    assert len(card.lines) == 4


# Categories

def test_a_subfolder_becomes_a_category(tmp_path):
    _write(tmp_path, "Daily/1405-06-05.md", "- [ ] کار\n")
    assert load_library(tmp_path)[0].category == "Daily"


def test_a_note_in_the_root_gets_the_default_category(tmp_path):
    _write(tmp_path, "a.md", "متن\n")
    assert load_library(tmp_path)[0].category == ROOT_LABEL


def test_only_the_first_folder_level_is_a_category(tmp_path):
    """Nesting deeper should not invent a tab per subdirectory."""
    _write(tmp_path, "کارها/۱۴۰۵/a.md", "متن\n")
    assert load_library(tmp_path)[0].category == "کارها"


def test_the_root_category_leads_and_the_rest_are_sorted(tmp_path):
    _write(tmp_path, "z.md", "متن\n")
    _write(tmp_path, "Work/a.md", "متن\n")
    _write(tmp_path, "Archive/a.md", "متن\n")
    assert categories(load_library(tmp_path)) == [ROOT_LABEL, "Archive", "Work"]


def test_the_root_category_is_absent_when_nothing_is_loose(tmp_path):
    _write(tmp_path, "Work/a.md", "متن\n")
    assert categories(load_library(tmp_path)) == ["Work"]


def test_filtering_by_category_keeps_only_that_folder(tmp_path):
    _write(tmp_path, "loose.md", "متن\n")
    _write(tmp_path, "Work/a.md", "متن\n")
    cards = load_library(tmp_path)
    assert [c.title for c in in_category(cards, "Work")] == ["a"]
    assert len(in_category(cards, "")) == 2


# Loading

def test_newest_notes_come_first(tmp_path):
    import os
    import time

    old = _write(tmp_path, "old.md", "متن\n")
    time.sleep(0.01)
    _write(tmp_path, "new.md", "متن\n")
    os.utime(old, (1, 1))
    assert [c.title for c in load_library(tmp_path)][0] == "new"


def test_files_that_are_not_notes_are_skipped(tmp_path):
    _write(tmp_path, "a.md", "متن\n")
    _write(tmp_path, "b.pdf", "متن\n")
    assert [c.title for c in load_library(tmp_path)] == ["a"]


def test_a_missing_folder_loads_as_nothing(tmp_path):
    assert load_library(tmp_path / "nowhere") == []
