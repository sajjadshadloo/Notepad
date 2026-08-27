"""Ctrl+T — every unfinished dated task across the notes folder, in one place.

Three ways to look at the same list, because "what is late" and "what is my
day shaped like" are different questions:

* **لیست** groups by urgency — overdue, today, tomorrow, later, undated.
* **امروز و آینده** splits today away from everything after it.
* **تایم‌لاین** lays today's dated work out against the clock.

Selecting a task fills the panel on the left; opening one jumps to that exact
line, so this stays a view over the files rather than a second place where
work lives.
"""
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
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
from ui.task_cards import TaskCardList
from ui.task_rows import when_label

# Urgency order, and the order the groups are shown in.
GROUP_ORDER = ("عقب‌افتاده", "امروز", "فردا", "بعداً", "بدون تاریخ")

MODES = (("list", "لیست"), ("split", "امروز و آینده"), ("timeline", "تایم‌لاین"))

# The spine of a working day. Hours outside it appear only when something is
# actually scheduled there, so the timeline never scrolls through dead time.
WORKDAY_HOURS = (8, 9, 10, 11, 12, 14, 16, 18)

DETAIL_WIDTH = 290


class TodayDialog(QDialog):
    task_chosen = pyqtSignal(str, int)
    # Handled by the main window rather than written here: the note may be
    # open with unsaved edits, and writing underneath it would lose them.
    snooze_requested = pyqtSignal(str, int, int)

    def __init__(self, root: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("کارهای من")
        self.setModal(True)
        self.setMinimumSize(980, 620)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._root = root
        self._tasks: list[Task] = []
        self._selected: Task | None = None

        body = QHBoxLayout(self)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        main = QWidget()
        column = QVBoxLayout(main)
        column.setContentsMargins(26, 22, 26, 26)
        column.setSpacing(14)
        column.addLayout(self._build_header())

        self._stack = QStackedWidget()
        self._list_tree = self._make_list()
        self._today_tree = self._make_list()
        self._ahead_tree = self._make_list()
        self._timeline_tree = self._make_list()
        self._stack.addWidget(self._list_tree)
        self._stack.addWidget(self._build_split())
        self._stack.addWidget(self._timeline_tree)
        column.addWidget(self._stack, 1)

        body.addWidget(main, 1)
        body.addWidget(self._build_detail())

        self.reload()

    # Construction

    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(16)

        titles = QVBoxLayout()
        titles.setSpacing(6)
        self.heading = QLabel(format_long(datetime.now().date()))
        self.heading.setObjectName("taskHeading")
        self.summary = QLabel()
        self.summary.setObjectName("taskSummary")
        titles.addWidget(self.heading)
        titles.addWidget(self.summary)
        row.addLayout(titles)
        row.addStretch(1)

        switch = QWidget()
        switch.setObjectName("taskSwitch")
        switch.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        switch_row = QHBoxLayout(switch)
        switch_row.setContentsMargins(0, 0, 0, 0)
        switch_row.setSpacing(3)
        self._mode_buttons: dict[str, QToolButton] = {}
        for key, label in MODES:
            button = QToolButton()
            button.setText(label)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked, k=key: self.set_mode(k))
            switch_row.addWidget(button)
            self._mode_buttons[key] = button
        self._mode_buttons["list"].setChecked(True)
        row.addWidget(switch, 0, Qt.AlignmentFlag.AlignBottom)
        return row

    def _make_list(self) -> TaskCardList:
        cards = TaskCardList()
        cards.itemActivated.connect(self._choose)
        cards.currentItemChanged.connect(lambda current, _prev: self._select(current))
        return cards

    def _build_split(self) -> QWidget:
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(18)
        self._split_counts: dict[str, QLabel] = {}
        for title, cards in (
            ("امروز", self._today_tree),
            ("آینده", self._ahead_tree),
        ):
            column = QWidget()
            column.setObjectName("splitColumn")
            column.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            inner = QVBoxLayout(column)
            inner.setContentsMargins(14, 14, 14, 14)
            inner.setSpacing(10)
            head = QHBoxLayout()
            label = QLabel(title)
            label.setObjectName("splitColumnTitle")
            count = QLabel()
            count.setObjectName("splitColumnCount")
            head.addWidget(label)
            head.addStretch(1)
            head.addWidget(count)
            self._split_counts[title] = count
            inner.addLayout(head)
            inner.addWidget(cards, 1)
            row.addWidget(column, 1)
        return holder

    def _build_detail(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("taskDetail")
        panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        panel.setFixedWidth(DETAIL_WIDTH)
        column = QVBoxLayout(panel)
        column.setContentsMargins(18, 22, 18, 22)
        column.setSpacing(14)

        caption = QLabel("جزئیات کار")
        caption.setObjectName("sidebarSectionLabel")
        column.addWidget(caption)

        self.detail_text = QLabel()
        self.detail_text.setObjectName("detailTitle")
        self.detail_text.setWordWrap(True)
        column.addWidget(self.detail_text)

        pills = QHBoxLayout()
        pills.setSpacing(6)
        self.detail_when = QLabel()
        self.detail_when.setObjectName("detailPill")
        self.detail_repeat = QLabel("↻ هر هفته")
        self.detail_repeat.setObjectName("detailPill")
        pills.addWidget(self.detail_when)
        pills.addWidget(self.detail_repeat)
        pills.addStretch(1)
        column.addLayout(pills)

        rule = QFrame()
        rule.setObjectName("detailRule")
        rule.setFrameShape(QFrame.Shape.HLine)
        column.addWidget(rule)

        self.detail_note = self._detail_row(column, "یادداشت")
        self.detail_line = self._detail_row(column, "خط")
        self.detail_state = self._detail_row(column, "وضعیت")

        column.addStretch(1)

        self.open_button = QPushButton("باز کردن در یادداشت")
        self.open_button.setObjectName("primaryButton")
        self.open_button.clicked.connect(self._open_selected)
        column.addWidget(self.open_button)

        self.snooze_button = QPushButton("تعویق به فردا")
        self.snooze_button.setToolTip("تاریخ این کار یک روز جلو می‌رود")
        self.snooze_button.clicked.connect(self._snooze_selected)
        column.addWidget(self.snooze_button)

        self._set_detail(None)
        return panel

    def _detail_row(self, column: QVBoxLayout, label: str) -> QLabel:
        row = QHBoxLayout()
        row.setSpacing(10)
        name = QLabel(label)
        name.setObjectName("detailKey")
        value = QLabel()
        value.setObjectName("detailValue")
        value.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        value.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        row.addWidget(name)
        row.addWidget(value, 1)
        column.addLayout(row)
        return value

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

    def _add_card(self, cards: TaskCardList, task: Task, now: datetime, **kwargs):
        cards.add_card(
            task,
            when=when_label(task, now),
            note=Path(task.path).name if task.path else "",
            **kwargs,
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
                self._add_card(self._list_tree, task, now)
        if not self._tasks:
            self._list_tree.add_empty("کاری باقی نمانده ✓")

    def _fill_split(self, now: datetime):
        self._today_tree.clear()
        self._ahead_tree.clear()
        counts = {"امروز": 0, "آینده": 0}
        for task in self._tasks:
            due = task.next_due(now)
            today = due is not None and due.date() <= now.date()
            self._add_card(
                self._today_tree if today else self._ahead_tree, task, now
            )
            counts["امروز" if today else "آینده"] += 1
        for title, cards, empty in (
            ("امروز", self._today_tree, "امروز کاری نیست ✓"),
            ("آینده", self._ahead_tree, "چیزی در پیش نیست"),
        ):
            if cards.count() == 0:
                cards.add_empty(empty)
            self._split_counts[title].setText(
                to_persian_digits(str(counts[title]))
            )

    def _fill_timeline(self, now: datetime):
        """Today's dated work against the clock, undated work at the end."""
        from ui.styles import current_palette

        self._timeline_tree.clear()
        accent = current_palette()["accent"]
        today: dict[int, list[Task]] = {}
        loose: list[Task] = []
        for task in self._tasks:
            due = task.next_due(now)
            if due is not None and due.date() == now.date() and task.has_time:
                today.setdefault(due.hour, []).append(task)
            elif due is None:
                loose.append(task)
        for hour in sorted(set(WORKDAY_HOURS) | set(today)):
            self._timeline_tree.add_hour(
                to_persian_digits("%02d:00" % hour), now=hour == now.hour
            )
            for task in today.get(hour, []):
                self._add_card(
                    self._timeline_tree, task, now, timeline=True, rail=accent
                )
        if loose:
            self._timeline_tree.add_header(
                "بدون ساعت", to_persian_digits(str(len(loose)))
            )
            for task in loose:
                self._add_card(self._timeline_tree, task, now)

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
        for cards in (
            self._list_tree,
            self._today_tree,
            self._ahead_tree,
            self._timeline_tree,
        ):
            payload = cards.payload_of(item)
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
        when = when_label(task) if task else ""
        self.detail_when.setText(when)
        self.detail_when.setVisible(bool(when))
        self.detail_repeat.setVisible(bool(task and task.repeats))
        self.detail_note.setText(Path(task.path).name if task else "—")
        self.detail_line.setText(
            to_persian_digits(str(task.line_number + 1)) if task else "—"
        )
        if task is None:
            self.detail_state.setText("—")
        elif task.done:
            self.detail_state.setText("انجام شده")
        elif task.overdue:
            self.detail_state.setText("عقب‌افتاده")
        else:
            self.detail_state.setText("باز")
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
