"""The notes board: one card per note, under a row of folder tabs.

Cards are a fixed size and wrap into a grid rather than a masonry column
layout. Masonry is what a sticky-note app does, but it leaves every card at a
different height and the eye has to hunt for the next one; a plain grid reads
as one tidy surface, which is what was asked for.

Painted rather than assembled from widgets: a card made of six children each
carrying its own stylesheet is exactly where the old sidebar rows went wrong.
"""
from PyQt6.QtCore import QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import (
    QListWidget,
    QListWidgetItem,
    QMenu,
    QStyle,
    QStyledItemDelegate,
)

from core.jalali import to_persian_digits
from core.rtl_detector import detect_direction
from ui.styles import current_palette

ROLE_CARD = Qt.ItemDataRole.UserRole

CARD_WIDTH = 248
CARD_HEIGHT = 172
CARD_GAP = 14
CARD_RADIUS = 12
PAD = 14
TITLE_GAP = 10
LINE_GAP = 5
BOX = 13
BOX_GAP = 8
TITLE_SCALE = 1.04
BODY_SCALE = 0.9
BADGE_SCALE = 0.82


def _elide(metrics: QFontMetrics, text: str, width: int) -> str:
    return metrics.elidedText(text, Qt.TextElideMode.ElideRight, width)


class NoteCardDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index) -> QSize:
        return QSize(CARD_WIDTH, CARD_HEIGHT)

    def paint(self, painter: QPainter, option, index):
        card = index.data(ROLE_CARD)
        if card is None:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        palette = current_palette()
        body = QRect(
            option.rect.left(),
            option.rect.top(),
            option.rect.width() - CARD_GAP,
            option.rect.height() - CARD_GAP,
        )

        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        fill = palette["surface_alt"] if (selected or hovered) else palette["surface"]
        edge = palette["accent"] if selected else palette["border"]

        painter.setBrush(QColor(fill))
        painter.setPen(QPen(QColor(edge), 1.4 if selected else 1.0))
        painter.drawRoundedRect(
            body.adjusted(1, 1, -1, -1), CARD_RADIUS, CARD_RADIUS
        )

        inner = body.adjusted(PAD, PAD, -PAD, -PAD)
        rtl = detect_direction(card.title) == "rtl"
        align = Qt.AlignmentFlag.AlignRight if rtl else Qt.AlignmentFlag.AlignLeft

        title_font = QFont(option.font)
        title_font.setPointSizeF(option.font.pointSizeF() * TITLE_SCALE)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QColor(palette["text"]))
        title_metrics = QFontMetrics(title_font)
        painter.drawText(
            QRect(inner.left(), inner.top(), inner.width(), title_metrics.height()),
            int(align | Qt.AlignmentFlag.AlignVCenter),
            _elide(title_metrics, card.title, inner.width()),
        )

        cursor = inner.top() + title_metrics.height() + TITLE_GAP
        body_font = QFont(option.font)
        body_font.setPointSizeF(option.font.pointSizeF() * BODY_SCALE)
        body_metrics = QFontMetrics(body_font)
        painter.setFont(body_font)

        badge_room = body_metrics.height() + 6 if card.open_tasks else 0
        floor = inner.bottom() - badge_room

        if card.tasks:
            self._paint_tasks(
                painter, card, inner, cursor, floor, body_metrics, rtl, palette
            )
        else:
            self._paint_lines(
                painter, card, inner, cursor, floor, body_metrics, align, palette
            )

        if card.open_tasks:
            badge_font = QFont(option.font)
            badge_font.setPointSizeF(option.font.pointSizeF() * BADGE_SCALE)
            painter.setFont(badge_font)
            painter.setPen(QColor(palette["accent"]))
            metrics = QFontMetrics(badge_font)
            painter.drawText(
                QRect(
                    inner.left(),
                    inner.bottom() - metrics.height(),
                    inner.width(),
                    metrics.height(),
                ),
                int(align | Qt.AlignmentFlag.AlignVCenter),
                to_persian_digits(str(card.open_tasks) + " کار باز"),
            )
        painter.restore()

    def _paint_lines(self, painter, card, inner, cursor, floor, metrics, align, palette):
        painter.setPen(QColor(palette["muted"]))
        for line in card.lines:
            if cursor + metrics.height() > floor:
                break
            painter.drawText(
                QRect(inner.left(), cursor, inner.width(), metrics.height()),
                int(align | Qt.AlignmentFlag.AlignVCenter),
                _elide(metrics, line, inner.width()),
            )
            cursor += metrics.height() + LINE_GAP

    def _paint_tasks(self, painter, card, inner, cursor, floor, metrics, rtl, palette):
        for task in card.tasks:
            if cursor + metrics.height() > floor:
                break
            row = QRect(inner.left(), cursor, inner.width(), metrics.height())
            box_y = cursor + (metrics.height() - BOX) // 2
            box_x = row.right() - BOX if rtl else row.left()
            box = QRect(box_x, box_y, BOX, BOX)

            painter.setPen(QPen(QColor(palette["border"]), 1.2))
            painter.setBrush(
                QColor(palette["accent"]) if task.done else Qt.BrushStyle.NoBrush
            )
            painter.drawRoundedRect(box, 3, 3)
            if task.done:
                painter.setPen(QPen(QColor(palette["on_accent"]), 1.6))
                painter.drawLine(
                    box.left() + 3,
                    box.center().y(),
                    box.center().x() - 1,
                    box.bottom() - 3,
                )
                painter.drawLine(
                    box.center().x() - 1,
                    box.bottom() - 3,
                    box.right() - 3,
                    box.top() + 3,
                )

            text_rect = QRect(
                row.left() if rtl else row.left() + BOX + BOX_GAP,
                cursor,
                row.width() - BOX - BOX_GAP,
                metrics.height(),
            )
            font = QFont(painter.font())
            font.setStrikeOut(task.done)
            painter.setFont(font)
            painter.setPen(QColor(palette["muted"] if task.done else palette["text"]))
            painter.drawText(
                text_rect,
                int(
                    (Qt.AlignmentFlag.AlignRight if rtl else Qt.AlignmentFlag.AlignLeft)
                    | Qt.AlignmentFlag.AlignVCenter
                ),
                _elide(metrics, task.text, text_rect.width()),
            )
            font.setStrikeOut(False)
            painter.setFont(font)
            cursor += metrics.height() + LINE_GAP


