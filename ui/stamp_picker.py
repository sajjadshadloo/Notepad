"""The @ button's popup: pick the day a task is due.

3.11 offered an hour as well — four preset chips and a custom field. 4.1
takes them out. Nothing consumes an hour any more: reminders are gone, and
the calendar arranges a day's work as a list rather than against a clock. An
hour that changes nothing is a decision asked for no reason.
"""
from datetime import date

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from core.jalali import format_date
from ui.calendar_panel import CalendarPanel


class StampPicker(QDialog):
    """Emits ``picked`` with the chosen date."""

    picked = pyqtSignal(object)

    def __init__(self, root: str, initial: date | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("stampPicker")
        self.setWindowTitle("تاریخ کار")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setWindowFlags(Qt.WindowType.Popup)
        self.setFixedWidth(300)

        self._date = initial or date.today()

        column = QVBoxLayout(self)
        column.setContentsMargins(14, 12, 14, 12)
        column.setSpacing(10)

        self.calendar = CalendarPanel(root)
        self.calendar.day_activated.connect(self._pick_day)
        column.addWidget(self.calendar)

        rule = QFrame()
        rule.setObjectName("detailRule")
        rule.setFrameShape(QFrame.Shape.HLine)
        column.addWidget(rule)

        self.summary = QLabel()
        self.summary.setObjectName("detailValue")
        column.addWidget(self.summary)

        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        cancel = QPushButton("انصراف")
        cancel.clicked.connect(self.reject)
        confirm = QPushButton("ثبت")
        confirm.setObjectName("primaryButton")
        confirm.clicked.connect(self._accept)
        buttons.addWidget(cancel, 1)
        buttons.addWidget(confirm, 1)
        column.addLayout(buttons)

        self._refresh_summary()

    # Choosing

    def _pick_day(self, day: date):
        self._date = day
        self._refresh_summary()

    def _refresh_summary(self):
        self.summary.setText(format_date(self._date))

    # Finishing

    def _accept(self):
        self.picked.emit(self._date)
        self.accept()
