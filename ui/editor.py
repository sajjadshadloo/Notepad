import re
from dataclasses import dataclass

from PyQt6.QtCore import QPoint, QPointF, QRect, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPen,
    QTextBlockFormat,
    QTextCursor,
    QTextFormat,
)
from PyQt6.QtWidgets import QTextEdit, QWidget

from core.list_editing import (
    display_number_marker,
    indent_list_line,
    outdent_list_line,
    parse_list_item,
)
from core.rtl_detector import detect_direction
from core.syntax import detect_language, normalize_language
from ui.styles import current_is_light, current_palette


class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.setObjectName("lineNumberArea")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

    def sizeHint(self):
        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.editor.paint_line_number_area(event)


# Above this character count the editor skips the heavy unfenced-code
# heuristic so that typing never freezes on very large files. Fenced
# ``` blocks and direction handling stay active.
LARGE_FILE_THRESHOLD = 200_000

# Marker layout. The checkbox is sized from the line height but clamped so it
# stays a recognisable control at both small and large font sizes.
MARKER_MIN_WIDTH = 10
NUMBERED_LIST_GUTTER = 36
NUMBERED_MARKER_EDGE = 7
CHECKBOX_MIN_SIZE = 13
CHECKBOX_MAX_SIZE = 17
# The clickable area is grown around the painted box so the checkbox is a
# comfortable hit target without making the drawn square look heavy.
CHECKBOX_HIT_PADDING = 3


@dataclass(frozen=True)
class CodeBlock:
    start_line: int
    end_line: int
    text: str
    language: str = ""
    fenced: bool = False

    def contains(self, line_number: int) -> bool:
        return self.start_line <= line_number <= self.end_line


def code_lines_of(blocks: list["CodeBlock"]) -> set[int]:
    """Flatten code blocks into the set of line numbers they cover."""
    return {
        line_number
        for block in blocks
        for line_number in range(block.start_line, block.end_line + 1)
    }


_CODE_START = re.compile(
    r"^\s*(?:"
    r"def\s+\w+|class\s+\w+|async\s+def\s+\w+|"
    r"from\s+\w+\s+import|import\s+[\w.]|"
    r"function\s+&?\w*\s*\(|(?:const|let|var)\s+\w+|"
    r"(?:if|for|foreach|while|switch|try|catch|elseif)\s*[\(\{]|"
    r"(?:else|elif|try|except|finally|do)\s*:?\s*$|"
    r"(?:return|raise|yield|await|print|echo|throw|die|exit)\b|"
    r"console\.\w+\s*\(|"
    r"(?:public|private|protected|static|abstract|final)\s+|"
    r"#include\b|#define\b|SELECT\b|INSERT\b|UPDATE\b|DELETE\s+FROM\b|"
    r"CREATE\s+(?:TABLE|INDEX|VIEW)\b|"
    r"<\?(?:php|=)?|\?>|"
    r"<[/!?]?[a-zA-Z][^>]*>?|"
    r"\$\w+\s*(?:=|\[|->)|"
    r"@[\w.]+\s*(?:\(.*\))?\s*$|"
    r"[\w\"']+\s*:\s*(?:[\[{\d\"']|true\b|false\b|null\b)|"
    r"\w+\s*=\s*(?:[\[{\d\"'(]|lambda\b|function\b|new\s|\w+\s*\()|"
    r"[\w.\->:$\]]+\s*\(.*\)\s*[;,{]?\s*$|"
    r"[\}\]\)]\s*[,;]?\s*$|"
    r"[.#]?[\w-]+(?:\s*[,>+~]\s*[.#]?[\w-]+)*\s*\{\s*$"
    r")",
    re.IGNORECASE,
)

# Strong RTL characters mean prose, never code.
_RTL_CHAR_RE = re.compile(r"[֐-ࣿיִ-﷽ﹰ-ﻼ]")

# First word of a line that is SQL even without any symbol on it.
_SQL_WORDS = {
    "select", "from", "where", "insert", "update", "delete", "join",
    "inner", "left", "right", "group", "order", "having", "union",
    "values", "create", "alter", "drop", "and", "or", "on", "set",
}


