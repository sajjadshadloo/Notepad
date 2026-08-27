"""Geometry of the top bar and tab strip.

Every case here is something that looked wrong on screen and was invisible
in the code: a widget silently reserving space it never uses, a layout flag
that quietly switches off stretching, a badge stretched to its container's
height. Measurements, not screenshots, so they stay honest.
"""
import pytest

from ui.top_bar import BAR_HEIGHT, SEARCH_MAX_WIDTH


@pytest.fixture
def window(tmp_path, monkeypatch, qapp):
    monkeypatch.setenv("NOTEPAD_DATA_DIR", str(tmp_path / "appdata"))
    from ui.main_window import MainWindow

    window = MainWindow()
    window._cfg["notes_root"] = str(tmp_path / "notes")
    window.resize(1158, 576)
    window.show()
    qapp.processEvents()
    yield window
    for index in range(window.tabs.count()):
        window.tabs.widget(index).mark_clean()
    window.close()


def test_no_dead_space_between_the_last_tab_and_the_plus(window, qapp):
    """QTabBar's minimumSizeHint reserves room for scroll arrows it never
    shows, which left a wide gap in the strip."""
    bar = window.document_tab_bar
    qapp.processEvents()
    assert bar.width() == bar.tabRect(bar.count() - 1).right() + 1
    assert bar.new_button.x() == bar.width()


def test_the_tab_does_not_stretch_across_the_whole_strip(window, qapp):
    qapp.processEvents()
    assert window.document_tab_bar.tabRect(0).width() < 300
    assert not window.document_tab_bar.expanding()


def test_the_search_field_reaches_its_full_width(window, qapp):
    """An alignment flag on a layout item switches off stretching, and a
    modest stretch factor only ever won it half the slot."""
    qapp.processEvents()
    assert window.top_bar.search.width() == SEARCH_MAX_WIDTH


def test_the_search_field_is_centred_in_the_window(window, qapp):
    qapp.processEvents()
    search = window.top_bar.search
    centre = search.mapTo(window, search.rect().center()).x()
    assert abs(centre - window.width() // 2) <= 2


def test_the_ctrl_k_badge_is_a_pill_not_a_tall_box(window, qapp):
    """Left to the layout it took the field's full 30px height, drawing its
    border as a rectangle around a short label."""
    qapp.processEvents()
    hint = window.top_bar.search_hint
    assert hint.height() == 18
    assert hint.height() < window.top_bar.search.height()


def test_the_badge_is_vertically_centred_in_the_field(window, qapp):
    qapp.processEvents()
    hint = window.top_bar.search_hint
    search = window.top_bar.search
    above = hint.y()
    below = search.height() - (hint.y() + hint.height())
    assert abs(above - below) <= 1


def test_the_top_bar_keeps_the_designs_height(window):
    assert window.top_bar.height() == BAR_HEIGHT


def test_the_chrome_stacks_in_the_designs_order(window, qapp):
    """Top bar, tab strip, format bar, then the sidebar and editor."""
    qapp.processEvents()
    tops = [
        window.top_bar.mapTo(window, window.top_bar.rect().topLeft()).y(),
        window.tabs.mapTo(window, window.tabs.rect().topLeft()).y(),
        window.format_bar.mapTo(window, window.format_bar.rect().topLeft()).y(),
        window._splitter.mapTo(window, window._splitter.rect().topLeft()).y(),
    ]
    assert tops == sorted(tops), tops


def test_the_menu_bar_is_hidden_but_still_carries_the_commands(window):
    assert not window.menuBar().isVisible()
    assert len(window._palette_commands()) > 40


def test_every_menu_command_is_reachable_from_the_palette(window):
    """With no menu bar on screen, anything missing here is unreachable."""
    labels = {label for label, _hint, _run in window._palette_commands()}
    for name in ("Save", "Settings", "Go to File", "My Tasks"):
        assert any(name in label for label in labels), name
