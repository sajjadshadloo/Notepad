"""The 48px bar across the top of the window, exactly as the v4 design draws it.

Three columns — 300px, the rest, 300px — so the search well stays centred:
the brand and where you are on the right, one search field in the middle
that reaches notes, tasks and commands, and on the left quick capture, the
sync state, the desktop widget and the theme.
"""
from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import QHBoxLayout, QSizePolicy, QWidget

from ui.kit import (
    Button,
    Clickable,
    col,
    draw_icon,
    draw_text,
    elide,
    font,
    kbd,
    rounded,
    text_width,
)

BAR_HEIGHT = 48
SIDE_BLOCK = 300
SEARCH_MAX_WIDTH = 460
SEARCH_HEIGHT = 32

PAGES = (("home", "خانه"), ("editor", "یادداشت"), ("tasks", "کارهای من"), ("calendar", "تقویم"))


class BrandMark(QWidget):
    """The app icon in miniature: two line-number dots and two text lines."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(24, 24)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rounded(p, QRectF(0, 0, 24, 24), 7, fill=col("surface"), border=col("line"))
        # padding 0 4px, rows 2.5px tall with a 3px gap, centred vertically.
        top = 12 - (2.5 * 2 + 3) / 2
        for row, (length, alpha) in enumerate(((None, 1.0), (6.0, 0.55))):
            y = top + row * 5.5
            dot = col("accent")
            dot.setAlphaF(alpha)
            line = col("text")
            line.setAlphaF(alpha)
            p.setPen(Qt.PenStyle.NoPen)
            # RTL: the dot leads on the right, the line runs to its left.
            p.setBrush(dot)
            p.drawEllipse(QRectF(24 - 5 - 2.5, y, 2.5, 2.5))
            width = (24 - 10 - 2.5 - 2) if length is None else length
            p.setBrush(line)
            p.drawRoundedRect(QRectF(24 - 5 - 2.5 - 2 - width, y, width, 2.5), 1.25, 1.25)
        p.end()


class Breadcrumb(QWidget):
    """«نوت‌پد پلاس / خانه · همه» — the name, a faint slash, where you are."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._crumb = "خانه · همه"
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(24)

    def set_crumb(self, text: str):
        self._crumb = text
        self.update()

    def crumb(self) -> str:
        return self._crumb

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        right = float(self.width())
        name_font = font(13.5, 600)
        name = "نوت‌پد پلاس"
        w = text_width(name, name_font)
        draw_text(p, QRectF(right - w, 0, w, 24), name, name_font, col("text"), elide_text=False)
        right -= w + 10
        slash_font = font(13)
        w = text_width("/", slash_font)
        draw_text(p, QRectF(right - w, 0, w, 24), "/", slash_font, col("box"), elide_text=False)
        right -= w + 10
        crumb_font = font(12.5)
        draw_text(p, QRectF(0, 0, max(0.0, right), 24),
                  elide(self._crumb, crumb_font, max(0.0, right)), crumb_font,
                  col("muted"), elide_text=False)
        p.end()


