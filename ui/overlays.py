"""Everything the v4 design floats over the window.

Each overlay dims the whole window with the design's rgba(8,9,11,.62) and
holds one card with a 60px shadow: the command palette (Ctrl+K), settings
(Ctrl+,), quick capture (Alt+N) and the morning review. The toast and the
focus-mode pill are smaller: they sit over the page without a backdrop.
"""
from datetime import date, timedelta
from dataclasses import replace
from pathlib import Path

from PyQt6.QtCore import QEvent, QPoint, QPointF, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFontMetricsF, QPainter
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core import cloud_config, settings_manager
from core.jalali import MONTHS, from_gregorian, to_persian_digits
from core.when import day_label, parse_preview, parse_when, weekday_name
from ui.kit import (
    Button,
    Clickable,
    col,
    draw_checkbox,
    draw_icon,
    draw_text,
    elide,
    font,
    kbd,
    overlay_colour,
    rounded,
    text_width,
    tint,
    transparent_scroll,
)
from ui.cloud_sync_worker import SettingsTest, PairingWorker, DisconnectWorker, OpenLinkWorker
from ui.background import start_background
from ui.styles import PALETTES, current_palette


def _line_edit(px: float, placeholder: str) -> QLineEdit:
    edit = QLineEdit()
    edit.setFont(font(px))
    edit.setPlaceholderText(placeholder)
    edit.setFrame(False)
    edit.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    # Without an explicit right alignment an empty RTL field parks its caret
    # on the left, under the placeholder's far end.
    edit.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignAbsolute
                      | Qt.AlignmentFlag.AlignVCenter)
    t = current_palette()
    edit.setStyleSheet(
        f"QLineEdit {{ background: transparent; border: none; padding: 0; color: {t['text']};"
        f" selection-background-color: {t['accent']}; selection-color: {t['on_accent']}; }}"
    )
    return edit


class _Label(QWidget):
    """One line of painted text at a fixed height."""

    def __init__(self, text: str, px: float, weight: int = 400, colour: str = "text",
                 align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                 mono: bool = False, parent=None):
        super().__init__(parent)
        self.text, self._font, self.colour, self._align = text, font(px, weight, mono=mono), colour, align
        self.setFixedHeight(round(QFontMetricsF(self._font).height()))

    def set_text(self, text: str):
        self.text = text
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        draw_text(p, QRectF(self.rect()), self.text, self._font, col(self.colour), self._align)
        p.end()


class _Rule(QWidget):
    def __init__(self, token: str = "line", parent=None):
        super().__init__(parent)
        self._token = token
        self.setFixedHeight(1)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.fillRect(self.rect(), col(self._token))
        p.end()


class Card(QWidget):
    """A rounded panel with the design's `0 24px 60px rgba(0,0,0,.45)` shadow."""

    def __init__(self, fill: str = "surface", radius: float = 16, parent=None):
        super().__init__(parent)
        self._fill, self._radius = fill, radius
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

    def set_shadow(self, on: bool):
        """Attached only while the card is on screen: an effect on a hidden
        widget costs nothing but can outlive its owner at teardown."""
        if on and self.graphicsEffect() is None:
            shadow = QGraphicsDropShadowEffect(self)
            shadow.setBlurRadius(60)
            shadow.setOffset(0, 24)
            shadow.setColor(QColor(0, 0, 0, 115))
            self.setGraphicsEffect(shadow)
        elif not on:
            self.setGraphicsEffect(None)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rounded(p, QRectF(self.rect()), self._radius, fill=col(self._fill), border=col("border"))
        p.end()


class Overlay(QWidget):
    """A backdrop over the whole window holding one card.

    `top` places the card that many pixels from the top; None centres it.
    Clicking the backdrop or pressing Esc closes it.
    """

    closed = pyqtSignal()

    def __init__(self, window: QWidget, card: Card, width: int, *, top: int | None = None,
                 height: int | None = None, dim: float = 0.62, modal_close: bool = True):
        super().__init__(window)
        self._window, self.card = window, card
        self._width, self._height, self._top, self._dim = width, height, top, dim
        self._modal_close = modal_close
        card.setParent(self)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.hide()

    def window_resized(self):
        """Called by the main window's resizeEvent — no event filter on it,
        which Qt would still call into while the window is being destroyed."""
        if self.isVisible():
            self._place()

    def _place(self):
        self.setGeometry(self._window.rect())
        width = min(self._width, self.width() - 40)
        height = self._height or self.card.sizeHint().height()
        height = min(height, self.height() - 60)
        x = (self.width() - width) // 2
        y = self._top if self._top is not None else (self.height() - height) // 2
        self.card.setGeometry(x, y, width, height)

    def open(self):
        self._place()
        self.card.set_shadow(True)
        self.show()
        self.raise_()
        self.setFocus()
        self.focus_target().setFocus()

    def focus_target(self) -> QWidget:
        return self.card

    def close_overlay(self):
        if self.isVisible():
            self.hide()
            self.card.set_shadow(False)
            self.closed.emit()

    def paintEvent(self, _event):
        p = QPainter(self)
        colour = overlay_colour()
        colour.setAlphaF(self._dim)
        p.fillRect(self.rect(), colour)
        p.end()

    def mousePressEvent(self, event):
        if self._modal_close and not self.card.geometry().contains(event.position().toPoint()):
            self.close_overlay()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close_overlay()
            return
        super().keyPressEvent(event)


# Command palette

