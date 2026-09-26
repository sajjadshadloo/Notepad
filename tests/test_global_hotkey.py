"""Win+Alt+N, and the way it must not be caught.

Overriding nativeEvent on the main window made PyQt call into Python for
the messages sent while the native window was being created. Restoring a
maximized geometry does that inside __init__, and the process died on every
start — invisible offscreen, where no native window exists.
"""
import ctypes
import ctypes.wintypes
import sys

import pytest
from PyQt6.QtCore import QByteArray

from ui.main_window import HotkeyFilter, MainWindow


def test_the_window_does_not_override_native_event():
    assert "nativeEvent" not in MainWindow.__dict__


@pytest.mark.skipif(sys.platform != "win32", reason="Windows messages")
def test_the_filter_answers_only_its_own_hotkey(qapp, monkeypatch):
    calls = []
    monkeypatch.setattr("ui.main_window.QTimer.singleShot", lambda _ms, fn: calls.append(fn))
    hotkey = HotkeyFilter(0x4E50, "capture")
    kind = QByteArray(b"windows_generic_MSG")

    def send(message, w_param):
        msg = ctypes.wintypes.MSG()
        msg.message, msg.wParam = message, w_param
        return hotkey.nativeEventFilter(kind, ctypes.addressof(msg))

    assert send(0x0312, 0x4E50) == (True, 0)
    assert calls == ["capture"]
    assert send(0x0312, 0x1234) == (False, 0)
    assert send(0x0100, 0x4E50) == (False, 0)
    assert calls == ["capture"]
