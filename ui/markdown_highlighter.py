"""Live, lightweight styling for Markdown structure and code blocks.

Headings get larger, bold and tinted with the accent color while their
``#`` markers are visually hidden; ``**bold**`` spans render bold with hidden
asterisks; list markers are painted by SmartEditor; and code lines get
VSCode-style multi-language token colors from ``core.syntax``. The
document text itself is never modified — only its rendering.
"""
import re

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat

from core import syntax
from core.formatting import BULLET_RE, HEADING_RE, NUMBERED_RE, TODO_RE
from ui.styles import current_is_light, current_palette

HEADING_SCALE = {1: 1.5, 2: 1.3, 3: 1.15, 4: 1.08, 5: 1.04, 6: 1.0}
HIDDEN_MARKER_SIZE = 1.0

# ``**bold**`` — no space right after the opening or before the closing
# marker, matching how Markdown itself parses strong emphasis.
BOLD_RE = re.compile(r"\*\*(?!\s)(.+?)(?<!\s)\*\*")

# VSCode-inspired token palettes.
CODE_DARK = {
    syntax.KEYWORD: "#c586c0",
    syntax.BUILTIN: "#569cd6",
    syntax.STRING: "#ce9178",
    syntax.COMMENT: "#6a9955",
    syntax.NUMBER: "#b5cea8",
    syntax.FUNCTION: "#dcdcaa",
    syntax.CLASS: "#4ec9b0",
    syntax.VARIABLE: "#9cdcfe",
    syntax.TAG: "#569cd6",
    syntax.ATTRIBUTE: "#9cdcfe",
    syntax.PROPERTY: "#9cdcfe",
    syntax.DECORATOR: "#dcdcaa",
}

CODE_LIGHT = {
    syntax.KEYWORD: "#af00db",
    syntax.BUILTIN: "#0000ff",
    syntax.STRING: "#a31515",
    syntax.COMMENT: "#008000",
    syntax.NUMBER: "#098658",
    syntax.FUNCTION: "#795e26",
    syntax.CLASS: "#267f99",
    syntax.VARIABLE: "#001080",
    syntax.TAG: "#800000",
    syntax.ATTRIBUTE: "#e50000",
    syntax.PROPERTY: "#001080",
    syntax.DECORATOR: "#795e26",
}


class MarkdownHighlighter(QSyntaxHighlighter):
    def __init__(self, editor):
        super().__init__(editor.document())
        self._editor = editor

    def _palette(self) -> dict:
        return current_palette()

    def highlightBlock(self, text: str):
        block_number = self.currentBlock().blockNumber()
        if self._editor.line_is_code(block_number):
            self._highlight_code(text, block_number)
            return
        # Non-code lines never leave a comment/string open for the next one.
        self.setCurrentBlockState(syntax.STATE_NONE)

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

    def _highlight_code(self, text: str, block_number: int):
        language = self._editor.code_language_for_line(block_number)
        previous = self.previousBlockState()
        state = previous if previous > 0 else syntax.STATE_NONE
        # A state only carries over from another code line of the block.
        if not self._editor.line_is_code(block_number - 1):
            state = syntax.STATE_NONE
        spans, next_state = syntax.highlight_line(text, language, state)
        palette = CODE_LIGHT if current_is_light() else CODE_DARK
        for start, length, kind in spans:
            color = palette.get(kind)
            if color is None:
                continue
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(color))
            self.setFormat(start, length, fmt)
        self.setCurrentBlockState(next_state)
