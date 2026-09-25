"""«کارهای من» and «تقویم»: every task in the notes, as a list or a month.

The list groups work into عقب‌افتاده / امروز / فردا / بعداً / بدون تاریخ;
the month puts each day's tasks in its cell as chips. Either way the column
on the left shows the chosen task: its date, whether it repeats, which file
and line it lives on, the line exactly as written, and buttons to move it,
open it, or delete it.
"""
from datetime import date, timedelta
from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QFontMetricsF, QPainter
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.jalali import MONTHS, WEEKDAYS, column_of, from_gregorian, month_days, shift_month, to_gregorian, to_persian_digits
from core.tasks import Task
from core.when import day_label, parse_when, weekday_name
from ui.kit import (
    Button,
    col,
    draw_checkbox,
    draw_text,
    font,
    rounded,
    text_width,
    tint,
    transparent_scroll,
)
from ui.notes_board import _Segment
from ui.today_rail import ParseChip, QuickAddField, task_source
from core.when import parse_preview

DETAIL_WIDTH = 340
WEEK_NAMES = ("شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه")


def task_key(task: Task) -> tuple:
    return (task.path, task.line_number)


def _is_overdue(task: Task, today: date) -> bool:
    return not task.done and task.due is not None and task.due.date() < today


# The list

