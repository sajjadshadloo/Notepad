import logging
import os
import json
import sys
from datetime import date, datetime
from pathlib import Path

from PyQt6.QtCore import (
    QAbstractNativeEventFilter,
    QByteArray,
    QPoint,
    QSize,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QAction,
    QActionGroup,
    QCloseEvent,
    QColor,
    QFontDatabase,
    QIcon,
    QKeySequence,
    QPainter,
    QPixmap,
    QTextCursor,
    QTextDocument,
)
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QSystemTrayIcon,
    QTabBar,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core import task_file, trash
import core.note_index as note_index
import core.settings_manager as settings_manager
from core.external_change_monitor import ExternalChangeMonitor
from core import cloud_config
from ui.cloud_sync_worker import CloudSyncWorker
from core.jalali import to_persian_digits
from core.tasks import parse_document, parse_task
from core.tasks import set_stamp, shift_stamp
from core.formatting import (
    toggle_bold,
    toggle_bullet,
    toggle_done,
    toggle_heading,
    toggle_numbered,
    toggle_todo,
)
from core.file_service import read_text_file, write_text_file_atomic
from core.migration import legacy_notes_available, migrate_legacy_notes
from core.recovery_manager import (
    clear_all as clear_all_recoveries,
    load_recoveries,
    remove_recovery,
    save_recovery,
)
from ui.document_tab import DocumentTab, editor_font
from ui.document_tabs import DocumentTabs
from ui.icons import icon
from ui.tray import Tray
from ui.top_bar import TopBar
from ui.quick_open import QuickOpenDialog
from ui.task_watcher import TaskWatcher
from ui.today_view import TodayDialog
from ui.settings_dialog import SettingsDialog
from ui.stamp_picker import StampPicker
from ui.shortcuts_dialog import ShortcutsDialog
from ui.day_widget import DayWidget
from ui.today_rail import TodayRail
from ui.notes_board import NotesBoard
from ui.editor_chrome import DocumentTabBar, EditorStatus, FormatBar, LinksPanel, TabStrip
from ui.folder_sidebar import FolderSidebar
from ui.navigation_rail import NavigationRail
from ui.tasks_workspace import TasksWorkspace
from ui.quick_capture import QuickCaptureDialog
from ui.styles import build_stylesheet, current_palette, resolve_theme

log = logging.getLogger(__name__)

# The status dot the design puts before a tab name.
TAB_DOT_SIZE = 6

APP_TITLE = "Notepad Plus"
APP_VERSION = "4.7.0"

# Line endings, as characters rather than an escape.
NEWLINE_CHARS = chr(13) + chr(10)
FILE_FILTER = "Text Files (*.txt);;Markdown (*.md *.markdown);;All Files (*.*)"
ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"

# Word counting walks the whole document; above this size the status bar
# shows only the character count so typing stays instant.
WORD_COUNT_LIMIT = 200_000


def _app_icon() -> QIcon:
    icon_path = ASSETS_DIR / "icon.ico"
    return QIcon(str(icon_path)) if icon_path.exists() else QIcon()


_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_RUN_NAME = "NotepadPlus"


def _startup_command() -> str:
    """The packaged exe starts straight into the tray; a source run can't."""
    exe = Path(sys.executable)
    if getattr(sys, "frozen", False):
        return f'"{exe}" --minimized'
    return f'"{exe}" "{Path(__file__).resolve().parent.parent / "main.py"}" --minimized'


def _run_at_startup_enabled() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.QueryValueEx(key, _RUN_NAME)
        return True
    except OSError:
        return False


