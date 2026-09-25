"""Full-page task and calendar surfaces from the final V4 design."""
from datetime import date, datetime
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QStackedWidget, QToolButton,
    QVBoxLayout, QWidget,
)

from core.jalali import format_long, to_persian_digits
from core.tasks import group_of, sort_for_today
from ui.calendar_panel import CalendarPanel
from ui.task_rows import TaskList, when_label


GROUP_ORDER = ("عقب‌افتاده", "امروز", "فردا", "بعداً", "بدون تاریخ", "انجام‌شده")


class TasksWorkspace(QWidget):
    task_toggled = pyqtSignal(str, int, bool)
    task_delete_requested = pyqtSignal(str, int)
    task_opened = pyqtSignal(str, int)
    task_added = pyqtSignal(object, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("tasksWorkspace")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._tasks = []
        self._mode = "tasks"

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(14)
        header = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(1)
        self.title = QLabel("کارهای من")
        self.title.setObjectName("workspaceTitle")
        self.summary = QLabel()
        self.summary.setObjectName("workspaceSubtitle")
        title_col.addWidget(self.title)
        title_col.addWidget(self.summary)
        header.addLayout(title_col)
        header.addStretch(1)
        self.mode_tasks = self._mode_button("فهرست", "tasks")
        self.mode_calendar = self._mode_button("تقویم", "calendar")
        header.addWidget(self.mode_tasks)
        header.addWidget(self.mode_calendar)
        outer.addLayout(header)

        self.stack = QStackedWidget()
        task_page = QWidget()
        task_row = QHBoxLayout(task_page)
        task_row.setContentsMargins(0, 0, 0, 0)
        task_row.setSpacing(18)
        self.list = TaskList()
        self.list.task_toggled.connect(self.task_toggled)
        self.list.task_delete_requested.connect(self.task_delete_requested)
        self.list.itemActivated.connect(self._open_item)
        self.list.currentItemChanged.connect(self._show_detail)
        task_row.addWidget(self.list, 1)
        self.detail = QWidget()
        self.detail.setObjectName("taskDetail")
        self.detail.setFixedWidth(340)
        detail_col = QVBoxLayout(self.detail)
        detail_col.setContentsMargins(18, 18, 18, 18)
        detail_col.setSpacing(10)
        detail_caption = QLabel("جزئیات کار")
        detail_caption.setObjectName("sidebarSectionLabel")
        self.detail_title = QLabel("یک کار را انتخاب کن تا جزئیاتش اینجا دیده شود.")
        self.detail_title.setObjectName("detailTitle")
        self.detail_title.setWordWrap(True)
        self.detail_meta = QLabel()
        self.detail_meta.setObjectName("workspaceSubtitle")
        self.detail_meta.setWordWrap(True)
        self.detail_open = QPushButton("باز کردن یادداشت")
        self.detail_open.setObjectName("primaryButton")
        self.detail_open.setEnabled(False)
        self.detail_open.clicked.connect(self._open_selected)
        detail_col.addWidget(detail_caption)
        detail_col.addWidget(self.detail_title)
        detail_col.addWidget(self.detail_meta)
        detail_col.addStretch(1)
        detail_col.addWidget(self.detail_open)
        task_row.addWidget(self.detail)
        self.stack.addWidget(task_page)

        calendar_page = QWidget()
        calendar_row = QHBoxLayout(calendar_page)
        calendar_row.setContentsMargins(0, 0, 0, 0)
        calendar_row.setSpacing(18)
        self.calendar = CalendarPanel(expanded=True)
        self.calendar.day_activated.connect(self._select_day)
        calendar_row.addWidget(self.calendar, 1)
        agenda = QWidget()
        agenda.setObjectName("taskDetail")
        agenda.setFixedWidth(340)
        agenda_col = QVBoxLayout(agenda)
        agenda_col.setContentsMargins(16, 16, 16, 16)
        agenda_col.setSpacing(10)
        self.day_title = QLabel()
        self.day_title.setObjectName("detailTitle")
        self.day_list = TaskList()
        self.day_list.task_toggled.connect(self.task_toggled)
        self.day_list.task_delete_requested.connect(self.task_delete_requested)
        self.day_list.itemActivated.connect(self._open_day_item)
        self.add_day = QPushButton("+ کار برای این روز")
        self.add_day.setObjectName("primaryButton")
        self.add_day.clicked.connect(self._add_for_day)
        agenda_col.addWidget(self.day_title)
        agenda_col.addWidget(self.day_list, 1)
        agenda_col.addWidget(self.add_day)
        calendar_row.addWidget(agenda)
        self.stack.addWidget(calendar_page)
        outer.addWidget(self.stack, 1)
        self.set_mode("tasks")

    def _mode_button(self, text: str, mode: str):
        button = QToolButton()
        button.setText(text)
        button.setCheckable(True)
        button.setObjectName("modeButton")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(lambda _checked=False: self.set_mode(mode))
        return button

    def set_mode(self, mode: str):
        self._mode = "calendar" if mode == "calendar" else "tasks"
        self.stack.setCurrentIndex(1 if self._mode == "calendar" else 0)
        self.mode_tasks.setChecked(self._mode == "tasks")
        self.mode_calendar.setChecked(self._mode == "calendar")
        self.title.setText("تقویم" if self._mode == "calendar" else "کارهای من")
        self._fill()

    def set_tasks(self, tasks):
        self._tasks = list(tasks)
        self.calendar.set_marked_days({t.due.date() for t in self._tasks if t.due and not t.done})
        self._fill()

    def _fill(self):
        now = datetime.now()
        open_tasks = [task for task in sort_for_today(self._tasks, now) if not task.done]
        overdue = sum(1 for task in open_tasks if task.overdue)
        self.summary.setText(to_persian_digits(f"{len(open_tasks)} کار باز · {overdue} عقب‌افتاده · از همهٔ یادداشت‌ها"))
        self.list.clear()
        buckets = {}
        for task in self._tasks:
            label = "انجام‌شده" if task.done else group_of(task, now)
            buckets.setdefault(label, []).append(task)
        for label in GROUP_ORDER:
            items = buckets.get(label, [])
            if not items:
                continue
            self.list.add_header(label, to_persian_digits(str(len(items))), label == "عقب‌افتاده")
            for task in items:
                self.list.add_task(task, when_label(task, now), Path(task.path).name if task.path else "")
        if not self._tasks:
            self.list.add_empty("هنوز کاری ثبت نشده")
        self._fill_day(self.calendar.selected_day())

    def _fill_day(self, day: date):
        self.day_title.setText(format_long(day))
        self.day_list.clear()
        items = [task for task in self._tasks if task.due and task.due.date() == day]
        for task in sorted(items, key=lambda t: (t.done, t.due)):
            self.day_list.add_task(task, when_label(task))
        if not items:
            self.day_list.add_empty("برای این روز کاری نیست")

    def _select_day(self, day):
        self._fill_day(day)

    def _add_for_day(self):
        self.task_added.emit(self.calendar.selected_day(), "")

    def _open_item(self, item):
        payload = self.list.payload_of(item)
        if payload:
            self.task_opened.emit(*payload)

    def _task_for_item(self, item):
        payload = self.list.payload_of(item)
        if not payload:
            return None
        return next((task for task in self._tasks if (task.path, task.line_number) == payload), None)

    def _show_detail(self, item, _previous=None):
        task = self._task_for_item(item)
        if task is None:
            self.detail_title.setText("یک کار را انتخاب کن تا جزئیاتش اینجا دیده شود.")
            self.detail_meta.clear()
            self.detail_open.setEnabled(False)
            return
        self.detail_title.setText(task.text)
        self.detail_meta.setText(
            (when_label(task) or "بدون تاریخ") + "\n" + (Path(task.path).name if task.path else "")
        )
        self.detail_open.setEnabled(True)

    def _open_selected(self):
        item = self.list.currentItem()
        payload = self.list.payload_of(item)
        if payload:
            self.task_opened.emit(*payload)

    def _open_day_item(self, item):
        payload = self.day_list.payload_of(item)
        if payload:
            self.task_opened.emit(*payload)