class PaletteList(QWidget):
    """Grouped results: notes, tasks, commands — painted, keyboard-driven."""

    chosen = pyqtSignal(int)
    hovered_index = pyqtSignal(int)

    ICONS = {"note": "file", "task": "tasks", "cmd": "command"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.groups: list[tuple[str, list[dict]]] = []
        self.flat: list[dict] = []
        self.index = 0
        self.empty_text = ""
        self._rects: list[tuple[QRectF, int]] = []

    def set_groups(self, groups, empty_text: str):
        self.groups = [g for g in groups if g[1]]
        self.flat = [item for _label, items in self.groups for item in items]
        self.index = 0
        self.empty_text = empty_text
        self._fit()
        self.update()

    def _fit(self):
        label_h = 10 + QFontMetricsF(font(11, 600)).height() + 4
        h = sum(label_h + 42 * len(items) for _label, items in self.groups)
        self.setFixedHeight(round(h if self.flat else 34 * 2 + QFontMetricsF(font(13)).height()))

    def move(self, delta: int):
        if self.flat:
            self.index = max(0, min(len(self.flat) - 1, self.index + delta))
            self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        width = self.width()
        if not self.flat:
            draw_text(p, QRectF(self.rect()), self.empty_text, font(13), col("muted"),
                      Qt.AlignmentFlag.AlignCenter)
            p.end()
            return
        y = 0.0
        self._rects = []
        n = 0
        label_font = font(11, 600)
        label_h = QFontMetricsF(label_font).height()
        for label, items in self.groups:
            draw_text(p, QRectF(10, y + 10, width - 20, label_h), label, label_font, col("muted"))
            y += 10 + label_h + 4
            for item in items:
                rect = QRectF(0, y, width, 42)
                selected = n == self.index
                if selected:
                    rounded(p, rect, 9, fill=col("line"))
                right = rect.right() - 12
                draw_icon(p, self.ICONS[item["kind"]], QRectF(right - 16, rect.center().y() - 8, 16, 16),
                          col("accent" if selected else "muted"), 1.4)
                left = rect.left() + 12
                if item.get("kbd"):
                    f = font(10.5, mono=True)
                    w = text_width(item["kbd"], f) + 12
                    kbd(p, left + w, rect.center().y(), item["kbd"], colour="muted", border="border")
                    left += w + 12
                if item.get("sub"):
                    sf = font(11.5)
                    w = min(text_width(item["sub"], sf), 160)
                    draw_text(p, QRectF(left, rect.top(), w, 42), item["sub"], sf, col("muted"),
                              Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                    left += w + 12
                draw_text(p, QRectF(left, rect.top(), right - 16 - 12 - left, 42), item["label"],
                          font(13.5), col("text"))
                self._rects.append((rect, n))
                n += 1
                y += 42
        p.end()

    def _at(self, pos):
        for rect, n in self._rects:
            if rect.contains(QPointF(pos)):
                return n
        return -1

    def mouseMoveEvent(self, event):
        n = self._at(event.position())
        if n >= 0 and n != self.index:
            self.index = n
            self.update()

    def mouseReleaseEvent(self, event):
        n = self._at(event.position())
        if n >= 0:
            self.chosen.emit(n)


class CommandPalette(Overlay):
    """Ctrl+K: notes, open tasks and commands in one list."""

    note_chosen = pyqtSignal(str)
    task_chosen = pyqtSignal(str, int)
    create_note = pyqtSignal(str)

    def __init__(self, window):
        card = Card("surface", 16)
        super().__init__(window, card, 620, top=86)
        self._notes: list[dict] = []
        self._tasks: list[dict] = []
        self._commands: list[dict] = []
        self._extra: list[dict] = []

        column = QVBoxLayout(card)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)

        head = _PaletteHead()
        head_row = QHBoxLayout(head)
        head_row.setContentsMargins(18 + 17 + 12 + 40, 0, 18 + 17 + 12, 0)
        self.input = _line_edit(15, "نام یادداشت، کار یا دستور…")
        self.input.textChanged.connect(self._refresh)
        self.input.installEventFilter(self)
        head_row.addWidget(self.input)
        column.addWidget(head)
        column.addWidget(_Rule("line"))

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        transparent_scroll(self.scroll)
        holder = QWidget()
        holder_layout = QVBoxLayout(holder)
        holder_layout.setContentsMargins(8, 8, 8, 8)
        self.list = PaletteList()
        self.list.chosen.connect(self._activate)
        holder_layout.addWidget(self.list)
        holder_layout.addStretch(1)
        self.scroll.setWidget(holder)
        column.addWidget(self.scroll, 1)
        column.addWidget(_Rule("line"))
        column.addWidget(_Hints((("↑↓", "جابه‌جایی"), ("Enter", "باز کردن"), ("Esc", "بستن"))))

    def focus_target(self):
        return self.input

    def open_with(self, notes, tasks, commands, extra=()):
        """notes: [{label, sub, path}], tasks: [{label, sub, path, line}],
        commands: [{label, kbd, run}] in the design's order; extra: more
        commands (from the menus) that only a query reaches."""
        self._notes, self._tasks, self._commands, self._extra = notes, tasks, commands, list(extra)
        self.input.clear()
        self._refresh()
        self.open()

    def _refresh(self):
        q = self.input.text().strip().casefold()
        match = (lambda text: q in text.casefold()) if q else (lambda text: True)
        notes = [dict(n, kind="note") for n in self._notes if match(n["label"])][: 6 if q else 4]
        tasks = [dict(t, kind="task") for t in self._tasks if match(t["label"])][:3]
        commands = [dict(c, kind="cmd") for c in self._commands if match(c["label"])]
        if q:
            seen = {c["label"] for c in commands}
            commands += [dict(c, kind="cmd") for c in self._extra
                         if match(c["label"]) and c["label"] not in seen]
        commands = commands[: 7 if q else 4]
        self.list.set_groups(
            [("یادداشت‌ها", notes), ("کارها", tasks), ("دستورها", commands)],
            "چیزی پیدا نشد. Enter برای ساختن یادداشت «" + self.input.text().strip() + "»",
        )
        list_h = min(430, self.list.height() + 16)
        self._height = 56 + 1 + list_h + 1 + 38
        if self.isVisible():
            self._place()

    def eventFilter(self, obj, event):
        if obj is self.input and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Down:
                self.list.move(1)
                self._ensure_visible()
                return True
            if key == Qt.Key.Key_Up:
                self.list.move(-1)
                self._ensure_visible()
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if self.list.flat:
                    self._activate(self.list.index)
                elif self.input.text().strip():
                    title = self.input.text().strip()
                    self.close_overlay()
                    self.create_note.emit(title)
                return True
            if key == Qt.Key.Key_Escape:
                self.close_overlay()
                return True
        return super().eventFilter(obj, event)

    def _ensure_visible(self):
        y = 0
        n = 0
        label_h = 10 + QFontMetricsF(font(11, 600)).height() + 4
        for _label, items in self.list.groups:
            y += label_h
            for _item in items:
                if n == self.list.index:
                    self.scroll.ensureVisible(0, int(y + 8 + 21), 0, 30)
                    return
                y += 42
                n += 1

    def _activate(self, n: int):
        item = self.list.flat[n]
        self.close_overlay()
        if item["kind"] == "note":
            self.note_chosen.emit(item["path"])
        elif item["kind"] == "task":
            self.task_chosen.emit(item["path"], item["line"])
        else:
            QTimer.singleShot(0, item["run"])


class _PaletteHead(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(56)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self.rect())
        draw_icon(p, "search", QRectF(r.right() - 18 - 17, r.center().y() - 8.5, 17, 17), col("muted"), 1.4)
        f = font(10.5, mono=True)
        kbd(p, 18 + text_width("Esc", f) + 12, r.center().y(), "Esc", colour="muted", border="border")
        p.end()


class _Hints(QWidget):
    """The 38px footer: «↑↓ جابه‌جایی   Enter باز کردن   Esc بستن»."""

    def __init__(self, hints, button: QWidget | None = None, parent=None):
        super().__init__(parent)
        self._hints = hints
        self.setFixedHeight(38)
        if button is not None:
            row = QHBoxLayout(self)
            row.setContentsMargins(16, 0, 16, 0)
            row.addStretch(1)
            row.addWidget(button)
            row.setDirection(QHBoxLayout.Direction.LeftToRight)

    def paintEvent(self, _event):
        p = QPainter(self)
        x = self.width() - 18.0
        mono, words = font(11.5, mono=True), font(11.5)
        for key, label in self._hints:
            text = " " + label
            w1, w2 = text_width(key, mono), text_width(text, words)
            # RTL: the key first on the right, then its label.
            draw_text(p, QRectF(x - w1, 0, w1, 38), key, mono, col("muted"), elide_text=False)
            draw_text(p, QRectF(x - w1 - w2, 0, w2, 38), text, words, col("muted"), elide_text=False)
            x -= w1 + w2 + 18
        p.end()


# Quick capture

class QuickCapture(Overlay):
    """Win+Alt+N / Alt+N: one line into today's tasks, or a note in the inbox."""

    task_submitted = pyqtSignal(object, str)
    note_submitted = pyqtSignal(str)

    def __init__(self, window):
        card = Card("surface", 16)
        super().__init__(window, card, 560, top=130, height=None, dim=0.5)
        self._dest = "task"
        column = QVBoxLayout(card)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)

        head = QHBoxLayout()
        head.setContentsMargins(16, 14, 16, 0)
        head.setSpacing(10)
        head.addWidget(_QcTitle())
        head.addStretch(1)
        well = _Well("window", "surface_alt", 8)
        self.task_button = Button("کار", None, height=26, radius=6, padding=(12, 12), px=12,
                                  normal={"fg": "muted"}, active={"bg": "hover", "fg": "text"})
        self.note_button = Button("یادداشت در ورودی‌ها", None, height=26, radius=6, padding=(12, 12),
                                  px=12, normal={"fg": "muted"}, active={"bg": "hover", "fg": "text"})
        for button, dest in ((self.task_button, "task"), (self.note_button, "inbox")):
            button.setCheckable(True)
            button.clicked.connect(lambda _c=False, d=dest: self.set_destination(d))
            well.add(button)
        head.addWidget(well)
        column.addLayout(head)

        field_row = QVBoxLayout()
        field_row.setContentsMargins(16, 14, 16, 12)
        self.field = _Field(46, 10, "window", "line", 14)
        self.input = _line_edit(15, "")
        self.field.set_editor(self.input)
        self.input.installEventFilter(self)
        self.input.textChanged.connect(self._refresh_hint)
        field_row.addWidget(self.field)
        column.addLayout(field_row)

        self.hint = _QcHint()
        column.addWidget(self.hint)
        column.addWidget(_Rule("line"))
        save = Button("ذخیره", None, height=26, radius=7, padding=(12, 12), px=12, weight=600,
                      normal={"bg": "accent", "fg": "on_accent"})
        save.clicked.connect(self.submit)
        column.addWidget(_Hints((("Enter", "ذخیره"), ("Tab", "کار / یادداشت"), ("Esc", "بستن")), save))
        self._height = 14 + 28 + 14 + 46 + 12 + 40 + 14 + 1 + 38
        self.set_destination("task")

    def focus_target(self):
        return self.input

    def open_fresh(self):
        self.input.clear()
        self.set_destination("task")
        self.open()

    def set_destination(self, dest: str):
        self._dest = dest
        self.task_button.setChecked(dest == "task")
        self.note_button.setChecked(dest == "inbox")
        self.task_button.update()
        self.note_button.update()
        self.input.setPlaceholderText(
            "مثلاً «تماس با حمید فردا»" if dest == "task"
            else "فکر، ایده یا هر چیزی که نباید یادت برود…")
        self._refresh_hint()

    def _refresh_hint(self):
        preview = parse_preview(self.input.text()) if self._dest == "task" else None
        if preview:
            self.hint.show_parse(*preview)
        else:
            self.hint.show_text(
                "بدون تاریخ = امروز · می‌توانی بنویسی «فردا»، «شنبه» یا «۱۲ مهر»"
                if self._dest == "task" else "یک یادداشت تازه در پوشه‌ی «ورودی‌ها» ساخته می‌شود")

    def eventFilter(self, obj, event):
        if obj is self.input and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Tab or event.key() == Qt.Key.Key_Backtab:
                self.set_destination("inbox" if self._dest == "task" else "task")
                return True
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.submit()
                return True
            if event.key() == Qt.Key.Key_Escape:
                self.close_overlay()
                return True
        return super().eventFilter(obj, event)

    def submit(self):
        raw = self.input.text().strip()
        if not raw:
            return
        self.close_overlay()
        if self._dest == "task":
            found = parse_when(raw)
            self.task_submitted.emit(found.day if found else date.today(), found.text if found else raw)
        else:
            self.note_submitted.emit(raw)


