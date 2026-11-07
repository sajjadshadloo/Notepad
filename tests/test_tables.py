"""Markdown tables as data — what the grid reads and writes."""
from core import tables


def test_a_pipe_line_is_a_row():
    assert tables.is_row("| a | b |")
    assert tables.is_row("  | a | b |  ")
    assert not tables.is_row("a | b")
    assert not tables.is_row("||")
    assert not tables.is_row("")


def test_cells_are_trimmed_and_the_outer_pipes_dropped():
    assert tables.split_cells("| پروژه |  کارفرما | **مبلغ** |") == [
        "پروژه",
        "کارفرما",
        "**مبلغ**",
    ]


def test_an_empty_cell_stays_a_cell():
    assert tables.split_cells("| a |  | c |") == ["a", "", "c"]


def test_the_separator_line_is_recognised_with_alignment_colons():
    assert tables.is_separator("| :--- | :---: | ---: |")
    assert tables.is_separator("|---|---|")
    assert not tables.is_separator("| a | --- |")


def test_alignments_come_from_the_colons():
    assert tables.column_alignments("| :--- | :---: | ---: | --- |") == [
        "left",
        "center",
        "right",
        "left",
    ]


def test_replacing_a_cell_keeps_the_others():
    line = "| a | b | c |"
    assert tables.replace_cell(line, 1, "تازه") == "| a | تازه | c |"


def test_a_pipe_typed_into_a_cell_cannot_split_it():
    assert tables.split_cells(tables.replace_cell("| a | b |", 0, "x|y")) == ["x/y", "b"]


def test_replacing_past_the_end_grows_the_row():
    assert tables.replace_cell("| a |", 2, "z") == "| a |  | z |"


def test_a_new_table_is_header_separator_and_empty_rows():
    lines = tables.new_table(3, 2)
    assert len(lines) == 4
    assert tables.is_separator(lines[1])
    assert all(len(tables.split_cells(line)) == 3 for line in lines)


def test_adding_and_removing_a_column_keeps_every_row_the_same_width():
    lines = tables.new_table(2, 1)
    wider = tables.add_column(lines)
    assert {len(tables.split_cells(line)) for line in wider} == {3}
    assert tables.is_separator(wider[1])
    narrower = tables.remove_column(wider, 0)
    assert {len(tables.split_cells(line)) for line in narrower} == {2}


def test_the_last_column_cannot_be_removed():
    lines = tables.new_table(1, 1)
    assert tables.remove_column(lines, 0) == lines


def test_cell_html_shows_bold_code_and_breaks_and_escapes_the_rest():
    html = tables.cell_html("**ایونت**<br>`a.com` <x>")
    assert "<b>ایونت</b>" in html
    assert "<br>" in html
    assert "<code>a.com</code>" in html
    assert "&lt;x&gt;" in html
