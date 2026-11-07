"""Markdown tables, shown as a grid and edited a cell at a time.

The file keeps its "| a | b |" lines. On screen those lines are made
invisible and each row is given the height its cells need, then the grid is
painted over the space the rows reserve — the same trick the checkbox and the
date badge already use. Clicking a cell opens a one-line editor on top of it;
Tab moves on, and Tab in the last cell adds a row. Every change is one edit
to the document, so Ctrl+Z undoes it.
"""
import re

from PyQt6.QtCore import QLineF, QPoint, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QPainter,
    QPen,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextOption,
)
from PyQt6.QtWidgets import QLineEdit

from core import tables
from core.rtl_detector import detect_direction
from ui.markdown_highlighter import RULE_RE
from ui.styles import current_palette

PAD_X = 10
PAD_Y = 6
MIN_COL = 70
HIDDEN_PT = 1.0
SAFETY_PX = 2


class CellEditor(QLineEdit):
    """The one-line editor that sits on top of a cell while it is edited."""

    move = pyqtSignal(str)

    def focusNextPrevChild(self, forward: bool) -> bool:
        # Tab and Shift+Tab are consumed by focus handling before they reach
        # keyPressEvent, so they are caught here.
        self.move.emit("next" if forward else "prev")
        return True

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Down):
            self.move.emit("down")
        elif key == Qt.Key.Key_Up:
            self.move.emit("up")
        elif key == Qt.Key.Key_Escape:
            self.move.emit("cancel")
        else:
            super().keyPressEvent(event)


class RunLayout:
    """Column widths, row heights and cell text for one table."""

    def __init__(self, rows, width, font, rtl, theme, direction_of):
        self.rtl = rtl
        self.rows = rows  # [(block_number, text)]
        self.separator_at = {
            i for i, (_n, text) in enumerate(rows) if tables.is_separator(text)
        }
        self.has_header = len(rows) > 1 and 1 in self.separator_at
        self.cells = [tables.split_cells(text) for _n, text in rows]
        body = [i for i in range(len(rows)) if i not in self.separator_at]
        self.ncols = max((len(self.cells[i]) for i in body), default=1)
        self.aligns = (
            tables.column_alignments(rows[1][1]) if self.has_header else []
        )

        self.docs: dict[tuple[int, int], QTextDocument] = {}
        natural = [0.0] * self.ncols
        for i in body:
            for c in range(self.ncols):
                text = self.cells[i][c] if c < len(self.cells[i]) else ""
                doc = self._make_doc(
                    text, self.has_header and i == 0, font, theme, direction_of
                )
                doc.setTextWidth(-1)
                natural[c] = max(natural[c], doc.idealWidth() + 2 * PAD_X)
                self.docs[(i, c)] = doc

        # The narrowest a column can be is its longest unbreakable word; the
        # rest of the width is shared out by how much more each column wants.
        metrics = QFontMetricsF(font)
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setPointSizeF(font.pointSizeF() if font.pointSizeF() > 0 else 10.0)
        code_metrics = QFontMetricsF(mono)
        smallest = [2 * PAD_X + 10.0] * self.ncols
        for i in body:
            for c in range(self.ncols):
                text = self.cells[i][c] if c < len(self.cells[i]) else ""
                for code in re.findall(r"`([^`]+)`", text):
                    # Code is set in a wider monospace face than the body.
                    smallest[c] = max(
                        smallest[c], code_metrics.horizontalAdvance(code) + 2 * PAD_X
                    )
                plain = re.sub(r"`[^`]*`", " ", tables.BREAK_RE.sub(" ", text))
                plain = plain.replace("**", "")
                for word in plain.split():
                    smallest[c] = max(
                        smallest[c], metrics.horizontalAdvance(word) + 2 * PAD_X
                    )
        smallest = [min(low, high) for low, high in zip(smallest, natural)]

        total = sum(natural) or 1.0
        if total <= width:
            # Fill the page: a table narrower than the text above it looks
            # unfinished.
            self.col_widths = [w * width / total for w in natural]
        elif sum(smallest) >= width:
            self.col_widths = [w * width / sum(smallest) for w in smallest]
        else:
            spare = width - sum(smallest)
            wanting = [n - m for n, m in zip(natural, smallest)]
            share = sum(wanting) or 1.0
            self.col_widths = [
                m + spare * w / share for m, w in zip(smallest, wanting)
            ]
        self.total_width = sum(self.col_widths)

        line = QFontMetricsF(font).lineSpacing()
        self.row_heights: list[float] = []
        for i in range(len(rows)):
            if i in self.separator_at:
                self.row_heights.append(HIDDEN_PT)
                continue
            tallest = line
            for c in range(self.ncols):
                doc = self.docs[(i, c)]
                doc.setTextWidth(max(10.0, self.col_widths[c] - 2 * PAD_X))
                tallest = max(tallest, doc.size().height())
            self.row_heights.append(tallest + 2 * PAD_Y + SAFETY_PX)

    @staticmethod
    def _make_doc(text, bold, font, theme, direction_of):
        doc = QTextDocument()
        doc.setDefaultFont(font)
        doc.setDocumentMargin(0)
        option = QTextOption()
        rtl = direction_of(text) == "rtl"
        option.setTextDirection(
            Qt.LayoutDirection.RightToLeft if rtl else Qt.LayoutDirection.LeftToRight
        )
        option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        doc.setDefaultTextOption(option)
        doc.setDefaultStyleSheet(
            "code { font-family: Consolas; background-color: %s; }" % theme["hover"]
        )
        html = tables.cell_html(text)
        if bold:
            html = "<b>%s</b>" % html
        doc.setHtml('<span style="color:%s">%s</span>' % (theme["text"], html))
        return doc

    def column_x(self, origin: float) -> list[float]:
        """Left edge of every logical column, mirrored for a right-to-left table."""
        edges = []
        x = origin
        order = (
            range(self.ncols - 1, -1, -1) if self.rtl else range(self.ncols)
        )
        positions = {}
        for c in order:
            positions[c] = x
            x += self.col_widths[c]
        for c in range(self.ncols):
            edges.append(positions[c])
        return edges


