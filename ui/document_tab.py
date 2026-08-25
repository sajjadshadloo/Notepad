from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QVBoxLayout,
    QWidget,
)

from core.recovery_manager import new_recovery_id
from core.settings_manager import font_chain
from ui.editor import SmartEditor
from ui.markdown_highlighter import MarkdownHighlighter


def editor_font(latin: str, persian: str, size: int) -> QFont:
    """Editor font covering both scripts — see settings_manager.font_chain."""
    font = QFont()
    font.setFamilies(
        font_chain({"font_family_latin": latin, "font_family_persian": persian})
    )
    font.setPointSize(size)
    return font


class DocumentTab(QWidget):
    state_changed = pyqtSignal()
    cursor_changed = pyqtSignal()

    def __init__(
        self,
        *,
        text: str = "",
        path: str | None = None,
        encoding: str = "utf-8",
        font_family: str = "Inter",
        font_family_persian: str = "Vazirmatn",
        font_size: int = 14,
        recovery_id: str | None = None,
        # Documents are right-to-left unless told otherwise; MainWindow passes
        # the configured preference, and this is the fallback for direct use.
        direction_mode: str = "rtl",
        title: str | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.path = str(Path(path).resolve()) if path else None
        self.encoding = encoding
        self.recovery_id = recovery_id or new_recovery_id()
        self.untitled_title = title or "Untitled"
        self._counts: tuple[int, int] | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.editor = SmartEditor()
        self.editor.setFont(editor_font(font_family, font_family_persian, font_size))
        self.editor.set_direction_mode(direction_mode)
        self.highlighter = MarkdownHighlighter(self.editor)
        self.editor.markdown_highlighter = self.highlighter
        layout.addWidget(self.editor)

        self.editor.setPlainText(text)
        self.editor.document().setModified(False)
        self.editor.textChanged.connect(self._invalidate_counts)
        self.editor.textChanged.connect(self.state_changed)
        self.editor.cursorPositionChanged.connect(self.cursor_changed)
        self.editor.setFocus()

    @property
    def modified(self) -> bool:
        return self.editor.document().isModified()

    @property
    def display_name(self) -> str:
        return Path(self.path).name if self.path else self.untitled_title

    @property
    def text(self) -> str:
        return self.editor.toPlainText()

    def apply_font(self, font: QFont):
        self.editor.setFont(font)

    def _invalidate_counts(self):
        self._counts = None

    def counts(self) -> tuple[int, int]:
        """(words, characters) — recomputed only when the text changed."""
        if self._counts is None:
            text = self.text
            self._counts = (len(text.split()), len(text))
        return self._counts

    def mark_clean(self):
        self.editor.document().setModified(False)
        self.state_changed.emit()

    def set_encoding(self, encoding: str):
        if self.encoding != encoding:
            self.encoding = encoding
            self.editor.document().setModified(True)
            self.state_changed.emit()

    def set_untitled_title(self, title: str):
        cleaned = title.strip()
        if not self.path and cleaned and cleaned != self.untitled_title:
            self.untitled_title = cleaned
            self.editor.document().setModified(True)
            self.state_changed.emit()
