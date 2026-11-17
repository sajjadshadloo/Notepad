"""The release script refuses to build from uncommitted work."""
import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "build_release.py"


@pytest.fixture
def build():
    spec = importlib.util.spec_from_file_location("build_release", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_dirty_tree_is_refused_before_anything_runs(build, monkeypatch):
    calls = []
    monkeypatch.setattr(build, "dirty_files", lambda: [" M ui/editor.py"])
    monkeypatch.setattr(build.subprocess, "run", lambda *a, **k: calls.append(a))
    monkeypatch.setattr(build.sys, "argv", ["build_release.py"])
    assert build.main() == 1
    assert calls == [], "nothing may be built from uncommitted work"
