import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from pathlib import Path

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont, QIcon
from ui.main_window import APP_VERSION, MainWindow, _load_bundled_fonts
from ui.styles import build_stylesheet
import core.settings_manager as sm


def app_icon() -> QIcon:
    icon_path = Path(__file__).resolve().parent / "assets" / "icon.ico"
    return QIcon(str(icon_path)) if icon_path.exists() else QIcon()


def _set_windows_app_id():
    """Give Windows a stable AppUserModelID so the taskbar uses our icon
    instead of the generic pythonw.exe icon."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "Sajjad.NotepadPlus"
        )
    except Exception:
        pass


def main():
    _set_windows_app_id()
    app = QApplication(sys.argv)
    app.setApplicationName("Notepad Plus")
    app.setApplicationDisplayName("Notepad Plus")
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("Sajjad")
    app.setOrganizationDomain("local.notepad")
    app.setWindowIcon(app_icon())
    _load_bundled_fonts()

    settings = sm.load()
    app.setStyleSheet(build_stylesheet(settings.get("theme", "system")))
    ui_font = QFont()
    # Inter has no Persian glyphs. Put Vazirmatn before Segoe UI so Persian
    # labels (especially note titles in the sidebar) use the bundled typeface.
    ui_font.setFamilies(["Inter", "Vazirmatn", "Segoe UI", "sans-serif"])
    ui_font.setPointSize(10)
    app.setFont(ui_font)

    initial_files = [arg for arg in sys.argv[1:] if os.path.isfile(arg)]
    window = MainWindow(initial_files)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