class _QcTitle(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(28)
        f, m = font(12.5, 600), font(10.5, mono=True)
        self.setFixedWidth(round(15 + 10 + text_width("ضبط سریع", f) + 10 + text_width("Win Alt N", m) + 12 + 2))

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self.rect())
        x = r.right()
        draw_icon(p, "bolt", QRectF(x - 15, r.center().y() - 7.5, 15, 15), col("accent"), 1.5)
        x -= 15 + 10
        f = font(12.5, 600)
        w = text_width("ضبط سریع", f)
        draw_text(p, QRectF(x - w, 0, w, r.height()), "ضبط سریع", f, col("text"), elide_text=False)
        x -= w + 10
        m = font(10.5, mono=True)
        kbd(p, x, r.center().y(), "Win Alt N", colour="muted", border="border")
        p.end()


class _QcHint(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(40 + 14)
        self._mode, self._a, self._b = "text", "", ""

    def show_text(self, text: str):
        self._mode, self._a = "text", text
        self.update()

    def show_parse(self, label: str, rest: str):
        self._mode, self._a, self._b = "parse", label, rest
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(16, 0, self.width() - 32, 40)
        f = font(12)
        if self._mode == "text":
            draw_text(p, r, self._a, f, col("muted"))
        else:
            w = 9 + 11 + 5 + text_width(self._a, f) + 9
            chip = QRectF(r.right() - w, r.center().y() - 12, w, 24)
            rounded(p, chip, 6, fill=tint("accent", 0.12))
            draw_icon(p, "calendar_small", QRectF(chip.right() - 9 - 11, chip.top() + 6.5, 11, 11),
                      col("accent"), 1.6)
            draw_text(p, QRectF(chip.left() + 9, chip.top(), text_width(self._a, f), 24), self._a, f,
                      col("accent"), elide_text=False)
            draw_text(p, QRectF(r.left(), chip.top(), chip.left() - 8 - r.left(), 24), self._b, f,
                      col("muted"))
        p.end()


class _Well(QWidget):
    """A padded rounded well for a segmented control."""

    def __init__(self, fill: str, border: str | None, radius: float, parent=None):
        super().__init__(parent)
        self._fill, self._border, self._radius = fill, border, radius
        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(3, 3, 3, 3)
        self._row.setSpacing(2)

    def add(self, widget):
        self._row.addWidget(widget)

    def paintEvent(self, _event):
        p = QPainter(self)
        rounded(p, QRectF(self.rect()), self._radius, fill=col(self._fill),
                border=col(self._border) if self._border else None)
        p.end()


class _Field(QWidget):
    """A bordered input well hosting a frameless QLineEdit."""

    def __init__(self, height: int, radius: float, fill: str, border: str, pad: int, parent=None):
        super().__init__(parent)
        self._radius, self._fill, self._border = radius, fill, border
        self.setFixedHeight(height)
        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(pad, 0, pad, 0)

    def set_editor(self, edit):
        self._row.addWidget(edit)

    def paintEvent(self, _event):
        p = QPainter(self)
        rounded(p, QRectF(self.rect()), self._radius, fill=col(self._fill), border=col(self._border))
        p.end()


# Settings

class Toggle(Clickable):
    """The design's 40x23 switch: accent when on, knob right; grey when off."""

    toggled = pyqtSignal(bool)

    def __init__(self, on: bool = False, parent=None):
        super().__init__(parent)
        self.on = on
        self.setFixedSize(40, 23)
        self.clicked.connect(self._flip)

    def _flip(self):
        self.on = not self.on
        self.update()
        self.toggled.emit(self.on)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self.rect())
        rounded(p, r, 11.5, fill=col("accent" if self.on else "surface_alt"),
                border=col("accent" if self.on else "border"))
        # right:2px when on, right:19px when off (RTL: on sits at the right).
        x = r.right() - 2 - 17 if self.on else r.right() - 19 - 17
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col("on_accent" if self.on else "muted"))
        p.drawEllipse(QRectF(x, 3, 17, 17))
        p.end()


class Segmented(QWidget):
    """«تیره | روشن | مثل ویندوز»: the chosen one filled with the accent."""

    changed = pyqtSignal(str)

    def __init__(self, options, current: str, parent=None):
        super().__init__(parent)
        self._options = options
        self._current = current
        well = QHBoxLayout(self)
        well.setContentsMargins(3, 3, 3, 3)
        well.setSpacing(2)
        self._buttons = {}
        for key, label in options:
            button = Button(label, None, height=28, radius=6, padding=(14, 14), px=12.5,
                            normal={"fg": "muted"}, active={"bg": "accent", "fg": "on_accent"})
            button._font = font(12.5)
            button.setCheckable(True)
            button.setChecked(key == current)
            button.clicked.connect(lambda _c=False, k=key: self.choose(k))
            well.addWidget(button)
            self._buttons[key] = button

    def choose(self, key: str):
        self._current = key
        for k, button in self._buttons.items():
            button.setChecked(k == key)
            button._font = font(12.5, 600 if k == key else 400)
            button.update()
        self.changed.emit(key)

    def paintEvent(self, _event):
        p = QPainter(self)
        rounded(p, QRectF(self.rect()), 9, fill=col("surface_alt"))
        p.end()


class Swatch(Clickable):
    def __init__(self, name: str, selected: bool, parent=None):
        super().__init__(parent)
        self.name, self.selected = name, selected
        self.setFixedSize(34, 34)
        self.setToolTip(PALETTES[name]["label"])

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        half = PALETTES[self.name]["dark"]
        rounded(p, QRectF(self.rect()), 9, fill=QColor(half["surface"]),
                border=col("text") if self.selected else None, border_width=2)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(half["accent"]))
        p.drawEllipse(QPointF(17, 17), 7, 7)
        p.end()


