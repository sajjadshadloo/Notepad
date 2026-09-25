"""A small panel that lives on the desktop: today's date and today's work.

Not parented to the desktop itself. Windows only lets a window sit *behind*
icons by attaching it to the WorkerW shell window, which is undocumented,
breaks every time Explorer restarts or the wallpaper changes, and takes the
panel with it. A frameless window pinned to the *bottom* of the z-order gets
the same effect and survives: visible whenever the desktop is, never over
the window you are working in.

The v4 design draws it as a 272x348 card, radius 16: the day, «۱ از ۴ انجام
شده», a 4px progress bar, today's tasks, and a footnote saying how to move it.
"""
from datetime import date

from PyQt6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFontMetricsF, QPainter
from PyQt6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from core.jalali import MONTHS, from_gregorian, to_persian_digits
from core.tasks import Task
from core.when import weekday_name
from ui.kit import Button, col, draw_checkbox, draw_text, font, rounded

CARD_W, CARD_H = 272, 348
# Room around the card for its shadow (0 18px 44px in the design).
SHADOW = 18
WIDTH, HEIGHT = CARD_W + 2 * SHADOW, CARD_H + 2 * SHADOW
MARGIN = 24
RADIUS = 16
TASK_LIMIT = 12


class _WidgetList(QWidget):
    """Today's rows: a 15px box, 13px text; a click on the box ticks it."""

    task_toggled = pyqtSignal(str, int, bool)
    task_opened = pyqtSignal(str, int)

    ROW = 7 + 13 * 1.7 + 7

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self._tasks: list[Task] = []
        self._hover = -1

    def set_tasks(self, tasks):
        self._tasks = list(tasks)
        self.setMinimumHeight(round(self.ROW * len(self._tasks)) if self._tasks else 80)
        self.update()

    # The surface the older list offered, kept for callers and tests.
    def texts(self) -> list[str]:
        return [t.text for t in self._tasks] or ["امروز کاری ثبت نشده"]

    def item(self, index: int) -> int:
        return index

    def payload_of(self, index: int):
        task = self._tasks[index]
        return task.path, task.line_number

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if not self._tasks:
            draw_text(p, QRectF(8, 30, self.width() - 16, 20), "امروز کاری ثبت نشده", font(12.5),
                      col("muted"), Qt.AlignmentFlag.AlignCenter)
            p.end()
            return
        for index, task in enumerate(self._tasks):
            rect = QRectF(0, index * self.ROW, self.width(), self.ROW)
            if index == self._hover:
                rounded(p, rect, 8, fill=col("surface_alt"))
            right = rect.right() - 6
            draw_checkbox(p, QPointF(right - 10, rect.top() + 7 + 2 + 10), 15, 5, task.done)
            draw_text(p, QRectF(rect.left() + 6, rect.top() + 7, right - 20 - 9 - rect.left() - 6,
                                13 * 1.7), task.text, font(13),
                      col("muted" if task.done else "text"), strike=task.done)
        p.end()

    def _at(self, y: float) -> int:
        index = int(y // self.ROW)
        return index if 0 <= index < len(self._tasks) else -1

    def mouseMoveEvent(self, event):
        hover = self._at(event.position().y())
        if hover != self._hover:
            self._hover = hover
            self.update()

    def leaveEvent(self, event):
        self._hover = -1
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        index = self._at(event.position().y())
        if index < 0:
            return
        task = self._tasks[index]
        if event.position().x() >= self.width() - 6 - 20:
            self.task_toggled.emit(task.path, task.line_number, not task.done)
        else:
            self.task_opened.emit(task.path, task.line_number)


class _Bar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.fraction = 0.0
        self.setFixedHeight(4)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self.rect())
        rounded(p, r, 2, fill=col("surface_alt"))
        if self.fraction:
            w = r.width() * self.fraction
            p.fillRect(QRectF(r.right() - w, 0, w, r.height()), col("accent"))
        p.end()


