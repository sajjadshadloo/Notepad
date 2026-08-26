"""The left column: notes, tasks and a Jalali calendar, one at a time.

Three panes behind a segmented control rather than four things stacked in
one scroll: notes, tasks and the calendar answer different questions, and
stacking them meant none of the three ever had room.
"""
import os
from datetime import datetime, timedelta
from pathlib import Path

from PyQt6.QtCore import QThread, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

import core.note_index as note_index
from core.rtl_detector import detect_direction
from core.settings_manager import font_chain
from core.tasks import Task, group_of, sort_for_today
from ui.calendar_panel import CalendarPanel
from core.search_service import search_notes
from core.jalali import to_persian_digits
from ui.styles import current_palette
from ui.task_rows import TaskList, when_label

NOTE_EXTENSIONS = (".txt", ".md", ".markdown")

PANES = (("notes", "یادداشت‌ها"), ("tasks", "کارها"), ("calendar", "تقویم"))

# Same urgency order the Ctrl+T list uses, so the two never disagree.
TASK_GROUP_ORDER = ("عقب‌افتاده", "امروز", "فردا", "بعداً", "بدون تاریخ")

WEEKDAY_NAMES = ("شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه")


class _SearchWorker(QThread):
    finished_with_results = pyqtSignal(list)

    def __init__(self, root: str, query: str, parent=None):
        super().__init__(parent)
        self.root = root
        self.query = query

    def run(self):
        results = search_notes(self.root, self.query)
        self.finished_with_results.emit(results)


class _TaskScanWorker(QThread):
    """Reads every note to find tasks — never on the UI thread."""

    scanned = pyqtSignal(list)

    def __init__(self, root: str, parent=None):
        super().__init__(parent)
        self.root = root

    def run(self):
        from ui.reminder_service import scan_folder

        try:
            self.scanned.emit(scan_folder(self.root))
        except Exception:
            self.scanned.emit([])


