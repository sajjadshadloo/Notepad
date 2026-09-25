"""A compact Jalali month grid.

Clicking a day picks it. Days that carry work are marked, so the month
doubles as a map of where the week is heavy — the caller says which those
are, because 4.2 stopped keeping a file per day and the grid can no longer
read that off the folder.
"""
from datetime import date

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

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

    def __init__(self, root: str = "", parent=None, expanded: bool = False):
        super().__init__(parent)
        self.setObjectName("calendarPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._root = root
        self._expanded = bool(expanded)
        # Days that have at least one task. Set by whoever owns the tasks.
        self._marked: set = set()
        self._selected = date.today()
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
        header.addWidget(self._next)
        header.addWidget(self._title, 1)
        header.addWidget(self._previous)
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

    def set_expanded(self, expanded: bool = True):
        """Use the generous month cells from the full V4 calendar page."""
        self._expanded = bool(expanded)
        self.refresh()

    def set_marked_days(self, days):
        """Which days to show as carrying work."""
        marked = set(days)
        if marked != self._marked:
            self._marked = marked
            self.refresh()

    def selected_day(self):
        return self._selected

    def choose(self, day):
        """Pick a day, redraw the highlight, and tell whoever is listening."""
        self._selected = day
        self.refresh()
        self.day_activated.emit(day)

    def shift(self, delta: int):
        self._year, self._month = shift_month(self._year, self._month, delta)
        self.refresh()

    def go_to_today(self):
        self._year, self._month, _ = from_gregorian(date.today())
        self.choose(date.today())

    def refresh(self):
        self._title.setText(
            to_persian_digits(f"{MONTHS[self._month - 1]} {self._year}")
        )
        for cell in self._cells:
            self._grid.removeWidget(cell)
            cell.deleteLater()
        self._cells.clear()

        today = date.today()
        row = 1
        occupied = set()
        for day in month_days(self._year, self._month):
            column = column_of(day)
            _, _, jd = from_gregorian(day)
            cell = QToolButton()
            cell.setText(to_persian_digits(str(jd)))
            cell.setAutoRaise(not self._expanded)
            cell.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            cell.setCursor(Qt.CursorShape.PointingHandCursor)
            cell.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Expanding if self._expanded else QSizePolicy.Policy.Fixed,
            )
            cell.setMinimumSize(QSize(44, 68) if self._expanded else QSize(24, 24))
            cell.setProperty("expanded", self._expanded)
            cell.setProperty("empty", False)
            cell.setProperty("today", day == today)
            # A dot rather than a colour, so it still reads in either theme.
            carries_work = day in self._marked
            cell.setProperty("written", carries_work)
            cell.setProperty("chosen", day == self._selected)
            if carries_work:
                bold = QFont(cell.font())
                bold.setBold(True)
                cell.setFont(bold)
            if column == FRIDAY_COLUMN:
                cell.setProperty("holiday", True)
            cell.setObjectName("calendarDay")
            cell.clicked.connect(lambda _checked=False, d=day: self.choose(d))
            self._grid.addWidget(cell, row, column)
            self._cells.append(cell)
            occupied.add((row, column))
            if column == FRIDAY_COLUMN:
                row += 1
        if self._expanded:
            last_row = max((position[0] for position in occupied), default=1)
            for empty_row in range(1, last_row + 1):
                for empty_column in range(7):
                    if (empty_row, empty_column) in occupied:
                        continue
                    filler = QToolButton()
                    filler.setObjectName("calendarDay")
                    filler.setEnabled(False)
                    filler.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                    filler.setProperty("expanded", True)
                    filler.setProperty("empty", True)
                    filler.setSizePolicy(
                        QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
                    )
                    filler.setMinimumSize(QSize(44, 68))
                    self._grid.addWidget(filler, empty_row, empty_column)
                    self._cells.append(filler)
