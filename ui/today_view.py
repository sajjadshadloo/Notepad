"""Ctrl+T — every unfinished dated task across the notes folder, in one place.

Three ways to look at the same list, because "what is late" and "what is my
day shaped like" are different questions:

* **لیست** groups by urgency — overdue, today, tomorrow, later, undated.
* **امروز و آینده** splits today away from everything after it.
* **تایم‌لاین** lays today's dated work out against the clock.

Selecting a task opens the note at that exact line, so this stays a view over
the files rather than a second place where work lives.
"""
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.jalali import format_long, to_persian_digits
from core.tasks import Task, group_of, sort_for_today
from ui.reminder_service import scan_folder
from ui.task_rows import TaskList, when_label

# Urgency order, and the order the groups are shown in.
GROUP_ORDER = ("عقب‌افتاده", "امروز", "فردا", "بعداً", "بدون تاریخ")

MODES = (("list", "لیست"), ("split", "امروز و آینده"), ("timeline", "تایم‌لاین"))

# The spine of a working day. Hours outside it appear only when something is
# actually scheduled there, so the timeline never scrolls through dead time.
WORKDAY_HOURS = (8, 9, 10, 11, 12, 14, 16, 18)


class TodayDialog(QDialog):
    task_chosen = pyqtSignal(str, int)
    # Handled by the main window rather than written here: the note may be
    # open with unsaved edits, and writing underneath it would lose them.
    snooze_requested = pyqtSignal(str, int, int)

    def __init__(self, root: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("کارهای من")
        self.setModal(True)
        self.setMinimumSize(880, 560)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._root = root
        self._tasks: list[Task] = []
        self._selected: Task | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(12)

        outer.addLayout(self._build_header())

        body = QHBoxLayout()
        body.setSpacing(14)
        self._stack = QStackedWidget()
        self._list_tree = self._make_tree()
        self._today_tree = self._make_tree()
        self._ahead_tree = self._make_tree()
        self._timeline_tree = self._make_tree()
        self._stack.addWidget(self._list_tree)
        self._stack.addWidget(self._build_split())
        self._stack.addWidget(self._timeline_tree)
        body.addWidget(self._stack, 1)
        body.addWidget(self._build_detail())
        outer.addLayout(body, 1)

        self.summary = QLabel()
        self.summary.setObjectName("taskSummary")
        outer.addWidget(self.summary)

        self.reload()

    # Construction

    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)
        heading = QLabel(format_long(datetime.now().date()))
        heading.setObjectName("taskHeading")
        row.addWidget(heading)
        row.addStretch(1)

        switch = QWidget()
        switch.setObjectName("taskSwitch")
        switch_row = QHBoxLayout(switch)
        switch_row.setContentsMargins(0, 0, 0, 0)
        switch_row.setSpacing(2)
        self._mode_buttons: dict[str, QToolButton] = {}
        for key, label in MODES:
            button = QToolButton()
            button.setText(label)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            # Equal thirds, like the sidebar's switch — a stretch factor is
            # ignored by QToolButton's default fixed size policy.
            button.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
            )
            button.clicked.connect(lambda _checked, k=key: self.set_mode(k))
            switch_row.addWidget(button, 1)
            self._mode_buttons[key] = button
        self._mode_buttons["list"].setChecked(True)
        row.addWidget(switch)
        return row

    def _make_tree(self) -> TaskList:
        """One task list, drawn by the shared delegate."""
        tree = TaskList()
        tree.itemActivated.connect(self._choose)
        tree.itemClicked.connect(self._choose)
        tree.currentItemChanged.connect(lambda current, _prev: self._select(current))
        return tree

    def _build_split(self) -> QWidget:
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)
        for title, tree in (("امروز", self._today_tree), ("آینده", self._ahead_tree)):
            column = QWidget()
            column.setObjectName("splitColumn")
            inner = QVBoxLayout(column)
            inner.setContentsMargins(10, 10, 10, 10)
            inner.setSpacing(6)
            label = QLabel(title)
            label.setObjectName("splitColumnTitle")
            inner.addWidget(label)
            inner.addWidget(tree, 1)
            row.addWidget(column, 1)
        return holder

    def _build_detail(self) -> QWidget:
        panel = QWidget()
        panel.setFixedWidth(250)
        column = QVBoxLayout(panel)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(8)

        caption = QLabel("جزئیات کار")
        caption.setObjectName("sidebarSectionLabel")
        column.addWidget(caption)

        self.detail_text = QLabel("کاری انتخاب نشده")
        self.detail_text.setWordWrap(True)
        column.addWidget(self.detail_text)

        self.detail_when = QLabel()
        self.detail_when.setObjectName("statusLabel")
        column.addWidget(self.detail_when)

        self.detail_note = QLabel()
        self.detail_note.setObjectName("statusLabel")
        self.detail_note.setWordWrap(True)
        column.addWidget(self.detail_note)

        column.addStretch(1)

        self.open_button = QPushButton("باز کردن یادداشت")
        self.open_button.clicked.connect(self._open_selected)
        column.addWidget(self.open_button)

        self.snooze_button = QPushButton("تعویق به فردا")
        self.snooze_button.setToolTip("تاریخ این کار یک روز جلو می‌رود")
        self.snooze_button.clicked.connect(self._snooze_selected)
        column.addWidget(self.snooze_button)

        self._set_detail(None)
        return panel

    # Data

    def set_mode(self, mode: str):
        for key, button in self._mode_buttons.items():
            button.setChecked(key == mode)
        self._stack.setCurrentIndex([k for k, _ in MODES].index(mode))

    def reload(self):
        now = datetime.now()
        self._tasks = sort_for_today(scan_folder(self._root), now)
        self._fill_list(now)
        self._fill_split(now)
        self._fill_timeline(now)
        self._fill_summary(now)
        self._set_detail(None)

    def _add_task(self, tree, task: Task, now: datetime):
        tree.add_task(
            task,
            when=when_label(task, now),
            tooltip=task.text + chr(10) + Path(task.path).name,
        )

    def _fill_list(self, now: datetime):
        self._list_tree.clear()
        buckets: dict[str, list[Task]] = {}
        for task in self._tasks:
            buckets.setdefault(group_of(task, now), []).append(task)
        for title in GROUP_ORDER:
            tasks = buckets.get(title)
            if not tasks:
                continue
            self._list_tree.add_header(
                title,
                to_persian_digits(str(len(tasks))),
                urgent=title == "عقب‌افتاده",
            )
            for task in tasks:
                self._add_task(self._list_tree, task, now)
        if not self._tasks:
            self._list_tree.add_empty("کاری باقی نمانده ✓")

    def _fill_split(self, now: datetime):
        self._today_tree.clear()
        self._ahead_tree.clear()
        for task in self._tasks:
            due = task.next_due(now)
            target = (
                self._today_tree
                if due is not None and due.date() <= now.date()
                else self._ahead_tree
            )
            self._add_task(target, task, now)
        for tree, empty in (
            (self._today_tree, "امروز کاری نیست ✓"),
            (self._ahead_tree, "چیزی در پیش نیست"),
        ):
            if tree.count() == 0:
                tree.add_empty(empty)

    def _fill_timeline(self, now: datetime):
        """Today's dated work against the clock, undated work at the end."""
        self._timeline_tree.clear()
        today: dict[int, list[Task]] = {}
        loose: list[Task] = []
        for task in self._tasks:
            due = task.next_due(now)
            if due is not None and due.date() == now.date() and task.has_time:
                today.setdefault(due.hour, []).append(task)
            elif due is None:
                loose.append(task)
        for hour in sorted(set(WORKDAY_HOURS) | set(today)):
            at_hour = today.get(hour, [])
            self._timeline_tree.add_header(
                to_persian_digits("%02d:00" % hour),
                to_persian_digits(str(len(at_hour))) if at_hour else "",
            )
            for task in at_hour:
                self._add_task(self._timeline_tree, task, now)
        if loose:
            self._timeline_tree.add_header(
                "بدون ساعت", to_persian_digits(str(len(loose)))
            )
            for task in loose:
                self._add_task(self._timeline_tree, task, now)

    def _fill_summary(self, now: datetime):
        overdue = sum(1 for t in self._tasks if t.overdue)
        today = sum(
            1
            for t in self._tasks
            if (due := t.next_due(now)) and due.date() == now.date()
        )
        self.summary.setText(
            to_persian_digits(
                f"{len(self._tasks)} کار باز · {overdue} عقب‌افتاده · "
                f"{today} برای امروز"
            )
        )

    # Selection

    def _task_at(self, item) -> Task | None:
        """The task a row stands for, whichever of the four lists it is in."""
        if item is None:
            return None
        for tree in (
            self._list_tree,
            self._today_tree,
            self._ahead_tree,
            self._timeline_tree,
        ):
            payload = tree.payload_of(item)
            if payload:
                path, line = payload
                return next(
                    (
                        t
                        for t in self._tasks
                        if t.path == path and t.line_number == line
                    ),
                    None,
                )
        return None

    def _select(self, item):
        self._set_detail(self._task_at(item))

    def _set_detail(self, task: Task | None):
        self._selected = task
        self.detail_text.setText(task.text if task else "کاری انتخاب نشده")
        self.detail_when.setText(when_label(task) if task else "")
        self.detail_note.setText(Path(task.path).name if task else "")
        # Only a dated task can be pushed to tomorrow.
        self.snooze_button.setEnabled(bool(task and task.due))
        self.open_button.setEnabled(task is not None)

    def _choose(self, item):
        task = self._task_at(item)
        if task is not None:
            self.task_chosen.emit(task.path, task.line_number)
            self.accept()

    def _open_selected(self):
        if self._selected is not None:
            self.task_chosen.emit(self._selected.path, self._selected.line_number)
            self.accept()

    def _snooze_selected(self):
        task = self._selected
        if task is None or task.due is None:
            return
        self.snooze_requested.emit(task.path, task.line_number, 1)
        self.reload()
