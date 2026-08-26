"""Ctrl+P now answers three questions from one box.

Notes still lead — that is what the box is for — with open tasks and
commands below them. The group headings are not selectable, so arrowing
through the list never lands on one.
"""
import pytest
from PyQt6.QtCore import Qt

from core.tasks import parse_document
from ui.quick_open import QuickOpenDialog


@pytest.fixture
def notes(tmp_path):
    (tmp_path / "بامسما.md").write_text(
        "- [ ] ارسال فاکتور @1405/06/02\n", encoding="utf-8"
    )
    (tmp_path / "snippets.txt").write_text("# snippets\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def tasks(notes):
    path = notes / "بامسما.md"
    return parse_document(path.read_text(encoding="utf-8"), str(path))


def _rows(dialog):
    return [dialog.results.item(i).text() for i in range(dialog.results.count())]


def _payloads(dialog):
    return [
        dialog.results.item(i).data(Qt.ItemDataRole.UserRole)
        for i in range(dialog.results.count())
    ]


def _dialog(notes, tasks=(), commands=()):
    return QuickOpenDialog(str(notes), None, commands=list(commands), tasks=list(tasks))


def test_notes_come_first(qapp, notes, tasks):
    dialog = _dialog(notes, tasks, [("Settings", "Ctrl+,", lambda: None)])
    assert _rows(dialog)[0] == "Notes"
    dialog.deleteLater()


def test_all_three_groups_appear(qapp, notes, tasks):
    dialog = _dialog(notes, tasks, [("Settings", "Ctrl+,", lambda: None)])
    headings = [r for r in _rows(dialog) if r in ("Notes", "Open tasks", "Commands")]
    assert headings == ["Notes", "Open tasks", "Commands"]
    dialog.deleteLater()


def test_an_empty_group_is_left_out_entirely(qapp, notes):
    dialog = _dialog(notes)
    assert "Open tasks" not in _rows(dialog)
    assert "Commands" not in _rows(dialog)
    dialog.deleteLater()


def test_headings_are_not_selectable(qapp, notes, tasks):
    dialog = _dialog(notes, tasks, [("Settings", "Ctrl+,", lambda: None)])
    for index in range(dialog.results.count()):
        item = dialog.results.item(index)
        if item.text() in ("Notes", "Open tasks", "Commands"):
            assert item.data(Qt.ItemDataRole.UserRole) is None
            assert item.flags() == Qt.ItemFlag.NoItemFlags
    dialog.deleteLater()


def test_the_first_selected_row_is_never_a_heading(qapp, notes, tasks):
    dialog = _dialog(notes, tasks)
    assert _payloads(dialog)[dialog.results.currentRow()] is not None
    dialog.deleteLater()


def test_arrowing_down_skips_over_a_heading(qapp, notes, tasks):
    dialog = _dialog(notes, tasks, [("Settings", "Ctrl+,", lambda: None)])
    seen = set()
    row = dialog.results.currentRow()
    for _ in range(dialog.results.count()):
        row = dialog._step(row, 1)
        seen.add(row)
    assert all(_payloads(dialog)[r] is not None for r in seen)
    dialog.deleteLater()


def test_a_query_filters_commands_too(qapp, notes, tasks):
    commands = [
        ("Settings", "Ctrl+,", lambda: None),
        ("Toggle sidebar", "Ctrl+Shift+B", lambda: None),
    ]
    dialog = _dialog(notes, tasks, commands)
    dialog._refresh("sidebar")
    labels = _rows(dialog)
    assert any("Toggle sidebar" in text for text in labels)
    assert not any("Settings" in text for text in labels)
    dialog.deleteLater()


def test_a_query_filters_tasks_too(qapp, notes, tasks):
    dialog = _dialog(notes, tasks)
    dialog._refresh("فاکتور")
    assert any("فاکتور" in text for text in _rows(dialog))
    dialog._refresh("nothing-matches-this")
    assert "Open tasks" not in _rows(dialog)
    dialog.deleteLater()


def test_choosing_a_task_reports_its_line(qapp, notes, tasks):
    dialog = _dialog(notes, tasks)
    seen = []
    dialog.task_chosen.connect(lambda p, line: seen.append((p, line)))
    row = next(
        i
        for i in range(dialog.results.count())
        if (dialog.results.item(i).data(Qt.ItemDataRole.UserRole) or ("",))[0] == "task"
    )
    dialog._choose(dialog.results.item(row))
    assert seen == [(tasks[0].path, tasks[0].line_number)]


def test_choosing_a_command_runs_it(qapp, notes):
    fired = []
    dialog = _dialog(notes, (), [("Settings", "Ctrl+,", lambda: fired.append(1))])
    row = next(
        i
        for i in range(dialog.results.count())
        if (dialog.results.item(i).data(Qt.ItemDataRole.UserRole) or ("",))[0]
        == "command"
    )
    dialog._choose(dialog.results.item(row))
    assert fired == [1]


def test_a_heading_click_does_nothing(qapp, notes, tasks):
    dialog = _dialog(notes, tasks)
    seen = []
    dialog.note_chosen.connect(seen.append)
    dialog._choose(dialog.results.item(0))  # the "Notes" heading
    assert seen == []
    dialog.deleteLater()


def test_the_count_line_still_talks_about_notes(qapp, notes, tasks):
    dialog = _dialog(notes, tasks)
    assert dialog.hint.text() == "2 notes"
    dialog.deleteLater()
