"""The date button on a line that is not a task, and the numbered-list button."""
from datetime import date

import pytest
from PyQt6.QtGui import QTextCursor

from core import settings_manager
from ui.main_window import MainWindow


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    data = tmp_path / "appdata"
    data.mkdir()
    monkeypatch.setattr(settings_manager, "app_data_dir", lambda: data)
    win = MainWindow([])
    win.new_document()
    yield win
    for index in range(win.tabs.count()):
        win.tabs.widget(index).mark_clean()
    win._really_quitting = True
    win.close()
    win.deleteLater()


def _type(window, text, line=0):
    editor = window.current_document().editor
    editor.setPlainText(text)
    cursor = QTextCursor(editor.document().findBlockByNumber(line))
    cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
    editor.setTextCursor(cursor)
    return editor


def test_a_date_on_an_empty_line_makes_no_checkbox(window):
    editor = _type(window, "")
    window._apply_chosen_date(date(2026, 11, 7))
    text = editor.toPlainText().strip()
    assert text.startswith("@")
    assert "[ ]" not in text and not text.startswith("-")


def test_a_date_on_plain_text_stays_plain(window):
    editor = _type(window, "جلسه با کارفرما")
    window._apply_chosen_date(date(2026, 11, 7))
    text = editor.toPlainText()
    assert "جلسه با کارفرما" in text and "@" in text
    assert "- [ ]" not in text


def test_a_date_on_a_task_is_still_its_deadline(window):
    editor = _type(window, "- [ ] تحویل دمو")
    window._apply_chosen_date(date(2026, 11, 7))
    assert editor.toPlainText().startswith("- [ ] تحویل دمو")
    assert "@" in editor.toPlainText()


def test_choosing_again_replaces_the_date_instead_of_adding_one(window):
    editor = _type(window, "")
    window._apply_chosen_date(date(2026, 11, 7))
    window._apply_chosen_date(date(2026, 11, 9))
    assert editor.toPlainText().count("@") == 1


def test_the_numbered_button_numbers_the_line(window):
    editor = _type(window, "اول")
    window.format_bar.numbered.emit()
    assert editor.toPlainText().startswith("1. ")


def test_the_reading_view_is_gone(window):
    """4.7.3 dropped it: the editor itself is the finished page."""
    from ui.kit import Button

    labels = [b.toolTip() for b in window.format_bar.findChildren(Button)]
    assert not any("خواندن" in label for label in labels)
    assert not hasattr(window, "reading_action")
    assert not hasattr(window.current_document(), "set_reading")


def test_new_notes_use_the_full_width_by_default(window):
    assert window.current_document().editor.is_full_width()
