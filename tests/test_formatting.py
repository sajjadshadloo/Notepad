from core.formatting import (
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
