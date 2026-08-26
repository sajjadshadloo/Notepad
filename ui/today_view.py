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
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.jalali import format_date, format_long, to_persian_digits
from core.tasks import REPEAT_MARK, Task, group_of, sort_for_today
from ui.reminder_service import scan_folder
from ui.styles import current_palette

# Urgency order, and the order the groups are shown in.
GROUP_ORDER = ("عقب‌افتاده", "امروز", "فردا", "بعداً", "بدون تاریخ")

MODES = (("list", "لیست"), ("split", "امروز و آینده"), ("timeline", "تایم‌لاین"))

# The spine of a working day. Hours outside it appear only when something is
# actually scheduled there, so the timeline never scrolls through dead time.
WORKDAY_HOURS = (8, 9, 10, 11, 12, 14, 16, 18)


def when_label(task: Task, now: datetime | None = None) -> str:
    """The due moment as the user would write it, or '' for an undated task."""
    due = task.next_due(now)
    if due is None:
        return ""
    text = format_date(due.date())
    if task.has_time:
        text += to_persian_digits(due.strftime(" %H:%M"))
    if task.repeats:
        text += " " + REPEAT_MARK
    return text


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
            button.clicked.connect(lambda _checked, k=key: self.set_mode(k))
            switch_row.addWidget(button)
            self._mode_buttons[key] = button
        self._mode_buttons["list"].setChecked(True)
        row.addWidget(switch)
        return row

    def _make_tree(self) -> QTreeWidget:
        tree = QTreeWidget()
        tree.setObjectName("noteList")
        tree.setHeaderHidden(True)
        tree.setIndentation(12)
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

    def _colors(self) -> tuple[QColor, QColor]:
        palette = current_palette()
        return QColor(palette["danger"]), QColor(palette["muted"])

    def _task_item(self, task: Task, now: datetime) -> QTreeWidgetItem:
        overdue, _muted = self._colors()
        label = task.text
        when = when_label(task, now)
        if when:
            label = f"{label}   ·   {when}"
        item = QTreeWidgetItem([f"☐  {label}"])
        item.setData(0, Qt.ItemDataRole.UserRole, task)
        item.setToolTip(0, f"{Path(task.path).name}  ({task.path})")
        if task.overdue:
            item.setForeground(0, overdue)
        return item

    def _group_header(self, title: str, count: int, tree: QTreeWidget):
        overdue, muted = self._colors()
        parent = QTreeWidgetItem([f"{title}   {to_persian_digits(str(count))}"])
        bold = QFont(tree.font())
        bold.setBold(True)
        parent.setFont(0, bold)
        parent.setForeground(0, overdue if title == "عقب‌افتاده" else muted)
        tree.addTopLevelItem(parent)
        parent.setExpanded(True)
        return parent

    def _fill_list(self, now: datetime):
        self._list_tree.clear()
        buckets: dict[str, list[Task]] = {}
        for task in self._tasks:
            buckets.setdefault(group_of(task, now), []).append(task)
        for title in GROUP_ORDER:
            tasks = buckets.get(title)
            if not tasks:
                continue
            parent = self._group_header(title, len(tasks), self._list_tree)
            for task in tasks:
                parent.addChild(self._task_item(task, now))
        if not self._tasks:
            self._list_tree.addTopLevelItem(QTreeWidgetItem(["کاری باقی نمانده ✓"]))

    def _fill_split(self, now: datetime):
        self._today_tree.clear()
        self._ahead_tree.clear()
        for task in self._tasks:
            due = task.next_due(now)
            if due is not None and due.date() <= now.date():
                self._today_tree.addTopLevelItem(self._task_item(task, now))
            else:
                self._ahead_tree.addTopLevelItem(self._task_item(task, now))
        for tree, empty in (
            (self._today_tree, "امروز کاری نیست ✓"),
            (self._ahead_tree, "چیزی در پیش نیست"),
        ):
            if tree.topLevelItemCount() == 0:
                tree.addTopLevelItem(QTreeWidgetItem([empty]))

    def _fill_timeline(self, now: datetime):
        """Today's dated work against the clock, undated work at the end."""
        self._timeline_tree.clear()
        _overdue, muted = self._colors()
        today: dict[int, list[Task]] = {}
        loose: list[Task] = []
        for task in self._tasks:
            due = task.next_due(now)
            if due is not None and due.date() == now.date() and task.has_time:
                today.setdefault(due.hour, []).append(task)
            elif due is None:
                loose.append(task)
        for hour in sorted(set(WORKDAY_HOURS) | set(today)):
            parent = QTreeWidgetItem([to_persian_digits(f"{hour:02d}:00")])
            bold = QFont(self._timeline_tree.font())
            bold.setBold(hour == now.hour)
            parent.setFont(0, bold)
            parent.setForeground(0, muted)
            self._timeline_tree.addTopLevelItem(parent)
            parent.setExpanded(True)
            for task in today.get(hour, []):
                parent.addChild(self._task_item(task, now))
        if loose:
            parent = self._group_header(
                "بدون ساعت", len(loose), self._timeline_tree
            )
            for task in loose:
                parent.addChild(self._task_item(task, now))

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

    def _select(self, item: QTreeWidgetItem | None):
        task = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        self._set_detail(task if isinstance(task, Task) else None)

    def _set_detail(self, task: Task | None):
        self._selected = task
        self.detail_text.setText(task.text if task else "کاری انتخاب نشده")
        self.detail_when.setText(when_label(task) if task else "")
        self.detail_note.setText(Path(task.path).name if task else "")
        # Only a dated task can be pushed to tomorrow.
        self.snooze_button.setEnabled(bool(task and task.due))
        self.open_button.setEnabled(task is not None)

    def _choose(self, item: QTreeWidgetItem):
        task = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(task, Task):
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
