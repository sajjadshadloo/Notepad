from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QKeyEvent, QTextCursor

from core.rtl_detector import _RTL_RE, detect_direction, is_rtl_char
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


def test_direction_honours_the_callers_default():
    """The sidebar asks with default='ltr'; only strong characters override it."""
    assert detect_direction("", default="ltr") == "ltr"
    assert detect_direction("2024-01-01", default="ltr") == "ltr"
    assert detect_direction("2024-01-01", default="rtl") == "rtl"
    # The Arabic comma is a neutral separator, so it cannot override either.
    assert detect_direction("،", default="ltr") == "ltr"
    assert detect_direction("،", default="rtl") == "rtl"
    # The Arabic semicolon and question mark, by contrast, are strong RTL.
    assert detect_direction("؟", default="ltr") == "rtl"


def test_rtl_prescan_covers_every_right_to_left_character():
    """The regex fast path is only sound if it never misses an RTL character.

    A miss would make detect_direction skip counting entirely and report the
    caller's default, so this guards the one assumption the fast path makes.
    """
    import sys
    import unicodedata

    for code_point in range(sys.maxunicode + 1):
        char = chr(code_point)
        if unicodedata.bidirectional(char) in ("R", "AL", "AN"):
            assert _RTL_RE.search(char) is not None, hex(code_point)


def test_non_latin_left_to_right_scripts_are_detected():
    """Cyrillic and CJK are strong LTR even though they are not ASCII."""
    assert detect_direction("Привет мир") == "ltr"
    assert detect_direction("日本語のテキスト") == "ltr"


def test_digits_never_force_a_direction():
    """Neither ASCII nor Persian digits are strong characters.

    Persian digits U+06F0–U+06F9 are bidi class EN, not AN — only the Arabic
    set U+0660–U+0669 is AN — so a line of numbers keeps the caller's default
    whichever digits it is written with.
    """
    assert not is_rtl_char("4")
    assert not is_rtl_char("۴")
    assert is_rtl_char("٤")  # U+0664, the Arabic-Indic four, really is AN
    assert detect_direction("۱۲۳۴", default="rtl") == "rtl"
    assert detect_direction("۱۲۳۴", default="ltr") == "ltr"
    assert detect_direction("١٢٣٤", default="ltr") == "rtl"


def test_editor_applies_direction_per_paragraph(qapp):
    editor = SmartEditor()
    editor.setPlainText("سلام\nHello")
    qapp.processEvents()

    first = editor.document().begin()
    second = first.next()

    assert first.blockFormat().layoutDirection() == Qt.LayoutDirection.RightToLeft
    assert second.blockFormat().layoutDirection() == Qt.LayoutDirection.LeftToRight


def _layouts(editor) -> list:
    directions = []
    block = editor.document().begin()
    while block.isValid():
        directions.append(block.blockFormat().layoutDirection())
        block = block.next()
    return directions


RTL = Qt.LayoutDirection.RightToLeft
LTR = Qt.LayoutDirection.LeftToRight


def test_incremental_pass_reflows_only_the_edited_paragraph(qapp):
    """Typing re-evaluates the edited paragraph and leaves the rest alone."""
    editor = SmartEditor()
    editor.setPlainText("سلام\nHello\nدرود")
    qapp.processEvents()
    assert _layouts(editor) == [RTL, LTR, RTL]

    # Turn the middle (English) paragraph into a Persian one.
    cursor = editor.textCursor()
    cursor.setPosition(editor.document().findBlockByNumber(1).position())
    cursor.movePosition(
        QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor
    )
    cursor.insertText("سلام دنیا")
    editor._refresh_layout()

    assert _layouts(editor) == [RTL, RTL, RTL]


def test_deleting_across_paragraphs_keeps_directions_correct(qapp):
    """A removal reports characters that no longer exist; the dirty range
    must stay inside the document or the pass silently skips every block."""
    editor = SmartEditor()
    editor.setPlainText("Hello\nthere\nسلام")
    qapp.processEvents()

    document = editor.document()
    cursor = editor.textCursor()
    cursor.setPosition(document.findBlockByNumber(1).position())
    cursor.setPosition(
        document.findBlockByNumber(2).position() + 4,
        QTextCursor.MoveMode.KeepAnchor,
    )
    cursor.removeSelectedText()
    editor._refresh_layout()

    # "there\nسلام" collapsed into a single Persian remainder.
    assert _layouts(editor) == [LTR, RTL]


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


def test_default_mode_keeps_the_whole_document_right_to_left(qapp):
    """The point of the RTL default: an English line inside a Persian note
    must not flip the document's alignment mid-page."""
    editor = SmartEditor()
    editor.set_direction_mode("rtl")
    editor.setPlainText("سلام\nHello world\n123\nمتن دیگر")
    qapp.processEvents()

    assert _layouts(editor) == [RTL, RTL, RTL, RTL]


def test_switching_to_ltr_moves_every_paragraph(qapp):
    """Ctrl + left Shift is a document-wide switch, not a per-line one."""
    editor = SmartEditor()
    editor.set_direction_mode("rtl")
    editor.setPlainText("سلام\nHello\nدرود")
    qapp.processEvents()
    assert _layouts(editor) == [RTL, RTL, RTL]

    editor.set_direction_mode("ltr")
    qapp.processEvents()
    assert _layouts(editor) == [LTR, LTR, LTR]
