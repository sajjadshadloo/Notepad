import shutil
from pathlib import Path

from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFontComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

import core.settings_manager as settings_manager

THEMES = [("System", "system"), ("Light", "light"), ("Dark", "dark")]


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

        self.font_combo = QFontComboBox()
        self.font_combo.setCurrentFont(QFont(settings.get("font_family", "Vazirmatn")))
        font_row = QHBoxLayout()
        font_row.addWidget(self.font_combo, 1)
        install_font_button = QPushButton("Install…")
        install_font_button.setToolTip("Add a custom .ttf/.otf font to the app")
        install_font_button.clicked.connect(self._install_font)
        font_row.addWidget(install_font_button)
        form.addRow("Font:", font_row)

        self.size_spin = QSpinBox()
        self.size_spin.setRange(8, 40)
        self.size_spin.setValue(int(settings.get("font_size", 14)))
        form.addRow("Font size:", self.size_spin)

        layout.addWidget(appearance)

        files = QGroupBox("Files")
        files_form = QFormLayout(files)
        files_form.setSpacing(10)

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
        if installed_families:
            self.font_combo.setCurrentFont(QFont(installed_families[0]))

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
            "font_family": self.font_combo.currentFont().family(),
            "font_size": self.size_spin.value(),
            "word_wrap": self.wrap_check.isChecked(),
            "default_save_dir": (
                self.folder_edit.text().strip() or settings_manager.DEFAULT_SAVE_DIR
            ),
        }