def detect_code_blocks(text: str, heuristic: bool = True) -> list[CodeBlock]:
    """Find code blocks in ``text``.

    Fenced ``` blocks are always detected. The heavier heuristic that spots
    unfenced code is skipped when ``heuristic`` is False (used for very large
    files to keep typing responsive).
    """
    lines = text.splitlines()
    blocks: list[CodeBlock] = []
    fenced_start = None
    fenced_language = ""

    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("```"):
            if fenced_start is None:
                fenced_start = index
                fenced_language = stripped[3:].strip()
            else:
                content = "\n".join(lines[fenced_start + 1:index])
                blocks.append(
                    CodeBlock(
                        fenced_start,
                        index,
                        content,
                        fenced_language,
                        fenced=True,
                    )
                )
                fenced_start = None
                fenced_language = ""

    if fenced_start is not None:
        blocks.append(
            CodeBlock(
                fenced_start,
                max(fenced_start, len(lines) - 1),
                "\n".join(lines[fenced_start + 1:]),
                fenced_language,
                fenced=True,
            )
        )

    for position, block in enumerate(blocks):
        if block.fenced and not block.language:
            detected = detect_language(block.text)
            if detected:
                blocks[position] = CodeBlock(
                    block.start_line, block.end_line, block.text,
                    detected, fenced=True,
                )

    if not heuristic:
        return sorted(blocks, key=lambda block: block.start_line)

    fenced_lines = code_lines_of(blocks)
    index = 0
    while index < len(lines):
        if index in fenced_lines or not _looks_like_code(lines[index]):
            index += 1
            continue
        start = index
        index += 1
        while index < len(lines) and index not in fenced_lines:
            line = lines[index]
            if _looks_like_code(line) or _continues_code(line):
                index += 1
                continue
            if not line.strip():
                # Blank gaps stay inside the block as long as code resumes
                # within a couple of lines (blank lines are common in code).
                lookahead = index + 1
                while (
                    lookahead < len(lines)
                    and lookahead - index <= 2
                    and not lines[lookahead].strip()
                ):
                    lookahead += 1
                if (
                    lookahead < len(lines)
                    and lookahead not in fenced_lines
                    and _looks_like_code(lines[lookahead])
                ):
                    index = lookahead + 1
                    continue
            break
        end = index - 1
        while end > start and not lines[end].strip():
            end -= 1
        content = "\n".join(lines[start:end + 1])
        blocks.append(
            CodeBlock(start, end, content, detect_language(content))
        )

    return sorted(blocks, key=lambda block: block.start_line)


def _is_prose(line: str) -> bool:
    """A line that clearly reads as natural text, never code."""
    stripped = line.strip()
    if not stripped:
        return False
    if _RTL_CHAR_RE.search(stripped):
        return True
    words = re.findall(r"[A-Za-z']+", stripped)
    if len(words) < 4:
        return False
    if words[0].lower() in _SQL_WORDS:
        return False
    # Several words and none of the punctuation code lives on.
    return not re.search(r"[;{}=<>$@#\\]|\(\)|\[|->|::|\w\(", stripped)


