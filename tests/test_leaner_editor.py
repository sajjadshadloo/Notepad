"""What 4.1.2 took out of the editor, and what must still look right.

The reported symptom was a numbered list rendering "۱." on one line and
".2" on the next. The cause was the code fence: an unclosed ``` turned every
line after it into "code", which is forced left-to-right, so those markers
switched to Latin digits and flipped sides. Removing fenced blocks removes
the whole class of bug — and they were the one construct the editor showed
raw, three lines of ``` around whatever you wrote.
"""
import pytest

from core.list_editing import display_number_marker
from ui.editor import SmartEditor


@pytest.fixture
def editor(qapp):
    from ui.markdown_highlighter import MarkdownHighlighter

    widget = SmartEditor()
    widget.markdown_highlighter = MarkdownHighlighter(widget)
    widget.resize(700, 400)
    widget.show()
    yield widget
    widget.close()
    widget.deleteLater()


# Numbered markers

def test_every_numbered_marker_reads_the_same_way(editor, qapp):
    """Including the empty one: a half-typed row must not flip script."""
    editor.setPlainText("1. مورد اول\n2. \n3. مورد سوم\n")
    editor._refresh_layout()
    qapp.processEvents()

    markers = [
        display_number_marker(item.marker, True)
        for _block, item, _rect in editor._visible_list_markers()
        if item.kind == "numbered"
    ]
    assert markers == [".۱", ".۲", ".۳"]


def test_a_marker_in_a_forced_rtl_document_uses_persian_digits(editor):
    editor.set_direction_mode("rtl")
    editor.setPlainText("1. کار\n")
    editor._refresh_layout()
    markers = [
        display_number_marker(item.marker, True)
        for _b, item, _r in editor._visible_list_markers()
    ]
    assert markers == [".۱"]


def test_a_left_to_right_document_keeps_ascii_markers(editor):
    editor.set_direction_mode("ltr")
    editor.setPlainText("1. task\n")
    editor._refresh_layout()
    markers = [
        display_number_marker(item.marker, False)
        for _b, item, _r in editor._visible_list_markers()
    ]
    assert markers == ["1."]


# Code fences are gone

def test_the_editor_no_longer_knows_about_code_fences(editor):
    for name in ("line_is_code", "refresh_code_blocks", "_update_code_backgrounds"):
        assert not hasattr(editor, name), name


def test_backticks_are_now_just_text(editor, qapp):
    """Nothing is hidden or tinted; a plain file stays a plain file."""
    editor.setPlainText("```\n- [ ] کار\n```\n")
    editor._refresh_layout()
    qapp.processEvents()
    assert editor.toPlainText() == "```\n- [ ] کار\n```\n"
    # No extra selections means no code tint left behind.
    assert editor.extraSelections() == []


def test_a_checkbox_between_backticks_is_still_a_checkbox(editor, qapp):
    """It used to be inert because the fence claimed the line."""
    editor.setPlainText("```\n- [ ] کار\n```\n")
    editor._refresh_layout()
    qapp.processEvents()
    kinds = [item.kind for _b, item, _r in editor._visible_list_markers()]
    assert "todo" in kinds


def test_the_highlighter_has_no_code_branch():
    import ui.markdown_highlighter as module

    assert not hasattr(module, "CODE_FONT_FAMILIES")
    assert not hasattr(module.MarkdownHighlighter, "_highlight_code")
