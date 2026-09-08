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
    _rect, overdue, done = _capsules(editor, qapp)[0]
    assert overdue and not done


def test_a_finished_task_is_flagged_as_done(editor, qapp):
    editor.setPlainText("- [x] کار @1400/01/01 09:00\n")
    _rect, overdue, done = _capsules(editor, qapp)[0]
    assert done and not overdue


def test_a_future_task_is_neither(editor, qapp):
    editor.setPlainText("- [ ] کار @1499/01/01 09:00\n")
    _rect, overdue, done = _capsules(editor, qapp)[0]
    assert not overdue and not done


def test_lines_without_stamps_cost_nothing(editor, qapp):
    editor.setPlainText("سلام\n- [ ] بدون تاریخ\n## سرفصل\n")
    assert _capsules(editor, qapp) == []
