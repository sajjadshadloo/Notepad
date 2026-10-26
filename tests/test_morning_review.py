"""The morning review lists what is left from earlier days and what is due today."""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from PyQt6.QtWidgets import QWidget

from core.tasks import Task
from ui.overlays import MorningReview, _AllClear, _ReviewRow


def _task(text, when, line=1, done=False):
    return Task(text=text, done=done, due=when, has_time=True, path="tasks.md", line_number=line)


@pytest.fixture
def review(qapp):
    host = QWidget()
    host.resize(1000, 800)
    host.show()
    panel = MorningReview(host, "")
    yield panel
    host.deleteLater()


def _rows(review):
    return review.scroll.widget().findChildren(_ReviewRow)


def test_review_lists_leftovers_then_today(review):
    now = datetime.now()
    review.set_tasks([_task("کار مانده", now - timedelta(days=2))],
                     [_task("کار امروز", now.replace(hour=10, minute=0), line=2)])
    assert [row._task.text for row in _rows(review)] == ["کار مانده", "کار امروز"]


def test_a_task_due_today_is_not_offered_a_move_to_today(review):
    now = datetime.now()
    review.set_tasks([_task("کار مانده", now - timedelta(days=2))],
                     [_task("کار امروز", now.replace(hour=10, minute=0), line=2)])
    leftover, today = _rows(review)
    assert not leftover.today.isHidden()
    assert today.today.isHidden()


def test_only_today_tasks_are_listed_and_move_all_stays_hidden(review):
    now = datetime.now()
    review.set_tasks([], [_task("کار امروز", now.replace(hour=10, minute=0))])
    assert [row._task.text for row in _rows(review)] == ["کار امروز"]
    assert review.all_today.isHidden()


def test_nothing_left_and_nothing_today_shows_the_all_clear(review):
    review.set_tasks([], [])
    assert review.scroll.widget().findChildren(_AllClear)
    assert _rows(review) == []


def test_the_window_grows_with_the_list(review):
    now = datetime.now()
    review.set_tasks([], [])
    empty = review._height
    review.set_tasks([], [_task(f"کار {i}", now.replace(hour=9), line=i) for i in range(1, 6)])
    assert review._height > empty


def test_the_review_reads_overdue_and_today_from_the_same_scan():
    from ui.main_window import MainWindow

    now = datetime.now()
    tasks = [
        _task("کار مانده", now - timedelta(days=2), line=1),
        _task("کار امروز", now.replace(hour=10, minute=0), line=2),
        _task("کار امروز انجام شده", now.replace(hour=11, minute=0), line=3, done=True),
        _task("کار فردا", now + timedelta(days=1), line=4),
    ]
    fake = SimpleNamespace(_tasks_watcher=SimpleNamespace(all_tasks=lambda: tasks))
    overdue, due_today = MainWindow._overdue_and_today(fake)
    assert [t.text for t in overdue] == ["کار مانده"]
    assert [t.text for t in due_today] == ["کار امروز"]
