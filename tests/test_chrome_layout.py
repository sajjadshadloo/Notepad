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
    # The tab strip lives on the editor page now, and a page that is not the
    # current one is never laid out — every measurement here would be of a
    # widget Qt has not sized yet.
    window.show_page("editor")
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
    """Top bar, tab strip, format bar, then the pages."""
    window.show_page("editor")
    qapp.processEvents()
    tops = [
        window.top_bar.mapTo(window, window.top_bar.rect().topLeft()).y(),
        window.tabs.mapTo(window, window.tabs.rect().topLeft()).y(),
        window.format_bar.mapTo(window, window.format_bar.rect().topLeft()).y(),
        window.tabs.pages.mapTo(window, window.tabs.pages.rect().topLeft()).y(),
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


# The format bar, after 4.1.2 trimmed it
#
# It had eleven controls. Bullet, number, checkbox and bold are the ones that
# matter; H3, the weekly-repeat mark and the code fence were taking width
# from them.

def test_the_format_bar_holds_only_what_is_used(window):
    labels = [a.text() for a in window.format_bar.actions() if a.text()]
    assert labels == ["B", "H1", "H2", "•", "1.", "☑", "@", "Find"]


def test_the_code_fence_and_weekly_repeat_are_gone(window):
    assert not hasattr(window, "fence_action")
    assert not hasattr(window, "repeat_action")
    assert not hasattr(window, "wrap_in_code_fence")


def test_the_third_heading_level_is_still_reachable(window):
    """Off the bar, not out of the app — Ctrl+3 and the palette still have it."""
    assert len(window.heading_actions) == 3
    labels = {label for label, _hint, _run in window._palette_commands()}
    assert any("Heading 3" in label for label in labels)


def test_the_close_button_is_ours_not_the_platform_cross(window):
    """Qt's default close pixmap is a red cross that reads as an error."""
    from PyQt6.QtWidgets import QTabBar, QToolButton

    bar = window.document_tab_bar
    button = bar.tabButton(0, QTabBar.ButtonPosition.RightSide)
    assert isinstance(button, QToolButton)
    assert button.objectName() == "tabCloseButton"
    assert not button.icon().isNull()


def test_the_close_button_closes_the_tab_it_belongs_to(window, qapp):
    """Tabs are movable, so the index cannot be captured when it is built."""
    from PyQt6.QtWidgets import QTabBar

    window.new_document()
    qapp.processEvents()
    assert window.tabs.count() == 2
    closed = []
    window.document_tab_bar.tabCloseRequested.connect(closed.append)
    button = window.document_tab_bar.tabButton(1, QTabBar.ButtonPosition.RightSide)
    button.click()
    assert closed == [1]


def test_the_search_badge_names_a_key_that_works(window):
    """The field shows "Ctrl K"; that has to actually open it."""
    from PyQt6.QtGui import QKeySequence

    assert window.top_bar.search_hint.text() == "Ctrl K"
    keys = {s.toString() for s in window.quick_open_action.shortcuts()}
    assert QKeySequence("Ctrl+K").toString() in keys
    assert QKeySequence("Ctrl+P").toString() in keys
