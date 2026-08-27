"""Ctrl+P — type a few letters and press Enter.

The fastest path to anything: no sidebar, no mouse. Three groups share the
one box — notes, whatever is still open on the task list, and the commands
you would otherwise hunt for in a menu. Matching over notes runs on the path
relative to the notes folder, so a folder name finds a note too.
"""
from pathlib import Path

from PyQt6.QtCore import QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PyQt6.QtWidgets import (
    QWidget,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QStyle,
    QStyledItemDelegate,
    QVBoxLayout,
)

from ui.styles import current_palette

from core.quick_open import Candidate, rank
from core.rtl_detector import detect_direction

NOTE_EXTENSIONS = (".txt", ".md", ".markdown")
# Enough to keep the list responsive on a big notes tree without paging.
MAX_SCANNED = 5000
# The other two groups are a shortcut, not the point of the box; they stay
# short so notes are never pushed off the first screen.
MAX_TASKS = 4
MAX_COMMANDS = 6

_HEADER = "header"


def collect_candidates(root: str) -> list[Candidate]:
    """Every note under ``root``, described by its path relative to it."""
    root_path = Path(root)
    if not root_path.exists():
        return []
    candidates: list[Candidate] = []
    for path in root_path.rglob("*"):
        if len(candidates) >= MAX_SCANNED:
            break
        if not path.is_file() or path.suffix.lower() not in NOTE_EXTENSIONS:
            continue
        candidates.append(
            Candidate(
                path=str(path.resolve()),
                relative=path.relative_to(root_path).as_posix(),
                name=path.stem,
            )
        )
    return candidates


def match_label(query: str, label: str) -> bool:
    """Plain substring match, case-folded — what a person expects here."""
    return not query or query.casefold() in label.casefold()



ROLE_KIND = Qt.ItemDataRole.UserRole + 1
ROLE_FIELDS = Qt.ItemDataRole.UserRole + 2

CHIP = 22
CHIP_RADIUS = 6
ROW_PAD_X = 10
ROW_PAD_Y = 9
ROW_RADIUS = 9
GAP = 12


