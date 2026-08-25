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


def fenced_code_lines(text: str) -> set[int]:
    """Line numbers inside ``` fenced blocks, the fence rows included.

    Only explicit fences count. Earlier versions also *guessed* at unfenced
    code with a pile of regexes; that ran over the whole document on every
    keystroke and, worse, misread ordinary Persian prose as code and forced
    it left-to-right. If you want a block, mark it with ```.
    """
    lines = text.splitlines()
    inside: set[int] = set()
    start = None
    for index, line in enumerate(lines):
        if line.strip().startswith("```"):
            if start is None:
                start = index
            else:
                inside.update(range(start, index + 1))
                start = None
    if start is not None:
        # An unclosed fence runs to the end of the document.
        inside.update(range(start, len(lines)))
    return inside


class SmartEditor(QTextEdit):
    """Plain-text editor with line numbers and paragraph-level bidi direction."""

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
        self._code_line_set: set[int] = set()
        self._line_numbers_visible = True
        self.markdown_highlighter = None
        self._hovered_checkbox_block: int | None = None
        self._marker_cache: list | None = None
        # Paragraphs touched since the last layout pass. Only these need their
        # direction re-applied; every other block already carries the right
        # format, and Qt keeps that format attached to the block itself rather
        # than to its number. An empty range means "nothing to do".
        self._dirty_first = 0
        self._dirty_last = -1
        self._needs_full_pass = True
        self._line_area = LineNumberArea(self)
        self.viewport().setMouseTracking(True)
        # A single debounced pass scans the text once and updates both the
        # code highlight and paragraph directions, instead of scanning twice.
        self._refresh_timer = QTimer(self, singleShot=True, interval=120)
        self._refresh_timer.timeout.connect(self._refresh_layout)

        self.document().blockCountChanged.connect(self._update_line_area_width)
        self.document().contentsChange.connect(self._note_contents_change)
        self.verticalScrollBar().valueChanged.connect(self._line_area.update)
        self.horizontalScrollBar().valueChanged.connect(self._line_area.update)
        # The code background is a paint-only decoration, so it is rebuilt for
        # the visible lines alone and refreshed whenever the viewport moves.
        self.verticalScrollBar().valueChanged.connect(self._update_code_backgrounds)
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
        # A taller viewport can expose code lines that had no tint yet.
        self._update_code_backgrounds()
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
        # Every paragraph is affected, not just the edited ones.
        self._needs_full_pass = True
        self.apply_directions()
        self.direction_changed.emit(mode)

    def _note_contents_change(self, position: int, removed: int, added: int):
        """Remember which paragraphs an edit touched.

        Ignored while we are applying our own block formats: those blocks are
        already being handled by the pass that triggered them.
        """
        if self._formatting:
            return
        document = self.document()
        # The signal fires *after* the edit, so only ``added`` still maps to
        # live text — ``removed`` counts characters that no longer exist and
        # would run the end position past the document, where findBlock
        # returns an invalid block whose number is -1.
        limit = max(0, document.characterCount() - 1)
        first = document.findBlock(min(position, limit)).blockNumber()
        last = document.findBlock(min(position + added, limit)).blockNumber()
        if self._dirty_last < self._dirty_first:
            self._dirty_first, self._dirty_last = first, last
        else:
            self._dirty_first = min(self._dirty_first, first)
            self._dirty_last = max(self._dirty_last, last)

    def _schedule_refresh(self):
        if not self._formatting:
            self._refresh_timer.start()

    def _refresh_layout(self):
        """Single pass: scan code blocks once, then reuse for directions."""
        # A change to which lines are code can flip the direction of a
        # paragraph far away from the edit (typing ``` opens a fence over the
        # rest of the file), so that case still needs the whole document.
        code_changed = self.refresh_code_blocks()
        self.apply_directions(only_dirty=not code_changed)

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

    def apply_directions(self, only_dirty: bool = False):
        """Re-apply per-paragraph direction.

        By default every paragraph is visited. ``only_dirty`` restricts the
        pass to the paragraphs an edit actually touched, which is what makes
        typing in a large document independent of its size.
        """
        if self._formatting:
            return
        document = self.document()
        partial = only_dirty and not self._needs_full_pass
        if partial:
            first = max(0, self._dirty_first)
            last = min(self._dirty_last, document.blockCount() - 1)
            if last < first:
                self._dirty_first, self._dirty_last = 0, -1
                return
        else:
            first, last = 0, document.blockCount() - 1

        self._formatting = True
        was_modified = document.isModified()
        # Reuse the line set computed by refresh_code_blocks rather than
        # flattening the blocks again.
        code_lines = self._code_line_set
        # One edit block so the whole pass is a single undo command, which
        # the undo/redo overrides below can then skip over transparently.
        changed = False
        guard = QTextCursor(document)
        guard.beginEditBlock()
        try:
            block = document.findBlockByNumber(first)
            while block.isValid() and block.blockNumber() <= last:
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
            self._dirty_first, self._dirty_last = 0, -1
            self._needs_full_pass = False
        # Relayouting is expensive on large files, so it is skipped entirely on
        # the common typing path where no paragraph changed direction — and
        # confined to the paragraphs actually visited when one did.
        if changed:
            start_block = document.findBlockByNumber(first)
            end_block = document.findBlockByNumber(last)
            if start_block.isValid() and end_block.isValid():
                start = start_block.position()
                document.markContentsDirty(
                    start, end_block.position() + end_block.length() - start
                )
            else:
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

    def refresh_code_blocks(self, text: str | None = None) -> bool:
        """Rescan for ``` fenced blocks.

        Returns whether the set of code lines changed — the caller uses that
        to decide if paragraphs outside the edit need re-evaluating, since a
        fence flips everything after it.
        """
        if text is None:
            text = self.toPlainText()
        new_code_lines = fenced_code_lines(text)
        changed = new_code_lines != self._code_line_set
        self._code_line_set = new_code_lines
        self._update_code_backgrounds()
        if changed and self.markdown_highlighter is not None:
            was_formatting = self._formatting
            self._formatting = True
            try:
                self.markdown_highlighter.rehighlight()
            finally:
                self._formatting = was_formatting
        return changed

    def _update_code_backgrounds(self):
        """Tint the code lines currently on screen.

        This is a paint-only decoration — the monospace font that actually
        affects layout is applied per block by MarkdownHighlighter, so
        restricting the tint to the viewport is safe and keeps the cost
        proportional to the window rather than to the file.
        """
        if not self._code_line_set:
            if self.extraSelections():
                self.setExtraSelections([])
            return

        document = self.document()
        background = QColor("#eef2f9" if current_is_light() else "#2a2b36")
        viewport_bottom = self.viewport().height()
        selections: list[QTextEdit.ExtraSelection] = []
        block = self.cursorForPosition(QPoint(0, 0)).block()
        while block.isValid():
            if self.cursorRect(QTextCursor(block)).top() > viewport_bottom:
                break
            if block.isVisible() and block.blockNumber() in self._code_line_set:
                selection = QTextEdit.ExtraSelection()
                selection.cursor = QTextCursor(block)
                selection.cursor.clearSelection()
                selection.format.setProperty(
                    QTextFormat.Property.FullWidthSelection, True
                )
                selection.format.setBackground(background)
                selections.append(selection)
            block = block.next()
        self.setExtraSelections(selections)

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
        # Loading a document replaces everything, so nothing carries over from
        # the previous content and the first pass must visit every paragraph.
        self._needs_full_pass = True
        self.refresh_code_blocks(text)
        self.apply_directions()
