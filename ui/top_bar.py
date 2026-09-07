"""The 44px bar across the top of the window.

This is the design's own top row, and it is what replaces the File/Edit menu
bar: the folder you are in on the left, one search field in the middle that
reaches notes, tasks *and* commands, and the four things you actually toggle
on the right.

Geometry is the design's: 44px tall, a 270px block at each end so the search
field stays optically centred, 28px square buttons at radius 7, and a search
field 30px tall capped at 440px wide.
"""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPainter, QPixmap
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QWidget,
)

from ui.icons import icon, icon_size
from ui.styles import current_palette

BAR_HEIGHT = 44
SIDE_BLOCK = 270
SEARCH_MAX_WIDTH = 440
BUTTON_SIZE = 28
BRAND_SIZE = 16


class _IconButton(QToolButton):
    """A 28px icon button whose stroke follows hover, like the design's.

    Qt will not tint an icon for you, so the two colours are rendered up
    front and swapped on enter/leave.
    """

    def __init__(self, name: str, tooltip: str, parent=None, size: int = 15):
        super().__init__(parent)
        self._name = name
        self._glyph_size = size
        self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setIconSize(icon_size(size))
        self.setFixedHeight(BUTTON_SIZE)
        self.refresh()

    def refresh(self):
        palette = current_palette()
        self._idle = icon(self._name, palette["muted"], self._glyph_size)
        self._active = icon(self._name, palette["text"], self._glyph_size)
        self.setIcon(self._active if self.underMouse() else self._idle)

    def enterEvent(self, event):
        super().enterEvent(event)
        self.setIcon(self._active)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self.setIcon(self._idle)


