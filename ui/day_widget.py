"""A small panel that lives on the desktop: today's date and today's work.

Not parented to the desktop itself. Windows only lets a window sit *behind*
icons by attaching it to the WorkerW shell window, which is undocumented,
breaks every time Explorer restarts or the wallpaper changes, and takes the
panel with it. A frameless window pinned to the *bottom* of the z-order gets
the same effect and survives: visible whenever the desktop is, never over
the window you are working in.

It is deliberately small and does one job: show the day, and let a task be
ticked without opening the app.
"""
from datetime import date

from PyQt6.QtCore import QEvent, QPoint, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.jalali import format_long, to_persian_digits
from core.tasks import Task
from ui.styles import current_palette
from ui.task_rows import TaskList

WIDTH = 268
HEIGHT = 340
MARGIN = 24
RADIUS = 14
# Enough to read through, not so many that the panel becomes a second app.
TASK_LIMIT = 12


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
        # On the desktop, not over the work. Staying on *top* meant it sat
        # above whatever you were doing all day, which is its own kind of
        # interruption — the thing 4.0 removed reminders for. On the bottom
        # of the z-order it is there whenever the desktop is, and never in
        # front of anything else.
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
        column.setContentsMargins(16, 14, 16, 14)
        column.setSpacing(10)
        column.addLayout(self._build_header())

        self.list = TaskList()
        self.list.task_toggled.connect(self.task_toggled)
        self.list.task_delete_requested.connect(self.task_delete_requested)
        self.list.itemActivated.connect(self._open)
        column.addWidget(self.list, 1)

        self.progress = QLabel()
        self.progress.setObjectName("dayWidgetProgress")
        column.addWidget(self.progress)

    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)
        self.heading = QLabel()
        self.heading.setObjectName("dayWidgetHeading")
        self.heading.setWordWrap(True)

        open_button = QToolButton()
        open_button.setText("↗")
        open_button.setToolTip("باز کردن برنامه")
        open_button.setAutoRaise(True)
        open_button.setCursor(Qt.CursorShape.PointingHandCursor)
        open_button.clicked.connect(self.open_requested)

        close_button = QToolButton()
        close_button.setText("×")
        close_button.setToolTip("بستن ویجت")
        close_button.setAutoRaise(True)
        close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        close_button.clicked.connect(self._close_clicked)

        row.addWidget(self.heading, 1)
        row.addWidget(open_button)
        row.addWidget(close_button)
        self.heading.installEventFilter(self)
        return row

    # Content

    def set_tasks(self, tasks: list[Task]):
        """Given every task, keep today's — dated, and due today."""
        today = date.today()
        mine = [
            task
            for task in tasks
            if task.due is not None and task.due.date() == today
        ]
        mine.sort(key=lambda task: (task.done, task.text))
        self._tasks = mine

        self.heading.setText(format_long(today))
        self.list.clear()
        for task in mine[:TASK_LIMIT]:
            self.list.add_task(task, when="")
        if not mine:
            self.list.add_empty("امروز کاری ثبت نشده")

        done = sum(1 for task in mine if task.done)
        self.progress.setText(
            to_persian_digits(str(done) + " از " + str(len(mine)) + " انجام شده")
            if mine
            else ""
        )

    def task_texts(self) -> list[str]:
        return [task.text for task in self._tasks]

    def _open(self, item):
        payload = self.list.payload_of(item)
        if payload:
            self.task_opened.emit(payload[0], payload[1])

    def _close_clicked(self):
        self.hide()
        self.closed.emit()

    # Placement

    def place(self, screen, remembered=None):
        """Put the panel where it was left, or in a free corner.

        The default is the bottom *right*. 4.2.0 parked it bottom-left,
        which on a Windows desktop is exactly where the icons are.
        """
        area = screen.availableGeometry()
        if remembered:
            point = QPoint(int(remembered[0]), int(remembered[1]))
            # Only if it still lands on a screen — monitors get unplugged.
            if area.contains(QRect(point, self.size()).center()):
                self.move(point)
                return
        self.move(
            area.right() - self.width() - MARGIN,
            area.bottom() - self.height() - MARGIN,
        )

    # A frameless window has no title bar, so the header is the handle. The
    # panel's own mouse events only fire on bare background — the list and
    # the labels swallow theirs — which left almost nothing to grab, so the
    # heading watches for the drag on the panel's behalf.

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                self._drag_from = (
                    event.globalPosition().toPoint()
                    - self.frameGeometry().topLeft()
                )
        elif event.type() == QEvent.Type.MouseMove and self._drag_from is not None:
            if event.buttons() & Qt.MouseButton.LeftButton:
                self.move(event.globalPosition().toPoint() - self._drag_from)
                return True
        elif event.type() == QEvent.Type.MouseButtonRelease:
            if self._drag_from is not None:
                self._drag_from = None
                self.moved.emit(self.pos())
        return super().eventFilter(watched, event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_from = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )

    def mouseMoveEvent(self, event):
        if self._drag_from is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_from)

    def mouseReleaseEvent(self, event):
        if self._drag_from is not None:
            self._drag_from = None
            self.moved.emit(self.pos())

    def paintEvent(self, event):
        """Drawn rather than styled: a translucent window gets no stylesheet
        background, and the rounded corners have to be painted to be real."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        palette = current_palette()
        fill = QColor(palette["surface"])
        fill.setAlpha(244)
        painter.setBrush(fill)
        painter.setPen(QPen(QColor(palette["border"]), 1.0))
        painter.drawRoundedRect(
            self.rect().adjusted(0, 0, -1, -1), RADIUS, RADIUS
        )
        painter.end()
