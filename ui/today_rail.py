"""The 340px «امروز» column: the day's work, a quick-add field, and a month.

Header: the day's name and date, a progress bar with «۱ از ۳ انجام شده», and
an input that understands «فردا» or «۱۲ مهر» and says so underneath. Then
the day's tasks — overdue ones first when the day is today — and a compact
Jalali month where days carrying open work wear a dot.
"""
from datetime import date, datetime, timedelta
from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QFontMetricsF, QPainter, QPen
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QMenu,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.jalali import MONTHS, column_of, from_gregorian, month_days, shift_month, to_persian_digits
from core.task_file import FILE_NAME as TASKS_FILE
from core.tasks import Task
from core.when import day_label, parse_preview, parse_when
from ui.kit import (
    Button,
    Clickable,
    col,
    draw_checkbox,
    draw_icon,
    draw_text,
    font,
    kbd,
    rounded,
    text_width,
    tint,
)

RAIL_WIDTH = 340
WEEKDAY_INITIALS = ("ش", "ی", "د", "س", "چ", "پ", "ج")
FRIDAY_COLUMN = 6


def task_source(task: Task) -> str:
    """Where a task lives, as the design names it: the tasks file, or the note."""
    name = Path(task.path).name
    return name if name == TASKS_FILE else Path(task.path).stem


# Pieces

class ProgressBar(QWidget):
    """5px track, accent fill growing from the right."""

    def __init__(self, height: int = 5, parent=None):
        super().__init__(parent)
        self.fraction = 0.0
        self.setFixedHeight(height)

    def set_fraction(self, value: float):
        self.fraction = max(0.0, min(1.0, value))
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self.rect())
        radius = r.height() / 2 + 0.5
        rounded(p, r, radius, fill=col("surface_alt"))
        if self.fraction > 0:
            w = r.width() * self.fraction
            rounded(p, QRectF(r.right() - w, 0, w, r.height()), radius, fill=col("accent"))
        p.end()


class QuickAddField(QWidget):
    """The 40px well with a + on the right, the field, and «Enter» on the left."""

    submitted = pyqtSignal(str)
    text_changed = pyqtSignal(str)

    def __init__(self, placeholder: str, *, height: int = 40, radius: float = 10,
                 px: float = 13, fill: str = "window", show_enter: bool = True,
                 icon_size: float = 14, pad: float = 12, gap: float = 8, parent=None):
        super().__init__(parent)
        self._radius, self._fill, self._show_enter = radius, fill, show_enter
        self._icon_size, self._pad, self._gap = icon_size, pad, gap
        self.setFixedHeight(height)
        row = QHBoxLayout(self)
        enter_w = (text_width("Enter", font(10, mono=True)) + gap) if show_enter else 0
        row.setContentsMargins(round(pad + enter_w), 0, round(pad + icon_size + gap), 0)
        self.edit = QLineEdit()
        self.edit.setObjectName("quickAddEdit")
        self.edit.setPlaceholderText(placeholder)
        self.edit.setFont(font(px))
        self.edit.setFrame(False)
        self.edit.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.edit.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignAbsolute
                               | Qt.AlignmentFlag.AlignVCenter)
        self.edit.returnPressed.connect(self._submit)
        self.edit.textChanged.connect(self.text_changed)
        self.edit.installEventFilter(self)
        row.addWidget(self.edit)
        self._style_edit()

    def _style_edit(self):
        from ui.styles import current_palette

        t = current_palette()
        self.edit.setStyleSheet(
            f"QLineEdit {{ background: transparent; border: none; padding: 0;"
            f" color: {t['text']}; selection-background-color: {t['accent']};"
            f" selection-color: {t['on_accent']}; }}"
        )

    def eventFilter(self, obj, event):
        if obj is self.edit and event.type() in (event.Type.FocusIn, event.Type.FocusOut):
            self.update()
        return False

    def set_placeholder(self, text: str):
        self.edit.setPlaceholderText(text)

    def _submit(self):
        text = self.edit.text().strip()
        if text:
            self.edit.clear()
            self.submitted.emit(text)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self.rect())
        rounded(p, r, self._radius, fill=col(self._fill),
                border=col("accent" if self.edit.hasFocus() else "line"))
        s = self._icon_size
        draw_icon(p, "plus", QRectF(r.right() - self._pad - s, r.center().y() - s / 2, s, s),
                  col("accent"), 1.7)
        if self._show_enter:
            f = font(10, mono=True)
            w = text_width("Enter", f)
            draw_text(p, QRectF(self._pad, 0, w, r.height()), "Enter", f, col("faint"),
                      Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elide_text=False)
        p.end()


