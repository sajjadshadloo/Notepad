"""The 228px folder column on the home page.

«دفترچه» lists «همه» and every folder with its note count; «فایل‌های ثابت»
holds the tasks file, the index an agent starts from, and the Recycle Bin;
the notes folder's path closes the column in a small well.
"""
from pathlib import Path

from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from core.jalali import to_persian_digits
from ui.kit import Button, Clickable, col, draw_icon, draw_text, font, rounded

SIDEBAR_WIDTH = 228
ALL_LABEL = "همه"


class SidebarRow(Clickable):
    """One folder or fixed-file row: icon, name, and a count on the far left."""

    def __init__(self, name: str, glyph: str, count: str = "", *, height: int = 36,
                 selectable: bool = True, parent=None):
        super().__init__(parent)
        self.name = name
        self.glyph = glyph
        self.count = count
        self.selectable = selectable
        self.selected = False
        self.setFixedHeight(height)

    def set_selected(self, selected: bool):
        self.selected = selected
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self.rect())
        if self.selected:
            rounded(p, r, 8, fill=col("surface_alt"))
        elif self.hovered:
            rounded(p, r, 8, fill=col("divider"))
        fg = col("text") if (self.selected or self.hovered) else col("soft")
        icon_fg = col("accent") if self.selected else col("muted")
        cy = r.center().y()
        draw_icon(p, self.glyph, QRectF(r.right() - 10 - 16, cy - 8, 16, 16), icon_fg, 1.35)
        left = 10.0
        if self.count:
            count_font = font(11.5)
            draw_text(p, QRectF(10, 0, 40, r.height()), self.count, count_font, col("muted"),
                      Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            left = 10 + 30
        draw_text(p, QRectF(left, 0, r.width() - 10 - 16 - 10 - left, r.height()),
                  self.name, font(13), fg)
        p.end()


class SectionLabel(QWidget):
    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.text = text
        self.setFixedHeight(18)

    def paintEvent(self, _event):
        p = QPainter(self)
        draw_text(p, QRectF(0, 0, self.width() - 8, self.height()), self.text,
                  font(11.5, 600), col("muted"))
        p.end()


class PathCard(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.path = ""
        self.setFixedHeight(10 + 17 + 4 + 18 + 10)

    def set_path(self, path: str):
        self.path = path
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self.rect())
        rounded(p, r, 10, fill=col("window"), border=col("surface_alt"))
        draw_text(p, QRectF(10, 10, r.width() - 20, 17), "پوشه‌ی یادداشت‌ها",
                  font(11), col("muted"))
        draw_text(p, QRectF(10, 31, r.width() - 20, 18), self.path,
                  font(11.5, mono=True), col("soft"))
        p.end()


class FolderSidebar(QWidget):
    category_selected = pyqtSignal(str)
    tasks_requested = pyqtSignal()
    index_requested = pyqtSignal()
    trash_requested = pyqtSignal()
    new_folder_requested = pyqtSignal()

    def __init__(self, root: str, parent=None):
        super().__init__(parent)
        self.setObjectName("folderSidebar")
        self.setFixedWidth(SIDEBAR_WIDTH)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._root = root
        self._selected = ALL_LABEL
        self._rows: dict[str, SidebarRow] = {}

        column = QVBoxLayout(self)
        column.setContentsMargins(12, 18, 12, 14)
        column.setSpacing(0)

        header = QHBoxLayout()
        header.setContentsMargins(8, 0, 8, 10)
        header.setSpacing(0)
        header.addWidget(SectionLabel("دفترچه"), 1)
        self.new_folder = Button(
            "", "plus", height=24, width=24, radius=6, padding=(0, 0), icon_size=14,
            stroke=1.5, normal={"fg": "muted"}, hover={"bg": "surface_alt", "fg": "text"},
        )
        self.new_folder.setToolTip("پوشه‌ی جدید")
        self.new_folder.clicked.connect(self.new_folder_requested)
        header.addWidget(self.new_folder)
        column.addLayout(header)

        self.folder_column = QVBoxLayout()
        self.folder_column.setContentsMargins(0, 0, 0, 0)
        self.folder_column.setSpacing(2)
        column.addLayout(self.folder_column)

        column.addSpacing(14)
        rule = QWidget()
        rule.setFixedHeight(1)
        rule.paintEvent = lambda _e, w=rule: self._paint_rule(w)
        rule_row = QHBoxLayout()
        rule_row.setContentsMargins(8, 0, 8, 0)
        rule_row.addWidget(rule)
        column.addLayout(rule_row)
        column.addSpacing(14)

        fixed_label = QHBoxLayout()
        fixed_label.setContentsMargins(8, 0, 8, 8)
        fixed_label.addWidget(SectionLabel("فایل‌های ثابت"))
        column.addLayout(fixed_label)

        fixed = QVBoxLayout()
        fixed.setSpacing(2)
        self.tasks_row = SidebarRow("tasks.md", "tasks", height=34, selectable=False)
        self.tasks_row.clicked.connect(self.tasks_requested)
        self.index_row = SidebarRow("INDEX.md", "file", height=34, selectable=False)
        self.index_row.clicked.connect(self.index_requested)
        self.trash_row = SidebarRow("سطل بازیافت", "trash", height=34, selectable=False)
        self.trash_row.clicked.connect(self.trash_requested)
        for row in (self.tasks_row, self.index_row, self.trash_row):
            fixed.addWidget(row)
        column.addLayout(fixed)

        column.addStretch(1)
        self.path_card = PathCard()
        column.addWidget(self.path_card)
        self.set_root(root)

    def _paint_rule(self, widget):
        p = QPainter(widget)
        p.fillRect(widget.rect(), col("surface_alt"))
        p.end()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.fillRect(self.rect(), col("panel"))
        p.setPen(col("divider"))
        p.drawLine(0, 0, 0, self.height())
        p.end()

    def set_root(self, root: str):
        self._root = root
        path = Path(root)
        shown = "\\".join(path.parts[-2:]) if len(path.parts) >= 2 else str(path)
        self.path_card.set_path(shown)
        index = "INDEX.md"
        if not (path / "INDEX.md").exists() and (path / "AGENTS.md").exists():
            index = "AGENTS.md"
        self.index_row.name = index
        self.index_row.update()

    def index_file(self) -> Path:
        return Path(self._root) / self.index_row.name

    def set_categories(self, names, counts=None):
        counts = counts or {}
        while self.folder_column.count():
            item = self.folder_column.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._rows.clear()
        if self._selected not in names:
            self._selected = ALL_LABEL
        for name in names:
            count = to_persian_digits(str(counts[name])) if name in counts else ""
            row = SidebarRow(name, "folder", count)
            row.set_selected(name == self._selected)
            row.clicked.connect(lambda chosen=name: self.select(chosen))
            self.folder_column.addWidget(row)
            self._rows[name] = row

    def selected(self) -> str:
        return self._selected

    def select(self, name):
        self._selected = name
        for key, row in self._rows.items():
            row.set_selected(key == name)
        self.category_selected.emit(name)

    def refresh_palette(self):
        self.update()
        for child in self.findChildren(QWidget):
            child.update()
