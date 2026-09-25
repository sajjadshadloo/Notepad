"""The home page's middle: a greeting, the folder's title, and its notes.

Cards follow the design's `grid-template-columns: repeat(auto-fill,
minmax(236px,1fr))` with a 14px gap — as many 236px columns as fit, then
stretched to fill — and each row is as tall as its tallest card. The list
view is the same notes as a four-column table.

The folder is the category. Nothing is stored anywhere else: make a folder in
Explorer and it appears; move a file and it changes category.
"""
import time
from datetime import datetime

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QFontMetricsF, QPainter
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QMenu,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.jalali import to_persian_digits
from core.note_library import (
    ROOT_LABEL,
    categories,
    display_name,
    edited_label,
    in_category,
    load_library,
)
from ui.kit import (
    Button,
    col,
    draw_checkbox,
    draw_icon,
    draw_text,
    elide,
    font,
    rounded,
    text_width,
)

ALL_LABEL = "همه"
MIN_CARD = 236
GAP = 14
CARD_MIN_HEIGHT = 178


def _line_height(px: float, factor: float) -> float:
    return px * factor


class HomeHeader(QWidget):
    """Greeting, title and count on the right; view toggle and New on the left."""

    view_changed = pyqtSignal(str)
    new_note_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.greeting = ""
        self.title = "همه‌ی یادداشت‌ها"
        self.subtitle = ""
        self._g = font(12.5)
        self._t = font(24, 700)
        self._s = font(12.5)
        self._heights = (
            QFontMetricsF(self._g).height(),
            QFontMetricsF(self._t).height(),
            QFontMetricsF(self._s).height(),
        )
        self.setFixedHeight(round(sum(self._heights) + 8))
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        row.addStretch(1)

        toggle = _Segment()
        self.grid_button = Button(
            "", "grid", height=28, width=32, radius=6, padding=(0, 0), icon_size=15,
            stroke=1.35, normal={"fg": "muted"}, active={"bg": "hover", "fg": "text"},
        )
        self.list_button = Button(
            "", "list", height=28, width=32, radius=6, padding=(0, 0), icon_size=15,
            stroke=1.35, normal={"fg": "muted"}, active={"bg": "hover", "fg": "text"},
        )
        self.grid_button.setToolTip("کارت")
        self.list_button.setToolTip("فهرست")
        for button, mode in ((self.grid_button, "grid"), (self.list_button, "list")):
            button.setCheckable(True)
            button.clicked.connect(lambda _c=False, m=mode: self.set_view(m, emit=True))
            toggle.add(button)
        row.addWidget(toggle, 0, Qt.AlignmentFlag.AlignBottom)

        self.new_button = Button(
            "یادداشت جدید", "plus", height=36, radius=9, padding=(12, 14), gap=8, px=13,
            weight=600, icon_size=14, stroke=1.8,
            normal={"bg": "accent", "fg": "on_accent"}, hover={"bg": "accent_hover"},
        )
        self.new_button.clicked.connect(self.new_note_requested)
        row.addWidget(self.new_button, 0, Qt.AlignmentFlag.AlignBottom)
        self.set_view("grid")

    def set_view(self, mode: str, emit: bool = False):
        self.grid_button.setChecked(mode == "grid")
        self.list_button.setChecked(mode == "list")
        self.grid_button.update()
        self.list_button.update()
        if emit:
            self.view_changed.emit(mode)

    def set_texts(self, greeting: str, title: str, subtitle: str):
        self.greeting, self.title, self.subtitle = greeting, title, subtitle
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        width = self.width() * 0.6
        right = self.width()
        y = 0.0
        for text, f, colour, h in (
            (self.greeting, self._g, "muted", self._heights[0]),
            (self.title, self._t, "text", self._heights[1]),
            (self.subtitle, self._s, "muted", self._heights[2]),
        ):
            draw_text(p, QRectF(right - width, y, width, h), text, f, col(colour))
            y += h + 4
        p.end()