class TopBar(QWidget):
    search_requested = pyqtSignal()
    sidebar_toggled = pyqtSignal()
    tasks_requested = pyqtSignal()
    theme_toggled = pyqtSignal()
    settings_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("topBar")
        # A plain QWidget ignores a stylesheet background unless this is
        # set — only widgets Qt styles natively paint one. Without it the
        # bar showed the window colour and the QTabBar inside it painted
        # its own, which read as a stray lighter box around the tab.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(BAR_HEIGHT)

        row = QHBoxLayout(self)
        row.setContentsMargins(10, 0, 10, 0)
        row.setSpacing(10)

        row.addWidget(self._build_left())
        row.addWidget(self._build_search(), 1)
        row.addWidget(self._build_right())

    # Left: brand, sidebar toggle, breadcrumb

    def _build_left(self) -> QWidget:
        block = QWidget()
        block.setFixedWidth(SIDE_BLOCK)
        row = QHBoxLayout(block)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        self.brand = QLabel()
        self.brand.setObjectName("brandMark")
        self.brand.setFixedSize(BRAND_SIZE, BRAND_SIZE)
        row.addWidget(self.brand)

        self.sidebar_button = _IconButton("sidebar", "Sidebar — Ctrl+Shift+B")
        self.sidebar_button.setFixedWidth(BUTTON_SIZE)
        self.sidebar_button.clicked.connect(self.sidebar_toggled)
        row.addWidget(self.sidebar_button)

        self.breadcrumb = QLabel()
        self.breadcrumb.setObjectName("breadcrumb")
        self.breadcrumb.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        row.addWidget(self.breadcrumb, 1)
        return block

    # Centre: the one search field

    def _build_search(self) -> QWidget:
        # Centred by symmetry: two equal spacers either side, and the field
        # takes twice their stretch until it hits its 440px cap, after which
        # the spacers absorb the rest. An AlignHCenter flag cannot do this —
        # giving a layout item an alignment stops Qt expanding it at all, and
        # the field stayed at its content width with the label clipped.
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addStretch(1)

        self.search = QPushButton()
        self.search.setObjectName("topSearch")
        self.search.setMinimumWidth(260)
        self.search.setMaximumWidth(SEARCH_MAX_WIDTH)
        self.search.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.search.setFixedHeight(30)
        # A text cursor, because it reads as a field even though it opens a
        # dialog — that is exactly what the design intends.
        self.search.setCursor(Qt.CursorShape.IBeamCursor)
        self.search.clicked.connect(self.search_requested)

        inner = QHBoxLayout(self.search)
        inner.setContentsMargins(10, 0, 10, 0)
        inner.setSpacing(9)
        # The magnifier is a label in the row, not the button's own icon:
        # QPushButton draws its icon over its own contents area, on top of
        # the layout we put inside it.
        self.search_icon = QLabel()
        self.search_icon.setFixedSize(14, 14)
        self.search_icon.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        inner.addWidget(self.search_icon)

        self.search_label = QLabel("Search notes, tasks and commands")
        self.search_label.setObjectName("topSearchLabel")
        self.search_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        self.search_hint = QLabel("Ctrl K")
        self.search_hint.setObjectName("topSearchHint")
        self.search_hint.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        inner.addWidget(self.search_label, 1)
        # Aligned, not stretched: the badge is a 18px pill, and letting the
        # layout give it the field's full 30px height drew its border as a
        # tall rectangle around a short label.
        self.search_hint.setFixedHeight(18)
        inner.addWidget(self.search_hint, 0, Qt.AlignmentFlag.AlignVCenter)

        # The field takes nearly all the spare width until it hits its cap,
        # then the two equal spacers absorb what is left and keep it centred.
        # At stretch 2 against two 1s it only ever reached half the slot.
        row.addWidget(self.search, 20)
        row.addStretch(1)
        return holder

    # Right: tasks, theme, settings

    def _build_right(self) -> QWidget:
        block = QWidget()
        block.setFixedWidth(SIDE_BLOCK)
        row = QHBoxLayout(block)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)
        row.addStretch(1)

        # The tasks button carries the open count, so it is the one button
        # here that is wider than a square.
        self.tasks_button = _IconButton("tasks", "My tasks — Ctrl+T")
        self.tasks_button.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.tasks_button.setObjectName("tasksButton")
        self.tasks_button.clicked.connect(self.tasks_requested)
        row.addWidget(self.tasks_button)


        self.theme_button = _IconButton("theme", "Dark / Light")
        self.theme_button.setFixedWidth(BUTTON_SIZE)
        self.theme_button.clicked.connect(self.theme_toggled)
        row.addWidget(self.theme_button)

        self.settings_button = _IconButton("settings", "Settings — Ctrl+,")
        self.settings_button.setFixedWidth(BUTTON_SIZE)
        self.settings_button.clicked.connect(self.settings_requested)
        row.addWidget(self.settings_button)
        return block

    # State

    def set_breadcrumb(self, folder: str, name: str):
        self.breadcrumb.setText(f"{folder} / {name}" if folder else name)
        self.breadcrumb.setToolTip(self.breadcrumb.text())

    def set_open_task_count(self, count: str):
        """Blank hides the number, so the button is a plain square again."""
        self.tasks_button.setText(f" {count}" if count else "")

    def refresh_palette(self):
        """Re-render the stroke icons and the brand square after a restyle."""
        for button in (
            self.sidebar_button,
            self.tasks_button,
            self.theme_button,
            self.settings_button,
        ):
            button.refresh()
        self.search_icon.setPixmap(
            icon("search", current_palette()["muted"], 14).pixmap(14, 14)
        )

        # The brand mark is the app icon's accent square, at 16px with a 5px
        # radius — small enough that painting it beats shipping another asset.
        pixmap = QPixmap(BRAND_SIZE * 4, BRAND_SIZE * 4)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        from PyQt6.QtGui import QColor

        painter.setBrush(QColor(current_palette()["accent"]))
        painter.drawRoundedRect(pixmap.rect(), 5 * 4, 5 * 4)
        painter.end()
        self.brand.setPixmap(
            pixmap.scaled(
                BRAND_SIZE,
                BRAND_SIZE,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
