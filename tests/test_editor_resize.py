"""A wide editor must settle on its margins, not chase them.

QTextEdit routes its viewport's resize into the editor's resizeEvent with
the viewport's size. Margins computed from that width resized the viewport
again; past ~940px the side margin depends on the width, so two widths
answered each other until the stack overflowed and the app died.
"""
import sys

import pytest

from ui.editor import SmartEditor


@pytest.fixture
def editor(qapp):
    editor = SmartEditor()
    editor.setPlainText("سلام\n" * 40)
    yield editor
    editor.deleteLater()


@pytest.mark.parametrize("width", [700, 1200, 1920, 2560])
def test_resizing_settles(editor, qapp, width, monkeypatch):
    monkeypatch.setattr(sys, "getrecursionlimit", sys.getrecursionlimit)
    calls = []
    original = SmartEditor._update_line_area_width

    def counting(self, *args, **kwargs):
        calls.append(1)
        assert len(calls) < 50, "margins keep changing"
        return original(self, *args, **kwargs)

    monkeypatch.setattr(SmartEditor, "_update_line_area_width", counting)
    editor.resize(width, 700)
    editor.show()
    qapp.processEvents()
    calls.clear()
    editor.resize(width + 37, 700)
    qapp.processEvents()
    assert len(calls) < 10


def test_the_viewport_resize_does_not_move_the_margins(editor, qapp):
    editor.resize(1920, 700)
    editor.show()
    qapp.processEvents()
    before = editor.viewportMargins()
    viewport = editor.viewport()
    from PyQt6.QtCore import QSize
    from PyQt6.QtGui import QResizeEvent

    # What QTextEdit forwards: the viewport's own, narrower size.
    editor.resizeEvent(QResizeEvent(viewport.size(), QSize(1, 1)))
    assert editor.viewportMargins() == before
