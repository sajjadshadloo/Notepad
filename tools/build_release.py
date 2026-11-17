"""Build the installer — only from a clean, committed tree.

4.7.2 was replaced on a user's machine by a build made from a checkout full
of uncommitted, half-finished work. This script refuses that: every release
is a commit, so it can be named, rebuilt and rolled back.

    python tools/build_release.py            # tests, PyInstaller, Inno Setup
    python tools/build_release.py --no-tests
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ISCC_CANDIDATES = [
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Inno Setup 6/ISCC.exe",
    Path("C:/Program Files (x86)/Inno Setup 6/ISCC.exe"),
    Path("C:/Program Files/Inno Setup 6/ISCC.exe"),
]


def run(*args: str) -> str:
    return subprocess.run(
        args, cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def dirty_files() -> list[str]:
    return [line for line in run("git", "status", "--porcelain").splitlines() if line]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-tests", action="store_true")
    options = parser.parse_args()

    dirty = dirty_files()
    if dirty:
        print("Refusing to build: the tree has uncommitted changes.")
        for line in dirty[:20]:
            print("   ", line)
        print("Commit them (or set them aside) and run again.")
        return 1

    commit = run("git", "rev-parse", "--short", "HEAD")
    print(f"Building from commit {commit}")

    if not options.no_tests:
        subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT, check=True)

    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "notepad.spec", "--noconfirm"],
        cwd=ROOT, check=True,
    )
    iscc = shutil.which("ISCC.exe") or next(
        (str(p) for p in ISCC_CANDIDATES if p.is_file()), None
    )
    if iscc is None:
        print("Inno Setup (ISCC.exe) not found; the app is in dist/NotepadPlus.")
        return 1
    subprocess.run([iscc, "installer.iss"], cwd=ROOT, check=True)

    if dirty_files():
        print("Warning: the build changed tracked files; check git status.")
    print(f"Done: dist/ holds the installer built from {commit}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
