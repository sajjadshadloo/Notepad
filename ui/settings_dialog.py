import shutil
from pathlib import Path

from PyQt6.QtGui import QFontDatabase
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

import core.settings_manager as settings_manager

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
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        appearance = QGroupBox("Appearance")
        form = QFormLayout(appearance)
        form.setSpacing(10)

        self.theme_combo = QComboBox()
        for label, value in THEMES:
            self.theme_combo.addItem(label, value)
        current_theme = settings.get("theme", "system")
        index = next(
            (i for i, (_, value) in enumerate(THEMES) if value == current_theme), 0
        )
        self.theme_combo.setCurrentIndex(index)
        form.addRow("Theme:", self.theme_combo)

        self.latin_combo = self._family_combo(
            LATIN_SUGGESTIONS, settings.get("font_family_latin", "Inter")
        )
        self.latin_combo.setToolTip("Used for English and other Latin text")
        form.addRow("English font:", self.latin_combo)

        self.persian_combo = self._family_combo(
            PERSIAN_SUGGESTIONS, settings.get("font_family_persian", "Vazirmatn")
        )
        self.persian_combo.setToolTip(
            "Used for Persian and Arabic text, and for anything the English "
            "font has no glyph for"
        )
        persian_row = QHBoxLayout()
        persian_row.addWidget(self.persian_combo, 1)
        install_font_button = QPushButton("Install…")
        install_font_button.setToolTip("Add a custom .ttf/.otf font to the app")
        install_font_button.clicked.connect(self._install_font)
        persian_row.addWidget(install_font_button)
        form.addRow("Persian font:", persian_row)

        self.size_spin = QSpinBox()
        self.size_spin.setRange(8, 40)
        self.size_spin.setValue(int(settings.get("font_size", 14)))
        form.addRow("Font size:", self.size_spin)

        layout.addWidget(appearance)

        files = QGroupBox("Files")
        files_form = QFormLayout(files)
        files_form.setSpacing(10)

        self.direction_combo = QComboBox()
        for label, value in DIRECTIONS:
            self.direction_combo.addItem(label, value)
        current_direction = settings.get("default_direction", "rtl")
        self.direction_combo.setCurrentIndex(
            next(
                (i for i, (_, v) in enumerate(DIRECTIONS) if v == current_direction),
                0,
            )
        )
        self.direction_combo.setToolTip(
            "Direction new documents open with. Change one document with "
            "Ctrl + right/left Shift; the choice is remembered per file."
        )
        files_form.addRow("Text direction:", self.direction_combo)

        self.wrap_check = QCheckBox("Wrap long lines")
        self.wrap_check.setChecked(bool(settings.get("word_wrap", True)))
        files_form.addRow(self.wrap_check)

        folder_row = QHBoxLayout()
        self.folder_edit = QLineEdit(
            settings.get("default_save_dir", settings_manager.DEFAULT_SAVE_DIR)
        )
        browse_button = QPushButton("Browse…")
        browse_button.clicked.connect(self._browse_folder)
        folder_row.addWidget(self.folder_edit, 1)
        folder_row.addWidget(browse_button)
        files_form.addRow("Default save folder:", folder_row)

        layout.addWidget(files)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

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
            "theme": self.theme_combo.currentData(),
            "font_family_latin": (
                self.latin_combo.currentText().strip()
                or DEFAULTS_LATIN
            ),
            "font_family_persian": (
                self.persian_combo.currentText().strip()
                or DEFAULTS_PERSIAN
            ),
            "font_size": self.size_spin.value(),
            "word_wrap": self.wrap_check.isChecked(),
            "default_direction": self.direction_combo.currentData(),
            "default_save_dir": (
                self.folder_edit.text().strip() or settings_manager.DEFAULT_SAVE_DIR
            ),
        }
