"""The status dot the design puts before a tab's name.

It is drawn as the tab's icon rather than prefixed to the title as "●": a
bullet in the text lands on the wrong side of a Persian file name, and having
one only while the document is dirty made every tab jump wider as you typed.

The dot is built inside a slot, where an unhandled exception aborts the
process with no traceback rather than failing loudly — so it is worth a test
that actually exercises the drawing.
"""
import pytest

from ui.styles import current_palette


@pytest.fixture
def window(tmp_path, monkeypatch, qapp):
    monkeypatch.setenv("NOTEPAD_DATA_DIR", str(tmp_path / "appdata"))
    from ui.main_window import MainWindow

    window = MainWindow()
    window._cfg["notes_root"] = str(tmp_path / "notes")
    yield window
    for index in range(window.tabs.count()):
        window.tabs.widget(index).mark_clean()
    window.close()


def test_every_tab_has_a_dot_from_the_start(window):
    """Always present, so the tab never changes width when it goes dirty."""
    assert not window.tabs.tabIcon(0).isNull()


def test_the_dot_survives_going_dirty_and_clean(window):
    tab = window.current_document()
    # A real edit, not setPlainText — that resets the modified flag.
    tab.editor.textCursor().insertText("سلام")
    window._document_state_changed(tab)
    assert tab.modified
    assert not window.tabs.tabIcon(0).isNull()

    tab.mark_clean()
    window._document_state_changed(tab)
    assert not window.tabs.tabIcon(0).isNull()


def test_a_persian_name_keeps_its_title_clean(window):
    """No bullet character mixed into a right-to-left file name."""
    tab = window.current_document()
    tab.editor.textCursor().insertText("x")
    window._document_state_changed(tab)
    assert "●" not in window.tabs.tabText(0)


def test_dirty_and_clean_dots_are_different_colours(window):
    palette = current_palette()
    assert palette["accent"] != palette["border"]
    # Two entries, keyed by colour — one per state.
    window._dot_icon(True)
    window._dot_icon(False)
    assert len(window._dot_icons) == 2


def test_the_dot_is_cached_rather_than_redrawn(window):
    first = window._dot_icon(True)
    assert window._dot_icon(True) is first


def test_a_palette_change_redraws_the_dots(window):
    window._dot_icon(True)
    assert window._dot_icons
    window._cfg["accent_palette"] = "violet"
    window._restyle()
    # The old cache is dropped, and every tab gets a fresh dot.
    assert not window.tabs.tabIcon(0).isNull()
    assert all(
        key[0] in (current_palette()["accent"], current_palette()["border"])
        for key in window._dot_icons
    )


def test_the_window_title_still_marks_unsaved_work(window):
    tab = window.current_document()
    tab.editor.textCursor().insertText("y")
    window._document_state_changed(tab)
    assert window.windowTitle().startswith("● ")
    tab.mark_clean()
    window._document_state_changed(tab)
    assert not window.windowTitle().startswith("● ")
