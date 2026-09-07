import logging
import os
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QByteArray, QPoint, QSize, Qt, QTimer, pyqtSignal
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
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QSystemTrayIcon,
    QTabBar,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core import daily_notes
import core.note_index as note_index
import core.settings_manager as settings_manager
from core.external_change_monitor import ExternalChangeMonitor
from core.jalali import to_persian_digits
from core.tasks import parse_task
from core.tasks import set_stamp, shift_stamp, toggle_repeat
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
from ui.sidebar import Sidebar
from ui.styles import build_stylesheet, current_palette, resolve_theme

log = logging.getLogger(__name__)

# The status dot the design puts before a tab name.
TAB_DOT_SIZE = 6

APP_TITLE = "Notepad Plus"
APP_VERSION = "4.0.0"
FILE_FILTER = "Text Files (*.txt);;Markdown (*.md *.markdown);;All Files (*.*)"
ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"

# Word counting walks the whole document; above this size the status bar
# shows only the character count so typing stays instant.
WORD_COUNT_LIMIT = 200_000


class DocumentTabBar(QTabBar):
    """Tab bar with a browser-style New button beside the last document."""

    new_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.new_button = QToolButton(self)
        self.new_button.setObjectName("newTabButton")
        self.new_button.setText("+")
        self.new_button.setToolTip("New document  (Ctrl+N)")
        self.new_button.setAccessibleName("New document")
        self.new_button.setAutoRaise(True)
        self.new_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.new_button.setFixedSize(34, 30)
        self.new_button.clicked.connect(self.new_requested)

    # The + is placed by the tab strip's layout (see DocumentTabs), not
    # positioned by hand over the bar: computing its x from tabRect() put it
    # on top of the last tab's close button whenever the bar had not settled.


def _app_icon() -> QIcon:
    icon_path = ASSETS_DIR / "icon.ico"
    return QIcon(str(icon_path)) if icon_path.exists() else QIcon()


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


