"""Pushing a task to tomorrow, from My Tasks.

This is the one part of the redesign that writes to a note, so it is the one
that can lose work. The rule it has to keep: a note that is open is edited
through its document, so unsaved changes survive and Ctrl+Z takes it back;
only a note nobody has open is rewritten on disk.
"""
import pytest

from core.file_service import read_text_file


@pytest.fixture
def window(tmp_path, monkeypatch, qapp):
    monkeypatch.setenv("NOTEPAD_DATA_DIR", str(tmp_path / "appdata"))
    from ui.main_window import MainWindow

    window = MainWindow()
    window._cfg["notes_root"] = str(tmp_path / "notes")
    yield window
    for index in range(window.tabs.count()):
        window.tabs.widget(index).mark_clean()
    window.close()


NOTE = "# کارها\n- [ ] ارسال فاکتور @1405/06/02\n- [ ] تمدید هاست @1405/06/12\n"


def test_a_closed_note_is_rewritten_on_disk(window, tmp_path):
    path = tmp_path / "closed.md"
    path.write_text(NOTE, encoding="utf-8")

    window._snooze_task(str(path), 1, 1)

    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[1] == "- [ ] ارسال فاکتور @1405/06/03"
    assert lines[2] == "- [ ] تمدید هاست @1405/06/12", "other lines were touched"


def test_the_trailing_newline_survives(window, tmp_path):
    path = tmp_path / "trailing.md"
    path.write_text(NOTE, encoding="utf-8")
    window._snooze_task(str(path), 1, 1)
    assert path.read_text(encoding="utf-8").endswith("\n")


def test_the_file_encoding_is_preserved(window, tmp_path):
    path = tmp_path / "utf16.md"
    path.write_bytes(NOTE.encode("utf-16"))
    assert read_text_file(path).encoding.startswith("utf-16")

    window._snooze_task(str(path), 1, 1)

    loaded = read_text_file(path)
    assert loaded.encoding.startswith("utf-16")
    assert "@1405/06/03" in loaded.text


def test_an_open_note_is_edited_through_its_document(window, tmp_path):
    """Not written behind the tab's back."""
    path = tmp_path / "open.md"
    path.write_text(NOTE, encoding="utf-8")
    assert window.open_file(str(path))
    tab = window.current_document()

    window._snooze_task(str(path), 1, 1)

    assert tab.editor.document().findBlockByNumber(1).text() == (
        "- [ ] ارسال فاکتور @1405/06/03"
    )
    # The file itself is untouched until the user saves, as with any edit.
    assert path.read_text(encoding="utf-8") == NOTE
    tab.mark_clean()


def test_snoozing_an_open_note_keeps_every_other_line(window, tmp_path):
    """A block selection swallows the newline before it; getting that wrong
    joined the snoozed line onto the one above."""
    path = tmp_path / "join.md"
    path.write_text(NOTE, encoding="utf-8")
    assert window.open_file(str(path))
    tab = window.current_document()
    before = tab.editor.document().blockCount()

    window._snooze_task(str(path), 1, 1)

    assert tab.editor.document().blockCount() == before
    assert tab.editor.document().findBlockByNumber(0).text() == "# کارها"
    assert tab.editor.document().findBlockByNumber(2).text() == (
        "- [ ] تمدید هاست @1405/06/12"
    )
    tab.mark_clean()


def test_snoozing_the_first_line_does_not_lose_it(window, tmp_path):
    path = tmp_path / "first.md"
    path.write_text("- [ ] اول @1405/06/02\n- [ ] دوم\n", encoding="utf-8")
    assert window.open_file(str(path))
    tab = window.current_document()

    window._snooze_task(str(path), 0, 1)

    assert tab.editor.document().findBlockByNumber(0).text() == (
        "- [ ] اول @1405/06/03"
    )
    assert tab.editor.document().findBlockByNumber(1).text() == "- [ ] دوم"
    tab.mark_clean()


def test_one_undo_takes_the_snooze_back(window, tmp_path):
    path = tmp_path / "undo.md"
    path.write_text(NOTE, encoding="utf-8")
    assert window.open_file(str(path))
    tab = window.current_document()

    window._snooze_task(str(path), 1, 1)
    tab.editor.undo()

    assert tab.editor.document().findBlockByNumber(1).text() == (
        "- [ ] ارسال فاکتور @1405/06/02"
    )
    tab.mark_clean()


def test_a_line_with_no_stamp_is_left_alone(window, tmp_path):
    path = tmp_path / "nostamp.md"
    path.write_text("- [ ] بدون تاریخ\n", encoding="utf-8")
    window._snooze_task(str(path), 0, 1)
    assert path.read_text(encoding="utf-8") == "- [ ] بدون تاریخ\n"


def test_a_line_number_past_the_end_is_ignored(window, tmp_path):
    path = tmp_path / "short.md"
    path.write_text(NOTE, encoding="utf-8")
    window._snooze_task(str(path), 99, 1)
    assert path.read_text(encoding="utf-8") == NOTE


def test_a_missing_file_does_not_raise(window, tmp_path):
    window._snooze_task(str(tmp_path / "gone.md"), 0, 1)
