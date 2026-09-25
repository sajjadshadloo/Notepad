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
from PyQt6.QtGui import QColor, QFont, QFontMetricsF, QSyntaxHighlighter, QTextCharFormat

from core.formatting import BULLET_RE, HEADING_RE, NUMBERED_RE, TODO_RE
from core.links import LINK_RE
from core.tasks import stamp_span
from ui.styles import current_palette

# The v4 design sets a title at 27px/700 and a section at 17px/600 over a
# 14.5px body; smaller levels step down from there.
HEADING_SCALE = {1: 27 / 14.5, 2: 17 / 14.5, 3: 15.5 / 14.5, 4: 1.04, 5: 1.0, 6: 1.0}
HEADING_WEIGHT = {1: QFont.Weight.Bold}
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
            fmt.setFontWeight(HEADING_WEIGHT.get(level, QFont.Weight.DemiBold))
            fmt.setFontPointSize(base_size * HEADING_SCALE.get(level, 1.0))
            # Headings take the full text colour; paragraphs sit a step
            # softer (the editor's own colour is the design's body grey).
            fmt.setForeground(QColor(colors["text"]))
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
            # The design gives the box a 20px button and an 11px gap before
            # the words: the hidden «- [ ] » is letter-spaced to that width.
            self._stretch(box, text[marker_start:todo.end()], 20 + 11)
            self.setFormat(marker_start, todo.end() - marker_start, box)
            if todo.group(2) not in "xX":
                open_task = QTextCharFormat()
                open_task.setForeground(QColor(colors["text"]))
                self.setFormat(todo.end(), len(text) - todo.end(), open_task)
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
            self._apply_links(text, colors)
            return

        bullet = BULLET_RE.match(text)
        if bullet:
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(0, 0, 0, 0))
            fmt.setLayoutDirection(marker_direction)
            start = len(bullet.group(1))
            # A 6px dot and a 12px gap, as in the design.
            self._stretch(fmt, text[start:bullet.end()], 6 + 12)
            self.setFormat(start, bullet.end() - start, fmt)
            self._apply_inline_bold(text, colors)
            self._apply_links(text, colors)
            return

        numbered = NUMBERED_RE.match(text)
        if numbered:
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(0, 0, 0, 0))
            fmt.setLayoutDirection(marker_direction)
            start = len(numbered.group(1))
            self.setFormat(start, numbered.end() - start, fmt)

        self._apply_inline_bold(text, colors)
        self._apply_links(text, colors)

    def _apply_links(self, text: str, colors: dict):
        """«[[target|label]]» shows only its label, in the link colour.

        The opening «[[» keeps its width — the editor draws the link icon in
        that room — but turns invisible; the target (when a label is given)
        and the closing «]]» shrink away. The file keeps every character.
        """
        if "[[" not in text:
            return
        resolver = getattr(self._editor, "_link_resolver", lambda target: True)
        for match in LINK_RE.finditer(text):
            broken = not resolver(match.group(1).strip())
            shown = match.span(2) if match.group(2) else match.span(1)
            label = QTextCharFormat(self.format(shown[0]))
            label.setForeground(QColor(colors["danger" if broken else "accent"]))
            self.setFormat(shown[0], shown[1] - shown[0], label)
            # The chip needs 2px margin + 7px padding + an 11px icon and a
            # 4px gap on the opening side, and 7 + 2 on the closing one. The
            # brackets reserve exactly that room: invisible, letter-spaced.
            bracket = QFontMetricsF(self._editor.font()).horizontalAdvance("[")
            for start, room in ((match.start(), 2 + 7 + 11 + 4), (match.end() - 2, 7 + 2)):
                spacer = QTextCharFormat(self.format(start))
                spacer.setForeground(QColor(0, 0, 0, 0))
                spacer.setFontLetterSpacingType(QFont.SpacingType.AbsoluteSpacing)
                spacer.setFontLetterSpacing(room / 2 - bracket)
                spacer.setFontStrikeOut(False)
                self.setFormat(start, 2, spacer)
            if match.group(2):
                hidden = QTextCharFormat()
                hidden.setForeground(QColor(0, 0, 0, 0))
                hidden.setFontPointSize(HIDDEN_MARKER_SIZE)
                self.setFormat(match.start(1), match.start(2) - match.start(1), hidden)

    def _stretch(self, fmt: QTextCharFormat, token: str, width_px: float):
        """Letter-space an invisible marker so it takes `width_px` (design px)."""
        if not token:
            return
        scale = self._editor.font().pointSizeF() / 0.75 / 14.5
        natural = QFontMetricsF(self._editor.font()).horizontalAdvance(token)
        fmt.setFontLetterSpacingType(QFont.SpacingType.AbsoluteSpacing)
        fmt.setFontLetterSpacing((width_px * scale - natural) / len(token))

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
        # The gap before the chip is not part of the task's words: a done
        # task's strikethrough must stop at the last word.
        gap_start = len(text[:span[0]].rstrip())
        if gap_start < span[0]:
            gap = QTextCharFormat(self.format(gap_start))
            gap.setFontStrikeOut(False)
            self.setFormat(gap_start, span[0] - gap_start, gap)

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
