"""Render assets/icon.svg into icon.png and a multi-size icon.ico.

Run once after editing icon.svg:
    python assets/build_icon.py
Uses only PyQt6 (already a project dependency), no Pillow required.
"""
import sys
from pathlib import Path

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QApplication

ASSETS = Path(__file__).resolve().parent
SVG = ASSETS / "icon.svg"
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)


def render(size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    QSvgRenderer(str(SVG)).render(painter)
    painter.end()
    return image


def main() -> int:
    app = QApplication(sys.argv)  # noqa: F841  (needed for QImage rendering)
    render(256).save(str(ASSETS / "icon.png"), "PNG")

    # Write a minimal ICO container holding several PNG-encoded sizes.
    import struct

    pngs = []
    for size in ICO_SIZES:
        from PyQt6.QtCore import QBuffer, QByteArray

        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QBuffer.OpenModeFlag.WriteOnly)
        render(size).save(buffer, "PNG")
        buffer.close()
        pngs.append((size, bytes(data)))

    header = struct.pack("<HHH", 0, 1, len(pngs))
    offset = 6 + 16 * len(pngs)
    entries, blobs = b"", b""
    for size, blob in pngs:
        dim = 0 if size >= 256 else size
        entries += struct.pack(
            "<BBBBHHII", dim, dim, 0, 0, 1, 32, len(blob), offset
        )
        blobs += blob
        offset += len(blob)

    (ASSETS / "icon.ico").write_bytes(header + entries + blobs)
    print(f"Wrote {ASSETS / 'icon.png'} and {ASSETS / 'icon.ico'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
