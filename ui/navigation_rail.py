"""The final V4 navigation rail.

It stays visible on every desktop surface and mirrors the compact 68px rail
in the approved design: icon, short Persian label and a single selected state.
"""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QLabel, QToolButton, QVBoxLayout, QWidget

from ui.icons import icon, icon_size
from ui.styles import current_palette


RAIL_WIDTH = 68


class NavigationRail(QWidget):
    page_requested = pyqtSignal(str)
    settings_requested = pyqtSignal()

    PAGES = (
        ("home", "home", "خانه"),
        ("editor", "editor", "یادداشت"),
        ("tasks", "tasks", "کارها"),
        ("calendar", "calendar", "تقویم"),
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("navigationRail")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(RAIL_WIDTH)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        column = QVBoxLayout(self)
        column.setContentsMargins(8, 12, 8, 10)
        column.setSpacing(6)
        self.buttons = {}
        for key, glyph, label in self.PAGES:
            button = self._button(glyph, label)
            button.clicked.connect(
                lambda _checked=False, chosen=key: self.page_requested.emit(chosen)
            )
            column.addWidget(button)
            self.buttons[key] = button

        column.addStretch(1)
        self.settings = self._button("settings", "تنظیمات")
        self.settings.clicked.connect(self.settings_requested)
        column.addWidget(self.settings)
        self.set_page("home")

    def _button(self, glyph: str, label: str) -> QToolButton:
        button = QToolButton()
        button.setObjectName("railButton")
        button.setCheckable(True)
        button.setAutoExclusive(False)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        button.setText(label)
        button.setIconSize(icon_size(18))
        button.setFixedSize(52, 52)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setProperty("glyph", glyph)
        return button

    def set_page(self, key: str):
        for name, button in self.buttons.items():
            button.setChecked(name == key or (key == "calendar" and name == "calendar"))
        self.refresh_palette()

    def set_task_count(self, count: str):
        base = "کارها"
        self.buttons["tasks"].setText(base + ("  " + count if count else ""))

    def refresh_palette(self):
        palette = current_palette()
        for button in [*self.buttons.values(), self.settings]:
            colour = palette["accent"] if button.isChecked() else palette["muted"]
            button.setIcon(icon(button.property("glyph"), colour, 18))