def _set_run_at_startup(on: bool) -> bool:
    """Add or remove the per-user Run entry. Only ever this app's own value."""
    if sys.platform != "win32":
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if on:
                winreg.SetValueEx(key, _RUN_NAME, 0, winreg.REG_SZ, _startup_command())
            else:
                try:
                    winreg.DeleteValue(key, _RUN_NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        log.warning("Could not change the startup entry", exc_info=True)
        return False


def _load_bundled_fonts():
    folders = [ASSETS_DIR / "fonts", settings_manager.user_fonts_dir()]
    for folder in folders:
        if not folder.exists():
            continue
        for path in folder.glob("*"):
            if path.suffix.lower() in {".ttf", ".otf"}:
                QFontDatabase.addApplicationFont(str(path))


class FindReplaceDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        # Not ``self.window``: QWidget already defines a window() method, and
        # shadowing it breaks any Qt code that walks up to the top level.
        self._window = window
        self.setWindowTitle("Find and Replace")
        self.setModal(False)
        self.setObjectName("findPanel")
        self.setFixedWidth(430)
        # A frameless card floated over the editor, like the design's panel,
        # rather than a second window with its own title bar in the taskbar.
        self.setWindowFlags(
            Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(9)

        # Find row: the field carries its own label and match count, with
        # previous / next / close beside it.
        find_row = QHBoxLayout()
        find_row.setSpacing(8)
        find_box = QWidget()
        find_box.setObjectName("findField")
        find_box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        find_box.setFixedHeight(30)
        find_inner = QHBoxLayout(find_box)
        find_inner.setContentsMargins(10, 0, 10, 0)
        find_inner.setSpacing(8)
        find_caption = QLabel("Find")
        find_caption.setObjectName("findCaption")
        self.find_input = QLineEdit()
        self.find_input.setObjectName("findInput")
        self.find_input.setFrame(False)
        self.count_label = QLabel()
        self.count_label.setObjectName("findCount")
        find_inner.addWidget(find_caption)
        find_inner.addWidget(self.find_input, 1)
        find_inner.addWidget(self.count_label)
        find_row.addWidget(find_box, 1)

        for glyph, tooltip, slot in (
            ("‹", "Previous  (Shift+F3)", self.find_previous),
            ("›", "Next  (F3)", self.find_next),
        ):
            button = QPushButton(glyph)
            button.setObjectName("findStep")
            button.setFixedSize(28, 30)
            button.clicked.connect(slot)
            find_row.addWidget(button)
        close_button = QPushButton("×")
        close_button.setObjectName("findClose")
        close_button.setFixedSize(28, 30)
        close_button.clicked.connect(self.close)
        find_row.addWidget(close_button)
        layout.addLayout(find_row)

        # Replace row.
        replace_row = QHBoxLayout()
        replace_row.setSpacing(8)
        replace_box = QWidget()
        replace_box.setObjectName("findField")
        replace_box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        replace_box.setFixedHeight(30)
        replace_inner = QHBoxLayout(replace_box)
        replace_inner.setContentsMargins(10, 0, 10, 0)
        replace_inner.setSpacing(8)
        replace_caption = QLabel("Replace")
        replace_caption.setObjectName("findCaption")
        self.replace_input = QLineEdit()
        self.replace_input.setObjectName("findInput")
        self.replace_input.setFrame(False)
        replace_inner.addWidget(replace_caption)
        replace_inner.addWidget(self.replace_input, 1)
        replace_row.addWidget(replace_box, 1)

        replace_button = QPushButton("Replace")
        replace_button.setObjectName("findAction")
        replace_button.setFixedHeight(30)
        replace_button.clicked.connect(self.replace_one)
        replace_all_button = QPushButton("All")
        replace_all_button.setObjectName("findAction")
        replace_all_button.setFixedHeight(30)
        replace_all_button.clicked.connect(self.replace_all)
        replace_row.addWidget(replace_button)
        replace_row.addWidget(replace_all_button)
        layout.addLayout(replace_row)

        # The three options are pills, not checkboxes.
        options = QHBoxLayout()
        options.setSpacing(6)
        self.case_checkbox = self._flag_pill("Match case")
        self.word_checkbox = self._flag_pill("Whole word")
        self.wrap_checkbox = self._flag_pill("Wrap around")
        self.wrap_checkbox.setChecked(True)
        for box in (self.case_checkbox, self.word_checkbox, self.wrap_checkbox):
            options.addWidget(box)
        options.addStretch(1)
        layout.addLayout(options)

        self.find_input.textChanged.connect(self._update_count)
        self.find_input.returnPressed.connect(self.find_next)
        self.replace_input.returnPressed.connect(self.replace_one)

    def _flag_pill(self, label: str) -> QToolButton:
        pill = QToolButton()
        pill.setText(label)
        pill.setCheckable(True)
        pill.setObjectName("findFlag")
        pill.setCursor(Qt.CursorShape.PointingHandCursor)
        pill.toggled.connect(self._update_count)
        return pill

    def _update_count(self, *_args):
        """How many matches the current needle has, shown in the field."""
        editor = self._editor()
        needle = self.find_input.text()
        if editor is None or not needle:
            self.count_label.setText("")
            return
        document = editor.document()
        flags = self._flags()
        found = 0
        cursor = document.find(needle, 0, flags)
        while not cursor.isNull() and found < 999:
            found += 1
            cursor = document.find(needle, cursor, flags)
        self.count_label.setText(str(found) if found < 999 else "999+")

    def place_over_editor(self):
        """Top right of the editor, like the design's floating panel."""
        window = self._window
        top_left = window.mapToGlobal(window.rect().topLeft())
        x = top_left.x() + window.width() - self.width() - 26
        y = top_left.y() + 120
        self.move(max(top_left.x() + 10, x), y)

    def showEvent(self, event):
        super().showEvent(event)
        self.place_over_editor()
        self._update_count()

    def _editor(self):
        tab = self._window.current_document()
        return tab.editor if tab else None

    def _flags(self, backward: bool = False):
        flags = QTextDocument.FindFlag(0)
        if self.case_checkbox.isChecked():
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        if self.word_checkbox.isChecked():
            flags |= QTextDocument.FindFlag.FindWholeWords
        if backward:
            flags |= QTextDocument.FindFlag.FindBackward
        return flags

    def _find(self, backward: bool) -> bool:
        editor = self._editor()
        needle = self.find_input.text()
        if not editor or not needle:
            return False
        if editor.find(needle, self._flags(backward)):
            return True
        if not self.wrap_checkbox.isChecked():
            self._window.statusBar().showMessage(f'Cannot find "{needle}"', 3000)
            return False
        cursor = editor.textCursor()
        cursor.movePosition(
            QTextCursor.MoveOperation.End
            if backward
            else QTextCursor.MoveOperation.Start
        )
        editor.setTextCursor(cursor)
        if editor.find(needle, self._flags(backward)):
            return True
        self._window.statusBar().showMessage(f'Cannot find "{needle}"', 3000)
        return False

    def find_next(self) -> bool:
        return self._find(backward=False)

    def find_previous(self) -> bool:
        return self._find(backward=True)

    def replace_one(self):
        editor = self._editor()
        if not editor:
            return
        cursor = editor.textCursor()
        selected = cursor.selectedText()
        expected = self.find_input.text()
        matches = (
            selected == expected
            if self.case_checkbox.isChecked()
            else selected.casefold() == expected.casefold()
        )
        if selected and matches:
            cursor.insertText(self.replace_input.text())
        self.find_next()

    def replace_all(self):
        editor = self._editor()
        needle = self.find_input.text()
        if not editor or not needle:
            return
        cursor = editor.textCursor()
        cursor.beginEditBlock()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        editor.setTextCursor(cursor)
        count = 0
        while editor.find(needle, self._flags()):
            editor.textCursor().insertText(self.replace_input.text())
            count += 1
        cursor.endEditBlock()
        self._window.statusBar().showMessage(
            f"Replaced {count} occurrence{'s' if count != 1 else ''}.", 3000
        )


class HotkeyFilter(QAbstractNativeEventFilter):
    """Turns this app's WM_HOTKEY into a call; lets every other message by."""

    WM_HOTKEY = 0x0312

    def __init__(self, hotkey_id: int, callback):
        super().__init__()
        self._id = hotkey_id
        self._callback = callback

    def nativeEventFilter(self, event_type, message):
        try:
            if bytes(event_type) == b"windows_generic_MSG":
                import ctypes.wintypes

                msg = ctypes.wintypes.MSG.from_address(int(message))
                if msg.message == self.WM_HOTKEY and msg.wParam == self._id:
                    QTimer.singleShot(0, self._callback)
                    return True, 0
        except Exception:
            pass
        return False, 0


class MainWindow(QMainWindow):
    # Raised whenever a task is written anywhere. Every surface that shows
    # tasks listens, so the calendar, the day widget and the cards can never
    # disagree about what is done.
    tasks_changed = pyqtSignal()

    def __init__(self, initial_files: list[str] | None = None):
        super().__init__()
        self._cfg = settings_manager.load()
        # 4.3 measures the editor text in CSS pixels, as the design does
        # (body 14.5px). The old default 14pt becomes the design's 14.5px;
        # any other size keeps its look (1pt = 4/3px).
        if self._cfg.get("font_size_unit") != "px":
            old = float(self._cfg.get("font_size", 14))
            self._cfg["font_size"] = 14.5 if old in (14, 14.5) else round(old * 4 / 3 * 2) / 2
            self._cfg["font_size_unit"] = "px"
            settings_manager.save(self._cfg)
        save_dir = settings_manager.resolve_save_dir(self._cfg)
        if not self._cfg.get("notes_root"):
            self._cfg["notes_root"] = str(save_dir)
            settings_manager.save(self._cfg)
        self._note_index = note_index.load()
        self._file_monitor = ExternalChangeMonitor(self)
        self._file_monitor.changed.connect(self._external_file_changed)
        self._file_monitor.missing.connect(self._external_file_missing)
        self._closing_application = False
        # Closing the window only hides it; this is what tells closeEvent
        # the difference between that and actually leaving.
        self._really_quitting = False
        self._tray: Tray | None = None
        self._day_widget: DayWidget | None = None
        # Declared before anything is built. Restoring the last page happens
        # inside __init__, and the calendar page asks the watcher for tasks
        # on the way in — with this assigned at the end of __init__ instead,
        # launching onto the calendar crashed before the window ever showed.
        self._tasks_watcher: TaskWatcher | None = None
        self._links_worker = None
        self._links_pending = False
        self._links_cached = None
        self._links_cached_root = ""
        # Tab status dots, keyed by colour; dropped when the palette changes.
        self._dot_icons: dict = {}
        self._zoom_steps = 0
        self._recently_closed: list[str] = []
        # Fingerprint of the last snapshot written per tab, plus which tabs
        # currently have a file on disk, so the timer can skip both the write
        # and the delete when nothing has moved.
        self._recovery_marks: dict[str, tuple] = {}
        self._recovery_on_disk: set[str] = set()
        # Built on first Ctrl+F, not here. Constructing the first QDialog
        # makes Qt load its widget-style and platform-theme machinery, which
        # in the packaged build cost ~1.3s — 86% of startup — for a dialog
        # most sessions never open.
        self._find_dialog_instance: FindReplaceDialog | None = None
        # Zero-interval single shot: restarting it before it fires simply
        # replaces the pending call, so a burst of edits produces one refresh.
        self._status_timer = QTimer(self, singleShot=True, interval=0)
        self._status_timer.timeout.connect(self._refresh_status)

        from ui.app_updates import UpdateController
        self.updates = UpdateController(APP_VERSION, self._cfg, self)
        self.updates.available.connect(self._app_update_available)
        self.updates.install_requested.connect(self._install_app_update)

        self.setWindowTitle(APP_TITLE)
        self.setWindowIcon(_app_icon())
        available = self.screen().availableGeometry()
        self.setMinimumSize(min(1000, available.width()), min(600, max(400, available.height() - 40)))
        self.resize(min(1360, available.width()), min(820, max(400, available.height() - 40)))
        self.setAcceptDrops(True)

        self._build_actions()
        self._build_menus()
        self._build_format_bar()
        self._build_ui()
        self._sync_worker: CloudSyncWorker | None = None
        self._read_sync_status()
        self._sync_timer = QTimer(self, interval=60_000)
        self._sync_timer.timeout.connect(self._sync_tick)
        QApplication.instance().aboutToQuit.connect(self._finish_background_work)
        self._sync_timer.start()
        QTimer.singleShot(1500, self._sync_tick)
        self._restore_geometry()

        self._recovery_timer = QTimer(self, interval=10_000)
        self._recovery_timer.timeout.connect(self._write_recoveries)
        self._recovery_timer.start()

        opened = False
        for path in initial_files or []:
            opened = self.open_file(path) or opened
        if not opened:
            self.new_document()
            # A file on the command line means the editor, whatever page the
            # window was left on last time.
            self.show_page(self._cfg.get("page", "home"))
        else:
            self.show_page("editor")

        # Recovery and migration both raise modal prompts, and neither may run
        # from here: the window is not on screen yet, so the dialog gets no
        # visible parent, never reaches the taskbar, and can end up behind
        # other windows — the app then looks like it simply failed to start.
        # showEvent runs them once the window is actually up.
        self._startup_prompts_shown = False
        self._install_tray()

    # Actions and chrome

    def _action(self, text, slot, shortcut=None, checkable=False):
        action = QAction(text, self)
        action.setCheckable(checkable)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
            # Registered on the window itself, not left to the menu bar to
            # carry: the design has no menu bar, and a shortcut whose only
            # home is a hidden menu still fires — but one on an action in no
            # menu at all would not.
            self.addAction(action)
        action.triggered.connect(slot)
        return action

    def _build_actions(self):
        # File
        self.new_action = self._action("&New", self.new_document, "Ctrl+N")
        self.open_action = self._action("&Open…", self.open_dialog, "Ctrl+O")
        self.quick_open_action = self._action(
            "&Go to File…", self.show_quick_open, "Ctrl+P"
        )
        # The top bar's field carries a "Ctrl K" badge, so that has to open
        # it too — the badge was advertising a key nothing was bound to.
        self.quick_open_action.setShortcuts(
            [QKeySequence("Ctrl+P"), QKeySequence("Ctrl+K")]
        )
        self.today_action = self._action("My &Tasks…", self.show_today, "Ctrl+T")
        self.daily_note_action = self._action(
            "&Tasks File", self.open_tasks_file, "Ctrl+Shift+D"
        )
        self.save_action = self._action("&Save", self.save_current, "Ctrl+S")
        self.save_as_action = self._action(
            "Save &As…", self.save_current_as, "Ctrl+Shift+S"
        )
        self.rename_action = self._action(
            "&Rename…", self.rename_current_document, "F2"
        )
        self.close_tab_action = self._action(
            "&Close Tab", self.close_current_tab, "Ctrl+W"
        )
        self.reopen_tab_action = self._action(
            "Reopen Closed Ta&b", self.reopen_closed_tab, "Ctrl+Shift+T"
        )
        self.settings_action = self._action(
            "Se&ttings…", self.show_settings, "Ctrl+,"
        )
        self.exit_action = self._action("E&xit", self.quit_application, "Alt+F4")

        # Edit
        self.undo_action = self._action(
            "&Undo", lambda: self._edit_command("undo"), "Ctrl+Z"
        )
        self.redo_action = self._action(
            "&Redo", lambda: self._edit_command("redo"), "Ctrl+Y"
        )
        self.cut_action = self._action(
            "Cu&t", lambda: self._edit_command("cut"), "Ctrl+X"
        )
        self.copy_action = self._action(
            "&Copy", lambda: self._edit_command("copy"), "Ctrl+C"
        )
        self.paste_action = self._action(
            "&Paste", lambda: self._edit_command("paste"), "Ctrl+V"
        )
        # "\tDel" shows the key in the menu without registering a global
        # shortcut, so Delete keeps working inside every other input field.
        self.delete_action = self._action("&Delete\tDel", self.delete_selection)
        self.select_all_action = self._action(
            "Select &All", lambda: self._edit_command("selectAll"), "Ctrl+A"
        )
        self.find_action = self._action("&Find…", self.show_find_dialog, "Ctrl+F")
        self.find_next_action = self._action("Find &Next", self.find_next, "F3")
        self.find_prev_action = self._action(
            "Find Pre&vious", self.find_previous, "Shift+F3"
        )
        self.replace_action = self._action(
            "&Replace…", self.show_replace_dialog, "Ctrl+H"
        )
        self.goto_action = self._action("&Go To…", self.goto_line, "Ctrl+G")
        self.time_date_action = self._action(
            "Time/&Date", self.insert_time_date, "F5"
        )

        # Format
        self.word_wrap_action = self._action(
            "&Word Wrap", self.toggle_word_wrap, checkable=True
        )
        self.word_wrap_action.setChecked(self._cfg.get("word_wrap", True))
        self.heading_actions = [
            self._action(
                f"Heading &{level}",
                lambda checked=False, l=level: self._transform_selected_lines(
                    lambda line: toggle_heading(line, l)
                ),
                f"Ctrl+{level}",
            )
            for level in (1, 2, 3)
        ]
        self.bold_action = self._action("&Bold", self.toggle_bold, "Ctrl+B")
        self.bullet_action = self._action(
            "&Bullet List",
            lambda: self._transform_selected_lines(toggle_bullet),
            "Ctrl+Shift+8",
        )
        self.numbered_action = self._action(
            "&Numbered List",
            lambda: self._transform_selected_lines(toggle_numbered),
            "Ctrl+Shift+7",
        )
        self.todo_action = self._action(
            "&To-Do List",
            lambda: self._transform_selected_lines(toggle_todo),
            "Ctrl+Shift+9",
        )
        self.toggle_done_action = self._action(
            "Toggle Done",
            lambda: self._transform_selected_lines(toggle_done),
            "Ctrl+D",
        )
        # A task becomes a deadline by carrying a stamp, and a habit by
        # carrying the repeat mark after it. Both stay plain text.
        self.stamp_action = self._action(
            "Set &Date…", self.show_stamp_picker, "Ctrl+Shift+A"
        )
        self.font_action = self._action("&Font…", self.show_settings)

        # View
        self.zoom_in_action = self._action(
            "Zoom &In", lambda: self.change_zoom(1), "Ctrl+="
        )
        self.zoom_in_action.setShortcuts(
            [QKeySequence("Ctrl+="), QKeySequence("Ctrl++")]
        )
        self.zoom_out_action = self._action(
            "Zoom &Out", lambda: self.change_zoom(-1), "Ctrl+-"
        )
        self.zoom_reset_action = self._action(
            "&Restore Default Zoom", self.reset_zoom, "Ctrl+0"
        )
        self.day_widget_action = self._action(
            "&Day Widget", self.toggle_day_widget, "Ctrl+Shift+W", checkable=True
        )
        self.day_widget_action.setChecked(self._cfg.get("day_widget", False))
        self.line_numbers_action = self._action(
            "&Line Numbers", self.toggle_line_numbers, checkable=True
        )
        self.line_numbers_action.setChecked(self._cfg.get("show_line_numbers", True))
        self.reading_action = self._action(
            "&Reading View", self.toggle_reading, "Ctrl+E"
        )
        self.shortcuts_action = self._action(
            "&Keyboard Shortcuts", self.show_shortcuts, "Ctrl+/"
        )
        self.about_action = self._action("&About " + APP_TITLE, self.show_about)
        self.update_action = self._action("بررسی به‌روزرسانی…", lambda: self.show_settings('updates'))

        # Encoding
        self.encoding_group = QActionGroup(self)
        self.encoding_group.setExclusive(True)
        self.encoding_actions = {}
        for key, label in (
            ("utf-8", "UTF-8"),
            ("utf-8-sig", "UTF-8 with BOM"),
            ("utf-16-le", "UTF-16 LE"),
            ("utf-16-be", "UTF-16 BE"),
            ("cp1256", "Windows-1256 (Arabic)"),
            ("cp1252", "Windows-1252 (Latin)"),
        ):
            action = self._action(
                label,
                lambda checked=False, encoding=key: self.set_encoding(encoding),
                checkable=True,
            )
            self.encoding_group.addAction(action)
            self.encoding_actions[key] = action
        self.encoding_actions["utf-8"].setChecked(True)

        # Text direction. The editor itself handles Ctrl+Right Shift /
        # Ctrl+Left Shift natively (Windows convention); "\t" only renders
        # the hint in the menu without registering a shortcut.
        self.direction_group = QActionGroup(self)
        self.direction_group.setExclusive(True)
        self.direction_actions = {}
        for key, label in (
            ("auto", "&Automatic"),
            ("rtl", "&Right to Left\tCtrl+Right Shift"),
            ("ltr", "&Left to Right\tCtrl+Left Shift"),
        ):
            action = self._action(
                label,
                lambda checked=False, mode=key: self.set_direction(mode),
                checkable=True,
            )
            self.direction_group.addAction(action)
            self.direction_actions[key] = action
        startup_direction = self._cfg.get("default_direction", "rtl")
        self.direction_actions.get(
            startup_direction, self.direction_actions["rtl"]
        ).setChecked(True)

        # Theme
        self.theme_group = QActionGroup(self)
        self.theme_group.setExclusive(True)
        self.theme_actions = {}
        for key, label in (("system", "&System"), ("light", "&Light"), ("dark", "&Dark")):
            action = self._action(
                label,
                lambda checked=False, theme=key: self.set_theme(theme),
                checkable=True,
            )
            self.theme_group.addAction(action)
            self.theme_actions[key] = action
        current_theme = self._cfg.get("theme", "system")
        self.theme_actions.get(current_theme, self.theme_actions["system"]).setChecked(True)

    def _build_menus(self):
        """Build the menus, then hide the bar.

        The design has no menu bar — everything reaches you through the top
        bar and Ctrl+K. The menus are still built because they are what the
        command palette enumerates, so nothing can quietly become
        unreachable when a feature is added to a menu and nowhere else.
        """
        self.menuBar().setVisible(False)
        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction(self.new_action)
        file_menu.addAction(self.open_action)
        file_menu.addAction(self.quick_open_action)
        file_menu.addAction(self.today_action)
        file_menu.addAction(self.daily_note_action)
        file_menu.addSeparator()
        file_menu.addAction(self.save_action)
        file_menu.addAction(self.save_as_action)
        file_menu.addAction(self.rename_action)
        file_menu.addSeparator()
        # Encoding intentionally has no menu: it is auto-detected and can be
        # changed from the status bar chip, keeping the File menu lean.
        self.recent_menu = QMenu("Recent &Files", self)
        self.recent_menu.aboutToShow.connect(self._refresh_recent_menu)
        file_menu.addMenu(self.recent_menu)
        file_menu.addSeparator()
        file_menu.addAction(self.close_tab_action)
        file_menu.addAction(self.reopen_tab_action)
        file_menu.addSeparator()
        file_menu.addAction(self.settings_action)
        file_menu.addAction(self.exit_action)

        edit_menu = self.menuBar().addMenu("&Edit")
        edit_menu.addAction(self.undo_action)
        edit_menu.addAction(self.redo_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.cut_action)
        edit_menu.addAction(self.copy_action)
        edit_menu.addAction(self.paste_action)
        edit_menu.addAction(self.delete_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.find_action)
        edit_menu.addAction(self.find_next_action)
        edit_menu.addAction(self.find_prev_action)
        edit_menu.addAction(self.replace_action)
        edit_menu.addAction(self.goto_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.select_all_action)
        edit_menu.addAction(self.time_date_action)

        format_menu = self.menuBar().addMenu("F&ormat")
        format_menu.addAction(self.word_wrap_action)
        direction_menu = format_menu.addMenu("Text &Direction")
        direction_menu.addActions(self.direction_group.actions())
        format_menu.addSeparator()
        format_menu.addAction(self.bold_action)
        for action in self.heading_actions:
            format_menu.addAction(action)
        format_menu.addAction(self.bullet_action)
        format_menu.addAction(self.numbered_action)
        format_menu.addAction(self.todo_action)
        format_menu.addAction(self.toggle_done_action)
        format_menu.addAction(self.stamp_action)
        format_menu.addSeparator()
        format_menu.addAction(self.font_action)

        view_menu = self.menuBar().addMenu("&View")
        view_menu.addAction(self.zoom_in_action)
        view_menu.addAction(self.zoom_out_action)
        view_menu.addAction(self.zoom_reset_action)
        view_menu.addSeparator()
        theme_menu = view_menu.addMenu("&Theme")
        theme_menu.addActions(self.theme_group.actions())
        view_menu.addSeparator()
        view_menu.addAction(self.line_numbers_action)
        view_menu.addAction(self.day_widget_action)

        help_menu = self.menuBar().addMenu("&Help")
        help_menu.addAction(self.shortcuts_action)
        help_menu.addAction(self.update_action)
        help_menu.addAction(self.about_action)

    def _build_format_bar(self):
        """The design's format bar: B, two headings, list, task, date, link,
        direction — and on the far side, focus mode and the links panel."""
        bar = FormatBar()
        bar.bold.connect(self.bold_action.trigger)
        bar.heading.connect(lambda level: self.heading_actions[level - 1].trigger())
        bar.bullets.connect(self.bullet_action.trigger)
        bar.task.connect(self.todo_action.trigger)
        bar.date.connect(self.stamp_action.trigger)
        bar.link.connect(self.insert_note_link)
        bar.direction.connect(self.toggle_document_direction)
        bar.focus.connect(lambda: self.set_focus_mode(True))
        bar.links_toggled.connect(self.set_links_panel_visible)
        bar.reading_toggled.connect(self.set_reading)
        self.format_bar = bar

    def _build_ui(self):
        # The links panel re-reads the note a moment after typing stops.
        self._links_timer = QTimer(self, singleShot=True, interval=700)
        self._links_timer.timeout.connect(self.refresh_links_panel)
        self.document_tab_bar = DocumentTabBar()
        self.tabs = DocumentTabs(self.document_tab_bar)
        self.document_tab_bar.new_requested.connect(self.new_document)
        # The painted tab draws and hit-tests its own ×; Qt's close buttons
        # would sit on top of it.
        self.tabs.setTabsClosable(False)
        self.tabs.setMovable(True)
        self.document_tab_bar.set_modified_source(
            lambda index: bool(self.tabs.widget(index) and self.tabs.widget(index).modified))
        self.tabs.setDocumentMode(True)
        self.tabs.setIconSize(QSize(TAB_DOT_SIZE, TAB_DOT_SIZE))
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._current_tab_changed)
        tab_bar = self.tabs.tabBar()
        tab_bar.tabBarDoubleClicked.connect(self.rename_document)
        tab_bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        tab_bar.customContextMenuRequested.connect(self._show_tab_menu)

        self.notes_board = NotesBoard(self._cfg["notes_root"])
        self.notes_board.set_pinned(self._cfg.get("pinned_notes", []))
        self.notes_board.set_view(self._cfg.get("home_view", "grid"))
        self.notes_board.note_activated.connect(self.open_note_from_board)
        self.notes_board.note_delete_requested.connect(self.delete_note)
        self.notes_board.new_note_requested.connect(self.new_note_from_board)
        self.notes_board.view_changed.connect(self._remember_home_view)
        self.notes_board.pin_toggled.connect(self.toggle_pin)

        self.rail = TodayRail()
        self.rail.task_added.connect(self._add_day_task)
        self.rail.task_toggled.connect(self.set_task_done)
        self.rail.task_delete_requested.connect(self.delete_task)
        self.rail.task_opened.connect(self.open_task_in_editor)
        self.rail.file_requested.connect(lambda: self.show_page("tasks"))
        self.rail.added_elsewhere.connect(self.flash)

        self.folder_sidebar = FolderSidebar(self._cfg["notes_root"])
        self.notes_board.library_changed.connect(self._library_changed)
        self.folder_sidebar.category_selected.connect(self._show_folder)
        self.folder_sidebar.tasks_requested.connect(self.open_tasks_file)
        self.folder_sidebar.index_requested.connect(
            lambda: self.open_file(str(self.folder_sidebar.index_file()))
            if self.folder_sidebar.index_file().exists() else None)
        self.folder_sidebar.trash_requested.connect(self._open_recycle_bin)
        self.folder_sidebar.new_folder_requested.connect(self.new_folder)

        # The full month owns dozens of widgets. Build it only when the user
        # first visits Tasks/Calendar so ordinary editor startup stays lean.
        self.tasks_workspace: TasksWorkspace | None = None
        self._tasks_placeholder = QWidget()

        # Home: the notes on the left, today on the right, both at once. The
        # calendar used to be a page of its own, which put three moves
        # between wanting to tick something off and doing it.
        home = QWidget()
        home_row = QHBoxLayout(home)
        home_row.setContentsMargins(0, 0, 0, 0)
        home_row.setSpacing(0)
        home_row.setDirection(QBoxLayout.Direction.RightToLeft)
        home_row.addWidget(self.folder_sidebar)
        home_row.addWidget(self.notes_board, 1)
        home_row.addWidget(self.rail)

        # The editor keeps its tab strip and format bar; they belong to it
        # and mean nothing on the home screen, so they live on this page
        # rather than in the window's own column.
        # The editor page: tabs, format bar, text and status in one column;
        # the links panel beside it on the left.
        self.tab_strip = TabStrip()
        strip_row = QHBoxLayout(self.tab_strip)
        strip_row.setContentsMargins(10, 0, 10, 0)
        strip_row.setSpacing(4)
        strip_row.addWidget(self.tabs)
        self.tabs.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.tab_strip.setFixedHeight(44)
        self.editor_status = EditorStatus()
        self.editor_status.direction.clicked.connect(self.toggle_document_direction)
        self.editor_status.format.clicked.connect(
            lambda: self._popup_status_menu(self.editor_status.format, self.encoding_group.actions()))
        self.editor_status.zoom.clicked.connect(self.reset_zoom)

        editor_column_widget = QWidget()
        editor_column = QVBoxLayout(editor_column_widget)
        editor_column.setContentsMargins(0, 0, 0, 0)
        editor_column.setSpacing(0)
        editor_column.addWidget(self.tab_strip)
        editor_column.addWidget(self.format_bar)
        editor_column.addWidget(self.tabs.pages, 1)
        editor_column.addWidget(self.editor_status)

        self.links_panel = LinksPanel()
        self.links_panel.open_requested.connect(self.open_note_from_board)
        self.links_panel.create_requested.connect(self._create_linked_note)
        editor_page = QWidget()
        editor_row = QHBoxLayout(editor_page)
        editor_row.setContentsMargins(0, 0, 0, 0)
        editor_row.setSpacing(0)
        editor_row.setDirection(QBoxLayout.Direction.RightToLeft)
        editor_row.addWidget(editor_column_widget, 1)
        editor_row.addWidget(self.links_panel)
        links_on = self._cfg.get("links_panel", True)
        self.links_panel.setVisible(links_on)
        self.format_bar.set_links_visible(links_on)
        self.editor_chrome = (self.tab_strip, self.format_bar, self.editor_status)

        self.pages = QStackedWidget()
        self.pages.addWidget(home)
        self.pages.addWidget(editor_page)
        self.pages.addWidget(self._tasks_placeholder)

        self.navigation_rail = NavigationRail()
        self.navigation_rail.page_requested.connect(self.show_page)
        self.navigation_rail.settings_requested.connect(self.show_settings)

        self.top_bar = TopBar()
        self.top_bar.search_requested.connect(self.show_quick_open)
        self.top_bar.tasks_requested.connect(self.show_today)
        self.top_bar.theme_toggled.connect(self.cycle_theme)
        self.top_bar.settings_requested.connect(self.show_settings)
        self.top_bar.widget_toggled.connect(self.toggle_day_widget)
        self.top_bar.page_requested.connect(self.show_page)
        self.top_bar.sync_requested.connect(self.sync_now)
        self.top_bar.quick_capture_requested.connect(self.show_quick_capture)

        shell = QWidget()
        column = QVBoxLayout(shell)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self.top_bar)
        body = QWidget()
        body_row = QHBoxLayout(body)
        body_row.setContentsMargins(0, 0, 0, 0)
        body_row.setSpacing(0)
        body_row.setDirection(QBoxLayout.Direction.RightToLeft)
        body_row.addWidget(self.navigation_rail)
        body_row.addWidget(self.pages, 1)
        column.addWidget(body, 1)
        self.setCentralWidget(shell)
        self._build_overlays()

        # The window's own status bar is never shown in v4: the editor has
        # its status line, and passing messages become toasts.
        self.statusBar().hide()
        # Only the Persian messages are meant for the reader; the older
        # English ones («Opened …», «Saved …») narrated routine actions.
        self.statusBar().messageChanged.connect(
            lambda text: text and not text[:1].isascii() and self.flash(text))

    def update_open_task_count(self, count: int):
        label = to_persian_digits(str(count)) if count else ""
        self.top_bar.set_open_task_count(label)
        self.navigation_rail.set_task_count(label)
        self.notes_board.set_open_today(count)

    # Home page helpers

    def flash(self, message: str):
        """A short confirmation. The toast overlay replaces this in v4."""
        toast = getattr(self, "toast", None)
        if toast is not None:
            toast.flash(message)
        else:
            log.info("flash before the toast exists: %s", message)

    def _show_folder(self, name: str):
        self.notes_board.show_category(name)
        self._update_crumb()

    def _remember_home_view(self, mode: str):
        if self._cfg.get("home_view") != mode:
            self._cfg["home_view"] = mode
            settings_manager.save(self._cfg)

    def toggle_pin(self, path: str):
        pinned = list(self._cfg.get("pinned_notes", []))
        if path in pinned:
            pinned.remove(path)
        else:
            pinned.append(path)
        self._cfg["pinned_notes"] = pinned
        settings_manager.save(self._cfg)
        self.notes_board.set_pinned(pinned)

    def _open_recycle_bin(self):
        try:
            os.startfile("shell:RecycleBinFolder")
        except OSError:
            self.flash("سطل بازیافت باز نشد")

    def new_folder(self):
        name, ok = QInputDialog.getText(self, "پوشه‌ی جدید", "نام پوشه:")
        name = name.strip() if ok else ""
        if not name or any(ch in name for ch in '<>:"/\\|?*'):
            return
        try:
            (Path(self._cfg["notes_root"]) / name).mkdir(parents=True, exist_ok=True)
        except OSError:
            self.flash("پوشه ساخته نشد")
            return
        self.flash("پوشه‌ی «" + name + "» ساخته شد؛ با اولین یادداشت نمایش داده می‌شود")

    def _update_crumb(self):
        """«خانه · همه», «پروژه‌ها · سلتامدیکال», «کارهای من» or «تقویم»."""
        page = getattr(self, "_page", "home")
        if page == "home":
            crumb = "خانه · " + self.folder_sidebar.selected()
        elif page == "editor":
            tab = self.current_document()
            if tab and tab.path:
                from core.note_library import display_name

                root = Path(self._cfg["notes_root"])
                try:
                    folder = Path(tab.path).resolve().relative_to(root.resolve()).parts[:-1]
                except ValueError:
                    folder = ()
                crumb = display_name(folder[0] if folder else "") + " · " + Path(tab.path).stem
            else:
                crumb = tab.display_name if tab else "یادداشت"
        elif page == "calendar":
            crumb = "تقویم"
        else:
            crumb = "کارهای من"
        self.top_bar.set_crumb(crumb)

    def cycle_theme(self):
        """The top bar's sun button: straight between dark and light.

        "System" is a setting, not a step in a toggle, so this lands on a
        concrete theme rather than cycling through three.
        """
        current = self._cfg.get("theme", "system")
        resolved = "light" if resolve_theme(current) == "light" else "dark"
        self.set_theme("dark" if resolved == "light" else "light")

    def show_stamp_picker(self):
        """The @ button: pick the day the task under the cursor is due."""
        tab = self.current_document()
        if not tab:
            return
        # Start on the date the line already carries, if it has one.
        existing = None
        line = tab.editor.textCursor().block().text()
        task = parse_task(line)
        if task is not None and task.due is not None:
            existing = task.due.date()

        picker = StampPicker(self._cfg["notes_root"], existing, self)
        picker.picked.connect(
            lambda day: self._transform_selected_lines(
                lambda text: set_stamp(text, day)
            )
        )
        # Under the @ button, so it reads as that button's own menu.
        anchor = self.format_bar
        if anchor is not None:
            picker.move(
                anchor.mapToGlobal(anchor.rect().bottomLeft())
            )
        picker.exec()

    def _popup_status_menu(self, button, actions):
        menu = QMenu(self)
        menu.addActions(actions)
        position = button.mapToGlobal(QPoint(0, 0))
        position.setY(position.y() - menu.sizeHint().height() - 4)
        menu.exec(position)

    # Documents

    def current_document(self) -> DocumentTab | None:
        widget = self.tabs.currentWidget()
        return widget if isinstance(widget, DocumentTab) else None

    def _effective_font_size(self) -> float:
        """The editor's text size in CSS pixels, zoom included."""
        base = float(self._cfg.get("font_size", 14.5))
        return max(8.0, min(96.0, base + self._zoom_steps))

    def _default_direction(self) -> str:
        return self._cfg.get("default_direction", "rtl")

    def _make_document(self, **kwargs) -> DocumentTab:
        kwargs.setdefault("direction_mode", self._default_direction())
        # A file that was switched by hand keeps that choice across sessions.
        path = kwargs.get("path")
        if path:
            remembered = note_index.direction_for(self._note_index, path)
            if remembered:
                kwargs["direction_mode"] = remembered
        tab = DocumentTab(
            font_family=self._cfg.get("font_family_latin", "Inter"),
            font_family_persian=self._cfg.get("font_family_persian", "Vazirmatn"),
            font_size=self._effective_font_size(),
            **kwargs,
        )
        tab.editor.setLineWrapMode(
            tab.editor.LineWrapMode.WidgetWidth
            if self.word_wrap_action.isChecked()
            else tab.editor.LineWrapMode.NoWrap
        )
        tab.editor.set_line_numbers_visible(
            self.line_numbers_action.isChecked()
        )
        tab.state_changed.connect(lambda tab=tab: self._document_state_changed(tab))
        tab.cursor_changed.connect(self._update_status)
        tab.reading_changed.connect(
            lambda on, tab=tab: tab is self.current_document() and self.format_bar.set_reading(on)
        )
        tab.editor.zoom_requested.connect(self.change_zoom)
        tab.editor.direction_changed.connect(self._editor_direction_changed)
        tab.editor.link_clicked.connect(self.open_link_target)
        tab.editor.set_link_names(lambda: self._links_index().titles())
        tab.editor.textChanged.connect(self._links_timer.start)
        if getattr(self, "_focus", False):
            tab.set_focus_layout(True)
        index = self.tabs.addTab(tab, tab.display_name)
        self.tabs.setCurrentIndex(index)
        self._document_state_changed(tab)
        return tab

    def new_document(self):
        self._make_document()

    def rename_current_document(self):
        self.rename_document(self.tabs.currentIndex())

    def rename_document(self, index: int):
        if index < 0:
            return
        tab = self.tabs.widget(index)
        if not isinstance(tab, DocumentTab):
            return
        self.tabs.setCurrentIndex(index)

        if not tab.path:
            title, accepted = QInputDialog.getText(
                self,
                "Rename Document",
                "New title:",
                text=tab.untitled_title,
            )
            if accepted and title.strip():
                tab.set_untitled_title(title)
                self._document_state_changed(tab)
                self.statusBar().showMessage(
                    f'Renamed to "{tab.display_name}".', 2500
                )
            return

        current_path = Path(tab.path)
        new_name, accepted = QInputDialog.getText(
            self,
            "Rename File",
            "New file name:",
            text=current_path.name,
        )
        if not accepted or not new_name.strip():
            return
        new_name = self._safe_filename(new_name.strip())
        if not Path(new_name).suffix:
            new_name += current_path.suffix
        destination = current_path.with_name(new_name)
        if os.path.normcase(str(destination)) == os.path.normcase(str(current_path)):
            return
        if destination.exists():
            QMessageBox.warning(
                self,
                "Name Already Exists",
                "A file with this name already exists in the folder.",
            )
            return
        try:
            current_path.rename(destination)
        except OSError as exc:
            QMessageBox.critical(
                self, "Rename Failed", f"The file could not be renamed:\n{exc}"
            )
            return
        old_path = tab.path
        tab.path = str(destination.resolve())
        self._file_monitor.move(old_path, tab.path)
        self._add_recent(tab.path)
        self._document_state_changed(tab)
        self.statusBar().showMessage(f"Renamed to {destination.name}", 3000)

    @staticmethod
    def _safe_filename(name: str) -> str:
        invalid = '<>:"/\\|?*'
        cleaned = "".join("_" if char in invalid else char for char in name)
        return cleaned.strip().rstrip(".") or "Untitled"

    def _show_tab_menu(self, position):
        tab_bar = self.tabs.tabBar()
        index = tab_bar.tabAt(position)
        if index < 0:
            return
        self.tabs.setCurrentIndex(index)
        menu = QMenu(self)
        rename = menu.addAction("Rename…")
        close_others = menu.addAction("Close Other Tabs")
        close = menu.addAction("Close Tab")
        selected = menu.exec(tab_bar.mapToGlobal(position))
        if selected == rename:
            self.rename_document(index)
        elif selected == close:
            self.close_tab(index)
        elif selected == close_others:
            self._close_other_tabs(index)

    def _close_other_tabs(self, keep_index: int):
        keep_tab = self.tabs.widget(keep_index)
        index = 0
        while self.tabs.count() > 1:
            if self.tabs.widget(index) is keep_tab:
                index += 1
                continue
            if not self.close_tab(index):
                index += 1
            if index >= self.tabs.count():
                break

    def _start_directory(self) -> str:
        tab = self.current_document()
        if tab and tab.path:
            return str(Path(tab.path).parent)
        return str(settings_manager.resolve_save_dir(self._cfg))

    def open_dialog(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Open", self._start_directory(), FILE_FILTER
        )
        for path in paths:
            self.open_file(path)

    def open_tasks_file(self):
        """Ctrl+Shift+D — open کارها.md, where every dated task lives.

        4.1 kept a note per day and this opened that day's file. One file per
        day fragmented the work into a folder of date-named files, each with
        a heading nobody wrote, so 4.2 keeps them all in one.
        """
        path = task_file.path_for(self._cfg["notes_root"])
        if not path.exists():
            existing = self._tab_for_pending(str(path))
            if existing is None:
                placeholder = self._placeholder_tab()
                self._make_document(text="", pending_path=str(path))
                self._discard_placeholder(placeholder)
            else:
                self.tabs.setCurrentWidget(existing)
        elif not self.open_file(str(path)):
            return
        self.show_page("editor")
        editor = self.current_document().editor
        cursor = editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        editor.setTextCursor(cursor)
        editor.setFocus()

    def show_today(self):
        """Ctrl+T — the dated to-do items from every note, in one place."""
        self._start_task_watcher()
        watcher = self._tasks_watcher
        dialog = TodayDialog(self._cfg["notes_root"], self, task_source=watcher.all_tasks)
        watcher.scanned.connect(dialog.reload)
        watcher.check_now()
        dialog.task_chosen.connect(self._open_task)
        dialog.snooze_requested.connect(self._snooze_task)
        try:
            dialog.exec()
        finally:
            dialog.deleteLater()

    def show_quick_open(self):
        """Ctrl+K / Ctrl+P — notes, open tasks and commands in one list."""
        from core.note_library import display_name
        from core.when import day_label
        from ui.today_rail import task_source

        notes = [
            {"label": card.title, "sub": display_name(card.folder), "path": card.path}
            for card in self.notes_board.cards()
        ]
        tasks = []
        if self._tasks_watcher is not None:
            for task in sorted((t for t in self._tasks_watcher.all_tasks() if not t.done),
                               key=lambda t: (t.due is None, t.due or datetime.max)):
                tasks.append({"label": task.text,
                              "sub": day_label(task.due.date()) if task.due else task_source(task),
                              "path": task.path, "line": task.line_number})
        commands = [
            {"label": "یادداشت جدید", "kbd": "Ctrl N", "run": self.new_document},
            {"label": "کارهای من", "kbd": "Ctrl T", "run": lambda: self.show_page("tasks")},
            {"label": "تقویم ماه", "kbd": "", "run": lambda: self.show_page("calendar")},
            {"label": "رفتن به امروز", "kbd": "",
             "run": lambda: (self.show_page("home"), self.rail.show_day(date.today()))},
            {"label": "ویجت روز روی دسکتاپ", "kbd": "Ctrl Shift W", "run": self.toggle_day_widget},
            {"label": "تنظیمات", "kbd": "Ctrl ,", "run": self.show_settings},
            {"label": "فهرست میان‌برها", "kbd": "Ctrl /", "run": self.show_shortcuts},
            {"label": "ضبط سریع", "kbd": "Alt N", "run": self.show_quick_capture},
            {"label": "مرور روز", "kbd": "", "run": self.show_review},
            {"label": "حالت تمرکز", "kbd": "F11", "run": lambda: self.set_focus_mode(True)},
        ]
        extra = [{"label": label, "kbd": keys.replace("+", " "), "run": run}
                 for label, keys, run in self._palette_commands()]
        self.palette_overlay.open_with(notes, tasks, commands, extra)

    def _build_overlays(self):
        from ui.overlays import (
            CommandPalette,
            FocusPill,
            MorningReview,
            QuickCapture,
            SettingsPanel,
            Toast,
        )

        self.palette_overlay = CommandPalette(self)
        self.palette_overlay.note_chosen.connect(self.open_note_from_board)
        self.palette_overlay.task_chosen.connect(self._open_task)
        self.palette_overlay.create_note.connect(self._new_titled_note)

        self.settings_overlay = SettingsPanel(self, APP_VERSION)
        self.settings_overlay.theme_changed.connect(self.set_theme)
        self.settings_overlay.palette_changed.connect(self._set_palette)
        self.settings_overlay.font_size_changed.connect(self._set_font_size)
        self.settings_overlay.line_numbers_changed.connect(self._set_line_numbers)
        self.settings_overlay.startup_changed.connect(self._set_run_at_startup)
        self.settings_overlay.tray_changed.connect(self._set_close_to_tray)
        self.settings_overlay.folder_change_requested.connect(self._choose_notes_root)
        self.settings_overlay.sync_requested.connect(self.sync_now)
        self.settings_overlay.sync_settings_changed.connect(self.sync_now)

        self.quick_capture = QuickCapture(self)
        self.quick_capture.task_submitted.connect(self._capture_task)
        self.quick_capture.note_submitted.connect(self._save_quick_note)

        self.review = MorningReview(self, self._cfg.get("display_name", ""))
        self.review.reschedule.connect(self._review_reschedule)
        self.review.mark_done.connect(lambda path, line: (self.set_task_done(path, line, True),
                                                         self._refill_review()))
        self.review.delete.connect(lambda path, line: (self.delete_task(path, line),
                                                      self._refill_review()))

        self.toast = Toast(self)
        self.focus_pill = FocusPill(self)
        self.focus_pill.exit_requested.connect(lambda: self.set_focus_mode(False))

        for keys, slot in (("Alt+N", self.show_quick_capture), ("F11", self.toggle_focus_mode),
                           ("Ctrl+Shift+F", self.toggle_focus_mode)):
            action = QAction(self)
            action.setShortcut(QKeySequence(keys))
            action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
            action.triggered.connect(slot)
            self.addAction(action)

    def _new_titled_note(self, title: str):
        self.new_document()
        tab = self.current_document()
        if tab is not None:
            tab.editor.setPlainText("# " + title + NEWLINE_CHARS[-1])
            cursor = tab.editor.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            tab.editor.setTextCursor(cursor)
        self.show_page("editor")

    def _capture_task(self, day, text: str):
        self._add_day_task(day, text)
        from core.when import day_label

        self.flash("به کارهای " + day_label(day) + " اضافه شد")

    # Settings panel

    def _settings_state(self) -> dict:
        settings = cloud_config.load()
        sync = {"enabled": False, "title": "همگام‌سازی خاموش"}
        sync["enabled"] = bool(settings.enabled and settings.url and settings.key)
        if sync["enabled"]:
            sync["title"] = "متصل به Mini App تلگرام"
        report = getattr(self, "_sync_report", None) or {}
        sync["last"] = self.top_bar.sync_button.text().replace("همگام · ", "")
        conflicts = int(report.get("conflicts", 0) or 0)
        sync["conflicts"] = "ندارد" if not conflicts else to_persian_digits(str(conflicts))
        try:
            state = json.loads((settings_manager.app_data_dir() / "cloud_sync_state.json")
                               .read_text(encoding="utf-8"))
            live = sum(1 for item in state.get("items", {}).values() if item.get("hash"))
            sync["files"] = to_persian_digits(str(live)) + " فایل"
        except (OSError, ValueError, AttributeError):
            sync["files"] = "—"
        shortcuts = [
            ("جست‌وجو و دستورها", "Ctrl K"), ("یادداشت جدید", "Ctrl N"), ("ذخیره", "Ctrl S"),
            ("کارهای من", "Ctrl T"), ("باز کردن tasks.md", "Ctrl Shift D"),
            ("ویجت روز", "Ctrl Shift W"), ("تبدیل خط به کار", "Ctrl Shift 9"),
            ("انجام شد / نشد", "Ctrl D"), ("دادن تاریخ به کار", "Ctrl Shift A"),
            ("جست‌وجو / جایگزینی", "Ctrl F / Ctrl H"), ("ضبط سریع", "Alt N"),
            ("حالت تمرکز", "F11"),
        ]
        return {
            "notes_root": str(Path(self._cfg["notes_root"])),
            "theme": self._cfg.get("theme", "system"),
            "palette": self._cfg.get("accent_palette", "graphite"),
            "font_size": self._cfg.get("font_size", 14.5),
            "line_numbers": self._cfg.get("show_line_numbers", True),
            "startup": _run_at_startup_enabled(),
            "tray": self._cfg.get("close_to_tray", True),
            "sync": sync,
            "sync_settings": settings,
            "shortcuts": shortcuts,
        }

    def _set_palette(self, name: str):
        self._cfg["accent_palette"] = name
        settings_manager.save(self._cfg)
        self._restyle()

    def _set_font_size(self, size: float):
        self._cfg["font_size"] = size
        settings_manager.save(self._cfg)
        self._apply_editor_fonts()

    def _set_line_numbers(self, on: bool):
        self.line_numbers_action.setChecked(on)
        self.toggle_line_numbers(on)

    def _set_close_to_tray(self, on: bool):
        self._cfg["close_to_tray"] = on
        settings_manager.save(self._cfg)

    def _set_run_at_startup(self, on: bool):
        if not _set_run_at_startup(on):
            self.flash("تنظیم اجرا همراه ویندوز ممکن نشد")

    def _choose_notes_root(self):
        folder = QFileDialog.getExistingDirectory(self, "پوشه‌ی یادداشت‌ها", self._cfg["notes_root"])
        if folder:
            self.set_notes_root(folder)
            if self.settings_overlay.isVisible():
                self.settings_overlay.open_with(self._settings_state(), "general")

    # Morning review

    def show_review(self):
        self._refill_review()
        self.review.open()

    def _overdue_and_today(self):
        if self._tasks_watcher is None:
            return [], 0
        today = date.today()
        tasks = self._tasks_watcher.all_tasks()
        overdue = sorted((t for t in tasks if not t.done and t.due and t.due.date() < today),
                         key=lambda t: t.due)
        open_today = sum(1 for t in tasks if not t.done and t.due and t.due.date() == today)
        return overdue, open_today

    def _refill_review(self):
        overdue, open_today = self._overdue_and_today()
        self.review.set_tasks(overdue, open_today)

    def _review_reschedule(self, path: str, line: int, day):
        self.set_task_day(path, line, day)
        self._refill_review()

    def _maybe_morning_review(self):
        """Once a day, the first time the window is on screen with the tasks read."""
        today = date.today().isoformat()
        if self._closing_application or self._cfg.get("review_date") == today or not self.isVisible() or self.isMinimized():
            return
        if QApplication.activeModalWidget() is not None or any(overlay.isVisible() for overlay in
                (self.settings_overlay, self.palette_overlay, self.quick_capture, self.review)):
            # Never cover a pairing code, an unsaved-change prompt or a field
            # the user is typing into with a second blocking overlay.
            QTimer.singleShot(15_000, self._maybe_morning_review)
            return
        self._cfg["review_date"] = today
        settings_manager.save(self._cfg)
        self.show_review()

    # Links between notes

    def insert_note_link(self):
        """The format bar's link button: «[[]]» with the caret inside."""
        tab = self.current_document()
        if tab is None:
            return
        editor = tab.editor
        cursor = editor.textCursor()
        selected = cursor.selectedText()
        cursor.insertText("[[" + selected + "]]")
        if not selected:
            cursor.movePosition(cursor.MoveOperation.Left, n=2)
            editor.setTextCursor(cursor)
            editor.show_link_completer()
        editor.setFocus()

    def toggle_document_direction(self):
        tab = self.current_document()
        if tab is None:
            return
        rtl = tab.editor.current_direction() == "rtl"
        self.set_direction("ltr" if rtl else "rtl")

    def set_links_panel_visible(self, on: bool):
        self._cfg["links_panel"] = bool(on)
        settings_manager.save(self._cfg)
        if not getattr(self, "_focus", False):
            self.links_panel.setVisible(on)
        self.format_bar.set_links_visible(on)
        if on:
            self.refresh_links_panel()

    def _links_index(self):
        from core.links import NoteIndex

        root = self._cfg["notes_root"]
        if self._links_cached_root != root or self._links_cached is None:
            self.refresh_links_panel(force=True)
            return NoteIndex(root, paths=[])
        return self._links_cached

    def refresh_links_panel(self, force=False):
        """Stats, outgoing links and backlinks for the current note."""
        if not hasattr(self, "links_panel") or (not force and not self.links_panel.isVisible()):
            return
        from core.links import link_details
        from ui.background import ReadWorker, start_background

        tab = self.current_document()
        if tab is None:
            self.links_panel.show_links(0, [], [])
            return
        if self._closing_application:
            return
        if self._links_worker is not None:
            self._links_pending = True
            return
        root, path, text = self._cfg["notes_root"], tab.path, tab.text
        identity = (root, tab.recovery_id, tab.editor.document().revision())
        worker = ReadWorker(lambda cancelled: (identity, link_details(root, path, text, cancelled)))
        self._links_worker = worker
        worker.completed.connect(self._links_loaded)
        worker.finished.connect(self._links_finished)
        self.destroyed.connect(worker.cancel)
        start_background(worker)

    def _links_loaded(self, result, error):
        if error or self._closing_application:
            return
        identity, details = result
        tab = self.current_document()
        if not tab or identity != (self._cfg["notes_root"], tab.recovery_id, tab.editor.document().revision()):
            self._links_pending = True
            return
        index, open_tasks, outgoing, incoming = details
        self._links_cached_root, self._links_cached = identity[0], index
        self.links_panel.show_links(open_tasks, outgoing, incoming)
        tab.editor.set_link_resolver(lambda target: index.resolve(target) is not None)

    def _links_finished(self):
        self._links_worker = None
        if self._links_pending:
            self._links_pending = False
            self.refresh_links_panel()

    def _library_changed(self):
        self.folder_sidebar.set_categories(self.notes_board.category_names(), self.notes_board.category_counts())
        self._links_cached = None
        self._links_timer.start()

    def _create_linked_note(self, title: str):
        """A broken link's «ساختن»: the note, next to the one linking to it."""
        tab = self.current_document()
        folder = Path(tab.path).parent if tab and tab.path else Path(self._cfg["notes_root"]) / "Inbox"
        safe = "".join(ch for ch in title if ch not in '<>:"/\\|?*').strip() or "یادداشت بی‌نام"
        path = folder / (safe + ".md")
        if not path.exists():
            folder.mkdir(parents=True, exist_ok=True)
            write_text_file_atomic(str(path), "# " + title + NEWLINE_CHARS[-1] * 2, "utf-8")
            self.flash("یادداشت «" + title + "» ساخته شد")
        self.open_note_from_board(str(path))

    def open_link_target(self, target: str):
        """Clicking «[[…]]» in the text: open that note, or make it."""
        if self._links_cached is None or self._links_cached_root != self._cfg["notes_root"]:
            self.refresh_links_panel(force=True)
            self.flash("فهرست پیوندها در حال آماده‌شدن است؛ چند لحظه بعد دوباره بزن.")
            return
        found = self._links_index().resolve(target)
        if found is not None:
            self.open_note_from_board(str(found))
        else:
            self._create_linked_note(target)

    # Reading view

    def toggle_reading(self):
        tab = self.current_document()
        if tab:
            self.set_reading(not tab.reading)

    def set_reading(self, on: bool):
        """Ctrl+E: the current note as a finished page — tables, links and
        all — or back to editing it. The file is not touched either way."""
        tab = self.current_document()
        if tab is None:
            self.format_bar.set_reading(False)
            return
        self.show_page("editor")
        tab.set_reading(on)
        self.format_bar.set_reading(tab.reading)

    # Focus mode

    def toggle_focus_mode(self):
        self.set_focus_mode(not getattr(self, "_focus", False))

    def set_focus_mode(self, on: bool):
        """Only the page of text: no chrome, a 780px column, a pill to leave by."""
        self._focus = on
        if on:
            self.show_page("editor")
        self.top_bar.setVisible(not on)
        self.navigation_rail.setVisible(not on)
        editor_chrome = getattr(self, "editor_chrome", ())
        for widget in editor_chrome:
            widget.setVisible(not on)
        self.links_panel.setVisible(not on and self._cfg.get("links_panel", True))
        for index in range(self.tabs.count()):
            tab = self.tabs.widget(index)
            if hasattr(tab, "set_focus_layout"):
                tab.set_focus_layout(on)
        if on:
            self.focus_pill.show_pill()
        else:
            self.focus_pill.hide_pill()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        for name in ("palette_overlay", "settings_overlay", "quick_capture", "review"):
            overlay = getattr(self, name, None)
            if overlay is not None:
                overlay.window_resized()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape and getattr(self, "_focus", False):
            self.set_focus_mode(False)
            return
        super().keyPressEvent(event)

    def _palette_commands(self) -> list[tuple]:
        """Every command in the app, read off the (hidden) menus.

        Walking the menus rather than listing commands by hand is what keeps
        the palette complete: with no menu bar on screen, anything missing
        here would be reachable only by its shortcut, if it has one.
        """
        commands: list[tuple] = []
        seen: set[int] = set()

        def walk(menu, prefix: str):
            for action in menu.actions():
                if action.isSeparator() or not action.isEnabled():
                    continue
                submenu = action.menu()
                label = action.text().replace("&", "").strip()
                if submenu is not None:
                    walk(submenu, f"{prefix}{label} › " if label else prefix)
                    continue
                if not label or id(action) in seen:
                    continue
                seen.add(id(action))
                commands.append(
                    (
                        prefix + label.rstrip("…"),
                        action.shortcut().toString(),
                        action.trigger,
                    )
                )

        for menu_action in self.menuBar().actions():
            menu = menu_action.menu()
            if menu is not None:
                walk(menu, "")
        return commands

    def open_file(self, path: str) -> bool:
        candidate = str(Path(path).resolve())
        for index in range(self.tabs.count()):
            tab = self.tabs.widget(index)
            if tab.path and os.path.normcase(tab.path) == os.path.normcase(candidate):
                self.tabs.setCurrentIndex(index)
                return True
        try:
            loaded = read_text_file(candidate)
        except Exception as exc:
            QMessageBox.critical(
                self, "Open Failed", f"The file could not be opened:\n{exc}"
            )
            return False
        # Replace an unused empty tab instead of leaving it behind.
        placeholder = self._placeholder_tab()
        self._make_document(text=loaded.text, path=candidate, encoding=loaded.encoding)
        self._file_monitor.watch(candidate)
        self._discard_placeholder(placeholder)
        self._add_recent(candidate)
        note_index.touch(self._note_index, candidate)
        self.notes_board.reload()
        self.statusBar().showMessage(f"Opened {candidate}", 3000)
        return True

    def _placeholder_tab(self) -> DocumentTab | None:
        """The lone untouched blank document, if that is all there is.

        Opening or recovering a file should take its place rather than leave
        an empty "Untitled" tab sitting next to the real one.
        """
        if self.tabs.count() != 1:
            return None
        tab = self.tabs.widget(0)
        if isinstance(tab, DocumentTab) and not tab.path and not tab.modified and not tab.text:
            return tab
        return None

    def _discard_placeholder(self, tab: DocumentTab | None):
        if tab is None:
            return
        index = self.tabs.indexOf(tab)
        if index >= 0 and self.tabs.count() > 1:
            self.tabs.removeTab(index)
            tab.deleteLater()

    def save_current(self) -> bool:
        tab = self.current_document()
        if not tab:
            return False
        if not tab.path:
            # A day's note already knows where it belongs; asking would be
            # a dialog with one right answer.
            if tab.pending_path:
                Path(tab.pending_path).parent.mkdir(parents=True, exist_ok=True)
                return self._save_document(tab, tab.pending_path)
            return self.save_current_as()
        return self._save_document(tab, tab.path)

    def save_current_as(self) -> bool:
        tab = self.current_document()
        if not tab:
            return False
        if tab.path:
            suggested = tab.path
        else:
            save_dir = settings_manager.resolve_save_dir(self._cfg)
            suggested = str(save_dir / f"{self._safe_filename(tab.display_name)}.txt")
        path, selected_filter = QFileDialog.getSaveFileName(
            self, "Save As", suggested, FILE_FILTER
        )
        if not path:
            return False
        if not Path(path).suffix:
            path += ".md" if selected_filter.startswith("Markdown") else ".txt"
        return self._save_document(tab, path)

    def _save_document(self, tab: DocumentTab, path: str) -> bool:
        previous_path = tab.path
        try:
            write_text_file_atomic(path, tab.text, tab.encoding)
        except (OSError, UnicodeError) as exc:
            QMessageBox.critical(
                self, "Save Failed", f"The file could not be saved:\n{exc}"
            )
            return False
        tab.path = str(Path(path).resolve())
        if previous_path and os.path.normcase(previous_path) != os.path.normcase(tab.path):
            self._file_monitor.unwatch(previous_path)
        self._file_monitor.watch(tab.path)
        tab.mark_clean()
        remove_recovery(tab.recovery_id)
        self._add_recent(tab.path)
        note_index.touch(self._note_index, tab.path)
        self.notes_board.reload()
        self._document_state_changed(tab)
        self.statusBar().showMessage(f"Saved {tab.path}", 3000)
        return True

    def close_current_tab(self):
        if self.tabs.currentIndex() >= 0:
            self.close_tab(self.tabs.currentIndex())

    def close_tab(self, index: int, create_replacement: bool = True) -> bool:
        tab = self.tabs.widget(index)
        if not isinstance(tab, DocumentTab):
            return True
        if not self._confirm_close(tab):
            return False
        if tab.path:
            self._recently_closed.append(tab.path)
            del self._recently_closed[:-10]
            self._file_monitor.unwatch(tab.path)
        remove_recovery(tab.recovery_id)
        self.tabs.removeTab(index)
        tab.deleteLater()
        if (
            create_replacement
            and not self._closing_application
            and self.tabs.count() == 0
        ):
            self.new_document()
        return True

    def reopen_closed_tab(self):
        while self._recently_closed:
            path = self._recently_closed.pop()
            if Path(path).exists():
                self.open_file(path)
                return
        self.statusBar().showMessage("No recently closed tabs.", 2000)

    def _confirm_close(self, tab: DocumentTab) -> bool:
        if not tab.modified:
            return True
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(APP_TITLE)
        box.setText(f'Do you want to save changes to "{tab.display_name}"?')
        save_button = box.addButton("Save", QMessageBox.ButtonRole.AcceptRole)
        discard_button = box.addButton("Don't Save", QMessageBox.ButtonRole.DestructiveRole)
        cancel_button = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(save_button)
        box.exec()
        if box.clickedButton() == cancel_button:
            return False
        if box.clickedButton() == discard_button:
            return True
        self.tabs.setCurrentWidget(tab)
        return self.save_current()

    def _document_for_path(self, path: str) -> DocumentTab | None:
        normalized = os.path.normcase(str(Path(path).resolve()))
        for index in range(self.tabs.count()):
            tab = self.tabs.widget(index)
            if (
                isinstance(tab, DocumentTab)
                and tab.path
                and os.path.normcase(str(Path(tab.path).resolve())) == normalized
            ):
                return tab
        return None

    def _reload_document_from_disk(self, tab: DocumentTab) -> bool:
        if not tab.path:
            return False
        try:
            loaded = read_text_file(tab.path)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Reload Failed",
                f"The changed file could not be reloaded:\n{exc}",
            )
            self._file_monitor.acknowledge(tab.path)
            return False

        position = tab.editor.textCursor().position()
        tab.editor.setPlainText(loaded.text)
        cursor = tab.editor.textCursor()
        cursor.setPosition(min(position, len(loaded.text)))
        tab.editor.setTextCursor(cursor)
        tab.encoding = loaded.encoding
        tab.mark_clean()
        remove_recovery(tab.recovery_id)
        self._file_monitor.acknowledge(tab.path)
        self._document_state_changed(tab)
        self._update_status()
        self.statusBar().showMessage(f"Reloaded {tab.path}", 3000)
        return True

    def _keep_document_version(self, tab: DocumentTab, path: str):
        tab.editor.document().setModified(True)
        self._file_monitor.acknowledge(path)
        self._document_state_changed(tab)
        self.statusBar().showMessage(
            "Keeping the editor version. Save to overwrite the disk version.",
            5000,
        )

    def _save_external_copy(self, tab: DocumentTab) -> bool:
        if tab.path:
            source = Path(tab.path)
            suggested = source.with_name(f"{source.stem} copy{source.suffix}")
        else:
            suggested = settings_manager.resolve_save_dir(self._cfg) / "Untitled.txt"
        path, selected_filter = QFileDialog.getSaveFileName(
            self, "Save a Copy", str(suggested), FILE_FILTER
        )
        if not path:
            return False
        if not Path(path).suffix:
            path += ".md" if selected_filter.startswith("Markdown") else ".txt"
        return self._save_document(tab, path)

    def _external_file_changed(self, path: str):
        if self._closing_application:
            return
        tab = self._document_for_path(path)
        if tab is None:
            self._file_monitor.unwatch(path)
            return
        if not tab.modified:
            self._reload_document_from_disk(tab)
            return
        self.tabs.setCurrentWidget(tab)

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("File Changed on Disk")
        box.setText(f'"{tab.display_name}" was changed by another application.')
        if tab.modified:
            box.setInformativeText(
                "This tab also has unsaved changes. Choose which version to keep."
            )
        else:
            box.setInformativeText("Reload the newer version from disk?")
        reload_button = box.addButton("Reload", QMessageBox.ButtonRole.AcceptRole)
        keep_button = box.addButton(
            "Keep My Version", QMessageBox.ButtonRole.RejectRole
        )
        copy_button = box.addButton(
            "Save a Copy…", QMessageBox.ButtonRole.ActionRole
        )
        box.setDefaultButton(keep_button if tab.modified else reload_button)
        box.exec()

        if box.clickedButton() == reload_button:
            self._reload_document_from_disk(tab)
        elif box.clickedButton() == copy_button:
            if not self._save_external_copy(tab):
                self._keep_document_version(tab, path)
        else:
            self._keep_document_version(tab, path)

    def _external_file_missing(self, path: str):
        if self._closing_application:
            return
        tab = self._document_for_path(path)
        if tab is None:
            self._file_monitor.unwatch(path)
            return
        self.tabs.setCurrentWidget(tab)

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("File Missing")
        box.setText(f'"{tab.display_name}" was moved or deleted outside the app.')
        box.setInformativeText(
            "You can keep the document open, save it elsewhere, or close the tab."
        )
        keep_button = box.addButton("Keep Open", QMessageBox.ButtonRole.AcceptRole)
        copy_button = box.addButton("Save As…", QMessageBox.ButtonRole.ActionRole)
        close_button = box.addButton("Close Tab", QMessageBox.ButtonRole.DestructiveRole)
        box.setDefaultButton(keep_button)
        box.exec()

        if box.clickedButton() == copy_button:
            if self._save_external_copy(tab):
                return
        elif box.clickedButton() == close_button:
            self._file_monitor.unwatch(path)
            self.close_tab(self.tabs.indexOf(tab))
            return

        self._file_monitor.unwatch(path)
        tab.editor.document().setModified(True)
        self._document_state_changed(tab)
        self.statusBar().showMessage(
            "The missing file is kept open as an unsaved document.", 5000
        )

    def _dot_icon(self, modified: bool) -> QIcon:
        """The 6px status dot the design puts before a tab's name.

        Drawn rather than prefixed as "●": a bullet in the title lands on the
        wrong side of a Persian name, and only having one when the document is
        dirty made every tab jump a few pixels wider as you typed.
        """
        palette = current_palette()
        key = (palette["accent"] if modified else palette["border"], modified)
        cached = self._dot_icons.get(key)
        if cached is not None:
            return cached
        # Drawn oversized and handed to QIcon, which scales it down for
        # whatever DPI the screen turns out to be. Asking the widget for its
        # device pixel ratio here instead re-enters window creation and
        # overflows the stack — this runs while the window is still being
        # built, before it has a screen to ask about.
        side = TAB_DOT_SIZE * 4
        pixmap = QPixmap(side, side)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(key[0]))
        painter.drawEllipse(0, 0, side, side)
        painter.end()
        icon = QIcon(pixmap)
        self._dot_icons[key] = icon
        return icon

    def _document_state_changed(self, tab: DocumentTab):
        index = self.tabs.indexOf(tab)
        if index < 0:
            return
        self.tabs.setTabText(index, tab.display_name)
        self.tabs.setTabIcon(index, self._dot_icon(tab.modified))
        self.tabs.setTabToolTip(index, tab.path or "Unsaved document")
        if tab is self.current_document():
            self._update_status()
            marker = "● " if tab.modified else ""
            self.setWindowTitle(f"{marker}{tab.display_name} — {APP_TITLE}")

    def _current_tab_changed(self, _index):
        tab = self.current_document()
        if hasattr(self, "top_bar"):
            self._update_crumb()
        if hasattr(self, "links_panel"):
            QTimer.singleShot(0, self.refresh_links_panel)
        if hasattr(self, "format_bar"):
            self.format_bar.set_reading(bool(tab and tab.reading))
        if tab:
            self.direction_actions[tab.editor.direction_mode].setChecked(True)
            if tab.encoding in self.encoding_actions:
                self.encoding_actions[tab.encoding].setChecked(True)
            self._document_state_changed(tab)
            (tab.reader if tab.reading else tab.editor).setFocus()
        else:
            self.setWindowTitle(APP_TITLE)
        self._update_status()

    # Edit commands

    def _edit_command(self, method: str):
        """Send an edit command to the focused widget when it supports it,
        otherwise to the current editor. Keeps Ctrl+X/C/V… working inside
        the sidebar search box and dialogs."""
        widget = QApplication.focusWidget()
        if widget is not None and hasattr(widget, method):
            getattr(widget, method)()
            return
        tab = self.current_document()
        if tab:
            getattr(tab.editor, method)()

    def delete_selection(self):
        tab = self.current_document()
        if not tab:
            return
        cursor = tab.editor.textCursor()
        if cursor.hasSelection():
            cursor.removeSelectedText()

    @property
    def _find_dialog(self) -> FindReplaceDialog:
        if self._find_dialog_instance is None:
            self._find_dialog_instance = FindReplaceDialog(self)
        return self._find_dialog_instance

    def show_find_dialog(self):
        self._show_search_dialog(focus_replace=False)

    def show_replace_dialog(self):
        self._show_search_dialog(focus_replace=True)

    def _show_search_dialog(self, focus_replace: bool):
        tab = self.current_document()
        if tab:
            # Search walks the editor; it has to be on screen to show a match.
            tab.set_reading(False)
            selected = tab.editor.textCursor().selectedText()
            if selected and "\u2029" not in selected:
                self._find_dialog.find_input.setText(selected)
        self._find_dialog.show()
        self._find_dialog.raise_()
        self._find_dialog.activateWindow()
        target = (
            self._find_dialog.replace_input
            if focus_replace
            else self._find_dialog.find_input
        )
        target.setFocus()
        target.selectAll()

    def _has_search_term(self) -> bool:
        """Whether F3 has something to repeat — without building the dialog."""
        dialog = self._find_dialog_instance
        return dialog is not None and bool(dialog.find_input.text())

    def find_next(self):
        if not self._has_search_term():
            self.show_find_dialog()
            return
        self._find_dialog.find_next()

    def find_previous(self):
        if not self._has_search_term():
            self.show_find_dialog()
            return
        self._find_dialog.find_previous()

    def goto_line(self):
        tab = self.current_document()
        if not tab:
            return
        tab.set_reading(False)
        total = tab.editor.document().blockCount()
        current = tab.editor.textCursor().blockNumber() + 1
        line, accepted = QInputDialog.getInt(
            self, "Go To Line", f"Line number (1–{total}):", current, 1, total
        )
        if not accepted:
            return
        block = tab.editor.document().findBlockByNumber(line - 1)
        cursor = QTextCursor(block)
        tab.editor.setTextCursor(cursor)
        tab.editor.setFocus()

    def insert_time_date(self):
        tab = self.current_document()
        if not tab:
            return
        stamp = datetime.now().strftime("%H:%M %Y-%m-%d")
        tab.editor.textCursor().insertText(stamp)

    def set_direction(self, mode: str):
        tab = self.current_document()
        if tab:
            tab.editor.set_direction_mode(mode)
            self._direction_chosen(tab, mode)

    def _editor_direction_changed(self, mode: str):
        """The editor switched direction itself (Ctrl + left/right Shift)."""
        tab = self.current_document()
        if tab and self.sender() is tab.editor:
            self._direction_chosen(tab, mode)

    def _direction_chosen(self, tab: DocumentTab, mode: str):
        self.direction_actions[mode].setChecked(True)
        # Only a saved file has somewhere to remember the choice.
        if tab.path:
            note_index.set_direction(self._note_index, tab.path, mode)
        self._update_status()

    def _transform_selected_lines(self, transform):
        """Apply a line transform to every line touched by the selection,
        as one undoable edit."""
        tab = self.current_document()
        if not tab:
            return
        editor = tab.editor
        document = editor.document()
        cursor = editor.textCursor()
        first = document.findBlock(cursor.selectionStart()).blockNumber()
        last = document.findBlock(cursor.selectionEnd()).blockNumber()
        edit = QTextCursor(document)
        edit.beginEditBlock()
        try:
            for number in range(first, last + 1):
                block = document.findBlockByNumber(number)
                new_text = transform(block.text())
                if new_text != block.text():
                    line = QTextCursor(document)
                    line.setPosition(block.position())
                    line.setPosition(
                        block.position() + block.length() - 1,
                        QTextCursor.MoveMode.KeepAnchor,
                    )
                    line.insertText(new_text)
        finally:
            edit.endEditBlock()
        editor.setFocus()

    def toggle_bold(self):
        """Toggle **bold** around the selection (or the word under the
        cursor), Word-style: pressing it again removes the markers."""
        tab = self.current_document()
        if not tab:
            return
        editor = tab.editor
        cursor = editor.textCursor()
        if not cursor.hasSelection():
            cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        if not cursor.hasSelection():
            # Empty spot: drop a marker pair and type inside it.
            cursor.insertText("****")
            cursor.movePosition(
                QTextCursor.MoveOperation.Left,
                QTextCursor.MoveMode.MoveAnchor,
                2,
            )
            editor.setTextCursor(cursor)
            return

        document = editor.document()
        start, end = cursor.selectionStart(), cursor.selectionEnd()
        selected = cursor.selectedText()

        def _chars(position: int, count: int) -> str:
            probe = QTextCursor(document)
            probe.setPosition(max(0, position))
            probe.setPosition(
                min(document.characterCount() - 1, position + count),
                QTextCursor.MoveMode.KeepAnchor,
            )
            return probe.selectedText()

        cursor.beginEditBlock()
        try:
            if selected.startswith("**") and selected.endswith("**") and len(selected) > 4:
                replacement = selected[2:-2]
                cursor.insertText(replacement)
                new_start = start
            elif _chars(start - 2, 2) == "**" and _chars(end, 2) == "**":
                # The markers sit just outside the selection — remove them.
                wide = QTextCursor(document)
                wide.setPosition(start - 2)
                wide.setPosition(end + 2, QTextCursor.MoveMode.KeepAnchor)
                replacement = selected
                wide.insertText(replacement)
                new_start = start - 2
            else:
                # Bold is per-line in Markdown, so wrap each selected line.
                parts = selected.split("\u2029")
                replacement = "\u2029".join(
                    toggle_bold(part) if part.strip() else part for part in parts
                )
                cursor.insertText(replacement.replace("\u2029", "\n"))
                new_start = start
        finally:
            cursor.endEditBlock()

        restored = QTextCursor(document)
        restored.setPosition(new_start)
        restored.setPosition(
            new_start + len(replacement), QTextCursor.MoveMode.KeepAnchor
        )
        editor.setTextCursor(restored)
        editor.setFocus()

    def set_encoding(self, encoding: str):
        tab = self.current_document()
        if tab:
            tab.set_encoding(encoding)
            self.encoding_actions[encoding].setChecked(True)
            self._update_status()

    def toggle_word_wrap(self, checked: bool):
        self._cfg["word_wrap"] = checked
        settings_manager.save(self._cfg)
        for index in range(self.tabs.count()):
            editor = self.tabs.widget(index).editor
            editor.setLineWrapMode(
                editor.LineWrapMode.WidgetWidth
                if checked
                else editor.LineWrapMode.NoWrap
            )

    def change_zoom(self, delta: int):
        base = float(self._cfg.get("font_size", 14.5))
        self._zoom_steps = max(8 - base, min(96 - base, self._zoom_steps + delta))
        self._apply_editor_fonts()
        self._update_status()

    def reset_zoom(self):
        self._zoom_steps = 0
        self._apply_editor_fonts()
        self._update_status()

    def _apply_editor_fonts(self):
        latin = self._cfg.get("font_family_latin", "Inter")
        persian = self._cfg.get("font_family_persian", "Vazirmatn")
        size = self._effective_font_size()
        font = editor_font(latin, persian, size)
        for index in range(self.tabs.count()):
            tab = self.tabs.widget(index)
            tab.apply_font(font)
            tab.highlighter.rehighlight()

    def toggle_line_numbers(self, checked: bool):
        self._cfg["show_line_numbers"] = checked
        settings_manager.save(self._cfg)
        for index in range(self.tabs.count()):
            self.tabs.widget(index).editor.set_line_numbers_visible(checked)

    def set_notes_root(self, folder: str):
        self._cfg["notes_root"] = folder
        settings_manager.save(self._cfg)
        self.notes_board.set_root(folder)
        self.folder_sidebar.set_root(folder)
        if self._tasks_watcher is not None:
            self._tasks_watcher.set_root(folder)
        self.sync_now()

    def _read_sync_status(self):
        path = settings_manager.app_data_dir() / "cloud_sync_status.json"
        if not path.exists():
            self.top_bar.set_sync("همگام · نامشخص", "off",
                                  "هنوز گزارشی ثبت نشده؛ برای بررسی کلیک کن.")
            return None
        try:
            from core.note_library import edited_label

            data = json.loads(path.read_text(encoding="utf-8"))
            checked = datetime.fromisoformat(data["checked_at"]).astimezone()
            self._sync_report = data
            if data["state"] == "error":
                title, state = "خطای همگام‌سازی", "error"
            elif data["state"] == "attention":
                title, state = "همگام · نیاز به بررسی", "error"
            else:
                title, state = "همگام · " + edited_label(checked.timestamp()), "ok"
            self.top_bar.set_sync(
                title, state,
                "آخرین بررسی: " + to_persian_digits(checked.strftime("%H:%M"))
                + "\nتعارض: " + to_persian_digits(str(data.get("conflicts", 0)))
                + " · فایل در انتظار: " + to_persian_digits(str(data.get("skipped", 0)))
                + ("\n" + data["error"] if data.get("error") else "")
                + "\nبرای همگام‌سازی دوباره کلیک کن.")
            return checked
        except (OSError, ValueError, KeyError, TypeError):
            self.top_bar.set_sync("همگام · نامشخص", "off")
            return None

    def _sync_tick(self):
        if not cloud_config.load().enabled:
            self.top_bar.set_sync("همگام‌سازی خاموش", "off")
            return
        checked = self._read_sync_status()
        if checked is None or (datetime.now().astimezone() - checked).total_seconds() > 90:
            self.sync_now()

    def sync_now(self):
        if self._closing_application or (self._sync_worker and self._sync_worker.isRunning()):
            return
        settings = cloud_config.load()
        if not settings.enabled:
            log.debug('Sync is disabled', extra={'event': 'sync.skipped', 'reason': 'disabled'})
            self.top_bar.set_sync("همگام‌سازی خاموش", "off")
            return
        if not (settings.url and settings.key):
            log.warning('Sync requires a service and readable credential', extra={'event': 'sync.skipped', 'reason': 'unconfigured'})
            self.top_bar.set_sync("همگام · تنظیم نشده", "off",
                                  "آدرس سرور و کلید را در تنظیمات ← همگام‌سازی بگذار.")
            return
        if settings.device_id and str(Path(self._cfg["notes_root"]).resolve()) != settings.confirmed_root:
            log.warning('Sync folder needs confirmation', extra={'event': 'sync.skipped', 'reason': 'folder_unconfirmed'})
            self.top_bar.set_sync("همگام · تأیید پوشه", "off",
                                  "پوشهٔ یادداشت‌ها تغییر کرده است؛ در تنظیمات، اتصال این پوشه را دوباره تأیید کن.")
            return
        try:
            protected = {tab.path for index in range(self.tabs.count())
                         if (tab := self.tabs.widget(index)).path and tab.modified}
            self._sync_worker = CloudSyncWorker(
                self._cfg["notes_root"], settings_manager.app_data_dir() / "cloud_sync_state.json",
                settings.url, settings.key, protected, self, settings.proxy, settings.user_id, settings.excluded_paths)
            worker = self._sync_worker
            worker.completed.connect(self._sync_finished)
            worker.finished.connect(worker.deleteLater)
            worker.finished.connect(lambda: self._clear_sync_worker(worker))
            self.top_bar.set_sync("در حال همگام‌سازی…", "busy")
            worker.start()
        except (OSError, ValueError, KeyError) as exc:
            self.top_bar.set_sync("همگام · نامشخص", "off", f"تنظیم همگام‌سازی پیدا نشد: {exc}")

    def _sync_finished(self, result, error: str):
        if self._closing_application:
            return
        self._read_sync_status()
        if error:
            self.top_bar.set_sync("خطای همگام‌سازی", "error", error + "\nبرای تلاش دوباره کلیک کن.")
            self.statusBar().showMessage(f"همگام‌سازی انجام نشد: {error}", 10000)
            return
        if result.downloaded or result.uploaded or result.deleted:
            self.notes_board.reload()
            self._notify_tasks_changed()
        if result.conflicts:
            self.statusBar().showMessage(f"تعارض همگام‌سازی: {result.conflicts}", 10000)
        elif result.skipped:
            self.statusBar().showMessage(
                f"{result.skipped} فایل باز یا تغییرکرده در انتظار است.", 8000)

    SYNC_EXIT_WAIT_MS = 15_000

    def _finish_background_work(self):
        """Let a sync in flight land before the process goes.

        Qt aborts the whole process when a QThread is destroyed while still
        running. Quitting mid-sync did that; so did quitting during the task
        scan, which on a cold first launch was still walking the folder.
        """
        self._closing_application = True
        self.updates.stop()
        self._sync_timer.stop()
        self.notes_board.stop_loading()
        self._links_timer.stop()
        if self._links_worker is not None:
            self._links_worker.requestInterruption()
        self.settings_overlay.wait_for_test()
        if self._tasks_watcher is not None:
            self._tasks_watcher.stop()
        worker = self._sync_worker
        if worker is not None and worker.isRunning():
            if not worker.wait(self.SYNC_EXIT_WAIT_MS):
                log.warning("Cloud sync still running at exit")

    def _clear_sync_worker(self, worker):
        if self._sync_worker is worker:
            self._sync_worker = None

    def set_theme(self, theme: str):
        self._cfg["theme"] = theme
        settings_manager.save(self._cfg)
        self.theme_actions[theme].setChecked(True)
        self._restyle()

    def _restyle(self):
        """Rebuild the stylesheet from the current theme and palette.

        The editor paints its markers itself, and so do the tab close
        buttons, so those have to be recoloured here — a stylesheet swap
        alone leaves them on the outgoing palette's colours.
        """
        QApplication.instance().setStyleSheet(
            build_stylesheet(
                self._cfg.get("theme", "system"),
                self._cfg.get("accent_palette", "graphite"),
            )
        )
        self._dot_icons.clear()
        # The painted v4 surfaces read the palette at paint time; they only
        # need to be told to paint again. The one QLineEdit in each quick-add
        # field carries a small sheet of its own.
        for widget in (self.top_bar, self.navigation_rail, self.folder_sidebar,
                       self.notes_board, self.rail):
            widget.refresh_palette()
        self.update()
        for widget in (self.tab_strip, self.format_bar, self.editor_status, self.links_panel):
            widget.update()
            for child in widget.findChildren(QWidget):
                child.update()
        self.document_tab_bar.refresh_close_icons()
        for index in range(self.tabs.count()):
            tab = self.tabs.widget(index)
            tab.highlighter.rehighlight()
            tab.refresh_reading()
            self.tabs.setTabIcon(index, self._dot_icon(tab.modified))

    def show_settings(self, section: str = "look"):
        """Ctrl+, — the design's settings panel; every change applies at once."""
        self.settings_overlay.open_with(self._settings_state(),
                                        section if isinstance(section, str) else "look")

    def show_shortcuts(self):
        self.show_settings("keys")

    def _app_update_available(self, version):
        self.update_action.setText('نسخهٔ ' + to_persian_digits(version) + ' آماده است…')
        self.flash('نسخهٔ جدید آماده است؛ تنظیمات ← به‌روزرسانی را باز کن.')

    def _install_app_update(self, update):
        if self._sync_worker is not None and self._sync_worker.isRunning():
            self.updates.message = 'همگام‌سازی در حال اجراست؛ پس از پایان آن، نصب را دوباره بزن.'
            return
        # Installation is deferred until main() has left the event loop.
        # An unsaved-document Cancel therefore cannot start the installer.
        self.updates.pending_install = update
        self.quit_application()
        if not self._closing_application:
            self.updates.pending_install = None
            self.updates.message = 'خروج لغو شد؛ نسخهٔ دریافت‌شده برای نصب بعدی آماده است.'

    def show_about(self):
        QMessageBox.about(
            self,
            f"About {APP_TITLE}",
            f"<h3>{APP_TITLE}</h3>"
            f"<p>Version {APP_VERSION}</p>"
            "<p>A fast, minimal text editor for Windows with first-class "
            "support for both English and Persian text.</p>"
            "<p>Automatic RTL/LTR paragraph direction, code block detection, "
            "to-do lists, atomic saves and crash recovery.</p>"
            "<p><b>Developer:</b> Sajjad Shadloo</p>",
        )

    def _update_status(self):
        """Queue a status-bar refresh.

        Every keystroke reaches here twice — once for the text change and once
        for the cursor move — and the refresh counts words over the whole
        document. Collapsing both into a single deferred call halves that work
        and keeps it off the keystroke itself.
        """
        self._status_timer.start()

    def _refresh_status(self):
        tab = self.current_document()
        if not tab:
            return
        status = self.editor_status
        cursor = tab.editor.textCursor()
        status.set_position(cursor.blockNumber() + 1, cursor.positionInBlock() + 1)
        document = tab.editor.document()
        if document.characterCount() <= WORD_COUNT_LIMIT:
            tasks = len(parse_document(tab.text))
        else:
            tasks = 0
        status.set_counts(document.blockCount(), tasks)
        base = float(self._cfg.get("font_size", 14.5))
        status.set_zoom(round(self._effective_font_size() / base * 100))
        kind = "Markdown" if (tab.path or tab.pending_path or "").lower().endswith(
            (".md", ".markdown")) or not (tab.path or tab.pending_path) else "Text"
        status.format.set_text(kind + " · " + tab.encoding.upper().replace("UTF-8-SIG", "UTF-8 BOM"))
        rtl = tab.editor.current_direction() == "rtl"
        label = "راست‌چین" if rtl else "چپ‌چین"
        if tab.editor.direction_mode == "auto":
            label += " · خودکار"
        status.direction.set_text(label)
        self.format_bar.set_direction_label(rtl)
        status.set_saved(not tab.modified)
        self.document_tab_bar.update()

    # Recent files, recovery, migration

    def _add_recent(self, path: str):
        self._cfg = settings_manager.add_recent_file(self._cfg, path)

    def _refresh_recent_menu(self):
        """Build the Recent Files menu without touching the filesystem.

        Probing each entry here froze the menu whenever one of them lived on a
        disconnected network share or a removed USB drive. A path that has
        gone away is dropped when opening it fails instead.
        """
        self.recent_menu.clear()
        recent = self._cfg.get("recent_files", [])
        if not recent:
            empty = self.recent_menu.addAction("(empty)")
            empty.setEnabled(False)
            return
        for position, path in enumerate(recent, start=1):
            action = self.recent_menu.addAction(f"&{position % 10}  {path}")
            action.triggered.connect(
                lambda checked=False, selected=path: self._open_recent(selected)
            )
        self.recent_menu.addSeparator()
        clear_action = self.recent_menu.addAction("Clear List")
        clear_action.triggered.connect(self._clear_recent)

    def _open_recent(self, path: str):
        """Open a recent entry, forgetting it when it is no longer there."""
        if self.open_file(path):
            return
        remaining = [
            item
            for item in self._cfg.get("recent_files", [])
            if os.path.normcase(item) != os.path.normcase(path)
        ]
        if remaining != self._cfg.get("recent_files", []):
            self._cfg["recent_files"] = remaining
            settings_manager.save(self._cfg)

    def _clear_recent(self):
        self._cfg["recent_files"] = []
        settings_manager.save(self._cfg)

    def _write_recoveries(self):
        """Snapshot every unsaved tab — but only the ones that actually moved.

        ``modified`` stays true from the first edit until the file is saved,
        so without the fingerprint check this rewrote the full text of every
        dirty tab to disk every ten seconds even when nothing had changed.
        """
        live_ids = set()
        for index in range(self.tabs.count()):
            tab = self.tabs.widget(index)
            recovery_id = tab.recovery_id
            live_ids.add(recovery_id)
            if not tab.modified:
                if recovery_id in self._recovery_on_disk:
                    remove_recovery(recovery_id)
                    self._recovery_on_disk.discard(recovery_id)
                    self._recovery_marks.pop(recovery_id, None)
                continue
            text = tab.text
            mark = (len(text), hash(text), tab.path, tab.encoding, tab.display_name)
            if self._recovery_marks.get(recovery_id) == mark:
                continue
            save_recovery(
                recovery_id,
                text=text,
                path=tab.path,
                encoding=tab.encoding,
                title=tab.display_name,
                direction_mode=tab.editor.direction_mode,
            )
            self._recovery_marks[recovery_id] = mark
            self._recovery_on_disk.add(recovery_id)
        # Drop bookkeeping for tabs that have since been closed.
        for stale in set(self._recovery_marks) - live_ids:
            del self._recovery_marks[stale]
        self._recovery_on_disk &= live_ids

    def showEvent(self, event):
        super().showEvent(event)
        # Deferred by one event-loop turn so the window is painted and has
        # focus before anything modal appears on top of it.
        QTimer.singleShot(0, self._run_startup_prompts)
        if getattr(self, "_review_checked", False):
            QTimer.singleShot(300, self._maybe_morning_review)

    def _run_startup_prompts(self):
        # Guarded here rather than in showEvent: showing the window again
        # (restore, un-minimise, a second instance raising us) must never
        # re-offer recovery and duplicate every recovered document.
        if self._startup_prompts_shown or not self.isVisible():
            return
        self._startup_prompts_shown = True
        self.raise_()
        self.activateWindow()
        self._offer_recovery()
        QTimer.singleShot(250, self._offer_legacy_migration)
        self._rename_legacy_tasks_file()
        self._import_legacy_daily_notes()
        self._start_task_watcher()
        if self._cfg.get("day_widget"):
            self._show_day_widget()

    def _rename_legacy_tasks_file(self):
        """کارها.md became tasks.md in 4.2.5. Left alone while it is open,
        so a tab never ends up pointing at a file that is no longer there."""
        root = self._cfg["notes_root"]
        if self._tab_for_path(str(Path(root) / task_file.LEGACY_NAME)):
            return
        try:
            task_file.rename_legacy_file(root)
        except OSError:
            log.warning("Could not rename the tasks file", exc_info=True)

    def _import_legacy_daily_notes(self):
        """Fold a 4.1 Daily folder into the one tasks file — once.

        A day file is removed only when everything in it was taken; one that
        also holds prose stays, because that prose is a note. Latched in
        settings: after this there is no Daily folder to walk.
        """
        if self._cfg.get("daily_cleanup_done"):
            return
        self._cfg["daily_cleanup_done"] = True
        settings_manager.save(self._cfg)
        try:
            moved = task_file.import_daily_notes(self._cfg["notes_root"])
        except OSError:
            log.warning("Could not fold in the Daily folder", exc_info=True)
            return
        if not moved:
            return
        log.info("Moved %d task(s) out of the Daily folder", moved)
        self.notes_board.reload()
        self.statusBar().showMessage(
            to_persian_digits(f"{moved} کار به فایل کارها منتقل شد"), 5000
        )

    def toggle_day_widget(self, shown: bool | None = None):
        """Ctrl+Shift+W — the small panel that sits on the desktop."""
        if shown is None:
            shown = self._day_widget is None or not self._day_widget.isVisible()
        self._cfg["day_widget"] = bool(shown)
        settings_manager.save(self._cfg)
        self.day_widget_action.setChecked(bool(shown))
        self.top_bar.set_widget_active(bool(shown))
        if not shown:
            if self._day_widget is not None:
                self._day_widget.hide()
            return
        self._show_day_widget()

    def _show_day_widget(self):
        if self._day_widget is None:
            self._day_widget = DayWidget()
            self._day_widget.task_toggled.connect(self.set_task_done)
            self._day_widget.task_delete_requested.connect(self.delete_task)
            self._day_widget.task_opened.connect(self._open_task_from_widget)
            self._day_widget.open_requested.connect(self._reveal_window)
            self._day_widget.closed.connect(
                lambda: self.toggle_day_widget(False)
            )
            self._day_widget.moved.connect(self._remember_widget_position)
            self._day_widget.place(
                self.screen(), self._cfg.get("day_widget_position")
            )
        self._day_widget.show()
        self._start_task_watcher()
        self.refresh_day_widget()
        if self._tasks_watcher is not None:
            self._tasks_watcher.check_now()

    def _remember_widget_position(self, point):
        self._cfg["day_widget_position"] = [point.x(), point.y()]
        settings_manager.save(self._cfg)

    def refresh_day_widget(self):
        if self._day_widget is not None and self._tasks_watcher is not None:
            self._day_widget.set_tasks(self._tasks_watcher.all_tasks())

    def _open_task_from_widget(self, path: str, line_number: int):
        self._reveal_window()
        self.open_task_in_editor(path, line_number)

    def _reveal_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def has_tray(self) -> bool:
        return self._tray is not None

    def start_in_background(self):
        """A --minimized start: no window, but tasks and the widget are live."""
        self._start_task_watcher()
        if self._cfg.get("day_widget"):
            self._show_day_widget()

    # Win+Alt+N from anywhere in Windows
    #
    # Caught by an application-wide native event filter, never by overriding
    # nativeEvent on the window: PyQt calls an override for the messages sent
    # while the native window is being created — which restoring a maximized
    # geometry does inside __init__ — and that crashed the process on start.
    # The filter only sees messages taken from the queue, where WM_HOTKEY is.

    _HOTKEY_ID = 0x4E50  # "NP"

    def register_global_hotkey(self):
        """Quick capture from any app. Silently skipped if Windows refuses —
        another program may already own the combination."""
        if sys.platform != "win32":
            return
        try:
            import ctypes

            MOD_ALT, MOD_WIN, MOD_NOREPEAT, VK_N = 0x0001, 0x0008, 0x4000, 0x4E
            self._hotkey_ok = bool(ctypes.windll.user32.RegisterHotKey(
                int(self.winId()), self._HOTKEY_ID, MOD_ALT | MOD_WIN | MOD_NOREPEAT, VK_N))
            if self._hotkey_ok:
                self._hotkey_filter = HotkeyFilter(self._HOTKEY_ID, self.show_quick_capture)
                app = QApplication.instance()
                app.installNativeEventFilter(self._hotkey_filter)
                # A quit need not pass through closeEvent; a Python filter
                # still installed while Qt tears the application down kills
                # the process on the way out.
                app.aboutToQuit.connect(self._unregister_global_hotkey)
        except Exception:
            self._hotkey_ok = False
            log.warning("Could not register Win+Alt+N", exc_info=True)

    def _unregister_global_hotkey(self):
        if sys.platform == "win32" and getattr(self, "_hotkey_ok", False):
            try:
                import ctypes

                ctypes.windll.user32.UnregisterHotKey(int(self.winId()), self._HOTKEY_ID)
            except Exception:
                pass
        hotkey_filter = getattr(self, "_hotkey_filter", None)
        if hotkey_filter is not None:
            QApplication.instance().removeNativeEventFilter(hotkey_filter)
            self._hotkey_filter = None

    def _install_tray(self):
        """Put the app in the notification area, if there is one.

        Without a tray there is nowhere to hide to, so the window keeps its
        ordinary behaviour and closing it ends the process as before.
        """
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self._tray = Tray(_app_icon(), self)
        self._tray.show()
        # The window is no longer what keeps the process alive.
        QApplication.setQuitOnLastWindowClosed(False)

    # Pages

    # "home" is the notes and the rail together; "editor" is a document.
    PAGE_INDEX = {"home": 0, "editor": 1, "tasks": 2, "calendar": 2}

    def show_page(self, key: str):
        if key in {"tasks", "calendar"}:
            self._ensure_tasks_workspace()
        index = self.PAGE_INDEX.get(key)
        if index is None:
            return
        self.pages.setCurrentIndex(index)
        self._page = key
        self.top_bar.set_page(key)
        self.navigation_rail.set_page(key)
        if key in {"tasks", "calendar"} and self.tasks_workspace is not None:
            self.tasks_workspace.set_mode("calendar" if key == "calendar" else "tasks")
        self._cfg["page"] = key
        settings_manager.save(self._cfg)
        # Home is a view over files anything may have changed, so it re-reads
        # on the way in rather than trusting what it last drew.
        if key == "home":
            self.notes_board.reload()
            self.folder_sidebar.set_categories(
                self.notes_board.category_names(), self.notes_board.category_counts()
            )
            self.refresh_tasks()
        elif key == "editor":
            tab = self.current_document()
            if tab:
                tab.editor.setFocus()
        else:
            self.refresh_tasks()
        self._update_crumb()

    def open_note_from_board(self, path: str):
        if self.open_file(path):
            self.show_page("editor")

    def new_note_from_board(self):
        self.new_document()
        self.show_page("editor")

    def open_task_in_editor(self, path: str, line_number: int):
        self._open_task(path, line_number)
        self.show_page("editor")

    def refresh_tasks(self):
        """Hand the rail every dated task."""
        if self._tasks_watcher is None:
            self._start_task_watcher()
        if self._tasks_watcher is not None:
            tasks = self._tasks_watcher.all_tasks()
            self.rail.set_tasks(tasks)
            if self.tasks_workspace is not None:
                self.tasks_workspace.set_tasks(tasks)
            self._tasks_watcher.check_now()

    def _ensure_tasks_workspace(self):
        if self.tasks_workspace is not None:
            return
        workspace = TasksWorkspace(line_reader=self.task_line)
        workspace.task_toggled.connect(self.set_task_done)
        workspace.task_delete_requested.connect(self.delete_task)
        workspace.task_opened.connect(self.open_task_in_editor)
        workspace.task_added.connect(self._workspace_add_task)
        workspace.task_rescheduled.connect(self.set_task_day)
        workspace.added_elsewhere.connect(self.flash)
        workspace.day_chosen.connect(self.rail.show_day)
        self.pages.insertWidget(2, workspace)
        self.pages.removeWidget(self._tasks_placeholder)
        self._tasks_placeholder.deleteLater()
        self.tasks_workspace = workspace
        if self._tasks_watcher is not None:
            workspace.set_tasks(self._tasks_watcher.all_tasks())

    def _add_day_task(self, day, text: str):
        if not self.add_task_to_day(day, text):
            return
        # Read the file back now. The background scan will agree in a minute
        # or two, but waiting for it means typing a task and watching the day
        # stay empty, which reads as nothing having happened.
        self._reread_tasks_for(day)
        self.statusBar().showMessage("کار اضافه شد", 2500)

    def _workspace_add_task(self, day, text: str):
        if text.strip():
            self._add_day_task(day, text)
        else:
            self.show_quick_capture(day)

    def show_quick_capture(self, day=None):
        """Alt+N (and Win+Alt+N from anywhere): one line, task or inbox note."""
        self._reveal_window()
        self.quick_capture.open_fresh()

    def _save_quick_note(self, text: str):
        """Write a captured thought into Inbox/, the same folder the bot uses.

        A timestamp keeps the name collision-free; the first line becomes
        the note's Markdown heading.
        """
        root = Path(self._cfg["notes_root"])
        inbox = root / "Inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        first = next((line.strip("# ") for line in text.splitlines() if line.strip()), "یادداشت سریع")
        safe = "".join(ch for ch in first[:36] if ch not in '<>:"/\\|?*').strip() or "یادداشت سریع"
        path = inbox / f"{datetime.now():%Y%m%d-%H%M%S}-{safe}.md"
        body = text if text.lstrip().startswith("#") else f"# {first}\n\n{text}"
        write_text_file_atomic(str(path), body, "UTF-8")
        self.notes_board.reload()
        self.folder_sidebar.set_categories(
            self.notes_board.category_names(), self.notes_board.category_counts()
        )
        self.flash("در «ورودی‌ها» ذخیره شد")

    def _reread_tasks_for(self, day):
        path = task_file.path_for(self._cfg["notes_root"])
        if not path.exists():
            return
        try:
            found = parse_document(
                read_text_file(path).text, str(path.resolve())
            )
        except (OSError, UnicodeError):
            log.warning("Could not re-read %s", path, exc_info=True)
            return
        self.rail.replace_day(
            day, [t for t in found if t.due and t.due.date() == day]
        )

    def _start_task_watcher(self):
        """Begin keeping the task counts fresh.

        Started here rather than in __init__ so nothing about it can show up
        in startup time; the watcher itself defers its first scan further and
        does the folder walk on a worker thread.
        """
        if self._tasks_watcher is not None:
            return
        self._tasks_watcher = TaskWatcher(self._cfg["notes_root"], self)
        self._tasks_watcher.open_count_changed.connect(self.update_open_task_count)
        # The calendar redraws from every completed scan, so a change made in
        # the editor shows up there without anyone asking.
        self._tasks_watcher.scanned.connect(self._update_task_surfaces)
        self._tasks_watcher.scanned.connect(self.refresh_day_widget)
        self._tasks_watcher.start()

    def _update_task_surfaces(self):
        if self._tasks_watcher is None:
            return
        tasks = self._tasks_watcher.all_tasks()
        self.rail.set_tasks(tasks)
        if self.tasks_workspace is not None:
            self.tasks_workspace.set_tasks(tasks)
        if self.review.isVisible():
            self._refill_review()
        if not getattr(self, "_review_checked", False):
            # The first scan after start is what the morning review needs.
            self._review_checked = True
            QTimer.singleShot(300, self._maybe_morning_review)

    def _tab_for_pending(self, path: str) -> DocumentTab | None:
        """An open, still-unsaved document already aimed at this filename."""
        target = os.path.normcase(os.path.abspath(path))
        for index in range(self.tabs.count()):
            tab = self.tabs.widget(index)
            if (
                isinstance(tab, DocumentTab)
                and not tab.path
                and tab.pending_path
                and os.path.normcase(os.path.abspath(tab.pending_path)) == target
            ):
                return tab
        return None

    def _tab_for_path(self, path: str) -> DocumentTab | None:
        target = os.path.normcase(os.path.abspath(path))
        for index in range(self.tabs.count()):
            tab = self.tabs.widget(index)
            if tab.path and os.path.normcase(os.path.abspath(tab.path)) == target:
                return tab
        return None

    def rewrite_task_line(self, path: str, line_number: int, transform) -> bool:
        """Apply `transform` to one line of a note, wherever that note lives.

        A note that is open is edited through its document, so the change
        joins that tab's undo stack and any unsaved work in it survives; only
        a note nobody has open is rewritten on disk. Every surface that
        changes a task — the calendar, the day widget, the tasks window —
        goes through here, because getting this wrong loses typing.

        `transform` returns the new line, or None to leave it alone.
        """
        tab = self._tab_for_path(path)
        if tab is not None:
            block = tab.editor.document().findBlockByNumber(line_number)
            if not block.isValid():
                return False
            changed = transform(block.text())
            if changed is None or changed == block.text():
                return False
            # Anchored from the start of the block to its end rather than
            # QTextCursor.BlockUnderCursor, which also takes the newline
            # before it — replacing that joined the line onto the one above.
            # One edit block, so a single Ctrl+Z takes the whole thing back.
            cursor = QTextCursor(block)
            cursor.beginEditBlock()
            cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            cursor.movePosition(
                QTextCursor.MoveOperation.EndOfBlock,
                QTextCursor.MoveMode.KeepAnchor,
            )
            cursor.insertText(changed)
            cursor.endEditBlock()
            return True

        try:
            loaded = read_text_file(path)
            lines = loaded.text.splitlines(keepends=True)
            if line_number >= len(lines):
                return False
            original = lines[line_number]
            body = original.rstrip(NEWLINE_CHARS)
            changed = transform(body)
            if changed is None or changed == body:
                return False
            lines[line_number] = changed + original[len(body):]
            write_text_file_atomic(path, "".join(lines), loaded.encoding)
        except (OSError, UnicodeError):
            log.warning("Could not rewrite %s line %s", path, line_number, exc_info=True)
            return False
        return True

    def _snooze_task(self, path: str, line_number: int, days: int):
        """Push one task's date forward by `days`."""
        if self.rewrite_task_line(
            path, line_number, lambda line: shift_stamp(line, days)
        ):
            self.statusBar().showMessage("کار به فردا موکول شد", 3000)
            self._notify_tasks_changed()
        else:
            self.statusBar().showMessage("تعویق این کار ممکن نشد", 4000)

    def set_task_day(self, path: str, line_number: int, day):
        """Give one task a new date, keeping its time and its ↻."""
        def transform(line: str):
            task = parse_task(line)
            if task is None:
                return None
            at = task.due.time() if (task.due and task.has_time) else None
            return set_stamp(line, day, at)

        if self.rewrite_task_line(path, line_number, transform):
            from core.when import day_label

            self.flash("به کارهای " + day_label(day) + " منتقل شد")
            self._notify_tasks_changed()
            self.refresh_tasks()

    def task_line(self, path: str, line_number: int) -> str | None:
        return self._task_line(path, line_number)

    def set_task_done(self, path: str, line_number: int, done: bool):
        """Tick or untick one task from a surface outside the editor."""
        def transform(line: str):
            task = parse_task(line)
            return None if task is None or task.done == done else toggle_done(line)

        if self.rewrite_task_line(path, line_number, transform):
            self._notify_tasks_changed()

    def add_task_to_day(self, day, text: str) -> bool:
        """Add a dated task to the one tasks file."""
        if not text.strip():
            return False
        try:
            path = task_file.add_task(self._cfg["notes_root"], day, text)
        except (OSError, UnicodeError):
            log.warning("Could not add a task for %s", day, exc_info=True)
            self.statusBar().showMessage("افزودن این کار ممکن نشد", 4000)
            return False
        # The note may be open with unsaved edits; reloading it underneath
        # would lose them, so say so instead of silently diverging.
        tab = self._tab_for_path(str(path))
        if tab is not None and not tab.modified:
            self._reload_document_from_disk(tab)
        self.notes_board.reload()
        self._notify_tasks_changed()
        return True

    def delete_task(self, path: str, line_number: int):
        """Remove one task's line from its file, after asking.

        The line goes for good — unlike a note, there is no Recycle Bin for
        part of a file — so the text is shown in the question rather than a
        bare "are you sure".
        """
        line = self._task_line(path, line_number)
        if line is None:
            return
        task = parse_task(line)
        label = task.text if task else line.strip()
        if (
            QMessageBox.question(
                self,
                "حذف کار",
                'این کار حذف شود؟' + chr(10) + chr(10) + label,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        if self._remove_line(path, line_number):
            self.statusBar().showMessage("کار حذف شد", 2500)
            self._notify_tasks_changed()
            self.refresh_tasks()

    def _task_line(self, path: str, line_number: int) -> str | None:
        tab = self._tab_for_path(path)
        if tab is not None:
            block = tab.editor.document().findBlockByNumber(line_number)
            return block.text() if block.isValid() else None
        try:
            lines = read_text_file(path).text.splitlines()
        except (OSError, UnicodeError):
            return None
        return lines[line_number] if line_number < len(lines) else None

    def _remove_line(self, path: str, line_number: int) -> bool:
        """Drop one whole line, through the document when the file is open."""
        tab = self._tab_for_path(path)
        if tab is not None:
            block = tab.editor.document().findBlockByNumber(line_number)
            if not block.isValid():
                return False
            cursor = QTextCursor(block)
            cursor.beginEditBlock()
            cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
            cursor.removeSelectedText()
            # BlockUnderCursor leaves the newline behind on the first block.
            if block.blockNumber() == 0:
                cursor.deleteChar()
            cursor.endEditBlock()
            return True
        try:
            loaded = read_text_file(path)
            lines = loaded.text.splitlines(keepends=True)
            if line_number >= len(lines):
                return False
            del lines[line_number]
            write_text_file_atomic(path, "".join(lines), loaded.encoding)
        except (OSError, UnicodeError):
            log.warning("Could not delete line %s of %s", line_number, path, exc_info=True)
            return False
        return True

    def delete_note(self, path: str):
        """Send a note to the Recycle Bin, after asking.

        The Bin rather than an unlink: a note is the user's writing and a
        wrong click has to be recoverable. Where there is no Bin, the
        question says so instead of quietly deleting.
        """
        name = Path(path).name
        recoverable = trash.available()
        question = (
            'یادداشت «' + name + '» حذف شود؟'
            + chr(10) + chr(10)
            + ("به سطل بازیافت می‌رود." if recoverable else "بازگرداندنش ممکن نیست.")
        )
        if (
            QMessageBox.question(
                self,
                "حذف یادداشت",
                question,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return

        tab = self._tab_for_path(path)
        self._file_monitor.unwatch(path)

        removed = trash.send_to_recycle_bin(path) if recoverable else self._unlink(path)
        if not removed:
            if tab is not None:
                self._file_monitor.watch(path)
            QMessageBox.critical(self, "حذف نشد", "این یادداشت حذف نشد.")
            return
        if tab is not None:
            index = self.tabs.indexOf(tab)
            if index >= 0:
                tab.mark_clean()
                self.close_tab(index)
        self.notes_board.reload()
        self._notify_tasks_changed()
        self.statusBar().showMessage("یادداشت حذف شد", 2500)

    @staticmethod
    def _unlink(path: str) -> bool:
        try:
            Path(path).unlink()
        except OSError:
            log.warning("Could not delete %s", path, exc_info=True)
            return False
        return True

    def _notify_tasks_changed(self):
        """Every task surface re-reads after a change, so none drifts."""
        if self._tasks_watcher is not None:
            self._tasks_watcher.check_now()
        self.tasks_changed.emit()

    def _open_task(self, path: str, line_number: int):
        """Jump to the exact line a task came from."""
        if not self.open_file(path):
            return
        tab = self.current_document()
        block = tab.editor.document().findBlockByNumber(line_number)
        if block.isValid():
            tab.editor.setTextCursor(QTextCursor(block))
        tab.editor.setFocus()
        self.setWindowState(
            (self.windowState() & ~Qt.WindowState.WindowMinimized)
            | Qt.WindowState.WindowActive
        )
        self.show()
        self.raise_()
        self.activateWindow()

    def _offer_recovery(self) -> bool:
        recoveries = load_recoveries()
        if not recoveries:
            return False
        answer = QMessageBox.question(
            self,
            "Recover Documents",
            f"{len(recoveries)} unsaved document(s) from the previous session "
            "were found.\nDo you want to recover them?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            clear_all_recoveries()
            return False
        # The blank document created at startup makes way for the real ones.
        placeholder = self._placeholder_tab()
        for item in recoveries:
            self._make_document(
                text=item.get("text", ""),
                path=item.get("path"),
                encoding=item.get("encoding", "utf-8"),
                recovery_id=item.get("id"),
                direction_mode=item.get("direction_mode") or self._default_direction(),
                title=f"{item.get('title', 'Untitled')} (recovered)",
            )
            tab = self.current_document()
            tab.editor.document().setModified(True)
            # Its snapshot file already exists, so the timer must know it is
            # there — otherwise saving the tab would leave the file behind.
            self._recovery_on_disk.add(tab.recovery_id)
            self._document_state_changed(tab)
        self._discard_placeholder(placeholder)
        return True

    def _offer_legacy_migration(self):
        # A hidden window must never raise a modal prompt: the deferred
        # timer can fire after the window closed (or in tests).
        if not self.isVisible():
            return
        if self._cfg.get("migration_checked") or not legacy_notes_available():
            return
        answer = QMessageBox.question(
            self,
            "Import Old Notes",
            "Notes from a previous version were found.\n"
            "Do you want to convert them to Markdown files?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer == QMessageBox.StandardButton.Yes:
            folder = QFileDialog.getExistingDirectory(
                self, "Destination Folder", self._start_directory()
            )
            if folder:
                try:
                    created = migrate_legacy_notes(folder)
                    QMessageBox.information(
                        self,
                        "Import Complete",
                        f"{len(created)} note(s) were converted to Markdown files.",
                    )
                except Exception as exc:
                    QMessageBox.critical(
                        self, "Import Failed", f"The import failed:\n{exc}"
                    )
                    return
            else:
                return
        self._cfg["migration_checked"] = True
        settings_manager.save(self._cfg)

    # Window integration

    def open_from_another_instance(self, paths: list[str]):
        """A second launch handed us its file paths: open them and come to
        the front (an empty list still raises the window)."""
        for path in paths:
            if os.path.isfile(path):
                self.open_file(path)
        self.setWindowState(
            (self.windowState() & ~Qt.WindowState.WindowMinimized)
            | Qt.WindowState.WindowActive
        )
        self.show()
        self.raise_()
        self.activateWindow()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and any(
            url.isLocalFile() for url in event.mimeData().urls()
        ):
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if url.isLocalFile() and Path(url.toLocalFile()).is_file():
                self.open_file(url.toLocalFile())
        event.acceptProposedAction()

    def _restore_geometry(self):
        encoded = self._cfg.get("window_geometry")
        if encoded:
            try:
                self.restoreGeometry(QByteArray.fromBase64(encoded.encode("ascii")))
            except Exception:
                pass

    def quit_application(self):
        """Really leave — the tray menu's "خروج" and File > Exit.

        Separate from closing the window, which now only hides it.
        """
        self._really_quitting = True
        self.close()

    def closeEvent(self, event: QCloseEvent):
        """Closing hides to the tray; quitting is a deliberate act.

        Startup in the packaged build is dominated by Windows loading the Qt
        runtime, which no amount of Python can shorten — so the process stays
        alive and reopening costs nothing. Without a tray there is nowhere to
        hide to, so that case still exits.
        """
        if (not self._really_quitting and self._tray is not None
                and self._cfg.get("close_to_tray", True)):
            self._save_window_state()
            self.hide()
            event.ignore()
            self._announce_tray_once()
            return

        self._closing_application = True
        if self._tasks_watcher is not None:
            self._tasks_watcher.stop()
        self._write_recoveries()
        while self.tabs.count():
            if not self.close_tab(0, create_replacement=False):
                self._closing_application = False
                self._really_quitting = False
                event.ignore()
                return
        self._save_window_state()
        self._unregister_global_hotkey()
        if self._tray is not None:
            self._tray.hide()
        if self._day_widget is not None:
            # A Tool window outlives the main window and would keep the
            # process alive with nothing on screen to close it from.
            self._day_widget.close()
        event.accept()
        QApplication.quit()

    def _save_window_state(self):
        self._cfg["window_geometry"] = bytes(
            self.saveGeometry().toBase64()
        ).decode("ascii")
        settings_manager.save(self._cfg)

    def _announce_tray_once(self):
        """Say where the window went — once, ever.

        Hiding on close is surprising exactly once. After that the balloon
        would be the annoyance the reminders were removed for being.
        """
        if self._cfg.get("tray_notice_shown"):
            return
        self._cfg["tray_notice_shown"] = True
        settings_manager.save(self._cfg)
        try:
            self._tray.showMessage(
                "Notepad Plus",
                "برنامه در نوار وظیفه باز مانده تا دفعهٔ بعد فوری باز شود.\n"
                "برای بستن کامل، روی آیکون راست‌کلیک کن و «خروج» را بزن.",
                QSystemTrayIcon.MessageIcon.Information,
                6000,
            )
        except Exception:
            pass
