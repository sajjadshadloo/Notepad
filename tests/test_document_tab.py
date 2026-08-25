from PyQt6.QtCore import Qt

from ui.document_tab import DocumentTab


def test_a_tab_is_just_an_editor(qapp):
    """The Markdown preview and the code bar were removed in 3.1: the live
    rendering already showed the formatting, and the bar flickered in and out
    as the cursor moved."""
    tab = DocumentTab(text="# Hello")

    assert not hasattr(tab, "preview")
    assert not hasattr(tab, "code_bar")
    assert tab.editor.isVisible() or not tab.isVisible()


def test_live_markdown_hides_heading_and_bold_tokens(qapp):
    tab = DocumentTab(text="# Title\nSome **bold** text.")
    qapp.processEvents()

    heading = tab.editor.document().begin()
    heading_formats = heading.layout().formats()
    heading_marker = next(r for r in heading_formats if r.start == 0)
    assert heading_marker.format.foreground().color().alpha() == 0
    assert heading_marker.format.fontPointSize() == 1.0
    heading_text = next(r for r in heading_formats if r.start == 2)
    assert heading_text.format.foreground().style() == Qt.BrushStyle.NoBrush

    paragraph = heading.next()
    bold_markers = [
        r for r in paragraph.layout().formats()
        if r.format.foreground().color().alpha() == 0
    ]
    assert [(r.start, r.length) for r in bold_markers] == [(5, 2), (11, 2)]
    assert all(r.format.fontPointSize() == 1.0 for r in bold_markers)
