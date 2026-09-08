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
