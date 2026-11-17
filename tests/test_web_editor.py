"""The Python side of the web editor, without starting a browser.

``headless=True`` skips the web engine, so these check what Python does with
the page's reports and with edits made on the shadow document — the part the
rest of the app depends on.
"""
import pytest
from PyQt6.QtGui import QTextCursor

from ui.web_editor import WebEditor


@pytest.fixture
def editor(qapp):
    widget = WebEditor(headless=True)
    yield widget
    widget.deleteLater()


def test_opening_a_note_sets_the_shadow_and_tells_the_page(editor):
    editor.setPlainText("اول\nدوم\n")
    assert editor.toPlainText() == "اول\nدوم\n"
    assert editor.document().blockCount() == 3
    assert any("open" in code for code in editor.sent)


def test_a_change_reported_by_the_page_updates_the_text_and_marks_modified(editor):
    editor.setPlainText("اول\n")
    editor.document().setModified(False)
    seen = []
    editor.textChanged.connect(lambda: seen.append(1))
    editor._on_text("اول\nدوم\n")
    assert editor.toPlainText() == "اول\nدوم\n"
    assert editor.document().isModified()
    assert seen


def test_the_page_echoing_the_same_text_is_not_a_change(editor):
    editor.setPlainText("اول\n")
    editor.document().setModified(False)
    editor._on_text("اول\n")
    assert not editor.document().isModified()


def test_an_edit_on_the_shadow_document_goes_to_the_page(editor):
    """Tasks written back from the rail, dates, replace-all: all edit the shadow."""
    editor.setPlainText("- [ ] کار\n")
    editor.sent.clear()
    cursor = QTextCursor(editor.document().findBlockByNumber(0))
    cursor.select(QTextCursor.SelectionType.LineUnderCursor)
    cursor.insertText("- [x] کار")
    assert editor.toPlainText() == "- [x] کار\n"
    assert any("replace" in code and "[x]" in code for code in editor.sent)


def test_the_text_cursor_follows_the_line_the_page_reports(editor):
    editor.setPlainText("اول\nدوم\nسوم\n")
    editor._on_cursor(2, 3, 0, 1)
    cursor = editor.textCursor()
    assert cursor.blockNumber() == 1
    assert cursor.block().text() == "دوم"


def test_moving_the_text_cursor_scrolls_the_page_to_that_line(editor):
    editor.setPlainText("اول\nدوم\nسوم\n")
    editor.sent.clear()
    editor.setTextCursor(QTextCursor(editor.document().findBlockByNumber(2)))
    assert any("goToLine(3)" in code for code in editor.sent)


def test_find_uses_the_shadow_and_the_match_becomes_the_selection(editor):
    editor.setPlainText("سیب موز سیب\n")
    assert editor.find("سیب")
    assert editor.textCursor().selectedText() == "سیب"
    first = editor.textCursor().selectionStart()
    assert editor.find("سیب")
    assert editor.textCursor().selectionStart() > first
    assert not editor.find("هلو")


def test_formatting_commands_become_calls_on_the_page(editor):
    editor.sent.clear()
    editor.command("bold")
    editor.command("insertText", "@۱۴۰۵/۰۸/۲۶ ")
    assert 'cmd("bold")' in editor.sent[0]
    assert "insertText" in editor.sent[1] and "@" in editor.sent[1]


def test_the_theme_arrives_as_the_pages_variables(editor):
    editor.sent.clear()
    editor.apply_palette({
        "window": "#111111", "text": "#eeeeee", "muted": "#999999", "border": "#222222",
        "hover": "#333333", "accent": "#6cb6ff", "danger": "#ff0000",
    })
    code = editor.sent[0]
    assert '"bg": "#111111"' in code and '"accent": "#6cb6ff"' in code


def test_direction_modes(editor):
    editor.set_direction_mode("ltr")
    assert editor.current_direction() == "ltr"
    editor.set_direction_mode("auto")
    assert editor.current_direction() == "rtl"
