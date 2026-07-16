from pathlib import Path

from PyQt6.QtCore import QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from core.recovery_manager import new_recovery_id
from ui.editor import SmartEditor
from ui.markdown_highlighter import MarkdownHighlighter


def editor_font(family: str, size: int) -> QFont:
    """Editor font with fallbacks: Inter for Latin, Vazirmatn for Persian.

    Inter carries no Arabic-script glyphs, so with Inter first the Persian
    text falls through to Vazirmatn while English gets Inter — one font
    chain covers both scripts cleanly."""
    font = QFont()
    font.setFamilies([family, "Inter", "Vazirmatn", "Segoe UI"])
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
        font_size: int = 14,
        recovery_id: str | None = None,
        direction_mode: str = "auto",
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

        self.code_bar = QWidget()
        self.code_bar.setObjectName("codeBar")
        code_layout = QHBoxLayout(self.code_bar)
        code_layout.setContentsMargins(14, 6, 14, 6)
        self.code_label = QLabel("Code block")
        self.code_label.setObjectName("codeLabel")
        self.copy_code_button = QPushButton("Copy code")
        self.copy_code_button.setObjectName("copyCodeButton")
        self.copy_code_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_code_button.clicked.connect(self.copy_current_code)
        code_layout.addWidget(self.code_label)
        code_layout.addStretch()
        code_layout.addWidget(self.copy_code_button)
        self.code_bar.hide()
        layout.addWidget(self.code_bar)

        self.editor = SmartEditor()
        self.editor.setFont(editor_font(font_family, font_size))
        self.editor.set_direction_mode(direction_mode)
        self.highlighter = MarkdownHighlighter(self.editor)
        self.editor.markdown_highlighter = self.highlighter
        layout.addWidget(self.editor)

        self.preview = QTextBrowser()
        self.preview.setFont(editor_font(font_family, font_size))
        self.preview.hide()
        layout.addWidget(self.preview)
        self._preview_active = False

        self.editor.setPlainText(text)
        self.editor.document().setModified(False)
        self.editor.textChanged.connect(self._invalidate_counts)
        self.editor.textChanged.connect(self.state_changed)
        self.editor.cursorPositionChanged.connect(self.cursor_changed)
        self.editor.code_block_changed.connect(self._update_code_bar)
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

    @property
    def preview_active(self) -> bool:
        return self._preview_active

    def _invalidate_counts(self):
        self._counts = None

    def counts(self) -> tuple[int, int]:
        """(words, characters) — recomputed only when the text changed."""
        if self._counts is None:
            text = self.text
            self._counts = (len(text.split()), len(text))
        return self._counts

    def toggle_preview(self) -> bool:
        if self._preview_active:
            self.preview.hide()
            self.editor.show()
            self._preview_active = False
        else:
            self.preview.document().setMarkdown(self.text)
            self.preview.setLayoutDirection(self.editor.layoutDirection())
            self.code_bar.hide()
            self.editor.hide()
            self.preview.show()
            self._preview_active = True
        return self._preview_active

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

    def _update_code_bar(self, code_block):
        self.code_bar.setVisible(code_block is not None)
        if code_block is None:
            return
        language = f" · {code_block.language}" if code_block.language else ""
        source = "Markdown" if code_block.fenced else "auto-detected"
        self.code_label.setText(f"Code block · {source}{language}")

    def copy_current_code(self):
        code_block = self.editor.current_code_block()
        if code_block is None:
            return
        QApplication.clipboard().setText(code_block.text)
        self.copy_code_button.setText("Copied ✓")
        QTimer.singleShot(1200, lambda: self.copy_code_button.setText("Copy code"))