class SizeSlider(QWidget):
    """A 180px track with an accent fill from the right and a 14px knob."""

    changed = pyqtSignal(float)

    def __init__(self, value: float, low: float = 10, high: float = 20, parent=None):
        super().__init__(parent)
        self.value, self.low, self.high = value, low, high
        self.setFixedSize(180, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _label(self) -> str:
        text = f"{self.value:g}".replace(".", "٫")
        return to_persian_digits(text)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        track = QRectF(32 + 10, 10, self.width() - 32 - 10, 4)
        rounded(p, track, 2, fill=col("surface_alt"))
        fraction = (self.value - self.low) / (self.high - self.low)
        w = track.width() * fraction
        rounded(p, QRectF(track.right() - w, track.top(), w, 4), 2, fill=col("accent"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col("accent"))
        p.drawEllipse(QPointF(track.right() - w, track.center().y()), 7, 7)
        draw_text(p, QRectF(0, 0, 32, 24), self._label(), font(12), col("soft"),
                  Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elide_text=False)
        p.end()

    def _set_from(self, x: float):
        track_left, track_right = 42.0, float(self.width())
        fraction = (track_right - x) / (track_right - track_left)
        value = self.low + max(0.0, min(1.0, fraction)) * (self.high - self.low)
        value = round(value * 2) / 2
        if value != self.value:
            self.value = value
            self.update()
            self.changed.emit(value)

    def mousePressEvent(self, event):
        self._set_from(event.position().x())

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._set_from(event.position().x())


class _SettingRow(QWidget):
    """«label / hint» on the right, the control on the left, a rule below."""

    def __init__(self, label: str, hint: str = "", control: QWidget | None = None, *,
                 rule: bool = True, mono_hint: bool = False, parent=None):
        super().__init__(parent)
        self._rule = rule
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 16, 0, 16)
        row.setSpacing(16)
        texts = QVBoxLayout()
        texts.setSpacing(3)
        texts.addWidget(_Label(label, 13.5))
        if hint:
            texts.addWidget(_Label(hint, 12, colour="muted", mono=mono_hint))
        row.addLayout(texts, 1)
        if control is not None:
            row.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)

    def paintEvent(self, _event):
        if self._rule:
            p = QPainter(self)
            p.fillRect(QRectF(0, self.height() - 1, self.width(), 1), col("divider"))
            p.end()


class _NavItem(Clickable):
    def __init__(self, key: str, label: str, parent=None):
        super().__init__(parent)
        self.key, self.label, self.active = key, label, False
        self.setFixedHeight(36)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self.rect())
        if self.active:
            rounded(p, r, 8, fill=col("divider"))
        draw_text(p, r.adjusted(12, 0, -12, 0), self.label, font(13),
                  col("text" if (self.active or self.hovered) else "muted"))
        p.end()


def _guide_html() -> str:
    """The server guide as the settings screen shows it."""
    from html import escape

    parts = []
    for kind, text in cloud_config.GUIDE:
        if kind == "h":
            parts.append(f"<p style='font-weight:600; margin-top:14px'>{escape(text)}</p>")
        elif kind == "code":
            parts.append(
                f"<pre dir='ltr' style='background-color:{col('surface_alt').name()}; "
                f"white-space:pre-wrap; padding:8px'>{escape(text)}</pre>")
        else:
            parts.append(f"<p style='margin:4px 0'>{escape(text)}</p>")
    return "".join(parts)


