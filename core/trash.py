"""Deleting a note without destroying it.

A note is the user's writing, and a wrong click must be recoverable. On
Windows that means the Recycle Bin, which the shell exposes through
SHFileOperationW — there is no Python standard-library route to it.

If the shell call is unavailable or refuses, the caller is told so and can
decide; nothing here deletes permanently behind the user's back.
"""
import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)

# SHFileOperationW flags
_FO_DELETE = 0x0003
_FOF_ALLOWUNDO = 0x0040
_FOF_NOCONFIRMATION = 0x0010
_FOF_SILENT = 0x0004
_FOF_NOERRORUI = 0x0400


def available() -> bool:
    return sys.platform == "win32"


def send_to_recycle_bin(path: str | Path) -> bool:
    """Move one file to the Recycle Bin. False when that was not possible."""
    if not available():
        return False
    target = Path(path)
    if not target.exists():
        return False

    try:
        import ctypes
        from ctypes import wintypes

        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [
                ("hwnd", wintypes.HWND),
                ("wFunc", wintypes.UINT),
                ("pFrom", wintypes.LPCWSTR),
                ("pTo", wintypes.LPCWSTR),
                ("fFlags", ctypes.c_uint16),
                ("fAnyOperationsAborted", wintypes.BOOL),
                ("hNameMappings", ctypes.c_void_p),
                ("lpszProgressTitle", wintypes.LPCWSTR),
            ]

        # The path list is double-null terminated; one file still needs both.
        source = str(target.resolve()) + "\0\0"
        operation = SHFILEOPSTRUCTW(
            hwnd=None,
            wFunc=_FO_DELETE,
            pFrom=source,
            pTo=None,
            fFlags=_FOF_ALLOWUNDO
            | _FOF_NOCONFIRMATION
            | _FOF_SILENT
            | _FOF_NOERRORUI,
            fAnyOperationsAborted=False,
            hNameMappings=None,
            lpszProgressTitle=None,
        )
        result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))
    except Exception:
        log.warning("Recycle Bin unavailable for %s", target, exc_info=True)
        return False

    if result != 0 or operation.fAnyOperationsAborted:
        log.warning("SHFileOperationW refused %s (code %s)", target, result,
                    extra={'event': 'file.recycle.failed', 'reason': f'windows_error_{result}'})
        return False
    return not target.exists()