class MainWindow(QMainWindow):
    def __init__(self, initial_files: list[str] | None = None):
        super().__init__()
        self._cfg = settings_manager.load()
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

        self.setWindowTitle(APP_TITLE)
        self.setWindowIcon(_app_icon())
        self.setMinimumSize(720, 480)
        self.resize(1060, 720)
        self.setAcceptDrops(True)

        self._build_actions()
        self._build_menus()
        self._build_format_bar()
        self._build_ui()
        self._restore_geometry()

        self._recovery_timer = QTimer(self, interval=10_000)
        self._recovery_timer.timeout.connect(self._write_recoveries)
        self._recovery_timer.start()

        opened = False
        for path in initial_files or []:
            opened = self.open_file(path) or opened
        if not opened:
            self.new_document()

        # Recovery and migration both raise modal prompts, and neither may run
        # from here: the window is not on screen yet, so the dialog gets no
        # visible parent, never reaches the taskbar, and can end up behind
        # other windows — the app then looks like it simply failed to start.
        # showEvent runs them once the window is actually up.
        self._startup_prompts_shown = False
        self._tasks_watcher: TaskWatcher | None = None
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
        self.today_action = self._action("My &Tasks…", self.show_today, "Ctrl+T")
        self.daily_note_action = self._action(
            "Today's &Note", self.open_daily_note, "Ctrl+Shift+D"
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
            "Schedule…", self.show_stamp_picker, "Ctrl+Shift+A"
        )
        self.repeat_action = self._action(
            "Repeat &Weekly",
            lambda: self._transform_selected_lines(toggle_repeat),
            "Ctrl+Shift+R",
        )
        self.fence_action = self._action(
            "Code &Fence", self.wrap_in_code_fence, "Ctrl+Shift+C"
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
        # Ctrl+B now bolds text (the writing shortcut everyone expects);
        # the sidebar moved to Ctrl+Shift+B.
        self.sidebar_action = self._action(
            "&Sidebar", self.toggle_sidebar, "Ctrl+Shift+B", checkable=True
        )
        self.sidebar_action.setChecked(self._cfg.get("sidebar_visible", False))
        self.sidebar_right_action = self._action(
            "Sidebar on &Right", self.set_sidebar_on_right, checkable=True
        )
        self.sidebar_right_action.setChecked(self._cfg.get("sidebar_on_right", False))
        self.line_numbers_action = self._action(
            "&Line Numbers", self.toggle_line_numbers, checkable=True
        )
        self.line_numbers_action.setChecked(self._cfg.get("show_line_numbers", True))
        self.shortcuts_action = self._action(
            "&Keyboard Shortcuts", self.show_shortcuts, "Ctrl+/"
        )
        self.about_action = self._action("&About " + APP_TITLE, self.show_about)

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
        format_menu.addAction(self.repeat_action)
        format_menu.addSeparator()
        format_menu.addAction(self.fence_action)
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
        view_menu.addAction(self.sidebar_action)
        view_menu.addAction(self.sidebar_right_action)

        help_menu = self.menuBar().addMenu("&Help")
        help_menu.addAction(self.shortcuts_action)
        help_menu.addAction(self.about_action)

    def _build_format_bar(self):
        """Slim quick-access bar for formatting, like Windows Notepad's."""
        bar = QToolBar("Formatting", self)
        bar.setObjectName("formatBar")
        bar.setMovable(False)
        bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        bold = self._action("B", self.bold_action.trigger)
        bold.setToolTip("Bold  (Ctrl+B)")
        bar.addAction(bold)
        bar.addSeparator()
        for level, action in enumerate(self.heading_actions, start=1):
            proxy = self._action(f"H{level}", action.trigger)
            proxy.setToolTip(f"Heading {level}  (Ctrl+{level})")
            bar.addAction(proxy)
        bar.addSeparator()
        bullet = self._action("•", self.bullet_action.trigger)
        bullet.setToolTip("Bullet list  (Ctrl+Shift+8)")
        numbered = self._action("1.", self.numbered_action.trigger)
        numbered.setToolTip("Numbered list  (Ctrl+Shift+7)")
        todo = self._action("☑", self.todo_action.trigger)
        todo.setToolTip("To-do list  (Ctrl+Shift+9)")
        bar.addAction(bullet)
        bar.addAction(numbered)
        bar.addAction(todo)
        bar.addSeparator()

        # The three that turn a checkbox into something with a deadline.
        stamp = self._action("@", self.stamp_action.trigger)
        stamp.setToolTip("Schedule this task — pick a day and an hour")
        self._stamp_toolbar_action = stamp
        repeat = self._action("↻", self.repeat_action.trigger)
        repeat.setToolTip("Repeat this task weekly")
        fence = self._action("</>", self.fence_action.trigger)
        fence.setToolTip("Wrap the selection in a code fence")
        bar.addAction(stamp)
        bar.addAction(repeat)
        bar.addAction(fence)

        # Find sits at the far end, away from the formatting cluster.
        spacer = QWidget()
        spacer.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        bar.addWidget(spacer)
        find = self._action("Find", self.find_action.trigger)
        find.setIcon(icon("search", current_palette()["muted"], 13))
        find.setToolTip("Find and replace  (Ctrl+F)")
        bar.addAction(find)
        # Kept as a plain widget, not addToolBar(): the design puts this
        # below the tab strip, and a QMainWindow toolbar can only go above
        # the central widget.
        bar.setFloatable(False)
        self.format_bar = bar
        self._find_toolbar_action = find

    def _build_ui(self):
        self.document_tab_bar = DocumentTabBar()
        self.tabs = DocumentTabs(self.document_tab_bar)
        self.document_tab_bar.new_requested.connect(self.new_document)
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.setIconSize(QSize(TAB_DOT_SIZE, TAB_DOT_SIZE))
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._current_tab_changed)
        tab_bar = self.tabs.tabBar()
        tab_bar.tabBarDoubleClicked.connect(self.rename_document)
        tab_bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        tab_bar.customContextMenuRequested.connect(self._show_tab_menu)

        self.tabs.setCornerWidget(
            self._build_today_meter(), Qt.Corner.TopRightCorner
        )

        self.sidebar = Sidebar(
            self._cfg["notes_root"],
            self._note_index,
            font_families=settings_manager.font_chain(self._cfg),
        )
        self.sidebar.note_activated.connect(self._open_from_sidebar)
        self.sidebar.day_activated.connect(self.open_daily_note)
        self.sidebar.task_activated.connect(self._open_task)
        self.sidebar.root_changed.connect(self._sidebar_root_changed)
        self.sidebar.setVisible(self._cfg.get("sidebar_visible", False))

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.addWidget(self.sidebar)
        self._splitter.addWidget(self.tabs.pages)
        self._apply_sidebar_side()

        # The design's stacking order, top to bottom: the top bar, the tab
        # strip, the format bar, then the sidebar and editor side by side.
        # The format bar is a plain widget in this column rather than a
        # QMainWindow toolbar, because a toolbar can only sit above the
        # central widget — which would put it above the tabs.
        self.top_bar = TopBar()
        self.top_bar.search_requested.connect(self.show_quick_open)
        self.top_bar.sidebar_toggled.connect(self.sidebar_action.trigger)
        self.top_bar.tasks_requested.connect(self.show_today)
        self.top_bar.theme_toggled.connect(self.cycle_theme)
        self.top_bar.settings_requested.connect(self.show_settings)

        shell = QWidget()
        column = QVBoxLayout(shell)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self.top_bar)
        column.addWidget(self.tabs)
        column.addWidget(self.format_bar)
        column.addWidget(self._splitter, 1)
        self.setCentralWidget(shell)

        # Save state leads on the left, where the eye lands first — it is the
        # one thing here you might need to act on. Counts and the three
        # pickers sit right, out of the way until wanted.
        self.saved_label = QLabel()
        self.saved_label.setObjectName("savedLabel")
        self.cursor_label = QLabel("Ln 1, Col 1")
        self.cursor_label.setObjectName("statusLabel")
        self.statusBar().addWidget(self.saved_label)
        self.statusBar().addWidget(self.cursor_label)

        self.count_label = QLabel("0 characters")
        self.count_label.setObjectName("statusLabel")
        self.statusBar().addPermanentWidget(self.count_label)

        # Encoding and direction are clickable chips: one click opens the
        # picker right above the status bar.
        self.encoding_button = QPushButton("UTF-8")
        self.encoding_button.setToolTip("File encoding — click to change")
        self.encoding_button.clicked.connect(
            lambda: self._popup_status_menu(
                self.encoding_button, self.encoding_group.actions()
            )
        )
        self.direction_button = QPushButton("Auto")
        self.direction_button.setToolTip("Text direction — click to change")
        self.direction_button.clicked.connect(
            lambda: self._popup_status_menu(
                self.direction_button, self.direction_group.actions()
            )
        )
        # Zoom joins them as a chip rather than a dead label: at a glance it
        # reads the same, and a click puts it back to 100%.
        self.zoom_label = QPushButton("100%")
        self.zoom_label.setToolTip("Zoom — click to restore 100%")
        self.zoom_label.clicked.connect(self.reset_zoom)

        for button in (self.encoding_button, self.direction_button, self.zoom_label):
            button.setObjectName("statusButton")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFlat(True)
            self.statusBar().addPermanentWidget(button)

    def _build_today_meter(self) -> QWidget:
        """How much of today is done, at the end of the tab strip.

        Fed by the task watcher’s existing scan, so it costs nothing
        extra — and it stays hidden on a day with nothing scheduled rather
        than sitting there empty.
        """
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(10, 0, 10, 0)
        row.setSpacing(8)

        caption = QLabel("امروز")
        caption.setObjectName("todayMeterCaption")
        self.today_meter = QProgressBar()
        self.today_meter.setObjectName("todayMeter")
        self.today_meter.setTextVisible(False)
        self.today_meter.setFixedWidth(96)
        self.today_meter_label = QLabel()
        self.today_meter_label.setObjectName("todayMeterLabel")

        row.addWidget(caption)
        row.addWidget(self.today_meter)
        row.addWidget(self.today_meter_label)
        holder.setVisible(False)
        self._today_meter_holder = holder
        return holder

    def update_open_task_count(self, count: int):
        self.top_bar.set_open_task_count(
            to_persian_digits(str(count)) if count else ""
        )

    def update_today_meter(self, done: int, total: int):
        self._today_meter_holder.setVisible(total > 0)
        if total <= 0:
            return
        self.today_meter.setMaximum(total)
        self.today_meter.setValue(done)
        self.today_meter_label.setText(to_persian_digits(f"{done}/{total}"))
        self._today_meter_holder.setToolTip(
            to_persian_digits(f"{done} از {total} کار امروز انجام شده")
        )

    def cycle_theme(self):
        """The top bar's sun button: straight between dark and light.

        "System" is a setting, not a step in a toggle, so this lands on a
        concrete theme rather than cycling through three.
        """
        current = self._cfg.get("theme", "system")
        resolved = "light" if resolve_theme(current) == "light" else "dark"
        self.set_theme("dark" if resolved == "light" else "light")

    def show_stamp_picker(self):
        """The @ button: pick a day and an hour for the task under the cursor.

        Before this the button stamped today and said nothing about how to
        add a time, which you could only do by knowing to type it.
        """
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
            lambda day, at: self._transform_selected_lines(
                lambda text: set_stamp(text, day, at)
            )
        )
        # Under the @ button, so it reads as that button's own menu.
        anchor = self.format_bar.widgetForAction(self._stamp_toolbar_action)
        if anchor is not None:
            picker.move(
                anchor.mapToGlobal(anchor.rect().bottomLeft())
            )
        picker.exec()

    def wrap_in_code_fence(self):
        """Put ``` lines around the selection, or open an empty fence.

        One edit block, so a single Ctrl+Z takes the whole thing back.
        """
        tab = self.current_document()
        if not tab:
            return
        cursor = tab.editor.textCursor()
        cursor.beginEditBlock()
        if cursor.hasSelection():
            start, end = cursor.selectionStart(), cursor.selectionEnd()
            cursor.setPosition(end)
            cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
            cursor.insertText("\n```")
            cursor.setPosition(start)
            cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            cursor.insertText("```\n")
        else:
            cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            cursor.insertText("```\n\n```\n")
            cursor.movePosition(QTextCursor.MoveOperation.Up, n=2)
        cursor.endEditBlock()
        tab.editor.setTextCursor(cursor)

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

    def _effective_font_size(self) -> int:
        base = self._cfg.get("font_size", 14)
        return max(6, min(72, base + self._zoom_steps))

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
        tab.editor.zoom_requested.connect(self.change_zoom)
        tab.editor.direction_changed.connect(self._editor_direction_changed)
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

    def open_daily_note(self, day=None):
        """Ctrl+Shift+D — the note for a day.

        Nothing is written to disk here. Until 4.0 this created the file on
        the spot, so browsing the calendar left a trail of notes containing
        only their own heading — seven of them, every one empty, in a folder
        of twenty-three. Now the day opens as an unsaved document that knows
        its filename, and becomes a file the moment you save something.
        """
        from datetime import date as _date

        when = day if isinstance(day, _date) else _date.today()
        path = daily_notes.path_for(self._cfg["notes_root"], when)
        if not path.exists():
            existing = self._tab_for_pending(str(path))
            if existing is not None:
                self.tabs.setCurrentWidget(existing)
                existing.editor.setFocus()
                return
            self._make_document(
                text=daily_notes.starter_text(when),
                pending_path=str(path),
            )
            editor = self.current_document().editor
            cursor = editor.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            editor.setTextCursor(cursor)
            editor.setFocus()
            return
        if self.open_file(str(path)):
            # Land at the end, ready to type rather than at the heading.
            editor = self.current_document().editor
            cursor = editor.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            editor.setTextCursor(cursor)
            editor.setFocus()

    def show_today(self):
        """Ctrl+T — the dated to-do items from every note, in one place."""
        dialog = TodayDialog(self._cfg["notes_root"], self)
        dialog.task_chosen.connect(self._open_task)
        dialog.snooze_requested.connect(self._snooze_task)
        dialog.exec()

    def show_quick_open(self):
        """Ctrl+P — find a note by name without leaving the keyboard."""
        dialog = QuickOpenDialog(
            self._cfg["notes_root"],
            self,
            commands=self._palette_commands(),
            tasks=self._tasks_watcher.open_tasks() if self._tasks_watcher else [],
        )
        dialog.note_chosen.connect(self.open_file)
        dialog.task_chosen.connect(self._open_task)
        dialog.exec()

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
        self.sidebar.refresh()
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
        self.sidebar.refresh()
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
            folder = ""
            if tab.path:
                root = Path(self._cfg.get("notes_root") or "")
                try:
                    folder = Path(tab.path).resolve().parent.relative_to(
                        root.resolve()
                    ).as_posix()
                except (ValueError, OSError):
                    folder = Path(tab.path).parent.name
                folder = "" if folder == "." else folder
            self.top_bar.set_breadcrumb(folder, tab.display_name)
            self.sidebar.set_active_note(tab.path or None)
            self._update_status()
            marker = "● " if tab.modified else ""
            self.setWindowTitle(f"{marker}{tab.display_name} — {APP_TITLE}")

    def _current_tab_changed(self, _index):
        tab = self.current_document()
        if tab:
            self.direction_actions[tab.editor.direction_mode].setChecked(True)
            if tab.encoding in self.encoding_actions:
                self.encoding_actions[tab.encoding].setChecked(True)
            self._document_state_changed(tab)
            tab.editor.setFocus()
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
        base = self._cfg.get("font_size", 14)
        self._zoom_steps = max(6 - base, min(72 - base, self._zoom_steps + delta))
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

    def toggle_sidebar(self, checked: bool):
        self.sidebar.setVisible(checked)
        self._cfg["sidebar_visible"] = checked
        settings_manager.save(self._cfg)

    def _apply_sidebar_side(self):
        """Order the splitter so the sidebar sits on the configured side.

        Useful when writing RTL, where a left sidebar sits between you and
        the start of every line.
        """
        on_right = self._cfg.get("sidebar_on_right", False)
        sidebar_index = self._splitter.indexOf(self.sidebar)
        wanted_index = 1 if on_right else 0
        if sidebar_index != wanted_index:
            # insertWidget reparents in place; the widget keeps its state.
            self._splitter.insertWidget(wanted_index, self.sidebar)
        editor_index = 1 - wanted_index
        self._splitter.setCollapsible(wanted_index, True)
        self._splitter.setCollapsible(editor_index, False)
        sizes = [260, 800] if not on_right else [800, 260]
        self._splitter.setSizes(sizes)

    def set_sidebar_on_right(self, checked: bool):
        self._cfg["sidebar_on_right"] = checked
        settings_manager.save(self._cfg)
        self._apply_sidebar_side()

    def _open_from_sidebar(self, path: str):
        self.open_file(path)

    def _sidebar_root_changed(self, folder: str):
        self._cfg["notes_root"] = folder
        settings_manager.save(self._cfg)
        if self._tasks_watcher is not None:
            self._tasks_watcher.set_root(folder)

    def set_theme(self, theme: str):
        self._cfg["theme"] = theme
        settings_manager.save(self._cfg)
        self.theme_actions[theme].setChecked(True)
        self._restyle()

    def _restyle(self):
        """Rebuild the stylesheet from the current theme and palette.

        The editor paints code backgrounds and markers itself, so those have
        to be recomputed here — a stylesheet swap alone leaves them on the
        outgoing palette's colours.
        """
        QApplication.instance().setStyleSheet(
            build_stylesheet(
                self._cfg.get("theme", "system"),
                self._cfg.get("accent_palette", "graphite"),
            )
        )
        self._dot_icons.clear()
        self.top_bar.refresh_palette()
        self._find_toolbar_action.setIcon(
            icon("search", current_palette()["muted"], 13)
        )
        for index in range(self.tabs.count()):
            tab = self.tabs.widget(index)
            tab.editor.refresh_code_blocks()
            tab.highlighter.rehighlight()
            self.tabs.setTabIcon(index, self._dot_icon(tab.modified))

    def show_settings(self):
        dialog = SettingsDialog(self._cfg, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        restyle_needed = values["theme"] != self._cfg.get("theme") or values[
            "accent_palette"
        ] != self._cfg.get("accent_palette")
        self._cfg.update(values)
        settings_manager.save(self._cfg)
        settings_manager.resolve_save_dir(self._cfg)
        if restyle_needed:
            self.theme_actions[values["theme"]].setChecked(True)
            self._restyle()
        self.line_numbers_action.setChecked(values["show_line_numbers"])
        self.toggle_line_numbers(values["show_line_numbers"])
        self.word_wrap_action.setChecked(values["word_wrap"])
        self.toggle_word_wrap(values["word_wrap"])
        self._apply_editor_fonts()
        self._update_status()

    def show_shortcuts(self):
        ShortcutsDialog(
            self._cfg.get("theme", "system"),
            self,
            self._cfg.get("accent_palette", "graphite"),
        ).show()

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
        cursor = tab.editor.textCursor()
        self.cursor_label.setText(
            f"Ln {cursor.blockNumber() + 1}, Col {cursor.positionInBlock() + 1}"
        )
        if tab.editor.document().characterCount() <= WORD_COUNT_LIMIT:
            words, chars = tab.counts()
            self.count_label.setText(f"{words:,} words · {chars:,} characters")
        else:
            self.count_label.setText(
                f"{tab.editor.document().characterCount() - 1:,} characters"
            )
        base = self._cfg.get("font_size", 14)
        self.zoom_label.setText(f"{round(self._effective_font_size() / base * 100)}%")
        self.encoding_button.setText(tab.encoding.upper())
        direction = tab.editor.current_direction().upper()
        if tab.editor.direction_mode == "auto":
            direction += " · Auto"
        self.direction_button.setText(direction)
        # A dot carries the state at a glance; the word confirms it. The
        # property drives the colour, so the sheet owns which one it is.
        self.saved_label.setText(
            "● Unsaved" if tab.modified else "● Saved"
        )
        dirty = "true" if tab.modified else "false"
        if self.saved_label.property("dirty") != dirty:
            self.saved_label.setProperty("dirty", dirty)
            self.saved_label.style().unpolish(self.saved_label)
            self.saved_label.style().polish(self.saved_label)

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
        self._prune_empty_daily_notes()
        self._start_task_watcher()

    def _prune_empty_daily_notes(self):
        """Clear the empty day notes older versions left behind — once.

        Only files still holding exactly their generated heading are touched,
        so nothing typed can be lost. Latched in settings because after 4.0
        no new ones appear and walking the folder every launch would be work
        for nothing.
        """
        if self._cfg.get("daily_cleanup_done"):
            return
        self._cfg["daily_cleanup_done"] = True
        settings_manager.save(self._cfg)
        try:
            removed = daily_notes.prune_empty(self._cfg["notes_root"])
        except OSError:
            log.warning("Could not tidy the Daily folder", exc_info=True)
            return
        if not removed:
            return
        log.info("Removed %d empty daily note(s)", len(removed))
        self.sidebar.refresh()
        self.statusBar().showMessage(
            to_persian_digits(f"{len(removed)} یادداشت روزانهٔ خالی پاک شد"), 5000
        )

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

    def _start_task_watcher(self):
        """Begin keeping the task counts fresh.

        Started here rather than in __init__ so nothing about it can show up
        in startup time; the watcher itself defers its first scan further and
        does the folder walk on a worker thread.
        """
        if self._tasks_watcher is not None:
            return
        self._tasks_watcher = TaskWatcher(self._cfg["notes_root"], self)
        self._tasks_watcher.progress_changed.connect(self.update_today_meter)
        self._tasks_watcher.open_count_changed.connect(self.update_open_task_count)
        self._tasks_watcher.start()

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

    def _snooze_task(self, path: str, line_number: int, days: int):
        """Push one task's date forward by `days`.

        A note that is already open is edited through its document, so the
        change joins that tab's undo stack and any unsaved work in it
        survives; only a note nobody has open is rewritten on disk.
        """
        tab = self._tab_for_path(path)
        if tab is not None:
            block = tab.editor.document().findBlockByNumber(line_number)
            if not block.isValid():
                return
            moved = shift_stamp(block.text(), days)
            if moved is None:
                return
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
            cursor.insertText(moved)
            cursor.endEditBlock()
            self.statusBar().showMessage("کار به فردا موکول شد", 3000)
            return

        try:
            loaded = read_text_file(path)
            lines = loaded.text.splitlines(keepends=True)
            if line_number >= len(lines):
                return
            original = lines[line_number]
            body = original.rstrip("\r\n")
            moved = shift_stamp(body, days)
            if moved is None:
                return
            lines[line_number] = moved + original[len(body):]
            write_text_file_atomic(path, "".join(lines), loaded.encoding)
        except (OSError, UnicodeError):
            log.warning("Could not snooze the task in %s", path, exc_info=True)
            self.statusBar().showMessage("تعویق این کار ممکن نشد", 4000)
            return
        self.statusBar().showMessage("کار به فردا موکول شد", 3000)

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
        splitter_state = self._cfg.get("splitter_state")
        if splitter_state:
            try:
                self._splitter.restoreState(
                    QByteArray.fromBase64(splitter_state.encode("ascii"))
                )
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
        if not self._really_quitting and self._tray is not None:
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
        if self._tray is not None:
            self._tray.hide()
        event.accept()
        QApplication.quit()

    def _save_window_state(self):
        self._cfg["window_geometry"] = bytes(
            self.saveGeometry().toBase64()
        ).decode("ascii")
        self._cfg["splitter_state"] = bytes(
            self._splitter.saveState().toBase64()
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
