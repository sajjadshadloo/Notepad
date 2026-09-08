"""Live, lightweight styling for Markdown structure.

Headings get larger and bold while their ``#`` markers are visually hidden;
``**bold**`` spans render bold with hidden asterisks; and list markers are
painted by SmartEditor. The document text itself is never modified — only
its rendering.

4.1.2 dropped fenced code blocks. They were the one construct the editor
showed raw — three lines of ``` around whatever you wrote — and a note full
of Persian tasks has no use for them.
"""
import re

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat

from core.formatting import BULLET_RE, HEADING_RE, NUMBERED_RE, TODO_RE
from core.tasks import stamp_span
from ui.styles import current_palette

HEADING_SCALE = {1: 1.5, 2: 1.3, 3: 1.15, 4: 1.08, 5: 1.04, 6: 1.0}
HIDDEN_MARKER_SIZE = 1.0

# ``**bold**`` — no space right after the opening or before the closing
# marker, matching how Markdown itself parses strong emphasis.
BOLD_RE = re.compile(r"\*\*(?!\s)(.+?)(?<!\s)\*\*")

class MarkdownHighlighter(QSyntaxHighlighter):
    def __init__(self, editor):
        super().__init__(editor.document())
        self._editor = editor

    def _palette(self) -> dict:
        return current_palette()

    def highlightBlock(self, text: str):
        colors = self._palette()
        base_size = self._editor.font().pointSizeF()
        marker_direction = (
            Qt.LayoutDirection.RightToLeft
            if self._editor._direction_for_text(text) == "rtl"
            else Qt.LayoutDirection.LeftToRight
        )

        heading = HEADING_RE.match(text)
        if heading:
            level = len(heading.group(1))
            fmt = QTextCharFormat()
            fmt.setFontWeight(QFont.Weight.Bold)
            fmt.setFontPointSize(base_size * HEADING_SCALE.get(level, 1.0))
            # A heading is distinguished by size and weight only. Preserve
            # the editor's normal foreground instead of recoloring user text.
            self.setFormat(0, len(text), fmt)
            # Keep Markdown in the plain-text document, but make the editing
            # surface read like a visual editor. Shrinking the transparent
            # token also avoids leaving a heading-sized gap before the title.
            marker = QTextCharFormat()
            marker.setForeground(QColor(0, 0, 0, 0))
            marker.setFontPointSize(HIDDEN_MARKER_SIZE)
            self.setFormat(0, heading.end(), marker)
            return

        todo = TODO_RE.match(text)
        if todo:
            box = QTextCharFormat()
            # The raw Markdown token stays in the document but is painted as
            # a native-looking checkbox by SmartEditor.paintEvent.
            box.setForeground(QColor(0, 0, 0, 0))
            # Keep neutral '[ ]' and strong-LTR '[x]' at the same visual edge
            # in RTL paragraphs; otherwise checking a Persian item makes the
            # marker jump to the opposite side of the line.
            box.setLayoutDirection(marker_direction)
            # Cover the whole token *including* the space before the text.
            # Leaving that space unformatted let it render in the default
            # style, and the strikethrough below then drew a stray dash
            # across the gap between the checkbox and the first word.
            marker_start = len(todo.group(1))
            self.setFormat(marker_start, todo.end() - marker_start, box)
            if todo.group(2) in "xX":
                done = QTextCharFormat()
                done.setForeground(QColor(colors["muted"]))
                done.setFontStrikeOut(True)
                self.setFormat(todo.end(), len(text) - todo.end(), done)
            # After the strikethrough, not before: that run covers the rest
            # of the line, stamp included, and would paint the characters
            # back into view on a finished task.
            self._hide_stamp(text)
            self._apply_inline_bold(text, colors)
            return

        bullet = BULLET_RE.match(text)
        if bullet:
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(0, 0, 0, 0))
            fmt.setLayoutDirection(marker_direction)
            start = len(bullet.group(1))
            self.setFormat(start, bullet.end() - start, fmt)
            self._apply_inline_bold(text, colors)
            return

        numbered = NUMBERED_RE.match(text)
        if numbered:
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(0, 0, 0, 0))
            fmt.setLayoutDirection(marker_direction)
            start = len(numbered.group(1))
            self.setFormat(start, numbered.end() - start, fmt)

        self._apply_inline_bold(text, colors)

    def _hide_stamp(self, text: str):
        """Make the raw "@1405/06/05" invisible; the editor paints a badge.

        Same idea as the heading markers and the checkbox token: the file
        keeps its plain text, and the screen shows something a person reads.
        The characters are left at full size rather than shrunk, because the
        badge is drawn over the space they reserve.
        """
        span = stamp_span(text)
        if span is None:
            return
        hidden = QTextCharFormat()
        hidden.setForeground(QColor(0, 0, 0, 0))
        self.setFormat(span[0], span[1] - span[0], hidden)

    def _apply_inline_bold(self, text: str, colors: dict):
        """Render ``**bold**`` spans, keeping whatever format is already set
        (e.g. the strikethrough of a completed to-do)."""
        for match in BOLD_RE.finditer(text):
            content_start = match.start() + 2
            content_length = len(match.group(1))
            fmt = QTextCharFormat(self.format(content_start))
            fmt.setFontWeight(QFont.Weight.Bold)
            self.setFormat(content_start, content_length, fmt)
            for marker_start in (match.start(), match.end() - 2):
                marker = QTextCharFormat(self.format(marker_start))
                marker.setForeground(QColor(0, 0, 0, 0))
                marker.setFontPointSize(HIDDEN_MARKER_SIZE)
                self.setFormat(marker_start, 2, marker)
