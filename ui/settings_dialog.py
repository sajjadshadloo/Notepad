import shutil
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFontDatabase, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

import core.settings_manager as settings_manager
import ui.styles as styles

DEFAULTS_LATIN = settings_manager.DEFAULTS["font_family_latin"]
DEFAULTS_PERSIAN = settings_manager.DEFAULTS["font_family_persian"]

THEMES = [("System", "system"), ("Light", "light"), ("Dark", "dark")]

# "Automatic" decides per paragraph, which makes a document look like it is
# jumping sides while you write; the other two hold the whole document.
DIRECTIONS = [
    ("Right to left", "rtl"),
    ("Left to right", "ltr"),
    ("Automatic (per paragraph)", "auto"),
]

# Curated shortlists rather than every installed family. QFontComboBox scans
# and previews the whole system font set, which is slow to open and happily
# offers Persian faces for English text (and worse, Latin-only faces for
# Persian, which renders as empty boxes). Families missing from the machine
# are filtered out, and anything the user installs is appended.
LATIN_SUGGESTIONS = [
    "Inter", "Segoe UI", "Calibri", "Georgia", "Verdana", "Arial",
    "Cascadia Mono", "Consolas", "Times New Roman",
]
PERSIAN_SUGGESTIONS = [
    "Vazirmatn", "Segoe UI", "Tahoma", "IRANSans", "Iranian Sans",
    "B Nazanin", "Arial",
]


