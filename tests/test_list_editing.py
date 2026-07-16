from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QTextCursor
from PyQt6.QtTest import QTest

from core.list_editing import (
    display_number_marker,
    indent_list_line,
    outdent_list_line,
    parse_list_item,
)
from ui.editor import SmartEditor
from ui.editor import NUMBERED_LIST_GUTTER, NUMBERED_MARKER_EDGE


def _editor_at_end(qapp, text: str) -> SmartEditor:
    editor = SmartEditor()
    editor.setPlainText(text)
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    editor.setTextCursor(cursor)
    editor.document().clearUndoRedoStacks()
    return editor


def test_parse_all_list_kinds():
    bullet = parse_list_item("  - item")
    assert bullet and bullet.kind == "bullet"
    assert bullet.continuation_prefix() == "  - "

    todo = parse_list_item("- [x] done")
    assert todo and todo.kind == "todo" and todo.checked
    assert todo.continuation_prefix() == "- [ ] "

    numbered = parse_list_item("9. item")
    assert numbered and numbered.kind == "numbered"
    assert numbered.continuation_prefix() == "10. "


def test_display_number_marker_uses_persian_digits_in_rtl():
    """RTL shows Persian digits with the dot visually to the LEFT of the
    digit (LTR paint run of «.۱») — Persian reading order; the document
    keeps ASCII digits. User-confirmed in 2.5.0: dot on the right is wrong."""
    assert display_number_marker("12.", rtl=True) == ".۱۲"
    assert display_number_marker("12.", rtl=False) == "12."
    assert display_number_marker("3)", rtl=True) == ")۳"


def test_indent_and_outdent_only_list_lines():
    assert indent_list_line("- item") == "  - item"
    assert outdent_list_line("  - item") == "- item"
    assert indent_list_line("plain") == "plain"
    assert outdent_list_line("plain") == "plain"


def test_enter_continues_bullet(qapp):
    editor = _editor_at_end(qapp, "- item")
    QTest.keyClick(editor, Qt.Key.Key_Return)
    assert editor.toPlainText() == "- item\n- "


def test_enter_continues_todo_unchecked(qapp):
    editor = _editor_at_end(qapp, "- [x] finished")
    QTest.keyClick(editor, Qt.Key.Key_Return)
    assert editor.toPlainText() == "- [x] finished\n- [ ] "


def test_enter_increments_numbered_list(qapp):
    editor = _editor_at_end(qapp, "9. item")
    QTest.keyClick(editor, Qt.Key.Key_Return)
    assert editor.toPlainText() == "9. item\n10. "


def test_enter_on_empty_item_exits_list(qapp):
    editor = _editor_at_end(qapp, "- item\n- ")
    QTest.keyClick(editor, Qt.Key.Key_Return)
    assert editor.toPlainText() == "- item\n\n"
    assert editor.textCursor().blockNumber() == 2


def test_plain_enter_advances_from_an_empty_paragraph(qapp):
    editor = _editor_at_end(qapp, "paragraph\n")

    QTest.keyClick(editor, Qt.Key.Key_Return)

    assert editor.toPlainText() == "paragraph\n\n"
    assert editor.textCursor().blockNumber() == 2


def test_exit_from_empty_list_is_one_undo_step(qapp):
    editor = _editor_at_end(qapp, "- item\n- ")

    QTest.keyClick(editor, Qt.Key.Key_Return)
    editor.undo()

    assert editor.toPlainText() == "- item\n- "


def test_tab_and_backtab_change_list_indent(qapp):
    editor = _editor_at_end(qapp, "- item")
    QTest.keyClick(editor, Qt.Key.Key_Tab)
    assert editor.toPlainText() == "  - item"
    QTest.keyClick(editor, Qt.Key.Key_Backtab)
    assert editor.toPlainText() == "- item"


def test_backspace_removes_empty_marker(qapp):
    editor = _editor_at_end(qapp, "- [ ] ")
    QTest.keyClick(editor, Qt.Key.Key_Backspace)
    assert editor.toPlainText() == ""


def test_list_continuation_is_one_undo_step(qapp):
    editor = _editor_at_end(qapp, "- item")
    QTest.keyClick(editor, Qt.Key.Key_Return)
    editor.undo()
    assert editor.toPlainText() == "- item"


def test_checked_todo_direction_comes_from_body_not_x_marker(qapp):
    editor = SmartEditor()
    assert editor._direction_for_text("- [x] کار انجام شد") == "rtl"
    assert editor._direction_for_text("- [x] task done") == "ltr"


def _laid_out_editor(qapp, text: str) -> SmartEditor:
    """Editor with real geometry.

    cursorRect() only returns meaningful coordinates once the widget has
    been shown and laid out; before that every marker rect collapses to the
    origin and geometry assertions are meaningless.
    """
    editor = _editor_at_end(qapp, text)
    editor.resize(600, 400)
    editor.show()
    qapp.processEvents()
    editor.apply_directions()
    editor._invalidate_marker_cache()
    return editor


