from ui.editor import SmartEditor


def test_undo_reverts_text_after_direction_pass(qapp):
    """The automatic direction pass must merge into the user's undo step,
    so a single Ctrl+Z undoes the typed text — not an invisible format."""
    editor = SmartEditor()
    editor.textCursor().insertText("سلام دنیا")
    editor._refresh_layout()  # force the debounced direction/code pass

    editor.undo()

    assert editor.toPlainText() == ""


def test_redo_restores_text(qapp):
    editor = SmartEditor()
    editor.textCursor().insertText("hello")
    editor._refresh_layout()

    editor.undo()
    assert editor.toPlainText() == ""
    editor.redo()
    assert editor.toPlainText() == "hello"
