"""A compact Jalali month grid for the sidebar.

Clicking a day opens that day's note. Days that already have one are marked,
so the month doubles as a map of what you have actually written down.
"""
from datetime import date

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core import daily_notes
from core.jalali import (
    MONTHS,
    column_of,
    from_gregorian,
    month_days,
    shift_month,
    to_persian_digits,
)

# Saturday first, the way a Persian calendar is laid out.
WEEKDAY_INITIALS = ("ش", "ی", "د", "س", "چ", "پ", "ج")
FRIDAY_COLUMN = 6


class CalendarPanel(QWidget):
    day_activated = pyqtSignal(date)

    def __init__(self, root: str, parent=None):
        super().__init__(parent)
        self.setObjectName("calendarPanel")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._root = root
        today = date.today()
        self._year, self._month, _ = from_gregorian(today)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 6)
        outer.setSpacing(4)

        header = QHBoxLayout()
        header.setSpacing(2)
        self._previous = self._arrow("‹", -1)
        self._next = self._arrow("›", 1)
        self._title = QLabel()
        self._title.setObjectName("sidebarHeader")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._today_button = QPushButton("امروز")
        self._today_button.setObjectName("tagChip")
        self._today_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._today_button.clicked.connect(self.go_to_today)
        header.addWidget(self._next)
        header.addWidget(self._title, 1)
        header.addWidget(self._previous)
        header.addWidget(self._today_button)
        outer.addLayout(header)

        self._grid = QGridLayout()
        self._grid.setSpacing(1)
        outer.addLayout(self._grid)

        for column, initial in enumerate(WEEKDAY_INITIALS):
            label = QLabel(initial)
            label.setObjectName("calendarWeekday")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._grid.addWidget(label, 0, column)

        self._cells: list[QToolButton] = []
        self.refresh()

    def _arrow(self, glyph: str, delta: int) -> QToolButton:
        button = QToolButton()
        button.setText(glyph)
        button.setAutoRaise(True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFixedSize(22, 22)
        button.clicked.connect(lambda: self.shift(delta))
        return button

    def set_root(self, root: str):
        self._root = root
        self.refresh()

    def shift(self, delta: int):
        self._year, self._month = shift_month(self._year, self._month, delta)
        self.refresh()

    def go_to_today(self):
        self._year, self._month, _ = from_gregorian(date.today())
        self.refresh()
        self.day_activated.emit(date.today())

    def refresh(self):
        self._title.setText(
            to_persian_digits(f"{MONTHS[self._month - 1]} {self._year}")
        )
        for cell in self._cells:
            self._grid.removeWidget(cell)
            cell.deleteLater()
        self._cells.clear()

        written = daily_notes.existing_days(self._root)
        today = date.today()
        row = 1
        for day in month_days(self._year, self._month):
            column = column_of(day)
            _, _, jd = from_gregorian(day)
            cell = QToolButton()
            cell.setText(to_persian_digits(str(jd)))
            cell.setAutoRaise(True)
            cell.setCursor(Qt.CursorShape.PointingHandCursor)
            cell.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            cell.setMinimumSize(QSize(24, 24))
            cell.setProperty("today", day == today)
            # A dot rather than a colour, so it still reads in either theme.
            stem = daily_notes.path_for(self._root, day).stem
            cell.setProperty("written", stem in written)
            if stem in written:
                bold = QFont(cell.font())
                bold.setBold(True)
                cell.setFont(bold)
            if column == FRIDAY_COLUMN:
                cell.setProperty("holiday", True)
            cell.setObjectName("calendarDay")
            cell.clicked.connect(lambda _checked=False, d=day: self.day_activated.emit(d))
            self._grid.addWidget(cell, row, column)
            self._cells.append(cell)
            if column == FRIDAY_COLUMN:
                row += 1