def _looks_like_code(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if _is_prose(line):
        return False
    if _CODE_START.search(line):
        return True
    if stripped.endswith((";", "{", "}", "=>", "*/")):
        return True
    if stripped.startswith(("/*", "*/", "//")):
        return True
    return bool(
        re.search(r"(?:==|!=|<=|>=|&&|\|\||->|::|\+=|-=|\*=|/=|=>)", stripped)
    )


def _continues_code(line: str) -> bool:
    """Whether a line that doesn't *start* a block may still belong to one.

    Keeps indented continuation lines, lone brackets and short symbol
    lines inside the block so real-world code isn't chopped into pieces.
    """
    stripped = line.strip()
    if not stripped or _is_prose(line):
        return False
    if line[0] in " \t":
        return True
    if len(stripped) <= 3:
        return True
    first_word = re.match(r"[A-Za-z]+", stripped)
    if first_word and first_word.group().lower() in _SQL_WORDS:
        return True
    return bool(re.search(r"[(){}\[\];=$<>]", stripped))


class SmartEditor(QTextEdit):
    """Plain-text editor with line numbers and paragraph-level bidi direction."""

    code_block_changed = pyqtSignal(object)
    zoom_requested = pyqtSignal(int)
    direction_changed = pyqtSignal(str)

    # Windows scan codes for the left and right Shift keys. Pressing the
    # right Shift while holding Ctrl switches to RTL, the left one to LTR —
    # the same convention Windows itself uses in text fields.
    _SHIFT_SCANCODES = {42: "ltr", 54: "rtl"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptRichText(False)
        self.direction_mode = "auto"
        self._formatting = False
        self._code_blocks: list[CodeBlock] = []
        self._code_line_set: set[int] = set()
        self._code_line_language: dict[int, str] = {}
        self._line_numbers_visible = True
        self.markdown_highlighter = None
        self._hovered_checkbox_block: int | None = None
        self._marker_cache: list | None = None
        self._line_area = LineNumberArea(self)
        self.viewport().setMouseTracking(True)
        # A single debounced pass scans the text once and updates both the
        # code highlight and paragraph directions, instead of scanning twice.
        self._refresh_timer = QTimer(self, singleShot=True, interval=120)
        self._refresh_timer.timeout.connect(self._refresh_layout)

        self.document().blockCountChanged.connect(self._update_line_area_width)
        self.verticalScrollBar().valueChanged.connect(self._line_area.update)
        self.horizontalScrollBar().valueChanged.connect(self._line_area.update)
        self.textChanged.connect(self._schedule_refresh)
        self.textChanged.connect(self._line_area.update)
        self.cursorPositionChanged.connect(self._cursor_context_changed)
        # Anything that moves a marker on screen drops the cached geometry.
        self.textChanged.connect(self._invalidate_marker_cache)
        self.verticalScrollBar().valueChanged.connect(self._invalidate_marker_cache)
        self.horizontalScrollBar().valueChanged.connect(self._invalidate_marker_cache)
        self.document().documentLayout().documentSizeChanged.connect(
            lambda _size: self._invalidate_marker_cache()
        )
        self._update_line_area_width()

    # Line numbers

    def line_number_area_width(self) -> int:
        digits = max(2, len(str(max(1, self.document().blockCount()))))
        return 14 + self.fontMetrics().horizontalAdvance("9") * digits

    def _update_line_area_width(self):
        # Line numbers live in a fixed gutter on the left, regardless of the
        # per-paragraph text direction.
        width = self.line_number_area_width() if self._line_numbers_visible else 0
        self.setViewportMargins(width, 0, 0, 0)

    def set_line_numbers_visible(self, visible: bool):
        self._line_numbers_visible = visible
        self._line_area.setVisible(visible)
        self._update_line_area_width()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._invalidate_marker_cache()
        content = self.contentsRect()
        width = self.line_number_area_width()
        self._line_area.setGeometry(
            QRect(content.left(), content.top(), width, content.height())
        )

    def paint_line_number_area(self, event):
        painter = QPainter(self._line_area)
        theme = current_palette()
        idle_color = QColor(theme["muted"])
        idle_color.setAlpha(150)
        current_color = QColor(theme["accent"])
        current_line = self.textCursor().blockNumber()

        number_font = QFont(self.font())
        number_font.setPointSizeF(max(7.0, self.font().pointSizeF() * 0.85))
        painter.setFont(number_font)

        first_cursor = self.cursorForPosition(QPoint(0, 0))
        block = first_cursor.block()
        number = block.blockNumber()

        while block.isValid():
            cursor = QTextCursor(block)
            top = self.cursorRect(cursor).top()
            height = max(self.fontMetrics().height(), self.cursorRect(cursor).height())
            bottom = top + height
            if top > event.rect().bottom():
                break
            if block.isVisible() and bottom >= event.rect().top():
                is_current = number == current_line
                number_font.setBold(is_current)
                painter.setFont(number_font)
                painter.setPen(current_color if is_current else idle_color)
                painter.drawText(
                    0,
                    top,
                    self._line_area.width() - 10,
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight,
                    str(number + 1),
                )
            block = block.next()
            number += 1

    # Direction

    def set_direction_mode(self, mode: str):
        if mode not in {"auto", "rtl", "ltr"}:
            return
        self.direction_mode = mode
        self.apply_directions()
        self.direction_changed.emit(mode)

    def _schedule_refresh(self):
        if not self._formatting:
            self._refresh_timer.start()

    def _refresh_layout(self):
        """Single pass: scan code blocks once, then reuse for directions."""
        self.refresh_code_blocks()
        self.apply_directions()

    def _direction_for_text(self, text: str, is_code: bool = False) -> str:
        # Code is always LTR, even when the user forces the document RTL —
        # right-to-left code is unreadable and breaks the block layout.
        if is_code:
            return "ltr"
        if self.direction_mode in {"rtl", "ltr"}:
            return self.direction_mode
        # Markdown markers are presentation, not content. In particular the
        # ``x`` in ``- [x] متن`` must not turn a completed Persian task LTR.
        item = parse_list_item(text)
        direction_text = item.body if item is not None else text
        return detect_direction(direction_text, default="rtl")

    def _apply_block_direction(self, cursor: QTextCursor, direction: str) -> bool:
        """Apply layout/alignment/margins; True when the block actually changed."""
        current = cursor.blockFormat()
        item = parse_list_item(cursor.block().text())
        numbered = (
            item is not None
            and item.kind == "numbered"
            and not self.line_is_code(cursor.block().blockNumber())
        )
        expected_layout = (
            Qt.LayoutDirection.RightToLeft
            if direction == "rtl"
            else Qt.LayoutDirection.LeftToRight
        )
        expected_alignment = (
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignAbsolute
            if direction == "rtl"
            else Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignAbsolute
        )
        expected_left_margin = (
            float(NUMBERED_LIST_GUTTER)
            if numbered and direction == "ltr"
            else 0.0
        )
        expected_right_margin = (
            float(NUMBERED_LIST_GUTTER)
            if numbered and direction == "rtl"
            else 0.0
        )
        # Exact comparison: an `&` test passes as soon as the AlignAbsolute
        # bit matches, silently skipping the actual left/right realignment.
        if (
            current.layoutDirection() == expected_layout
            and current.alignment() == expected_alignment
            and current.leftMargin() == expected_left_margin
            and current.rightMargin() == expected_right_margin
        ):
            return False
        fmt = QTextBlockFormat(current)
        fmt.setLayoutDirection(expected_layout)
        fmt.setAlignment(expected_alignment)
        fmt.setLeftMargin(expected_left_margin)
        fmt.setRightMargin(expected_right_margin)
        cursor.setBlockFormat(fmt)
        return True

    def apply_directions(self):
        if self._formatting:
            return
        self._formatting = True
        document = self.document()
        was_modified = document.isModified()
        # Reuse the already-computed code blocks rather than rescanning.
        code_lines = code_lines_of(self._code_blocks)
        # One edit block so the whole pass is a single undo command, which
        # the undo/redo overrides below can then skip over transparently.
        changed = False
        guard = QTextCursor(document)
        guard.beginEditBlock()
        try:
            block = document.begin()
            while block.isValid():
                cursor = QTextCursor(block)
                changed |= self._apply_block_direction(
                    cursor,
                    self._direction_for_text(
                        block.text(), block.blockNumber() in code_lines
                    ),
                )
                block = block.next()
        finally:
            guard.endEditBlock()
            document.setModified(was_modified)
            self._formatting = False
        # Relayouting the whole document is expensive on large files; skip it
        # on the common typing path where no paragraph changed direction.
        if changed:
            document.markContentsDirty(0, document.characterCount())
            self.viewport().update()

    # Undo/redo that skip invisible auto-format passes. Qt records the
    # automatic per-paragraph direction formatting as regular undo commands;
    # stepping again while the text is unchanged keeps Ctrl+Z/Ctrl+Y focused
    # on what the user actually typed.

    def undo(self):
        document = self.document()
        before = self.toPlainText()
        super().undo()
        while document.isUndoAvailable() and self.toPlainText() == before:
            super().undo()

    def redo(self):
        document = self.document()
        before = self.toPlainText()
        super().redo()
        while document.isRedoAvailable() and self.toPlainText() == before:
            super().redo()

    def _cursor_context_changed(self):
        self._ensure_current_empty_block_direction()
        self.code_block_changed.emit(self.current_code_block())
        self._line_area.update()

    def _ensure_current_empty_block_direction(self):
        # Purely cosmetic (cursor side on an empty line) — never worth
        # clearing the redo chain for, so skip while a redo is pending.
        if self.document().isRedoAvailable():
            return
        block = self.textCursor().block()
        if block.isValid() and not block.text():
            was_modified = self.document().isModified()
            self._apply_block_direction(
                QTextCursor(block), self._direction_for_text("")
            )
            self.document().setModified(was_modified)

    def current_direction(self) -> str:
        layout = self.textCursor().blockFormat().layoutDirection()
        return "rtl" if layout == Qt.LayoutDirection.RightToLeft else "ltr"

    # Code detection

    def line_is_code(self, line_number: int) -> bool:
        return line_number in self._code_line_set

    def code_language_for_line(self, line_number: int) -> str:
        """Normalized language id of the code block covering this line."""
        return self._code_line_language.get(line_number, "")

    def refresh_code_blocks(self):
        text = self.toPlainText()
        self._code_blocks = detect_code_blocks(
            text, heuristic=len(text) <= LARGE_FILE_THRESHOLD
        )
        new_code_lines = code_lines_of(self._code_blocks)
        new_languages = {
            line_number: normalize_language(code_block.language)
            for code_block in self._code_blocks
            for line_number in range(
                code_block.start_line, code_block.end_line + 1
            )
        }
        code_lines_changed = (
            new_code_lines != self._code_line_set
            or new_languages != self._code_line_language
        )
        self._code_line_set = new_code_lines
        self._code_line_language = new_languages
        selections: list[QTextEdit.ExtraSelection] = []
        document = self.document()

        background = QColor("#eef2f9" if current_is_light() else "#2a2b36")
        # No foreground here: the syntax highlighter colors the tokens and
        # an ExtraSelection foreground would paint over all of them.
        for code_block in self._code_blocks:
            for line_number in range(code_block.start_line, code_block.end_line + 1):
                block = document.findBlockByNumber(line_number)
                if not block.isValid():
                    continue
                selection = QTextEdit.ExtraSelection()
                selection.cursor = QTextCursor(block)
                selection.cursor.clearSelection()
                selection.format.setProperty(
                    QTextFormat.Property.FullWidthSelection, True
                )
                selection.format.setBackground(background)
                selection.format.setFontFamilies(["Consolas", "Cascadia Mono"])
                selection.format.setFontFixedPitch(True)
                selections.append(selection)

        self.setExtraSelections(selections)
        if code_lines_changed and self.markdown_highlighter is not None:
            was_formatting = self._formatting
            self._formatting = True
            try:
                self.markdown_highlighter.rehighlight()
            finally:
                self._formatting = was_formatting
        self.code_block_changed.emit(self.current_code_block())

    def current_code_block(self) -> CodeBlock | None:
        line_number = self.textCursor().blockNumber()
        return next(
            (block for block in self._code_blocks if block.contains(line_number)),
            None,
        )

    @classmethod
    def direction_for_shift_scancode(cls, scan_code: int) -> str | None:
        return cls._SHIFT_SCANCODES.get(scan_code)

    def keyPressEvent(self, event):
        # Ctrl + right/left Shift switches paragraph direction, matching the
        # native Windows text-field convention. Ctrl+Shift+Arrow is left
        # untouched so word selection keeps working.
        if (
            event.key() == Qt.Key.Key_Shift
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            mode = self.direction_for_shift_scancode(event.nativeScanCode())
            if mode:
                self.set_direction_mode(mode)
                event.accept()
                return

        if self._handle_list_key(event):
            event.accept()
            return

        previous = self.textCursor().block()
        previous_direction = self.current_direction()
        super().keyPressEvent(event)

        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            current = self.textCursor().block()
            if current.isValid() and not current.text() and previous.isValid():
                cursor = QTextCursor(current)
                if self.direction_mode == "auto":
                    self._apply_block_direction(cursor, previous_direction)
                else:
                    self._apply_block_direction(cursor, self.direction_mode)
        elif event.text():
            self._schedule_refresh()

    # Smart Markdown lists

    def _handle_list_key(self, event) -> bool:
        """Handle Word-like list continuation and indentation."""
        modifiers = event.modifiers()
        if modifiers & (
            Qt.KeyboardModifier.ControlModifier
            | Qt.KeyboardModifier.AltModifier
            | Qt.KeyboardModifier.MetaModifier
        ):
            return False

        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if modifiers & Qt.KeyboardModifier.ShiftModifier:
                return False
            if self._insert_paragraph_after_empty_block():
                return True
            return self._continue_list()

        if key in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
            outdent = key == Qt.Key.Key_Backtab or bool(
                modifiers & Qt.KeyboardModifier.ShiftModifier
            )
            return self._change_list_indent(outdent)

        if key == Qt.Key.Key_Backspace:
            return self._remove_empty_list_marker()

        return False

    def _insert_paragraph_after_empty_block(self) -> bool:
        """Make plain Enter advance from an already-empty paragraph.

        Qt does not create another block when Return is pressed in an empty
        paragraph carrying an explicit RTL/absolute block format. Shift+Enter
        still inserts a soft break, which was why the bug looked like Enter
        only worked with Shift. Insert the paragraph explicitly instead.
        """
        cursor = self.textCursor()
        if (
            cursor.hasSelection()
            or cursor.block().text()
            or self.line_is_code(cursor.blockNumber())
        ):
            return False

        previous_direction = self.current_direction()
        cursor.beginEditBlock()
        try:
            cursor.insertBlock()
            self._apply_block_direction(
                cursor,
                previous_direction if self.direction_mode == "auto" else self.direction_mode,
            )
        finally:
            cursor.endEditBlock()
        self.setTextCursor(cursor)
        self._schedule_refresh()
        return True

    def _continue_list(self) -> bool:
        cursor = self.textCursor()
        if cursor.hasSelection() or self.line_is_code(cursor.blockNumber()):
            return False
        block = cursor.block()
        item = parse_list_item(block.text())
        if item is None:
            return False
        previous_direction = self.current_direction()

        cursor.beginEditBlock()
        try:
            if item.is_empty:
                line = QTextCursor(block)
                line.movePosition(
                    QTextCursor.MoveOperation.EndOfBlock,
                    QTextCursor.MoveMode.KeepAnchor,
                )
                line.removeSelectedText()
                cursor = line
                # A second Enter on an empty list item both exits the list and
                # advances to a genuinely new paragraph. Previously the token
                # disappeared but the caret stayed on the same visual row,
                # which made Enter look broken unless Shift+Enter was used.
                cursor.insertBlock()
                if self.direction_mode == "auto":
                    self._apply_block_direction(cursor, previous_direction)
                else:
                    self._apply_block_direction(cursor, self.direction_mode)
            else:
                cursor.insertBlock()
                cursor.insertText(item.continuation_prefix())
                if self.direction_mode == "auto":
                    self._apply_block_direction(cursor, previous_direction)
                else:
                    self._apply_block_direction(cursor, self.direction_mode)
        finally:
            cursor.endEditBlock()

        self.setTextCursor(cursor)
        self._schedule_refresh()
        return True

    def _change_list_indent(self, outdent: bool) -> bool:
        cursor = self.textCursor()
        document = self.document()
        first = document.findBlock(cursor.selectionStart()).blockNumber()
        last = document.findBlock(cursor.selectionEnd()).blockNumber()
        blocks = [document.findBlockByNumber(number) for number in range(first, last + 1)]
        if not any(parse_list_item(block.text()) for block in blocks):
            return False

        transform = outdent_list_line if outdent else indent_list_line
        anchor = cursor.anchor()
        position = cursor.position()
        deltas: list[tuple[int, int]] = []
        edit = QTextCursor(document)
        edit.beginEditBlock()
        try:
            for block in blocks:
                old_text = block.text()
                new_text = transform(old_text)
                if new_text == old_text:
                    continue
                block_position = block.position()
                line = QTextCursor(block)
                line.movePosition(
                    QTextCursor.MoveOperation.EndOfBlock,
                    QTextCursor.MoveMode.KeepAnchor,
                )
                line.insertText(new_text)
                deltas.append((block_position, len(new_text) - len(old_text)))
        finally:
            edit.endEditBlock()

        def adjusted(original: int) -> int:
            return original + sum(delta for start, delta in deltas if start <= original)

        restored = QTextCursor(document)
        restored.setPosition(max(0, adjusted(anchor)))
        restored.setPosition(
            max(0, adjusted(position)), QTextCursor.MoveMode.KeepAnchor
        )
        self.setTextCursor(restored)
        self._schedule_refresh()
        return True

    def _remove_empty_list_marker(self) -> bool:
        cursor = self.textCursor()
        if cursor.hasSelection():
            return False
        block = cursor.block()
        item = parse_list_item(block.text())
        if (
            item is None
            or not item.is_empty
            or cursor.positionInBlock() < item.prefix_end
        ):
            return False

        cursor.beginEditBlock()
        try:
            line = QTextCursor(block)
            line.movePosition(
                QTextCursor.MoveOperation.EndOfBlock,
                QTextCursor.MoveMode.KeepAnchor,
            )
            line.removeSelectedText()
            cursor = line
        finally:
            cursor.endEditBlock()
        self.setTextCursor(cursor)
        self._schedule_refresh()
        return True

    def contextMenuEvent(self, event):
        """Slim custom context menu — no Unicode-control-character clutter,
        and Undo/Redo route through the format-skipping overrides."""
        from PyQt6.QtWidgets import QApplication, QMenu

        document = self.document()
        cursor = self.textCursor()
        menu = QMenu(self)

        undo = menu.addAction("Undo\tCtrl+Z", self.undo)
        undo.setEnabled(document.isUndoAvailable())
        redo = menu.addAction("Redo\tCtrl+Y", self.redo)
        redo.setEnabled(document.isRedoAvailable())
        menu.addSeparator()
        cut = menu.addAction("Cut\tCtrl+X", self.cut)
        cut.setEnabled(cursor.hasSelection())
        copy = menu.addAction("Copy\tCtrl+C", self.copy)
        copy.setEnabled(cursor.hasSelection())
        paste = menu.addAction("Paste\tCtrl+V", self.paste)
        paste.setEnabled(bool(QApplication.clipboard().text()))
        delete = menu.addAction(
            "Delete\tDel", lambda: self.textCursor().removeSelectedText()
        )
        delete.setEnabled(cursor.hasSelection())
        menu.addSeparator()
        menu.addAction("Select All\tCtrl+A", self.selectAll)

        menu.exec(event.globalPos())
        menu.deleteLater()

    # List marker presentation and interactive to-do checkboxes

    def _marker_rect(self, block, item) -> QRect:
        """Viewport rect of the marker token.

        The two cursor rects are the *visual* edges of the token, which swap
        sides in an RTL paragraph — so the span is taken from both edges
        rather than assuming the start cursor sits on the left. A minimum
        width keeps a zero-width span (marker scrolled out sideways, or a
        collapsed layout) from producing an unclickable rect.
        """
        start = QTextCursor(block)
        start.setPosition(block.position() + item.marker_start)
        end = QTextCursor(block)
        end.setPosition(block.position() + item.marker_end)
        start_rect = self.cursorRect(start)
        end_rect = self.cursorRect(end)
        left = min(start_rect.left(), end_rect.left())
        right = max(start_rect.right(), end_rect.right())
        width = max(MARKER_MIN_WIDTH, right - left)
        if item.kind == "numbered":
            # Numbered lists get a real gutter through QTextBlockFormat. Paint
            # into that fixed viewport-side column instead of following bidi
            # cursor geometry, which can jump across the text as line length
            # or window width changes.
            width = NUMBERED_LIST_GUTTER - NUMBERED_MARKER_EDGE * 2
            if self._direction_for_text(block.text()) == "rtl":
                right = self.viewport().width() - NUMBERED_MARKER_EDGE
                left = right - width
            else:
                left = NUMBERED_MARKER_EDGE
        top = min(start_rect.top(), end_rect.top())
        height = max(start_rect.height(), end_rect.height(), self.fontMetrics().height())
        return QRect(left, top, width, height)

    def _visible_list_markers(self):
        """Yield (block, item, rect) for list markers inside the viewport.

        Results are cached per paint/hover pass: the geometry only changes
        when the document, scroll position or font does, and recomputing it
        on every mouse move was the main cost of hovering a long list.
        """
        cached = self._marker_cache
        if cached is not None:
            yield from cached
            return

        markers = []
        block = self.cursorForPosition(QPoint(0, 0)).block()
        viewport_bottom = self.viewport().height()
        while block.isValid():
            top = self.cursorRect(QTextCursor(block)).top()
            if top > viewport_bottom:
                break
            if block.isVisible() and not self.line_is_code(block.blockNumber()):
                item = parse_list_item(block.text())
                if item is not None:
                    markers.append((block, item, self._marker_rect(block, item)))
            block = block.next()
        self._marker_cache = markers
        yield from markers

    def _invalidate_marker_cache(self):
        self._marker_cache = None

    def _checkbox_hit_rect(self, marker_rect: QRect) -> QRect:
        """Clickable area of a to-do checkbox, slightly larger than the box."""
        return marker_rect.adjusted(
            -CHECKBOX_HIT_PADDING,
            -CHECKBOX_HIT_PADDING,
            CHECKBOX_HIT_PADDING,
            CHECKBOX_HIT_PADDING,
        )

    def _paint_checkbox(self, painter, marker_rect, item, hovered, theme):
        accent = QColor(theme["accent"])
        muted = QColor(theme["muted"])
        on_accent = QColor(theme["on_accent"])

        size = max(CHECKBOX_MIN_SIZE, min(CHECKBOX_MAX_SIZE, marker_rect.height() - 4))
        box = QRect(0, 0, size, size)
        box.moveCenter(marker_rect.center())

        if item.checked:
            border = accent
        elif hovered:
            border = accent
        else:
            border = muted
        painter.setPen(QPen(border, 1.8))
        painter.setBrush(accent if item.checked else Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(box, 3, 3)

        if not item.checked:
            return
        # Tick geometry is derived from the box so it stays centred and
        # proportional at every font size.
        painter.setPen(
            QPen(on_accent, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        )
        left = QPointF(box.left() + size * 0.24, box.top() + size * 0.52)
        middle = QPointF(box.left() + size * 0.43, box.top() + size * 0.72)
        right = QPointF(box.left() + size * 0.76, box.top() + size * 0.30)
        painter.drawLine(left, middle)
        painter.drawLine(middle, right)

    def paintEvent(self, event):
        super().paintEvent(event)

        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        theme = current_palette()
        accent = QColor(theme["accent"])

        for block, item, marker_rect in self._visible_list_markers():
            if not marker_rect.intersects(event.rect()):
                continue

            if item.kind == "bullet":
                diameter = max(5, min(7, marker_rect.height() // 3))
                dot = QRect(0, 0, diameter, diameter)
                dot.moveCenter(marker_rect.center())
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(accent)
                painter.drawEllipse(dot)
            elif item.kind == "numbered":
                painter.save()
                font = QFont(self.font())
                font.setBold(True)
                font.setPointSizeF(max(9.0, self.font().pointSizeF()))
                painter.setFont(font)
                painter.setPen(accent)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                # Numbers hug the text they belong to: right-aligned in an
                # LTR paragraph, left-aligned when the marker sits on the
                # right of an RTL one. An RTL paragraph shows Persian digits
                # (display only — the file keeps ASCII digits), which also
                # keeps the "." visible instead of being bidi-reordered away.
                rtl = self._direction_for_text(block.text()) == "rtl"
                alignment = (
                    Qt.AlignmentFlag.AlignLeft if rtl else Qt.AlignmentFlag.AlignRight
                )
                # Draw the already-localized digits in a stable LTR run. Qt's
                # bidi reordering could otherwise move the punctuation over
                # the digit or paint part of it outside the marker rectangle.
                painter.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
                painter.drawText(
                    marker_rect,
                    int(
                        alignment
                        | Qt.AlignmentFlag.AlignVCenter
                    ),
                    display_number_marker(item.marker, rtl),
                )
                painter.restore()
            else:
                self._paint_checkbox(
                    painter,
                    marker_rect,
                    item,
                    block.blockNumber() == self._hovered_checkbox_block,
                    theme,
                )

        painter.end()

    def _checkbox_at(self, point) -> QTextCursor | None:
        """Cursor selecting the state character under a painted checkbox."""
        for block, item, marker_rect in self._visible_list_markers():
            if item.kind != "todo":
                continue
            if not self._checkbox_hit_rect(marker_rect).contains(point):
                continue
            toggle = QTextCursor(self.document())
            # group(2) of TODO_RE — the character between the brackets.
            toggle.setPosition(block.position() + item.marker_start + 3)
            # NextCharacter, not Right: "Right" follows *visual* order and so
            # selects the '[' instead of the state character in an RTL
            # paragraph, corrupting the marker on click.
            toggle.movePosition(
                QTextCursor.MoveOperation.NextCharacter,
                QTextCursor.MoveMode.KeepAnchor,
            )
            return toggle
        return None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not event.modifiers():
            toggle = self._checkbox_at(event.position().toPoint())
            if toggle is not None:
                checked = toggle.selectedText() in ("x", "X")
                # One edit block so a click is a single Ctrl+Z, matching the
                # keyboard toggle.
                toggle.beginEditBlock()
                try:
                    toggle.insertText(" " if checked else "x")
                finally:
                    toggle.endEditBlock()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        toggle = (
            self._checkbox_at(event.position().toPoint())
            if not event.buttons()
            else None
        )
        hovered_block = toggle.blockNumber() if toggle is not None else None
        if hovered_block != self._hovered_checkbox_block:
            self._hovered_checkbox_block = hovered_block
            self.viewport().update()
        self.viewport().setCursor(
            Qt.CursorShape.PointingHandCursor
            if toggle is not None
            else Qt.CursorShape.IBeamCursor
        )
        super().mouseMoveEvent(event)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta:
                self.zoom_requested.emit(1 if delta > 0 else -1)
            event.accept()
            return
        super().wheelEvent(event)

    def setPlainText(self, text: str):
        super().setPlainText(text)
        self.refresh_code_blocks()
        self.apply_directions()
