"""The tab strip, separated from the pages it switches between.

The design stacks the window as: top bar, tab strip, format bar, then the
sidebar and editor side by side. A QTabWidget cannot produce that — its pages
sit directly under its own bar, so nothing can come between them.

So the bar and the page stack are two widgets the window lays out itself,
behind the slice of the QTabWidget API the rest of the window already uses.
"""
from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QStackedWidget,
    QTabBar,
    QWidget,
)


class DocumentTabs(QWidget):
    """The tab strip. `pages` is the stack it drives."""

    tabCloseRequested = pyqtSignal(int)
    currentChanged = pyqtSignal(int)

    def __init__(self, bar: QTabBar, parent=None):
        super().__init__(parent)
        self.setObjectName("documentTabs")
        # Tabs start at the right edge, the + after the last one.
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._bar = bar
        self._bar.setParent(self)
        self.pages = QStackedWidget()
        self.pages.setObjectName("documentPages")

        # Tabs keep their natural width; QTabBar otherwise stretches them to
        # fill the strip, so a lone document became one very wide tab.
        self._bar.setExpanding(False)
        # Without this the bar's minimumSizeHint reserves room for the two
        # scroll arrows it never shows, leaving ~37px of dead strip between
        # the last tab and the + button.
        self._bar.setUsesScrollButtons(False)
        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(0, 0, 0, 0)
        self._row.setSpacing(0)
        self._row.addWidget(self._bar, 0)
        new_button = getattr(self._bar, "new_button", None)
        if new_button is not None:
            new_button.setParent(self)
            self._row.addWidget(new_button)
        self._row.addStretch(1)

        self._bar.currentChanged.connect(self._current_changed)
        self._bar.tabCloseRequested.connect(self.tabCloseRequested)
        self._bar.tabMoved.connect(self._tab_moved)

    # The QTabWidget surface the window uses

    def tabBar(self) -> QTabBar:
        return self._bar

    def count(self) -> int:
        return self._bar.count()

    def widget(self, index: int):
        return self.pages.widget(index)

    def currentWidget(self):
        return self.pages.currentWidget()

    def currentIndex(self) -> int:
        return self._bar.currentIndex()

    def indexOf(self, widget) -> int:
        return self.pages.indexOf(widget)

    def addTab(self, widget, text: str) -> int:
        self.pages.addWidget(widget)
        return self._bar.addTab(text)

    def insertTab(self, index: int, widget, text: str) -> int:
        self.pages.insertWidget(index, widget)
        return self._bar.insertTab(index, text)

    def removeTab(self, index: int):
        page = self.pages.widget(index)
        if page is not None:
            self.pages.removeWidget(page)
            page.setParent(None)
        self._bar.removeTab(index)

    def setCurrentIndex(self, index: int):
        self._bar.setCurrentIndex(index)
        self.pages.setCurrentIndex(index)

    def setCurrentWidget(self, widget):
        index = self.pages.indexOf(widget)
        if index >= 0:
            self.setCurrentIndex(index)

    def tabText(self, index: int) -> str:
        return self._bar.tabText(index)

    def setTabText(self, index: int, text: str):
        self._bar.setTabText(index, text)

    def tabIcon(self, index: int):
        return self._bar.tabIcon(index)

    def setTabIcon(self, index: int, icon):
        self._bar.setTabIcon(index, icon)

    def setTabToolTip(self, index: int, text: str):
        self._bar.setTabToolTip(index, text)

    def setTabsClosable(self, closable: bool):
        self._bar.setTabsClosable(closable)

    def setMovable(self, movable: bool):
        self._bar.setMovable(movable)

    def setDocumentMode(self, on: bool):
        self._bar.setDocumentMode(on)

    def setIconSize(self, size: QSize):
        self._bar.setIconSize(size)

    def setCornerWidget(self, widget: QWidget, _corner=None):
        """Anything parked at the end of the strip — the progress meter."""
        self._row.addWidget(widget)

    # Keeping the two halves in step

    def _current_changed(self, index: int):
        self.pages.setCurrentIndex(index)
        self.currentChanged.emit(index)

    def _tab_moved(self, source: int, target: int):
        """Dragging a tab has to carry its page with it."""
        page = self.pages.widget(source)
        if page is None:
            return
        self.pages.removeWidget(page)
        self.pages.insertWidget(target, page)
        self.pages.setCurrentIndex(self._bar.currentIndex())
