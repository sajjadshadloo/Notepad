"""The reminder card that slides in over the editor.

Windows' own tray balloon is easy to miss and impossible to act on — it says
a task is due and then disappears. The design puts the reminder in the window
instead, with the two things you actually want: open it, or push it ten
minutes down the road.

The tray notification still fires as well, because that is the one that
reaches you when the window is behind something else.
"""
from PyQt6.QtCore import QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ui.styles import current_palette

WIDTH = 330
MARGIN = 20
BOTTOM = 44
# Long enough to notice and act on, short enough not to sit there all day.
LINGER_MS = 12_000
SNOOZE_MINUTES = 10


class ReminderToast(QWidget):
    """One reminder. `opened` and `snoozed` carry (path, line)."""

    opened = pyqtSignal(str, int)
    snoozed = pyqtSignal(str, int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("toast")
        self.setFixedWidth(WIDTH)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._task_path = ""
        self._task_line = 0

        column = QVBoxLayout(self)
        column.setContentsMargins(14, 14, 14, 14)
        column.setSpacing(0)

        head = QHBoxLayout()
        head.setSpacing(9)
        self.mark = QLabel()
        self.mark.setFixedSize(16, 16)
        title = QLabel("یادآوری — Notepad Plus")
        title.setObjectName("toastTitle")
        close = QToolButton()
        close.setText("×")
        close.setObjectName("toastClose")
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.clicked.connect(self.dismiss)
        head.addWidget(self.mark)
        head.addWidget(title, 1)
        head.addWidget(close)
        column.addLayout(head)
        column.addSpacing(10)

        self.body = QLabel()
        self.body.setObjectName("toastBody")
        self.body.setWordWrap(True)
        column.addWidget(self.body)

        self.meta = QLabel()
        self.meta.setObjectName("toastMeta")
        column.addWidget(self.meta)
        column.addSpacing(12)

        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        self.open_button = QPushButton("باز کردن")
        self.open_button.setObjectName("primaryButton")
        self.open_button.clicked.connect(self._open)
        self.snooze_button = QPushButton("۱۰ دقیقه بعد")
        self.snooze_button.clicked.connect(self._snooze)
        buttons.addWidget(self.open_button, 1)
        buttons.addWidget(self.snooze_button, 1)
        column.addLayout(buttons)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.dismiss)
        self.hide()

    def show_task(self, text: str, meta: str, path: str, line: int):
        self._task_path = path
        self._task_line = line
        self.body.setText(text)
        self.meta.setText(meta)
        self._paint_mark()
        self.adjustSize()
        self.setFixedWidth(WIDTH)
        self._reposition()
        self.show()
        self.raise_()
        self._timer.start(LINGER_MS)

    def dismiss(self):
        self._timer.stop()
        self.hide()

    def _open(self):
        path, line = self._task_path, self._task_line
        self.dismiss()
        if path:
            self.opened.emit(path, line)

    def _snooze(self):
        path, line = self._task_path, self._task_line
        self.dismiss()
        if path:
            self.snoozed.emit(path, line, SNOOZE_MINUTES)

    def _paint_mark(self):
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(current_palette()["accent"]))
        painter.drawRoundedRect(pixmap.rect(), 20, 20)
        painter.end()
        self.mark.setPixmap(
            pixmap.scaled(
                16,
                16,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _reposition(self):
        parent = self.parentWidget()
        if parent is None:
            return
        self.move(
            MARGIN,
            max(MARGIN, parent.height() - self.height() - BOTTOM),
        )

    def parent_resized(self):
        if self.isVisible():
            self._reposition()