class _Segment(QWidget):
    """The rounded well two or three toggle buttons sit in (padding 3, gap 2)."""

    def __init__(self, parent=None, fill: str = "surface", border: str = "surface_alt",
                 radius: float = 9):
        super().__init__(parent)
        self._fill, self._border, self._radius = fill, border, radius
        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(3, 3, 3, 3)
        self._row.setSpacing(2)

    def add(self, button):
        self._row.addWidget(button)

    def paintEvent(self, _event):
        p = QPainter(self)
        rounded(p, QRectF(self.rect()), self._radius, fill=col(self._fill),
                border=col(self._border) if self._border else None)
        p.end()


class CardGrid(QWidget):
    """Every note as a card, painted — no delegate, no item views."""

    note_activated = pyqtSignal(str)
    note_delete_requested = pyqtSignal(str)
    pin_toggled = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._cards = []
        self._pinned: set = set()
        self._rects: list[QRectF] = []
        self._hover = -1
        self._now = time.time()
        self._title_font = font(14.5, 600)
        self._body_font = font(12.5)
        self._foot_font = font(11.5)

    def show_cards(self, cards, pinned=frozenset()):
        self._cards = list(cards)
        self._pinned = set(pinned)
        self._now = time.time()
        self._hover = -1
        self._layout(self.width())
        self.update()

    def titles(self) -> list[str]:
        return [card.title for card in self._cards]

    def activate(self, index: int):
        """Open the card at `index`, as a click on it would."""
        if 0 <= index < len(self._cards):
            self.note_activated.emit(self._cards[index].path)

    # Geometry

    def _columns(self, width: float) -> tuple[int, float]:
        columns = max(1, int((width + GAP) // (MIN_CARD + GAP)))
        return columns, (width - GAP * (columns - 1)) / columns

    def _title_height(self, card, width: float) -> float:
        inner = width - 32 - (22 if card.path in self._pinned else 0)
        rect = QFontMetricsF(self._title_font).boundingRect(
            QRectF(0, 0, inner, 1000), int(Qt.TextFlag.TextWordWrap), card.title)
        lines = max(1, round(rect.height() / QFontMetricsF(self._title_font).lineSpacing()))
        return lines * _line_height(14.5, 1.5)

    def _natural_height(self, card, width: float) -> float:
        rows = len(card.tasks) + len(card.lines)
        body = rows * _line_height(12.5, 1.6) + max(0, rows - 1) * 6
        chip = QFontMetricsF(self._foot_font).height() + 2
        footer = 1 + 10 + chip
        return 16 + self._title_height(card, width) + 12 + body + 12 + footer + 14

    def _layout(self, width: float):
        self._rects = []
        if not self._cards or width <= 0:
            self.setFixedHeight(0)
            return
        columns, card_width = self._columns(width)
        y = 0.0
        for start in range(0, len(self._cards), columns):
            row = self._cards[start:start + columns]
            height = max([CARD_MIN_HEIGHT] + [self._natural_height(c, card_width) for c in row])
            for index in range(len(row)):
                # RTL: the first card of a row sits against the right edge.
                x = width - (index + 1) * card_width - index * GAP
                self._rects.append(QRectF(x, y, card_width, height))
            y += height + GAP
        self.setFixedHeight(round(y - GAP))

    def resizeEvent(self, event):
        self._layout(event.size().width())
        super().resizeEvent(event)

    def sizeHint(self) -> QSize:
        return QSize(MIN_CARD, self.height())

    # Painting

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        for index, (card, rect) in enumerate(zip(self._cards, self._rects)):
            self._paint_card(p, card, rect, index == self._hover)
        p.end()

    def _paint_card(self, p: QPainter, card, rect: QRectF, hovered: bool):
        rounded(p, rect, 14, fill=col("divider" if hovered else "surface"),
                border=col("border" if hovered else "surface_alt"))
        left, right = rect.left() + 16, rect.right() - 16
        y = rect.top() + 16

        pinned = card.path in self._pinned
        title_right = right
        title_left = left + (22 if pinned else 0)
        title_h = self._title_height(card, rect.width())
        draw_text(p, QRectF(title_left, y, title_right - title_left, title_h), card.title,
                  self._title_font, col("text"),
                  Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop, wrap=True)
        if pinned:
            draw_icon(p, "pin", QRectF(left, y + 4, 14, 14), col("accent"), 1.4)
        y += title_h + 12

        line_h = _line_height(12.5, 1.6)
        for task in card.tasks:
            cy = y + line_h / 2
            draw_checkbox(p, QPointF(right - 6.5, cy), 13, 4, task.done,
                          border_width=1.4, check_size=9, check_stroke=2.6)
            draw_text(p, QRectF(left, y, right - 13 - 8 - left, line_h), task.text,
                      self._body_font, col("muted" if task.done else "body"),
                      strike=task.done)
            y += line_h + 6
        for line in card.lines:
            draw_text(p, QRectF(left, y, right - left, line_h), line, self._body_font,
                      col("muted"))
            y += line_h + 6

        chip_h = QFontMetricsF(self._foot_font).height() + 2
        foot_top = rect.bottom() - 14 - chip_h - 10 - 1
        p.setPen(col("surface_alt"))
        p.drawLine(QPointF(left, foot_top), QPointF(right, foot_top))
        cy = foot_top + 1 + 10 + chip_h / 2
        chip_text = display_name(card.folder)
        chip_w = text_width(chip_text, self._foot_font) + 16
        chip = QRectF(right - chip_w, cy - chip_h / 2, chip_w, chip_h)
        rounded(p, chip, 6, fill=col("surface_alt"))
        draw_text(p, chip, chip_text, self._foot_font, col("soft"),
                  Qt.AlignmentFlag.AlignCenter, elide_text=False)
        open_w = 0.0
        if card.open_tasks:
            label = to_persian_digits(str(card.open_tasks)) + " کار باز"
            open_w = text_width(label, self._foot_font)
            draw_text(p, QRectF(left, cy - chip_h / 2, open_w, chip_h), label,
                      self._foot_font, col("accent"), elide_text=False)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(col("accent"))
            p.drawEllipse(QPointF(left + open_w + 5 + 2.5, cy), 2.5, 2.5)
            open_w += 5 + 5
        edited_left = left + open_w + 8
        draw_text(p, QRectF(edited_left, cy - chip_h / 2, chip.left() - 8 - edited_left, chip_h),
                  edited_label(card.modified, self._now), self._foot_font, col("muted"))

    # Mouse

    def _card_at(self, pos) -> int:
        for index, rect in enumerate(self._rects):
            if rect.contains(QPointF(pos)):
                return index
        return -1

    def mouseMoveEvent(self, event):
        hover = self._card_at(event.position())
        if hover != self._hover:
            self._hover = hover
            self.setCursor(Qt.CursorShape.PointingHandCursor if hover >= 0
                           else Qt.CursorShape.ArrowCursor)
            self.update()

    def leaveEvent(self, event):
        self._hover = -1
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        index = self._card_at(event.position())
        if index >= 0 and event.button() == Qt.MouseButton.LeftButton:
            self.note_activated.emit(self._cards[index].path)

    def contextMenuEvent(self, event):
        index = self._card_at(event.pos())
        if index < 0:
            return
        path = self._cards[index].path
        menu = QMenu(self)
        menu.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        pin = QAction("برداشتن سنجاق" if path in self._pinned else "سنجاق کردن", menu)
        pin.triggered.connect(lambda: self.pin_toggled.emit(path))
        delete = QAction("حذف یادداشت", menu)
        delete.triggered.connect(lambda: self.note_delete_requested.emit(path))
        menu.addAction(pin)
        menu.addAction(delete)
        menu.exec(event.globalPos())


class CardList(CardGrid):
    """The same notes as a table: note, folder, open tasks, last change."""

    COLUMNS = (110, 100, 110)  # folder, open, edited — the note takes the rest

    def _layout(self, width: float):
        self._rects = []
        header = 10 + QFontMetricsF(self._foot_font).height() + 10 + 1
        y = header
        row_h = 12 + QFontMetricsF(font(13.5, 600)).height() + 2 + QFontMetricsF(font(12)).height() + 12
        for _card in self._cards:
            self._rects.append(QRectF(0, y, width, row_h))
            y += row_h
        self.setFixedHeight(round(y) if self._cards else 0)

    def _columns_x(self, width: float) -> list[tuple[float, float]]:
        """Right-to-left spans for the four columns, inside 18px padding."""
        right = width - 18
        spans = []
        note_w = width - 36 - sum(self.COLUMNS) - 16 * 3
        for w in (note_w, *self.COLUMNS):
            spans.append((right - w, w))
            right -= w + 16
        return spans

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        whole = QRectF(self.rect())
        if not self._cards:
            p.end()
            return
        rounded(p, whole, 14, fill=col("panel"), border=col("surface_alt"))
        spans = self._columns_x(whole.width())
        head_h = 10 + QFontMetricsF(self._foot_font).height() + 10
        for (x, w), label in zip(spans, ("یادداشت", "پوشه", "کار باز", "آخرین تغییر")):
            draw_text(p, QRectF(x, 0, w, head_h), label, self._foot_font, col("muted"))
        p.setPen(col("surface_alt"))
        p.drawLine(QPointF(1, head_h), QPointF(whole.width() - 1, head_h))
        title_f, preview_f, cell_f = font(13.5, 600), font(12), font(12.5)
        for index, (card, rect) in enumerate(zip(self._cards, self._rects)):
            if index == self._hover:
                clip = rect.adjusted(1, 0, -1, 0)
                if index == len(self._cards) - 1:
                    p.save()
                    p.setClipRect(clip)
                    rounded(p, whole.adjusted(1, 1, -1, -1), 13, fill=col("surface"))
                    p.restore()
                else:
                    p.fillRect(clip, col("surface"))
            if index < len(self._cards) - 1:
                p.setPen(col("divider"))
                p.drawLine(QPointF(1, rect.bottom()), QPointF(whole.width() - 1, rect.bottom()))
            th = QFontMetricsF(title_f).height()
            (nx, nw), (fx, fw), (ox, ow), (ex, ew) = spans
            top = rect.top() + 12
            pinned = card.path in self._pinned
            title = elide(card.title, title_f, nw - (11 if pinned else 0))
            tw = text_width(title, title_f)
            draw_text(p, QRectF(nx + nw - tw, top, tw, th), title, title_f, col("text"),
                      elide_text=False)
            if pinned:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(col("accent"))
                p.drawEllipse(QPointF(nx + nw - tw - 6 - 2.5, top + th / 2), 2.5, 2.5)
            preview = " · ".join(card.lines or [t.text for t in card.tasks]) or "خالی"
            draw_text(p, QRectF(nx, top + th + 2, nw, QFontMetricsF(preview_f).height()),
                      preview, preview_f, col("muted"))
            cy = rect.center().y()
            h = QFontMetricsF(cell_f).height()
            draw_text(p, QRectF(fx, cy - h / 2, fw, h), display_name(card.folder), cell_f, col("soft"))
            count = to_persian_digits(str(card.open_tasks)) if card.open_tasks else "—"
            draw_text(p, QRectF(ox, cy - h / 2, ow, h), count, cell_f,
                      col("accent" if card.open_tasks else "muted"))
            draw_text(p, QRectF(ex, cy - h / 2, ew, h), edited_label(card.modified, self._now),
                      cell_f, col("muted"))
        p.end()


class NotesBoard(QWidget):
    note_activated = pyqtSignal(str)
    note_delete_requested = pyqtSignal(str)
    new_note_requested = pyqtSignal()
    view_changed = pyqtSignal(str)
    pin_toggled = pyqtSignal(str)

    def __init__(self, root: str, parent=None):
        super().__init__(parent)
        self.setObjectName("notesBoard")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._root = root
        self._cards: list = []
        self._category = ALL_LABEL
        self._pinned: set = set()
        self._view = "grid"
        self._open_today = 0

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(self.scroll)

        page = QWidget()
        page.setAutoFillBackground(False)
        column = QVBoxLayout(page)
        column.setContentsMargins(30, 26, 30, 30)
        column.setSpacing(22)
        self.header = HomeHeader()
        self.header.new_note_requested.connect(self.new_note_requested)
        self.header.view_changed.connect(self.set_view)
        column.addWidget(self.header)

        self.grid = CardGrid()
        self.list = CardList()
        for canvas in (self.grid, self.list):
            canvas.note_activated.connect(self.note_activated)
            canvas.note_delete_requested.connect(self.note_delete_requested)
            canvas.pin_toggled.connect(self.pin_toggled)
            column.addWidget(canvas)
        self.list.hide()
        column.addStretch(1)
        self.scroll.setWidget(page)
        self.scroll.viewport().setAutoFillBackground(False)
        page.setStyleSheet("background: transparent;")

    def paintEvent(self, _event):
        p = QPainter(self)
        p.fillRect(self.rect(), col("window"))
        p.end()

    # Data

    def set_root(self, root: str):
        self._root = root
        self.reload()

    def set_pinned(self, paths):
        self._pinned = set(paths)
        self._fill()

    def set_open_today(self, count: int):
        self._open_today = count
        self._fill_header()

    def reload(self):
        """Re-read the folder on the UI thread — 2.8 ms for the real folder."""
        self._show(load_library(self._root))

    def _show(self, cards: list):
        self._cards = cards
        if self._category not in self.category_names():
            self._category = ALL_LABEL
        self._fill()

    def show_category(self, name: str):
        self._category = name
        self._fill()

    def set_view(self, mode: str):
        self._view = "list" if mode == "list" else "grid"
        self.header.set_view(self._view)
        self._fill()
        self.view_changed.emit(self._view)

    def view(self) -> str:
        return self._view

    def shown_cards(self) -> list:
        shown = in_category(self._cards, "" if self._category == ALL_LABEL else self._category)
        # Pinned first, then most recently changed — load_library already
        # sorted by time, and sorted() is stable.
        return sorted(shown, key=lambda card: card.path not in self._pinned)

    def _fill(self):
        shown = self.shown_cards()
        self.grid.setVisible(self._view == "grid")
        self.list.setVisible(self._view == "list")
        (self.grid if self._view == "grid" else self.list).show_cards(shown, self._pinned)
        self._fill_header()

    def _fill_header(self):
        shown = self.shown_cards()
        hour = datetime.now().hour
        hello = "صبح بخیر" if hour < 12 else "روز بخیر" if hour < 17 else "عصر بخیر"
        greeting = hello + " · " + to_persian_digits(str(self._open_today)) + " کار برای امروز مانده"
        title = "همه‌ی یادداشت‌ها" if self._category == ALL_LABEL else self._category
        subtitle = to_persian_digits(str(len(shown))) + " یادداشت"
        if shown:
            newest = max(shown, key=lambda card: card.modified)
            subtitle += " · آخرین تغییر " + edited_label(newest.modified)
        self.header.set_texts(greeting, title, subtitle)

    def card_titles(self) -> list[str]:
        return [card.title for card in self.shown_cards()]

    def category_names(self) -> list[str]:
        return [ALL_LABEL] + categories(self._cards)

    def category_counts(self) -> dict[str, int]:
        return {
            name: len(in_category(self._cards, "" if name == ALL_LABEL else name))
            for name in self.category_names()
        }

    def set_sidebar_mode(self, enabled: bool = True):
        """Kept for callers: folders always live in the sidebar in v4."""

    def refresh_palette(self):
        self.update()
        for child in self.findChildren(QWidget):
            child.update()
