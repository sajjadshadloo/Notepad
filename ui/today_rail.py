"""The column that is always on screen: today's work, and a small month.

4.1 put the calendar on a page of its own. To tick one thing off you had to
leave the notes, find the day, find the task — three moves for the one thing
done most often. The rail keeps it beside the notes instead, so the daily
loop costs nothing: read the list, tick a box, type the next thing.

The month underneath is for looking ahead or back. Picking a day swaps the
list above it; there is no separate calendar to visit.
"""
from datetime import date, datetime

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.jalali import format_long, to_persian_digits
from core.tasks import Task, group_of
from ui.calendar_panel import CalendarPanel
from ui.task_rows import TaskList

RAIL_WIDTH = 340


class TodayRail(QWidget):
    task_added = pyqtSignal(object, str)          # (date, text)
    task_toggled = pyqtSignal(str, int, bool)     # (path, line, done)
    task_delete_requested = pyqtSignal(str, int)  # (path, line)
    task_opened = pyqtSignal(str, int)            # (path, line)
    file_requested = pyqtSignal()                 # open کارها.md in the editor

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("todayRail")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setFixedWidth(RAIL_WIDTH)

        self._tasks: list[Task] = []
        self._day = date.today()

        column = QVBoxLayout(self)
        column.setContentsMargins(16, 14, 16, 14)
        column.setSpacing(10)
        column.addLayout(self._build_header())

        self.input = QLineEdit()
        self.input.setObjectName("dayInput")
        self.input.setPlaceholderText("کار جدید…")
        self.input.setClearButtonEnabled(True)
        self.input.returnPressed.connect(self._submit)
        column.addWidget(self.input)

        self.list = TaskList()
        self.list.task_toggled.connect(self.task_toggled)
        self.list.task_delete_requested.connect(self.task_delete_requested)
        self.list.itemActivated.connect(self._open)
        column.addWidget(self.list, 1)

        self.progress = QLabel()
        self.progress.setObjectName("railProgress")
        column.addWidget(self.progress)

        rule = QFrame()
        rule.setObjectName("detailRule")
        rule.setFrameShape(QFrame.Shape.HLine)
        column.addWidget(rule)

        self.calendar = CalendarPanel()
        self.calendar.day_activated.connect(self.show_day)
        column.addWidget(self.calendar)

    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)
        self.heading = QLabel()
        self.heading.setObjectName("railHeading")
        self.heading.setWordWrap(True)

        self.today_button = QToolButton()
        self.today_button.setText("امروز")
        self.today_button.setObjectName("railTodayButton")
        self.today_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.today_button.setToolTip("برگشت به امروز")
        self.today_button.clicked.connect(lambda: self.show_day(date.today()))

        open_file = QToolButton()
        open_file.setText("↗")
        open_file.setObjectName("railTodayButton")
        open_file.setCursor(Qt.CursorShape.PointingHandCursor)
        open_file.setToolTip("باز کردن فایل کارها")
        open_file.clicked.connect(self.file_requested)

        row.addWidget(self.heading, 1)
        row.addWidget(self.today_button)
        row.addWidget(open_file)
        return row

    # Data

    def set_tasks(self, tasks: list[Task]):
        """Every task in the folder; the rail keeps the dated ones."""
        self._tasks = [task for task in tasks if task.due is not None]
        self.calendar.set_marked_days(
            {task.due.date() for task in self._tasks if not task.done}
        )
        self._fill()

    def show_day(self, day: date):
        self._day = day
        if self.calendar.selected_day() != day:
            self.calendar.choose(day)
        self._fill()
        self.input.setFocus()

    def selected_day(self) -> date:
        return self._day

    def tasks_on(self, day: date) -> list[Task]:
        found = [t for t in self._tasks if t.due and t.due.date() == day]
        found.sort(key=lambda t: (t.done, t.text))
        return found

    def replace_day(self, day: date, tasks: list[Task]):
        """Swap one day's tasks in without waiting for the next folder scan."""
        self._tasks = [
            task
            for task in self._tasks
            if not (task.due and task.due.date() == day)
        ]
        self._tasks.extend(task for task in tasks if task.due is not None)
        self.calendar.set_marked_days(
            {task.due.date() for task in self._tasks if not task.done}
        )
        self._fill()

    def _fill(self):
        today = date.today()
        self.heading.setText(
            "امروز" if self._day == today else format_long(self._day)
        )
        self.today_button.setVisible(self._day != today)

        tasks = self.tasks_on(self._day)
        self.list.clear()
        overdue = [
            task
            for task in self._tasks
            if not task.done
            and task.due
            and task.due.date() < today
            and self._day == today
        ]
        if overdue:
            self.list.add_header(
                "عقب‌افتاده", to_persian_digits(str(len(overdue))), urgent=True
            )
            now = datetime.now()
            for task in sorted(overdue, key=lambda t: t.due):
                self.list.add_task(task, when=group_of(task, now))
        for task in tasks:
            self.list.add_task(task, when="")
        if not tasks and not overdue:
            self.list.add_empty(
                "امروز کاری ثبت نشده" if self._day == today else "برای این روز کاری نیست"
            )

        done = sum(1 for task in tasks if task.done)
        self.progress.setText(
            to_persian_digits(str(done) + " از " + str(len(tasks)) + " انجام شده")
            if tasks
            else ""
        )

    # Actions

    def _submit(self):
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        self.task_added.emit(self._day, text)

    def _open(self, item):
        payload = self.list.payload_of(item)
        if payload:
            self.task_opened.emit(payload[0], payload[1])
