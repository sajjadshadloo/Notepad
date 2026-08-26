"""The three colour palettes, and the promise that nothing hardcodes a colour.

The redesign's whole premise is that every colour comes from one of eleven
tokens, so a palette is a data change. These tests hold that line.
"""
import re

import pytest

import ui.styles as styles


@pytest.mark.parametrize("name", styles.palette_names())
@pytest.mark.parametrize("half", ["dark", "light"])
def test_every_palette_defines_exactly_the_same_tokens(name, half):
    assert set(styles.PALETTES[name][half]) == set(styles.TOKENS)


@pytest.mark.parametrize("name", styles.palette_names())
@pytest.mark.parametrize("half", ["dark", "light"])
def test_every_token_is_a_hex_colour(name, half):
    for token, value in styles.PALETTES[name][half].items():
        assert re.fullmatch(r"#[0-9a-f]{6}", value), f"{name}/{half}/{token}"


@pytest.mark.parametrize("name", styles.palette_names())
def test_a_palette_is_actually_two_different_halves(name):
    dark = styles.PALETTES[name]["dark"]
    light = styles.PALETTES[name]["light"]
    assert dark["window"] != light["window"]
    assert dark["text"] != light["text"]


@pytest.mark.parametrize("name", styles.palette_names())
def test_each_palette_has_its_own_accent(name):
    """Otherwise the picker would offer three names for one look."""
    others = [
        styles.PALETTES[other]["dark"]["accent"]
        for other in styles.palette_names()
        if other != name
    ]
    assert styles.PALETTES[name]["dark"]["accent"] not in others


def test_an_unknown_palette_falls_back_rather_than_raising():
    """A settings file written by an older version names none of these."""
    assert styles.palette_for("dark", "no-such-palette") == styles.PALETTES[
        styles.DEFAULT_PALETTE
    ]["dark"]


def test_the_theme_still_picks_the_half():
    assert styles.palette_for("light", "amber") is styles.PALETTES["amber"]["light"]
    assert styles.palette_for("dark", "amber") is styles.PALETTES["amber"]["dark"]


@pytest.mark.parametrize("name", styles.palette_names())
@pytest.mark.parametrize("theme", ["dark", "light"])
def test_the_stylesheet_names_no_colour_outside_its_palette(name, theme):
    """A hardcoded hex in the sheet is a colour a palette cannot reach."""
    sheet = styles.build_stylesheet(theme, name)
    allowed = {v.lower() for v in styles.palette_for(theme, name).values()}
    used = {m.lower() for m in re.findall(r"#[0-9a-fA-F]{6}", sheet)}
    assert used <= allowed, f"stray colours: {sorted(used - allowed)}"


def test_building_a_sheet_updates_what_the_painters_read():
    """The editor paints its own markers from current_palette()."""
    styles.build_stylesheet("light", "violet")
    assert styles.current_palette() is styles.PALETTES["violet"]["light"]
    assert styles.current_is_light()

    styles.build_stylesheet("dark", "amber")
    assert styles.current_palette() is styles.PALETTES["amber"]["dark"]
    assert not styles.current_is_light()


def test_light_is_reported_even_when_two_palettes_share_a_value():
    """current_is_light() used to compare identity against one LIGHT dict.

    Every palette's light half sets surface to #ffffff, so identity was the
    wrong question the moment there was more than one palette.
    """
    styles.build_stylesheet("light", "amber")
    assert styles.current_is_light()
    styles.build_stylesheet("light", "graphite")
    assert styles.current_is_light()


def test_the_default_palette_is_one_of_the_offered_ones():
    assert styles.DEFAULT_PALETTE in styles.palette_names()


def test_every_palette_has_a_label_for_the_picker():
    for name in styles.palette_names():
        assert styles.palette_label(name).strip()
