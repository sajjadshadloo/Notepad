"""The v4 design's building blocks: type, colour, icons and painted buttons.

The design is written in CSS pixels, so everything here speaks pixels too:
`font(13.5, 600)` is the design's `font-size:13.5px;font-weight:600`, and a
button's padding and radius are the numbers in its style attribute. Keeping
that one-to-one is what lets a screen be checked against the design by
reading the two side by side.

Colours are always tokens (see ui/styles.py), never hex, so the palettes and
the light theme still reach every pixel.
"""
from functools import lru_cache

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen, QTextOption
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QAbstractButton, QSizePolicy, QWidget

from ui.styles import current_palette

UI_FAMILIES = ["Vazirmatn", "Inter", "Segoe UI", "sans-serif"]
# The design asks for `ui-monospace, Consolas`; on Windows that resolves to
# Consolas, so Consolas leads.
MONO_FAMILIES = ["Consolas", "Cascadia Mono", "monospace"]

_WEIGHTS = {
    300: QFont.Weight.Light,
    400: QFont.Weight.Normal,
    500: QFont.Weight.Medium,
    600: QFont.Weight.DemiBold,
    700: QFont.Weight.Bold,
}


# Type

def font(px: float, weight: int = 400, *, mono: bool = False) -> QFont:
    """The design's font-size (CSS px) and font-weight as a QFont.

    Point sizes, because QFont.setPixelSize only takes whole pixels and the
    design uses 10.5, 11.5, 12.5 and 13.5 throughout. At 96 logical DPI a
    CSS pixel is three quarters of a point.
    """
    f = QFont()
    f.setFamilies(MONO_FAMILIES if mono else UI_FAMILIES)
    f.setPointSizeF(px * 0.75)
    f.setWeight(_WEIGHTS.get(weight, QFont.Weight.Normal))
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return f


def text_width(text: str, f: QFont) -> float:
    return QFontMetricsF(f).horizontalAdvance(text)


def elide(text: str, f: QFont, width: float) -> str:
    return QFontMetricsF(f).elidedText(text, Qt.TextElideMode.ElideRight, width)


# Colour

def col(token: str) -> QColor:
    return QColor(current_palette()[token])


def tint(token: str, alpha: float) -> QColor:
    colour = QColor(current_palette()[token])
    colour.setAlphaF(alpha)
    return colour


def overlay_colour() -> QColor:
    """The backdrop behind a modal: rgba(8,9,11,.62) over the window."""
    colour = QColor(current_palette()["chrome"]).darker(260)
    colour.setAlphaF(0.62)
    return colour


# Icons — the design's own SVG bodies, 16-unit viewBox, stroke=currentColor

