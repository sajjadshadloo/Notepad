import os
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QThread, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import core.note_index as note_index
from core.rtl_detector import detect_direction
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

    def __init__(self, root: str, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.root = root
        self._index = note_index.load()
        self._active_tags: set[str] = set()
        self._search_worker: _SearchWorker | None = None

        # Match the application's intended Latin/Persian font chain. Segoe UI
        # contains Arabic glyphs, so placing it before Vazirmatn silently made
        # Persian note titles use the wrong face.
        sidebar_font = QFont(self.font())
        sidebar_font.setFamilies(["Inter", "Vazirmatn", "Segoe UI"])
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

        self.tag_row = QHBoxLayout()
        self.tag_row.setSpacing(4)
        layout.addLayout(self.tag_row)

        self.note_list = QListWidget()
        self.note_list.setObjectName("noteList")
        # Single click opens a note; itemActivated keeps Enter working too.
        self.note_list.itemClicked.connect(self._activate_item)
        self.note_list.itemActivated.connect(self._activate_item)
        self.note_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.note_list.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.note_list, 1)

        self.refresh()

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

    def _style_note_item(self, item: QListWidgetItem, direction_text: str):
        """Apply the correct font fallback and alignment to one note row."""
        item.setFont(self.font())
        rtl = self._is_rtl(direction_text)
        item.setTextAlignment(
            (Qt.AlignmentFlag.AlignRight if rtl else Qt.AlignmentFlag.AlignLeft)
            | Qt.AlignmentFlag.AlignVCenter
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
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, result.path)
            item.setToolTip(result.path)
            self._style_note_item(item, name)
            self.note_list.addItem(item)

    def refresh(self):
        root_path = Path(self.root)
        root_path.mkdir(parents=True, exist_ok=True)
        files = [
            str(p.resolve())
            for p in root_path.rglob("*")
            if p.is_file() and p.suffix.lower() in NOTE_EXTENSIONS
        ]
        self._index = note_index.prune(self._index, set(files))
        self._rebuild_tag_row()
        self._rebuild_note_list(files)

    def _rebuild_tag_row(self):
        while self.tag_row.count():
            item = self.tag_row.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        for tag in note_index.all_tags(self._index):
            chip = QPushButton(tag)
            chip.setObjectName("tagChip")
            chip.setCheckable(True)
            chip.setChecked(tag in self._active_tags)
            chip.toggled.connect(lambda checked, t=tag: self._toggle_tag(t, checked))
            self.tag_row.addWidget(chip)
        self.tag_row.addStretch()

    def _toggle_tag(self, tag: str, checked: bool):
        if checked:
            self._active_tags.add(tag)
        else:
            self._active_tags.discard(tag)
        self.refresh()

    def _rebuild_note_list(self, files: list[str]):
        self.note_list.clear()

        def sort_key(path: str):
            entry = self._index.get(path, {})
            pinned_rank = 0 if entry.get("pinned", False) else 1
            return (pinned_rank, entry.get("last_opened", "") or "0")

        visible = []
        for path in files:
            entry = self._index.get(path, {})
            tags = entry.get("tags", [])
            if self._active_tags and not self._active_tags.issubset(set(tags)):
                continue
            visible.append(path)

        visible.sort(key=lambda p: sort_key(p)[1], reverse=True)
        visible.sort(key=lambda p: sort_key(p)[0])

        for path in visible:
            entry = self._index.get(path, {})
            tags = entry.get("tags", [])
            pin_glyph = "📌 " if entry.get("pinned") else ""
            tag_suffix = f"  [{', '.join(tags)}]" if tags else ""
            date_label = self._format_date(path, entry)
            item = QListWidgetItem(
                f"{pin_glyph}{Path(path).name}{tag_suffix}\n{date_label}"
            )
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setToolTip(path)
            self._style_note_item(item, Path(path).name)
            self.note_list.addItem(item)

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

    def _activate_item(self, item: QListWidgetItem):
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            self.note_activated.emit(path)

    def note_opened(self, path: str):
        note_index.touch(self._index, path)
        self.refresh()

    def _show_context_menu(self, position):
        item = self.note_list.itemAt(position)
        if not item:
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        entry = self._index.get(path, {})
        menu = QMenu(self)
        pin_label = "Unpin" if entry.get("pinned") else "Pin"
        pin_action = menu.addAction(pin_label)
        add_tag_action = menu.addAction("Add Tag…")
        remove_tag_menu = None
        if entry.get("tags"):
            remove_tag_menu = menu.addMenu("Remove Tag")
            for tag in entry["tags"]:
                action = remove_tag_menu.addAction(tag)
                action.setData(tag)
        selected = menu.exec(self.note_list.mapToGlobal(position))
        if selected == pin_action:
            note_index.set_pinned(self._index, path, not entry.get("pinned", False))
            self.refresh()
        elif selected == add_tag_action:
            tag, accepted = QInputDialog.getText(self, "Add Tag", "Tag name:")
            if accepted and tag.strip():
                note_index.add_tag(self._index, path, tag.strip())
                self.refresh()
        elif remove_tag_menu and selected and selected.parentWidget() is remove_tag_menu:
            note_index.remove_tag(self._index, path, selected.data())
            self.refresh()
