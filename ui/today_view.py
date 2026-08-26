"""Ctrl+T — every unfinished dated task across the notes folder, in one list.

Overdue first, then today, then what is coming. Selecting one opens the note
at that exact line, so the list stays a view over the files rather than a
second place where work lives.
"""
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QDialog,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from core.jalali import format_date, format_long, to_persian_digits
from core.tasks import Task, sort_for_today
from ui.reminder_service import scan_folder
from ui.styles import current_palette


def group_of(task: Task, now: datetime) -> str:
    if task.due is None:
        return "بدون تاریخ"
    if task.due < now:
        return "عقب‌افتاده"
    if task.due.date() == now.date():
        return "امروز"
    if (task.due.date() - now.date()).days == 1:
        return "فردا"
    return "بعداً"


class TodayDialog(QDialog):
    task_chosen = pyqtSignal(str, int)

    def __init__(self, root: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("کارهای من")
        self.setModal(True)
        self.setMinimumSize(620, 460)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        now = datetime.now()
        heading = QLabel(format_long(now.date()))
        heading.setObjectName("sidebarHeader")
        font = QFont(heading.font())
        font.setPointSizeF(font.pointSizeF() * 1.25)
        font.setBold(True)
        heading.setFont(font)
        layout.addWidget(heading)

        self.tree = QTreeWidget()
        self.tree.setObjectName("noteList")
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(12)
        self.tree.itemActivated.connect(self._choose)
        self.tree.itemClicked.connect(self._choose)
        layout.addWidget(self.tree, 1)

        self.summary = QLabel()
        self.summary.setObjectName("statusLabel")
        layout.addWidget(self.summary)

        self._populate(root, now)

    def _populate(self, root: str, now: datetime):
        tasks = sort_for_today(scan_folder(root), now)
        palette = current_palette()
        overdue_color = QColor(palette["danger"])
        muted = QColor(palette["muted"])

        groups: dict[str, QTreeWidgetItem] = {}
        for task in tasks:
            name = group_of(task, now)
            parent = groups.get(name)
            if parent is None:
                parent = QTreeWidgetItem([name])
                bold = QFont(self.tree.font())
                bold.setBold(True)
                parent.setFont(0, bold)
                parent.setForeground(0, overdue_color if name == "عقب‌افتاده" else muted)
                self.tree.addTopLevelItem(parent)
                parent.setExpanded(True)
                groups[name] = parent

            when = ""
            if task.due:
                when = format_date(task.due.date())
                if task.has_time:
                    when += to_persian_digits(task.due.strftime(" %H:%M"))
            item = QTreeWidgetItem([f"{task.text}   ·   {when}" if when else task.text])
            item.setData(0, Qt.ItemDataRole.UserRole, (task.path, task.line_number))
            item.setToolTip(0, f"{Path(task.path).name}  ({task.path})")
            if task.overdue:
                item.setForeground(0, overdue_color)
            parent.addChild(item)

        overdue = sum(1 for t in tasks if t.overdue)
        today = sum(1 for t in tasks if t.due and t.due.date() == now.date())
        self.summary.setText(
            to_persian_digits(
                f"{len(tasks)} کار باز · {overdue} عقب‌افتاده · {today} برای امروز"
            )
        )
        if not tasks:
            self.tree.addTopLevelItem(QTreeWidgetItem(["کاری باقی نمانده ✓"]))

    def _choose(self, item: QTreeWidgetItem):
        payload = item.data(0, Qt.ItemDataRole.UserRole)
        if payload:
            self.task_chosen.emit(payload[0], payload[1])
            self.accept()