class NoteCardGrid(QListWidget):
    """A wrapping grid of note cards."""

    note_activated = pyqtSignal(str)
    note_delete_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("noteCardGrid")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setMovement(QListWidget.Movement.Static)
        self.setWrapping(True)
        self.setSpacing(0)
        self.setUniformItemSizes(True)
        self.setGridSize(QSize(CARD_WIDTH + CARD_GAP, CARD_HEIGHT + CARD_GAP))
        self.setMouseTracking(True)
        self.setFrameShape(QListWidget.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setItemDelegate(NoteCardDelegate(self))
        self.itemActivated.connect(self._activate)
        self.itemClicked.connect(self._activate)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_menu)

    def show_cards(self, cards):
        self.clear()
        for card in cards:
            item = QListWidgetItem()
            item.setData(ROLE_CARD, card)
            item.setSizeHint(QSize(CARD_WIDTH + CARD_GAP, CARD_HEIGHT + CARD_GAP))
            self.addItem(item)

    def card_titles(self) -> list[str]:
        return [self.item(row).data(ROLE_CARD).title for row in range(self.count())]

    def _activate(self, item: QListWidgetItem):
        card = item.data(ROLE_CARD)
        if card is not None:
            self.note_activated.emit(card.path)

    def _show_menu(self, position):
        item = self.itemAt(position)
        card = item.data(ROLE_CARD) if item is not None else None
        if card is None:
            return
        menu = QMenu(self)
        open_action = menu.addAction("باز کردن")
        menu.addSeparator()
        delete_action = menu.addAction("حذف یادداشت")
        chosen = menu.exec(self.viewport().mapToGlobal(position))
        if chosen is open_action:
            self.note_activated.emit(card.path)
        elif chosen is delete_action:
            self.note_delete_requested.emit(card.path)