class Sidebar(QWidget):
    note_activated = pyqtSignal(str)
    root_changed = pyqtSignal(str)
    day_activated = pyqtSignal(object)
    # (path, line) — opening a task from the sidebar jumps to its exact line.
    task_activated = pyqtSignal(str, int)

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

        self._tasks: list[Task] = []
        self._tasks_stale = True
        self._task_worker: _TaskScanWorker | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        layout.addWidget(self._build_switch())

        self._panes = QStackedWidget()
        self._panes.addWidget(self._build_notes_pane())
        self._panes.addWidget(self._build_tasks_pane())
        self._panes.addWidget(self._build_calendar_pane())
        layout.addWidget(self._panes, 1)

        self._search_debounce = QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(300)
        self._search_debounce.timeout.connect(self._run_search)

    def _build_switch(self) -> QWidget:
        switch = QWidget()
        switch.setObjectName("sidebarSwitch")
        row = QHBoxLayout(switch)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)
        self._pane_buttons: dict[str, QToolButton] = {}
        for key, label in PANES:
            button = QToolButton()
            button.setText(label)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked, k=key: self.show_pane(k))
            row.addWidget(button, 1)
            self._pane_buttons[key] = button
        self._pane_buttons["notes"].setChecked(True)
        return switch

    def _build_notes_pane(self) -> QWidget:
        pane = QWidget()
        column = QVBoxLayout(pane)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("sidebarSearch")
        self.search_input.setPlaceholderText("Search notes…")
        self.search_input.textChanged.connect(self._on_search_text_changed)
        self.search_input.textChanged.connect(self._style_search_input)
        column.addWidget(self.search_input)

        # A tree, not a list: subfolders are how notes get organised, and a
        # flat rglob hid that structure entirely.
        self.note_list = QTreeWidget()
        self.note_list.setObjectName("noteList")
        self.note_list.setHeaderHidden(True)
        self.note_list.setIndentation(12)
        # Single click opens a note; itemActivated keeps Enter working too.
        self.note_list.itemClicked.connect(self._activate_item)
        self.note_list.itemActivated.connect(self._activate_item)
        column.addWidget(self.note_list, 1)

        # The notes root is a rare change, so it sits at the foot of the pane
        # it applies to rather than taking a header row from every pane.
        self.root_label = QLabel(self._short_root())
        self.root_label.setObjectName("sidebarHeader")
        self._style_root_label()
        change_root_button = QPushButton("Change…")
        change_root_button.clicked.connect(self.choose_root)
        footer = QHBoxLayout()
        footer.addWidget(self.root_label, 1)
        footer.addWidget(change_root_button)
        column.addLayout(footer)
        return pane

    def _build_tasks_pane(self) -> QWidget:
        pane = QWidget()
        pane.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        column = QVBoxLayout(pane)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(6)
        self.task_list = TaskList()
        self.task_list.itemClicked.connect(self._activate_task)
        self.task_list.itemActivated.connect(self._activate_task)
        column.addWidget(self.task_list, 1)
        return pane

    def _build_calendar_pane(self) -> QWidget:
        pane = QWidget()
        column = QVBoxLayout(pane)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(10)

        self.calendar = CalendarPanel(self.root)
        self.calendar.day_activated.connect(self.day_activated)
        column.addWidget(self.calendar)

        caption = QLabel("این هفته")
        caption.setObjectName("sidebarSectionLabel")
        column.addWidget(caption)

        self.week_ahead = QWidget()
        self.week_ahead.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._week_rows = QVBoxLayout(self.week_ahead)
        self._week_rows.setContentsMargins(0, 0, 0, 0)
        self._week_rows.setSpacing(4)
        column.addWidget(self.week_ahead)

        column.addStretch(1)
        return pane

    def show_pane(self, key: str):
        for name, button in self._pane_buttons.items():
            button.setChecked(name == key)
        self._panes.setCurrentIndex([k for k, _ in PANES].index(key))
        # Tasks and the week-ahead summary both come from a full folder scan,
        # so it happens when one of them is actually looked at, not on save.
        if key in ("tasks", "calendar") and self._tasks_stale:
            self._scan_tasks()

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
            self.calendar.set_root(folder)
            self._tasks_stale = True
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
        self._tasks_stale = True
        self.calendar.refresh()
        if self._panes.currentIndex() in (1, 2):
            self._scan_tasks()
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

    # Tasks and the week ahead

    def _scan_tasks(self):
        if self._task_worker and self._task_worker.isRunning():
            return
        self._tasks_stale = False
        self._task_worker = _TaskScanWorker(self.root, self)
        self._task_worker.scanned.connect(self._tasks_scanned)
        self._task_worker.start()

    def _tasks_scanned(self, tasks: list):
        self._tasks = sort_for_today(tasks, datetime.now())
        self._rebuild_task_list()
        self._rebuild_week_ahead()

    def _rebuild_task_list(self):
        self.task_list.clear()
        now = datetime.now()

        buckets: dict[str, list[Task]] = {}
        for task in self._tasks:
            buckets.setdefault(group_of(task, now), []).append(task)

        for title in TASK_GROUP_ORDER:
            tasks = buckets.get(title)
            if not tasks:
                continue
            self.task_list.add_header(
                title,
                to_persian_digits(str(len(tasks))),
                urgent=title == "عقب‌افتاده",
            )
            for task in tasks:
                self.task_list.add_task(
                    task,
                    when=when_label(task, now),
                    tooltip=f"{task.text}\n{Path(task.path).name}",
                )

        if not self._tasks:
            self.task_list.add_empty("کاری باقی نمانده ✓")

    def _rebuild_week_ahead(self):
        """One row per day for the coming week, with how much is due on it."""
        while self._week_rows.count():
            item = self._week_rows.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        now = datetime.now()
        counts: dict[str, int] = {}
        for task in self._tasks:
            due = task.next_due(now)
            if due is not None:
                counts[due.date().isoformat()] = (
                    counts.get(due.date().isoformat(), 0) + 1
                )

        for offset in range(7):
            day = (now + timedelta(days=offset)).date()
            count = counts.get(day.isoformat(), 0)
            if offset > 0 and count == 0:
                continue
            row = QHBoxLayout()
            # Saturday is column 0 in this calendar, so the name list starts there.
            name = "امروز" if offset == 0 else WEEKDAY_NAMES[(day.weekday() + 2) % 7]
            label = QLabel(name)
            label.setObjectName("weekAheadRow")
            amount = QLabel(to_persian_digits(str(count)) if count else "—")
            amount.setObjectName("weekAheadCount")
            row.addWidget(label, 1)
            row.addWidget(amount)
            holder = QWidget()
            holder.setLayout(row)
            row.setContentsMargins(2, 0, 2, 0)
            self._week_rows.addWidget(holder)

    def _activate_task(self, item):
        payload = self.task_list.payload_of(item)
        if payload:
            self.task_activated.emit(payload[0], payload[1])

    def _activate_item(self, item: QTreeWidgetItem):
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if path:
            self.note_activated.emit(path)
        else:
            # A folder row: toggle it instead of pretending to open something.
            item.setExpanded(not item.isExpanded())
