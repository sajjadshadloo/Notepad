from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QKeyEvent

from core.rtl_detector import detect_direction
from ui.editor import SmartEditor


def test_direction_detection_defaults_empty_to_rtl():
    assert detect_direction("") == "rtl"
    assert detect_direction("سلام") == "rtl"
    assert detect_direction("Hello") == "ltr"
    assert detect_direction("  123") == "rtl"


def test_direction_detection_uses_majority_for_mixed_text():
    # Starts with an English label but is mostly Persian -> should stay rtl,
    # not flip ltr just because the first strong character is Latin.
    assert detect_direction("Project: این یک جمله طولانی فارسی است") == "rtl"
    # Mostly English with a single trailing Persian word -> stays ltr.
    assert detect_direction("This is a long English sentence پروژه") == "ltr"
    # Roughly balanced mixed text with an RTL-leaning tie defaults to rtl.
    assert detect_direction("Hi سلام") == "rtl"


def test_editor_applies_direction_per_paragraph(qapp):
    editor = SmartEditor()
    editor.setPlainText("سلام\nHello")
    qapp.processEvents()

    first = editor.document().begin()
    second = first.next()

    assert first.blockFormat().layoutDirection() == Qt.LayoutDirection.RightToLeft
    assert second.blockFormat().layoutDirection() == Qt.LayoutDirection.LeftToRight


def test_empty_document_starts_rtl(qapp):
    editor = SmartEditor()
    editor.setPlainText("")

    assert editor.current_direction() == "rtl"


def test_rtl_is_visually_aligned_to_right(qapp):
    editor = SmartEditor()
    editor.resize(800, 300)
    editor.show()
    editor.setPlainText("سلام")
    qapp.processEvents()
    cursor = editor.textCursor()
    cursor.setPosition(0)
    editor.setTextCursor(cursor)

    assert editor.cursorRect().x() > editor.viewport().width() // 2


def _ctrl_shift_event(scan_code: int) -> QKeyEvent:
    return QKeyEvent(
        QEvent.Type.KeyPress,
        Qt.Key.Key_Shift,
        Qt.KeyboardModifier.ControlModifier,
        scan_code,
        0,
        0,
    )


def test_direction_shortcuts(qapp):
    """Ctrl + left/right Shift switches direction (Windows convention)."""
    editor = SmartEditor()
    editor.show()

    editor.keyPressEvent(_ctrl_shift_event(42))  # left Shift
    assert editor.direction_mode == "ltr"

    editor.keyPressEvent(_ctrl_shift_event(54))  # right Shift
    assert editor.direction_mode == "rtl"

    assert SmartEditor.direction_for_shift_scancode(99) is None


def test_code_blocks_are_ltr_in_auto_mode(qapp):
    editor = SmartEditor()
    editor.setPlainText("```\nprint('hello')\n```")
    qapp.processEvents()

    block = editor.document().begin()
    while block.isValid():
        assert block.blockFormat().layoutDirection() == Qt.LayoutDirection.LeftToRight
        block = block.next()
