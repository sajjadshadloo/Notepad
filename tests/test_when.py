"""Reading a day out of a typed task, the way the v4 design's inputs do."""
from datetime import date

import pytest

from core.when import day_label, long_label, parse_preview, parse_when

# 1405/07/03 — a Friday, the design's own "today".
FRIDAY = date(2026, 9, 25)


@pytest.mark.parametrize("raw, days, text", [
    ("تماس با حمید فردا", 1, "تماس با حمید"),
    ("فردا تماس با حمید", 1, "تماس با حمید"),
    ("پس‌فردا جلسه", 2, "جلسه"),
    ("پس فردا جلسه", 2, "جلسه"),
    ("امروز بک‌آپ", 0, "بک‌آپ"),
    ("گزارش هفته‌ی بعد", 7, "گزارش"),
    ("گزارش هفته بعد", 7, "گزارش"),
])
def test_relative_words(raw, days, text):
    found = parse_when(raw, FRIDAY)
    assert (found.day - FRIDAY).days == days
    assert found.text == text


def test_a_weekday_is_the_next_one_to_come():
    found = parse_when("جلسه با تیم طراحی شنبه", FRIDAY)
    assert found.day == date(2026, 9, 26)
    assert found.text == "جلسه با تیم طراحی"


def test_todays_own_weekday_means_next_week():
    assert parse_when("جمعه خرید", FRIDAY).day == date(2026, 10, 2)


def test_a_weekday_with_a_space_instead_of_a_zwnj():
    assert parse_when("سه شنبه تحویل", FRIDAY).day == date(2026, 9, 29)


def test_a_jalali_date_with_persian_digits():
    found = parse_when("تمدید دامنه ۱۲ مهر", FRIDAY)
    assert found.day == date(2026, 10, 4)
    assert found.text == "تمدید دامنه"


def test_a_date_already_past_this_year_is_next_years():
    assert parse_when("تولد ۱ مهر", FRIDAY).day == date(2027, 9, 23)


def test_other_months_work_too():
    assert parse_when("تحویل ۲۰ آبان", FRIDAY).day == date(2026, 11, 11)


def test_a_word_inside_another_word_is_not_a_day():
    assert parse_when("فرداها بهتر است", FRIDAY) is None
    assert parse_when("امروزی", FRIDAY) is None


def test_plain_text_has_no_day():
    assert parse_when("خرید نان", FRIDAY) is None


def test_labels():
    assert day_label(FRIDAY, FRIDAY) == "امروز"
    assert day_label(date(2026, 9, 26), FRIDAY) == "فردا"
    assert day_label(date(2026, 9, 24), FRIDAY) == "دیروز"
    assert day_label(date(2026, 10, 4), FRIDAY) == "۱۲ مهر"
    assert long_label(date(2026, 9, 26)) == "شنبه ۴ مهر"


def test_the_preview_chip():
    label, rest = parse_preview("تماس با حمید فردا", FRIDAY)
    assert label == "فردا · شنبه ۴ مهر"
    assert rest == "کار: «تماس با حمید»"
    assert parse_preview("خرید نان", FRIDAY) is None