class _Heading(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.title, self.sub = "", ""
        self.setFixedHeight(round(QFontMetricsF(font(14.5, 700)).height() + 1
                                  + QFontMetricsF(font(11.5)).height()))

    def text(self) -> str:
        return self.sub

    def paintEvent(self, _event):
        p = QPainter(self)
        th = QFontMetricsF(font(14.5, 700)).height()
        draw_text(p, QRectF(0, 0, self.width(), th), self.title, font(14.5, 700), col("text"))
        draw_text(p, QRectF(0, th + 1, self.width(), self.height() - th - 1), self.sub,
                  font(11.5), col("muted"))
        p.end()


class DayWidget(QWidget):
    """The desktop panel. Its content is a view; the files stay the truth."""

    task_toggled = pyqtSignal(str, int, bool)
    task_delete_requested = pyqtSignal(str, int)
    task_opened = pyqtSignal(str, int)
    open_requested = pyqtSignal()
    closed = pyqtSignal()
    # Where the panel was dragged to, so it can be put back there.
    moved = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dayWidget")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnBottomHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(WIDTH, HEIGHT)
        self._drag_from: QPoint | None = None
        self._tasks: list[Task] = []

        column = QVBoxLayout(self)
        column.setContentsMargins(SHADOW, SHADOW, SHADOW, SHADOW)
        column.setSpacing(0)

        head = QHBoxLayout()
        head.setContentsMargins(10, 14, 14, 10)
        head.setSpacing(6)
        self.heading = _Heading()
        head.addWidget(self.heading, 1)
        small = dict(height=26, width=26, radius=7, padding=(0, 0), normal={"fg": "muted"},
                     hover={"bg": "hover", "fg": "text"})
        opener = Button("", "open_out", icon_size=13, stroke=1.6, **small)
        opener.setToolTip("باز کردن برنامه")
        opener.clicked.connect(self.open_requested)
        closer = Button("", "close", icon_size=10, stroke=1.8, **small)
        closer.setToolTip("بستن ویجت")
        closer.clicked.connect(self._close_clicked)
        head.addWidget(opener, 0, Qt.AlignmentFlag.AlignTop)
        head.addWidget(closer, 0, Qt.AlignmentFlag.AlignTop)
        column.addLayout(head)

        bar_row = QHBoxLayout()
        bar_row.setContentsMargins(14, 0, 14, 6)
        self.bar = _Bar()
        bar_row.addWidget(self.bar)
        column.addLayout(bar_row)

        list_row = QVBoxLayout()
        list_row.setContentsMargins(8, 4, 8, 10)
        self.list = _WidgetList()
        self.list.task_toggled.connect(self.task_toggled)
        self.list.task_opened.connect(self.task_opened)
        list_row.addWidget(self.list)
        list_row.addStretch(1)
        column.addLayout(list_row, 1)
        self.footer_height = round(8 + QFontMetricsF(font(11)).height() + 8)
        column.addSpacing(self.footer_height)
        # The design's name for the counter — kept so callers can read it.
        self.progress = self.heading

    # Content

    def set_tasks(self, tasks: list[Task]):
        """Given every task, keep today's — dated, and due today."""
        today = date.today()
        mine = [t for t in tasks if t.due is not None and t.due.date() == today]
        # Open first, then in the order they are written in their file.
        mine.sort(key=lambda task: (task.done, task.path, task.line_number))
        self._tasks = mine
        _, month, day = from_gregorian(today)
        self.heading.title = weekday_name(today) + "، " + to_persian_digits(str(day)) + " " + MONTHS[month - 1]
        done = sum(1 for task in mine if task.done)
        self.heading.sub = to_persian_digits(f"{done} از {len(mine)} انجام شده")
        self.heading.update()
        self.bar.fraction = done / len(mine) if mine else 0.0
        self.bar.update()
        self.list.set_tasks(mine[:TASK_LIMIT])

    def task_texts(self) -> list[str]:
        return [task.text for task in self._tasks]

    def _close_clicked(self):
        self.hide()
        self.closed.emit()

    # Placement

    def place(self, screen, remembered=None):
        """Put the panel where it was left, or in the bottom-right corner —
        the left of a Windows desktop is where the icons are."""
        area = screen.availableGeometry()
        if remembered:
            point = QPoint(int(remembered[0]), int(remembered[1]))
            if area.contains(QRect(point, self.size()).center()):
                self.move(point)
                return
        self.move(area.right() - self.width() - MARGIN, area.bottom() - self.height() - MARGIN)

    # A frameless window has no title bar: the card itself is the handle.

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_from = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag_from is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_from)

    def mouseReleaseEvent(self, event):
        if self._drag_from is not None:
            self._drag_from = None
            self.moved.emit(self.pos())

    def paintEvent(self, _event):
        """Drawn, not styled: a translucent window gets no stylesheet
        background, and the corners and shadow have to be painted."""
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        card = QRectF(SHADOW, SHADOW, CARD_W, CARD_H)
        # A soft shadow below the card: stacked translucent layers.
        for step in range(SHADOW, 0, -3):
            shade = QColor(0, 0, 0, round(46 * (1 - step / SHADOW) ** 2))
            rounded(p, card.adjusted(-step / 2, -step / 3, step / 2, step), RADIUS + step / 2, fill=shade)
        fill = col("surface")
        fill.setAlphaF(0.96)
        rounded(p, card, RADIUS, fill=fill, border=col("border"))
        foot_top = card.bottom() - self.footer_height
        p.fillRect(QRectF(card.left() + 1, foot_top, CARD_W - 2, 1), col("line"))
        draw_text(p, QRectF(card.left() + 14, foot_top, CARD_W - 28, self.footer_height),
                  "از عنوان بگیر و جابه‌جا کن · پشت پنجره‌ها می‌ماند", font(11), col("faint"))
        p.end()
