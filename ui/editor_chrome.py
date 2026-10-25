"""The editor page's chrome, as the v4 design draws it.

Top to bottom: a 44px strip of document tabs, a 42px format bar, the text,
and a 32px status line; on the left a 300px panel of the note's links —
what it links to, and which notes link to it.
"""
import math

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QFontMetricsF, QPainter
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QScrollArea,
    QSizePolicy,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from core.jalali import to_persian_digits
from ui.kit import (
    Button,
    Clickable,
    col,
    draw_icon,
    draw_text,
    elide,
    font,
    rounded,
    text_width,
    tint,
    transparent_scroll,
)

TAB_STRIP_HEIGHT = 44
FORMAT_BAR_HEIGHT = 42
STATUS_HEIGHT = 32
LINKS_WIDTH = 300


def tab_title(text: str) -> str:
    """A note's tab shows its name; «.md» is noise there."""
    for ext in (".md", ".markdown"):
        if text.lower().endswith(ext):
            return text[: -len(ext)]
    return text


class DocumentTabBar(QTabBar):
    """Tabs drawn as the design's 32px pills: a status dot, the name, a ×.

    QTabBar still does the bookkeeping — order, dragging, the current tab;
    only the drawing and the close hit-test are ours.
    """

    new_requested = pyqtSignal()

    PAD_RIGHT, PAD_LEFT, DOT, GAP, CLOSE = 8, 6, 6, 8, 20
    MAX_WIDTH = 220

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDrawBase(False)
        self.setMouseTracking(True)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setElideMode(Qt.TextElideMode.ElideRight)
        self._hover_tab = -1
        self._hover_close = -1
        self._modified = lambda index: False
        self.new_button = Button(
            "", "plus", height=30, width=30, radius=7, padding=(0, 0), icon_size=14,
            stroke=1.6, normal={"fg": "muted"}, hover={"bg": "surface_alt", "fg": "accent"},
        )
        self.new_button.setToolTip("یادداشت جدید")
        self.new_button.clicked.connect(self.new_requested)

    def set_modified_source(self, source):
        self._modified = source

    def _font(self):
        return font(12.5)

    def tabSizeHint(self, index: int) -> QSize:
        text = tab_title(self.tabText(index))
        width = (self.PAD_RIGHT + self.DOT + self.GAP + text_width(text, self._font())
                 + self.GAP + self.CLOSE + self.PAD_LEFT)
        # Rounded up with a pixel spare: a fraction short and the name elides.
        return QSize(math.ceil(min(self.MAX_WIDTH, width)) + 1 + 4, TAB_STRIP_HEIGHT)

    def minimumTabSizeHint(self, index: int) -> QSize:
        return QSize(90, TAB_STRIP_HEIGHT)

    def _pill(self, index: int) -> QRectF:
        return QRectF(self.tabRect(index)).adjusted(2, 6, -2, -6)

    def _close_rect(self, index: int) -> QRectF:
        pill = self._pill(index)
        return QRectF(pill.left() + self.PAD_LEFT, pill.center().y() - 10, 20, 20)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        current = self.currentIndex()
        for index in range(self.count()):
            pill = self._pill(index)
            active = index == current
            hovered = index == self._hover_tab
            if active:
                rounded(p, pill, 8, fill=col("window"), border=col("line"))
            modified = self._modified(index)
            dot = "accent" if modified else ("box" if active else "border")
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(col(dot))
            p.drawEllipse(QPointF(pill.right() - self.PAD_RIGHT - 3, pill.center().y()), 3, 3)
            close = self._close_rect(index)
            if self._hover_close == index:
                rounded(p, close, 5, fill=col("hover"))
            draw_icon(p, "close", QRectF(close.center().x() - 5, close.center().y() - 5, 10, 10),
                      col("text" if self._hover_close == index else "muted"), 1.8)
            text_right = pill.right() - self.PAD_RIGHT - self.DOT - self.GAP
            text_left = close.right() + self.GAP
            draw_text(p, QRectF(text_left, pill.top(), text_right - text_left, pill.height()),
                      tab_title(self.tabText(index)), self._font(),
                      col("text" if (active or hovered) else "muted"))
        p.end()

    def mouseMoveEvent(self, event):
        pos = event.position()
        tab = self.tabAt(pos.toPoint())
        close = tab if tab >= 0 and self._close_rect(tab).contains(pos) else -1
        if (tab, close) != (self._hover_tab, self._hover_close):
            self._hover_tab, self._hover_close = tab, close
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._hover_tab = self._hover_close = -1
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        tab = self.tabAt(event.position().toPoint())
        if (event.button() == Qt.MouseButton.LeftButton and tab >= 0
                and self._close_rect(tab).contains(event.position())):
            self.tabCloseRequested.emit(tab)
            event.accept()
            return
        if event.button() == Qt.MouseButton.MiddleButton and tab >= 0:
            self.tabCloseRequested.emit(tab)
            event.accept()
            return
        super().mousePressEvent(event)

    def refresh_close_icons(self):
        self.update()