class SettingsPanel(Overlay):
    """Ctrl+, — عمومی، ظاهر، همگام‌سازی، میان‌برها. Changes apply at once."""

    theme_changed = pyqtSignal(str)
    palette_changed = pyqtSignal(str)
    font_size_changed = pyqtSignal(float)
    line_numbers_changed = pyqtSignal(bool)
    startup_changed = pyqtSignal(bool)
    tray_changed = pyqtSignal(bool)
    folder_change_requested = pyqtSignal()
    sync_requested = pyqtSignal()
    # The sync settings were saved (and tested): the window syncs with them now.
    sync_settings_changed = pyqtSignal()

    SECTIONS = (("general", "عمومی"), ("look", "ظاهر"), ("sync", "همگام‌سازی"),
                ("updates", "به‌روزرسانی"), ("diagnostics", "گزارش و عیب‌یابی"), ("keys", "میان‌برها"))

    def __init__(self, window, version: str):
        card = Card("panel", 16)
        super().__init__(window, card, 780, height=540)
        self._version = version
        self._updates = getattr(window, 'updates', None)
        self._state: dict = {}
        self._section = "look"
        self._test = None
        self._pairing = None
        self._disconnect = None
        self._opener = None
        self._confirm_code = ''
        self._pair_message = ''
        self._pair_link = ""
        self._busy = False

        row = QHBoxLayout(card)
        row.setContentsMargins(1, 1, 1, 1)
        row.setSpacing(0)

        nav = _NavColumn(version)
        nav_column = QVBoxLayout(nav)
        nav_column.setContentsMargins(12, 20, 12, 20)
        nav_column.setSpacing(2)
        title = _Label("تنظیمات", 15, 700)
        title_row = QHBoxLayout()
        title_row.setContentsMargins(10, 0, 10, 14)
        title_row.addWidget(title)
        nav_column.addLayout(title_row)
        self._nav = {}
        for key, label in self.SECTIONS:
            item = _NavItem(key, label)
            item.clicked.connect(lambda k=key: self.show_section(k))
            nav_column.addWidget(item)
            self._nav[key] = item
        nav_column.addStretch(1)
        row.addWidget(nav)

        body = QWidget()
        body_column = QVBoxLayout(body)
        body_column.setContentsMargins(0, 0, 0, 0)
        body_column.setSpacing(0)
        header = QWidget()
        header.setFixedHeight(56)
        header_row = QHBoxLayout(header)
        header_row.setContentsMargins(24, 0, 24, 0)
        self._title = _Label("", 15, 600)
        header_row.addWidget(self._title, 1)
        close = Button("", "close", height=30, width=30, radius=7, padding=(0, 0), icon_size=12,
                       stroke=1.8, normal={"fg": "muted"}, hover={"bg": "surface_alt", "fg": "text"})
        close.clicked.connect(self.close_overlay)
        header_row.addWidget(close)
        body_column.addWidget(header)
        body_column.addWidget(_Rule("divider"))

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        transparent_scroll(self.scroll)
        body_column.addWidget(self.scroll, 1)
        row.addWidget(body, 1)

    def open_with(self, state: dict, section: str = "look"):
        """state: notes_root, theme, palette, font_size, line_numbers, startup,
        tray, sync (dict for the sync card), shortcuts [(label, keys)]."""
        self._state = state
        self.show_section(section)
        self.open()

    def show_section(self, key: str):
        if key not in ('sync', 'diagnostics', 'updates') and self._pairing is not None and self._pairing.isRunning():
            self._pairing.requestInterruption()
        self._section = key
        self._height = 680 if key == 'diagnostics' else 540
        if self.isVisible():
            self._place()
        for k, item in self._nav.items():
            item.active = k == key
            item.update()
        self._title.set_text(dict(self.SECTIONS)[key])
        page = QWidget()
        column = QVBoxLayout(page)
        column.setContentsMargins(24, 8, 24, 24)
        column.setSpacing(0)
        getattr(self, "_build_" + key)(column)
        column.addStretch(1)
        self.scroll.setWidget(page)

    def _build_general(self, column):
        s = self._state
        change = Button("تغییر", None, height=32, radius=8, padding=(14, 14), px=12.5,
                        normal={"bg": "surface_alt", "fg": "text", "border": "border"},
                        hover={"border": "accent"})
        change.clicked.connect(self.folder_change_requested)
        column.addWidget(_SettingRow("پوشه‌ی یادداشت‌ها", s.get("notes_root", ""), change, mono_hint=True))
        for key, label, hint, signal in (
            ("startup", "اجرا همراه ویندوز", "برنامه بعد از روشن شدن رایانه در نوار وظیفه آماده است.",
             self.startup_changed),
            ("tray", "بستن پنجره = ماندن در نوار وظیفه", "دفعه‌ی بعد برنامه آنی باز می‌شود.",
             self.tray_changed),
            ("line_numbers", "شماره‌ی خط در ویرایشگر", "با رقم فارسی، کنار هر خط.",
             self.line_numbers_changed),
        ):
            toggle = Toggle(bool(s.get(key)))
            toggle.toggled.connect(signal)
            column.addWidget(_SettingRow(label, hint, toggle))

    def _build_diagnostics(self, column):
        from ui.diagnostics_panel import DiagnosticsPanel

        self.diagnostics_panel = DiagnosticsPanel(self._version)
        column.addWidget(self.diagnostics_panel)

    def _build_updates(self, column):
        from ui.app_updates import UpdateController, UpdatesPanel

        if self._updates is None:
            self._updates = UpdateController(self._version, settings_manager.load(), self)
        column.addWidget(UpdatesPanel(self._updates))

    def _build_look(self, column):
        s = self._state
        theme = Segmented((("dark", "تیره"), ("light", "روشن"), ("system", "مثل ویندوز")),
                          s.get("theme", "system"))
        theme.changed.connect(self.theme_changed)
        column.addWidget(_SettingRow("تم", "", theme))

        swatches = QWidget()
        swatch_row = QHBoxLayout(swatches)
        swatch_row.setContentsMargins(0, 0, 0, 0)
        swatch_row.setSpacing(8)
        self._swatches = []
        for name in PALETTES:
            swatch = Swatch(name, name == s.get("palette", "graphite"))
            swatch.clicked.connect(lambda n=name: self._choose_palette(n))
            swatch_row.addWidget(swatch)
            self._swatches.append(swatch)
        column.addWidget(_SettingRow("پالت رنگ", "", swatches))

        slider = SizeSlider(float(s.get("font_size", 14)))
        slider.changed.connect(self.font_size_changed)
        column.addWidget(_SettingRow("اندازه‌ی متن ویرایشگر", "Ctrl + چرخ ماوس هم کار می‌کند", slider))
        column.addWidget(_SettingRow("فونت", "وزیرمتن برای فارسی، Inter برای لاتین",
                                     _Label("وزیرمتن", 13, colour="soft"), rule=False))

    def _choose_palette(self, name: str):
        for swatch in self._swatches:
            swatch.selected = swatch.name == name
            swatch.update()
        self.palette_changed.emit(name)

    def _build_sync(self, column):
        sync = self._state.get("sync", {})
        settings = self._state.get("sync_settings") or cloud_config.SyncSettings()
        column.addSpacing(16)
        card = _SyncCard(sync)
        card.check.clicked.connect(self.sync_requested)
        column.addWidget(card)
        column.addSpacing(16)
        column.addWidget(_Label("اتصال با تلگرام", 14, 600))
        column.addSpacing(8)
        column.addWidget(_Paragraph("نیازی به تنظیم سرور یا ساخت بات نیست. اتصال را شروع کن و کد تطبیق را در تلگرام تأیید کن."))
        root = self._state.get('notes_root', '')
        folder = QLabel(root or 'پوشهٔ یادداشت‌ها در بخش عمومی انتخاب می‌شود.')
        folder.setWordWrap(True)
        folder.setTextFormat(Qt.TextFormat.PlainText)
        folder.setFont(font(12))
        folder.setStyleSheet(f"color: {col('soft').name()};")
        column.addWidget(folder)
        column.addSpacing(8)
        self._share_folder = Toggle(False)
        column.addWidget(_SettingRow("همگام‌سازی این پوشه را می‌پذیرم",
            "نسخه‌ای از فایل‌های متنی آن روی سرور نوت‌پد ذخیره می‌شود.", self._share_folder))
        self._exclude = self._line('Private, پوشهٔ دیگر', ', '.join(settings.excluded_paths or ('Private',)))
        column.addWidget(self._labelled('پوشه‌های مستثنا از همگام‌سازی (با کاما جدا کن)', self._field(self._exclude)))
        column.addSpacing(8)

        def action_button(label, action, *, primary=False):
            button = Button(label, None, height=38, radius=9, padding=(12, 12), px=12.5,
                            weight=600 if primary else 400,
                            normal={"bg": "accent" if primary else "surface_alt",
                                    "fg": "on_accent" if primary else "text",
                                    "border": None if primary else "border"},
                            hover={"bg": "accent_hover"} if primary else {"border": "accent"})
            # Button normally fixes its width to its text. These actions share
            # the available row width, independently of their Persian labels.
            button.setMinimumWidth(0)
            button.setMaximumWidth(16777215)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.clicked.connect(action)
            return button

        connect_row = QHBoxLayout()
        connect_row.setContentsMargins(0, 0, 0, 0)
        connect_row.setSpacing(8)
        self._connect = action_button('اتصال به تلگرام', self._begin_pairing, primary=True)
        self._connect.setEnabled(not self._busy)
        connect_row.addWidget(self._connect, 1)
        connect_row.addWidget(action_button('بازکردن تلگرام', self._open_pair_link), 1)
        connect_row.addWidget(action_button('لغو درخواست', self._cancel_pairing), 1)
        column.addLayout(connect_row)
        self._copy_pair_link = action_button('کپی لینک اتصال', self._copy_link)
        self._copy_pair_link.setEnabled(bool(self._pair_link))
        column.addWidget(self._copy_pair_link)
        column.addSpacing(8)
        self._pair_status = QLabel(self._pair_message or ('اتصال این رایانه ذخیره شده است.' if settings.device_id else ''))
        self._pair_status.setTextFormat(Qt.TextFormat.PlainText)
        self._pair_status.setWordWrap(True)
        self._pair_status.setFont(font(12))
        self._pair_status.setStyleSheet(f"color: {col('accent').name()};")
        self._pair_status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignAbsolute | Qt.AlignmentFlag.AlignVCenter)
        column.addWidget(self._pair_status)
        if settings.device_id:
            column.addSpacing(8)
            column.addWidget(action_button('قطع اتصال این رایانه', self._disconnect_pairing))

        # The personal-server form remains available for existing installations.
        advanced = QWidget()
        advanced_column = QVBoxLayout(advanced)
        advanced_column.setContentsMargins(0, 0, 0, 0)
        column.addSpacing(16)
        column.addWidget(_Rule('divider'))
        column.addSpacing(8)
        column.addWidget(action_button('تنظیمات پیشرفته / سرور شخصی', lambda: advanced.setHidden(not advanced.isHidden())))
        column.addWidget(advanced)
        advanced.setHidden(True)
        column = advanced_column

        column.addSpacing(20)
        column.addWidget(_Label("اتصال به سرور", 13.5, 600))
        column.addSpacing(8)
        self._url = self._line("https://نام-شما.workers.dev", settings.url)
        column.addWidget(self._labelled("آدرس سرور", self._field(self._url)))
        column.addSpacing(10)
        self._key = self._line("کلید همگام‌سازی", settings.key, secret=True)
        column.addWidget(self._labelled("کلید همگام‌سازی", self._field(
            self._key,
            self._button("نمایش", lambda: self._reveal(self._key)),
            self._button("ساخت کلید", self._make_key))))
        self._enabled = Toggle(settings.enabled)
        column.addWidget(_SettingRow("همگام‌سازی روشن",
                                     "خاموش باشد، برنامه به سرور وصل نمی‌شود.", self._enabled))

        column.addSpacing(18)
        column.addWidget(_Label("تلگرام (اختیاری)", 13.5, 600))
        column.addSpacing(8)
        self._token = self._line("123456:ABC…", settings.bot_token, secret=True)
        column.addWidget(self._labelled("توکن بات تلگرام", self._field(
            self._token, self._button("نمایش", lambda: self._reveal(self._token)))))
        column.addWidget(_Paragraph(
            "این توکن فقط برای «تست بات» همین‌جا به کار می‌رود. بات روی سرور کار می‌کند،"
            " پس توکن را آن‌جا هم بگذار (راهنمای پایین)."))

        column.addSpacing(16)
        save_row = QHBoxLayout()
        save_row.setContentsMargins(0, 0, 0, 0)
        self._save = Button("ذخیره و تست", None, height=36, radius=9, padding=(18, 18), px=13,
                            weight=600, normal={"bg": "accent", "fg": "on_accent"},
                            hover={"bg": "accent_hover"})
        self._save.clicked.connect(self._save_sync)
        save_row.addWidget(self._save)
        save_row.addStretch(1)
        column.addLayout(save_row)
        self._result = QLabel("")
        self._result.setWordWrap(True)
        column.addWidget(self._result)

        column.addSpacing(18)
        guide = QLabel(_guide_html())
        guide.setTextFormat(Qt.TextFormat.RichText)
        guide.setWordWrap(True)
        guide.setFont(font(12.5))
        guide.setStyleSheet(f"color: {col('text').name()};")
        guide.setHidden(True)
        guide_button = self._button("راهنمای ساخت سرور", lambda: guide.setHidden(not guide.isHidden()))
        column.addWidget(guide_button, 0, Qt.AlignmentFlag.AlignLeft)
        column.addWidget(guide)

    def _line(self, placeholder: str, text: str, secret: bool = False) -> QLineEdit:
        edit = QLineEdit(text)
        edit.setPlaceholderText(placeholder)
        edit.setFrame(False)
        edit.setFont(font(13))
        edit.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        edit.setStyleSheet(f"QLineEdit {{ background: transparent; border: none; color: {col('text').name()}; }}")
        if secret:
            edit.setEchoMode(QLineEdit.EchoMode.Password)
        return edit

    def _field(self, edit: QLineEdit, *buttons) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        well = _Field(38, 10, "surface_alt", "border", 12)
        well.set_editor(edit)
        layout.addWidget(well, 1)
        for button in buttons:
            layout.addWidget(button)
        return row

    def _labelled(self, text: str, widget: QWidget) -> QWidget:
        box = QWidget()
        column = QVBoxLayout(box)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(6)
        column.addWidget(_Label(text, 12.5, colour="muted"))
        column.addWidget(widget)
        return box

    def _button(self, label: str, action) -> Button:
        button = Button(label, None, height=32, radius=8, padding=(14, 14), px=12.5,
                        normal={"bg": "surface_alt", "fg": "text", "border": "border"},
                        hover={"border": "accent"})
        button.clicked.connect(action)
        return button

    def _reveal(self, edit: QLineEdit):
        hidden = edit.echoMode() == QLineEdit.EchoMode.Password
        edit.setEchoMode(QLineEdit.EchoMode.Normal if hidden else QLineEdit.EchoMode.Password)

    def _make_key(self):
        if (self._state.get('sync_settings') or cloud_config.SyncSettings()).device_id:
            self._say('برای اتصال مدیریت‌شده، کلید خودکار ساخته می‌شود. از دکمهٔ اتصال به تلگرام استفاده کن.', ok=False)
            return
        key = cloud_config.new_secret()
        self._key.setEchoMode(QLineEdit.EchoMode.Normal)
        self._key.setText(key)
        QApplication.clipboard().setText(key)
        self._say("کلید ساخته شد و کپی شد. همان را روی سرور بگذار (راهنمای پایین) و «ذخیره و تست» را بزن."
                  " اگر قبلاً کلید دیگری روی سرور گذاشته‌ای، باید آن‌جا هم عوض شود.", ok=True)

    def _save_sync(self):
        if self._busy:
            return
        previous = self._state.get("sync_settings") or cloud_config.SyncSettings()
        settings = cloud_config.SyncSettings(
            enabled=self._enabled.on, url=self._url.text().strip(),
            key=self._key.text().strip(), bot_token=self._token.text().strip(),
            proxy=previous.proxy, user_id=previous.user_id, device_id=previous.device_id,
            confirmed_root=previous.confirmed_root, excluded_paths=previous.excluded_paths)
        if previous.device_id and (settings.url != previous.url or settings.key != previous.key):
            self._say('آدرس و کلید این اتصال خودکار مدیریت می‌شوند. از اتصال به تلگرام استفاده کن.', ok=False)
            return
        problem = (cloud_config.address_problem(settings.url) or cloud_config.key_problem(settings.key)
                   or cloud_config.token_problem(settings.bot_token))
        if problem:
            self._say(problem, ok=False)
            return
        try:
            cloud_config.save(settings)
        except OSError:
            self._say("تنظیمات ذخیره نشد. دوباره امتحان کن.", ok=False)
            return
        self._state["sync_settings"] = settings
        self._busy = True
        self._say("ذخیره شد. در حال تست…", ok=True)
        self._test = SettingsTest(settings, self)
        self._test.done.connect(self._test_done)
        self._test.start()

    def _test_done(self, ok: bool, message: str):
        self._busy = False
        if self._section == 'sync':
            self._say(message, ok=ok)
        self.sync_settings_changed.emit()

    def _say(self, text: str, ok: bool):
        self._result.setText(text)
        self._result.setWordWrap(True)
        self._result.setStyleSheet(f"color: {col('accent' if ok else 'danger').name()}; font-size: 12.5px;")

    def wait_for_test(self):
        """Before the app quits: a test thread must not outlive the window."""
        if self._test is not None and self._test.isRunning():
            self._test.wait(20_000)
        if self._pairing is not None and self._pairing.isRunning():
            self._pairing.requestInterruption()
            self._pairing.wait(20_000)
        if self._disconnect is not None and self._disconnect.isRunning():
            self._disconnect.wait(20_000)

    def _begin_pairing(self):
        if self._busy:
            return
        root = self._state.get('notes_root', '')
        if not root or not self._share_folder.on:
            self._pair_status.setText('ابتدا پوشهٔ یادداشت‌ها و پذیرش همگام‌سازی آن را مشخص کن.')
            return
        previous = self._state.get('sync_settings') or cloud_config.SyncSettings()
        excluded = tuple(p.strip().replace('\\', '/').strip('/') for p in self._exclude.text().replace('،', ',').split(',') if p.strip())
        if any(p.startswith('.') or ':' in p or '..' in p.split('/') or not p for p in excluded):
            self._pair_status.setText('نام پوشه‌های مستثنا باید مسیر نسبی و معتبر باشد.')
            return
        self._busy = True
        self._confirm_code = ''
        self._connect.setEnabled(False)
        self._pair_status.setText('در حال آماده‌کردن اتصال…')
        self._pairing = PairingWorker(previous, root, excluded, self)
        self._pairing.ready.connect(self._pairing_ready)
        self._pairing.progress.connect(self._pairing_progress)
        self._pairing.done.connect(self._pairing_done)
        self._pairing.start()

    def _pairing_ready(self, info):
        self._pair_link = info['telegram_url']
        self._confirm_code = info['confirm_code']
        self._pair_message = 'کد تطبیق: ' + self._confirm_code + '\nهمین کد را در بات بررسی و اتصال را تأیید کن.'
        if self._section == 'sync':
            self._copy_pair_link.setEnabled(True)
            self._pair_status.setText(self._pair_message)
            QTimer.singleShot(0, self._reveal_pair_status)
        if self._section in ('sync', 'diagnostics', 'updates'):
            self._open_pair_link()

    def _reveal_pair_status(self):
        if self._section == 'sync' and self.isVisible():
            self.scroll.ensureWidgetVisible(self._pair_status, 0, 20)

    def _pairing_progress(self, message):
        self._pair_message = 'کد تطبیق: ' + self._confirm_code + '\n' + message
        if self._section == 'sync':
            self._pair_status.setText(self._pair_message)

    def _open_pair_link(self):
        if self._pair_link and (self._opener is None or not self._opener.isRunning()):
            self._opener = OpenLinkWorker(self._pair_link)
            self._opener.done.connect(self._link_opened)
            self._opener.finished.connect(self._link_finished)
            start_background(self._opener)

    def _copy_link(self):
        if self._pair_link:
            QApplication.clipboard().setText(self._pair_link)

    def _link_finished(self):
        self._opener = None

    def _link_opened(self, link, opened):
        if not opened and link == self._pair_link:
            self._pairing_progress('مرورگر باز نشد. با دکمهٔ «کپی لینک اتصال» لینک را در مرورگر باز کن.')

    def _cancel_pairing(self):
        if self._pairing is not None:
            self._pairing.requestInterruption()

    def _pairing_done(self, settings, error):
        self._busy = False
        self._pair_link = ''
        if settings is not None:
            try:
                cloud_config.save(settings)
                self._state['sync_settings'] = settings
                self._state['sync'] = {**self._state.get('sync', {}), 'enabled': True,
                                       'title': 'اتصال ذخیره شد؛ در انتظار بررسی همگام‌سازی'}
                self.sync_settings_changed.emit()
            except OSError:
                error = 'اتصال تأیید شد ولی تنظیمات ذخیره نشد؛ دوباره تلاش کن.'
        self._pair_message = error or 'اتصال برقرار شد. همگام‌سازی پوشهٔ تأییدشده آغاز می‌شود.'
        if self._section == 'sync':
            self.show_section('sync')
            self._pair_status.setText(self._pair_message)
            QTimer.singleShot(0, self._reveal_pair_status)

    def _disconnect_pairing(self):
        if self._busy:
            return
        settings = self._state.get('sync_settings') or cloud_config.SyncSettings()
        if not settings.device_id:
            return
        paused = replace(settings, enabled=False)
        try:
            cloud_config.save(paused)
        except OSError:
            self._pair_status.setText('تنظیمات ذخیره نشد. دوباره تلاش کن.')
            return
        self._state['sync_settings'] = paused
        self.sync_settings_changed.emit()
        self._busy = True
        self._pair_status.setText('همگام‌سازی خاموش شد؛ در حال قطع دسترسی سرور…')
        self._disconnect = DisconnectWorker(settings, self)
        self._disconnect.done.connect(self._disconnected)
        self._disconnect.start()

    def _disconnected(self, ok):
        self._busy = False
        if self._section == 'sync':
            self._pair_status.setText('اتصال قطع شد. فایل‌های محلی باقی می‌مانند.' if ok else
                'همگام‌سازی خاموش است؛ سرور در دسترس نبود. برای لغو دسترسی از /devices در بات استفاده کن.')

    def _build_keys(self, column):
        for label, keys in self._state.get("shortcuts", []):
            column.addWidget(_ShortcutRow(label, keys))


