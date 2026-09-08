from datetime import date, datetime, timedelta

from core.tasks import (
    due_within,
    group_of,
    parse_document,
    parse_task,
    sort_for_today,
)


def test_plain_checkbox_has_no_deadline():
    task = parse_task("- [ ] بدون تاریخ")
    assert task and task.due is None and not task.done


def test_jalali_stamp_with_time():
    task = parse_task("- [ ] تحویل سایت @1405/06/05 10:00")
    assert task.text == "تحویل سایت"
    assert task.due == datetime(2026, 8, 27, 10, 0)
    assert task.has_time


def test_persian_digits_are_accepted():
    assert parse_task("- [ ] تماس @۱۴۰۵/۰۶/۰۳").due == datetime(2026, 8, 25, 9, 0)


def test_gregorian_stamp_still_works():
    """Above 1600 the year is read as Gregorian, so both calendars parse."""
    assert parse_task("- [ ] x @2026-08-27 14:30").due == datetime(2026, 8, 27, 14, 30)


def test_date_without_time_defaults_to_morning():
    task = parse_task("- [ ] x @1405/06/05")
    assert task.due == datetime(2026, 8, 27, 9, 0)
    assert not task.has_time


def test_a_typo_keeps_the_text_instead_of_dropping_it():
    """Losing the words to a bad date would be worse than losing the date."""
    task = parse_task("- [ ] مهم @1405/13/45")
    assert task.due is None
    assert "1405/13/45" in task.text


def test_completed_tasks_are_marked():
    assert parse_task("- [x] done @1405/06/01").done
    assert parse_task("- [X] done").done


def test_non_task_lines_are_ignored():
    for line in ("عنوان", "- bullet", "1. numbered", "", "  - [] malformed"):
        assert parse_task(line) is None


def test_parse_document_records_line_numbers():
    text = "# عنوان\n- [ ] اول @1405/06/05\nمتن\n- [x] دوم"
    tasks = parse_document(text, path="C:/notes/a.md")
    assert [t.line_number for t in tasks] == [1, 3]
    assert all(t.path == "C:/notes/a.md" for t in tasks)


def test_due_within_ignores_finished_and_future_work():
    tasks = parse_document(
        "- [ ] now @1405/06/03 09:00\n"
        "- [x] done @1405/06/03 09:00\n"
        "- [ ] later @1405/09/01 09:00\n"
        "- [ ] undated"
    )
    ready = due_within(tasks, datetime(2026, 8, 25, 9, 0))
    assert [t.text for t in ready] == ["now"]


def test_today_view_puts_overdue_first_then_undated_last():
    tasks = parse_document(
        "- [ ] later @1405/06/10 09:00\n"
        "- [ ] overdue @1405/06/01 09:00\n"
        "- [ ] undated\n"
        "- [ ] today @1405/06/03 18:00\n"
        "- [x] finished @1405/06/01 09:00"
    )
    order = [t.text for t in sort_for_today(tasks, datetime(2026, 8, 25, 12, 0))]
    assert order == ["overdue", "today", "later", "undated"]


# A date without a time owns the whole day
#
# Stamps carry no time since 4.1, and the parser fills in 9am so tasks sort
# sensibly within a day. Reading that 9am as a deadline turned everything
# written in the morning red by lunchtime — including a task added today.

def _stamped(day, suffix=""):
    from core.jalali import format_date

    return parse_task(
        "- [ ] کار @" + format_date(day, persian_digits=False) + suffix
    )


def test_todays_task_is_not_late_while_today_is_still_running():
    task = _stamped(date.today())
    assert not task.overdue
    assert group_of(task, datetime.now()) == "امروز"


def test_yesterdays_task_is_late():
    task = _stamped(date.today() - timedelta(days=1))
    assert task.overdue
    assert group_of(task, datetime.now()) == "عقب‌افتاده"


def test_tomorrows_task_is_not_late():
    task = _stamped(date.today() + timedelta(days=1))
    assert not task.overdue
    assert group_of(task, datetime.now()) == "فردا"


def test_an_explicit_time_that_has_passed_is_still_late():
    """Notes written by 3.x carry times; those keep meaning what they meant."""
    task = _stamped(date.today(), " 00:01")
    assert task.has_time
    assert task.overdue


def test_an_explicit_time_still_ahead_is_not_late():
    task = _stamped(date.today(), " 23:59")
    assert task.has_time
    assert not task.overdue


def test_a_finished_task_is_never_late():
    from core.jalali import format_date

    when = format_date(date.today() - timedelta(days=3), persian_digits=False)
    assert not parse_task("- [x] کار @" + when).overdue


def test_the_hour_is_still_used_for_ordering_within_a_day():
    """Dropping it from the deadline must not drop it from the sort."""
    task = _stamped(date.today())
    assert task.due.hour == 9