class _PaletteDelegate(QStyledItemDelegate):
    """The design's row: a square icon chip, the label, then the hint."""

    def sizeHint(self, option, index) -> QSize:
        self.initStyleOption(option, index)
        metrics = QFontMetrics(option.font)
        if index.data(ROLE_KIND) == _HEADER:
            return QSize(option.rect.width(), metrics.height() + 12)
        return QSize(option.rect.width(), max(metrics.height(), CHIP) + 2 * ROW_PAD_Y)

    def paint(self, painter: QPainter, option, index):
        self.initStyleOption(option, index)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        palette = current_palette()
        rect = option.rect
        fields = index.data(ROLE_FIELDS) or {}

        if index.data(ROLE_KIND) == _HEADER:
            font = QFont(option.font)
            font.setPointSizeF(max(6.5, option.font.pointSizeF() * 0.8))
            font.setBold(True)
            font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 112)
            painter.setFont(font)
            painter.setPen(QColor(palette["muted"]))
            painter.drawText(
                rect.adjusted(ROW_PAD_X, 4, -ROW_PAD_X, 0),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop),
                fields.get("label", "").upper(),
            )
            painter.restore()
            return

        if option.state & (QStyle.StateFlag.State_Selected | QStyle.StateFlag.State_MouseOver):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(palette["hover"]))
            painter.drawRoundedRect(
                rect.adjusted(2, 1, -2, -1), ROW_RADIUS, ROW_RADIUS
            )

        rtl = fields.get("rtl", False)
        inner = rect.adjusted(ROW_PAD_X, 0, -ROW_PAD_X, 0)
        centre = inner.top() + inner.height() // 2

        chip = QRect(inner.left(), centre - CHIP // 2, CHIP, CHIP)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(palette["surface_alt"]))
        painter.drawRoundedRect(chip, CHIP_RADIUS, CHIP_RADIUS)
        chip_font = QFont(option.font)
        chip_font.setPointSizeF(max(6.5, option.font.pointSizeF() * 0.8))
        painter.setFont(chip_font)
        painter.setPen(QColor(palette["muted"]))
        painter.drawText(
            chip, int(Qt.AlignmentFlag.AlignCenter), fields.get("icon", "")
        )

        hint = fields.get("hint", "")
        hint_font = QFont(option.font)
        hint_font.setPointSizeF(max(6.5, option.font.pointSizeF() * 0.82))
        hint_width = QFontMetrics(hint_font).horizontalAdvance(hint) if hint else 0
        if hint:
            painter.setFont(hint_font)
            painter.setPen(QColor(palette["muted"]))
            painter.drawText(
                QRect(inner.right() - hint_width, inner.top(), hint_width, inner.height()),
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                hint,
            )

        left = chip.right() + GAP
        width = max(30, inner.right() - hint_width - GAP - left)
        painter.setFont(option.font)
        painter.setPen(QColor(palette["text"]))
        painter.drawText(
            QRect(left, inner.top(), width, inner.height()),
            int(
                (Qt.AlignmentFlag.AlignRight if rtl else Qt.AlignmentFlag.AlignLeft)
                | Qt.AlignmentFlag.AlignVCenter
            ),
            QFontMetrics(option.font).elidedText(
                fields.get("label", ""), Qt.TextElideMode.ElideRight, width
            ),
        )
        painter.restore()


_HEADER = "header"
_ROW = "row"


class QuickOpenDialog(QDialog):
    note_chosen = pyqtSignal(str)
    task_chosen = pyqtSignal(str, int)

    def __init__(self, root: str, parent=None, commands=None, tasks=None):
        super().__init__(parent)
        self.setWindowTitle("Go to File")
        self.setModal(True)
        self.setMinimumWidth(620)
        self.setMinimumHeight(420)
        self._candidates = collect_candidates(root)
        # (label, hint, callable)
        self._commands = list(commands or [])
        self._tasks = list(tasks or [])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header.setObjectName("paletteHeader")
        header_row = QHBoxLayout(header)
        header_row.setContentsMargins(16, 14, 16, 14)
        header_row.setSpacing(10)
        self.scope = QLabel(">")
        self.scope.setObjectName("paletteScope")
        self.input = QLineEdit()
        self.input.setObjectName("paletteInput")
        self.input.setPlaceholderText("Search notes, tasks, commands…")
        self.input.setFrame(False)
        self.input.textChanged.connect(self._refresh)
        # Arrow keys belong to the list even while the box has focus, so the
        # whole interaction is one uninterrupted piece of typing.
        self.input.installEventFilter(self)
        self.escape_hint = QLabel("Esc")
        self.escape_hint.setObjectName("topSearchHint")
        self.escape_hint.setFixedHeight(18)
        header_row.addWidget(self.scope)
        header_row.addWidget(self.input, 1)
        header_row.addWidget(self.escape_hint, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(header)

        rule = QFrame()
        rule.setObjectName("detailRule")
        rule.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(rule)

        self.results = QListWidget()
        self.results.setObjectName("quickOpenList")
        self.results.setMouseTracking(True)
        self.results.setItemDelegate(_PaletteDelegate(self.results))
        self.results.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.results.itemActivated.connect(self._choose)
        self.results.itemClicked.connect(self._choose)
        layout.addWidget(self.results, 1)

        footer_rule = QFrame()
        footer_rule.setObjectName("detailRule")
        footer_rule.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(footer_rule)

        footer = QWidget()
        footer.setObjectName("paletteFooter")
        footer_row = QHBoxLayout(footer)
        footer_row.setContentsMargins(16, 8, 16, 8)
        footer_row.setSpacing(16)
        for text in ("↑↓ move", "↵ open"):
            label = QLabel(text)
            label.setObjectName("paletteFootnote")
            footer_row.addWidget(label)
        footer_row.addStretch(1)
        self.hint = QLabel()
        self.hint.setObjectName("paletteFootnote")
        footer_row.addWidget(self.hint)
        layout.addWidget(footer)

        self._refresh("")
        self.input.setFocus()

    # Navigation

    def _step(self, start: int, step: int) -> int:
        """The next selectable row — group headings are skipped over."""
        row = start + step
        while 0 <= row < self.results.count():
            item = self.results.item(row)
            if item.data(Qt.ItemDataRole.UserRole) is not None:
                return row
            row += step
        return start

    def eventFilter(self, source, event):
        if source is self.input and event.type() == event.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                step = 1 if event.key() == Qt.Key.Key_Down else -1
                self.results.setCurrentRow(
                    self._step(self.results.currentRow(), step)
                )
                return True
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                item = self.results.currentItem()
                if item is not None:
                    self._choose(item)
                return True
        return super().eventFilter(source, event)

    # Contents

    def _add_header(self, label: str):
        item = QListWidgetItem()
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        item.setData(Qt.ItemDataRole.UserRole, None)
        item.setData(ROLE_KIND, _HEADER)
        item.setData(ROLE_FIELDS, {"label": label})
        self.results.addItem(item)

    def _add_row(
        self,
        label: str,
        payload,
        hint: str = "",
        rtl_probe: str = "",
        icon: str = "",
    ):
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, payload)
        item.setData(ROLE_KIND, _ROW)
        item.setData(
            ROLE_FIELDS,
            {
                "label": label,
                "hint": hint,
                "icon": icon,
                "rtl": detect_direction(rtl_probe or label, default="ltr") == "rtl",
            },
        )
        item.setToolTip(label)
        self.results.addItem(item)

    def _refresh(self, query: str = ""):
        self.results.clear()
        query = query.strip()

        notes = rank(query, self._candidates)
        if notes:
            self._add_header("Notes")
            for candidate in notes:
                self._add_row(
                    candidate.relative,
                    ("note", candidate.path),
                    rtl_probe=candidate.name,
                    icon="✎",
                )

        tasks = [t for t in self._tasks if match_label(query, t.text)][:MAX_TASKS]
        if tasks:
            self._add_header("Open tasks")
            for task in tasks:
                self._add_row(
                    task.text,
                    ("task", task.path, task.line_number),
                    rtl_probe=task.text,
                    icon="☐",
                )

        commands = [
            (label, hint, run)
            for label, hint, run in self._commands
            if match_label(query, label)
        ][:MAX_COMMANDS]
        if commands:
            self._add_header("Commands")
            for index, (label, hint, _run) in enumerate(commands):
                self._add_row(label, ("command", index), hint=hint, icon="›")
        self._visible_commands = commands

        first = self._step(-1, 1)
        if self.results.count() and self.results.item(first).data(
            Qt.ItemDataRole.UserRole
        ) is not None:
            self.results.setCurrentRow(first)

        total = len(self._candidates)
        shown = len(notes)
        self.hint.setText(
            f"{shown} of {total} notes" if query else f"{total} notes"
        )
        self.scope.setText(">" if query else "⌘")

    def _choose(self, item: QListWidgetItem):
        payload = item.data(Qt.ItemDataRole.UserRole)
        if not payload:
            return
        kind = payload[0]
        if kind == "note":
            self.note_chosen.emit(payload[1])
            self.accept()
        elif kind == "task":
            self.task_chosen.emit(payload[1], payload[2])
            self.accept()
        elif kind == "command":
            run = self._visible_commands[payload[1]][2]
            self.accept()
            run()
