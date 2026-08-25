"""Ctrl+P — type a few letters of a note's name and press Enter.

The fastest path to a file: no sidebar, no mouse. Matching runs over the
path relative to the notes folder, so a folder name finds a note too.
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


class QuickOpenDialog(QDialog):
    note_chosen = pyqtSignal(str)

    def __init__(self, root: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Go to File")
        self.setModal(True)
        self.setMinimumWidth(560)
        self._candidates = collect_candidates(root)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.input = QLineEdit()
        self.input.setPlaceholderText("Type part of a file name…")
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

    def eventFilter(self, source, event):
        if source is self.input and event.type() == event.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                row = self.results.currentRow()
                step = 1 if event.key() == Qt.Key.Key_Down else -1
                self.results.setCurrentRow(
                    max(0, min(self.results.count() - 1, row + step))
                )
                return True
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                item = self.results.currentItem()
                if item is not None:
                    self._choose(item)
                return True
        return super().eventFilter(source, event)

    def _refresh(self, query: str = ""):
        self.results.clear()
        matches = rank(query, self._candidates)
        for candidate in matches:
            item = QListWidgetItem(candidate.relative)
            item.setData(Qt.ItemDataRole.UserRole, candidate.path)
            item.setToolTip(candidate.path)
            # Persian names read right-to-left, same as in the sidebar.
            item.setTextAlignment(
                (
                    Qt.AlignmentFlag.AlignRight
                    if detect_direction(candidate.name, default="ltr") == "rtl"
                    else Qt.AlignmentFlag.AlignLeft
                )
                | Qt.AlignmentFlag.AlignVCenter
            )
            self.results.addItem(item)
        if self.results.count():
            self.results.setCurrentRow(0)
        total = len(self._candidates)
        shown = self.results.count()
        self.hint.setText(
            f"{shown} of {total} notes" if query else f"{total} notes"
        )

    def _choose(self, item: QListWidgetItem):
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            self.note_chosen.emit(path)
            self.accept()