class TabStrip(QWidget):
    """The 44px band the tab bar and its + sit on."""

    def paintEvent(self, _event):
        p = QPainter(self)
        p.fillRect(self.rect(), col("panel"))
        p.fillRect(QRectF(0, self.height() - 1, self.width(), 1), col("divider"))
        p.end()


class _Separator(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(13, 18)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.fillRect(QRectF(6, 0, 1, 18), col("line"))
        p.end()


class FormatBar(QWidget):
    """B · عنوان ۱ · عنوان ۲ | list · task · date · link | direction ··· خواندن · تمرکز · پیوندها"""

    bold = pyqtSignal()
    heading = pyqtSignal(int)
    bullets = pyqtSignal()
    task = pyqtSignal()
    date = pyqtSignal()
    link = pyqtSignal()
    direction = pyqtSignal()
    focus = pyqtSignal()
    links_toggled = pyqtSignal(bool)
    reading_toggled = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(FORMAT_BAR_HEIGHT)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 0, 14, 0)
        row.setSpacing(2)
        idle, over = {"fg": "muted"}, {"bg": "divider", "fg": "text"}

        def text_button(label, px, weight, tip):
            b = Button(label, None, height=30, radius=7, padding=(8, 8), px=px, weight=weight,
                       normal=idle, hover=over)
            b.setMinimumWidth(32)
            b.setToolTip(tip)
            return b

        def icon_button(glyph, tip):
            b = Button("", glyph, height=30, width=32, radius=7, padding=(0, 0), icon_size=16,
                       stroke=1.4, normal=idle, hover=over)
            b.setToolTip(tip)
            return b

        bold = text_button("B", 13, 700, "پررنگ — Ctrl+B")
        bold.clicked.connect(self.bold)
        h1 = text_button("عنوان ۱", 12, 600, "عنوان ۱ — Ctrl+1")
        h1.clicked.connect(lambda: self.heading.emit(1))
        h2 = text_button("عنوان ۲", 12, 600, "عنوان ۲ — Ctrl+2")
        h2.clicked.connect(lambda: self.heading.emit(2))
        for widget in (bold, h1, h2):
            row.addWidget(widget)
        row.addWidget(_Separator())
        for glyph, tip, signal in (("bullets", "فهرست", self.bullets),
                                   ("tasks", "تبدیل خط به کار — Ctrl+Shift+9", self.task),
                                   ("calendar", "تاریخ کار — Ctrl+Shift+A", self.date),
                                   ("link", "پیوند به یادداشت — [[", self.link)):
            button = icon_button(glyph, tip)
            button.clicked.connect(signal)
            row.addWidget(button)
        row.addWidget(_Separator())
        self.direction_button = Button("راست‌چین", "align", height=30, radius=7, padding=(9, 9),
                                       gap=6, px=12, icon_size=15, stroke=1.4, normal=idle, hover=over)
        self.direction_button.setToolTip("جهت متن")
        self.direction_button.clicked.connect(self.direction)
        row.addWidget(self.direction_button)
        # Everything so far edits the text; the reading view has none to edit.
        self._editing_buttons = [
            row.itemAt(i).widget() for i in range(row.count())
            if isinstance(row.itemAt(i).widget(), Button)
        ]
        row.addStretch(1)
        self.reading_button = Button("خواندن", "read", height=30, radius=7, padding=(10, 10),
                                     gap=6, px=12, icon_size=15, stroke=1.4,
                                     normal={"fg": "muted"}, hover={"fg": "text"},
                                     active={"bg": "divider", "fg": "accent"})
        self.reading_button.setCheckable(True)
        self.reading_button.setToolTip("حالت خواندن — Ctrl+E")
        self.reading_button.clicked.connect(
            lambda: self.reading_toggled.emit(self.reading_button.isChecked()))
        row.addWidget(self.reading_button)
        focus = Button("تمرکز", "focus", height=30, radius=7, padding=(10, 10), gap=6, px=12,
                       icon_size=15, stroke=1.4, normal=idle, hover=over)
        focus.setToolTip("حالت تمرکز — F11")
        focus.clicked.connect(self.focus)
        row.addWidget(focus)
        self.links_button = Button("پیوندها", "link", height=30, radius=7, padding=(10, 10), gap=6,
                                   px=12, icon_size=15, stroke=1.4, normal={"fg": "muted"},
                                   hover={"fg": "text"}, active={"bg": "divider", "fg": "accent"})
        self.links_button.setCheckable(True)
        self.links_button.setToolTip("پنل پیوندها")
        self.links_button.clicked.connect(lambda: self.links_toggled.emit(self.links_button.isChecked()))
        row.addWidget(self.links_button)

    def set_direction_label(self, rtl: bool):
        self.direction_button.set_label("راست‌چین" if rtl else "چپ‌چین")

    def set_reading(self, on: bool):
        self.reading_button.setChecked(on)
        self.reading_button.update()
        for button in self._editing_buttons:
            button.setEnabled(not on)

    def set_links_visible(self, on: bool):
        self.links_button.setChecked(on)
        self.links_button.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.fillRect(self.rect(), col("window"))
        p.fillRect(QRectF(0, self.height() - 1, self.width(), 1), col("divider"))
        p.end()