ICONS = {
    "search": '<circle cx="7" cy="7" r="4.5"/><line x1="10.5" y1="10.5" x2="14" y2="14"/>',
    "bolt": '<path d="M9 1.8 3.5 9h4l-1 5.2L12.5 7h-4z"/>',
    "widget": '<rect x="1.5" y="2.5" width="13" height="11" rx="2"/><line x1="4" y1="6" x2="11" y2="6"/><line x1="4" y1="9" x2="9" y2="9"/>',
    "sun": '<circle cx="8" cy="8" r="3.2"/><line x1="8" y1="1.2" x2="8" y2="2.6"/><line x1="8" y1="13.4" x2="8" y2="14.8"/><line x1="1.2" y1="8" x2="2.6" y2="8"/><line x1="13.4" y1="8" x2="14.8" y2="8"/>',
    "home": '<path d="M2.5 7 8 2.5 13.5 7v6a1 1 0 0 1-1 1h-9a1 1 0 0 1-1-1z"/><path d="M6.5 14v-3.5h3V14"/>',
    "note": '<path d="M4 1.5h5.5L13 5v8.5a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-11a1 1 0 0 1 1-1z"/><path d="M9.5 1.5V5H13"/><path d="M5.5 8.5h5M5.5 11h3.5"/>',
    "file": '<path d="M4 1.5h5.5L13 5v8.5a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-11a1 1 0 0 1 1-1z"/><path d="M9.5 1.5V5H13"/>',
    "tasks": '<rect x="2" y="2.5" width="12" height="11" rx="2.2"/><polyline points="5,8 7,10 11,5.6"/>',
    "calendar": '<rect x="2" y="3" width="12" height="11" rx="2.2"/><path d="M2 6.5h12M5.5 1.5v3M10.5 1.5v3"/>',
    "calendar_small": '<rect x="2" y="3" width="12" height="11" rx="2.2"/><path d="M2 6.5h12"/>',
    "settings": '<path d="M2.5 4.5h6.5M12.5 4.5h1M2.5 11.5h1M7 11.5h6.5"/><circle cx="10.8" cy="4.5" r="1.7"/><circle cx="5.2" cy="11.5" r="1.7"/>',
    "plus": '<path d="M8 3v10M3 8h10"/>',
    "folder": '<path d="M1.8 4.5a1 1 0 0 1 1-1h3.4l1.5 1.6h5.5a1 1 0 0 1 1 1v6.4a1 1 0 0 1-1 1H2.8a1 1 0 0 1-1-1z"/>',
    "trash": '<path d="M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.6 9h5.8l.6-9"/>',
    "grid": '<rect x="2" y="2" width="5" height="5" rx="1.3"/><rect x="9" y="2" width="5" height="5" rx="1.3"/><rect x="2" y="9" width="5" height="5" rx="1.3"/><rect x="9" y="9" width="5" height="5" rx="1.3"/>',
    "list": '<path d="M2.5 4h11M2.5 8h11M2.5 12h11"/>',
    "pin": '<path d="M10 1.8 14.2 6l-1.8.7-2.6 2.6.2 2.9-1.1 1.1-5.2-5.2 1.1-1.1 2.9.2 2.6-2.6z"/><path d="M5.3 10.7 1.8 14.2"/>',
    "check": '<polyline points="3,8.5 6.5,12 13,4.5"/>',
    "open_out": '<path d="M11 5 5 11M5.5 5H11v5.5"/>',
    "chevron_right": '<path d="M6 4l4 4-4 4"/>',
    "chevron_left": '<path d="M10 4 6 8l4 4"/>',
    "close": '<path d="M4 4l8 8M12 4l-8 8"/>',
    "bullets": '<path d="M6 4h7.5M6 8h7.5M6 12h7.5"/><circle cx="3" cy="4" r=".7" fill="currentColor"/><circle cx="3" cy="8" r=".7" fill="currentColor"/><circle cx="3" cy="12" r=".7" fill="currentColor"/>',
    "link": '<path d="M6.8 9.2a2.6 2.6 0 0 0 3.7 0l2.2-2.2a2.6 2.6 0 0 0-3.7-3.7l-.8.8"/><path d="M9.2 6.8a2.6 2.6 0 0 0-3.7 0L3.3 9a2.6 2.6 0 0 0 3.7 3.7l.8-.8"/>',
    "align": '<path d="M3 4h10M3 8h10M7 12h6"/>',
    "focus": '<path d="M2.5 6V2.5H6M10 2.5h3.5V6M13.5 10v3.5H10M6 13.5H2.5V10"/>',
    "command": '<path d="M3 5l3 3-3 3M8 11.5h5"/>',
}

_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="none" '
    'stroke="{c}" stroke-width="{w}" stroke-linecap="round" '
    'stroke-linejoin="round">{body}</svg>'
)


@lru_cache(maxsize=512)
def _renderer(name: str, colour: str, stroke: float) -> QSvgRenderer:
    body = ICONS[name].replace("currentColor", colour)
    return QSvgRenderer(_SVG.format(c=colour, w=stroke, body=body).encode("utf-8"))


def draw_icon(painter: QPainter, name: str, rect: QRectF, colour: QColor,
              stroke: float = 1.4):
    """Render one design icon straight into the painter — crisp at any DPI."""
    if name not in ICONS:
        return
    _renderer(name, colour.name(), stroke).render(painter, QRectF(rect))


# Shapes

