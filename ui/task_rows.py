"""One task row, drawn the way the design draws it.

The design's row is a flex line with `align-items:flex-start` and a 2px top
margin on the box and the date — which is only meaningful if the middle
column *wraps*. That is the whole point: a task is a sentence, and a sidebar
is narrow, so the text takes the lines it needs and the box and the date stay
level with its first line.

Getting this from a plain QTreeWidget is not possible: it gives one elided
line per row, an indent column, and an expand arrow the design does not have.
So the rows are painted here, and both task surfaces share it.
"""
from PyQt6.QtCore import QRect, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QListWidget, QListWidgetItem, QStyledItemDelegate

from core.jalali import format_date, to_persian_digits
from core.tasks import REPEAT_MARK
from ui.styles import current_palette


def when_label(task, now=None) -> str:
    """The due moment as the user would write it, or '' for an undated task."""
    due = task.next_due(now)
    if due is None:
        return ""
    text = format_date(due.date())
    if task.has_time:
        text += to_persian_digits(due.strftime(" %H:%M"))
    if task.repeats:
        text += " " + REPEAT_MARK
    return text

# (path, line) for a task, None for a group heading.
ROLE_PAYLOAD = Qt.ItemDataRole.UserRole
ROLE_KIND = Qt.ItemDataRole.UserRole + 1
ROLE_FIELDS = Qt.ItemDataRole.UserRole + 2

KIND_TASK = "task"
KIND_HEADER = "header"
KIND_EMPTY = "empty"

# Straight from the design: 14px box, 8px gap, 7px/8px padding, 7px radius.
BOX = 14
BOX_BORDER = 1.4
BOX_RADIUS = 4
GAP = 8
PAD_X = 8
PAD_Y = 7
ROW_RADIUS = 7
# The box and the date sit 2px down so they line up with the first line of
# text rather than with the top of the row.
TOP_NUDGE = 2
DATE_SCALE = 0.84
HEADER_SCALE = 0.86


def _font(base: QFont, scale: float = 1.0, bold: bool = False) -> QFont:
    font = QFont(base)
    font.setPointSizeF(max(6.5, base.pointSizeF() * scale))
    font.setBold(bold)
    return font


class TaskRowDelegate(QStyledItemDelegate):
    """Paints group headings and wrapped task rows."""

    def _metrics(self, option, index):
        """The three columns of a task row, in that row's own rect."""
        fields = index.data(ROLE_FIELDS) or {}
        date_font = _font(option.font, DATE_SCALE)
        from PyQt6.QtGui import QFontMetrics

        date_width = (
            QFontMetrics(date_font).horizontalAdvance(fields.get("when", ""))
            if fields.get("when")
            else 0
        )
        text_width = max(
            40,
            option.rect.width()
            - 2 * PAD_X
            - BOX
            - GAP
            - (date_width + GAP if date_width else 0),
        )
        return fields, date_font, date_width, text_width

    def sizeHint(self, option, index) -> QSize:
        kind = index.data(ROLE_KIND)
        self.initStyleOption(option, index)
        from PyQt6.QtGui import QFontMetrics

        if kind == KIND_HEADER:
            height = QFontMetrics(_font(option.font, HEADER_SCALE, True)).height()
            return QSize(option.rect.width(), height + PAD_Y + 4)
        if kind == KIND_EMPTY:
            return QSize(option.rect.width(), QFontMetrics(option.font).height() + 16)

        fields, _date_font, _date_width, text_width = self._metrics(option, index)
        metrics = QFontMetrics(option.font)
        bounds = metrics.boundingRect(
            QRect(0, 0, text_width, 0),
            int(Qt.TextFlag.TextWordWrap),
            fields.get("text", ""),
        )
        # Never shorter than the box, or a one-word task would look clipped.
        return QSize(option.rect.width(), max(bounds.height(), BOX) + 2 * PAD_Y)

    def paint(self, painter: QPainter, option, index):
        self.initStyleOption(option, index)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        palette = current_palette()
        kind = index.data(ROLE_KIND)
        rect = option.rect

        if kind == KIND_HEADER:
            self._paint_header(painter, option, index, palette)
            painter.restore()
            return

        if kind == KIND_EMPTY:
            painter.setPen(QColor(palette["muted"]))
            painter.setFont(option.font)
            painter.drawText(
                rect.adjusted(PAD_X, 0, -PAD_X, 0),
                int(Qt.AlignmentFlag.AlignCenter),
                index.data(Qt.ItemDataRole.DisplayRole) or "",
            )
            painter.restore()
            return

        fields, date_font, date_width, text_width = self._metrics(option, index)
        from PyQt6.QtWidgets import QStyle

        state = option.state
        hovered = bool(state & QStyle.StateFlag.State_MouseOver)
        selected = bool(state & QStyle.StateFlag.State_Selected)
        if selected or hovered:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(palette["hover"]))
            painter.drawRoundedRect(
                rect.adjusted(2, 1, -2, -1), ROW_RADIUS, ROW_RADIUS
            )

        done = bool(fields.get("done"))
        overdue = bool(fields.get("overdue"))
        text_color = QColor(palette["danger"] if overdue else palette["text"])
        if done:
            text_color = QColor(palette["muted"])

        # Right-to-left: the box leads on the right, the date closes on the left.
        box_x = rect.right() - PAD_X - BOX
        box_y = rect.top() + PAD_Y + TOP_NUDGE
        self._paint_box(painter, QRect(box_x, box_y, BOX, BOX), palette, done)

        text_right = box_x - GAP
        text_rect = QRect(
            text_right - text_width, rect.top() + PAD_Y, text_width, rect.height()
        )
        painter.setPen(text_color)
        painter.setFont(option.font)
        flags = int(
            Qt.AlignmentFlag.AlignRight
            | Qt.AlignmentFlag.AlignTop
            | Qt.TextFlag.TextWordWrap
        )
        painter.drawText(text_rect, flags, fields.get("text", ""))

        if date_width:
            painter.setFont(date_font)
            painter.setPen(
                QColor(palette["danger"] if overdue else palette["muted"])
            )
            painter.drawText(
                QRect(
                    rect.left() + PAD_X,
                    rect.top() + PAD_Y + TOP_NUDGE,
                    date_width,
                    rect.height(),
                ),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop),
                fields.get("when", ""),
            )
        painter.restore()

    def _paint_box(self, painter, box: QRect, palette: dict, done: bool):
        pen = QPen(QColor(palette["accent"] if done else palette["border"]))
        pen.setWidthF(BOX_BORDER)
        painter.setPen(pen)
        painter.setBrush(
            QColor(palette["accent"]) if done else Qt.BrushStyle.NoBrush
        )
        painter.drawRoundedRect(box, BOX_RADIUS, BOX_RADIUS)
        if done:
            tick = QPen(QColor(palette["on_accent"]))
            tick.setWidthF(1.8)
            tick.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(tick)
            left, top = box.left(), box.top()
            painter.drawLine(left + 3, top + 7, left + 6, top + 10)
            painter.drawLine(left + 6, top + 10, left + 11, top + 4)

    def _paint_header(self, painter, option, index, palette: dict):
        fields = index.data(ROLE_FIELDS) or {}
        rect = option.rect
        painter.setFont(_font(option.font, HEADER_SCALE, True))
        painter.setPen(
            QColor(palette["danger"] if fields.get("urgent") else palette["muted"])
        )
        painter.drawText(
            rect.adjusted(PAD_X, 4, -PAD_X, 0),
            int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop),
            fields.get("label", ""),
        )
        count = fields.get("count", "")
        if count:
            painter.setPen(QColor(palette["muted"]))
            painter.drawText(
                rect.adjusted(PAD_X, 4, -PAD_X, 0),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop),
                count,
            )