class SearchWell(Clickable):
    """A button that looks like a field: it opens the command palette."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.IBeamCursor)
        self.setFixedHeight(SEARCH_HEIGHT)
        self.setMaximumWidth(SEARCH_MAX_WIDTH)
        self.setMinimumWidth(220)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.label = "جست‌وجو در یادداشت‌ها، کارها و دستورها"
        self.hint = "Ctrl K"

    def hint_rect(self) -> QRectF:
        f = font(10.5, mono=True)
        width = text_width(self.hint, f) + 12
        return QRectF(12, (self.height() - 18) / 2, width, 18)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self.rect())
        rounded(p, r, 9, fill=col("well_hover" if self.hovered else "panel"),
                border=col("border" if self.hovered else "line"))
        # RTL: icon on the right, label, then the key hint at the left end.
        cy = r.center().y()
        draw_icon(p, "search", QRectF(r.right() - 12 - 15, cy - 7.5, 15, 15), col("muted"), 1.4)
        left = kbd(p, 12 + text_width(self.hint, font(10.5, mono=True)) + 12, cy, self.hint,
                   colour="muted", border="border")
        label_font = font(12.5)
        right = r.right() - 12 - 15 - 10
        draw_text(p, QRectF(left + 10, 0, right - left - 10, r.height()), self.label,
                  label_font, col("muted"))
        p.end()


class SyncButton(Clickable):
    """«● همگام · ۲ دقیقه پیش» — the dot says the state, the words say when."""

    STATES = {"ok": "accent", "busy": "muted", "error": "danger", "off": "box"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self._text = "همگام‌سازی…"
        self._state = "busy"
        self.setFixedHeight(30)
        self._resize()

    def setText(self, text: str):  # noqa: N802 — mirrors QAbstractButton
        self._text = text
        self._resize()
        self.update()

    def text(self) -> str:
        return self._text

    def set_state(self, state: str):
        self._state = state if state in self.STATES else "ok"
        self.update()

    def _resize(self):
        self.setFixedWidth(round(10 + 7 + 7 + text_width(self._text, font(12)) + 10))

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self.rect())
        if self.hovered:
            rounded(p, r, 8, fill=col("surface"))
        cy = r.center().y()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col(self.STATES[self._state]))
        p.drawEllipse(QPointF(r.right() - 10 - 3.5, cy), 3.5, 3.5)
        draw_text(p, QRectF(10, 0, r.width() - 10 - 10 - 7 - 7, r.height()), self._text,
                  font(12), col("text" if self.hovered else "muted"))
        p.end()


class TopBar(QWidget):
    search_requested = pyqtSignal()
    page_requested = pyqtSignal(str)
    widget_toggled = pyqtSignal()
    tasks_requested = pyqtSignal()
    theme_toggled = pyqtSignal()
    settings_requested = pyqtSignal()
    sync_requested = pyqtSignal()
    quick_capture_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("topBar")
        self.setFixedHeight(BAR_HEIGHT)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        row = QHBoxLayout(self)
        row.setContentsMargins(14, 0, 14, 0)
        row.setSpacing(12)

        # Right column: brand and breadcrumb.
        brand = QWidget()
        brand.setFixedWidth(SIDE_BLOCK)
        brand_row = QHBoxLayout(brand)
        brand_row.setContentsMargins(0, 0, 0, 0)
        brand_row.setSpacing(10)
        brand_row.addWidget(BrandMark())
        self.breadcrumb = Breadcrumb()
        brand_row.addWidget(self.breadcrumb, 1)
        row.addWidget(brand)

        # Centre column: the search well, centred and capped at 460px.
        centre = QWidget()
        centre_row = QHBoxLayout(centre)
        centre_row.setContentsMargins(0, 0, 0, 0)
        centre_row.setSpacing(0)
        centre_row.addStretch(1)
        self.search = SearchWell()
        self.search.clicked.connect(self.search_requested)
        centre_row.addWidget(self.search, 100)
        centre_row.addStretch(1)
        row.addWidget(centre, 1)

        # Left column: quick capture, sync, widget, theme — packed leftwards.
        actions = QWidget()
        actions.setFixedWidth(SIDE_BLOCK)
        actions_row = QHBoxLayout(actions)
        actions_row.setContentsMargins(0, 0, 0, 0)
        actions_row.setSpacing(4)
        actions_row.addStretch(1)

        self.quick_button = Button(
            "ضبط سریع", "bolt", height=30, radius=8, padding=(10, 10), gap=7, px=12,
            icon_size=14, stroke=1.5,
            normal={"fg": "text", "border": "line"},
            hover={"fg": "accent", "border": "accent"},
        )
        self.quick_button.setToolTip("ضبط سریع — Alt+N")
        self.quick_button.clicked.connect(self.quick_capture_requested)

        self.sync_button = SyncButton()
        self.sync_button.setToolTip("اجرای همگام‌سازی")
        self.sync_button.clicked.connect(self.sync_requested)

        square = dict(height=30, width=32, radius=8, padding=(0, 0), icon_size=16, stroke=1.4)
        self.widget_button = Button(
            "", "widget", **square,
            normal={"fg": "muted"}, hover={"bg": "surface", "fg": "text"},
            active={"bg": "divider", "fg": "accent"},
        )
        self.widget_button.setCheckable(True)
        self.widget_button.setToolTip("ویجت روز روی دسکتاپ — Ctrl+Shift+W")
        self.widget_button.clicked.connect(self.widget_toggled)

        self.theme_button = Button(
            "", "sun", **square,
            normal={"fg": "muted"}, hover={"bg": "surface", "fg": "text"},
        )
        self.theme_button.setToolTip("تم تیره / روشن")
        self.theme_button.clicked.connect(self.theme_toggled)

        for widget in (self.quick_button, self.sync_button, self.widget_button, self.theme_button):
            actions_row.addWidget(widget)
        row.addWidget(actions)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.fillRect(self.rect(), col("chrome"))
        p.setPen(col("divider"))
        p.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        p.end()

    # State

    def set_widget_active(self, active: bool):
        self.widget_button.setChecked(active)
        self.widget_button.update()

    def set_page(self, key: str):
        """Only a fallback: the window sets the full crumb with set_crumb."""
        self.breadcrumb.set_crumb(dict(PAGES).get(key, "خانه"))

    def set_crumb(self, text: str):
        self.breadcrumb.set_crumb(text)

    def set_sync(self, text: str, state: str = "ok", tooltip: str = ""):
        self.sync_button.setText(text)
        self.sync_button.set_state(state)
        if tooltip:
            self.sync_button.setToolTip(tooltip)

    def set_open_task_count(self, count: str):
        """The count lives on the rail's tasks button in v4."""

    def refresh_palette(self):
        self.update()
        for child in self.findChildren(QWidget):
            child.update()
