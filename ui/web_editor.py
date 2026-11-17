"""The TipTap editor, hosted in Qt WebEngine.

The page lives in ``editor-web/`` (built to ``editor-web/dist``). The page is
the single source of truth for a note's text. This widget:

* hands the page a note's text and keeps a copy of what the page last said;
* answers the same questions the old QTextEdit-based editor did (``document()``,
  ``textCursor()``, ``toPlainText()`` …) from a hidden *shadow* QTextDocument
  that mirrors the page, so the rest of the app — tasks written back from the
  rail, dates, find and replace — works unchanged;
* sends an edit made on that shadow document back to the page.

Saving never uses a stale copy: ``fresh_text()`` asks the page when it has
changes it has not yet reported.
"""
import json
import logging
import sys
from pathlib import Path

from PyQt6.QtCore import QEventLoop, QObject, Qt, QTimer, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QFont, QTextCursor, QTextDocument
from PyQt6.QtWidgets import QTextEdit, QVBoxLayout, QWidget

log = logging.getLogger("notepad.web_editor")

try:  # Not every build ships the web engine; the old editor is the fallback.
    from PyQt6.QtWebChannel import QWebChannel
    from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
    from PyQt6.QtWebEngineWidgets import QWebEngineView

    ENGINE = True
except ImportError:  # pragma: no cover - depends on the installation
    ENGINE = False


def bundle_dir() -> Path:
    """Where the built page is: inside the app when frozen, in the repo otherwise."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "editor-web"
    return Path(__file__).resolve().parent.parent / "editor-web" / "dist"


ASSETS_FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"


def available() -> bool:
    return ENGINE and (bundle_dir() / "index.html").is_file()


class _Bridge(QObject):
    """What the page calls. Slot names are the page's; signals are ours."""

    text_reported = pyqtSignal(str)
    became_dirty = pyqtSignal()
    cursor_reported = pyqtSignal(int, int, int, int)
    became_ready = pyqtSignal()
    note_link = pyqtSignal(str)
    date_requested = pyqtSignal()
    zoom_requested = pyqtSignal(int)

    @pyqtSlot(str)
    def changed(self, text):
        self.text_reported.emit(text)

    @pyqtSlot()
    def dirty(self):
        self.became_dirty.emit()

    @pyqtSlot(int, int, int, int)
    def cursor(self, line, column, selected, block):
        self.cursor_reported.emit(line, column, selected, block)

    @pyqtSlot()
    def ready(self):
        self.became_ready.emit()

    @pyqtSlot(str)
    def noteLink(self, target):
        self.note_link.emit(target)

    @pyqtSlot()
    def dateRequested(self):
        self.date_requested.emit()

    @pyqtSlot(int)
    def zoom(self, direction):
        self.zoom_requested.emit(direction)


if ENGINE:

    class _Page(QWebEnginePage):
        def javaScriptConsoleMessage(self, level, message, line, source):
            # Page errors belong in the app's log, not on a console nobody sees.
            log.log(
                logging.ERROR if "Error" in message else logging.DEBUG,
                "page: %s (%s:%s)", message, source, line,
            )


