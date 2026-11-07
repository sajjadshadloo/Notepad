"""Editing a table the way a person does: click a cell, type, Tab on.

The file never changes shape except through these edits, and every edit is
one Ctrl+Z.
"""
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtCore import QEvent

from ui.document_tab import DocumentTab

TABLE = (
    "متن بالا\n"
    "\n"
    "| پروژه | وضعیت |\n"
    "| --- | --- |\n"
    "| ایونت | فعال |\n"
    "| هورگل | شروع |\n"
    "\n"
    "متن پایین\n"
)


@pytest.fixture
def tab(qapp):
    widget = DocumentTab(text=TABLE)
    widget.resize(900, 700)
    widget.show()
    for _ in range(5):
        qapp.processEvents()
    yield widget
    widget.editor.tables.commit()
    widget.mark_clean()
    widget.close()
    widget.deleteLater()


def _lines(tab):
    return tab.editor.toPlainText().split("\n")


def _block(tab, line):
    return tab.editor.document().findBlockByNumber(line)


def test_showing_a_table_does_not_touch_the_text(tab):
    assert tab.editor.toPlainText() == TABLE.rstrip("\n") or tab.editor.toPlainText() == TABLE
    assert not tab.editor.document().isModified()


def test_a_cell_edit_rewrites_only_that_cell(tab):
    tables = tab.editor.tables
    tables.open_cell(4, 1)
    tables.edit.setText("تحویل شد")
    tables.commit()
    assert _lines(tab)[4] == "| ایونت | تحویل شد |"
    assert _lines(tab)[5] == "| هورگل | شروع |"


def test_opening_and_leaving_a_cell_unchanged_edits_nothing(tab):
    tables = tab.editor.tables
    revision = tab.editor.document().revision()
    tables.open_cell(4, 0)
    tables.commit()
    assert not tab.editor.document().isModified()
    assert tab.editor.document().revision() == revision


def test_a_cell_edit_is_one_undo_step(tab):
    tables = tab.editor.tables
    tables.open_cell(4, 1)
    tables.edit.setText("جدید")
    tables.commit()
    tab.editor.undo()
    assert _lines(tab)[4] == "| ایونت | فعال |"


def test_tab_moves_to_the_next_cell_and_saves_the_one_it_left(tab):
    tables = tab.editor.tables
    tables.open_cell(4, 0)
    tables.edit.setText("تازه")
    tables._on_move("next")
    assert _lines(tab)[4] == "| تازه | فعال |"
    assert tables._target == (4, 1)


def test_tab_in_the_last_cell_adds_a_row(tab):
    tables = tab.editor.tables
    tables.open_cell(5, 1)
    tables._on_move("next")
    assert _lines(tab)[6] == "|  |  |"
    assert tables._target == (6, 0)


def test_the_separator_row_cannot_be_entered(tab):
    tables = tab.editor.tables
    tables.open_cell(3, 0)
    assert tables._target is None


def test_a_pipe_typed_in_a_cell_does_not_split_it(tab):
    tables = tab.editor.tables
    tables.open_cell(4, 0)
    tables.edit.setText("a|b")
    tables.commit()
    assert _lines(tab)[4].count("|") == 3


def test_typing_while_the_cursor_sits_in_a_table_opens_the_cell(tab):
    from PyQt6.QtGui import QTextCursor

    editor = tab.editor
    cursor = QTextCursor(_block(tab, 4))
    editor.setTextCursor(cursor)
    editor.setFocus()
    before = editor.toPlainText()
    event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_A, Qt.KeyboardModifier.NoModifier, "a")
    editor.keyPressEvent(event)
    assert editor.toPlainText() == before, "hidden text must not be edited"


def test_inserting_a_table_adds_header_separator_and_rows(qapp):
    widget = DocumentTab(text="")
    widget.resize(800, 600)
    widget.show()
    widget.editor.tables.insert_table(3, 2)
    for _ in range(5):
        qapp.processEvents()
    lines = widget.editor.toPlainText().split("\n")
    assert sum(1 for line in lines if line.startswith("|")) == 4
    widget.editor.tables.commit()
    widget.mark_clean()
    widget.close()
    widget.deleteLater()


def test_deleting_a_row_removes_just_that_line(tab):
    tab.editor.tables.delete_row(_block(tab, 4))
    assert "ایونت" not in tab.editor.toPlainText()
    assert "هورگل" in tab.editor.toPlainText()


def test_the_header_row_cannot_be_deleted(tab):
    before = tab.editor.toPlainText()
    tab.editor.tables.delete_row(_block(tab, 2))
    assert tab.editor.toPlainText() == before


def test_adding_a_column_widens_every_row(tab):
    tab.editor.tables.add_column(_block(tab, 4))
    rows = [l for l in _lines(tab) if l.startswith("|")]
    assert {l.count("|") for l in rows} == {4}


def test_rules_and_code_leave_the_text_alone(qapp):
    text = "---\n`a.com`\n"
    widget = DocumentTab(text=text)
    widget.resize(600, 400)
    widget.show()
    for _ in range(3):
        qapp.processEvents()
    assert widget.editor.toPlainText() == text
    widget.mark_clean()
    widget.close()
    widget.deleteLater()


def test_the_format_bar_has_a_table_button_that_inserts_one(qapp, tmp_path, monkeypatch):
    from core import settings_manager
    from ui.kit import Button
    from ui.main_window import MainWindow

    data = tmp_path / "appdata"
    data.mkdir()
    monkeypatch.setattr(settings_manager, "app_data_dir", lambda: data)
    window = MainWindow([])
    tips = [b.toolTip() for b in window.format_bar.findChildren(Button)]
    assert "جدول — Ctrl+Alt+T" in tips

    window.new_document()
    window.table_action.trigger()
    for _ in range(3):
        qapp.processEvents()
    text = window.current_document().editor.toPlainText()
    assert sum(1 for line in text.split("\n") if line.startswith("|")) == 4

    window.current_document().editor.tables.commit()
    for index in range(window.tabs.count()):
        window.tabs.widget(index).mark_clean()
    window._really_quitting = True
    window.close()
    window.deleteLater()