class TaskGroups(QWidget):
    """Grouped rows, painted; a click selects, the box toggles."""

    selected = pyqtSignal(object)            # Task
    task_toggled = pyqtSignal(str, int, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self._items: list[tuple] = []   # ("header", label, count, colour) | ("task", Task)
        self._rects: list[QRectF] = []
        self._hover = -1
        self._selected_key = None
        self._today = date.today()

    def set_groups(self, groups, selected_key):
        self._items = []
        self._today = date.today()
        for label, colour, tasks in groups:
            self._items.append(("header", label, to_persian_digits(str(len(tasks))), colour))
            self._items.extend(("task", task) for task in tasks)
        self._selected_key = selected_key
        self._layout()
        self.update()

    def set_selected(self, key):
        self._selected_key = key
        self.update()

    def _row_height(self) -> float:
        return 10 + 14 * 1.7 + 10

    def _layout(self):
        self._rects = []
        y = 0.0
        head_h = 14 + 6 + QFontMetricsF(font(12.5, 600)).height() + 6
        for item in self._items:
            h = head_h if item[0] == "header" else self._row_height()
            self._rects.append(QRectF(0, y, self.width(), h))
            y += h
        self.setMinimumHeight(round(y))

    def resizeEvent(self, event):
        self._layout()
        super().resizeEvent(event)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        for index, (item, rect) in enumerate(zip(self._items, self._rects)):
            if item[0] == "header":
                self._paint_header(p, item, rect)
            else:
                self._paint_row(p, item[1], rect, index == self._hover)
        p.end()

    def _paint_header(self, p, item, rect):
        _, label, count, colour = item
        inner = rect.adjusted(10, 14 + 6, -10, -6)
        lf, cf = font(12.5, 600), font(11.5)
        lw = text_width(label, lf)
        draw_text(p, QRectF(inner.right() - lw, inner.top(), lw, inner.height()), label, lf,
                  col(colour), elide_text=False)
        cw = text_width(count, cf)
        cx = inner.right() - lw - 10 - cw
        draw_text(p, QRectF(cx, inner.top(), cw, inner.height()), count, cf, col("muted"),
                  elide_text=False)
        p.setPen(col("surface_alt"))
        y = inner.center().y()
        p.drawLine(QPointF(inner.left(), y), QPointF(cx - 10, y))

    def _paint_row(self, p, task: Task, rect, hovered):
        today = self._today
        selected = task_key(task) == self._selected_key
        if selected:
            rounded(p, rect, 10, fill=col("divider"))
        elif hovered:
            rounded(p, rect, 10, fill=col("surface"))
        overdue = _is_overdue(task, today)
        right, left = rect.right() - 12, rect.left() + 12
        cy = rect.center().y()
        draw_checkbox(p, QPointF(right - 11, cy), 17, 5, task.done,
                      border=col("danger" if overdue else "box"))
        x = right - 22 - 12
        when = day_label(task.due.date(), today) if task.due else ""
        when_rect = QRectF(left, cy - 10, 64, 20)
        draw_text(p, when_rect, when, font(12), col("danger" if overdue else "muted"),
                  Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elide_text=False)
        chip_font = font(11.5)
        src = task_source(task)
        chip_w = text_width(src, chip_font) + 18
        chip_h = QFontMetricsF(chip_font).height() + 4
        chip = QRectF(left + 64 + 12, cy - chip_h / 2, chip_w, chip_h)
        rounded(p, chip, 6, fill=col("surface"), border=col("surface_alt"))
        draw_text(p, chip, src, chip_font, col("soft"), Qt.AlignmentFlag.AlignCenter,
                  elide_text=False)
        text_left = chip.right() + 12
        if task.repeats:
            rf = font(13)
            rw = text_width("↻", rf)
            draw_text(p, QRectF(chip.right() + 12, cy - 10, rw, 20), "↻", rf, col("muted"),
                      elide_text=False)
            text_left += rw + 12
        colour = "muted" if task.done else "danger" if overdue else "text"
        draw_text(p, QRectF(text_left, rect.top(), x - text_left, rect.height()), task.text,
                  font(14), col(colour), strike=task.done)

    def _row_at(self, pos) -> int:
        for index, rect in enumerate(self._rects):
            if self._items[index][0] == "task" and rect.contains(QPointF(pos)):
                return index
        return -1

    def mouseMoveEvent(self, event):
        hover = self._row_at(event.position())
        if hover != self._hover:
            self._hover = hover
            self.setCursor(Qt.CursorShape.PointingHandCursor if hover >= 0
                           else Qt.CursorShape.ArrowCursor)
            self.update()

    def leaveEvent(self, event):
        self._hover = -1
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        index = self._row_at(event.position())
        if index < 0 or event.button() != Qt.MouseButton.LeftButton:
            return
        task = self._items[index][1]
        rect = self._rects[index]
        if event.position().x() >= rect.right() - 12 - 22:
            self.task_toggled.emit(task.path, task.line_number, not task.done)
        else:
            self.selected.emit(task)

    def texts(self) -> list[str]:
        return [item[1].text for item in self._items if item[0] == "task"]


# The month

class MonthGrid(QWidget):
    day_clicked = pyqtSignal(date)
    selected = pyqtSignal(object)

    HEAD_PAD = 9
    MIN_CELL = 112

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self._year, self._month, _ = from_gregorian(date.today())
        self._tasks: list[Task] = []
        self._selected_key = None
        self._hover = None
        self._cells: list[tuple] = []
        self._chips: list[tuple] = []
        self._fit()

    def set_month(self, year: int, month: int):
        self._year, self._month = year, month
        self._fit()
        self.update()

    def month(self) -> tuple[int, int]:
        return self._year, self._month

    def set_tasks(self, tasks, selected_key):
        self._tasks = [t for t in tasks if t.due is not None]
        self._selected_key = selected_key
        self._fit()
        self.update()

    def set_selected(self, key):
        self._selected_key = key
        self.update()

    def _slots(self) -> list[date]:
        """Whole weeks from the Saturday on or before the 1st."""
        days = month_days(self._year, self._month)
        first = days[0] - timedelta(days=column_of(days[0]))
        weeks = (column_of(days[0]) + len(days) + 6) // 7
        return [first + timedelta(days=i) for i in range(weeks * 7)]

    def _head_h(self) -> float:
        return self.HEAD_PAD * 2 + QFontMetricsF(font(11.5)).height()

    CHIP_H = 11.5 * 1.5 + 6

    def _row_heights(self) -> list[float]:
        """Each week is as tall as its fullest day, never under 112px."""
        slots = self._slots()
        more_h = QFontMetricsF(font(11)).height()
        heights = []
        for week in range(len(slots) // 7):
            tallest = self.MIN_CELL
            for day in slots[week * 7:week * 7 + 7]:
                count = sum(1 for t in self._tasks if t.due.date() == day)
                if not count:
                    continue
                shown = min(3, count)
                h = 8 + 26 + 4 + shown * self.CHIP_H + (shown - 1) * 4 + 8
                if count > 3:
                    h += 4 + more_h
                tallest = max(tallest, h)
            heights.append(tallest)
        return heights

    def _fit(self):
        heights = self._row_heights()
        self.setMinimumHeight(round(self._head_h() + 1 + sum(heights) + len(heights) - 1 + 2))

    def sizeHint(self) -> QSize:
        return QSize(700, self.minimumHeight())

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        whole = QRectF(self.rect())
        rounded(p, whole, 14, fill=col("surface_alt"))
        p.save()
        from PyQt6.QtGui import QPainterPath

        clip = QPainterPath()
        clip.addRoundedRect(whole.adjusted(1, 1, -1, -1), 13, 13)
        p.setClipPath(clip)
        width = whole.width() - 2
        cw = (width - 6) / 7
        head_h = self._head_h()
        for index, name in enumerate(WEEK_NAMES):
            x = 1 + width - (index + 1) * cw - index
            rect = QRectF(x, 1, cw, head_h)
            p.fillRect(rect, col("panel"))
            draw_text(p, rect.adjusted(12, 0, -12, 0), name, font(11.5), col("muted"))
        slots = self._slots()
        heights = self._row_heights()
        tops, y = [], 1 + head_h + 1
        for h in heights:
            tops.append(y)
            y += h + 1
        today = date.today()
        self._cells, self._chips = [], []
        for index, day in enumerate(slots):
            row, column = divmod(index, 7)
            x = 1 + width - (column + 1) * cw - column
            rect = QRectF(x, tops[row], cw, heights[row])
            _, month, number = from_gregorian(day)
            in_month = month == self._month
            p.fillRect(rect, col("well_hover" if (self._hover == day and in_month) else
                                 "window" if in_month else "chrome"))
            self._cells.append((rect, day, in_month))
            is_today = day == today and in_month
            num = QRectF(rect.right() - 8 - 26, rect.top() + 8, 26, 26)
            label = to_persian_digits(str(number))
            nf = font(12.5, 700 if is_today else 500)
            num.setLeft(num.right() - max(26.0, text_width(label, nf) + 10))
            if is_today:
                rounded(p, num, 13, fill=col("accent"))
            colour = col("on_accent" if is_today else "danger" if column == 6 else "soft")
            if not in_month:
                colour.setAlphaF(0.35)
            draw_text(p, num, label, nf, colour, Qt.AlignmentFlag.AlignCenter, elide_text=False)
            if not in_month:
                continue
            on_day = sorted((t for t in self._tasks if t.due.date() == day),
                            key=lambda t: (t.done, t.due))
            chip_y = num.bottom() + 4
            cf = font(11.5)
            chip_h = self.CHIP_H
            for task in on_day[:3]:
                overdue = _is_overdue(task, today)
                chip = QRectF(rect.left() + 8, chip_y, rect.width() - 16, chip_h)
                fill = (tint("danger", 0.12) if overdue else
                        tint("accent", 0.16) if task_key(task) == self._selected_key else
                        col("divider"))
                rounded(p, chip, 6, fill=fill)
                draw_text(p, chip.adjusted(7, 0, -7, 0), task.text, cf,
                          col("muted" if task.done else "danger" if overdue else "text"),
                          strike=task.done)
                self._chips.append((chip, task))
                chip_y += chip_h + 4
            if len(on_day) > 3:
                more = "+" + to_persian_digits(str(len(on_day) - 3)) + " کار دیگر"
                draw_text(p, QRectF(rect.left() + 8 + 7, chip_y, rect.width() - 30, 16), more,
                          font(11), col("muted"))
        p.restore()
        p.end()

    def _hit(self, pos):
        point = QPointF(pos)
        for chip, task in self._chips:
            if chip.contains(point):
                return "chip", task
        for rect, day, in_month in self._cells:
            if rect.contains(point) and in_month:
                return "day", day
        return None, None

    def mouseMoveEvent(self, event):
        kind, value = self._hit(event.position())
        day = value if kind == "day" else None
        if kind == "chip":
            day = value.due.date()
        if day != self._hover:
            self._hover = day
            self.setCursor(Qt.CursorShape.PointingHandCursor if day else Qt.CursorShape.ArrowCursor)
            self.update()

    def leaveEvent(self, event):
        self._hover = None
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        kind, value = self._hit(event.position())
        if kind == "chip":
            self.selected.emit(value)
        elif kind == "day":
            self.day_clicked.emit(value)


# The detail column

class _Painted(QWidget):
    """A fixed-height strip drawn by a callback — for the detail's static parts."""

    def __init__(self, height: float, painter, parent=None):
        super().__init__(parent)
        self._painter = painter
        self.setFixedHeight(round(height))

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self._painter(p, QRectF(self.rect()))
        p.end()


class TaskDetail(QWidget):
    toggle_requested = pyqtSignal(object)
    shift_requested = pyqtSignal(object, int)
    open_requested = pyqtSignal(object)
    delete_requested = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(DETAIL_WIDTH)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._task: Task | None = None
        self._raw = ""

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 24, 20, 24)
        outer.setSpacing(18)

        self.body = QWidget()
        column = QVBoxLayout(self.body)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(18)

        top = QHBoxLayout()
        top.setSpacing(8)
        self.pill = _Painted(QFontMetricsF(font(11.5)).height() + 4, self._paint_pill)
        top.addWidget(self.pill, 1)
        self.toggle = Button("انجام شد", None, height=28, radius=7, padding=(11, 11), px=12,
                             normal={"bg": "surface_alt", "fg": "text"}, hover={"bg": "hover"})
        self.toggle.clicked.connect(lambda: self._task and self.toggle_requested.emit(self._task))
        top.addWidget(self.toggle)
        column.addLayout(top)

        self.title = _Painted(18 * 1.7, self._paint_title)
        column.addWidget(self.title)

        row_h = 12 + QFontMetricsF(font(13)).height() + 12
        self.table = _Painted(row_h * 3 + 1, self._paint_table)
        column.addWidget(self.table)

        raw_h = QFontMetricsF(font(11.5)).height() + 6 + 10 + 12 * 1.8 + 10
        self.raw = _Painted(raw_h, self._paint_raw)
        column.addWidget(self.raw)

        shift = QVBoxLayout()
        shift.setSpacing(8)
        shift.addWidget(_Painted(QFontMetricsF(font(11.5)).height(),
                                 lambda p, r: draw_text(p, r, "جابه‌جایی تاریخ", font(11.5), col("muted"))))
        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        for label, days in (("فردا", 1), ("۳ روز بعد", 3), ("هفته‌ی بعد", 7)):
            button = Button(label, None, height=34, radius=8, padding=(0, 0), px=12.5,
                            normal={"bg": "surface", "fg": "text", "border": "line"},
                            hover={"fg": "accent", "border": "accent"})
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.setMinimumWidth(40)
            button.setMaximumWidth(10000)
            button.clicked.connect(lambda _c=False, n=days: self._task and self.shift_requested.emit(self._task, n))
            buttons.addWidget(button)
        shift.addLayout(buttons)
        column.addLayout(shift)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 4, 0, 0)
        actions.setSpacing(8)
        self.open_button = Button("باز کردن در فایل", "open_out", height=36, radius=9, padding=(0, 0),
                                  gap=7, px=13, weight=600, icon_size=14, stroke=1.7,
                                  normal={"bg": "accent", "fg": "on_accent"}, hover={"bg": "accent_hover"})
        self.open_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.open_button.setMaximumWidth(10000)
        self.open_button.setMinimumWidth(80)
        self.open_button.clicked.connect(lambda: self._task and self.open_requested.emit(self._task))
        self.delete_button = Button("", "trash", height=36, width=40, radius=9, padding=(0, 0),
                                    icon_size=15, stroke=1.4,
                                    normal={"fg": "danger", "border": "line"})
        self.delete_button._hover = {"bg": None}
        self.delete_button.setToolTip("حذف کار")
        self.delete_button.clicked.connect(lambda: self._task and self.delete_requested.emit(self._task))
        actions.addWidget(self.open_button, 1)
        actions.addWidget(self.delete_button)
        column.addLayout(actions)
        outer.addWidget(self.body)
        outer.addStretch(1)

        self.empty = _Painted(60, lambda p, r: draw_text(
            p, r, "یک کار را انتخاب کن تا جزئیاتش این‌جا بیاید.", font(12.5), col("muted"),
            Qt.AlignmentFlag.AlignCenter, wrap=True))
        outer.insertWidget(0, self.empty)
        self.set_task(None)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.fillRect(self.rect(), col("panel"))
        p.setPen(col("divider"))
        p.drawLine(self.width() - 1, 0, self.width() - 1, self.height())
        # The delete button's hover wash is a translucent danger, which the
        # token-only Button cannot express; drawn here under it instead.
        if self.delete_button.underMouse() and self._task:
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            geo = QRectF(self.delete_button.geometry()).translated(
                self.body.pos().x(), self.body.pos().y())
            rounded(p, geo, 9, fill=tint("danger", 0.1))
        p.end()

    def task(self) -> Task | None:
        return self._task

    def set_task(self, task: Task | None, raw: str = ""):
        self._task = task
        self._raw = raw
        self.body.setVisible(task is not None)
        self.empty.setVisible(task is None)
        if task is not None:
            self.toggle.set_label("برگرداندن" if task.done else "انجام شد")
            fm = QFontMetricsF(font(18, 600))
            bound = fm.boundingRect(QRectF(0, 0, DETAIL_WIDTH - 40, 1000),
                                    int(Qt.TextFlag.TextWordWrap), task.text)
            lines = max(1, round(bound.height() / fm.lineSpacing()))
            self.title.setFixedHeight(round(lines * 18 * 1.7))
        for widget in (self.pill, self.title, self.table, self.raw):
            widget.update()

    # Painters

    def _group(self) -> tuple[str, bool]:
        task, today = self._task, date.today()
        if task.due is None:
            return "بدون تاریخ", False
        if _is_overdue(task, today):
            return "عقب‌افتاده", True
        return day_label(task.due.date(), today), False

    def _paint_pill(self, p, r):
        if not self._task:
            return
        label, overdue = self._group()
        f = font(11.5)
        w = text_width(label, f) + 18
        pill = QRectF(r.right() - w, 0, w, r.height())
        rounded(p, pill, 6, fill=tint("danger", 0.12) if overdue else col("surface_alt"))
        draw_text(p, pill, label, f, col("danger" if overdue else "soft"),
                  Qt.AlignmentFlag.AlignCenter, elide_text=False)

    def _paint_title(self, p, r):
        if not self._task:
            return
        draw_text(p, r, self._task.text, font(18, 600),
                  col("muted" if self._task.done else "text"), strike=self._task.done,
                  align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, wrap=True)

    def _paint_table(self, p, r):
        task = self._task
        if not task:
            return
        if task.due is None:
            when = "بدون تاریخ"
        else:
            y, m, d = from_gregorian(task.due.date())
            when = (weekday_name(task.due.date()) + "، " + to_persian_digits(str(d)) + " "
                    + MONTHS[m - 1] + " " + to_persian_digits(str(y)))
        rows = (("تاریخ", when, ""), ("تکرار", "هر هفته" if task.repeats else "ندارد", ""),
                ("فایل", task_source(task), "خط " + to_persian_digits(str(task.line_number + 1))))
        row_h = (r.height() - 1) / 3
        p.setPen(col("surface_alt"))
        p.drawLine(QPointF(r.left(), 0.5), QPointF(r.right(), 0.5))
        for index, (key, value, extra) in enumerate(rows):
            top = 1 + index * row_h
            cell = QRectF(r.left(), top, r.width(), row_h - 1)
            draw_text(p, QRectF(cell.right() - 62, top, 62, row_h - 1), key, font(12), col("muted"))
            extra_w = text_width(extra, font(11.5)) + 12 if extra else 0
            draw_text(p, QRectF(cell.left() + extra_w, top, cell.width() - 62 - 12 - extra_w, row_h - 1),
                      value, font(13), col("text"))
            if extra:
                draw_text(p, QRectF(cell.left(), top, extra_w, row_h - 1), extra, font(11.5),
                          col("muted"), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                          elide_text=False)
            p.setPen(col("surface_alt"))
            p.drawLine(QPointF(r.left(), top + row_h - 0.5), QPointF(r.right(), top + row_h - 0.5))

    def _paint_raw(self, p, r):
        caption_h = QFontMetricsF(font(11.5)).height()
        draw_text(p, QRectF(r.left(), 0, r.width(), caption_h), "در فایل این‌طور نوشته شده",
                  font(11.5), col("muted"))
        box = QRectF(r.left(), caption_h + 6, r.width(), r.height() - caption_h - 6)
        rounded(p, box, 9, fill=col("window"), border=col("surface_alt"))
        draw_text(p, box.adjusted(12, 0, -12, 0), self._raw.strip(), font(12, mono=True),
                  col("soft"))


