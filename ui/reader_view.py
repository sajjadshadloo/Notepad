"""Reading view: the whole note set as a page, tables and all.

The editor already draws headings, bold, lists and tasks in place, but some
Markdown has no sensible live form — a pipe table, `code`, a [text](url)
link, a quote. Notes written by agents are full of tables, and read raw they
are a wall of pipes. This view renders the same text with Qt's own Markdown
reader and then restyles the result to match the editor's page.

It only reads. The file is never touched, and edits go back through the
editor (Ctrl+E switches).
"""
import re

from PyQt6.QtCore import QPointF, QRectF, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QDesktopServices,
    QFont,
    QImage,
    QPainter,
    QPen,
    QPolygonF,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextFormat,
    QTextFrameFormat,
    QTextImageFormat,
    QTextLength,
    QTextTable,
)
from PyQt6.QtWidgets import QTextBrowser

from core.formatting import BULLET_RE, TODO_RE
from core.links import LINK_RE
from core.rtl_detector import detect_direction
from core.tasks import stamp_span
from ui.editor import DOC_BOTTOM, DOC_TOP, FOCUS_BOTTOM, FOCUS_TOP, FOCUS_WIDTH, LEFT_ROOM, TEXT_MAX
from ui.markdown_highlighter import HEADING_SCALE, HEADING_WEIGHT
from ui.styles import current_palette

# «[[target|label]]» becomes a link Qt can follow; the scheme marks it as a
# note of ours rather than a web address.
NOTE_SCHEME = "note"
LINE_HEIGHT = 155  # percent: Persian needs more air than Latin text
PARAGRAPH_GAP = 10
CELL_PADDING = 8

_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_CELL_SPLIT_RE = re.compile(r"(?<!\\)\|")

# Tasks are drawn as a box and the words, as in the editor. Qt's own task
# markers sit on top of the first word in a right-to-left paragraph, and the
# ballot-box characters are missing from both of the app's fonts, so the box
# is a small picture the document carries (see _marker_image). Qt's Markdown
# reader drops an image it cannot load yet, so the text carries a ballot box
# as a placeholder and _place_boxes swaps in the picture afterwards.
OPEN_BOX, DONE_BOX = "box:open", "box:done"
# A bullet is the editor's dot, for the same reason: Qt's list bullet sits
# right against the first word of a right-to-left line.
BULLET = "list:dot"
_PLACEHOLDER = {"☐": OPEN_BOX, "☑": DONE_BOX, "•": BULLET}
# How much of the line each marker takes, in design pixels.
_MARKER_WIDTH = {OPEN_BOX: 16, DONE_BOX: 16, BULLET: 10}
BOX_SIZE = 16
_BOX_GAP = "\u2002"


def _note_link(match) -> str:
    target = match.group(1).strip()
    label = (match.group(2) or match.group(1)).strip()
    encoded = QUrl.toPercentEncoding(target).data().decode("ascii")
    return f"[{label}]({NOTE_SCHEME}:{encoded})"


def _mirrored(row: str) -> str:
    """A pipe-table row with its cells in reverse order."""
    cells = _CELL_SPLIT_RE.split(row.strip())
    if cells and not cells[0].strip():
        cells = cells[1:]
    if cells and not cells[-1].strip():
        cells = cells[:-1]
    return "| " + " | ".join(cell.strip() for cell in reversed(cells)) + " |"


