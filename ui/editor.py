from PyQt6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, QStringListModel, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QFontMetrics,
    QFontMetricsF,
    QColor,
    QFont,
    QPainter,
    QPen,
    QTextBlockFormat,
    QTextCursor,
)
from PyQt6.QtWidgets import QCompleter, QTextEdit, QWidget

from core.list_editing import (
    display_number_marker,
    indent_list_line,
    outdent_list_line,
    parse_list_item,
)
from core.jalali import format_pill, to_persian_digits
from core.rtl_detector import detect_direction
from core.formatting import HEADING_RE
from core.links import LINK_RE
from core.tasks import parse_task, stamp_span
from core.when import day_label
from ui.kit import col, draw_checkbox, draw_icon, draw_text, font as design_font, rounded, text_width, tint
from ui.styles import current_palette

# The design's text column, in CSS pixels at the 14.5px body size: a row per
# line with 2px above and below, a 26px line-number column 14px in from the
# right edge with a 14px gap before the text, 40px of room on the left,
# 34px above the first line and 60 below the last.
BODY_PX = 14.5
ROW_PAD = 2
NUMBER_COLUMN = 26
NUMBER_EDGE = 14
NUMBER_GAP = 14
LEFT_ROOM = 40
DOC_TOP, DOC_BOTTOM = 34, 60
TEXT_MAX = 860
FOCUS_WIDTH, FOCUS_PAD, FOCUS_TOP, FOCUS_BOTTOM = 780, 24, 72, 120
# (size, CSS line-height, extra top padding) per heading level, at 14.5px.
HEADING_SPEC = {1: (27, 1.6, 0), 2: (17, 1.9, 6), 3: (15.5, 1.9, 4)}


class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.setObjectName("lineNumberArea")

    def sizeHint(self):
        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event):  # noqa: D401 — delegates to the editor
        self.editor.paint_line_number_area(event)


class MarginArea(QWidget):
    """The empty room on the far side of the text: it only carries the
    current line's highlight, which in the design spans the whole row."""

    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def paintEvent(self, event):  # noqa: D401 — delegates to the editor
        self.editor.paint_margin_area(self)


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
# How far the date capsule is grown around the stamp's own glyphs. Kept
# small: the only room it has is the space before the "@".
STAMP_PAD_X = 4
STAMP_TEXT_SCALE = 0.88
STAMP_PAD_Y = 1


