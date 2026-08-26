"""Render the app icon from the design, at every size Windows asks for.

The mark is the line-number gutter: three dots in the accent colour, each
followed by a line of text, fading back. Geometry is taken from
`App Icon - Line Numbers.dc.html` — a 100-unit design box:

    side padding 12   row gap 14   stroke height 9
    dot 9            dot-to-bar gap 11
    bar 2 max 44     bar 3 max 26     opacity 1 / .55 / .30

Below 32px the third row is dropped and the strokes thicken, or the mark
turns to mush.

Run:  python tools/make_icon.py
"""
import struct
import sys
from pathlib import Path

from PyQt6.QtCore import QRectF, Qt, QBuffer, QByteArray
from PyQt6.QtGui import QColor, QImage, QPainter, QGuiApplication

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

BACKGROUND = "#191a1f"
INK = "#e8e9ec"
ACCENT = "#6cb6ff"

# Windows shows these; the first two get the simplified two-row mark.
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
SIMPLE_BELOW = 32

# How much of the tile the mark occupies. The design breathes more at small
# sizes and fills the tile at 256.
INSET = {16: 0.875, 24: 0.833, 32: 0.81, 48: 0.79}


def _rows(simple: bool):
    """(dot ⌀, gap, stroke height, row gap, side pad, [(bar, opacity)…])."""
    if simple:
        # Two rows, heavier strokes: dot 13, gap 12, row gap 20, padding 10.
        return 13, 12, 13, 20, 10, [(None, 1.0), (32, 0.5)]
    return 9, 11, 9, 14, 12, [(None, 1.0), (44, 0.55), (26, 0.30)]


def render(size: int, *, monochrome: bool = False, radius_ratio: float = 0.23) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    radius = size * radius_ratio
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(BACKGROUND))
    painter.drawRoundedRect(QRectF(0, 0, size, size), radius, radius)

    simple = size < SIMPLE_BELOW
    dot, gap, stroke, row_gap, pad, bars = _rows(simple)

    # The 100-unit design box, scaled into the tile.
    box = size * INSET.get(size, 1.0)
    unit = box / 100.0
    origin = (size - box) / 2.0

    total = len(bars) * stroke + (len(bars) - 1) * row_gap
    y = origin + (box - total * unit) / 2.0

    content_right = origin + box - pad * unit
    content_left = origin + pad * unit

    ink = QColor(INK)
    dot_color = QColor(INK if monochrome else ACCENT)

    for bar_width, opacity in bars:
        # Right to left: the dot is the line number, the bar is the text.
        dot_size = dot * unit
        dot_y = y + (stroke * unit - dot_size) / 2.0
        painter.setOpacity(opacity)
        painter.setBrush(dot_color)
        painter.drawEllipse(
            QRectF(content_right - dot_size, dot_y, dot_size, dot_size)
        )

        bar_right = content_right - dot_size - gap * unit
        span = bar_right - content_left
        width = span if bar_width is None else min(span, bar_width * unit)
        height = stroke * unit
        painter.setBrush(ink)
        painter.drawRoundedRect(
            QRectF(bar_right - width, y, width, height), height / 2, height / 2
        )
        y += (stroke + row_gap) * unit

    painter.setOpacity(1.0)
    painter.end()
    return image


def _png_bytes(image: QImage) -> bytes:
    # The QByteArray has to outlive the QBuffer that wraps it; passing a
    # temporary here crashes the interpreter rather than raising.
    store = QByteArray()
    buffer = QBuffer(store)
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    return bytes(store)


def write_ico(path: Path, images: list[QImage]):
    """Pack PNG-compressed entries into an .ico container.

    Qt has no multi-size ICO writer, but the container is a fixed header plus
    one 16-byte directory entry per image, and Vista onward reads PNG payloads
    directly — so this is the whole format.
    """
    payloads = [_png_bytes(image) for image in images]
    offset = 6 + 16 * len(payloads)
    header = struct.pack("<HHH", 0, 1, len(payloads))
    directory = b""
    for image, payload in zip(images, payloads):
        side = image.width()
        directory += struct.pack(
            "<BBBBHHII",
            0 if side >= 256 else side,   # 0 means 256
            0 if side >= 256 else side,
            0,                            # palette colours
            0,                            # reserved
            1,                            # colour planes
            32,                           # bits per pixel
            len(payload),
            offset,
        )
        offset += len(payload)
    path.write_bytes(header + directory + b"".join(payloads))


def write_svg(path: Path, size: int = 256):
    """The same mark as vector, from the same numbers.

    Emitted here rather than hand-kept, so the .svg can never drift from the
    .ico the app actually ships.
    """
    dot, gap, stroke, row_gap, pad, bars = _rows(False)
    unit = size / 100.0
    total = len(bars) * stroke + (len(bars) - 1) * row_gap
    y = (size - total * unit) / 2.0
    right = size - pad * unit
    left = pad * unit

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 {size} {size}">',
        f'<rect width="{size}" height="{size}" rx="{size * 0.23:.1f}" '
        f'fill="{BACKGROUND}"/>',
    ]
    for bar_width, opacity in bars:
        d = dot * unit
        cy = y + (stroke * unit) / 2.0
        parts.append(
            f'<circle cx="{right - d / 2:.1f}" cy="{cy:.1f}" r="{d / 2:.1f}" '
            f'fill="{ACCENT}" opacity="{opacity}"/>'
        )
        bar_right = right - d - gap * unit
        span = bar_right - left
        width = span if bar_width is None else min(span, bar_width * unit)
        height = stroke * unit
        parts.append(
            f'<rect x="{bar_right - width:.1f}" y="{y:.1f}" width="{width:.1f}" '
            f'height="{height:.1f}" rx="{height / 2:.1f}" fill="{INK}" '
            f'opacity="{opacity}"/>'
        )
        y += (stroke + row_gap) * unit
    parts.append("</svg>")
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def main():
    app = QGuiApplication(sys.argv)  # kept alive for the whole render
    ASSETS.mkdir(parents=True, exist_ok=True)

    images = [render(size) for size in ICO_SIZES]
    write_ico(ASSETS / "icon.ico", images)

    render(256).save(str(ASSETS / "icon.png"), "PNG")
    write_svg(ASSETS / "icon.svg")
    # The tray sits on an unknown background, so it gets the one-colour mark.
    render(64, monochrome=True).save(str(ASSETS / "tray.png"), "PNG")

    for size in ICO_SIZES:
        print(f"  {size:>3}px")
    print(f"icon.ico  {(ASSETS / 'icon.ico').stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