def prepare(text: str, direction=lambda text: "rtl") -> str:
    """The note's text as Qt's Markdown reader should see it.

    The differences from plain Markdown are all about showing a note the way
    the editor does:
    - a line break is a line break (Markdown would join «**وضعیت:** …» and
      «**هدف:** …» into one paragraph);
    - «[[note]]» is a link to another note;
    - a task is a box and its words, a finished one struck through;
    - a right-to-left table starts on the right. Qt lays tables out
      left-to-right whatever the direction it is given, so the columns of
      such a table are handed over in reverse.
    `direction(text)` says which way a stretch of text reads. Code fences are
    left exactly as written.
    """
    lines = text.split("\n")
    out, fenced, index = [], False, 0
    while index < len(lines):
        line = lines[index]
        index += 1
        if _FENCE_RE.match(line):
            fenced = not fenced
            out.append(line)
            continue
        if fenced or not line.strip():
            out.append(line)
            continue
        if "[[" in line:
            line = LINK_RE.sub(_note_link, line)
        if line.lstrip().startswith("|"):
            table = [line]
            while index < len(lines) and lines[index].lstrip().startswith("|"):
                table.append(LINK_RE.sub(_note_link, lines[index]))
                index += 1
            if direction(" ".join(table)) == "rtl":
                table = [_mirrored(row) for row in table]
            out.extend(table)
            continue
        task = TODO_RE.match(line)
        if task:
            indent = "\u2003" * (len(task.group(1).expandtabs(4)) // 2)
            words = line[task.end():].strip()
            if task.group(2) in "xX":
                line = f"{indent}☑{_BOX_GAP}~~{words}~~" if words else f"{indent}☑"
            else:
                line = f"{indent}☐{_BOX_GAP}{words}"
            # Its own paragraph, so a finished task can be greyed alone.
            out.extend([line, ""])
            continue
        bullet = BULLET_RE.match(line)
        if bullet:
            indent = " " * (len(bullet.group(1).expandtabs(4)) // 2)
            out.extend([f"{indent}•{_BOX_GAP}{line[bullet.end():].strip()}", ""])
            continue
        # Two trailing spaces: Markdown's hard line break.
        out.append(line.rstrip() + "  ")
    return "\n".join(out)


def _marker_image(name: str, ratio: float) -> QImage:
    """The editor's markers: an outlined box, a filled one with a tick, or
    the accent dot of a bullet."""
    colors = current_palette()
    done = name == DONE_BOX
    width = _MARKER_WIDTH[name]
    image = QImage(round(width * ratio), round(BOX_SIZE * ratio),
                   QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    image.setDevicePixelRatio(ratio)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    box = QRectF(1.5, 1.5, BOX_SIZE - 3, BOX_SIZE - 3)
    if name == BULLET:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(colors["accent"]))
        painter.drawEllipse(QPointF(width / 2, BOX_SIZE / 2), 3, 3)
    elif done:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(colors["accent"]))
        painter.drawRoundedRect(box, 4, 4)
        pen = QPen(QColor("#ffffff"), 1.8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolyline(QPolygonF([QPointF(4.8, 8.2), QPointF(7.0, 10.4), QPointF(11.2, 5.8)]))
    else:
        painter.setPen(QPen(QColor(colors["muted"]), 1.4))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(box, 4, 4)
    painter.end()
    return image


class ReaderView(QTextBrowser):
    """A read-only page for one note."""

    link_clicked = pyqtSignal(str)  # a note name, as «[[…]]» wrote it

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("readerView")
        self.setReadOnly(True)
        self.setOpenLinks(False)
        self.setFrameShape(QTextBrowser.Shape.NoFrame)
        self.anchorClicked.connect(self._follow)
        self._focus_layout = False
        self._source = ""
        self._font = QFont()
        self._direction_mode = "rtl"

    # Rendering

    def render(self, text: str, font: QFont, direction_mode: str = "rtl"):
        """`direction_mode` is the editor's: "rtl" and "ltr" hold for the
        whole note, "auto" decides per paragraph — the same rule as
        SmartEditor._direction_for_text, so both views agree."""
        self._source = text
        self._font = QFont(font)
        self._direction_mode = direction_mode
        self._rebuild()

    def _direction(self, text: str) -> str:
        if self._direction_mode in ("rtl", "ltr"):
            return self._direction_mode
        return detect_direction(text, "rtl")

    def refresh(self):
        """Paint again from the same text — after a theme or font change."""
        self._rebuild()

    def _rebuild(self):
        scroll = self.verticalScrollBar().value()
        doc = QTextDocument(self)
        doc.setDefaultFont(self._font)
        doc.setDocumentMargin(0)
        doc.setMarkdown(
            prepare(self._source, self._direction),
            QTextDocument.MarkdownFeature.MarkdownDialectGitHub,
        )
        # After setMarkdown, which starts by clearing the document's resources.
        ratio = self.devicePixelRatioF()
        for name in _MARKER_WIDTH:
            doc.addResource(QTextDocument.ResourceType.ImageResource.value, QUrl(name),
                            _marker_image(name, ratio))
        self._place_boxes(doc)
        self._restyle(doc)
        self.setDocument(doc)
        self._apply_page()
        self.verticalScrollBar().setValue(scroll)

    def _restyle(self, doc: QTextDocument):
        colors = current_palette()
        base = self._font.pointSizeF()
        cursor = QTextCursor(doc)
        block = doc.begin()
        while block.isValid():
            text = block.text()
            fmt = block.blockFormat()
            # Code stays left-to-right whatever the note's direction, as in
            # the editor.
            code = fmt.hasProperty(QTextFormat.Property.BlockCodeFence)
            direction = "ltr" if code else self._direction(text)
            layout = (Qt.LayoutDirection.RightToLeft if direction == "rtl"
                      else Qt.LayoutDirection.LeftToRight)
            fmt.setLayoutDirection(layout)
            fmt.setAlignment(Qt.AlignmentFlag.AlignLeading)
            fmt.setLineHeight(LINE_HEIGHT, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
            level = fmt.headingLevel()
            if level:
                fmt.setTopMargin(base * (1.4 if level == 1 else 1.0))
                fmt.setBottomMargin(base * 0.5)
            elif block.textList() is None:
                fmt.setBottomMargin(PARAGRAPH_GAP)
            if code:
                fmt.setBackground(QColor(colors["surface_alt"]))
            cursor.setPosition(block.position())
            cursor.setBlockFormat(fmt)

            run = QTextCursor(block)
            run.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
            if level:
                char = QTextCharFormat()
                char.setFontPointSize(base * HEADING_SCALE.get(level, 1.0))
                char.setFontWeight(HEADING_WEIGHT.get(level, QFont.Weight.DemiBold))
                char.setForeground(QColor(colors["text"]))
                run.mergeCharFormat(char)
            elif self._task_state(block) == DONE_BOX:
                done = QTextCharFormat()
                done.setForeground(QColor(colors["muted"]))
                run.mergeCharFormat(done)
            elif self._task_state(block) == OPEN_BOX:
                open_task = QTextCharFormat()
                open_task.setForeground(QColor(colors["text"]))
                run.mergeCharFormat(open_task)
            elif fmt.hasProperty(QTextFormat.Property.BlockQuoteLevel):
                quote = QTextCharFormat()
                quote.setForeground(QColor(colors["muted"]))
                run.mergeCharFormat(quote)

            self._style_fragments(block, colors)
            span = stamp_span(text)
            if span is not None:
                stamp = QTextCursor(block)
                stamp.setPosition(block.position() + span[0])
                stamp.setPosition(block.position() + span[1], QTextCursor.MoveMode.KeepAnchor)
                quiet = QTextCharFormat()
                quiet.setForeground(QColor(colors["muted"]))
                quiet.setFontStrikeOut(False)
                stamp.mergeCharFormat(quiet)
            block = block.next()

        for frame in self._tables(doc.rootFrame()):
            self._style_table(frame, colors)

    def _style_fragments(self, block, colors: dict):
        """Links in the accent colour; inline code on a soft chip."""
        it = block.begin()
        while not it.atEnd():
            fragment = it.fragment()
            if fragment.isValid():
                char = fragment.charFormat()
                change = QTextCharFormat()
                if char.isImageFormat():
                    change = None  # a marker, already sized by _place_boxes
                elif char.isAnchor():
                    change.setForeground(QColor(colors["accent"]))
                    change.setFontUnderline(False)
                elif char.fontFixedPitch():
                    change.setBackground(QColor(colors["surface_alt"]))
                    change.setForeground(QColor(colors["text"]))
                else:
                    change = None
                if change is not None:
                    cursor = QTextCursor(block.document())
                    cursor.setPosition(fragment.position())
                    cursor.setPosition(fragment.position() + fragment.length(),
                                       QTextCursor.MoveMode.KeepAnchor)
                    cursor.mergeCharFormat(change)
            it += 1

    @staticmethod
    def _place_boxes(doc: QTextDocument):
        """Swap each task's or bullet's placeholder character for its picture."""
        block = doc.begin()
        while block.isValid():
            text = block.text()
            offset = len(text) - len(text.lstrip(" "))
            name = _PLACEHOLDER.get(text[offset:offset + 1])
            if name is not None:
                cursor = QTextCursor(block)
                cursor.setPosition(block.position() + offset)
                cursor.setPosition(block.position() + offset + 1, QTextCursor.MoveMode.KeepAnchor)
                image = QTextImageFormat()
                image.setName(name)
                image.setWidth(_MARKER_WIDTH[name])
                image.setHeight(BOX_SIZE)
                image.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignMiddle)
                cursor.insertImage(image)
            block = block.next()

    @staticmethod
    def _task_state(block) -> str | None:
        """OPEN_BOX or DONE_BOX when the paragraph is a task, else None."""
        it = block.begin()
        while not it.atEnd():
            char = it.fragment().charFormat()
            if char.isImageFormat():
                name = char.toImageFormat().name()
                return name if name in (OPEN_BOX, DONE_BOX) else None
            if it.fragment().text().strip("\u2003\u2002 "):
                return None
            it += 1
        return None

    def _tables(self, frame):
        for child in frame.childFrames():
            if isinstance(child, QTextTable):
                yield child
            yield from self._tables(child)

    def _style_table(self, table: QTextTable, colors: dict):
        cells = [table.cellAt(row, col) for row in range(table.rows())
                 for col in range(table.columns())]
        for cell in cells:
            # A table right after a code block arrives from Qt's reader with
            # an empty paragraph at the top of its first cell.
            first = cell.firstCursorPosition()
            if not first.block().text() and first.block() != cell.lastCursorPosition().block():
                first.deleteChar()
        words = " ".join(
            QTextCursor(cell.firstCursorPosition()).block().text() for cell in cells
        )
        rtl = self._direction(words) == "rtl"

        fmt = table.format()
        fmt.setLayoutDirection(Qt.LayoutDirection.RightToLeft if rtl
                               else Qt.LayoutDirection.LeftToRight)
        fmt.setBorder(1)
        fmt.setBorderBrush(QBrush(QColor(colors["border"])))
        fmt.setBorderStyle(QTextFrameFormat.BorderStyle.BorderStyle_Solid)
        fmt.setBorderCollapse(True)
        fmt.setCellSpacing(0)
        fmt.setCellPadding(CELL_PADDING)
        fmt.setWidth(QTextLength(QTextLength.Type.PercentageLength, 100))
        fmt.setTopMargin(4)
        fmt.setBottomMargin(PARAGRAPH_GAP + 6)
        fmt.setAlignment(Qt.AlignmentFlag.AlignRight if rtl else Qt.AlignmentFlag.AlignLeft)
        table.setFormat(fmt)

        for row in range(table.rows()):
            for col in range(table.columns()):
                cell = table.cellAt(row, col)
                cell_fmt = cell.format().toTableCellFormat()
                if row == 0:
                    cell_fmt.setBackground(QColor(colors["surface_alt"]))
                cell.setFormat(cell_fmt)
                cursor = cell.firstCursorPosition()
                cursor.setPosition(cell.lastCursorPosition().position(),
                                   QTextCursor.MoveMode.KeepAnchor)
                block_fmt = QTextBlockFormat()
                block_fmt.setBottomMargin(0)
                block_fmt.setLineHeight(140, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
                cursor.mergeBlockFormat(block_fmt)
                if row == 0:
                    head = QTextCharFormat()
                    head.setFontWeight(QFont.Weight.DemiBold)
                    head.setForeground(QColor(colors["text"]))
                    cursor.mergeCharFormat(head)

    # Page

    def set_focus_layout(self, on: bool):
        self._focus_layout = on
        self._apply_page()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_page()

    def _apply_page(self):
        """The editor's page: an 860px column, or focus mode's 780px one."""
        width = max(1, self.viewport().width())
        if self._focus_layout:
            inner, top, bottom = FOCUS_WIDTH, FOCUS_TOP, FOCUS_BOTTOM
        else:
            inner, top, bottom = TEXT_MAX, DOC_TOP, DOC_BOTTOM
        side = max(LEFT_ROOM, (width - inner) / 2)
        frame = self.document().rootFrame()
        fmt = frame.frameFormat()
        wanted = (top, bottom, side, side)
        if (fmt.topMargin(), fmt.bottomMargin(), fmt.leftMargin(), fmt.rightMargin()) != wanted:
            fmt.setTopMargin(top)
            fmt.setBottomMargin(bottom)
            fmt.setLeftMargin(side)
            fmt.setRightMargin(side)
            frame.setFrameFormat(fmt)

    # Links

    def _follow(self, url: QUrl):
        if url.scheme() == NOTE_SCHEME:
            self.link_clicked.emit(url.path(QUrl.ComponentFormattingOption.FullyDecoded))
        elif url.scheme() in ("http", "https", "mailto"):
            QDesktopServices.openUrl(url)
