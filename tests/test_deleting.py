"""Removing a note or a task.

Both destroy something the user wrote, so both ask first, and a note goes to
the Recycle Bin rather than being unlinked — a wrong click has to be
recoverable. The confirmation is stubbed here; what is checked is that
"no" really means nothing happened.
"""
from datetime import date

import pytest
from PyQt6.QtWidgets import QMessageBox

from core import settings_manager, task_file, trash
from core.file_service import read_text_file
from core.tasks import parse_document
from ui.main_window import MainWindow


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    data = tmp_path / "appdata"
    data.mkdir()
    monkeypatch.setattr(settings_manager, "app_data_dir", lambda: data)
    notes = tmp_path / "notes"
    notes.mkdir()
    win = MainWindow([])
    win._cfg["notes_root"] = str(notes)
    yield win
    while win.tabs.count():
        win.tabs.widget(0).mark_clean()
        win.close_tab(0, create_replacement=False)
    win._really_quitting = True
    win.close()
    win.deleteLater()


def _answer(monkeypatch, button):
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: button))


def _tasks_in(path):
    return parse_document(read_text_file(path).text, str(path))


# Tasks

def test_deleting_a_task_removes_only_its_line(window, monkeypatch):
    root = window._cfg["notes_root"]
    for text in ("یک", "دو", "سه"):
        window.add_task_to_day(date(2026, 8, 27), text)
    path = task_file.path_for(root)
    line = _tasks_in(path)[1].line_number

    _answer(monkeypatch, QMessageBox.StandardButton.Yes)
    window.delete_task(str(path), line)

    assert [t.text for t in _tasks_in(path)] == ["یک", "سه"]


def test_saying_no_leaves_the_task_alone(window, monkeypatch):
    root = window._cfg["notes_root"]
    window.add_task_to_day(date(2026, 8, 27), "کار")
    path = task_file.path_for(root)
    before = path.read_text(encoding="utf-8")

    _answer(monkeypatch, QMessageBox.StandardButton.No)
    window.delete_task(str(path), 0)

    assert path.read_text(encoding="utf-8") == before


def test_deleting_a_task_in_an_open_file_goes_through_the_document(
    window, monkeypatch
):
    """The file may hold unsaved edits; writing to disk would lose them."""
    root = window._cfg["notes_root"]
    window.add_task_to_day(date(2026, 8, 27), "یک")
    window.add_task_to_day(date(2026, 8, 27), "دو")
    path = task_file.path_for(root)
    window.open_file(str(path))
    tab = window.current_document()
    # At the end, or the unsaved text lands on the very line being deleted.
    cursor = tab.editor.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    tab.editor.setTextCursor(cursor)
    tab.editor.insertPlainText("\nیادداشت ذخیره‌نشده")

    _answer(monkeypatch, QMessageBox.StandardButton.Yes)
    window.delete_task(str(path), 0)

    assert "یک" not in tab.text
    assert "دو" in tab.text
    assert "یادداشت ذخیره‌نشده" in tab.text
    # Untouched on disk: nothing was saved, so nothing was lost.
    assert "یک" in path.read_text(encoding="utf-8")


def test_deleting_a_task_is_one_undo_step(window, monkeypatch):
    root = window._cfg["notes_root"]
    window.add_task_to_day(date(2026, 8, 27), "یک")
    window.add_task_to_day(date(2026, 8, 27), "دو")
    path = task_file.path_for(root)
    window.open_file(str(path))
    tab = window.current_document()
    before = tab.text

    _answer(monkeypatch, QMessageBox.StandardButton.Yes)
    window.delete_task(str(path), 0)
    assert tab.text != before
    tab.editor.undo()
    assert tab.text == before


def test_a_line_past_the_end_asks_nothing_and_does_nothing(window, monkeypatch):
    root = window._cfg["notes_root"]
    window.add_task_to_day(date(2026, 8, 27), "کار")
    path = task_file.path_for(root)
    before = path.read_text(encoding="utf-8")

    def refuse(*args, **kwargs):
        pytest.fail("should not have asked about a line that is not there")

    monkeypatch.setattr(QMessageBox, "question", staticmethod(refuse))
    window.delete_task(str(path), 999)
    assert path.read_text(encoding="utf-8") == before


# Notes

def test_deleting_a_note_removes_the_file(window, monkeypatch):
    root = window._cfg["notes_root"]
    path = root + "/یادداشت.md"
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("متن\n")

    _answer(monkeypatch, QMessageBox.StandardButton.Yes)
    window.delete_note(path)

    from pathlib import Path

    assert not Path(path).exists()


def test_saying_no_leaves_the_note_alone(window, monkeypatch):
    from pathlib import Path

    root = window._cfg["notes_root"]
    path = root + "/یادداشت.md"
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("متن\n")

    _answer(monkeypatch, QMessageBox.StandardButton.No)
    window.delete_note(path)

    assert Path(path).exists()


def test_a_note_goes_to_the_recycle_bin_when_there_is_one(window, monkeypatch):
    """Unlinking is the fallback, not the first choice."""
    root = window._cfg["notes_root"]
    path = root + "/یادداشت.md"
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("متن\n")

    asked = []
    monkeypatch.setattr(
        trash, "send_to_recycle_bin", lambda p: asked.append(p) or True
    )
    monkeypatch.setattr(
        MainWindow, "_unlink", staticmethod(lambda p: pytest.fail("unlinked"))
    )
    _answer(monkeypatch, QMessageBox.StandardButton.Yes)
    window.delete_note(path)

    assert asked == [path]


def test_an_open_note_is_closed_before_it_is_deleted(window, monkeypatch):
    from pathlib import Path

    root = window._cfg["notes_root"]
    path = root + "/یادداشت.md"
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("متن\n")
    window.open_file(path)
    assert window.current_document().path == str(Path(path).resolve())

    _answer(monkeypatch, QMessageBox.StandardButton.Yes)
    window.delete_note(path)

    open_paths = [
        window.tabs.widget(i).path for i in range(window.tabs.count())
    ]
    assert str(Path(path).resolve()) not in open_paths
    assert not Path(path).exists()
