"""The date capsule drawn behind a task's stamp.

The file keeps plain `@1405/06/05 10:00`; only the drawing changes. Two
things are easy to get wrong and invisible in the code: which characters
count as the stamp, and where that run actually lands on a bidi line.
"""
import pytest

from core.tasks import stamp_span


def _stamp(line: str) -> str | None:
    span = stamp_span(line)
    return line[span[0]:span[1]] if span else None


# What counts as the stamp

def test_the_capsule_covers_the_date_and_the_time():
    assert _stamp("- [ ] تحویل سایت @1405/06/05 10:00") == "@1405/06/05 10:00"


def test_the_repeat_mark_is_inside_the_capsule():
    line = "- [ ] بررسی @۱۴۰۵/۰۶/۰۴ ۱۴:۳۰ ↻"
    assert _stamp(line) == "@۱۴۰۵/۰۶/۰۴ ۱۴:۳۰ ↻"


def test_persian_digits_are_recognised():
    assert _stamp("- [ ] کار @۱۴۰۵/۰۶/۰۵") == "@۱۴۰۵/۰۶/۰۵"


def test_a_gregorian_stamp_is_recognised():
    assert _stamp("- [x] done @2026-08-27 09:30") == "@2026-08-27 09:30"


def test_a_task_with_no_stamp_gets_no_capsule():
    assert stamp_span("- [ ] بدون تاریخ") is None


def test_an_email_address_is_not_a_deadline():
    """An @ in ordinary prose must not be drawn as a date."""
    assert stamp_span("ایمیل به sajad@example.com") is None


def test_only_checkbox_lines_get_a_capsule():
    assert stamp_span("یادداشت @1405/06/05") is None


def test_the_stamp_stops_at_the_date_when_no_time_is_given():
    assert _stamp("- [ ] کار @1405/06/05 و بعد چیز دیگر") == "@1405/06/05"


# Where it lands on screen

@pytest.fixture
def editor(qapp):
    from ui.editor import SmartEditor
    from ui.styles import build_stylesheet

    qapp.setStyleSheet(build_stylesheet("dark", "graphite"))
    editor = SmartEditor()
    editor.resize(900, 400)
    editor.show()
    qapp.processEvents()
    yield editor
    editor.close()


def _capsules(editor, qapp):
    qapp.processEvents()
    editor._invalidate_marker_cache()
    return list(editor._visible_stamps())


def test_a_right_to_left_line_gets_one_capsule(editor, qapp):
    editor.setPlainText("- [ ] تحویل سایت بامسما @1405/06/05 10:00\n")
    assert len(_capsules(editor, qapp)) == 1


def test_the_capsule_spans_the_whole_stamp_on_a_bidi_line(editor, qapp):
    """Bidi can put the time on the far side of the date, so bounding the
    run by its two outer carets alone left the time outside the ring."""
    editor.setPlainText("- [ ] تحویل سایت بامسما @1405/06/05 10:00\n")
    with_time = _capsules(editor, qapp)[0][0]

    editor.setPlainText("- [ ] تحویل سایت بامسما @1405/06/05\n")
    without_time = _capsules(editor, qapp)[0][0]

    assert with_time.width() > without_time.width()


def test_a_left_to_right_line_gets_a_capsule_too(editor, qapp):
    editor.setPlainText("- [ ] Ship the invoice @2026-09-04 09:30\n")
    capsules = _capsules(editor, qapp)
    assert len(capsules) == 1
    assert capsules[0][0].width() > 0


def test_an_overdue_task_is_flagged_for_the_danger_colour(editor, qapp):
    editor.setPlainText("- [ ] کار @1400/01/01 09:00\n")
    _rect, _label, overdue, done = _capsules(editor, qapp)[0]
    assert overdue and not done


def test_a_finished_task_is_flagged_as_done(editor, qapp):
    editor.setPlainText("- [x] کار @1400/01/01 09:00\n")
    _rect, _label, overdue, done = _capsules(editor, qapp)[0]
    assert done and not overdue


def test_a_future_task_is_neither(editor, qapp):
    editor.setPlainText("- [ ] کار @1499/01/01 09:00\n")
    _rect, _label, overdue, done = _capsules(editor, qapp)[0]
    assert not overdue and not done


def test_lines_without_stamps_cost_nothing(editor, qapp):
    editor.setPlainText("سلام\n- [ ] بدون تاریخ\n## سرفصل\n")
    assert _capsules(editor, qapp) == []


# The badge replaces the stamp's own text
#
# "@۱۴۰۵/۰۶/۰۵ ۱۷:۱۳" is markup showing through. The characters are painted
# invisible and this is drawn over the space they reserve, so the file keeps
# its plain-text stamp and the screen shows a date a person reads.

def test_the_badge_reads_as_a_date_not_as_a_stamp(editor, qapp):
    from datetime import date

    from core.jalali import format_date

    today = date.today()
    editor.setPlainText("- [ ] کار @" + format_date(today, persian_digits=False) + "\n")
    _rect, label, _overdue, _done = _capsules(editor, qapp)[0]
    assert label == "امروز"
    assert "@" not in label


def test_tomorrow_and_yesterday_get_their_own_words(editor, qapp):
    from datetime import date, timedelta

    from core.jalali import format_date

    for delta, expected in ((1, "فردا"), (-1, "دیروز")):
        when = date.today() + timedelta(days=delta)
        editor.setPlainText(
            "- [ ] کار @" + format_date(when, persian_digits=False) + "\n"
        )
        _rect, label, _o, _d = _capsules(editor, qapp)[0]
        assert label == expected


def test_a_distant_date_is_named_by_its_day_and_month(editor, qapp):
    editor.setPlainText("- [ ] کار @1405/06/05\n")
    _rect, label, _o, _d = _capsules(editor, qapp)[0]
    assert "شهریور" in label
    assert "@" not in label and "/" not in label


def test_the_file_still_holds_the_plain_stamp(editor, qapp):
    """Nothing is rewritten — only the rendering changes."""
    editor.setPlainText("- [ ] کار @1405/06/05 17:13\n")
    _capsules(editor, qapp)
    assert editor.toPlainText() == "- [ ] کار @1405/06/05 17:13\n"


def test_the_stamp_characters_are_painted_invisible(qapp):
    """Otherwise the badge would be drawn on top of the raw text.

    Its own editor, because the hiding is the highlighter's job and the
    shared fixture attaches none. Read off the block layout, not the cursor:
    a highlighter's formats are extra ranges on the layout and never reach
    charFormat().
    """
    from core.tasks import stamp_span
    from ui.editor import SmartEditor
    from ui.markdown_highlighter import MarkdownHighlighter

    widget = SmartEditor()
    widget.markdown_highlighter = MarkdownHighlighter(widget)
    widget.setPlainText("- [ ] کار @1405/06/05\n")
    widget._refresh_layout()
    qapp.processEvents()

    block = widget.document().firstBlock()
    start, end = stamp_span(block.text())
    covered = [
        run
        for run in block.layout().formats()
        if run.format.foreground().color().alpha() == 0
        and run.start <= start
        and run.start + run.length >= end
    ]
    widget.deleteLater()
    assert covered, "the stamp is still drawn in its own ink"
