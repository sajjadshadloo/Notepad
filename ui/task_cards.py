"""The card rows My Tasks is built from.

The sidebar's task row (ui/task_rows.py) is a narrow, wrapping line. This is
the other one the design draws: a bordered card 11px/12px inside, holding a
checkbox, the task, an optional "↻ هفتگی", when it is due, and which note it
came from. Wide enough that everything fits on one line, so the text elides
rather than wrapping.

Group headings here are a label, a hairline that fills the width, and a
count — not the plain text the sidebar uses.
"""
from PyQt6.QtCore import QRect, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import QListWidget, QListWidgetItem, QStyle, QStyledItemDelegate

from ui.styles import current_palette

ROLE_PAYLOAD = Qt.ItemDataRole.UserRole
ROLE_KIND = Qt.ItemDataRole.UserRole + 1
ROLE_FIELDS = Qt.ItemDataRole.UserRole + 2

KIND_CARD = "card"
KIND_HEADER = "header"
KIND_HOUR = "hour"
KIND_EMPTY = "empty"

# The design's card metrics.
BOX = 18
BOX_BORDER = 1.6
BOX_RADIUS = 5
CARD_RADIUS = 10
PAD_X = 12
PAD_Y = 11
GAP = 12
CARD_SPACING = 6
NOTE_MAX_WIDTH = 190
# The hour column in the timeline, and the rail down a scheduled card.
HOUR_COLUMN = 56
RAIL_WIDTH = 3

TEXT_SCALE = 1.0
SMALL_SCALE = 0.86
HEADER_SCALE = 0.86


def _font(base: QFont, scale: float = 1.0, bold: bool = False) -> QFont:
    font = QFont(base)
    font.setPointSizeF(max(6.5, base.pointSizeF() * scale))
    font.setBold(bold)
    return font


class TaskCardDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index) -> QSize:
        self.initStyleOption(option, index)
        metrics = QFontMetrics(option.font)
        kind = index.data(ROLE_KIND)
        if kind == KIND_HEADER:
            return QSize(option.rect.width(), metrics.height() + 18)
        if kind == KIND_HOUR:
            return QSize(option.rect.width(), metrics.height() + 14)
        if kind == KIND_EMPTY:
            return QSize(option.rect.width(), metrics.height() + 20)
        height = max(metrics.height(), BOX) + 2 * PAD_Y
        return QSize(option.rect.width(), height + CARD_SPACING)

    def paint(self, painter: QPainter, option, index):
        self.initStyleOption(option, index)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        palette = current_palette()
        kind = index.data(ROLE_KIND)
        fields = index.data(ROLE_FIELDS) or {}

        if kind == KIND_HEADER:
            self._paint_header(painter, option, fields, palette)
        elif kind == KIND_HOUR:
            self._paint_hour(painter, option, fields, palette)
        elif kind == KIND_EMPTY:
            painter.setPen(QColor(palette["muted"]))
            painter.setFont(option.font)
            painter.drawText(
                option.rect,
                int(Qt.AlignmentFlag.AlignCenter),
                index.data(Qt.ItemDataRole.DisplayRole) or "",
            )
        else:
            self._paint_card(painter, option, fields, palette)
        painter.restore()

    # Group heading: label · hairline · count

    def _paint_header(self, painter, option, fields, palette):
        rect = option.rect
        font = _font(option.font, HEADER_SCALE, True)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        label = fields.get("label", "")
        colour = QColor(palette["danger"] if fields.get("urgent") else palette["muted"])
        count = fields.get("count", "")
        count_width = metrics.horizontalAdvance(count) if count else 0

        baseline = rect.top() + 12
        label_width = metrics.horizontalAdvance(label)
        painter.setPen(colour)
        painter.drawText(
            QRect(rect.right() - label_width, baseline, label_width, metrics.height()),
            int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
            label,
        )
        if count:
            painter.setPen(QColor(palette["muted"]))
            painter.drawText(
                QRect(rect.left(), baseline, count_width, metrics.height()),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                count,
            )
        # The hairline fills whatever is left between the two.
        line_left = rect.left() + count_width + GAP
        line_right = rect.right() - label_width - GAP
        if line_right > line_left:
            pen = QPen(QColor(palette["border"]))
            pen.setWidth(1)
            painter.setPen(pen)
            middle = baseline + metrics.height() // 2
            painter.drawLine(line_left, middle, line_right, middle)

    def _paint_hour(self, painter, option, fields, palette):
        rect = option.rect
        pen = QPen(QColor(palette["border"]))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawLine(rect.left(), rect.top(), rect.right(), rect.top())
        font = _font(option.font, SMALL_SCALE, bool(fields.get("now")))
        painter.setFont(font)
        painter.setPen(
            QColor(palette["accent"] if fields.get("now") else palette["muted"])
        )
        painter.drawText(
            QRect(rect.left(), rect.top() + 6, HOUR_COLUMN, rect.height() - 6),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop),
            fields.get("label", ""),
        )

    # The card itself

    def _paint_card(self, painter, option, fields, palette):
        rect = option.rect.adjusted(0, 0, 0, -CARD_SPACING)
        indent = HOUR_COLUMN + GAP if fields.get("timeline") else 0
        rect = QRect(
            rect.left(), rect.top(), rect.width() - indent, rect.height()
        )

        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        painter.setBrush(
            QColor(palette["surface_alt"] if selected else palette["surface"])
        )
        pen = QPen(
            QColor(
                palette["accent"]
                if selected
                else (palette["accent_hover"] if hovered else palette["border"])
            )
        )
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawRoundedRect(
            rect.adjusted(0, 0, -1, -1), CARD_RADIUS, CARD_RADIUS
        )

        if fields.get("rail"):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(fields["rail"]))
            painter.drawRoundedRect(
                QRect(rect.left() + 1, rect.top() + 6, RAIL_WIDTH, rect.height() - 13),
                2,
                2,
            )

        done = bool(fields.get("done"))
        overdue = bool(fields.get("overdue"))
        centre = rect.top() + rect.height() // 2

        # Right to left: box, text, then the metadata closing on the left.
        box_x = rect.right() - PAD_X - BOX
        self._paint_box(
            painter, QRect(box_x, centre - BOX // 2, BOX, BOX), palette, done
        )

        small = _font(option.font, SMALL_SCALE)
        metrics = QFontMetrics(small)
        left = rect.left() + PAD_X

        note = fields.get("note", "")
        if note:
            width = min(NOTE_MAX_WIDTH, metrics.horizontalAdvance(note))
            painter.setFont(small)
            painter.setPen(QColor(palette["muted"]))
            painter.drawText(
                QRect(left, rect.top(), width, rect.height()),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                metrics.elidedText(note, Qt.TextElideMode.ElideLeft, width),
            )
            left += width + GAP

        when = fields.get("when", "")
        if when:
            width = metrics.horizontalAdvance(when)
            painter.setFont(small)
            painter.setPen(
                QColor(palette["danger"] if overdue else palette["muted"])
            )
            painter.drawText(
                QRect(left, rect.top(), width, rect.height()),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                when,
            )
            left += width + GAP

        if fields.get("repeats"):
            label = "↻ هفتگی"
            width = metrics.horizontalAdvance(label)
            painter.setFont(small)
            painter.setPen(QColor(palette["muted"]))
            painter.drawText(
                QRect(left, rect.top(), width, rect.height()),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                label,
            )
            left += width + GAP

        text_right = box_x - GAP
        text_width = max(30, text_right - left)
        painter.setFont(option.font)
        colour = QColor(
            palette["muted"]
            if done
            else (palette["danger"] if overdue else palette["text"])
        )
        painter.setPen(colour)
        font = QFont(option.font)
        font.setStrikeOut(done)
        painter.setFont(font)
        painter.drawText(
            QRect(left, rect.top(), text_width, rect.height()),
            int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
            QFontMetrics(font).elidedText(
                fields.get("text", ""), Qt.TextElideMode.ElideLeft, text_width
            ),
        )

    def _paint_box(self, painter, box: QRect, palette: dict, done: bool):
        pen = QPen(QColor(palette["accent"] if done else palette["border"]))
        pen.setWidthF(BOX_BORDER)
        painter.setPen(pen)
        painter.setBrush(
            QColor(palette["accent"]) if done else Qt.BrushStyle.NoBrush
        )
        painter.drawRoundedRect(box, BOX_RADIUS, BOX_RADIUS)
        if done:
            tick = QPen(QColor(palette["on_accent"]))
            tick.setWidthF(2.0)
            tick.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(tick)
            left, top = box.left(), box.top()
            painter.drawLine(left + 4, top + 9, left + 7, top + 12)
            painter.drawLine(left + 7, top + 12, left + 14, top + 5)


class TaskCardList(QListWidget):
    """Headings and cards, right to left, drawn by TaskCardDelegate."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("taskCards")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setMouseTracking(True)
        self.setUniformItemSizes(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setItemDelegate(TaskCardDelegate(self))

    def add_header(self, label: str, count: str = "", urgent: bool = False):
        item = QListWidgetItem()
        item.setData(ROLE_KIND, KIND_HEADER)
        item.setData(ROLE_PAYLOAD, None)
        item.setData(ROLE_FIELDS, {"label": label, "count": count, "urgent": urgent})
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        self.addItem(item)
        return item

    def add_hour(self, label: str, now: bool = False):
        item = QListWidgetItem()
        item.setData(ROLE_KIND, KIND_HOUR)
        item.setData(ROLE_PAYLOAD, None)
        item.setData(ROLE_FIELDS, {"label": label, "now": now})
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        self.addItem(item)
        return item

    def add_card(
        self,
        task,
        when: str = "",
        note: str = "",
        timeline: bool = False,
        rail: str = "",
    ):
        item = QListWidgetItem()
        item.setData(ROLE_KIND, KIND_CARD)
        item.setData(ROLE_PAYLOAD, (task.path, task.line_number))
        item.setData(
            ROLE_FIELDS,
            {
                "text": task.text,
                "when": when,
                "note": note,
                "done": task.done,
                "overdue": task.overdue,
                "repeats": task.repeats,
                "timeline": timeline,
                "rail": rail,
            },
        )
        item.setToolTip(task.text)
        self.addItem(item)
        return item

    def add_empty(self, message: str):
        item = QListWidgetItem(message)
        item.setData(ROLE_KIND, KIND_EMPTY)
        item.setData(ROLE_PAYLOAD, None)
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        self.addItem(item)
        return item

    def payload_of(self, item) -> tuple | None:
        return item.data(ROLE_PAYLOAD) if item is not None else None

    def row_kind(self, row: int) -> str:
        return self.item(row).data(ROLE_KIND)

    def card_texts(self) -> list[str]:
        return [
            (self.item(row).data(ROLE_FIELDS) or {}).get("text", "")
            for row in range(self.count())
            if self.row_kind(row) == KIND_CARD
        ]

    def header_texts(self) -> list[str]:
        return [
            (self.item(row).data(ROLE_FIELDS) or {}).get("label", "")
            for row in range(self.count())
            if self.row_kind(row) == KIND_HEADER
        ]