class TaskList(QListWidget):
    """A flat list of headings and task rows — no indent, no expand arrows."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("taskList")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setMouseTracking(True)
        self.setUniformItemSizes(False)
        self.setWordWrap(True)
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setItemDelegate(TaskRowDelegate(self))

    def add_header(self, label: str, count: str = "", urgent: bool = False):
        item = QListWidgetItem()
        item.setData(ROLE_KIND, KIND_HEADER)
        item.setData(ROLE_PAYLOAD, None)
        item.setData(ROLE_FIELDS, {"label": label, "count": count, "urgent": urgent})
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        self.addItem(item)
        return item

    def add_task(self, task, when: str = "", tooltip: str = ""):
        item = QListWidgetItem()
        item.setData(ROLE_KIND, KIND_TASK)
        item.setData(ROLE_PAYLOAD, (task.path, task.line_number))
        item.setData(
            ROLE_FIELDS,
            {
                "text": task.text,
                "when": when,
                "done": task.done,
                "overdue": task.overdue,
            },
        )
        if tooltip:
            item.setToolTip(tooltip)
        self.addItem(item)
        return item

    def add_empty(self, message: str):
        item = QListWidgetItem(message)
        item.setData(ROLE_KIND, KIND_EMPTY)
        item.setData(ROLE_PAYLOAD, None)
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        self.addItem(item)
        return item

    def payload_of(self, item) -> tuple | None:
        return item.data(ROLE_PAYLOAD) if item is not None else None

    # Rows are painted, not labelled, so the text lives in the fields rather
    # than in DisplayRole. These read it back — for tests, and for anything
    # that wants to know what is on screen.

    def row_kind(self, row: int) -> str:
        return self.item(row).data(ROLE_KIND)

    def row_text(self, row: int) -> str:
        item = self.item(row)
        fields = item.data(ROLE_FIELDS) or {}
        return fields.get("label") or fields.get("text") or item.text()

    def texts(self) -> list[str]:
        return [self.row_text(row) for row in range(self.count())]

    def header_texts(self) -> list[str]:
        return [
            self.row_text(row)
            for row in range(self.count())
            if self.row_kind(row) == KIND_HEADER
        ]

    def task_texts(self) -> list[str]:
        return [
            self.row_text(row)
            for row in range(self.count())
            if self.row_kind(row) == KIND_TASK
        ]
