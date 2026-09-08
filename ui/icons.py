"""The design's line icons, drawn from its own SVG paths.

Every icon in `Notepad Plus - Redesign.dc.html` is a 16-unit stroked outline
at `stroke-width:1.3` with `stroke="currentColor"`. The paths below are those
exact ones; the colour is substituted per call, because a stroke icon has to
be recoloured to follow hover and disabled states — Qt cannot tint an icon
for you.

Rendered through QtSvg (already shipped: Qt6Svg.dll is in the build) and
cached, so hovering a toolbar does not re-rasterise anything.
"""
from functools import lru_cache

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

# Straight from the design's markup.
PATHS = {
    "sidebar": (
        '<rect x="1.5" y="2.5" width="13" height="11" rx="2"></rect>'
        '<line x1="6" y1="2.5" x2="6" y2="13.5"></line>'
    ),
    "close": (
        '<line x1="4" y1="4" x2="12" y2="12"></line>'
        '<line x1="12" y1="4" x2="4" y2="12"></line>'
    ),
    "search": (
        '<circle cx="7" cy="7" r="4.5"></circle>'
        '<line x1="10.5" y1="10.5" x2="14" y2="14"></line>'
    ),
    "tasks": (
        '<rect x="2" y="2.5" width="12" height="11" rx="2"></rect>'
        '<polyline points="5,8 7,10 11,5.6"></polyline>'
    ),
    "theme": (
        '<circle cx="8" cy="8" r="3.4"></circle>'
        '<line x1="8" y1="1" x2="8" y2="2.6"></line>'
        '<line x1="8" y1="13.4" x2="8" y2="15"></line>'
        '<line x1="1" y1="8" x2="2.6" y2="8"></line>'
        '<line x1="13.4" y1="8" x2="15" y2="8"></line>'
    ),
    "settings": (
        '<circle cx="8" cy="8" r="2.4"></circle>'
        '<circle cx="8" cy="8" r="5.6"></circle>'
    ),
}

_TEMPLATE = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
    'viewBox="0 0 16 16" fill="none" stroke="{color}" stroke-width="1.3" '
    'stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
)

# Icons are drawn at 4x and scaled by QIcon, so they stay crisp on a
# high-DPI screen without asking the widget about its device pixel ratio —
# that question re-enters window creation while the window is being built.
_OVERSAMPLE = 4


@lru_cache(maxsize=256)
def icon(name: str, color: str, size: int = 15) -> QIcon:
    """One line icon in one colour. Cached — hover states ask repeatedly."""
    body = PATHS.get(name)
    if body is None:
        return QIcon()
    side = size * _OVERSAMPLE
    svg = _TEMPLATE.format(size=side, color=color, body=body)
    renderer = QSvgRenderer(svg.encode("utf-8"))
    pixmap = QPixmap(side, side)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)


def icon_size(size: int = 15) -> QSize:
    return QSize(size, size)
