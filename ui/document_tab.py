from pathlib import Path

from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.recovery_manager import new_recovery_id
from core.settings_manager import font_chain
from ui.editor import SmartEditor
from ui.markdown_highlighter import MarkdownHighlighter


def editor_font(latin: str, persian: str, size: float) -> QFont:
    """Editor font covering both scripts — see settings_manager.font_chain.

    `size` is in CSS pixels (the design's 14.5px body); a pixel is three
    quarters of a point at 96 logical DPI.
    """
    font = QFont()
    font.setFamilies(
        font_chain({"font_family_latin": latin, "font_family_persian": persian})
    )
    font.setPointSizeF(size * 0.75)
    return font


class DocumentTab(QWidget):
    state_changed = pyqtSignal()
    cursor_changed = pyqtSignal()
    reading_changed = pyqtSignal(bool)

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
        # Where this document will be written the first time it is saved,
        # for a note that has a name in mind but no file yet.
        pending_path: str | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.path = str(Path(path).resolve()) if path else None
        self.encoding = encoding
        self.recovery_id = recovery_id or new_recovery_id()
        self.untitled_title = title or "Untitled"
        self.pending_path = str(Path(pending_path)) if pending_path else None
        self._counts: tuple[int, int] | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.editor = SmartEditor()
        self.editor.setFont(editor_font(font_family, font_family_persian, font_size))
        self.editor.set_direction_mode(direction_mode)
        self.highlighter = MarkdownHighlighter(self.editor)
        self.editor.markdown_highlighter = self.highlighter
        # The editor, and — built the first time it is asked for — the
        # reading view of the same text (ui/reader_view.py).
        self.pages = QStackedWidget()
        self.pages.addWidget(self.editor)
        layout.addWidget(self.pages)
        self.reader = None
        self._focus_layout = False
        # Typing never happens while reading, but a command can still change
        # the text (Ctrl+D, a file changed outside the app). One repaint for
        # a burst of changes.
        self._reader_timer = QTimer(self, singleShot=True, interval=120)
        self._reader_timer.timeout.connect(self._render_reader)

        self.editor.setPlainText(text)
        self.editor.document().setModified(False)
        self.editor.textChanged.connect(self._invalidate_counts)
        self.editor.textChanged.connect(self.state_changed)
        self.editor.textChanged.connect(self._reader_out_of_date)
        self.editor.direction_changed.connect(self._reader_out_of_date)
        self.editor.cursorPositionChanged.connect(self.cursor_changed)
        self.editor.setFocus()

    @property
    def modified(self) -> bool:
        return self.editor.document().isModified()

    @property
    def display_name(self) -> str:
        if self.path:
            return Path(self.path).name
        if self.pending_path:
            return Path(self.pending_path).name
        return self.untitled_title

    @property
    def text(self) -> str:
        return self.editor.toPlainText()

    def apply_font(self, font: QFont):
        self.editor.setFont(font)
        self._reader_out_of_date()

    def set_focus_layout(self, on: bool):
        self._focus_layout = on
        self.editor.set_focus_layout(on)
        if self.reader is not None:
            self.reader.set_focus_layout(on)

    # Reading view

    @property
    def reading(self) -> bool:
        return self.reader is not None and self.pages.currentWidget() is self.reader

    def set_reading(self, on: bool):
        """Show the note as a finished page, or go back to editing it."""
        if on == self.reading:
            return
        if on:
            if self.reader is None:
                from ui.reader_view import ReaderView

                self.reader = ReaderView()
                self.reader.set_focus_layout(self._focus_layout)
                # A «[[note]]» clicked while reading opens like one clicked
                # in the editor.
                self.reader.link_clicked.connect(self.editor.link_clicked)
                self.pages.addWidget(self.reader)
            self._render_reader()
            self.pages.setCurrentWidget(self.reader)
            self.reader.setFocus()
        else:
            self._reader_timer.stop()
            self.pages.setCurrentWidget(self.editor)
            self.editor.setFocus()
        self.reading_changed.emit(on)

    def refresh_reading(self):
        """After a theme change: the reading view sets its colours itself."""
        if self.reading:
            self.reader.refresh()

    def _reader_out_of_date(self, *_args):
        if self.reading:
            self._reader_timer.start()

    def _render_reader(self):
        self.reader.render(self.text, self.editor.font(), self.editor.direction_mode)

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
