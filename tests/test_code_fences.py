"""Only an explicit ``` fence marks code now.

Before 3.1 the editor guessed at unfenced code with a stack of regexes. It
scanned the whole document on every keystroke, and it misread ordinary notes
— anything with a colon, a bracket or an equals sign — as code, which forced
those paragraphs left-to-right in a right-to-left document.
"""
from PyQt6.QtCore import Qt

from ui.editor import SmartEditor, fenced_code_lines


def test_fence_marks_its_own_lines_and_nothing_else():
    text = "متن\n```python\nprint('hi')\n```\nادامه"
    assert fenced_code_lines(text) == {1, 2, 3}


def test_unclosed_fence_runs_to_the_end():
    assert fenced_code_lines("a\n```\nb\nc") == {1, 2, 3}


def test_prose_is_never_guessed_to_be_code():
    """Every one of these tripped the old heuristic."""
    for line in (
        "def hello():",
        "x = 1",
        "قیمت: ۱۲۰۰ تومان",
        "user@example.com",
        "ساعت ۱۰:۳۰ جلسه {مهم}",
        "SELECT everything you need",
        "console.log",
        "<تگ>",
    ):
        assert fenced_code_lines(line) == set(), line


def test_persian_note_with_punctuation_stays_right_to_left(qapp):
    """The regression that motivated removing the guesswork."""
    editor = SmartEditor()
    editor.set_direction_mode("rtl")
    editor.setPlainText(
        "یادداشت\nهاست: server1.example.com\nپورت = ۲۲\nرمز {محرمانه}"
    )
    qapp.processEvents()

    block = editor.document().begin()
    while block.isValid():
        assert (
            block.blockFormat().layoutDirection() == Qt.LayoutDirection.RightToLeft
        ), block.text()
        assert not editor.line_is_code(block.blockNumber()), block.text()
        block = block.next()


def test_fenced_block_is_still_forced_left_to_right(qapp):
    editor = SmartEditor()
    editor.set_direction_mode("rtl")
    editor.setPlainText("توضیح\n```\nx = compute(1)\n```\nپایان")
    qapp.processEvents()

    assert editor.line_is_code(2)
    second = editor.document().findBlockByNumber(2)
    assert second.blockFormat().layoutDirection() == Qt.LayoutDirection.LeftToRight
