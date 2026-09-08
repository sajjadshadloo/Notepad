"""What the chrome actually paints, sampled from a rendered window.

A plain QWidget silently ignores a stylesheet `background` unless it has
WA_StyledBackground. Nothing warns, the rule looks right in the sheet, and
the widget just shows whatever is behind it — which is how the tab strip
ended up with the QTabBar painting `surface` inside a bar showing `window`,
and reading as a stray box around the tab.

The only honest test for that is to render and look at the pixels.
"""
import pytest

from ui.styles import PALETTES


@pytest.fixture
def window(tmp_path, monkeypatch, qapp):
    monkeypatch.setenv("NOTEPAD_DATA_DIR", str(tmp_path / "appdata"))
    from ui.main_window import MainWindow
    from ui.styles import build_stylesheet

    window = MainWindow()
    # Styled on the window, not the application. These tests read pixels, so
    # a stylesheet is required — but an app-wide one re-polishes every widget
    # alive in the process, including any a previous test file leaked, and
    # walking one of those crashes the interpreter outright.
    window.setStyleSheet(build_stylesheet("dark", "graphite"))
    window._cfg["notes_root"] = str(tmp_path / "notes")
    window.show_page("editor")
    window.resize(1100, 560)
    window.show()
    qapp.processEvents()
    yield window
    for index in range(window.tabs.count()):
        window.tabs.widget(index).mark_clean()
    window.close()


def _colour_at(window, widget, dx: int, dy: int) -> str:
    image = window.grab().toImage()
    origin = widget.mapTo(window, widget.rect().topLeft())
    return image.pixelColor(origin.x() + dx, origin.y() + dy).name().lower()


@pytest.fixture
def tokens():
    return PALETTES["graphite"]["dark"]


def test_the_top_bar_paints_the_chrome_colour(window, qapp, tokens):
    qapp.processEvents()
    assert _colour_at(window, window.top_bar, 300, 6) == tokens["surface"]


def test_the_tab_strip_paints_the_chrome_colour(window, qapp, tokens):
    """Not just under the tabs — the whole strip, or the QTabBar's own fill
    reads as a lighter box floating in it."""
    qapp.processEvents()
    assert _colour_at(window, window.tabs, 600, 8) == tokens["surface"]


def test_the_strip_matches_under_and_beside_the_tabs(window, qapp):
    qapp.processEvents()
    beside = _colour_at(window, window.tabs, 600, 8)
    far = _colour_at(window, window.tabs, 900, 8)
    assert beside == far


def test_the_notes_board_paints_the_window_colour(window, qapp, tokens):
    """The board is a page, not a panel: it owns the whole area below the bar
    and so paints the window colour, with the cards raised on top of it."""
    window.show_page("notes")
    qapp.processEvents()
    assert _colour_at(window, window.notes_board, 6, 300) == tokens["window"]


def test_the_format_bar_sits_on_the_page_colour(window, qapp, tokens):
    """The design puts this one on the window colour, not the chrome."""
    qapp.processEvents()
    assert _colour_at(window, window.format_bar, 600, 8) == tokens["window"]


def test_the_selection_is_a_wash_not_a_solid_accent(window, tokens):
    """A solid fill hides the text it is highlighting."""
    from ui.styles import build_stylesheet, translucent

    sheet = build_stylesheet("dark", "graphite")
    assert translucent(tokens["accent"], 0.30) in sheet
    assert f"selection-background-color: {tokens['accent']};" not in sheet


def test_selected_text_keeps_its_own_colour(window):
    from ui.styles import build_stylesheet, PALETTES

    sheet = build_stylesheet("dark", "graphite")
    tokens = PALETTES["graphite"]["dark"]
    assert f"selection-color: {tokens['text']}" in sheet
    assert f"selection-color: {tokens['on_accent']}" not in sheet
