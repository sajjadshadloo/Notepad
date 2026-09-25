"""Compact V4 quick-capture sheet for a task or inbox note."""
from datetime import date, timedelta

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup, QDialog, QHBoxLayout, QLabel, QPushButton, QTextEdit,
    QToolButton, QVBoxLayout, QWidget,
)

from core.jalali import format_long


class QuickCaptureDialog(QDialog):
    task_submitted = pyqtSignal(object, str)
    note_submitted = pyqtSignal(str)

    def __init__(self, parent=None, day=None):
        super().__init__(parent)
        self.setObjectName("quickCapture")
        self.setWindowTitle("ضبط سریع")
        self.setModal(True)
        self.setFixedWidth(520)
        self._day = day or date.today()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 20)
        outer.setSpacing(14)
        title = QLabel("ضبط سریع")
        title.setObjectName("workspaceTitle")
        outer.addWidget(title)

        switch = QWidget()
        switch.setObjectName("segmented")
        switch_row = QHBoxLayout(switch)
        switch_row.setContentsMargins(3, 3, 3, 3)
        switch_row.setSpacing(3)
        self.kind = QButtonGroup(self)
        self.kind.setExclusive(True)
        self.task_button = QToolButton()
        self.task_button.setText("کار")
        self.task_button.setCheckable(True)
        self.task_button.setChecked(True)
        self.note_button = QToolButton()
        self.note_button.setText("یادداشت")
        self.note_button.setCheckable(True)
        self.kind.addButton(self.task_button)
        self.kind.addButton(self.note_button)
        switch_row.addWidget(self.task_button)
        switch_row.addWidget(self.note_button)
        outer.addWidget(switch)

        self.text = QTextEdit()
        self.text.setObjectName("captureText")
        self.text.setPlaceholderText("مثلاً «جلسه با حمید فردا ساعت ۱۱»")
        self.text.setFixedHeight(118)
        outer.addWidget(self.text)

        chips = QHBoxLayout()
        for label, offset in (("امروز", 0), ("فردا", 1), ("پس‌فردا", 2), ("هفتهٔ بعد", 7)):
            button = QToolButton()
            button.setText(label)
            button.setObjectName("tagChip")
            button.clicked.connect(lambda _checked=False, days=offset: self._choose(days))
            chips.addWidget(button)
        chips.addStretch(1)
        outer.addLayout(chips)
        self.when = QLabel(format_long(self._day))
        self.when.setObjectName("workspaceSubtitle")
        outer.addWidget(self.when)

        self.save = QPushButton("افزودن کار")
        self.save.setObjectName("primaryButton")
        self.save.setFixedHeight(46)
        self.save.clicked.connect(self._submit)
        self.task_button.toggled.connect(self._kind_changed)
        outer.addWidget(self.save)

    def _choose(self, offset):
        self._day = date.today() + timedelta(days=offset)
        self.when.setText(format_long(self._day))

    def _kind_changed(self, task):
        self.save.setText("افزودن کار" if task else "ذخیره در ورودی‌ها")
        self.when.setVisible(task)

    def _submit(self):
        text = self.text.toPlainText().strip()
        if not text:
            self.text.setFocus()
            return
        if self.task_button.isChecked():
            self.task_submitted.emit(self._day, text)
        else:
            self.note_submitted.emit(text)
        self.accept()

