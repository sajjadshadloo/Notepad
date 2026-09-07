import logging
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

from logging.handlers import RotatingFileHandler
from pathlib import Path

from core.startup_trace import ENABLED as _TRACE, elapsed_ms, mark as _mark, marks

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QFont, QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox

_mark("import Qt")

import core.settings_manager as sm
from core.single_instance import SingleInstanceGuard

_mark("import core")

# ui.main_window pulls in the editor, the sidebar and every dialog. A launch
# that turns out to be a second instance hands its arguments to the running
# one and exits, and must not pay for any of that, so the import happens
# inside main() once we know this process is the one that will show a window.

log = logging.getLogger("notepad")


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


def _setup_logging() -> Path:
    log_dir = sm.app_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "notepad.log"
    handler = RotatingFileHandler(
        log_file, maxBytes=512_000, backupCount=2, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    return log_file


def _install_excepthook(log_file: Path):
    """Log unhandled exceptions and show a plain message instead of the raw
    'Failed to execute script' traceback dialog. The app keeps running."""

    def hook(exc_type, exc, tb):
        log.critical("Unhandled exception", exc_info=(exc_type, exc, tb))
        try:
            QMessageBox.critical(
                None,
                "Notepad Plus",
                "An unexpected error occurred. Your open documents are "
                "unaffected.\n\nDetails were written to:\n" + str(log_file),
            )
        except Exception:
            pass

    sys.excepthook = hook


def _report_startup():
    total = elapsed_ms()
    log.info("Startup ready in %.1f ms", total)
    if not _TRACE:
        return
    previous = 0.0
    for label, at in [*marks(), ("first paint", total)]:
        log.info("  %-16s %7.1f ms  (at %7.1f)", label, at - previous, at)
        previous = at


def main() -> int:
    _set_windows_app_id()
    app = QApplication(sys.argv)
    app.setApplicationName("Notepad Plus")
    app.setApplicationDisplayName("Notepad Plus")
    app.setOrganizationName("Sajjad")
    app.setOrganizationDomain("local.notepad")

    _mark("QApplication")
    log_file = _setup_logging()
    _install_excepthook(log_file)
    _mark("logging")

    # Resolve now: a second instance forwards these paths to the first one,
    # which has a different working directory.
    initial_files = [
        str(Path(arg).resolve()) for arg in sys.argv[1:] if os.path.isfile(arg)
    ]
    guard = SingleInstanceGuard(sm.app_data_dir())
    if not guard.acquire():
        if guard.notify_running_instance(initial_files):
            return 0
        log.warning(
            "Another instance holds the lock but is not answering; "
            "continuing standalone."
        )
    else:
        guard.listen()

    _mark("single instance")

    from ui.main_window import APP_VERSION, MainWindow, _load_bundled_fonts
    from ui.styles import build_stylesheet

    _mark("import ui")
    app.setApplicationVersion(APP_VERSION)
    app.setWindowIcon(app_icon())
    _load_bundled_fonts()
    _mark("fonts")

    settings = sm.load()
    app.setStyleSheet(
        build_stylesheet(
            settings.get("theme", "system"),
            settings.get("accent_palette", "graphite"),
        )
    )
    ui_font = QFont()
    ui_font.setFamilies(sm.font_chain(settings, extra=("sans-serif",)))
    ui_font.setPointSize(10)
    app.setFont(ui_font)

    _mark("theme")
    window = MainWindow(initial_files)
    _mark("MainWindow")
    guard.files_received.connect(window.open_from_another_instance)
    window.show()
    _mark("show")
    # Logged from the event loop so it measures the moment the window is
    # actually usable, not just the moment show() returned.
    QTimer.singleShot(
        0,
        lambda: _report_startup(),
    )
    if "--smoke-test" in sys.argv:
        QTimer.singleShot(0, app.quit)
    exit_code = app.exec()
    guard.release()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