class _NavColumn(QWidget):
    def __init__(self, version: str, parent=None):
        super().__init__(parent)
        self._version = version
        self.setFixedWidth(210)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # Only the right-hand corners are rounded; the card clips the rest.
        p.save()
        from PyQt6.QtGui import QPainterPath

        path = QPainterPath()
        r = QRectF(self.rect())
        path.addRoundedRect(r.adjusted(0, 0, 16, 0), 15, 15)
        p.setClipRect(r)
        p.fillPath(path, col("chrome"))
        p.restore()
        p.fillRect(QRectF(0, 0, 1, self.height()), col("divider"))
        draw_text(p, QRectF(12, self.height() - 20 - 18, self.width() - 24, 18),
                  "Notepad Plus " + self._version, font(11), col("faint"))
        p.end()


class _Paragraph(QWidget):
    def __init__(self, text: str, px: float = 12, colour: str = "muted", parent=None):
        super().__init__(parent)
        self._text, self._px, self._colour = text, px, colour
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(round(px * 1.9 * 2 + 4))

    def paintEvent(self, _event):
        p = QPainter(self)
        draw_text(p, QRectF(self.rect()), self._text, font(self._px), col(self._colour),
                  Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop, wrap=True)
        p.end()


class _SyncCard(QWidget):
    def __init__(self, sync: dict, parent=None):
        super().__init__(parent)
        self._sync = sync
        column = QVBoxLayout(self)
        column.setContentsMargins(16, 16, 16, 16)
        column.setSpacing(12)
        top = QHBoxLayout()
        top.setSpacing(10)
        top.addWidget(_Dot("accent" if sync.get("enabled") else "box"))
        top.addWidget(_Label(sync.get("title", "متصل به Mini App تلگرام"), 14, 600), 1)
        self.check = Button("بررسی الان", None, height=32, radius=8, padding=(14, 14), px=12.5,
                            weight=600, normal={"bg": "accent", "fg": "on_accent"},
                            hover={"bg": "accent_hover"})
        top.addWidget(self.check)
        column.addLayout(top)
        grid = QHBoxLayout()
        grid.setSpacing(10)
        for key, value in (("آخرین بررسی", sync.get("last", "—")), ("فایل‌ها", sync.get("files", "—")),
                           ("تعارض", sync.get("conflicts", "ندارد"))):
            cell = QVBoxLayout()
            cell.setSpacing(2)
            cell.addWidget(_Label(key, 11.5, colour="muted"))
            cell.addWidget(_Label(value, 13))
            grid.addLayout(cell, 1)
        column.addLayout(grid)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rounded(p, QRectF(self.rect()), 12, fill=col("surface"), border=col("surface_alt"))
        p.end()


