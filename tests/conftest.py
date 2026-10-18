import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QCoreApplication, QEvent
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("NotepadTests")
    app.setOrganizationName("Sajjad")
    return app


@pytest.fixture(autouse=True)
def _isolated_app_storage(tmp_path, monkeypatch):
    """No GUI test may scan or write the developer's real notes or account."""
    from core import settings_manager

    notes = tmp_path / "Documents" / "Notepad"
    notes.mkdir(parents=True)
    monkeypatch.setenv("NOTEPAD_DATA_DIR", str(tmp_path / "appdata"))
    monkeypatch.setitem(settings_manager.DEFAULTS, "default_save_dir", str(notes))
    monkeypatch.setitem(settings_manager.DEFAULTS, "notes_root", str(notes))


@pytest.fixture(autouse=True)
def _collect_deleted_widgets(qapp):
    """Actually destroy what each test asked to be deleted.

    deleteLater() only posts a DeferredDelete event; with no event loop
    running under pytest, the widget stays alive for the rest of the
    session. They pile up, and MainWindow._restyle calls
    QApplication.setStyleSheet, which re-polishes every widget alive in the
    process — walking a half-dead window from three files ago is an access
    violation that takes the interpreter with it. It surfaced roughly one
    run in seven.
    """
    yield
    qapp.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()