# The page

class TasksWorkspace(QWidget):
    task_toggled = pyqtSignal(str, int, bool)
    task_delete_requested = pyqtSignal(str, int)
    task_opened = pyqtSignal(str, int)
    task_added = pyqtSignal(object, str)
    task_rescheduled = pyqtSignal(str, int, object)
    day_chosen = pyqtSignal(date)
    added_elsewhere = pyqtSignal(str)

    def __init__(self, line_reader=None, parent=None):
        super().__init__(parent)
        self.setObjectName("tasksWorkspace")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._tasks: list[Task] = []
        self._selected_key = None
        self._mode = "tasks"
        self._line_reader = line_reader or (lambda path, line: "")

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        main = QWidget()
        main_column = QVBoxLayout(main)
        main_column.setContentsMargins(0, 0, 0, 0)
        main_column.setSpacing(0)

        header = QWidget()
        header_row = QHBoxLayout(header)
        header_row.setContentsMargins(30, 26, 30, 16)
        header_row.setSpacing(16)
        self.heading = _Painted(QFontMetricsF(font(24, 700)).height() + 4
                                + QFontMetricsF(font(12.5)).height(), self._paint_heading)
        header_row.addWidget(self.heading, 1)
        switch = _Segment()
        self.list_button = Button("فهرست", None, height=30, radius=6, padding=(16, 16), px=12.5,
                                  weight=600, normal={"fg": "muted"}, active={"bg": "hover", "fg": "text"})
        self.month_button = Button("ماه", None, height=30, radius=6, padding=(16, 16), px=12.5,
                                   weight=600, normal={"fg": "muted"}, active={"bg": "hover", "fg": "text"})
        for button, mode in ((self.list_button, "tasks"), (self.month_button, "calendar")):
            button.setCheckable(True)
            button.clicked.connect(lambda _c=False, m=mode: self.set_mode(m))
            switch.add(button)
        header_row.addWidget(switch, 0, Qt.AlignmentFlag.AlignBottom)
        main_column.addWidget(header)

        self.stack = QStackedWidget()
        main_column.addWidget(self.stack, 1)

        # List mode
        list_scroll = self._scroll()
        list_page = QWidget()
        list_column = QVBoxLayout(list_page)
        list_column.setContentsMargins(30, 0, 30, 30)
        list_column.setSpacing(0)
        self.input = QuickAddField("کار جدید… مثلاً «جلسه با تیم طراحی شنبه»", height=44,
                                   radius=11, px=13.5, fill="panel", show_enter=False,
                                   icon_size=15, pad=14, gap=10)
        self.input.submitted.connect(self._submit)
        self.input.text_changed.connect(lambda t: self.parse_chip.show_preview(parse_preview(t)))
        list_column.addWidget(self.input)
        # The input's 10px bottom margin and the first group's 14px top margin
        # collapse into one 14px gap in the design's block layout; the group
        # header carries those 14. With the chip showing, input→chip is
        # 10 + (-2) = 8px.
        self.parse_chip = ParseChip()
        chip_row = QHBoxLayout()
        chip_row.setContentsMargins(4, 8, 4, 0)
        chip_row.addWidget(self.parse_chip)
        list_column.addLayout(chip_row)
        self.groups = TaskGroups()
        self.groups.selected.connect(self.select_task)
        self.groups.task_toggled.connect(self.task_toggled)
        list_column.addWidget(self.groups)
        list_column.addStretch(1)
        list_scroll.setWidget(list_page)
        self.stack.addWidget(list_scroll)

        # Month mode
        month_scroll = self._scroll()
        month_page = QWidget()
        month_column = QVBoxLayout(month_page)
        month_column.setContentsMargins(30, 0, 30, 30)
        month_column.setSpacing(12)
        month_head = QHBoxLayout()
        month_head.setSpacing(8)
        self.month_title = _Painted(26, lambda p, r: draw_text(
            p, r, self._month_title(), font(16, 600), col("text")))
        month_head.addWidget(self.month_title, 1)
        arrows = dict(height=30, width=30, radius=8, padding=(0, 0), icon_size=13, stroke=1.6,
                      normal={"fg": "muted"}, hover={"bg": "surface", "fg": "text"})
        self.previous = Button("", "chevron_right", **arrows)
        self.next = Button("", "chevron_left", **arrows)
        self.previous.setToolTip("ماه قبل")
        self.next.setToolTip("ماه بعد")
        self.previous.clicked.connect(lambda: self._shift_month(-1))
        self.next.clicked.connect(lambda: self._shift_month(1))
        self.today_button = Button("امروز", None, height=30, radius=8, padding=(12, 12), px=12,
                                   normal={"bg": "surface", "fg": "text", "border": "surface_alt"},
                                   hover={"bg": "divider"})
        self.today_button.clicked.connect(self._back_to_today)
        month_head.addWidget(self.previous)
        month_head.addWidget(self.next)
        month_head.addWidget(self.today_button)
        month_column.addLayout(month_head)
        self.month = MonthGrid()
        self.month.selected.connect(self.select_task)
        self.month.day_clicked.connect(self.day_chosen)
        month_column.addWidget(self.month)
        month_column.addStretch(1)
        month_scroll.setWidget(month_page)
        self.stack.addWidget(month_scroll)

        row.addWidget(main, 1)
        self.detail = TaskDetail()
        self.detail.toggle_requested.connect(
            lambda t: self.task_toggled.emit(t.path, t.line_number, not t.done))
        self.detail.shift_requested.connect(self._shift_task)
        self.detail.open_requested.connect(lambda t: self.task_opened.emit(t.path, t.line_number))
        self.detail.delete_requested.connect(
            lambda t: self.task_delete_requested.emit(t.path, t.line_number))
        row.addWidget(self.detail)
        self.set_mode("tasks")

    def _scroll(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        transparent_scroll(scroll)
        return scroll

    def paintEvent(self, _event):
        p = QPainter(self)
        p.fillRect(self.rect(), col("window"))
        p.end()

    # Data

    def set_tasks(self, tasks: list[Task]):
        self._tasks = list(tasks)
        keys = {task_key(t) for t in self._tasks}
        if self._selected_key not in keys:
            # Keep the same task selected if its line moved; else the first.
            current = self.detail.task()
            match = next((t for t in self._tasks if current and t.text == current.text
                          and t.path == current.path), None)
            self._selected_key = task_key(match) if match else None
        self._fill()

    def set_mode(self, mode: str):
        self._mode = "calendar" if mode == "calendar" else "tasks"
        self.list_button.setChecked(self._mode == "tasks")
        self.month_button.setChecked(self._mode == "calendar")
        self.list_button.update()
        self.month_button.update()
        self.stack.setCurrentIndex(1 if self._mode == "calendar" else 0)
        self.heading.update()

    def mode(self) -> str:
        return self._mode

    def _groups(self):
        today = date.today()
        tomorrow = today + timedelta(days=1)
        buckets = (
            ("عقب‌افتاده", "danger", lambda t: _is_overdue(t, today)),
            ("امروز", "text", lambda t: t.due is not None and t.due.date() == today),
            ("فردا", "text", lambda t: t.due is not None and t.due.date() == tomorrow),
            ("بعداً", "text", lambda t: t.due is not None and t.due.date() > tomorrow),
            # Done work with no date has nothing left to plan; only open
            # undated tasks are listed, or a finished project checklist would
            # bury the group.
            ("بدون تاریخ", "muted", lambda t: t.due is None and not t.done),
        )
        groups = []
        for label, colour, test in buckets:
            found = [t for t in self._tasks if test(t)]
            found.sort(key=lambda t: (t.done, t.due or datetime_max(), t.text))
            if found:
                groups.append((label, colour, found))
        return groups

    def _fill(self):
        groups = self._groups()
        if self._selected_key is None and groups:
            first = next((g[2][0] for g in groups if g[0] == "امروز"), groups[0][2][0])
            self._selected_key = task_key(first)
        self.groups.set_groups(groups, self._selected_key)
        self.month.set_tasks(self._tasks, self._selected_key)
        self.month_title.update()
        self.heading.update()
        selected = next((t for t in self._tasks if task_key(t) == self._selected_key), None)
        self.detail.set_task(selected, self._line_reader(*self._selected_key) if selected else "")

    def select_task(self, task: Task):
        self._selected_key = task_key(task)
        self.groups.set_selected(self._selected_key)
        self.month.set_selected(self._selected_key)
        self.detail.set_task(task, self._line_reader(task.path, task.line_number) or "")

    # Painters

    def _paint_heading(self, p, r):
        title_h = QFontMetricsF(font(24, 700)).height()
        title = "تقویم" if self._mode == "calendar" else "کارهای من"
        draw_text(p, QRectF(r.left(), 0, r.width(), title_h), title, font(24, 700), col("text"))
        today = date.today()
        open_all = sum(1 for t in self._tasks if not t.done)
        overdue = sum(1 for t in self._tasks if _is_overdue(t, today))
        summary = to_persian_digits(str(open_all)) + " کار باز"
        if overdue:
            summary += " · " + to_persian_digits(str(overdue)) + " عقب‌افتاده"
        summary += " · از همه‌ی یادداشت‌ها"
        draw_text(p, QRectF(r.left(), title_h + 4, r.width(), r.height() - title_h - 4), summary,
                  font(12.5), col("muted"))

    def _month_title(self) -> str:
        year, month = self.month.month()
        return MONTHS[month - 1] + " " + to_persian_digits(str(year))

    # Actions

    def _shift_month(self, delta: int):
        self.month.set_month(*shift_month(*self.month.month(), delta))
        self.month_title.update()

    def _back_to_today(self):
        year, month, _ = from_gregorian(date.today())
        self.month.set_month(year, month)
        self.month_title.update()
        self.day_chosen.emit(date.today())

    def _shift_task(self, task: Task, days: int):
        base = max(task.due.date(), date.today()) if task.due else date.today()
        self.task_rescheduled.emit(task.path, task.line_number, base + timedelta(days=days))

    def _submit(self, text: str):
        found = parse_when(text)
        day = found.day if found else date.today()
        self.parse_chip.show_preview(None)
        if found and day != date.today():
            self.added_elsewhere.emit("به کارهای " + day_label(day) + " اضافه شد")
        self.task_added.emit(day, found.text if found else text)

    def refresh_palette(self):
        self.input._style_edit()
        self.update()
        for child in self.findChildren(QWidget):
            child.update()


def datetime_max():
    from datetime import datetime

    return datetime.max
