"""The notes list: a flat list under folder headings, not a folder tree.

The design's row is a name on one side and how long ago you touched it on
the other, grouped under an uppercase folder label. A QTreeWidget gives an
indent column and an expand arrow instead, and has nowhere to put the date.

Each row picks its own direction from its own name, exactly as the design
does — a Persian note reads right to left, `snippets.txt` reads left to
right, in the same list.
"""
from PyQt6.QtCore import QRect, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PyQt6.QtWidgets import QListWidget, QListWidgetItem, QStyle, QStyledItemDelegate

from core.rtl_detector import detect_direction
from ui.styles import current_palette

ROLE_PATH = Qt.ItemDataRole.UserRole
ROLE_KIND = Qt.ItemDataRole.UserRole + 1
ROLE_FIELDS = Qt.ItemDataRole.UserRole + 2

KIND_NOTE = "note"
KIND_HEADER = "header"

PAD_X = 8
PAD_Y = 7
ROW_RADIUS = 7
META_SCALE = 0.84
HEADER_SCALE = 0.8
GAP = 8


class NoteRowDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index) -> QSize:
        self.initStyleOption(option, index)
        metrics = QFontMetrics(option.font)
        if index.data(ROLE_KIND) == KIND_HEADER:
            return QSize(option.rect.width(), metrics.height() + 12)
        return QSize(option.rect.width(), metrics.height() + 2 * PAD_Y)

    def paint(self, painter: QPainter, option, index):
        self.initStyleOption(option, index)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        palette = current_palette()
        rect = option.rect
        fields = index.data(ROLE_FIELDS) or {}

        if index.data(ROLE_KIND) == KIND_HEADER:
            font = QFont(option.font)
            font.setPointSizeF(max(6.5, option.font.pointSizeF() * HEADER_SCALE))
            font.setBold(True)
            # The design letterspaces its section labels; Qt does that on the
            # font, not in the stylesheet.
            font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 112)
            painter.setFont(font)
            painter.setPen(QColor(palette["muted"]))
            painter.drawText(
                rect.adjusted(PAD_X, 6, -PAD_X, 0),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop),
                fields.get("label", "").upper(),
            )
            painter.restore()
            return

        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if fields.get("active") or selected:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(palette["surface_alt"]))
            painter.drawRoundedRect(
                rect.adjusted(2, 1, -2, -1), ROW_RADIUS, ROW_RADIUS
            )
        elif hovered:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(palette["hover"]))
            painter.drawRoundedRect(
                rect.adjusted(2, 1, -2, -1), ROW_RADIUS, ROW_RADIUS
            )

        meta = fields.get("meta", "")
        meta_font = QFont(option.font)
        meta_font.setPointSizeF(max(6.5, option.font.pointSizeF() * META_SCALE))
        meta_width = QFontMetrics(meta_font).horizontalAdvance(meta) if meta else 0

        title = fields.get("title", "")
        rtl = fields.get("rtl", False)
        inner = rect.adjusted(PAD_X, 0, -PAD_X, 0)
        title_width = max(20, inner.width() - meta_width - (GAP if meta else 0))

        # The name takes the reading edge, the date the far one.
        if rtl:
            title_rect = QRect(
                inner.right() - title_width, inner.top(), title_width, inner.height()
            )
            meta_rect = QRect(inner.left(), inner.top(), meta_width, inner.height())
            title_align = Qt.AlignmentFlag.AlignRight
        else:
            title_rect = QRect(
                inner.left(), inner.top(), title_width, inner.height()
            )
            meta_rect = QRect(
                inner.right() - meta_width, inner.top(), meta_width, inner.height()
            )
            title_align = Qt.AlignmentFlag.AlignLeft

        painter.setFont(option.font)
        painter.setPen(
            QColor(palette["accent"] if fields.get("active") else palette["text"])
        )
        painter.drawText(
            title_rect,
            int(title_align | Qt.AlignmentFlag.AlignVCenter),
            QFontMetrics(option.font).elidedText(
                title, Qt.TextElideMode.ElideRight, title_width
            ),
        )
        if meta:
            painter.setFont(meta_font)
            painter.setPen(QColor(palette["muted"]))
            painter.drawText(
                meta_rect,
                int(
                    (
                        Qt.AlignmentFlag.AlignLeft
                        if rtl
                        else Qt.AlignmentFlag.AlignRight
                    )
                    | Qt.AlignmentFlag.AlignVCenter
                ),
                meta,
            )
        painter.restore()


class NoteList(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("noteList")
        self.setMouseTracking(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setItemDelegate(NoteRowDelegate(self))

    def add_header(self, label: str):
        item = QListWidgetItem()
        item.setData(ROLE_KIND, KIND_HEADER)
        item.setData(ROLE_PATH, None)
        item.setData(ROLE_FIELDS, {"label": label})
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        self.addItem(item)
        return item

    def add_note(self, path: str, title: str, meta: str, active: bool = False):
        item = QListWidgetItem()
        item.setData(ROLE_KIND, KIND_NOTE)
        item.setData(ROLE_PATH, path)
        item.setData(
            ROLE_FIELDS,
            {
                "title": title,
                "meta": meta,
                "active": active,
                "rtl": detect_direction(title, default="ltr") == "rtl",
            },
        )
        item.setToolTip(path)
        self.addItem(item)
        return item

    def path_of(self, item) -> str | None:
        return item.data(ROLE_PATH) if item is not None else None

    def titles(self) -> list[str]:
        return [
            (self.item(row).data(ROLE_FIELDS) or {}).get("title", "")
            for row in range(self.count())
            if self.item(row).data(ROLE_KIND) == KIND_NOTE
        ]

    def headers(self) -> list[str]:
        return [
            (self.item(row).data(ROLE_FIELDS) or {}).get("label", "")
            for row in range(self.count())
            if self.item(row).data(ROLE_KIND) == KIND_HEADER
        ]