class _Dot(QWidget):
    def __init__(self, token: str, size: int = 8, parent=None):
        super().__init__(parent)
        self._token = token
        self.setFixedSize(size, size)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col(self._token))
        p.drawEllipse(QRectF(self.rect()))
        p.end()


class _ShortcutRow(QWidget):
    def __init__(self, label: str, keys: str, parent=None):
        super().__init__(parent)
        self._label, self._keys = label, keys
        self.setFixedHeight(round(11 + QFontMetricsF(font(13)).height() + 11))

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self.rect())
        f = font(11, mono=True)
        w = text_width(self._keys, f) + 16
        pill = QRectF(0, r.center().y() - 11, w, 22)
        rounded(p, pill, 6, fill=col("surface"), border=col("border"))
        draw_text(p, pill, self._keys, f, col("soft"), Qt.AlignmentFlag.AlignCenter, elide_text=False)
        draw_text(p, QRectF(w + 12, 0, r.width() - w - 12, r.height()), self._label, font(13), col("text"))
        p.fillRect(QRectF(0, r.height() - 1, r.width(), 1), col("divider"))
        p.end()


# Morning review

class MorningReview(Overlay):
    """Once a day: what was left over, one decision each, then «شروع روز»."""

    reschedule = pyqtSignal(str, int, object)
    mark_done = pyqtSignal(str, int)
    delete = pyqtSignal(str, int)
    finished = pyqtSignal()

    def __init__(self, window, name: str = ""):
        card = Card("panel", 18)
        super().__init__(window, card, 560, modal_close=False)
        self._name = name
        self._tasks: list = []
        self._open_today = 0
        self.closed.connect(self.finished)
        column = QVBoxLayout(card)
        column.setContentsMargins(1, 1, 1, 1)
        column.setSpacing(0)

        head = QVBoxLayout()
        head.setContentsMargins(24, 24, 24, 16)
        head.setSpacing(4)
        head.addWidget(_Label("مرور روز", 12.5, 600, "accent"))
        self._hello = _Label("", 21, 700)
        head.addWidget(self._hello)
        self._sub = _Label("", 12.5, colour="muted")
        head.addWidget(self._sub)
        column.addLayout(head)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        transparent_scroll(self.scroll)
        column.addWidget(self.scroll, 1)

        foot = _FootRule()
        foot_row = QHBoxLayout(foot)
        foot_row.setContentsMargins(16, 14, 16, 14)
        foot_row.setSpacing(8)
        self.all_today = Button("همه برای امروز", None, height=36, radius=9, padding=(14, 14),
                                px=12.5, normal={"fg": "muted"}, hover={"fg": "text", "bg": "divider"})
        self.all_today.clicked.connect(self._all_to_today)
        foot_row.addWidget(self.all_today)
        foot_row.addStretch(1)
        start = Button("شروع کار", None, height=36, radius=9, padding=(20, 20), px=13, weight=600,
                       normal={"bg": "accent", "fg": "on_accent"}, hover={"bg": "accent_hover"})
        start.clicked.connect(self.close_overlay)
        foot_row.addWidget(start)
        column.addWidget(foot)

    def open(self):
        from core.greeting import greeting

        self._hello.set_text(greeting() + ("، " + self._name if self._name else ""))
        super().open()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close_overlay()

    def set_tasks(self, overdue: list, open_today: int):
        """The overdue tasks (open, dated before today) and today's open count."""
        self._tasks, self._open_today = overdue, open_today
        today = date.today()
        y, m, d = from_gregorian(today)
        stamp = weekday_name(today) + "، " + to_persian_digits(f"{d}") + " " + MONTHS[m - 1] + " " + to_persian_digits(str(y))
        self._sub.set_text(stamp + " · " + (to_persian_digits(str(len(overdue))) + " کار از روزهای قبل مانده"
                                            if overdue else "چیزی از روزهای قبل نمانده"))
        self.all_today.setVisible(bool(overdue))
        page = QWidget()
        rows = QVBoxLayout(page)
        if overdue:
            rows.setContentsMargins(16, 0, 16, 8)
            rows.setSpacing(8)
            for task in overdue:
                rows.addWidget(self._row(task))
        else:
            rows.setContentsMargins(24, 26, 24, 20)
            rows.addWidget(_AllClear(open_today))
        rows.addStretch(1)
        self.scroll.setWidget(page)
        if overdue:
            content = 8 + sum(r.sizeHint().height() for r in page.findChildren(_ReviewRow)) \
                + 8 * (len(overdue) - 1)
        else:
            content = 26 + 20 + _AllClear(0).height()
        head = 24 + 16 + sum(QFontMetricsF(font(px, w)).height() for px, w in
                             ((12.5, 600), (21, 700), (12.5, 400))) + 8
        self._height = round(2 + head + content + 1 + 14 + 36 + 14)
        if self.isVisible():
            self._place()

    def _row(self, task) -> QWidget:
        row = _ReviewRow(task)
        row.today.clicked.connect(lambda: self.reschedule.emit(task.path, task.line_number, date.today()))
        row.tomorrow.clicked.connect(
            lambda: self.reschedule.emit(task.path, task.line_number, date.today() + timedelta(days=1)))
        row.done.clicked.connect(lambda: self.mark_done.emit(task.path, task.line_number))
        row.remove.clicked.connect(lambda: self.delete.emit(task.path, task.line_number))
        return row

    def _all_to_today(self):
        for task in list(self._tasks):
            self.reschedule.emit(task.path, task.line_number, date.today())


