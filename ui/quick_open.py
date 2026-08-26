"""Ctrl+P — type a few letters and press Enter.

The fastest path to anything: no sidebar, no mouse. Three groups share the
one box — notes, whatever is still open on the task list, and the commands
you would otherwise hunt for in a menu. Matching over notes runs on the path
relative to the notes folder, so a folder name finds a note too.
"""
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

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


class QuickOpenDialog(QDialog):
    note_chosen = pyqtSignal(str)
    task_chosen = pyqtSignal(str, int)

    def __init__(self, root: str, parent=None, commands=None, tasks=None):
        super().__init__(parent)
        self.setWindowTitle("Go to File")
        self.setModal(True)
        self.setMinimumWidth(560)
        self._candidates = collect_candidates(root)
        # (label, hint, callable)
        self._commands = list(commands or [])
        self._tasks = list(tasks or [])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.input = QLineEdit()
        self.input.setPlaceholderText("Type part of a file name, task or command…")
        self.input.textChanged.connect(self._refresh)
        # Arrow keys belong to the list even while the box has focus, so the
        # whole interaction is one uninterrupted piece of typing.
        self.input.installEventFilter(self)
        layout.addWidget(self.input)

        self.results = QListWidget()
        self.results.setObjectName("quickOpenList")
        self.results.itemActivated.connect(self._choose)
        self.results.itemClicked.connect(self._choose)
        layout.addWidget(self.results)

        self.hint = QLabel()
        self.hint.setObjectName("statusLabel")
        layout.addWidget(self.hint)

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
        item = QListWidgetItem(label)
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        item.setData(Qt.ItemDataRole.UserRole, None)
        item.setData(Qt.ItemDataRole.UserRole + 1, _HEADER)
        self.results.addItem(item)

    def _add_row(self, label: str, payload, hint: str = "", rtl_probe: str = ""):
        item = QListWidgetItem(f"{label}    {hint}" if hint else label)
        item.setData(Qt.ItemDataRole.UserRole, payload)
        item.setToolTip(label)
        item.setTextAlignment(
            (
                Qt.AlignmentFlag.AlignRight
                if detect_direction(rtl_probe or label, default="ltr") == "rtl"
                else Qt.AlignmentFlag.AlignLeft
            )
            | Qt.AlignmentFlag.AlignVCenter
        )
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
                )

        tasks = [t for t in self._tasks if match_label(query, t.text)][:MAX_TASKS]
        if tasks:
            self._add_header("Open tasks")
            for task in tasks:
                self._add_row(
                    "☐  " + task.text,
                    ("task", task.path, task.line_number),
                    rtl_probe=task.text,
                )

        commands = [
            (label, hint, run)
            for label, hint, run in self._commands
            if match_label(query, label)
        ][:MAX_COMMANDS]
        if commands:
            self._add_header("Commands")
            for index, (label, hint, _run) in enumerate(commands):
                self._add_row(label, ("command", index), hint=hint)
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