def rounded(painter: QPainter, rect: QRectF, radius: float, fill=None,
            border=None, border_width: float = 1.0, dashed: bool = False):
    """A CSS box: background, then a border drawn inside the rect."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    if fill is not None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, radius, radius)
    if border is not None:
        pen = QPen(border, border_width)
        if dashed:
            pen.setStyle(Qt.PenStyle.DashLine)
            pen.setDashPattern([4 / border_width, 3 / border_width])
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        inset = border_width / 2
        inner = rect.adjusted(inset, inset, -inset, -inset)
        painter.drawRoundedRect(inner, max(0.0, radius - inset), max(0.0, radius - inset))
    painter.restore()


def draw_checkbox(painter: QPainter, centre: QPointF, size: float, radius: float,
                  done: bool, border: QColor | None = None,
                  border_width: float = 1.5, check_size: float = 11,
                  check_stroke: float = 2.4):
    """The design's checkbox: an outlined square, or an accent square with a
    dark check (stroke #0d1117 = on_accent)."""
    rect = QRectF(centre.x() - size / 2, centre.y() - size / 2, size, size)
    if done:
        rounded(painter, rect, radius, fill=col("accent"))
        glyph = QRectF(centre.x() - check_size / 2, centre.y() - check_size / 2,
                       check_size, check_size)
        draw_icon(painter, "check", glyph, col("on_accent"), check_stroke)
    else:
        rounded(painter, rect, radius, border=border or col("box"),
                border_width=border_width)


def _is_ltr(text: str) -> bool:
    """True for text with no Persian/Arabic letters: a path, «Ctrl K», «tasks.md»."""
    return not any("؀" <= ch <= "ۿ" or "ﭐ" <= ch <= "﻿" for ch in text)


def text_option(align, text: str, wrap: bool = False) -> QTextOption:
    """Right-to-left paragraph direction for Persian, whatever it starts with.

    QPainter otherwise takes its base direction from the painter, and a
    Persian line that opens with a digit — «۶ یادداشت» — was laid out as
    left-to-right, the number at the far end.
    """
    option = QTextOption(Qt.AlignmentFlag(int(align)) | Qt.AlignmentFlag.AlignAbsolute)
    option.setTextDirection(
        Qt.LayoutDirection.LeftToRight if _is_ltr(text) else Qt.LayoutDirection.RightToLeft)
    option.setWrapMode(QTextOption.WrapMode.WordWrap if wrap else QTextOption.WrapMode.NoWrap)
    return option


def draw_text(painter: QPainter, rect: QRectF, text: str, f: QFont, colour: QColor,
              align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
              strike: bool = False, elide_text: bool = True, wrap: bool = False):
    painter.save()
    if strike:
        f = QFont(f)
        f.setStrikeOut(True)
    painter.setFont(f)
    painter.setPen(colour)
    shown = elide(text, f, rect.width()) if (elide_text and not wrap) else text
    painter.drawText(rect, shown, text_option(align, shown, wrap))
    painter.restore()


def kbd(painter: QPainter, right: float, centre_y: float, text: str, px: float = 10.5,
        colour: str = "muted", border: str = "border", pad_x: float = 6,
        pad_y: float = 1, radius: float = 5) -> float:
    """A monospace key hint in a thin pill, laid out from its right edge.

    Returns the pill's left edge so callers can keep laying out leftwards.
    """
    f = font(px, mono=True)
    width = text_width(text, f) + pad_x * 2
    height = QFontMetricsF(f).height() + pad_y * 2
    rect = QRectF(right - width, centre_y - height / 2, width, height)
    rounded(painter, rect, radius, border=col(border))
    draw_text(painter, rect, text, f, col(colour),
              Qt.AlignmentFlag.AlignCenter, elide_text=False)
    return rect.left()


def transparent_scroll(scroll):
    """Let a QScrollArea show whatever its parent paints.

    A scroll area's viewport and the page inside it otherwise fill with the
    stock palette's light grey — the stylesheet never names them.
    """
    # Only the viewport and the page in it — the scroll bars live in sibling
    # containers and keep the application sheet's styling.
    scroll.setStyleSheet(
        "QScrollArea { background: transparent; border: none; }"
        " QWidget#qt_scrollarea_viewport { background: transparent; }"
        " QWidget#qt_scrollarea_viewport > QWidget { background: transparent; }"
    )
    scroll.viewport().setAutoFillBackground(False)


# A painted button

class Button(QAbstractButton):
    """A button drawn from design numbers rather than QSS.

    Each look is a dict of token names: bg, fg, border (any may be None for
    transparent). `normal`, `hover` and `active` (checked) cascade — hover
    and active only name what changes. Icon, text and an optional trailing
    badge are laid out right-to-left with `gap` between them, inside
    `padding` (right, left) — the order a Persian reader meets them.
    """

    def __init__(self, text: str = "", icon: str | None = None, *,
                 height: int = 30, width: int | None = None, radius: float = 8,
                 padding: tuple = (10, 10), gap: float = 7, px: float = 12,
                 weight: int = 400, icon_size: float = 14, stroke: float = 1.5,
                 normal: dict | None = None, hover: dict | None = None,
                 active: dict | None = None, align: str = "center",
                 border_width: float = 1.0, parent=None):
        super().__init__(parent)
        self.setText(text)
        self._icon = icon
        self._height = height
        self._fixed_width = width
        self._radius = radius
        self._padding = padding
        self._gap = gap
        self._font = font(px, weight)
        self._icon_size = icon_size
        self._stroke = stroke
        self._normal = {"bg": None, "fg": "text", "border": None, "icon": None}
        self._normal.update(normal or {})
        self._hover = hover or {}
        self._active = active or {}
        self._align = align
        self._border_width = border_width
        self._hovered = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(height)
        if width is not None:
            self.setFixedWidth(width)
        else:
            self.setFixedWidth(round(self._content_width()))

    def set_icon(self, name: str | None):
        self._icon = name
        self.update()

    def set_label(self, text: str):
        self.setText(text)
        if self._fixed_width is None:
            self.setFixedWidth(round(self._content_width()))
        self.update()

    def _content_width(self) -> float:
        width = self._padding[0] + self._padding[1]
        parts = 0
        if self._icon:
            width += self._icon_size
            parts += 1
        if self.text():
            width += text_width(self.text(), self._font)
            parts += 1
        return width + self._gap * max(0, parts - 1)

    def sizeHint(self) -> QSize:
        return QSize(round(self._content_width()), self._height)

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def look(self) -> dict:
        look = dict(self._normal)
        if self.isChecked():
            look.update(self._active)
        elif self._hovered:
            look.update(self._hover)
        return look

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        look = self.look()
        rect = QRectF(self.rect())
        rounded(
            painter, rect, self._radius,
            fill=col(look["bg"]) if look.get("bg") else None,
            border=col(look["border"]) if look.get("border") else None,
            border_width=self._border_width,
        )
        fg = col(look["fg"])
        icon_colour = col(look["icon"]) if look.get("icon") else fg
        content = self._content_width() - self._padding[0] - self._padding[1]
        if self._align == "right":
            x = rect.right() - self._padding[0]
        else:
            x = rect.center().x() + content / 2
        cy = rect.center().y()
        if self._icon:
            size = self._icon_size
            draw_icon(painter, self._icon, QRectF(x - size, cy - size / 2, size, size),
                      icon_colour, self._stroke)
            x -= size + self._gap
        if self.text():
            width = text_width(self.text(), self._font)
            available = x - (rect.left() + self._padding[1])
            draw_text(painter, QRectF(x - max(width, available), rect.top(),
                                      max(width, available), rect.height()),
                      self.text(), self._font, fg)
        painter.end()


class Surface(QWidget):
    """A plain region that paints one token, with optional edge borders.

    `edges` names the sides that carry a 1px `divider` line, in screen terms
    ("left", "right", "top", "bottom").
    """

    def __init__(self, token: str, edges: tuple = (), border: str = "divider", parent=None):
        super().__init__(parent)
        self._token = token
        self._edges = edges
        self._border = border
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), col(self._token))
        painter.setPen(QPen(col(self._border), 1))
        r = self.rect()
        if "left" in self._edges:
            painter.drawLine(r.left(), r.top(), r.left(), r.bottom())
        if "right" in self._edges:
            painter.drawLine(r.right(), r.top(), r.right(), r.bottom())
        if "top" in self._edges:
            painter.drawLine(r.left(), r.top(), r.right(), r.top())
        if "bottom" in self._edges:
            painter.drawLine(r.left(), r.bottom(), r.right(), r.bottom())
        painter.end()


class Clickable(QWidget):
    """A painted widget that knows hover and emits clicked."""

    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.hovered = False
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def enterEvent(self, event):
        self.hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hovered = False
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
            event.position().toPoint()
        ):
            self.clicked.emit()
        super().mouseReleaseEvent(event)