class _FootRule(QWidget):
    def paintEvent(self, _event):
        p = QPainter(self)
        p.fillRect(QRectF(0, 0, self.width(), 1), col("surface_alt"))
        p.end()


class _ReviewRow(QWidget):
    def __init__(self, task, parent=None):
        super().__init__(parent)
        from ui.today_rail import task_source

        self._task = task
        self._src = task_source(task)
        column = QVBoxLayout(self)
        column.setContentsMargins(14, 14, 14, 14)
        column.setSpacing(10)
        self._head = QWidget()
        self._head.setFixedHeight(round(14 * 1.7 + 2 + QFontMetricsF(font(11.5)).height()))
        self._head.paintEvent = self._paint_head
        column.addWidget(self._head)
        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        outline = dict(height=32, radius=8, px=12.5,
                       normal={"fg": "text", "border": "border"}, hover={"fg": "accent", "border": "accent"})
        self.today = Button("امروز انجامش می‌دهم", None, padding=(0, 0), **dict(outline, normal={
            "bg": "surface_alt", "fg": "text", "border": "border"}))
        self.today.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.today.setMaximumWidth(10000)
        self.tomorrow = Button("فردا", None, padding=(14, 14), **outline)
        self.done = Button("انجام شده", None, padding=(14, 14), **outline)
        self.remove = Button("", "trash", height=32, width=34, radius=8, padding=(0, 0),
                             icon_size=14, stroke=1.4, normal={"fg": "danger", "border": "border"})
        self.remove.setToolTip("حذف")
        for button in (self.today, self.tomorrow, self.done, self.remove):
            buttons.addWidget(button)
        column.addLayout(buttons)

    def _paint_head(self, _event):
        p = QPainter(self._head)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self._head.rect())
        when = day_label(self._task.due.date())
        f = font(11.5)
        w = text_width(when, f) + 18
        h = QFontMetricsF(f).height() + 4
        pill = QRectF(0, 0, w, h)
        rounded(p, pill, 6, fill=tint("danger", 0.12))
        draw_text(p, pill, when, f, col("danger"), Qt.AlignmentFlag.AlignCenter, elide_text=False)
        text_h = 14 * 1.7
        draw_text(p, QRectF(w + 10, 0, r.width() - w - 10, text_h), self._task.text, font(14), col("text"))
        draw_text(p, QRectF(w + 10, text_h + 2, r.width() - w - 10, r.height() - text_h - 2),
                  self._src, f, col("muted"))
        p.end()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rounded(p, QRectF(self.rect()), 12, fill=col("surface"), border=col("surface_alt"))
        p.end()


class _AllClear(QWidget):
    def __init__(self, open_today: int, parent=None):
        super().__init__(parent)
        self._open = open_today
        self.setFixedHeight(44 + 10 + 24 + 10 + 20)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        cx = self.width() / 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(tint("accent", 0.12))
        p.drawEllipse(QPointF(cx, 22), 22, 22)
        draw_icon(p, "check", QRectF(cx - 10, 12, 20, 20), col("accent"), 1.8)
        draw_text(p, QRectF(0, 54, self.width(), 24), "همه‌چیز مرتب است", font(15, 600), col("text"),
                  Qt.AlignmentFlag.AlignCenter)
        draw_text(p, QRectF(0, 88, self.width(), 20),
                  "امروز " + to_persian_digits(str(self._open)) + " کار باز داری.", font(12.5),
                  col("muted"), Qt.AlignmentFlag.AlignCenter)
        p.end()


# Toast and focus pill

class Toast(QWidget):
    """«● همگام‌سازی انجام شد» — bottom centre, gone after 2.2 seconds."""

    def __init__(self, window: QWidget):
        super().__init__(window)
        self._window = window
        self._text = ""
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._vanish)
        self.hide()

    def _vanish(self):
        self.hide()
        self.setGraphicsEffect(None)

    def flash(self, text: str):
        self._text = text
        f = font(12.5)
        width = round(14 + 7 + 10 + text_width(text, f) + 14)
        height = round(10 + QFontMetricsF(f).height() + 10)
        margin = 40
        self.setGeometry((self._window.width() - width - margin) // 2,
                         self._window.height() - 24 - height - margin // 2,
                         width + margin, height + margin)
        if self.graphicsEffect() is None:
            shadow = QGraphicsDropShadowEffect(self)
            shadow.setBlurRadius(30)
            shadow.setOffset(0, 12)
            shadow.setColor(QColor(0, 0, 0, 90))
            self.setGraphicsEffect(shadow)
        self.show()
        self.raise_()
        self.update()
        self._timer.start(2200)

    def text(self) -> str:
        return self._text

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(20, 10, -20, -30)
        rounded(p, r, 11, fill=col("surface"), border=col("border"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col("accent"))
        p.drawEllipse(QPointF(r.right() - 14 - 3.5, r.center().y()), 3.5, 3.5)
        draw_text(p, QRectF(r.left() + 14, r.top(), r.width() - 14 - 7 - 10 - 14, r.height()),
                  self._text, font(12.5), col("text"), elide_text=False)
        p.end()


class FocusPill(QWidget):
    """«حالت تمرکز  [خروج · Esc]» — top centre, three quarters visible."""

    exit_requested = pyqtSignal()

    def __init__(self, window: QWidget):
        super().__init__(window)
        self._window = window
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        row = QHBoxLayout(self)
        f = font(12)
        row.setContentsMargins(6, 0, 14, 0)
        row.setSpacing(10)
        row.addWidget(_Label("حالت تمرکز", 12, colour="muted"))
        button = Button("خروج · Esc", None, height=24, radius=12, padding=(10, 10), px=11.5,
                        normal={"bg": "surface_alt", "fg": "text"})
        button.clicked.connect(self.exit_requested)
        row.addWidget(button)
        self._width = round(14 + text_width("حالت تمرکز", f) + 10 + button.width() + 6)
        self.hide()

    def show_pill(self):
        self.setGeometry((self._window.width() - self._width) // 2, 16, self._width, 34)
        opacity = QGraphicsOpacityEffect(self)
        opacity.setOpacity(0.75)
        self.setGraphicsEffect(opacity)
        self.show()
        self.raise_()

    def hide_pill(self):
        self.hide()
        self.setGraphicsEffect(None)

    def _set_opacity(self, value: float):
        effect = self.graphicsEffect()
        if effect is not None:
            effect.setOpacity(value)

    def enterEvent(self, event):
        self._set_opacity(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._set_opacity(0.75)
        super().leaveEvent(event)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rounded(p, QRectF(self.rect()), 17, fill=col("surface"), border=col("line"))
        p.end()