class SmartEditor(QTextEdit):
    """Plain-text editor with line numbers and paragraph-level bidi direction."""

    zoom_requested = pyqtSignal(int)
    direction_changed = pyqtSignal(str)
    link_clicked = pyqtSignal(str)

    # Windows scan codes for the left and right Shift keys. Pressing the
    # right Shift while holding Ctrl switches to RTL, the left one to LTR —
    # the same convention Windows itself uses in text fields.
    _SHIFT_SCANCODES = {42: "ltr", 54: "rtl"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptRichText(False)
        self.direction_mode = "auto"
        self._formatting = False
        self._line_numbers_visible = True
        self.markdown_highlighter = None
        self._hovered_checkbox_block: int | None = None
        self._marker_cache: list | None = None
        self._stamp_cache: list | None = None
        # Paragraphs touched since the last layout pass. Only these need their
        # direction re-applied; every other block already carries the right
        # format, and Qt keeps that format attached to the block itself rather
        # than to its number. An empty range means "nothing to do".
        self._dirty_first = 0
        self._dirty_last = -1
        self._needs_full_pass = True
        self._line_area = LineNumberArea(self)
        self._margin_area = MarginArea(self)
        self._focus_layout = False
        self._near_pad = NUMBER_EDGE
        self._far_pad = LEFT_ROOM
        self._row_metrics: dict = {}
        self._link_resolver = lambda target: True
        self._link_names = lambda: []
        self._link_cache: list | None = None
        self._completer: QCompleter | None = None
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
        self.textChanged.connect(self._schedule_refresh)
        self.textChanged.connect(self._line_area.update)
        self.cursorPositionChanged.connect(self._cursor_context_changed)
        self.cursorPositionChanged.connect(self._margin_area.update)
        self.cursorPositionChanged.connect(self.viewport().update)
        self.verticalScrollBar().valueChanged.connect(self._margin_area.update)
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
        """The near-side room: the number column plus its edge and gap."""
        if not self._line_numbers_visible:
            return round(self._near_pad)
        return round(self._near_pad + NUMBER_COLUMN + NUMBER_GAP)

    def _is_rtl_document(self) -> bool:
        return self.direction_mode != "ltr"

    def _update_line_area_width(self, width: int | None = None, relayout: bool = True):
        """Lay out the page: numbers on the near side (right, for RTL), the
        design's 40px room on the far side, 34px above and 60px below — or
        the 780px centred column of focus mode."""
        before = self.viewportMargins()
        width = max(1, width if width is not None else self.contentsRect().width())
        if self._focus_layout:
            inner = min(FOCUS_WIDTH, width)
            side = (width - inner) / 2
            self._near_pad = side + FOCUS_PAD
            self._far_pad = side + FOCUS_PAD
            top, bottom = FOCUS_TOP, FOCUS_BOTTOM
            far = self._far_pad
        else:
            self._near_pad = NUMBER_EDGE
            self._far_pad = LEFT_ROOM
            top, bottom = DOC_TOP, DOC_BOTTOM
            far = max(LEFT_ROOM, width - self.line_number_area_width() - TEXT_MAX)
        near = self.line_number_area_width()
        if self._is_rtl_document():
            self.setViewportMargins(round(far), 0, near, 0)
        else:
            self.setViewportMargins(near, 0, round(far), 0)
        frame = self.document().rootFrame()
        fmt = frame.frameFormat()
        if (fmt.topMargin(), fmt.bottomMargin(), fmt.leftMargin(), fmt.rightMargin()) != (top, bottom, 0, 0):
            # A frame format change counts as an edit to Qt; it is layout,
            # not content, so the document must not turn «unsaved» over it.
            was_modified = self.document().isModified()
            self._formatting = True
            self.document().setDocumentMargin(0)
            fmt = frame.frameFormat()
            fmt.setTopMargin(top)
            fmt.setBottomMargin(bottom)
            fmt.setLeftMargin(0)
            fmt.setRightMargin(0)
            frame.setFrameFormat(fmt)
            self._formatting = False
            self.document().setModified(was_modified)
        self._place_side_areas()
        if relayout and self.viewportMargins() != before:
            # QTextEdit wraps to the viewport width only when it is resized
            # itself; a margin change narrows the viewport without that.
            from PyQt6.QtGui import QResizeEvent

            QTextEdit.resizeEvent(self, QResizeEvent(self.size(), self.size()))

    def _place_side_areas(self):
        content = self.contentsRect()
        margins = self.viewportMargins()
        if self._is_rtl_document():
            near = QRect(content.right() - margins.right() + 1, content.top(), margins.right(), content.height())
            far = QRect(content.left(), content.top(), margins.left(), content.height())
        else:
            near = QRect(content.left(), content.top(), margins.left(), content.height())
            far = QRect(content.right() - margins.right() + 1, content.top(), margins.right(), content.height())
        self._line_area.setGeometry(near)
        self._margin_area.setGeometry(far)

    def set_focus_layout(self, on: bool):
        self._focus_layout = on
        self._update_line_area_width()
        self.viewport().update()

    def set_link_resolver(self, resolver):
        """`resolver(target) -> bool`: does «[[target]]» name a real note?"""
        self._link_resolver = resolver
        if self.markdown_highlighter is not None:
            self.markdown_highlighter.rehighlight()
        self._link_cache = None
        self.viewport().update()

    def set_link_names(self, source):
        """`source() -> [str]`: note names offered after «[[»."""
        self._link_names = source

    def set_line_numbers_visible(self, visible: bool):
        self._line_numbers_visible = visible
        self._line_area.setVisible(visible)
        self._update_line_area_width()

    def resizeEvent(self, event):
        # Margins first, so the text wraps to the viewport it will really have.
        self._update_line_area_width(event.size().width() - 2 * self.frameWidth(), relayout=False)
        super().resizeEvent(event)
        self._invalidate_marker_cache()
        self._place_side_areas()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == event.Type.FontChange:
            # Row heights are derived from the font; every block needs them again.
            self._row_metrics.clear()
            self._needs_full_pass = True
            self.apply_directions()

    def _block_rect(self, block) -> QRectF:
        """A block's full row, margins included, in viewport coordinates."""
        rect = self.document().documentLayout().blockBoundingRect(block)
        return rect.translated(0, -self.verticalScrollBar().value())

    def _current_row(self) -> QRectF | None:
        block = self.textCursor().block()
        if not block.isValid() or self.textCursor().hasSelection():
            return None
        return self._block_rect(block)

    def paint_margin_area(self, area):
        painter = QPainter(area)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(area.rect(), col("window"))
        row = self._current_row()
        if row is not None:
            if self._is_rtl_document():
                rect = QRectF(self._far_pad, row.top(), area.width() - self._far_pad + 10, row.height())
            else:
                rect = QRectF(-10, row.top(), area.width() - self._far_pad + 10, row.height())
            rounded(painter, rect, 6, fill=col("current_line"))
        painter.end()

    def paint_line_number_area(self, event):
        """Persian line numbers at 11.5px in the design's 26px column, and the
        near end of the current line's highlight."""
        area = self._line_area
        painter = QPainter(area)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(area.rect(), col("window"))
        rtl = self._is_rtl_document()
        row = self._current_row()
        if row is not None:
            if rtl:
                rect = QRectF(-10, row.top(), area.width() - self._near_pad + 10, row.height())
            else:
                rect = QRectF(self._near_pad, row.top(), area.width() - self._near_pad + 10, row.height())
            rounded(painter, rect, 6, fill=col("current_line"))
        if not self._line_numbers_visible:
            painter.end()
            return
        number_font = design_font(11.5)
        colour = col("gutter")
        column_x = area.width() - self._near_pad - NUMBER_COLUMN if rtl else self._near_pad
        block = self.cursorForPosition(QPoint(0, 0)).block()
        bottom_limit = event.rect().bottom()
        while block.isValid():
            first_line = self.cursorRect(QTextCursor(block))
            if first_line.top() > bottom_limit:
                break
            if block.isVisible() and first_line.bottom() >= event.rect().top():
                draw_text(painter, QRectF(column_x, first_line.top(), NUMBER_COLUMN, first_line.height()),
                          to_persian_digits(str(block.blockNumber() + 1)), number_font, colour,
                          Qt.AlignmentFlag.AlignCenter, elide_text=False)
            block = block.next()
        painter.end()

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
        self.apply_directions(only_dirty=True)

    def _direction_for_text(self, text: str) -> str:
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
        top, bottom, distance = self._row_spacing(cursor.block().text())
        # Exact comparison: an `&` test passes as soon as the AlignAbsolute
        # bit matches, silently skipping the actual left/right realignment.
        if (
            current.layoutDirection() == expected_layout
            and current.alignment() == expected_alignment
            and current.leftMargin() == expected_left_margin
            and current.rightMargin() == expected_right_margin
            and abs(current.topMargin() - top) < 0.01
            and abs(current.bottomMargin() - bottom) < 0.01
            and abs(current.lineHeight() - distance) < 0.01
            and current.lineHeightType() == 4
        ):
            return False
        fmt = QTextBlockFormat(current)
        fmt.setLayoutDirection(expected_layout)
        fmt.setAlignment(expected_alignment)
        fmt.setLeftMargin(expected_left_margin)
        fmt.setRightMargin(expected_right_margin)
        fmt.setTopMargin(top)
        fmt.setBottomMargin(bottom)
        fmt.setLineHeight(distance, 4)  # LineDistanceHeight
        cursor.setBlockFormat(fmt)
        return True

    def _body_px(self) -> float:
        return self.font().pointSizeF() / 0.75

    def _row_spacing(self, text: str) -> tuple[float, float, float]:
        """(top margin, bottom margin, extra line distance) for one block.

        The design sets every line as a row: CSS line-height 2 for body text
        (1.6 for a title, 1.9 for a section), 2px above and below, at least
        32px. Qt lays a line at the font's own height, so the difference is
        split above and below the first line and added between wrapped ones.
        """
        heading = HEADING_RE.match(text)
        level = len(heading.group(1)) if heading else 0
        base = self._body_px()
        key = (level, round(base, 2))
        cached = self._row_metrics.get(key)
        if cached is not None:
            return cached
        scale = base / BODY_PX
        if level in HEADING_SPEC:
            size, factor, extra = HEADING_SPEC[level]
            px, extra = size * scale, extra * scale
        else:
            px, factor, extra = base, 2.0, 0.0
        # A line is as tall as the tallest font it uses: Persian text falls
        # back to Vazirmatn, whose ascent and descent are well above Inter's.
        natural = 0.0
        for family in self.font().families() or [self.font().family()]:
            measured = QFont(self.font())
            measured.setFamilies([family])
            measured.setPointSizeF(px * 0.75)
            natural = max(natural, QFontMetricsF(measured).height())
        line = px * factor
        row = max(32 * scale, line + 2 * ROW_PAD * scale)
        spare = row - natural
        result = (spare / 2 + extra, spare / 2, line - natural)
        self._row_metrics[key] = result
        return result

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
                    self._direction_for_text(block.text()),
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

        popup = self._completer.popup() if self._completer else None
        if popup is not None and popup.isVisible() and event.key() in (
            Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Escape,
            Qt.Key.Key_Tab, Qt.Key.Key_Backtab,
        ):
            # The popup has the keyboard for these; let it pick or close.
            event.ignore()
            return

        if self._handle_list_key(event):
            event.accept()
            return

        if event.text() == "[" and self._text_before_cursor(1) == "[":
            cursor = self.textCursor()
            cursor.insertText("[]]")
            cursor.movePosition(QTextCursor.MoveOperation.PreviousCharacter, n=2)
            self.setTextCursor(cursor)
            self.show_link_completer()
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
        if popup is not None and popup.isVisible():
            self._update_completion_prefix()

    # «[[» suggestions

    def _text_before_cursor(self, count: int) -> str:
        cursor = self.textCursor()
        block_text = cursor.block().text()
        column = cursor.positionInBlock()
        return block_text[max(0, column - count):column]

    def _link_prefix(self) -> str | None:
        """What has been typed since the «[[» the caret sits after, if any."""
        cursor = self.textCursor()
        before = cursor.block().text()[:cursor.positionInBlock()]
        opening = before.rfind("[[")
        if opening < 0 or "]]" in before[opening:]:
            return None
        return before[opening + 2:]

    def show_link_completer(self):
        names = list(self._link_names())
        if not names:
            return
        if self._completer is None:
            self._completer = QCompleter(QStringListModel(names), self)
            self._completer.setWidget(self)
            self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            self._completer.setFilterMode(Qt.MatchFlag.MatchContains)
            self._completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
            self._completer.activated[str].connect(self._insert_link_name)
            popup = self._completer.popup()
            popup.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            popup.setFont(design_font(13))
        else:
            self._completer.model().setStringList(names)
        self._update_completion_prefix()

    def _update_completion_prefix(self):
        prefix = self._link_prefix()
        if prefix is None or self._completer is None:
            if self._completer is not None:
                self._completer.popup().hide()
            return
        self._completer.setCompletionPrefix(prefix)
        rect = self.cursorRect()
        rect.translate(self.viewport().pos())
        rect.setWidth(260)
        if self._is_rtl_document():
            rect.moveRight(self.cursorRect().right() + self.viewport().pos().x())
        self._completer.complete(rect)

    def _insert_link_name(self, name: str):
        prefix = self._link_prefix()
        if prefix is None:
            return
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.PreviousCharacter,
                            QTextCursor.MoveMode.KeepAnchor, len(prefix))
        cursor.insertText(name)
        if cursor.block().text()[cursor.positionInBlock():].startswith("]]"):
            cursor.movePosition(QTextCursor.MoveOperation.NextCharacter, n=2)
        self.setTextCursor(cursor)

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
        if cursor.hasSelection():
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
            if block.isVisible():
                item = parse_list_item(block.text())
                if item is not None:
                    markers.append((block, item, self._marker_rect(block, item)))
            block = block.next()
        self._marker_cache = markers
        yield from markers

    def _invalidate_marker_cache(self):
        self._marker_cache = None
        self._stamp_cache = None
        self._link_cache = None

    def _span_rect(self, block, start: int, end: int) -> QRect | None:
        """Screen rectangle covering one character range of a block.

        Every character boundary is measured, not just the two ends. A stamp
        is one logical run but bidi can split it into several visual ones —
        "@1405/06/02 10:00" on a right-to-left line puts the time on the far
        side of the date — and the two outer carets then bound only part of
        it. The union of all of them is the real box.
        """
        cursor = QTextCursor(block)
        base = block.position()

        # On a left-to-right line the stamp cannot be reordered, so the two
        # outer carets already bound it and the scan below is wasted work.
        if self._direction_for_text(block.text()) != "rtl":
            cursor.setPosition(base + start)
            first = self.cursorRect(cursor)
            cursor.setPosition(base + end)
            last = self.cursorRect(cursor)
            if first.top() != last.top() or first.left() == last.left():
                return None
            return QRect(
                min(first.left(), last.left()),
                first.top(),
                abs(last.left() - first.left()),
                first.height(),
            )

        left = top = height = None
        right = None
        for position in range(start, end + 1):
            cursor.setPosition(base + position)
            rect = self.cursorRect(cursor)
            if top is None:
                left = right = rect.left()
                top, height = rect.top(), rect.height()
                continue
            # Wrapped onto another visual line: stop at the first one, so a
            # capsule is never stretched down the page.
            if rect.top() != top:
                return None
            left = min(left, rect.left())
            right = max(right, rect.left())
        if top is None or right == left:
            return None
        return QRect(left, top, right - left, height)

    def _visible_stamps(self):
        """Yield (rect, label, overdue, done) for the date badges on screen.

        Cached exactly like the list markers, and for the same reason: the
        geometry only moves when the text, the scroll position or the font
        does, so a repaint on its own must not recompute it.
        """
        cached = self._stamp_cache
        if cached is not None:
            yield from cached
            return

        stamps = []
        block = self.cursorForPosition(QPoint(0, 0)).block()
        viewport_bottom = self.viewport().height()
        while block.isValid():
            top = self.cursorRect(QTextCursor(block)).top()
            if top > viewport_bottom:
                break
            if block.isVisible():
                text = block.text()
                span = stamp_span(text)
                if span is not None:
                    rect = self._span_rect(block, *span)
                    if rect is not None and rect.width() > 0:
                        task = parse_task(text)
                        stamps.append(
                            (
                                rect.adjusted(
                                    -STAMP_PAD_X,
                                    -STAMP_PAD_Y,
                                    STAMP_PAD_X,
                                    STAMP_PAD_Y,
                                ),
                                day_label(task.due.date())
                                if task and task.due
                                else "",
                                bool(task and task.overdue),
                                bool(task and task.done),
                            )
                        )
            block = block.next()
        self._stamp_cache = stamps
        yield from stamps

    def _checkbox_hit_rect(self, marker_rect: QRect) -> QRect:
        """Clickable area of a to-do checkbox, slightly larger than the box."""
        return marker_rect.adjusted(
            -CHECKBOX_HIT_PADDING,
            -CHECKBOX_HIT_PADDING,
            CHECKBOX_HIT_PADDING,
            CHECKBOX_HIT_PADDING,
        )

    def _paint_checkbox(self, painter, marker_rect, item, hovered, theme):
        """The design's box: 16px, radius 5, a 1.5px outline — or an accent
        square with a dark check."""
        centre = QPointF(marker_rect.center())
        border = col("accent") if hovered else col("box")
        draw_checkbox(painter, centre, 16, 5, item.checked, border=border)

    def _visible_links(self):
        """(rect, target, broken) for every «[[…]]» label on screen."""
        if self._link_cache is not None:
            return self._link_cache
        links = []
        block = self.cursorForPosition(QPoint(0, 0)).block()
        bottom = self.viewport().height()
        while block.isValid():
            if self.cursorRect(QTextCursor(block)).top() > bottom:
                break
            text = block.text()
            if block.isVisible() and "[[" in text:
                for match in LINK_RE.finditer(text):
                    start, end = match.span(2) if match.group(2) else match.span(1)
                    rect = self._span_rect(block, start, end)
                    if rect is not None and rect.width() > 0:
                        target = match.group(1).strip()
                        links.append((rect, target, not self._link_resolver(target)))
            block = block.next()
        self._link_cache = links
        return links

    def _link_chip(self, rect: QRect) -> QRectF:
        """Label rect grown into the design's chip: 7px each side, an 11px
        link icon and a 4px gap before the label (on the right, for RTL)."""
        extra = 4 + 11
        grow = QRectF(rect).adjusted(-7, -2, 7, 2)
        if self._is_rtl_document():
            return grow.adjusted(0, 0, extra, 0)
        return grow.adjusted(-extra, 0, 0, 0)

    def paintEvent(self, event):
        under = QPainter(self.viewport())
        under.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        row = self._current_row()
        if row is not None:
            under.save()
            # The row runs on into both side areas; round only the far ends.
            rounded(under, QRectF(-10, row.top(), self.viewport().width() + 20, row.height()),
                    6, fill=col("current_line"))
            under.restore()
        for rect, _target, broken in self._visible_links():
            chip = self._link_chip(rect)
            rounded(under, chip, 6, fill=tint("danger" if broken else "accent", 0.1 if broken else 0.12))
            icon_x = chip.right() - 7 - 11 if self._is_rtl_document() else chip.left() + 7
            draw_icon(under, "link", QRectF(icon_x, chip.center().y() - 5.5, 11, 11),
                      col("danger" if broken else "accent"), 1.7)
            if broken:
                pen = QPen(col("danger"), 1)
                pen.setStyle(Qt.PenStyle.DashLine)
                under.setPen(pen)
                under.drawLine(QPointF(chip.left() + 7, chip.bottom() - 1),
                               QPointF(chip.right() - 7, chip.bottom() - 1))
        under.end()

        super().paintEvent(event)

        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        theme = current_palette()

        # The date chip: the stamp's own characters are painted invisible by
        # the highlighter and this is drawn over the room they reserve, so
        # «@1405/07/03» reads as «امروز» while the file keeps plain text.
        chip_font = design_font(11.5 * self._body_px() / BODY_PX)
        for stamp_rect, label, overdue, _done in self._visible_stamps():
            if not stamp_rect.intersects(event.rect()) or not label:
                continue
            tone = "danger" if overdue else "accent"
            width = 8 + 11 + 5 + text_width(label, chip_font) + 8
            height = 22 * self._body_px() / BODY_PX
            # 11px from the task's last word, as the design's flex gap puts it;
            # the stamp's own room begins one space (~4px) after that word.
            inset = STAMP_PAD_X + 7 * self._body_px() / BODY_PX
            if self._is_rtl_document():
                chip = QRectF(stamp_rect.right() - inset - width, stamp_rect.center().y() - height / 2,
                              width, height)
                icon_x = chip.right() - 8 - 11
                text_rect = QRectF(chip.left() + 8, chip.top(), width - 16 - 11 - 5, height)
            else:
                chip = QRectF(stamp_rect.left() + inset, stamp_rect.center().y() - height / 2,
                              width, height)
                icon_x = chip.left() + 8
                text_rect = QRectF(chip.left() + 8 + 11 + 5, chip.top(), width - 16 - 11 - 5, height)
            rounded(painter, chip, 6, fill=tint(tone, 0.12))
            draw_icon(painter, "calendar_small", QRectF(icon_x, chip.center().y() - 5.5, 11, 11),
                      col(tone), 1.6)
            draw_text(painter, text_rect, label, chip_font, col(tone), Qt.AlignmentFlag.AlignCenter,
                      elide_text=False)

        scale = self._body_px() / BODY_PX
        for block, item, marker_rect in self._visible_list_markers():
            if not marker_rect.intersects(event.rect()):
                continue
            rtl = self._direction_for_text(block.text()) == "rtl"
            if item.kind == "bullet":
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(col("accent"))
                x = marker_rect.right() - 3 * scale if rtl else marker_rect.left() + 3 * scale
                painter.drawEllipse(QPointF(x, marker_rect.center().y()), 3 * scale, 3 * scale)
            elif item.kind == "numbered":
                painter.save()
                number_font = QFont(self.font())
                number_font.setBold(True)
                painter.setFont(number_font)
                painter.setPen(col("accent"))
                rtl = self._direction_for_text(block.text()) == "rtl"
                alignment = Qt.AlignmentFlag.AlignLeft if rtl else Qt.AlignmentFlag.AlignRight
                painter.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
                painter.drawText(marker_rect, int(alignment | Qt.AlignmentFlag.AlignVCenter),
                                 display_number_marker(item.marker, rtl))
                painter.restore()
            else:
                # The box sits in the first 20px of the marker's room.
                x = marker_rect.right() - 10 * scale if rtl else marker_rect.left() + 10 * scale
                hovered = block.blockNumber() == self._hovered_checkbox_block
                draw_checkbox(painter, QPointF(x, marker_rect.center().y()), 16 * scale, 5 * scale,
                              item.checked, border=col("accent" if hovered else "box"),
                              check_size=11 * scale)
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

    def _link_at(self, point) -> str | None:
        for rect, target, _broken in self._visible_links():
            if self._link_chip(rect).contains(QPointF(point)):
                return target
        return None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not event.modifiers():
            target = self._link_at(event.position().toPoint())
            if target is not None:
                self.link_clicked.emit(target)
                event.accept()
                return
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
        on_link = not event.buttons() and self._link_at(event.position().toPoint()) is not None
        self.viewport().setCursor(
            Qt.CursorShape.PointingHandCursor
            if toggle is not None or on_link
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
        self.apply_directions()
