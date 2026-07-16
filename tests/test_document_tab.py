from PyQt6.QtCore import Qt

from ui.document_tab import DocumentTab


def test_toggle_preview_swaps_visibility(qapp):
    tab = DocumentTab(text="# Hello\n\nSome **bold** text.")

    assert tab.preview_active is False
    assert tab.editor.isVisible() or not tab.isVisible()

    active = tab.toggle_preview()
    assert active is True
    assert tab.preview_active is True
    assert tab.preview.isHidden() is False
    assert tab.editor.isHidden() is True
    assert "Hello" in tab.preview.toPlainText()

    active = tab.toggle_preview()
    assert active is False
    assert tab.preview_active is False
    assert tab.editor.isHidden() is False
    assert tab.preview.isHidden() is True


def test_toggle_preview_hides_code_bar(qapp):
    tab = DocumentTab(text="```\nprint('hi')\n```")
    qapp.processEvents()
    tab.code_bar.show()

    tab.toggle_preview()

    assert tab.code_bar.isHidden() is True


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
