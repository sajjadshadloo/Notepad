"""Keeping the app alive in the notification area.

The reason is measured, not stylistic. In the packaged build almost all of
startup is Windows paging a 69 MB Qt runtime off disk and Defender scanning
it — the Python side of building the window takes 0.2s, the packaged side
took 4.5s, and a cold start reached 12-20s. None of that can be optimised
away in Python, because none of it is Python.

So the fix is to not pay it twice: closing the window hides it instead of
ending the process, and opening it again is a `show()`. The one real cost is
that the app now has to be quit deliberately, which is what the tray menu and
File > Exit are for.
"""
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon


class Tray(QSystemTrayIcon):
    """The tray presence, with the two commands that actually matter."""

    def __init__(self, icon: QIcon, window):
        super().__init__(icon, window)
        self._window = window
        self.setToolTip("Notepad Plus")

        menu = QMenu()
        self.open_action = QAction("باز کردن", menu)
        self.open_action.triggered.connect(self.reveal)
        self.quit_action = QAction("خروج", menu)
        self.quit_action.triggered.connect(window.quit_application)
        menu.addAction(self.open_action)
        menu.addSeparator()
        menu.addAction(self.quit_action)
        # Held on the instance: QSystemTrayIcon does not take ownership, and
        # a menu that only the local scope referenced is collected, leaving a
        # tray icon whose right-click does nothing.
        self._menu = menu
        self.setContextMenu(menu)

        self.activated.connect(self._activated)

    def _activated(self, reason):
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.reveal()

    def reveal(self):
        """Bring the window back, from hidden or minimised."""
        window = self._window
        window.showNormal()
        window.raise_()
        window.activateWindow()
