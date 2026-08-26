import os
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QByteArray, QPoint, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QAction,
    QActionGroup,
    QCloseEvent,
    QFontDatabase,
    QIcon,
    QKeySequence,
    QTextCursor,
    QTextDocument,
)
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabBar,
    QTabWidget,
    QToolBar,
    QToolButton,
    QVBoxLayout,
)

import core.note_index as note_index
import core.settings_manager as settings_manager
from core.external_change_monitor import ExternalChangeMonitor
from core.export_service import export_to_html, export_to_pdf
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
from ui.quick_open import QuickOpenDialog
from ui.settings_dialog import SettingsDialog
from ui.shortcuts_dialog import ShortcutsDialog
from ui.sidebar import Sidebar
from ui.styles import build_stylesheet


APP_TITLE = "Notepad Plus"
APP_VERSION = "3.3.0"
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
        self.tabMoved.connect(lambda *_args: self._position_new_button())

    def _position_new_button(self):
        if self.count():
            x = self.tabRect(self.count() - 1).right() + 5
        else:
            x = 4
        x = min(x, max(4, self.width() - self.new_button.width() - 4))
        y = max(0, (self.height() - self.new_button.height()) // 2)
        self.new_button.move(x, y)
        self.new_button.raise_()

    def tabInserted(self, index: int):
        super().tabInserted(index)
        QTimer.singleShot(0, self._position_new_button)

    def tabRemoved(self, index: int):
        super().tabRemoved(index)
        QTimer.singleShot(0, self._position_new_button)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_new_button()

    def showEvent(self, event):
        super().showEvent(event)
        self._position_new_button()


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
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.addWidget(QLabel("Find:"), 0, 0)
        self.find_input = QLineEdit()
        grid.addWidget(self.find_input, 0, 1)
        grid.addWidget(QLabel("Replace with:"), 1, 0)
        self.replace_input = QLineEdit()
        grid.addWidget(self.replace_input, 1, 1)
        layout.addLayout(grid)

        options = QHBoxLayout()
        self.case_checkbox = QCheckBox("Match case")
        self.word_checkbox = QCheckBox("Whole word")
        self.wrap_checkbox = QCheckBox("Wrap around")
        self.wrap_checkbox.setChecked(True)
        for box in (self.case_checkbox, self.word_checkbox, self.wrap_checkbox):
            options.addWidget(box)
        options.addStretch()
        layout.addLayout(options)

        buttons = QHBoxLayout()
        find_button = QPushButton("Find Next")
        find_prev_button = QPushButton("Find Previous")
        replace_button = QPushButton("Replace")
        replace_all_button = QPushButton("Replace All")
        find_button.clicked.connect(self.find_next)
        find_prev_button.clicked.connect(self.find_previous)
        replace_button.clicked.connect(self.replace_one)
        replace_all_button.clicked.connect(self.replace_all)
        for button in (find_button, find_prev_button, replace_button, replace_all_button):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.find_input.returnPressed.connect(self.find_next)
        self.replace_input.returnPressed.connect(self.replace_one)

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

    # Actions and chrome

    def _action(self, text, slot, shortcut=None, checkable=False):
        action = QAction(text, self)
        action.setCheckable(checkable)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(slot)
        return action

    def _build_actions(self):
        # File
        self.new_action = self._action("&New", self.new_document, "Ctrl+N")
        self.open_action = self._action("&Open…", self.open_dialog, "Ctrl+O")
        self.quick_open_action = self._action(
            "&Go to File…", self.show_quick_open, "Ctrl+P"
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
        self.exit_action = self._action("E&xit", self.close, "Alt+F4")

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

        # Export
        self.export_pdf_action = self._action("PDF…", lambda: self._export_current("pdf"))
        self.export_html_action = self._action("HTML…", lambda: self._export_current("html"))
        self.export_md_action = self._action("Markdown (.md)…", lambda: self._export_current("md"))

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
        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction(self.new_action)
        file_menu.addAction(self.open_action)
        file_menu.addAction(self.quick_open_action)
        file_menu.addSeparator()
        file_menu.addAction(self.save_action)
        file_menu.addAction(self.save_as_action)
        file_menu.addAction(self.rename_action)
        file_menu.addSeparator()
        # Encoding intentionally has no menu: it is auto-detected and can be
        # changed from the status bar chip, keeping the File menu lean.
        export_menu = file_menu.addMenu("Ex&port")
        export_menu.addAction(self.export_pdf_action)
        export_menu.addAction(self.export_html_action)
        export_menu.addAction(self.export_md_action)
        file_menu.addSeparator()
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
        self.addToolBar(bar)

    def _build_ui(self):
        self.tabs = QTabWidget()
        self.tabs.setObjectName("documentTabs")
        self.document_tab_bar = DocumentTabBar(self.tabs)
        self.tabs.setTabBar(self.document_tab_bar)
        self.document_tab_bar.new_requested.connect(self.new_document)
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._current_tab_changed)
        tab_bar = self.tabs.tabBar()
        tab_bar.tabBarDoubleClicked.connect(self.rename_document)
        tab_bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        tab_bar.customContextMenuRequested.connect(self._show_tab_menu)

        self.sidebar = Sidebar(
            self._cfg["notes_root"],
            self._note_index,
            font_families=settings_manager.font_chain(self._cfg),
        )
        self.sidebar.note_activated.connect(self._open_from_sidebar)
        self.sidebar.root_changed.connect(self._sidebar_root_changed)
        self.sidebar.setVisible(self._cfg.get("sidebar_visible", False))

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.addWidget(self.sidebar)
        self._splitter.addWidget(self.tabs)
        self._apply_sidebar_side()
        self.setCentralWidget(self._splitter)

        self.cursor_label = QLabel("Ln 1, Col 1")
        self.count_label = QLabel("0 characters")
        self.zoom_label = QLabel("100%")
        self.saved_label = QLabel("Saved")
        for label in (self.cursor_label, self.count_label, self.zoom_label):
            label.setObjectName("statusLabel")
            self.statusBar().addPermanentWidget(label)

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
        for button in (self.encoding_button, self.direction_button):
            button.setObjectName("statusButton")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            self.statusBar().addPermanentWidget(button)

        self.saved_label.setObjectName("statusLabel")
        self.statusBar().addPermanentWidget(self.saved_label)

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

    def show_quick_open(self):
        """Ctrl+P — find a note by name without leaving the keyboard."""
        dialog = QuickOpenDialog(self._cfg["notes_root"], self)
        dialog.note_chosen.connect(self.open_file)
        dialog.exec()

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

    def _document_state_changed(self, tab: DocumentTab):
        index = self.tabs.indexOf(tab)
        if index < 0:
            return
        title = f"● {tab.display_name}" if tab.modified else tab.display_name
        self.tabs.setTabText(index, title)
        self.tabs.setTabToolTip(index, tab.path or "Unsaved document")
        if tab is self.current_document():
            self._update_status()
            self.setWindowTitle(f"{title} — {APP_TITLE}")

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

    def _export_current(self, fmt: str):
        tab = self.current_document()
        if not tab:
            return
        filters = {
            "pdf": ("Export PDF", "PDF (*.pdf)", ".pdf"),
            "html": ("Export HTML", "HTML (*.html)", ".html"),
            "md": ("Export Markdown", "Markdown (*.md)", ".md"),
        }
        title, file_filter, suffix = filters[fmt]
        if tab.path:
            suggested = str(Path(tab.path).with_suffix(suffix))
        else:
            save_dir = settings_manager.resolve_save_dir(self._cfg)
            suggested = str(save_dir / f"{self._safe_filename(tab.display_name)}{suffix}")
        path, _ = QFileDialog.getSaveFileName(self, title, suggested, file_filter)
        if not path:
            return
        if not Path(path).suffix:
            path += suffix
        try:
            if fmt == "pdf":
                export_to_pdf(tab.text, path)
            elif fmt == "md":
                write_text_file_atomic(path, tab.text, "utf-8")
            else:
                export_to_html(tab.text, path)
        except Exception as exc:
            QMessageBox.critical(self, "Export Failed", f"The export failed:\n{exc}")
            return
        self.statusBar().showMessage(f"Exported {path}", 3000)

    def _open_from_sidebar(self, path: str):
        self.open_file(path)

    def _sidebar_root_changed(self, folder: str):
        self._cfg["notes_root"] = folder
        settings_manager.save(self._cfg)

    def set_theme(self, theme: str):
        self._cfg["theme"] = theme
        settings_manager.save(self._cfg)
        self.theme_actions[theme].setChecked(True)
        QApplication.instance().setStyleSheet(build_stylesheet(theme))
        for index in range(self.tabs.count()):
            tab = self.tabs.widget(index)
            tab.editor.refresh_code_blocks()
            tab.highlighter.rehighlight()

    def show_settings(self):
        dialog = SettingsDialog(self._cfg, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        theme_changed = values["theme"] != self._cfg.get("theme")
        self._cfg.update(values)
        settings_manager.save(self._cfg)
        settings_manager.resolve_save_dir(self._cfg)
        if theme_changed:
            self.set_theme(values["theme"])
        self.word_wrap_action.setChecked(values["word_wrap"])
        self.toggle_word_wrap(values["word_wrap"])
        self._apply_editor_fonts()
        self._update_status()

    def show_shortcuts(self):
        ShortcutsDialog(self._cfg.get("theme", "system"), self).show()

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
        self.saved_label.setText("Unsaved" if tab.modified else "Saved")

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

    def closeEvent(self, event: QCloseEvent):
        self._closing_application = True
        self._write_recoveries()
        while self.tabs.count():
            if not self.close_tab(0, create_replacement=False):
                self._closing_application = False
                event.ignore()
                return
        self._cfg["window_geometry"] = bytes(
            self.saveGeometry().toBase64()
        ).decode("ascii")
        self._cfg["splitter_state"] = bytes(
            self._splitter.saveState().toBase64()
        ).decode("ascii")
        settings_manager.save(self._cfg)
        event.accept()
