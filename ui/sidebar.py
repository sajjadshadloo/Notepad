import os
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QThread, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

import core.note_index as note_index
from core.rtl_detector import detect_direction
from core.settings_manager import font_chain
from core.search_service import search_notes

NOTE_EXTENSIONS = (".txt", ".md", ".markdown")


class _SearchWorker(QThread):
    finished_with_results = pyqtSignal(list)

    def __init__(self, root: str, query: str, parent=None):
        super().__init__(parent)
        self.root = root
        self.query = query

    def run(self):
        results = search_notes(self.root, self.query)
        self.finished_with_results.emit(results)


class Sidebar(QWidget):
    note_activated = pyqtSignal(str)
    root_changed = pyqtSignal(str)

    def __init__(
        self,
        root: str,
        index: dict | None = None,
        parent=None,
        font_families: list[str] | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.root = root
        # The main window shares its index dict so both always see the same
        # timestamps and never overwrite each other's saves.
        self._index = note_index.load() if index is None else index
        self._search_worker: _SearchWorker | None = None
        self._needs_refresh = True

        # Match the application's Latin/Persian font chain. Segoe UI contains
        # Arabic glyphs, so placing it before the Persian family silently made
        # Persian note titles use the wrong face. Rows need the font set on
        # the item itself, so the widget font has to carry the full chain.
        sidebar_font = QFont(self.font())
        sidebar_font.setFamilies(font_families or font_chain({}))
        self.setFont(sidebar_font)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        header = QHBoxLayout()
        self.root_label = QLabel(self._short_root())
        self.root_label.setObjectName("sidebarHeader")
        self._style_root_label()
        change_root_button = QPushButton("Change folder")
        change_root_button.clicked.connect(self.choose_root)
        header.addWidget(self.root_label, 1)
        header.addWidget(change_root_button)
        layout.addLayout(header)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("sidebarSearch")
        self.search_input.setPlaceholderText("Search notes…")
        self.search_input.textChanged.connect(self._on_search_text_changed)
        self.search_input.textChanged.connect(self._style_search_input)
        layout.addWidget(self.search_input)

        self._search_debounce = QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(300)
        self._search_debounce.timeout.connect(self._run_search)

        # A tree, not a list: subfolders are how notes get organised, and a
        # flat rglob hid that structure entirely.
        self.note_list = QTreeWidget()
        self.note_list.setObjectName("noteList")
        self.note_list.setHeaderHidden(True)
        self.note_list.setIndentation(12)
        # Single click opens a note; itemActivated keeps Enter working too.
        self.note_list.itemClicked.connect(self._activate_item)
        self.note_list.itemActivated.connect(self._activate_item)
        layout.addWidget(self.note_list, 1)

    def _short_root(self) -> str:
        name = Path(self.root).name or self.root
        return f"📁 {name}"

    @staticmethod
    def _is_rtl(text: str) -> bool:
        return detect_direction(text, default="ltr") == "rtl"

    def _style_root_label(self):
        rtl = self._is_rtl(Path(self.root).name or self.root)
        self.root_label.setLayoutDirection(
            Qt.LayoutDirection.RightToLeft if rtl else Qt.LayoutDirection.LeftToRight
        )
        self.root_label.setAlignment(
            (Qt.AlignmentFlag.AlignRight if rtl else Qt.AlignmentFlag.AlignLeft)
            | Qt.AlignmentFlag.AlignVCenter
        )

    def _style_search_input(self, text: str):
        rtl = self._is_rtl(text) if text.strip() else False
        self.search_input.setLayoutDirection(
            Qt.LayoutDirection.RightToLeft if rtl else Qt.LayoutDirection.LeftToRight
        )
        self.search_input.setAlignment(
            Qt.AlignmentFlag.AlignRight if rtl else Qt.AlignmentFlag.AlignLeft
        )

    def _style_note_item(self, item: QTreeWidgetItem, direction_text: str):
        """Apply the correct font fallback and alignment to one note row."""
        item.setFont(0, self.font())
        rtl = self._is_rtl(direction_text)
        item.setTextAlignment(
            0,
            (Qt.AlignmentFlag.AlignRight if rtl else Qt.AlignmentFlag.AlignLeft)
            | Qt.AlignmentFlag.AlignVCenter,
        )

    def choose_root(self):
        folder = QFileDialog.getExistingDirectory(self, "Notes Folder", self.root)
        if folder:
            self.root = folder
            self.root_label.setText(self._short_root())
            self._style_root_label()
            self.root_changed.emit(folder)
            self.refresh()

    def _on_search_text_changed(self, _text: str):
        self._search_debounce.start()

    def _run_search(self):
        query = self.search_input.text().strip()
        if not query:
            self.refresh()
            return
        if self._search_worker and self._search_worker.isRunning():
            self._search_worker.finished_with_results.disconnect()
            self._search_worker.quit()
            self._search_worker.wait()
        self._search_worker = _SearchWorker(self.root, query, self)
        self._search_worker.finished_with_results.connect(self._show_search_results)
        self._search_worker.start()

    def _show_search_results(self, results):
        self.note_list.clear()
        for result in results:
            name = Path(result.path).name
            # line_number 0 marks a title match — show it like a normal
            # note entry; content matches keep their snippet context.
            if result.line_number == 0:
                label = name
            else:
                label = f"{name} · {result.snippet}"
            item = QTreeWidgetItem([label])
            item.setData(0, Qt.ItemDataRole.UserRole, result.path)
            item.setToolTip(0, result.path)
            self._style_note_item(item, name)
            self.note_list.addTopLevelItem(item)

    def refresh(self):
        """Rescan the notes folder — but only while the sidebar is visible.

        The sidebar is hidden by default, so scanning a possibly large folder
        at startup (or after every save) would be wasted work; the pending
        refresh runs once in showEvent instead.
        """
        if not self.isVisible():
            self._needs_refresh = True
            return
        self._needs_refresh = False
        root_path = Path(self.root)
        root_path.mkdir(parents=True, exist_ok=True)
        files = [
            str(p.resolve())
            for p in root_path.rglob("*")
            if p.is_file() and p.suffix.lower() in NOTE_EXTENSIONS
        ]
        self._index = note_index.prune(self._index, set(files))
        self._rebuild_note_list(files)

    def _rebuild_note_list(self, files: list[str]):
        """Group notes under the folder they live in.

        Files sitting loose in the notes root stay at the top level; every
        subfolder becomes a collapsible parent, so the tree mirrors what
        Explorer shows instead of flattening it all into one list.
        """
        self.note_list.clear()
        # Resolve the root the same way the file paths were resolved, or
        # relative_to() fails on every one of them — the stored root can be
        # "C:/Users/.../Notepad" while the scan yields "C:\Users\...".
        root_path = Path(self.root).resolve()

        def last_opened(path: str) -> str:
            return self._index.get(path, {}).get("last_opened", "") or "0"

        loose: list[str] = []
        by_folder: dict[str, list[str]] = {}
        for path in files:
            try:
                relative = Path(path).relative_to(root_path)
            except ValueError:
                loose.append(path)
                continue
            folder = relative.parent.as_posix()
            if folder in (".", ""):
                loose.append(path)
            else:
                by_folder.setdefault(folder, []).append(path)

        # Most recently opened first, within the root and within each folder.
        for path in sorted(loose, key=last_opened, reverse=True):
            self.note_list.addTopLevelItem(self._note_item(path))

        for folder in sorted(by_folder):
            parent = QTreeWidgetItem([f"📁 {folder}"])
            parent.setFirstColumnSpanned(True)
            self._style_note_item(parent, folder)
            for path in sorted(by_folder[folder], key=last_opened, reverse=True):
                parent.addChild(self._note_item(path))
            self.note_list.addTopLevelItem(parent)
            parent.setExpanded(True)

    def _note_item(self, path: str) -> QTreeWidgetItem:
        entry = self._index.get(path, {})
        name = Path(path).name
        item = QTreeWidgetItem([name])
        item.setData(0, Qt.ItemDataRole.UserRole, path)
        # One line per note keeps the tree scannable; the timestamp is
        # detail you want on demand, not on every row.
        date = self._format_date(path, entry)
        item.setToolTip(0, path + ((chr(10) + date) if date else ''))
        self._style_note_item(item, name)
        return item

    @staticmethod
    def _format_date(path: str, entry: dict) -> str:
        iso = entry.get("last_opened")
        if iso:
            try:
                moment = datetime.fromisoformat(iso)
            except ValueError:
                moment = None
        else:
            moment = None
        if moment is None:
            try:
                moment = datetime.fromtimestamp(os.path.getmtime(path))
            except OSError:
                return ""
        today = datetime.now().date()
        delta_days = (today - moment.date()).days
        if delta_days == 0:
            return "Today"
        if delta_days == 1:
            return "Yesterday"
        if 1 < delta_days < 30:
            return f"{delta_days} days ago"
        return moment.strftime("%Y-%m-%d")

    def showEvent(self, event):
        super().showEvent(event)
        if self._needs_refresh:
            self.refresh()

    def _activate_item(self, item: QTreeWidgetItem):
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if path:
            self.note_activated.emit(path)
        else:
            # A folder row: toggle it instead of pretending to open something.
            item.setExpanded(not item.isExpanded())