class ParseChip(QWidget):
    """«📅 فردا · شنبه ۴ مهر   کار: «…»» — shown only while a day is recognised."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.label = ""
        self.rest = ""
        self.setFixedHeight(24)
        self.hide()

    def show_preview(self, preview):
        if preview:
            self.label, self.rest = preview
            self.show()
        else:
            self.hide()
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        f = font(12)
        w = 9 + 11 + 5 + text_width(self.label, f) + 9
        chip = QRectF(self.width() - w, 0, w, 24)
        rounded(p, chip, 6, fill=tint("accent", 0.12))
        draw_icon(p, "calendar_small", QRectF(chip.right() - 9 - 11, 6.5, 11, 11),
                  col("accent"), 1.6)
        draw_text(p, QRectF(chip.left() + 9, 0, text_width(self.label, f), 24), self.label, f,
                  col("accent"), elide_text=False)
        draw_text(p, QRectF(0, 0, chip.left() - 8, 24), self.rest, f, col("muted"))
        p.end()


class DayList(QWidget):
    """Headers, task rows and an empty line, painted as one column."""

    task_toggled = pyqtSignal(str, int, bool)
    task_opened = pyqtSignal(str, int)
    task_delete_requested = pyqtSignal(str, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self._rows: list[dict] = []
        self._rects: list[QRectF] = []
        self._hover = -1
        self._text_font = font(13.5)
        self._small_font = font(11.5)
        self._head_font = font(11.5, 600)

    def set_rows(self, rows: list[dict]):
        self._rows = rows
        self._hover = -1
        self._layout()
        self.update()

    def resizeEvent(self, event):
        self._layout()
        super().resizeEvent(event)

    def _text_height(self, row, width) -> float:
        when_w = text_width(row["when"], self._small_font) + 10 if row["when"] else 0
        inner = width - 8 - 22 + 3 - 10 - when_w - 8
        fm = QFontMetricsF(self._text_font)
        bound = fm.boundingRect(QRectF(0, 0, max(10.0, inner), 2000),
                                int(Qt.TextFlag.TextWordWrap), row["text"])
        lines = max(1, round(bound.height() / fm.lineSpacing()))
        return lines * 13.5 * 1.7

    def _layout(self):
        width = self.width()
        y = 0.0
        self._rects = []
        head_h = 10 + QFontMetricsF(self._head_font).height() + 4
        for row in self._rows:
            if row["kind"] == "header":
                h = head_h
            elif row["kind"] == "empty":
                h = 28 * 2 + 12.5 * 1.9 * 2
            else:
                h = 8 + self._text_height(row, width) + 1 + QFontMetricsF(self._small_font).height() + 8
            self._rects.append(QRectF(0, y, width, h))
            y += h
        self.setMinimumHeight(round(y))

    def sizeHint(self) -> QSize:
        return QSize(RAIL_WIDTH - 24, self.minimumHeight())

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        for index, (row, rect) in enumerate(zip(self._rows, self._rects)):
            if row["kind"] == "header":
                inner = rect.adjusted(8, 10, -8, -4)
                draw_text(p, inner, row["label"], self._head_font, col(row["colour"]))
                draw_text(p, inner, row["count"], self._small_font, col("muted"),
                          Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            elif row["kind"] == "empty":
                draw_text(p, rect.adjusted(8, 28, -8, -28), row["text"], font(12.5),
                          col("muted"), Qt.AlignmentFlag.AlignCenter, wrap=True)
            else:
                self._paint_task(p, row, rect, index == self._hover)
        p.end()

    def _paint_task(self, p, row, rect, hovered):
        if hovered:
            rounded(p, rect, 8, fill=col("divider"))
        right = rect.right() - 8
        # 22px button, margin 1px -3px 0 0: its box is centred 11px in, nudged 3px out.
        box_centre = QPointF(right + 3 - 11, rect.top() + 8 + 1 + 11)
        draw_checkbox(p, box_centre, 16, 5, row["done"], border=col(row["box"]))
        when_w = 0.0
        if row["when"]:
            when_w = text_width(row["when"], self._small_font)
            draw_text(p, QRectF(rect.left() + 8, rect.top() + 8 + 3, when_w,
                                QFontMetricsF(self._small_font).height()),
                      row["when"], self._small_font, col(row["when_colour"]),
                      Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elide_text=False)
        text_right = right + 3 - 22 - 10
        text_left = rect.left() + 8 + (when_w + 10 if when_w else 0)
        th = self._text_height(row, self.width())
        draw_text(p, QRectF(text_left, rect.top() + 8, text_right - text_left, th),
                  row["text"], self._text_font, col(row["colour"]), strike=row["done"],
                  wrap=True)
        draw_text(p, QRectF(text_left, rect.top() + 8 + th + 1, text_right - text_left,
                            QFontMetricsF(self._small_font).height()),
                  row["src"], self._small_font, col("faint"))

    def _row_at(self, pos) -> int:
        for index, rect in enumerate(self._rects):
            if rect.contains(QPointF(pos)) and self._rows[index]["kind"] == "task":
                return index
        return -1

    def mouseMoveEvent(self, event):
        hover = self._row_at(event.position())
        if hover != self._hover:
            self._hover = hover
            self.update()

    def leaveEvent(self, event):
        self._hover = -1
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        index = self._row_at(event.position())
        if index < 0 or event.button() != Qt.MouseButton.LeftButton:
            return
        row, rect = self._rows[index], self._rects[index]
        task = row["task"]
        if event.position().x() >= rect.right() - 8 - 22:
            self.task_toggled.emit(task.path, task.line_number, not task.done)
        else:
            self.task_opened.emit(task.path, task.line_number)

    def contextMenuEvent(self, event):
        index = self._row_at(event.pos())
        if index < 0:
            return
        task = self._rows[index]["task"]
        menu = QMenu(self)
        menu.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        opener = QAction("باز کردن در فایل", menu)
        opener.triggered.connect(lambda: self.task_opened.emit(task.path, task.line_number))
        remover = QAction("حذف کار", menu)
        remover.triggered.connect(lambda: self.task_delete_requested.emit(task.path, task.line_number))
        menu.addAction(opener)
        menu.addAction(remover)
        menu.exec(event.globalPos())

    # Helpers for tests and callers
    def texts(self) -> list[str]:
        return [row["text"] for row in self._rows if row["kind"] == "task"]


class MiniCalendar(QWidget):
    """«مهر ۱۴۰۵» with arrows, weekday initials, and 32px day cells."""

    day_activated = pyqtSignal(date)

    CELL = 32
    GAP = 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self._selected = date.today()
        self._year, self._month, _ = from_gregorian(date.today())
        self._busy: set = set()
        self._overdue: set = set()
        self._hover: date | None = None
        self._cells: list[tuple[QRectF, date]] = []
        header = QHBoxLayout(self)
        header.setContentsMargins(0, 0, 0, 0)
        header.setAlignment(Qt.AlignmentFlag.AlignTop)
        header.addStretch(1)
        arrows = dict(height=26, width=26, radius=6, padding=(0, 0), icon_size=13, stroke=1.6,
                      normal={"fg": "muted"}, hover={"bg": "surface_alt", "fg": "text"})
        self.previous = Button("", "chevron_right", **arrows)
        self.next = Button("", "chevron_left", **arrows)
        self.previous.clicked.connect(lambda: self.shift(-1))
        self.next.clicked.connect(lambda: self.shift(1))
        header.setSpacing(2)
        header.addWidget(self.previous, 0, Qt.AlignmentFlag.AlignTop)
        header.addWidget(self.next, 0, Qt.AlignmentFlag.AlignTop)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._fit()

    def _rows(self) -> int:
        days = month_days(self._year, self._month)
        return (column_of(days[0]) + len(days) + 6) // 7

    def _fit(self):
        weekday_h = QFontMetricsF(font(10.5)).height() + 4
        self.setFixedHeight(round(26 + 10 + weekday_h + self._rows() * (self.CELL + self.GAP)))

    def set_marks(self, busy: set, overdue: set):
        self._busy, self._overdue = set(busy), set(overdue)
        self.update()

    def selected_day(self) -> date:
        return self._selected

    def choose(self, day: date, emit: bool = True):
        self._selected = day
        self._year, self._month, _ = from_gregorian(day)
        self._fit()
        self.update()
        if emit:
            self.day_activated.emit(day)

    def shift(self, delta: int):
        self._year, self._month = shift_month(self._year, self._month, delta)
        self._fit()
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        width = self.width()
        title = to_persian_digits(f"{MONTHS[self._month - 1]} {self._year}")
        draw_text(p, QRectF(0, 0, width, 26), title, font(13, 600), col("text"))
        column_w = (width - self.GAP * 6) / 7
        top = 26 + 10
        wf = font(10.5)
        wh = QFontMetricsF(wf).height()
        for index, initial in enumerate(WEEKDAY_INITIALS):
            x = width - (index + 1) * column_w - index * self.GAP
            draw_text(p, QRectF(x, top, column_w, wh), initial, wf, col("faint"),
                      Qt.AlignmentFlag.AlignCenter, elide_text=False)
        top += wh + 4
        today = date.today()
        self._cells = []
        days = month_days(self._year, self._month)
        offset = column_of(days[0])
        for day in days:
            slot = offset + days.index(day)
            row, column = divmod(slot, 7)
            x = width - (column + 1) * column_w - column * self.GAP
            y = top + row * (self.CELL + self.GAP)
            rect = QRectF(x, y, column_w, self.CELL)
            self._cells.append((rect, day))
            chosen, is_today = day == self._selected, day == today
            border = col("accent") if is_today and not chosen else (
                col("border") if self._hover == day else None)
            rounded(p, rect, 8, fill=col("accent") if chosen else None, border=border)
            colour = "on_accent" if chosen else "accent" if is_today else (
                "danger" if column == FRIDAY_COLUMN else "soft")
            _, _, number = from_gregorian(day)
            draw_text(p, rect, to_persian_digits(str(number)),
                      font(12, 700 if (chosen or is_today) else 400), col(colour),
                      Qt.AlignmentFlag.AlignCenter, elide_text=False)
            if day in self._busy and not chosen:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(col("danger" if day in self._overdue else "accent"))
                p.drawEllipse(QPointF(rect.center().x(), rect.bottom() - 3 - 2), 2, 2)
        p.end()

    def _day_at(self, pos):
        for rect, day in self._cells:
            if rect.contains(QPointF(pos)):
                return day
        return None

    def mouseMoveEvent(self, event):
        day = self._day_at(event.position())
        if day != self._hover:
            self._hover = day
            self.setCursor(Qt.CursorShape.PointingHandCursor if day else Qt.CursorShape.ArrowCursor)
            self.update()

    def leaveEvent(self, event):
        self._hover = None
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        day = self._day_at(event.position())
        if day is not None and event.button() == Qt.MouseButton.LeftButton:
            self.choose(day)


# The column

class TodayRail(QWidget):
    task_added = pyqtSignal(object, str)          # (date, text)
    task_toggled = pyqtSignal(str, int, bool)     # (path, line, done)
    task_delete_requested = pyqtSignal(str, int)  # (path, line)
    task_opened = pyqtSignal(str, int)            # (path, line)
    file_requested = pyqtSignal()                 # the arrow: all tasks
    added_elsewhere = pyqtSignal(str)             # a toast: «به کارهای فردا اضافه شد»

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("todayRail")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setFixedWidth(RAIL_WIDTH)

        self._tasks: list[Task] = []
        self._day = date.today()

        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)

        top = QWidget()
        head = QVBoxLayout(top)
        head.setContentsMargins(20, 22, 20, 0)
        head.setSpacing(14)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        self.heading = _DayHeading()
        title_row.addWidget(self.heading, 1)
        self.today_button = Button(
            "برگشت به امروز", None, height=28, radius=7, padding=(10, 10), px=12,
            normal={"bg": "surface_alt", "fg": "text"}, hover={"bg": "hover"},
        )
        self.today_button.clicked.connect(lambda: self.show_day(date.today()))
        title_row.addWidget(self.today_button, 0, Qt.AlignmentFlag.AlignTop)
        self.all_button = Button(
            "", "open_out", height=28, width=28, radius=7, padding=(0, 0), icon_size=15,
            stroke=1.5, normal={"fg": "muted"}, hover={"bg": "surface_alt", "fg": "text"},
        )
        self.all_button.setToolTip("همه‌ی کارها")
        self.all_button.clicked.connect(self.file_requested)
        title_row.addWidget(self.all_button, 0, Qt.AlignmentFlag.AlignTop)
        head.addLayout(title_row)

        self.progress_block = QWidget()
        progress = QVBoxLayout(self.progress_block)
        progress.setContentsMargins(0, 0, 0, 0)
        progress.setSpacing(7)
        self.progress_bar = ProgressBar()
        progress.addWidget(self.progress_bar)
        self.progress = _Caption()
        progress.addWidget(self.progress)
        head.addWidget(self.progress_block)

        self.input = QuickAddField("کار جدید برای امروز…")
        self.input.submitted.connect(self._submit)
        self.input.text_changed.connect(
            lambda text: self.parse_chip.show_preview(parse_preview(text)))
        head.addWidget(self.input)
        self.parse_chip = ParseChip()
        head.addWidget(self.parse_chip)
        column.addWidget(top)

        self.scroll = QScrollArea()
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setMinimumHeight(180)
        holder = QWidget()
        holder_layout = QVBoxLayout(holder)
        holder_layout.setContentsMargins(12, 12, 12, 8)
        self.list = DayList()
        self.list.task_toggled.connect(self.task_toggled)
        self.list.task_opened.connect(self.task_opened)
        self.list.task_delete_requested.connect(self.task_delete_requested)
        holder_layout.addWidget(self.list)
        holder_layout.addStretch(1)
        self.scroll.setWidget(holder)
        holder.setStyleSheet("background: transparent;")
        self.scroll.viewport().setAutoFillBackground(False)
        column.addWidget(self.scroll, 1)

        foot = _Footer()
        foot_layout = QVBoxLayout(foot)
        foot_layout.setContentsMargins(18, 14, 18, 18)
        self.calendar = MiniCalendar()
        self.calendar.day_activated.connect(self.show_day)
        foot_layout.addWidget(self.calendar)
        column.addWidget(foot)
        self._fill()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.fillRect(self.rect(), col("panel"))
        p.setPen(col("divider"))
        p.drawLine(self.width() - 1, 0, self.width() - 1, self.height())
        p.end()

    # Data

    def set_tasks(self, tasks: list[Task]):
        """Every task in the folder; the column keeps the dated ones."""
        self._tasks = [task for task in tasks if task.due is not None]
        self._fill()

    def show_day(self, day: date):
        self._day = day
        if self.calendar.selected_day() != day:
            self.calendar.choose(day, emit=False)
        self._fill()
        self.input.edit.setFocus()

    def selected_day(self) -> date:
        return self._day

    def tasks_on(self, day: date) -> list[Task]:
        found = [t for t in self._tasks if t.due and t.due.date() == day]
        found.sort(key=lambda t: (t.done, t.due))
        return found

    def replace_day(self, day: date, tasks: list[Task]):
        """Swap one day's tasks in without waiting for the next folder scan."""
        self._tasks = [t for t in self._tasks if not (t.due and t.due.date() == day)]
        self._tasks.extend(t for t in tasks if t.due is not None)
        self._fill()

    def _row(self, task: Task, today: date) -> dict:
        overdue = not task.done and task.due.date() < today
        return {
            "kind": "task", "task": task, "text": task.text, "done": task.done,
            "src": task_source(task),
            "when": day_label(task.due.date(), today) + (" ↻" if task.repeats else ""),
            "colour": "muted" if task.done else "danger" if overdue else "text",
            "when_colour": "danger" if overdue else "muted",
            "box": "danger" if overdue else "box",
        }

    def _fill(self):
        today = date.today()
        is_today = self._day == today
        self.heading.set_day(self._day, is_today)
        self.today_button.setVisible(not is_today)
        _, month, number = from_gregorian(self._day)
        self.input.set_placeholder(
            "کار جدید برای امروز…" if is_today
            else "کار جدید برای " + to_persian_digits(str(number)) + " " + MONTHS[month - 1] + "…")

        on_day = self.tasks_on(self._day)
        rows: list[dict] = []
        if is_today:
            overdue = sorted((t for t in self._tasks if not t.done and t.due.date() < today),
                             key=lambda t: t.due)
            if overdue:
                rows.append({"kind": "header", "label": "عقب‌افتاده",
                             "count": to_persian_digits(str(len(overdue))), "colour": "danger"})
                rows.extend(self._row(t, today) for t in overdue)
                if on_day:
                    rows.append({"kind": "header", "label": "امروز",
                                 "count": to_persian_digits(str(len(on_day))), "colour": "muted"})
        rows.extend(self._row(t, today) for t in on_day)
        if not rows:
            rows.append({"kind": "empty", "text": "امروز کاری ثبت نشده. اولین کار را بالا بنویس."
                         if is_today else "برای این روز کاری نیست."})
        self.list.set_rows(rows)

        done = sum(1 for t in on_day if t.done)
        self.progress_block.setVisible(bool(on_day))
        self.progress_bar.set_fraction(done / len(on_day) if on_day else 0)
        self.progress.set_text(to_persian_digits(f"{done} از {len(on_day)} انجام شده"))

        busy = {t.due.date() for t in self._tasks if not t.done}
        overdue_days = {d for d in busy if d < today}
        self.calendar.set_marks(busy, overdue_days)

    # Actions

    def _submit(self, text: str):
        found = parse_when(text)
        day = found.day if found else self._day
        body = found.text if found else text
        self.parse_chip.show_preview(None)
        if found and day != self._day:
            self.added_elsewhere.emit("به کارهای " + day_label(day) + " اضافه شد")
        self.task_added.emit(day, body)

    def refresh_palette(self):
        self.input._style_edit()
        self.update()
        for child in self.findChildren(QWidget):
            child.update()


