"""The month: a Jalali grid on the left, the chosen day on the right.

Only dated tasks appear here, and a task gets its date by being typed into a
day — not by being dragged from a backlog. The backlog was the earlier plan,
until the folder turned out to hold 67 tasks of which one had a date: the
undated ones are notes about projects, not work waiting for a slot, and
sweeping them onto days would invent a schedule nobody asked for.

So a day owns its tasks, and they live in that day's note. The Daily folder
finally earns its place: a file appears when work is put on that day, and
never otherwise.
"""
from datetime import date

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.jalali import (
    MONTHS,
    column_of,
    format_long,
    from_gregorian,
    month_days,
    shift_month,
    to_persian_digits,
)
from core.tasks import Task
from ui.styles import current_palette
from ui.task_rows import TaskList

# Saturday first, the way a Persian calendar is laid out.
WEEKDAY_NAMES = ("شنبه", "یک‌شنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنج‌شنبه", "جمعه")
FRIDAY_COLUMN = 6

DAY_MIN_HEIGHT = 78
PANEL_WIDTH = 300
# Beyond this a cell would rather say "+3" than list them all illegibly.
CELL_TASK_LIMIT = 3


class DayCell(QFrame):
    """One square of the month."""

    chosen = pyqtSignal(date)

    def __init__(self, day: date, in_month: bool, parent=None):
        super().__init__(parent)
        self.day = day
        self._in_month = in_month
        self._tasks: list[Task] = []
        self._today = day == date.today()
        self._selected = False
        self.setObjectName("dayCell")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumHeight(DAY_MIN_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_tasks(self, tasks: list[Task]):
        self._tasks = tasks
        self.update()

    def set_selected(self, selected: bool):
        if selected != self._selected:
            self._selected = selected
            self.update()

    def mousePressEvent(self, event):
        self.chosen.emit(self.day)
        super().mousePressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        palette = current_palette()
        rect = self.rect().adjusted(0, 0, -1, -1)

        if not self._in_month:
            fill = palette["window"]
        elif self._selected:
            fill = palette["surface_alt"]
        else:
            fill = palette["surface"]
        painter.setBrush(QColor(fill))
        border = palette["accent"] if (self._selected or self._today) else palette["border"]
        painter.setPen(QPen(QColor(border), 1.6 if (self._selected or self._today) else 1.0))
        painter.drawRoundedRect(rect, 8, 8)

        _, _, number = from_gregorian(self.day)
        label_font = QFont(self.font())
        label_font.setBold(self._today)
        painter.setFont(label_font)
        if not self._in_month:
            colour = palette["muted"]
        elif self._today:
            colour = palette["accent"]
        else:
            colour = palette["text"]
        painter.setPen(QColor(colour))
        header = rect.adjusted(8, 5, -8, 0)
        painter.drawText(
            header.left(),
            header.top(),
            header.width(),
            18,
            int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
            to_persian_digits(str(number)),
        )

        if not self._tasks:
            painter.end()
            return

        body_font = QFont(self.font())
        body_font.setPointSizeF(max(6.5, self.font().pointSizeF() * 0.84))
        painter.setFont(body_font)
        metrics = painter.fontMetrics()
        y = header.top() + 20
        shown = self._tasks[:CELL_TASK_LIMIT]
        for task in shown:
            if y + metrics.height() > rect.bottom() - 4:
                break
            done = task.done
            painter.setPen(QColor(palette["muted"] if done else palette["text"]))
            font = QFont(body_font)
            font.setStrikeOut(done)
            painter.setFont(font)
            painter.drawText(
                rect.left() + 8,
                y,
                rect.width() - 16,
                metrics.height(),
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                metrics.elidedText(
                    task.text, Qt.TextElideMode.ElideRight, rect.width() - 16
                ),
            )
            y += metrics.height() + 1

        remaining = len(self._tasks) - len(shown)
        if remaining > 0 and y + metrics.height() <= rect.bottom() - 2:
            painter.setFont(body_font)
            painter.setPen(QColor(palette["accent"]))
            painter.drawText(
                rect.left() + 8,
                y,
                rect.width() - 16,
                metrics.height(),
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                to_persian_digits("+" + str(remaining)),
            )
        painter.end()


class MonthView(QWidget):
    """The calendar page: pick a day, see and add its work."""

    task_added = pyqtSignal(object, str)          # (date, text)
    task_toggled = pyqtSignal(str, int, bool)     # (path, line, done)
    task_opened = pyqtSignal(str, int)            # (path, line)
    note_requested = pyqtSignal(object)           # (date) — open the day's note

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("monthView")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        today = date.today()
        self._year, self._month, _ = from_gregorian(today)
        self._selected = today
        self._tasks: list[Task] = []
        self._cells: dict[date, DayCell] = {}

        row = QHBoxLayout(self)
        row.setContentsMargins(18, 16, 18, 18)
        row.setSpacing(16)

        left = QVBoxLayout()
        left.setSpacing(10)
        left.addLayout(self._build_header())
        self._grid = QGridLayout()
        self._grid.setSpacing(6)
        left.addLayout(self._grid, 1)
        row.addLayout(left, 1)
        row.addWidget(self._build_panel())

        self._build_grid()

    # Construction

    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)
        self._title = QLabel()
        self._title.setObjectName("monthTitle")
        # Right-to-left: the arrow pointing right walks back through the
        # months, because that is the direction the calendar itself reads.
        previous = self._arrow("›", -1)
        following = self._arrow("‹", 1)
        today_button = QPushButton("امروز")
        today_button.setObjectName("tagChip")
        today_button.setCursor(Qt.CursorShape.PointingHandCursor)
        today_button.clicked.connect(self.go_to_today)

        row.addWidget(self._title)
        row.addStretch(1)
        row.addWidget(previous)
        row.addWidget(following)
        row.addWidget(today_button)
        return row

    def _arrow(self, glyph: str, delta: int) -> QToolButton:
        button = QToolButton()
        button.setText(glyph)
        button.setAutoRaise(True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFixedSize(QSize(26, 26))
        button.clicked.connect(lambda: self.shift(delta))
        return button

    def _build_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("dayPanel")
        panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        panel.setFixedWidth(PANEL_WIDTH)
        column = QVBoxLayout(panel)
        column.setContentsMargins(16, 16, 16, 16)
        column.setSpacing(12)

        self._day_title = QLabel()
        self._day_title.setObjectName("taskHeading")
        self._day_title.setWordWrap(True)
        column.addWidget(self._day_title)

        self._input = QLineEdit()
        self._input.setObjectName("dayInput")
        self._input.setPlaceholderText("کار جدید برای این روز…")
        self._input.setClearButtonEnabled(True)
        self._input.returnPressed.connect(self._submit)
        column.addWidget(self._input)

        self._list = TaskList()
        self._list.task_toggled.connect(self._toggle)
        self._list.itemActivated.connect(self._open)
        column.addWidget(self._list, 1)

        self._open_note = QPushButton("باز کردن یادداشت روز")
        self._open_note.setObjectName("tagChip")
        self._open_note.setCursor(Qt.CursorShape.PointingHandCursor)
        self._open_note.clicked.connect(
            lambda: self.note_requested.emit(self._selected)
        )
        column.addWidget(self._open_note)
        return panel

    def _build_grid(self):
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._cells.clear()

        for column, name in enumerate(WEEKDAY_NAMES):
            label = QLabel(name)
            label.setObjectName("calendarWeekday")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._grid.addWidget(label, 0, column)

        row = 1
        for day in month_days(self._year, self._month):
            cell = DayCell(day, in_month=True, parent=self)
            cell.chosen.connect(self.select_day)
            self._grid.addWidget(cell, row, column_of(day))
            self._cells[day] = cell
            if column_of(day) == FRIDAY_COLUMN:
                row += 1
        for index in range(7):
            self._grid.setColumnStretch(index, 1)

        self._title.setText(
            to_persian_digits(MONTHS[self._month - 1] + " " + str(self._year))
        )
        self._spread_tasks()
        self._mark_selection()

    # Navigation

    def shift(self, delta: int):
        self._year, self._month = shift_month(self._year, self._month, delta)
        self._build_grid()

    def go_to_today(self):
        today = date.today()
        self._year, self._month, _ = from_gregorian(today)
        self._build_grid()
        self.select_day(today)

    def select_day(self, day: date):
        self._selected = day
        self._mark_selection()
        self._fill_panel()
        self._input.setFocus()

    def _mark_selection(self):
        for day, cell in self._cells.items():
            cell.set_selected(day == self._selected)

    # Data

    def set_tasks(self, tasks: list[Task]):
        """Every dated task in the notes folder; undated ones never appear."""
        self._tasks = [t for t in tasks if t.due is not None]
        self._spread_tasks()
        self._fill_panel()

    def tasks_on(self, day: date) -> list[Task]:
        found = [t for t in self._tasks if t.due and t.due.date() == day]
        found.sort(key=lambda t: (t.done, t.text))
        return found

    def _spread_tasks(self):
        for day, cell in self._cells.items():
            cell.set_tasks(self.tasks_on(day))

    def _fill_panel(self):
        self._day_title.setText(format_long(self._selected))
        self._list.clear()
        tasks = self.tasks_on(self._selected)
        for task in tasks:
            self._list.add_task(task, when="")
        if not tasks:
            self._list.add_empty("کاری برای این روز نیست")

    # Actions

    def _submit(self):
        text = self._input.text().strip()
        if not text:
            return
        self._input.clear()
        self.task_added.emit(self._selected, text)

    def _toggle(self, path: str, line_number: int, done: bool):
        self.task_toggled.emit(path, line_number, done)

    def _open(self, item):
        payload = self._list.payload_of(item)
        if payload:
            self.task_opened.emit(payload[0], payload[1])
