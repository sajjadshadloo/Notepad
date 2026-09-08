"""The notes page: folder tabs across the top, cards underneath.

The folder is the category. That was chosen over a tag field because a tag
has to be maintained by hand and a folder maintains itself — you already move
files in Explorer, and 3.0's tags were abandoned for exactly this reason.
"""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.jalali import to_persian_digits
from core.note_library import categories, in_category, load_library
from ui.note_cards import NoteCardGrid

ALL_LABEL = "همه"


class NotesBoard(QWidget):
    note_activated = pyqtSignal(str)
    note_delete_requested = pyqtSignal(str)
    new_note_requested = pyqtSignal()

    def __init__(self, root: str, parent=None):
        super().__init__(parent)
        self.setObjectName("notesBoard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._root = root
        self._cards: list = []
        self._category = ALL_LABEL

        column = QVBoxLayout(self)
        column.setContentsMargins(18, 14, 18, 16)
        column.setSpacing(12)
        column.addLayout(self._build_header())

        self.grid = NoteCardGrid()
        self.grid.note_activated.connect(self.note_activated)
        self.grid.note_delete_requested.connect(self.note_delete_requested)
        column.addWidget(self.grid, 1)

        self._empty = QLabel("هنوز یادداشتی اینجا نیست")
        self._empty.setObjectName("emptyHint")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.hide()
        column.addWidget(self._empty, 1)

    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)

        self._tabs_holder = QWidget()
        self._tabs_holder.setObjectName("segmented")
        self._tabs_holder.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._tabs_holder.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._tabs_row = QHBoxLayout(self._tabs_holder)
        self._tabs_row.setContentsMargins(0, 0, 0, 0)
        self._tabs_row.setSpacing(2)
        self._buttons: dict[str, QToolButton] = {}

        new_button = QPushButton("یادداشت جدید")
        new_button.setObjectName("tagChip")
        new_button.setCursor(Qt.CursorShape.PointingHandCursor)
        new_button.clicked.connect(self.new_note_requested)

        row.addWidget(self._tabs_holder)
        row.addStretch(1)
        row.addWidget(new_button)
        return row

    # Data

    def set_root(self, root: str):
        self._root = root
        self.reload()

    def reload(self):
        """Re-read the folder. Deliberately on the UI thread.

        This began as a QThread, on the assumption that a disk walk needs
        one. Measured, the real folder takes 2.8 ms — and the thread cost
        two crashes: destroying the board while it ran was an access
        violation, and keeping it alive hung the process at exit. A folder
        of 500 notes would take ~165 ms, which is the point at which this
        should move off the thread again; a folder of 23 is not.
        """
        self._show(load_library(self._root))

    def _show(self, cards: list):
        self._cards = cards
        self._rebuild_tabs()
        self._fill()

    def _rebuild_tabs(self):
        names = [ALL_LABEL] + categories(self._cards)
        # Only one folder plus "همه" is two buttons saying the same thing.
        self._tabs_holder.setVisible(len(names) > 2)
        while self._tabs_row.count():
            item = self._tabs_row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._buttons.clear()

        if self._category not in names:
            self._category = ALL_LABEL
        for name in names:
            count = len(in_category(self._cards, "" if name == ALL_LABEL else name))
            button = QToolButton()
            button.setText(name + "  " + to_persian_digits(str(count)))
            button.setCheckable(True)
            button.setChecked(name == self._category)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(
                lambda _checked=False, chosen=name: self.show_category(chosen)
            )
            self._tabs_row.addWidget(button)
            self._buttons[name] = button

    def show_category(self, name: str):
        self._category = name
        for key, button in self._buttons.items():
            button.setChecked(key == name)
        self._fill()

    def _fill(self):
        shown = in_category(
            self._cards, "" if self._category == ALL_LABEL else self._category
        )
        self.grid.show_cards(shown)
        self.grid.setVisible(bool(shown))
        self._empty.setVisible(not shown)

    def card_titles(self) -> list[str]:
        return self.grid.card_titles()

    def category_names(self) -> list[str]:
        return list(self._buttons)