class SettingsDialog(QDialog):
    """Compact settings window: appearance and files, nothing else."""

    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.setMinimumWidth(560)
        self._settings = settings

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(20)

        layout.addWidget(self._section("Appearance"))
        appearance = QGridLayout()
        appearance.setHorizontalSpacing(14)
        appearance.setVerticalSpacing(10)
        appearance.setColumnMinimumWidth(0, 130)
        appearance.setColumnStretch(1, 1)
        layout.addLayout(appearance)

        # Theme is a segmented control, not a dropdown: three fixed choices
        # you switch between, which is what a segment is for.
        self._theme = settings.get("theme", "system")
        self.theme_buttons = self._segments(
            THEMES, self._theme, self._pick_theme
        )
        self._row(appearance, 0, "Theme", self.theme_buttons)

        self._palette = settings.get("accent_palette", styles.DEFAULT_PALETTE)
        self._row(appearance, 1, "Accent", self._swatches())

        self.latin_combo = self._family_combo(
            LATIN_SUGGESTIONS, settings.get("font_family_latin", "Inter")
        )
        self.latin_combo.setToolTip("Used for English and other Latin text")
        self._row(appearance, 2, "English font", self.latin_combo)

        self.persian_combo = self._family_combo(
            PERSIAN_SUGGESTIONS, settings.get("font_family_persian", "Vazirmatn")
        )
        self.persian_combo.setToolTip(
            "Used for Persian and Arabic text, and for anything the English "
            "font has no glyph for"
        )
        persian = QWidget()
        persian_row = QHBoxLayout(persian)
        persian_row.setContentsMargins(0, 0, 0, 0)
        persian_row.setSpacing(8)
        persian_row.addWidget(self.persian_combo, 1)
        install = QPushButton("Install…")
        install.setToolTip("Add a custom .ttf/.otf font to the app")
        install.clicked.connect(self._install_font)
        persian_row.addWidget(install)
        self._row(appearance, 3, "Persian font", persian)

        size = QWidget()
        size_row = QHBoxLayout(size)
        size_row.setContentsMargins(0, 0, 0, 0)
        size_row.setSpacing(10)
        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setRange(8, 40)
        self.size_slider.setValue(int(settings.get("font_size", 14)))
        self.size_slider.setFixedWidth(200)
        self.size_value = QLabel()
        self.size_value.setObjectName("settingsValue")
        self.size_slider.valueChanged.connect(
            lambda v: self.size_value.setText(f"{v} pt")
        )
        self.size_value.setText(f"{self.size_slider.value()} pt")
        size_row.addWidget(self.size_slider)
        size_row.addWidget(self.size_value)
        size_row.addStretch(1)
        self._row(appearance, 4, "Font size", size)

        self.line_numbers = self._toggle(
            bool(settings.get("show_line_numbers", True))
        )
        self._row(appearance, 5, "Line numbers", self.line_numbers)

        layout.addWidget(self._section("Files & reminders"))
        files = QGridLayout()
        files.setHorizontalSpacing(14)
        files.setVerticalSpacing(10)
        files.setColumnMinimumWidth(0, 130)
        files.setColumnStretch(1, 1)
        layout.addLayout(files)

        self._direction = settings.get("default_direction", "rtl")
        self.direction_buttons = self._segments(
            DIRECTIONS, self._direction, self._pick_direction
        )
        self.direction_buttons.setToolTip(
            "Direction new documents open with. Change one document with "
            "Ctrl + right/left Shift; the choice is remembered per file."
        )
        self._row(files, 0, "Text direction", self.direction_buttons)

        folder = QWidget()
        folder_row = QHBoxLayout(folder)
        folder_row.setContentsMargins(0, 0, 0, 0)
        folder_row.setSpacing(8)
        self.folder_edit = QLineEdit(
            settings.get("default_save_dir", settings_manager.DEFAULT_SAVE_DIR)
        )
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_folder)
        folder_row.addWidget(self.folder_edit, 1)
        folder_row.addWidget(browse)
        self._row(files, 1, "Notes folder", folder)

        checks = QWidget()
        checks_column = QVBoxLayout(checks)
        checks_column.setContentsMargins(0, 0, 0, 0)
        checks_column.setSpacing(8)
        self.schedule_check = QCheckBox(
            "Remind me even when Notepad Plus is closed"
        )
        self.schedule_check.setToolTip(
            "Registers upcoming reminders with Windows Task Scheduler. "
            "Turning this off removes the ones already registered."
        )
        self.schedule_check.setChecked(bool(settings.get("schedule_reminders", True)))
        self.wrap_check = QCheckBox("Wrap long lines")
        self.wrap_check.setChecked(bool(settings.get("word_wrap", True)))
        checks_column.addWidget(self.schedule_check)
        checks_column.addWidget(self.wrap_check)
        self._row(files, 2, "Reminders", checks)

        layout.addStretch(1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setObjectName(
            "primaryButton"
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # Building blocks

    def _section(self, title: str) -> QLabel:
        label = QLabel(title)
        label.setObjectName("sidebarSectionLabel")
        return label

    def _row(self, grid: QGridLayout, line: int, label: str, widget: QWidget):
        name = QLabel(label)
        name.setObjectName("settingsKey")
        grid.addWidget(name, line, 0, Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(widget, line, 1)

    def _segments(self, choices, current, on_pick) -> QWidget:
        """One of N, shown as a segmented control."""
        holder = QWidget()
        holder.setObjectName("segmented")
        holder.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(3)
        holder.buttons = {}
        for label, value in choices:
            button = QToolButton()
            button.setText(label)
            button.setCheckable(True)
            button.setChecked(value == current)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _c, v=value: on_pick(v))
            row.addWidget(button)
            holder.buttons[value] = button
        row.addStretch(1)
        return holder

    def _pick_theme(self, value: str):
        self._theme = value
        for key, button in self.theme_buttons.buttons.items():
            button.setChecked(key == value)

    def _pick_direction(self, value: str):
        self._direction = value
        for key, button in self.direction_buttons.buttons.items():
            button.setChecked(key == value)

    def _swatches(self) -> QWidget:
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self._swatch_buttons = {}
        for name in styles.palette_names():
            button = QToolButton()
            button.setObjectName("swatch")
            button.setCheckable(True)
            button.setChecked(name == self._palette)
            button.setFixedSize(26, 26)
            button.setToolTip(styles.palette_label(name))
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setIcon(self._swatch_icon(name))
            button.clicked.connect(lambda _c, n=name: self._pick_palette(n))
            row.addWidget(button)
            self._swatch_buttons[name] = button
        row.addStretch(1)
        return holder

    @staticmethod
    def _swatch_icon(name: str):
        """A filled square in that palette's accent, at its dark value."""
        from PyQt6.QtGui import QIcon

        colour = styles.PALETTES[name]["dark"]["accent"]
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(colour))
        painter.drawRoundedRect(pixmap.rect(), 18, 18)
        painter.end()
        return QIcon(pixmap)

    def _pick_palette(self, name: str):
        self._palette = name
        for key, button in self._swatch_buttons.items():
            button.setChecked(key == name)

    def _toggle(self, checked: bool) -> QToolButton:
        button = QToolButton()
        button.setObjectName("switch")
        button.setCheckable(True)
        button.setChecked(checked)
        button.setFixedSize(44, 24)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setText("")
        return button

    @staticmethod
    def _family_combo(suggestions: list[str], current: str) -> QComboBox:
        """Editable picker over the suggestions that exist on this machine.

        Editable so a family the shortlist does not know about — including
        one the user just installed — can still be typed in and kept.
        """
        installed = set(QFontDatabase.families())
        families = [name for name in suggestions if name in installed]
        if current and current not in families:
            families.insert(0, current)
        combo = QComboBox()
        combo.setEditable(True)
        combo.addItems(families)
        combo.setCurrentText(current)
        return combo

    def _install_font(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Install Font",
            str(Path.home()),
            "Font Files (*.ttf *.otf)",
        )
        installed_families: list[str] = []
        fonts_dir = settings_manager.user_fonts_dir()
        for path in paths:
            destination = fonts_dir / Path(path).name
            try:
                shutil.copyfile(path, destination)
            except OSError:
                continue
            font_id = QFontDatabase.addApplicationFont(str(destination))
            if font_id >= 0:
                installed_families.extend(
                    QFontDatabase.applicationFontFamilies(font_id)
                )
        if not installed_families:
            return
        # Offer the new families in both pickers, and select the first one for
        # Persian — that is what the Install button sits next to.
        for combo in (self.latin_combo, self.persian_combo):
            for family in installed_families:
                if combo.findText(family) < 0:
                    combo.addItem(family)
        self.persian_combo.setCurrentText(installed_families[0])

    def _browse_folder(self):
        start = self.folder_edit.text().strip() or str(Path.home())
        folder = QFileDialog.getExistingDirectory(
            self, "Default Save Folder", start
        )
        if folder:
            self.folder_edit.setText(folder)

    def values(self) -> dict:
        return {
            "theme": self._theme,
            "accent_palette": self._palette,
            "font_family_latin": (
                self.latin_combo.currentText().strip()
                or DEFAULTS_LATIN
            ),
            "font_family_persian": (
                self.persian_combo.currentText().strip()
                or DEFAULTS_PERSIAN
            ),
            "font_size": self.size_slider.value(),
            "word_wrap": self.wrap_check.isChecked(),
            "default_direction": self._direction,
            "show_line_numbers": self.line_numbers.isChecked(),
            "schedule_reminders": self.schedule_check.isChecked(),
            "default_save_dir": (
                self.folder_edit.text().strip() or settings_manager.DEFAULT_SAVE_DIR
            ),
        }