class _DayHeading(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._title = "امروز"
        self._sub = ""
        self.setFixedHeight(round(QFontMetricsF(font(19, 700)).height() + 2
                                  + QFontMetricsF(font(12.5)).height()))

    def set_day(self, day: date, is_today: bool):
        from core.when import weekday_name

        year, month, number = from_gregorian(day)
        self._title = "امروز" if is_today else to_persian_digits(str(number)) + " " + MONTHS[month - 1]
        self._sub = (weekday_name(day) + "، " + to_persian_digits(str(number)) + " "
                     + MONTHS[month - 1] + " " + to_persian_digits(str(year)))
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        th = QFontMetricsF(font(19, 700)).height()
        draw_text(p, QRectF(0, 0, self.width(), th), self._title, font(19, 700), col("text"))
        draw_text(p, QRectF(0, th + 2, self.width(), self.height() - th - 2), self._sub,
                  font(12.5), col("muted"))
        p.end()


class _Caption(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._text = ""
        self.setFixedHeight(round(QFontMetricsF(font(11.5)).height()))

    def set_text(self, text: str):
        self._text = text
        self.update()

    def text(self) -> str:
        return self._text

    def paintEvent(self, _event):
        p = QPainter(self)
        draw_text(p, QRectF(self.rect()), self._text, font(11.5), col("muted"))
        p.end()


class _Footer(QWidget):
    def paintEvent(self, _event):
        p = QPainter(self)
        p.setPen(col("divider"))
        p.drawLine(0, 0, self.width(), 0)
        p.end()
