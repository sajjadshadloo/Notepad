"""The 68px rail on the right edge: home, note, tasks, calendar, settings.

Each button is 52px wide with a 19px icon over a 10.5px label; the selected
one sits on a darker plate in the accent colour, and the tasks button wears
the count of today's open work as a small accent badge.
"""
from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QFontMetricsF, QPainter
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from ui.kit import Clickable, col, draw_icon, draw_text, font, rounded, text_width

RAIL_WIDTH = 68
BUTTON_WIDTH = 52


class RailButton(Clickable):
    def __init__(self, key: str, glyph: str, label: str, parent=None):
        super().__init__(parent)
        self.key = key
        self.glyph = glyph
        self.label = label
        self.active = False
        self.badge = ""
        self.settings_style = key == "settings"
        label_height = QFontMetricsF(font(10.5)).height()
        self.setFixedSize(BUTTON_WIDTH, round(8 + 19 + 4 + label_height + 6))

    def set_active(self, active: bool):
        self.active = active
        self.update()

    def set_badge(self, text: str):
        self.badge = text
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self.rect())
        if self.active:
            rounded(p, r, 11, fill=col("divider"))
        elif self.hovered and self.settings_style:
            rounded(p, r, 11, fill=col("well_hover"))
        fg = col("accent") if self.active else col("text" if self.hovered else "muted")
        draw_icon(p, self.glyph, QRectF(r.center().x() - 9.5, 8, 19, 19), fg, 1.35)
        label_font = font(10.5)
        draw_text(p, QRectF(0, 8 + 19 + 4, r.width(), QFontMetricsF(label_font).height()),
                  self.label, label_font, fg, Qt.AlignmentFlag.AlignCenter, elide_text=False)
        if self.badge:
            badge_font = font(10.5, 700)
            width = max(17.0, text_width(self.badge, badge_font) + 8)
            rect = QRectF(7, 3, width, 17)
            rounded(p, rect, 8.5, fill=col("accent"))
            draw_text(p, rect, self.badge, badge_font, col("on_accent"),
                      Qt.AlignmentFlag.AlignCenter, elide_text=False)
        p.end()


class NavigationRail(QWidget):
    page_requested = pyqtSignal(str)
    settings_requested = pyqtSignal()

    PAGES = (
        ("home", "home", "خانه"),
        ("editor", "note", "یادداشت"),
        ("tasks", "tasks", "کارها"),
        ("calendar", "calendar", "تقویم"),
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("navigationRail")
        self.setFixedWidth(RAIL_WIDTH)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        column = QVBoxLayout(self)
        column.setContentsMargins(8, 12, 8, 12)
        column.setSpacing(6)
        self.buttons: dict[str, RailButton] = {}
        for key, glyph, label in self.PAGES:
            button = RailButton(key, glyph, label)
            button.clicked.connect(lambda chosen=key: self.page_requested.emit(chosen))
            column.addWidget(button, 0, Qt.AlignmentFlag.AlignHCenter)
            self.buttons[key] = button
        column.addStretch(1)
        self.settings = RailButton("settings", "settings", "تنظیمات")
        self.settings.setToolTip("تنظیمات — Ctrl+,")
        self.settings.clicked.connect(self.settings_requested)
        column.addWidget(self.settings, 0, Qt.AlignmentFlag.AlignHCenter)
        self.set_page("home")

    def paintEvent(self, _event):
        p = QPainter(self)
        p.fillRect(self.rect(), col("chrome"))
        # border-left: on the side facing the page.
        p.setPen(col("divider"))
        p.drawLine(0, 0, 0, self.height())
        p.end()

    def set_page(self, key: str):
        for name, button in self.buttons.items():
            button.set_active(name == key)

    def set_task_count(self, count: str):
        self.buttons["tasks"].set_badge(count)

    def refresh_palette(self):
        self.update()
        for button in [*self.buttons.values(), self.settings]:
            button.update()