class _StatusItem(Clickable):
    def __init__(self, text: str = "", *, ltr: bool = False, clickable: bool = False, parent=None):
        super().__init__(parent)
        self._text = text
        self._clickable = clickable
        self.icon = None
        self.setFixedHeight(STATUS_HEIGHT)
        if not clickable:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        self._fit()

    def set_text(self, text: str, icon: str | None = None):
        self._text, self.icon = text, icon
        self._fit()
        self.update()

    def text(self) -> str:
        return self._text

    def _fit(self):
        extra = 12 + 6 if self.icon else 0
        self.setFixedWidth(round(text_width(self._text, font(11.5)) + extra + 1))

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self.rect())
        colour = col("text" if (self._clickable and self.hovered) else "muted")
        right = r.right()
        if self.icon:
            draw_icon(p, self.icon, QRectF(right - 12, r.center().y() - 6, 12, 12), col("accent"), 2)
            right -= 12 + 6
        draw_text(p, QRectF(0, 0, right, r.height()), self._text, font(11.5), colour, elide_text=False)
        p.end()


class EditorStatus(QWidget):
    """«✓ ذخیره شد   خط ۷، ستون ۱۲   ۱۴ خط · ۴ کار ······ راست‌چین   Markdown · UTF-8»"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(STATUS_HEIGHT)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 0, 16, 0)
        row.setSpacing(18)
        self.saved = _StatusItem("ذخیره شد")
        self.position = _StatusItem("خط ۱، ستون ۱")
        self.counts = _StatusItem("")
        self.direction = _StatusItem("راست‌چین", clickable=True)
        self.format = _StatusItem("Markdown · UTF-8", ltr=True, clickable=True)
        self.zoom = _StatusItem("", clickable=True)
        for widget in (self.saved, self.position, self.counts):
            row.addWidget(widget)
        row.addStretch(1)
        for widget in (self.zoom, self.direction, self.format):
            row.addWidget(widget)
        self.zoom.hide()

    def set_saved(self, saved: bool):
        self.saved.set_text("ذخیره شد" if saved else "ذخیره نشده", "check" if saved else None)

    def set_position(self, line: int, column: int):
        self.position.set_text("خط " + to_persian_digits(str(line)) + "، ستون "
                               + to_persian_digits(str(column)))

    def set_counts(self, lines: int, tasks: int):
        self.counts.set_text(to_persian_digits(str(lines)) + " خط · "
                             + to_persian_digits(str(tasks)) + " کار")

    def set_zoom(self, percent: int):
        self.zoom.setVisible(percent != 100)
        self.zoom.set_text(to_persian_digits(str(percent)) + "٪")

    def paintEvent(self, _event):
        p = QPainter(self)
        p.fillRect(self.rect(), col("panel"))
        p.fillRect(QRectF(0, 0, self.width(), 1), col("divider"))
        p.end()


# The links panel

class _Stat(QWidget):
    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self.label, self.value = label, "۰"
        self.setFixedHeight(round(10 + QFontMetricsF(font(17, 600)).height() + 2
                                  + QFontMetricsF(font(11)).height() + 10))

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self.rect())
        rounded(p, r, 10, fill=col("surface"), border=col("surface_alt"))
        vh = QFontMetricsF(font(17, 600)).height()
        draw_text(p, QRectF(10, 10, r.width() - 20, vh), self.value, font(17, 600), col("text"))
        draw_text(p, QRectF(10, 10 + vh + 2, r.width() - 20, r.height() - vh - 22), self.label,
                  font(11), col("muted"))
        p.end()


class _LinkCard(Clickable):
    """An outgoing link: file icon, title, folder — or «ساختن» when missing."""

    def __init__(self, title: str, sub: str, broken: bool, parent=None):
        super().__init__(parent)
        self.title, self.sub, self.broken = title, sub, broken
        self.setFixedHeight(round(9 + QFontMetricsF(font(13)).height()
                                  + QFontMetricsF(font(11)).height() + 9))

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self.rect())
        border = tint("danger", 0.35) if self.broken else col("surface_alt")
        rounded(p, r, 9, fill=col("divider" if self.hovered else "surface"), border=border)
        draw_icon(p, "file", QRectF(r.right() - 10 - 15, r.center().y() - 7.5, 15, 15),
                  col("danger" if self.broken else "accent"), 1.4)
        left = 10.0
        if self.broken:
            f = font(11.5)
            w = text_width("ساختن", f) + 18
            chip = QRectF(10, r.center().y() - 12, w, 24)
            rounded(p, chip, 6, fill=col("surface_alt"))
            draw_text(p, chip, "ساختن", f, col("text"), Qt.AlignmentFlag.AlignCenter, elide_text=False)
            left += w + 10
        text_right = r.right() - 10 - 15 - 10
        th = QFontMetricsF(font(13)).height()
        draw_text(p, QRectF(left, 9, text_right - left, th), self.title, font(13), col("text"))
        draw_text(p, QRectF(left, 9 + th, text_right - left, r.height() - 18 - th), self.sub,
                  font(11), col("danger" if self.broken else "muted"))
        p.end()


class _BacklinkCard(Clickable):
    def __init__(self, backlink, width: int = LINKS_WIDTH - 32, parent=None):
        super().__init__(parent)
        self.link = backlink
        self._lines = self._layout(width - 24)
        self.setFixedHeight(round(11 + QFontMetricsF(font(13, 600)).height() + 6
                                  + len(self._lines) * 12 * 1.8 + 11))

    def _layout(self, width: float) -> list[list[tuple[str, str]]]:
        """Word-wrap «before [link] after» into lines of (text, colour) runs."""
        f = font(12)
        words = [(w, "muted") for w in self.link.before.split()]
        words += [(w, "accent") for w in self.link.link.split()]
        words += [(w, "muted") for w in self.link.after.split()]
        lines, current, used = [], [], 0.0
        space = text_width(" ", f)
        for word, colour in words:
            w = text_width(word, f)
            if current and used + space + w > width:
                lines.append(current)
                current, used = [], 0.0
            current.append((word, colour))
            used += (space if used else 0) + w
        if current:
            lines.append(current)
        return lines or [[("", "muted")]]

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self.rect())
        rounded(p, r, 10, fill=col("divider" if self.hovered else "surface"),
                border=col("border" if self.hovered else "surface_alt"))
        th = QFontMetricsF(font(13, 600)).height()
        draw_text(p, QRectF(12, 11, r.width() - 24, th), self.link.title, font(13, 600), col("text"))
        f = font(12)
        space = text_width(" ", f)
        y = 11 + th + 6
        for line in self._lines:
            x = r.width() - 12
            for word, colour in line:
                w = text_width(word, f)
                draw_text(p, QRectF(x - w, y, w, 12 * 1.8), word, f, col(colour), elide_text=False)
                x -= w + space
            y += 12 * 1.8
        p.end()


class _Tip(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(round(12 + 12 * 1.9 * 2 + 12))

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self.rect())
        rounded(p, r, 10, border=col("border"), dashed=True)
        f, mono = font(12), font(12, mono=True)
        line_h = 12 * 1.9
        x, y = r.right() - 12, 12.0
        first = "برای پیوند به یادداشت دیگر"
        w = text_width(first, f)
        draw_text(p, QRectF(x - w, y, w, line_h), first, f, col("muted"), elide_text=False)
        x -= w + 6
        kw = text_width("[[", mono) + 12
        pill = QRectF(x - kw, y + (line_h - 18) / 2, kw, 18)
        rounded(p, pill, 5, fill=col("surface_alt"))
        draw_text(p, pill, "[[", mono, col("text"), Qt.AlignmentFlag.AlignCenter, elide_text=False)
        x -= kw + 6
        rest = "را تایپ کن؛ نام"
        w = text_width(rest, f)
        draw_text(p, QRectF(x - w, y, w, line_h), rest, f, col("muted"), elide_text=False)
        draw_text(p, QRectF(12, y + line_h, r.width() - 24, line_h), "یادداشت‌ها پیشنهاد می‌شود.",
                  f, col("muted"))
        p.end()


class LinksPanel(QWidget):
    """«در این یادداشت», its links, and the notes that link to it."""

    open_requested = pyqtSignal(str)    # a path
    create_requested = pyqtSignal(str)  # a missing note's name

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(LINKS_WIDTH)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        transparent_scroll(self.scroll)
        outer.addWidget(self.scroll)
        self.show_links(0, [], [])

    def paintEvent(self, _event):
        p = QPainter(self)
        p.fillRect(self.rect(), col("panel"))
        p.fillRect(QRectF(self.width() - 1, 0, 1, self.height()), col("divider"))
        p.end()

    def _caption(self, text: str) -> QWidget:
        from ui.overlays import _Label

        return _Label(text, 11.5, 600, "muted")

    def show_links(self, open_tasks: int, outgoing: list[dict], incoming: list):
        """outgoing: [{title, sub, broken, path}], incoming: [Backlink]."""
        page = QWidget()
        column = QVBoxLayout(page)
        column.setContentsMargins(16, 20, 16, 20)
        column.setSpacing(22)

        stats = QVBoxLayout()
        stats.setSpacing(10)
        stats.addWidget(self._caption("در این یادداشت"))
        grid = QHBoxLayout()
        grid.setSpacing(8)
        self.stats = []
        for label, value in (("کار باز", open_tasks), ("پیوند", len(outgoing)), ("ارجاع", len(incoming))):
            stat = _Stat(label)
            stat.value = to_persian_digits(str(value))
            grid.addWidget(stat, 1)
            self.stats.append(stat)
        stats.addLayout(grid)
        column.addLayout(stats)

        out = QVBoxLayout()
        out.setSpacing(6)
        out.addWidget(self._caption("پیوندهای این یادداشت"))
        out.addSpacing(4)
        for link in outgoing:
            card = _LinkCard(link["title"], link["sub"], link["broken"])
            if link["broken"]:
                card.clicked.connect(lambda t=link["title"]: self.create_requested.emit(t))
            else:
                card.clicked.connect(lambda path=link["path"]: self.open_requested.emit(path))
            out.addWidget(card)
        if not outgoing:
            from ui.overlays import _Label

            out.addWidget(_Label("هنوز پیوندی نیست.", 12, colour="muted"))
        column.addLayout(out)

        back = QVBoxLayout()
        back.setSpacing(8)
        back.addWidget(self._caption("یادداشت‌هایی که به این اشاره کرده‌اند"))
        back.addSpacing(2)
        for link in incoming:
            card = _BacklinkCard(link)
            card.clicked.connect(lambda path=link.path: self.open_requested.emit(path))
            back.addWidget(card)
        if not incoming:
            from ui.overlays import _Label

            back.addWidget(_Label("یادداشت دیگری به این‌جا پیوند نداده.", 12, colour="muted"))
        column.addLayout(back)
        column.addStretch(1)
        column.addWidget(_Tip())
        self.scroll.setWidget(page)