class TableSupport:
    """Everything the editor does about tables, kept out of editor.py."""

    def __init__(self, editor):
        self.editor = editor
        self._cache: dict[int, tuple[tuple, RunLayout]] = {}
        self._applied: dict[int, tuple] = {}
        self._environment = None
        self._target: tuple[int, int] | None = None
        self.edit: CellEditor | None = None
        self._timer = QTimer(editor, singleShot=True, interval=60)
        self._timer.timeout.connect(self.refresh)

    # Finding tables

    @staticmethod
    def run_of(block):
        if not block.isValid() or not tables.is_row(block.text()):
            return []
        first = block
        while first.previous().isValid() and tables.is_row(first.previous().text()):
            first = first.previous()
        run = []
        current = first
        while current.isValid() and tables.is_row(current.text()):
            run.append(current)
            current = current.next()
        return run

    def _width(self) -> float:
        margin = self.editor.document().documentMargin()
        return max(200.0, self.editor.viewport().width() - 2 * margin)

    def _signature(self, run) -> tuple:
        font = self.editor.font()
        return (
            tuple(b.text() for b in run),
            int(self._width()),
            font.pointSizeF(),
            font.family(),
            self.editor.direction_mode,
            current_palette()["text"],
        )

    def layout_of(self, run) -> RunLayout:
        key = run[0].blockNumber()
        signature = self._signature(run)
        cached = self._cache.get(key)
        if cached and cached[0] == signature:
            return cached[1]
        header_text = " ".join(tables.split_cells(run[0].text()))
        rtl = self.editor._direction_for_text(header_text) == "rtl"
        layout = RunLayout(
            [(b.blockNumber(), b.text()) for b in run],
            self._width(),
            self.editor.font(),
            rtl,
            current_palette(),
            self.editor._direction_for_text,
        )
        self._cache[key] = (signature, layout)
        return layout

    # Hiding the raw text (called by the highlighter)

    def style_row(self, highlighter, block, text):
        """Make the row's text invisible and give its line the row's height."""
        run = self.run_of(block)
        if not run:
            return False
        layout = self.layout_of(run)
        index = block.blockNumber() - run[0].blockNumber()
        hidden = QTextCharFormat()
        hidden.setForeground(QColor(0, 0, 0, 0))
        hidden.setFontPointSize(HIDDEN_PT)
        highlighter.setFormat(0, len(text), hidden)
        if index not in layout.separator_at and text:
            font = self.editor.font()
            point = font.pointSizeF() if font.pointSizeF() > 0 else 10.0
            pixels_per_point = QFontMetricsF(font).lineSpacing() / point
            tall = QTextCharFormat(hidden)
            tall.setFontPointSize(
                max(HIDDEN_PT, layout.row_heights[index] / pixels_per_point)
            )
            highlighter.setFormat(0, 1, tall)
        return True

    # Keeping the row heights current

    def schedule(self):
        self._timer.start()

    def refresh(self):
        highlighter = self.editor.markdown_highlighter
        if highlighter is None:
            return
        self._environment = (self.editor.viewport().width(), self.editor.font().pointSizeF())
        document = self.editor.document()
        seen = set()
        block = document.begin()
        while block.isValid():
            if tables.is_row(block.text()):
                run = self.run_of(block)
                key = run[0].blockNumber()
                seen.add(key)
                signature = self._signature(run)
                if self._applied.get(key) != signature:
                    self._applied[key] = signature
                    for member in run:
                        highlighter.rehighlightBlock(member)
                block = run[-1].next()
            else:
                block = block.next()
        for key in list(self._applied):
            if key not in seen:
                del self._applied[key]
                self._cache.pop(key, None)
        self.editor.viewport().update()

    def check_stale(self):
        environment = (
            self.editor.viewport().width(),
            self.editor.font().pointSizeF(),
        )
        if environment != self._environment:
            self._environment = environment
            self.schedule()

    # Painting

    def _origin(self, layout: RunLayout) -> float:
        margin = self.editor.document().documentMargin()
        offset = -self.editor.horizontalScrollBar().value()
        if layout.rtl:
            return (
                self.editor.viewport().width()
                - margin
                - layout.total_width
                + offset
            )
        return margin + offset

    def _row_rect(self, block):
        rect = self.editor.document().documentLayout().blockBoundingRect(block)
        return rect.translated(0, -self.editor.verticalScrollBar().value())

    def paint(self, painter: QPainter, update_rect):
        editor = self.editor
        theme = current_palette()
        border = QColor(theme["border"])
        header_fill = QColor(theme["surface_alt"])
        block = editor.cursorForPosition(QPoint(0, update_rect.top())).block()
        painted = set()
        while block.isValid():
            rect = self._row_rect(block)
            if rect.top() > update_rect.bottom():
                break
            if tables.is_row(block.text()):
                run = self.run_of(block)
                key = run[0].blockNumber()
                if key not in painted:
                    painted.add(key)
                    self._paint_run(painter, run, border, header_fill)
                block = run[-1].next()
                continue
            if RULE_RE.match(block.text()):
                self._paint_rule(painter, rect, border)
            block = block.next()

    def _paint_rule(self, painter, rect, border):
        margin = self.editor.document().documentMargin()
        y = rect.top() + rect.height() / 2
        painter.save()
        painter.setPen(QPen(border, 1.0))
        painter.drawLine(QLineF(margin, y, self.editor.viewport().width() - margin, y))
        painter.restore()

    def _paint_run(self, painter, run, border, header_fill):
        layout = self.layout_of(run)
        origin = self._origin(layout)
        columns = layout.column_x(origin)
        top = self._row_rect(run[0]).top()
        bottom = self._row_rect(run[-1]).bottom()
        outer = QRectF(origin, top, layout.total_width, bottom - top)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if layout.has_header:
            head = self._row_rect(run[0])
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(header_fill)
            painter.drawRect(QRectF(origin, head.top(), layout.total_width, head.height()))

        painter.setPen(QPen(border, 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for index, member in enumerate(run):
            if index in layout.separator_at:
                continue
            rect = self._row_rect(member)
            painter.setPen(QPen(border, 1.0))
            painter.drawLine(QLineF(outer.left(), rect.bottom(), outer.right(), rect.bottom()))
            for c in range(layout.ncols):
                doc = layout.docs[(index, c)]
                painter.save()
                painter.translate(columns[c] + PAD_X, rect.top() + PAD_Y)
                doc.drawContents(
                    painter,
                    QRectF(0, 0, layout.col_widths[c] - 2 * PAD_X, rect.height()),
                )
                painter.restore()
        for c in range(layout.ncols):
            x = columns[c]
            for edge in (x, x + layout.col_widths[c]):
                painter.setPen(QPen(border, 1.0))
                painter.drawLine(QLineF(edge, top, edge, bottom))
        painter.setPen(QPen(border, 1.0))
        painter.drawRect(outer)
        painter.restore()

    # Finding a cell

    def cell_at(self, point):
        """(block_number, column) under a viewport point, or None."""
        block = self.editor.cursorForPosition(point).block()
        run = self.run_of(block)
        if not run:
            return None
        rect = self._row_rect(block)
        if not (rect.top() <= point.y() <= rect.bottom()):
            return None
        layout = self.layout_of(run)
        index = block.blockNumber() - run[0].blockNumber()
        if index in layout.separator_at:
            return None
        columns = layout.column_x(self._origin(layout))
        for c in range(layout.ncols):
            if columns[c] <= point.x() <= columns[c] + layout.col_widths[c]:
                return block.blockNumber(), c
        return None

    def cell_rect(self, block, column):
        run = self.run_of(block)
        layout = self.layout_of(run)
        columns = layout.column_x(self._origin(layout))
        rect = self._row_rect(block)
        return QRectF(columns[column], rect.top(), layout.col_widths[column], rect.height())

    # Editing a cell

    def _ensure_editor(self) -> CellEditor:
        if self.edit is None:
            self.edit = CellEditor(self.editor.viewport())
            self.edit.move.connect(self._on_move)
            self.edit.editingFinished.connect(self.commit)
            self.edit.hide()
        return self.edit

    def editing(self) -> bool:
        return self._target is not None and self.edit is not None and self.edit.isVisible()

    def open_cell(self, block_number: int, column: int):
        self.commit()
        block = self.editor.document().findBlockByNumber(block_number)
        if not block.isValid() or not tables.is_row(block.text()):
            return
        run = self.run_of(block)
        layout = self.layout_of(run)
        if (block_number - run[0].blockNumber()) in layout.separator_at:
            return
        column = max(0, min(column, layout.ncols - 1))
        cells = tables.split_cells(block.text())
        text = cells[column] if column < len(cells) else ""

        edit = self._ensure_editor()
        palette = current_palette()
        edit.setStyleSheet(
            "QLineEdit { background: %s; color: %s; border: 1px solid %s;"
            " border-radius: 4px; padding: 0 6px; }"
            % (palette["window"], palette["text"], palette["accent"])
        )
        edit.setFont(self.editor.font())
        rtl = self.editor._direction_for_text(text or " ".join(cells)) == "rtl"
        edit.setLayoutDirection(
            Qt.LayoutDirection.RightToLeft if rtl else Qt.LayoutDirection.LeftToRight
        )
        edit.setText(text)
        edit.setGeometry(self.cell_rect(block, column).toRect().adjusted(1, 1, -1, -1))
        self._target = (block_number, column)
        edit.show()
        edit.setFocus()
        edit.deselect()
        edit.setCursorPosition(len(text))

    def reposition(self):
        """Keep the editor on its cell while the page scrolls or resizes."""
        if not self.editing():
            return
        block = self.editor.document().findBlockByNumber(self._target[0])
        if block.isValid() and tables.is_row(block.text()):
            self.edit.setGeometry(
                self.cell_rect(block, self._target[1]).toRect().adjusted(1, 1, -1, -1)
            )

    def commit(self):
        """Write the cell back to its line. One undo step; nothing if unchanged."""
        if self._target is None or self.edit is None:
            return
        block_number, column = self._target
        self._target = None
        text = self.edit.text()
        self.edit.hide()
        block = self.editor.document().findBlockByNumber(block_number)
        if not block.isValid() or not tables.is_row(block.text()):
            return
        cells = tables.split_cells(block.text())
        before = cells[column] if column < len(cells) else ""
        cleaned = text.replace("|", "/").strip()
        if cleaned == before:
            return
        new_line = tables.replace_cell(block.text(), column, text)
        self._replace_block_text(block, new_line)

    def _replace_block_text(self, block, new_text):
        cursor = QTextCursor(block)
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        cursor.movePosition(
            QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor
        )
        cursor.beginEditBlock()
        try:
            cursor.insertText(new_text)
        finally:
            cursor.endEditBlock()

    def _rows_of(self, block):
        run = self.run_of(block)
        layout = self.layout_of(run)
        rows = [
            m for i, m in enumerate(run) if i not in layout.separator_at
        ]
        return run, layout, rows

    def _on_move(self, how: str):
        if self._target is None:
            return
        block_number, column = self._target
        self.commit()
        block = self.editor.document().findBlockByNumber(block_number)
        if not block.isValid() or not tables.is_row(block.text()):
            return
        if how == "cancel":
            self.editor.setFocus()
            return
        run, layout, rows = self._rows_of(block)
        index = [r.blockNumber() for r in rows].index(block.blockNumber())
        if how == "next":
            if column + 1 < layout.ncols:
                self.open_cell(block.blockNumber(), column + 1)
            elif index + 1 < len(rows):
                self.open_cell(rows[index + 1].blockNumber(), 0)
            else:
                self.add_row_after(rows[-1])
                last = self.editor.document().findBlockByNumber(
                    rows[-1].blockNumber() + 1
                )
                self.open_cell(last.blockNumber(), 0)
        elif how == "prev":
            if column > 0:
                self.open_cell(block.blockNumber(), column - 1)
            elif index > 0:
                self.open_cell(rows[index - 1].blockNumber(), layout.ncols - 1)
        elif how == "down":
            if index + 1 < len(rows):
                self.open_cell(rows[index + 1].blockNumber(), column)
            else:
                self.leave(run, after=True)
        elif how == "up":
            if index > 0:
                self.open_cell(rows[index - 1].blockNumber(), column)
            else:
                self.leave(run, after=False)

    def leave(self, run, after: bool):
        """Hand the keyboard back to the text, below or above the table."""
        editor = self.editor
        document = editor.document()
        cursor = QTextCursor(document)
        if after:
            following = run[-1].next()
            if not following.isValid():
                cursor.setPosition(run[-1].position() + len(run[-1].text()))
                cursor.insertText("\n")
                following = run[-1].next()
            cursor.setPosition(following.position())
        else:
            previous = run[0].previous()
            if not previous.isValid():
                cursor.setPosition(run[0].position())
                cursor.insertText("\n")
                previous = run[0].previous()
            cursor.setPosition(previous.position() + len(previous.text()))
        editor.setTextCursor(cursor)
        editor.setFocus()

    # Changing the table's shape

    def add_row_after(self, block):
        run = self.run_of(block)
        ncols = self.layout_of(run).ncols
        cursor = QTextCursor(block)
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        cursor.beginEditBlock()
        try:
            cursor.insertText("\n" + tables.empty_row(ncols))
        finally:
            cursor.endEditBlock()

    def delete_row(self, block):
        run = self.run_of(block)
        layout = self.layout_of(run)
        index = block.blockNumber() - run[0].blockNumber()
        if index in layout.separator_at or (layout.has_header and index == 0):
            return
        cursor = QTextCursor(block)
        cursor.beginEditBlock()
        try:
            following = block.next()
            if following.isValid():
                cursor.setPosition(block.position())
                cursor.setPosition(following.position(), QTextCursor.MoveMode.KeepAnchor)
            else:
                previous = block.previous()
                cursor.setPosition(previous.position() + len(previous.text()))
                cursor.setPosition(
                    block.position() + len(block.text()), QTextCursor.MoveMode.KeepAnchor
                )
            cursor.removeSelectedText()
        finally:
            cursor.endEditBlock()

    def _replace_run(self, run, lines):
        cursor = QTextCursor(run[0])
        cursor.setPosition(run[0].position())
        cursor.setPosition(
            run[-1].position() + len(run[-1].text()), QTextCursor.MoveMode.KeepAnchor
        )
        cursor.beginEditBlock()
        try:
            cursor.insertText("\n".join(lines))
        finally:
            cursor.endEditBlock()

    def add_column(self, block):
        run = self.run_of(block)
        self._replace_run(run, tables.add_column([b.text() for b in run]))

    def delete_column(self, block, column):
        run = self.run_of(block)
        self._replace_run(run, tables.remove_column([b.text() for b in run], column))

    def insert_table(self, columns: int = 3, body_rows: int = 2):
        """A new empty table at the cursor, with its first cell ready to type in."""
        editor = self.editor
        cursor = editor.textCursor()
        cursor.beginEditBlock()
        try:
            cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
            if cursor.block().text().strip():
                cursor.insertText("\n\n")
            start = cursor.blockNumber()
            cursor.insertText("\n".join(tables.new_table(columns, body_rows)))
            cursor.insertText("\n")
        finally:
            cursor.endEditBlock()
        editor.setTextCursor(cursor)
        QTimer.singleShot(0, lambda: self.open_cell(start, 0))

    # Entering a table with the arrow keys

    def enter_at_cursor(self):
        """The text cursor moved onto a hidden row: open its first cell."""
        if self.editing():
            return
        block = self.editor.textCursor().block()
        if not tables.is_row(block.text()) or not self.editor.hasFocus():
            return
        run = self.run_of(block)
        layout = self.layout_of(run)
        index = block.blockNumber() - run[0].blockNumber()
        if index in layout.separator_at:
            index += 1
            if index >= len(run):
                return
            block = run[index]
        QTimer.singleShot(0, lambda: self.open_cell(block.blockNumber(), 0))