def _markers_of(editor) -> list:
    editor._invalidate_marker_cache()
    return list(editor._visible_list_markers())


def test_marker_rect_is_positive_width_in_both_directions(qapp):
    """The marker rect is measured from both visual edges.

    Using only cursorRect().left() collapsed the rect in RTL paragraphs,
    which left the checkbox unclickable and painted off-position.
    """
    editor = _laid_out_editor(qapp, "- [ ] task done\n- [ ] کار انجام نشده")

    markers = _markers_of(editor)
    assert len(markers) == 2
    for _block, item, rect in markers:
        assert item.kind == "todo"
        assert rect.width() > 0
        assert rect.height() > 0


def test_rtl_marker_sits_on_the_right_of_the_ltr_one(qapp):
    """An RTL item's marker is painted at the right edge of the viewport."""
    editor = _laid_out_editor(qapp, "- [ ] task\n- [ ] کار")

    markers = _markers_of(editor)
    ltr_rect = markers[0][2]
    rtl_rect = markers[1][2]
    assert rtl_rect.left() > ltr_rect.left()
    assert rtl_rect.left() > editor.viewport().width() // 2


def test_rtl_number_markers_share_one_fixed_column(qapp):
    editor = _laid_out_editor(qapp, "1. کوتاه\n2. کمی طولانی‌تر\n3. متن")

    markers = _markers_of(editor)
    rects = [rect for _block, item, rect in markers if item.kind == "numbered"]

    assert len(rects) == 3
    assert len({rect.left() for rect in rects}) == 1
    assert len({rect.width() for rect in rects}) == 1
    assert all(rect.left() >= 0 for rect in rects)
    assert all(rect.right() < editor.viewport().width() for rect in rects)
    for block, item, rect in markers:
        prefix = QTextCursor(block)
        prefix.setPosition(block.position() + item.prefix_end)
        assert rect.left() > editor.cursorRect(prefix).right()
        assert block.blockFormat().rightMargin() == NUMBERED_LIST_GUTTER
    assert rects[0].right() == editor.viewport().width() - NUMBERED_MARKER_EDGE - 1


def test_rtl_number_column_stays_on_right_when_editor_width_changes(qapp):
    editor = _laid_out_editor(qapp, "1. کوتاه\n2. یک متن بسیار طولانی‌تر")

    for width in (320, 760):
        editor.resize(width, 300)
        qapp.processEvents()
        editor.apply_directions()
        rects = [rect for _block, _item, rect in _markers_of(editor)]
        assert len({rect.left() for rect in rects}) == 1
        assert rects[0].right() == editor.viewport().width() - NUMBERED_MARKER_EDGE - 1
        assert rects[0].left() > editor.viewport().width() // 2


def test_checkbox_hit_test_finds_painted_box(qapp):
    editor = _laid_out_editor(qapp, "- [ ] task")

    _block, _item, rect = _markers_of(editor)[0]
    assert editor._checkbox_at(rect.center()) is not None
    far_away = rect.center() + QPoint(400, 0)
    assert editor._checkbox_at(far_away) is None


def test_checkbox_click_toggles_in_one_undo_step(qapp):
    editor = _laid_out_editor(qapp, "- [ ] task")

    _block, _item, rect = _markers_of(editor)[0]
    toggle = editor._checkbox_at(rect.center())
    toggle.beginEditBlock()
    toggle.insertText("x")
    toggle.endEditBlock()
    assert editor.toPlainText() == "- [x] task"
    editor.undo()
    assert editor.toPlainText() == "- [ ] task"


def test_rtl_checkbox_is_clickable(qapp):
    """A Persian to-do toggles from a click on its right-hand checkbox."""
    editor = _laid_out_editor(qapp, "- [ ] کار")

    _block, _item, rect = _markers_of(editor)[0]
    toggle = editor._checkbox_at(rect.center())
    assert toggle is not None
    assert toggle.selectedText() == " "
    toggle.insertText("x")
    assert editor.toPlainText() == "- [x] کار"


def test_markers_render_without_preview_highlighter(qapp):
    """Markers are painted even when no highlighter is attached.

    paintEvent used to return early when markdown_highlighter was None,
    so a tab without the preview pane showed raw '- [ ]' text instead.
    """
    editor = _laid_out_editor(qapp, "- [ ] task")
    assert editor.markdown_highlighter is None
    assert len(_markers_of(editor)) == 1


def test_marker_cache_is_dropped_when_text_changes(qapp):
    editor = _laid_out_editor(qapp, "- [ ] task")
    assert len(list(editor._visible_list_markers())) == 1
    editor.setPlainText("- [ ] task\n- [ ] second")
    # No manual invalidation: textChanged must drop the cache on its own.
    assert len(list(editor._visible_list_markers())) == 2