class WebEditor(QWidget):
    is_web = True
    # The old editor's enum, so ``tab.editor.LineWrapMode.WidgetWidth`` still reads.
    LineWrapMode = QTextEdit.LineWrapMode

    # What the old editor emitted, so the window connects to either one.
    textChanged = pyqtSignal()
    cursorPositionChanged = pyqtSignal()
    zoom_requested = pyqtSignal(int)
    direction_changed = pyqtSignal(str)
    link_clicked = pyqtSignal(str)
    date_requested = pyqtSignal()
    ready = pyqtSignal()

    def __init__(self, parent=None, headless: bool = False):
        super().__init__(parent)
        self.direction_mode = "rtl"
        self.markdown_highlighter = None
        self.line = 1
        self.column = 1
        self.selected = 0

        self._text = ""
        self._pending = False  # the page has changes it has not reported yet
        self._is_ready = headless
        self._queue: list[str] = []
        self.sent: list[str] = []  # what was sent to the page (tests read this)
        self._match: QTextCursor | None = None
        self._mirroring = False

        # The shadow: what the rest of the app reads and edits.
        self._doc = QTextDocument(self)
        self._doc.contentsChanged.connect(self._shadow_edited)

        self._view = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        if not headless:
            self._build_view(layout)

    def _build_view(self, layout):
        self._view = QWebEngineView(self)
        self._page = _Page(self._view)
        self._view.setPage(self._page)
        settings = self._page.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled, False)
        self._bridge = _Bridge(self)
        self._channel = QWebChannel(self)
        self._channel.registerObject("bridge", self._bridge)
        self._page.setWebChannel(self._channel)
        self._bridge.text_reported.connect(self._on_text)
        self._bridge.became_dirty.connect(self._on_dirty)
        self._bridge.cursor_reported.connect(self._on_cursor)
        self._bridge.became_ready.connect(self._on_ready)
        self._bridge.note_link.connect(self.link_clicked)
        self._bridge.date_requested.connect(self.date_requested)
        self._bridge.zoom_requested.connect(self.zoom_requested)
        layout.addWidget(self._view)
        self._view.load(QUrl.fromLocalFile(str(bundle_dir() / "index.html")))

    # Talking to the page

    def _js(self, code: str):
        self.sent.append(code)
        if not self._is_ready:
            self._queue.append(code)
        elif self._view is not None:
            self._page.runJavaScript(code)

    def call(self, function: str, *args):
        self._js(f"window.NotepadEditor.{function}({', '.join(json.dumps(a) for a in args)})")

    def _on_ready(self):
        self._is_ready = True
        queued, self._queue = self._queue, []
        for code in queued:
            self._page.runJavaScript(code)
        self.ready.emit()

    def is_ready(self) -> bool:
        return self._is_ready

    # The text, as the page holds it

    def _set_shadow(self, text: str):
        self._mirroring = True
        try:
            self._doc.setPlainText(text)
        finally:
            self._mirroring = False
        self._match = None

    def toPlainText(self) -> str:
        return self._text

    def fresh_text(self) -> str:
        """The page's text right now, asking it if it has unreported changes."""
        if self._pending:
            self.flush()
        return self._text

    def setPlainText(self, text: str):
        """Open a note, or reload one from disk."""
        self._text = text
        self._pending = False
        self._set_shadow(text)
        self.call("open", text)
        self.textChanged.emit()

    def replace_text(self, text: str):
        """An edit made outside the page: swap the text, keep the caret."""
        self._text = text
        self._pending = False
        self.call("replace", text)

    def _on_dirty(self):
        self._pending = True

    def _on_text(self, text: str):
        self._pending = False
        if text == self._text:
            return
        self._text = text
        self._set_shadow(text)
        self._doc.setModified(True)
        self.textChanged.emit()

    def _shadow_edited(self):
        """Python code edited the shadow document: tell the page."""
        if self._mirroring:
            return
        text = self._doc.toPlainText()
        if text == self._text:
            return
        self._text = text
        self._match = None
        self.replace_text(text)
        self.textChanged.emit()

    def flush(self, timeout_ms: int = 1500) -> str:
        """Ask the page for its text and wait for the answer."""
        if self._view is None or not self._is_ready:
            return self._text
        loop = QEventLoop()
        answer = {}

        def got(value):
            answer["text"] = value
            loop.quit()

        self._page.runJavaScript("window.NotepadEditor.flush()", got)
        QTimer.singleShot(timeout_ms, loop.quit)
        loop.exec()
        text = answer.get("text")
        if isinstance(text, str) and text != self._text:
            self._on_text(text)
        self._pending = False
        return self._text

    # The old editor's document and cursor, read from the shadow

    def document(self) -> QTextDocument:
        return self._doc

    def textCursor(self) -> QTextCursor:
        if self._match is not None:
            return QTextCursor(self._match)
        cursor = QTextCursor(self._doc)
        block = self._doc.findBlockByNumber(max(0, self.line - 1))
        if not block.isValid():
            block = self._doc.lastBlock()
        cursor.setPosition(block.position() + min(max(0, self.column - 1), max(0, block.length() - 1)))
        return cursor

    def setTextCursor(self, cursor: QTextCursor):
        self._match = None
        self.line = cursor.blockNumber() + 1
        self.column = cursor.positionInBlock() + 1
        self.go_to_line(self.line)
        self.cursorPositionChanged.emit()

    def _on_cursor(self, line, column, selected, _block):
        self.line, self.column, self.selected = line, column, selected
        self._match = None
        self.cursorPositionChanged.emit()

    # Commands (the page does the editing, so undo stays one step per action)

    def command(self, name: str, argument=None):
        if argument is None:
            self.call("cmd", name)
        else:
            self.call("cmd", name, argument)

    def insert_text(self, text: str):
        self.command("insertText", text)

    def go_to_line(self, line: int):
        self.call("goToLine", int(line))

    def setFocus(self, *args):
        if self._view is not None:
            self._view.setFocus()
        self.call("focus")

    def selected_text(self, callback):
        if self._view is not None and self._is_ready:
            self._page.runJavaScript("window.NotepadEditor.selectedText()", callback)

    # Find: the shadow decides what matches; Chromium shows it

    def find(self, needle, options=None) -> bool:
        flags = options if options is not None else QTextDocument.FindFlag(0)
        start = self.textCursor()
        if not flags & QTextDocument.FindFlag.FindBackward:
            start.setPosition(start.selectionEnd())
        found = self._doc.find(needle, start, flags)
        if found.isNull():
            return False
        self._match = found
        if self._view is not None and self._is_ready:
            page_flags = QWebEnginePage.FindFlag(0)
            if flags & QTextDocument.FindFlag.FindBackward:
                page_flags |= QWebEnginePage.FindFlag.FindBackward
            if flags & QTextDocument.FindFlag.FindCaseSensitively:
                page_flags |= QWebEnginePage.FindFlag.FindCaseSensitively
            self._page.findText(needle, page_flags)
        return True

    # Look

    def set_theme(self, colours: dict):
        self.call("theme", colours)

    def apply_palette(self, palette: dict):
        """The app's colours as the page's variables."""
        self.set_theme({
            "bg": palette["window"],
            "chrome": palette.get("surface", palette["window"]),
            "text": palette["text"],
            "muted": palette["muted"],
            "border": palette["border"],
            "hover": palette["hover"],
            "accent": palette["accent"],
            "danger": palette["danger"],
            "code": palette.get("surface_alt", palette["hover"]),
        })

    def setFont(self, font: QFont):
        super().setFont(font)
        families = ", ".join(f'"{name}"' for name in font.families() or [font.family()])
        size = font.pointSizeF() / 0.75 if font.pointSizeF() > 0 else 15
        self.call("font", {"families": families + ", system-ui, sans-serif", "size": round(size, 2)})

    def load_fonts(self, folder: Path):
        """Hand the page the fonts the app bundles; Chromium cannot see Qt's."""
        faces = []
        for path in sorted(Path(folder).glob("*.ttf")):
            family, _, style = path.stem.partition("-")
            weight = {"Regular": 400, "Medium": 500, "SemiBold": 600, "Bold": 700}.get(style, 400)
            faces.append({"family": family, "url": path.resolve().as_uri(), "weight": weight})
        self.call("font", {"faces": faces})

    def set_direction_mode(self, mode: str):
        self.direction_mode = mode
        self.call("direction", mode)

    def current_direction(self) -> str:
        return "ltr" if self.direction_mode == "ltr" else "rtl"

    def set_full_width(self, full: bool):
        self.call("width", bool(full))

    # Things the old editor had that have no meaning here

    def set_focus_layout(self, on: bool):
        pass

    def set_line_numbers_visible(self, visible: bool):
        pass

    def setLineWrapMode(self, mode):
        pass

    def set_link_resolver(self, resolver):
        pass

    def set_link_names(self, source):
        pass

    def show_link_completer(self):
        pass
