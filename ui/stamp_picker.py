"""The date-and-time popup behind the toolbar's @ button.

Before this, the button stamped today's date and the only way to add a time
was to know you could type one after it. Nothing said so. This puts both in
one place: pick a day on the Jalali calendar, pick an hour or leave it out.

Leaving the hour out is a real choice, not a missing one — an undated hour
means the reminder comes at nine in the morning, which is what most things
written down for "that day" actually want.
"""
from datetime import date, time

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTimeEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtCore import QTime

from core.jalali import format_date
from ui.calendar_panel import CalendarPanel

# The hours a working day actually gets scheduled around. Four, not five:
# a fifth chip does not fit the popup's width and Qt elides "09:00" to
# something unreadable rather than wrapping. Anything else is one field away.
QUICK_HOURS = ((9, 0), (12, 0), (16, 0), (18, 0))
DEFAULT_HOUR = time(9, 0)


class StampPicker(QDialog):
    """Emits ``picked`` with the chosen date and an optional time."""

    picked = pyqtSignal(object, object)

    def __init__(self, root: str, initial: date | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("stampPicker")
        self.setWindowTitle("زمان‌بندی")
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

        caption = QLabel("ساعت")
        caption.setObjectName("sidebarSectionLabel")
        column.addWidget(caption)

        chips = QWidget()
        chip_row = QHBoxLayout(chips)
        chip_row.setContentsMargins(0, 0, 0, 0)
        chip_row.setSpacing(4)
        self._hour_buttons = []
        for hour, minute in QUICK_HOURS:
            button = QToolButton()
            button.setText(f"{hour:02d}:{minute:02d}")
            button.setCheckable(True)
            button.setObjectName("findFlag")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(
                lambda _c, h=hour, m=minute: self._pick_hour(h, m)
            )
            chip_row.addWidget(button)
            self._hour_buttons.append(((hour, minute), button))
        column.addWidget(chips)

        custom = QHBoxLayout()
        custom.setSpacing(8)
        custom_label = QLabel("دلخواه")
        custom_label.setObjectName("detailKey")
        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat("HH:mm")
        self.time_edit.setTime(QTime(DEFAULT_HOUR.hour, DEFAULT_HOUR.minute))
        self.time_edit.timeChanged.connect(self._custom_time_changed)
        custom.addWidget(custom_label)
        custom.addWidget(self.time_edit, 1)
        column.addLayout(custom)

        self.summary = QLabel()
        self.summary.setObjectName("detailValue")
        column.addWidget(self.summary)

        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        without = QPushButton("بدون ساعت")
        without.clicked.connect(self._accept_without_time)
        confirm = QPushButton("ثبت")
        confirm.setObjectName("primaryButton")
        confirm.clicked.connect(self._accept_with_time)
        buttons.addWidget(without, 1)
        buttons.addWidget(confirm, 1)
        column.addLayout(buttons)

        self._time: time | None = None
        self._refresh_summary()

    # Choosing

    def _pick_day(self, day: date):
        self._date = day
        self._refresh_summary()

    def _pick_hour(self, hour: int, minute: int):
        self._time = time(hour, minute)
        for (values, button) in self._hour_buttons:
            button.setChecked(values == (hour, minute))
        self.time_edit.blockSignals(True)
        self.time_edit.setTime(QTime(hour, minute))
        self.time_edit.blockSignals(False)
        self._refresh_summary()

    def _custom_time_changed(self, value: QTime):
        self._time = time(value.hour(), value.minute())
        for (_values, button) in self._hour_buttons:
            button.setChecked(False)
        self._refresh_summary()

    def _refresh_summary(self):
        text = format_date(self._date)
        if self._time is not None:
            from core.jalali import to_persian_digits

            text += to_persian_digits(
                f"  ساعت {self._time.hour:02d}:{self._time.minute:02d}"
            )
        else:
            text += "  (بدون ساعت — یادآوری ۹ صبح)"
        self.summary.setText(text)

    # Finishing

    def _accept_without_time(self):
        self.picked.emit(self._date, None)
        self.accept()

    def _accept_with_time(self):
        self.picked.emit(self._date, self._time or DEFAULT_HOUR)
        self.accept()
