import pytest

from core.formatting import (
    strip_marker,
    todo_checkbox_span,
    toggle_bold,
    toggle_bullet,
    toggle_done,
    toggle_heading,
    toggle_numbered,
    toggle_todo,
)


def test_toggle_bold_roundtrip():
    assert toggle_bold("word") == "**word**"
    assert toggle_bold("**word**") == "word"
    assert toggle_bold("متن فارسی") == "**متن فارسی**"
    assert toggle_bold("**متن فارسی**") == "متن فارسی"


def test_toggle_bold_edge_cases():
    assert toggle_bold("") == ""
    # "****" is an empty marker pair, not bold content — wrap it again.
    assert toggle_bold("**") == "******"


def test_toggle_heading_add_change_remove():
    assert toggle_heading("Title", 1) == "# Title"
    assert toggle_heading("# Title", 2) == "## Title"
    assert toggle_heading("## Title", 2) == "Title"


def test_toggle_bullet_roundtrip():
    assert toggle_bullet("item") == "- item"
    assert toggle_bullet("- item") == "item"
    assert toggle_bullet("  - item") == "  item"
    assert toggle_bullet("  متن فارسی") == "  - متن فارسی"


def test_toggle_bullet_downgrades_todo():
    assert toggle_bullet("- [ ] task") == "- task"
    assert toggle_bullet("- [x] task") == "- task"


def test_toggle_todo_roundtrip_and_upgrade():
    assert toggle_todo("task") == "- [ ] task"
    assert toggle_todo("- [ ] task") == "task"
    assert toggle_todo("- [x] task") == "task"
    assert toggle_todo("- task") == "- [ ] task"


def test_toggle_numbered_roundtrip_and_conversion():
    assert toggle_numbered("item") == "1. item"
    assert toggle_numbered("1. item") == "item"
    assert toggle_numbered("  12. item") == "  item"
    assert toggle_numbered("- item") == "1. item"
    assert toggle_numbered("- [x] item") == "1. item"


def test_toggle_done_flips_state_only_on_todo_lines():
    assert toggle_done("- [ ] task") == "- [x] task"
    assert toggle_done("- [x] task") == "- [ ] task"
    assert toggle_done("- [X] task") == "- [ ] task"
    assert toggle_done("plain line") == "plain line"


def test_todo_checkbox_span():
    assert todo_checkbox_span("- [ ] task") == (0, 5)
    assert todo_checkbox_span("  - [x] کار") == (2, 7)
    assert todo_checkbox_span("- bullet") is None
    assert todo_checkbox_span("plain") is None


# Markers replace each other; they never stack
#
# Pressing ☑ then H2 then • used to build "- ## - [ ] ", which renders as a
# painted bullet followed by the literal text "## - [ ]" — every toggle knew
# only its own marker and prepended over the others. A line is one kind or
# none, so every pair is checked here rather than the few that were.

MARKERS = {
    "heading": lambda line: toggle_heading(line, 2),
    "bullet": toggle_bullet,
    "numbered": toggle_numbered,
    "todo": toggle_todo,
}

PREFIXES = {
    "heading": "## ",
    "bullet": "- ",
    "numbered": "1. ",
    "todo": "- [ ] ",
}


@pytest.mark.parametrize("first", sorted(MARKERS))
@pytest.mark.parametrize("second", sorted(MARKERS))
def test_one_marker_replaces_another(first, second):
    line = MARKERS[first]("متن کار")
    assert line == PREFIXES[first] + "متن کار"

    line = MARKERS[second](line)
    if first == second:
        assert line == "متن کار"
    else:
        assert line == PREFIXES[second] + "متن کار"


@pytest.mark.parametrize("kind", sorted(MARKERS))
def test_a_line_never_carries_two_markers(kind):
    """Whatever order they are pressed in, only one prefix survives."""
    line = "متن"
    for name in ("todo", "heading", "bullet", "numbered", kind):
        line = MARKERS[name](line)
    assert line.count("#") == 0 or line.startswith("## ")
    assert not line.startswith("- ## ")
    assert not line.startswith("1. - ")
    assert line.endswith("متن")


def test_the_reported_sequence_no_longer_stacks():
    """☑ then H2 then • — exactly what was on screen."""
    line = toggle_todo("")
    line = toggle_heading(line, 2)
    line = toggle_bullet(line)
    assert line == "- "


def test_indentation_survives_a_marker_change():
    assert toggle_todo("    - مورد") == "    - [ ] مورد"
    assert toggle_bullet("    - [ ] مورد") == "    - مورد"


def test_a_heading_drops_the_indent_it_cannot_have():
    assert toggle_heading("    - [ ] مورد", 1) == "# مورد"


def test_stripping_a_plain_line_leaves_it_alone():
    assert strip_marker("متن ساده") == ("", "متن ساده")
    assert strip_marker("  متن ساده") == ("  ", "متن ساده")


def test_stripping_recognises_every_marker():
    assert strip_marker("## عنوان") == ("", "عنوان")
    assert strip_marker("- مورد") == ("", "مورد")
    assert strip_marker("1. مورد") == ("", "مورد")
    assert strip_marker("- [ ] کار") == ("", "کار")
    assert strip_marker("- [x] کار") == ("", "کار")


def test_bold_is_untouched_by_a_marker_change():
    """Inline emphasis is not a line marker and must survive."""
    assert toggle_todo("- **مهم** است") == "- [ ] **مهم** است"
