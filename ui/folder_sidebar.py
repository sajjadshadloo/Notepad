"""Folder sidebar used by the V4 home surface."""
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QLabel, QToolButton, QVBoxLayout, QWidget

from core.jalali import to_persian_digits


SIDEBAR_WIDTH = 228


class FolderSidebar(QWidget):
    category_selected = pyqtSignal(str)
    tasks_requested = pyqtSignal()

    def __init__(self, root: str, parent=None):
        super().__init__(parent)
        self.setObjectName("folderSidebar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(SIDEBAR_WIDTH)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._root = root
        self._selected = "همه"
        self._buttons = {}

        self.column = QVBoxLayout(self)
        self.column.setContentsMargins(12, 18, 12, 14)
        self.column.setSpacing(6)
        caption = QLabel("دفترچه")
        caption.setObjectName("sidebarSectionLabel")
        self.column.addWidget(caption)
        self.folder_holder = QWidget()
        self.folder_column = QVBoxLayout(self.folder_holder)
        self.folder_column.setContentsMargins(0, 0, 0, 0)
        self.folder_column.setSpacing(2)
        self.column.addWidget(self.folder_holder)
        rule = QLabel()
        rule.setObjectName("sidebarRule")
        rule.setFixedHeight(1)
        self.column.addWidget(rule)
        fixed = QLabel("فایل‌های ثابت")
        fixed.setObjectName("sidebarSectionLabel")
        self.column.addWidget(fixed)
        tasks = self._entry("کارها.md", "")
        tasks.clicked.connect(self.tasks_requested)
        self.column.addWidget(tasks)
        self.column.addWidget(self._entry("INDEX.md", ""))
        self.column.addWidget(self._entry("سطل بازیافت", ""))
        self.column.addStretch(1)
        self.path = QLabel()
        self.path.setObjectName("folderPathCard")
        self.path.setWordWrap(True)
        self.column.addWidget(self.path)
        self.set_root(root)

    def _entry(self, label, count):
        button = QToolButton()
        button.setObjectName("folderButton")
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setText(label + ("  " + count if count else ""))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFixedHeight(35)
        return button

    def set_root(self, root: str):
        self._root = root
        display = Path(root).name or root
        self.path.setText("پوشهٔ یادداشت‌ها\n" + display)

    def set_categories(self, names, counts=None):
        counts = counts or {}
        while self.folder_column.count():
            item = self.folder_column.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._buttons.clear()
        for name in names:
            button = self._entry(name, to_persian_digits(str(counts.get(name, ""))) if name in counts else "")
            button.setCheckable(True)
            button.setChecked(name == self._selected)
            button.clicked.connect(lambda _checked=False, chosen=name: self.select(chosen))
            self.folder_column.addWidget(button)
            self._buttons[name] = button

    def select(self, name):
        self._selected = name
        for key, button in self._buttons.items():
            button.setChecked(key == name)
        self.category_selected.emit(name)

