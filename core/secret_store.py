"""Keep the sync key and the bot token readable only by this Windows account.

DPAPI encrypts with a key that belongs to the logged-in user, so a copy of the
settings file is useless on another computer or for another account. Off
Windows (only the tests run there) the value is stored as it is, marked so.
"""
import base64
import ctypes
import sys
from ctypes import wintypes


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi(data: bytes, protect: bool) -> bytes:
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    buffer = ctypes.create_string_buffer(data, len(data))
    source = _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    target = _Blob()
    call = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    if not call(ctypes.byref(source), None, None, None, None, 0, ctypes.byref(target)):
        raise OSError("Windows could not open the stored sync value")
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        kernel32.LocalFree(target.pbData)


def seal(text: str) -> str:
    """The form written to the settings file."""
    if not text:
        return ""
    if sys.platform != "win32":
        return "plain:" + text
    return "dpapi:" + base64.b64encode(_dpapi(text.encode("utf-8"), protect=True)).decode("ascii")


def unseal(stored: str) -> str:
    """The value behind a stored form. A bare value is an older plain one."""
    if not stored:
        return ""
    if stored.startswith("dpapi:"):
        return _dpapi(base64.b64decode(stored[len("dpapi:"):]), protect=False).decode("utf-8")
    if stored.startswith("plain:"):
        return stored[len("plain:"):]
    return stored
