"""The reading view: a note as a finished page, the file left alone."""
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QTextDocument

from ui.document_tab import DocumentTab, editor_font
from ui.reader_view import DONE_BOX, OPEN_BOX, ReaderView, prepare

NOTE = """# لینکدین

**وضعیت:** فعال
**هدف:** یه پروفایل درست

| کار | وضعیت |
| --- | --- |
| سلتا | زنده |

- [ ] هدلاین جدید
- [x] خواندن پروفایل

ببین [[selta|سلتا]] و `Projects/selta.md`
"""


def _font():
    return editor_font("Inter", "Vazirmatn", 14.5)


def _table_rows(view: ReaderView) -> list[list[str]]:
    table = next(view._tables(view.document().rootFrame()))
    return [
        [table.cellAt(row, col).firstCursorPosition().block().text()
         for col in range(table.columns())]
        for row in range(table.rows())
    ]


def test_lines_written_one_under_another_stay_that_way(qapp):
    """Markdown would join «**وضعیت:**» and «**هدف:**» into one paragraph;
    the editor shows them as two lines, so the page must too."""
    view = ReaderView()
    view.render(NOTE, _font())

    texts = []
    block = view.document().begin()
    while block.isValid():
        texts.append(block.text())
        block = block.next()
    status = next(t for t in texts if t.startswith("وضعیت"))
    assert "هدف" not in status


def test_a_right_to_left_table_starts_on_the_right(qapp):
    """Qt lays a table out left-to-right whatever it is told, so a Persian
    table reaches it with its columns reversed: «کار» ends up rightmost."""
    view = ReaderView()
    view.render(NOTE, _font(), "rtl")
    assert _table_rows(view) == [["وضعیت", "کار"], ["زنده", "سلتا"]]

    view.render("| a | b |\n| --- | --- |\n| 1 | 2 |", _font(), "ltr")
    assert _table_rows(view) == [["a", "b"], ["1", "2"]]


def test_a_table_after_a_code_block_has_no_empty_first_line(qapp):
    view = ReaderView()
    view.render("```\ncode\n```\n\n| الف | ب |\n| --- | --- |\n| ۱ | ۲ |",
                _font())
    table = next(view._tables(view.document().rootFrame()))
    for col in range(table.columns()):
        cell = table.cellAt(0, col)
        assert cell.firstCursorPosition().block() == cell.lastCursorPosition().block()


def test_tasks_become_boxes_and_a_finished_one_is_struck_through(qapp):
    text = prepare("- [ ] باز\n- [x] تمام")
    assert "[ ]" not in text and "[x]" not in text
    assert "~~تمام~~" in text

    view = ReaderView()
    view.render("- [ ] باز\n- [x] تمام", _font())
    states = []
    block = view.document().begin()
    while block.isValid():
        state = view._task_state(block)
        if state:
            states.append(state)
            assert view.document().resource(
                QTextDocument.ResourceType.ImageResource.value, QUrl(state)
            ) is not None
        block = block.next()
    assert states == [OPEN_BOX, DONE_BOX]


def test_a_note_link_is_followed_like_one_in_the_editor(qapp):
    assert "[سلتا](note:selta)" in prepare("ببین [[selta|سلتا]]")

    view = ReaderView()
    seen = []
    view.link_clicked.connect(seen.append)
    view._follow(QUrl("note:" + QUrl.toPercentEncoding("سلتا").data().decode()))
    assert seen == ["سلتا"]


def test_code_fences_are_left_as_written(qapp):
    source = "```\n- [ ] not a task\n[[not a link]]\n```"
    assert prepare(source) == source


def test_reading_never_changes_the_note(qapp):
    tab = DocumentTab(text=NOTE)
    assert not tab.reading

    tab.set_reading(True)
    assert tab.reading
    assert tab.pages.currentWidget() is tab.reader
    assert tab.text == NOTE
    assert not tab.modified

    tab.set_reading(False)
    assert not tab.reading
    assert tab.pages.currentWidget() is tab.editor
    assert tab.text == NOTE
    assert not tab.modified


def test_the_page_follows_a_change_made_while_reading(qapp):
    """Ctrl+D or a file changed outside the app edits the text while the
    page is up; the page catches up instead of showing the old note."""
    tab = DocumentTab(text="# قدیمی")
    tab.set_reading(True)
    tab.editor.setPlainText("# جدید")
    tab._reader_timer.timeout.emit()
    assert "جدید" in tab.reader.toPlainText()


def test_ctrl_e_switches_the_window_into_reading(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("NOTEPAD_DATA_DIR", str(tmp_path / "appdata"))
    from ui.main_window import MainWindow

    window = MainWindow([])
    window._recovery_timer.stop()
    tab = window.current_document()
    tab.editor.setPlainText(NOTE)
    tab.mark_clean()

    window.reading_action.trigger()
    assert tab.reading
    assert window.format_bar.reading_button.isChecked()
    assert not any(b.isEnabled() for b in window.format_bar._editing_buttons)

    # Search needs the editor on screen.
    window.show_find_dialog()
    assert not tab.reading
    assert not window.format_bar.reading_button.isChecked()
    assert all(b.isEnabled() for b in window.format_bar._editing_buttons)
    window._find_dialog.hide()
    tab.mark_clean()
