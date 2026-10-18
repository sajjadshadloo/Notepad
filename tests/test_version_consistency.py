"""The version shown by the app must match the installer and the file version.

The updater compares the running version with the published one, so a stale
constant makes an installed release offer itself again.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _find(text, pattern):
    match = re.search(pattern, text, re.MULTILINE)
    assert match, pattern
    return match.group(1)


def test_app_installer_and_file_versions_agree():
    app = _find((ROOT / "ui" / "main_window.py").read_text(encoding="utf-8"),
                r'^APP_VERSION = "([^"]+)"')
    installer = _find((ROOT / "installer.iss").read_text(encoding="utf-8"),
                      r'#define MyAppVersion "([^"]+)"')
    file_version = _find((ROOT / "version_info.txt").read_text(encoding="utf-8"),
                         r"StringStruct\('FileVersion', '([^']+)'\)")
    assert app == installer
    assert file_version == f"{app}.0"
