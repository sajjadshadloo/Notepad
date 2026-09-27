"""An edit made on both sides merges when the edits do not touch.

tasks.md is edited on the phone and on the PC. Before this, a change on
both sides between two passes always set the phone's copy aside as a
conflict file, even when one side ticked a task and the other added one.
"""
import json
from pathlib import Path

import pytest

from core import trash
from core.cloud_sync import merge_lines, sync_once
from tests.test_cloud_sync import FakeApi

BASE = "- [ ] الف\n- [ ] ب\n- [ ] پ\n- [ ] ت\n"


@pytest.fixture(autouse=True)
def no_recycle_bin(monkeypatch):
    monkeypatch.setattr(trash, "send_to_recycle_bin", lambda path: False)


# The rules

def test_edits_on_different_lines_are_both_kept():
    local = BASE.replace("- [ ] الف", "- [x] الف")
    remote = BASE.replace("- [ ] ت", "- [ ] ت @۱۴۰۵/۰۷/۰۶")
    assert merge_lines(BASE, local, remote) == "- [x] الف\n- [ ] ب\n- [ ] پ\n- [ ] ت @۱۴۰۵/۰۷/۰۶\n"


def test_lines_added_at_the_end_on_both_sides_are_both_kept():
    assert merge_lines(BASE, BASE + "- [ ] رایانه\n", BASE + "- [ ] گوشی\n") == \
        BASE + "- [ ] رایانه\n- [ ] گوشی\n"


def test_the_same_line_changed_differently_is_not_guessed():
    local = BASE.replace("- [ ] ب", "- [x] ب")
    remote = BASE.replace("- [ ] ب", "- [ ] ب @۱۴۰۵/۰۷/۰۶")
    assert merge_lines(BASE, local, remote) is None


def test_neighbouring_lines_are_not_guessed_either():
    local = BASE.replace("- [ ] ب", "- [x] ب")
    remote = BASE.replace("- [ ] پ", "- [x] پ")
    assert merge_lines(BASE, local, remote) is None


def test_the_same_change_on_both_sides_is_taken_once():
    same = BASE.replace("- [ ] پ", "- [x] پ")
    assert merge_lines(BASE, same, same) == same


def test_a_windows_file_keeps_its_line_endings():
    local = BASE.replace("\n", "\r\n").replace("- [ ] الف", "- [x] الف")
    remote = BASE + "- [ ] جدید\n"
    assert merge_lines(BASE, local, remote) == \
        "- [x] الف\r\n- [ ] ب\r\n- [ ] پ\r\n- [ ] ت\r\n- [ ] جدید\r\n"


# The sync

def _agreed(tmp_path: Path, text: str = BASE):
    root = tmp_path / "notes"
    root.mkdir()
    state = tmp_path / "state.json"
    api = FakeApi()
    note = api.call("/notes", "POST", {"path": "tasks.md", "text": text})["note"]
    sync_once(root, state, api)
    return root, state, api, note


def test_a_tick_on_the_pc_and_a_task_from_the_phone_meet(tmp_path: Path):
    root, state, api, note = _agreed(tmp_path)
    (root / "tasks.md").write_text(BASE.replace("- [ ] الف", "- [x] الف"), encoding="utf-8", newline="")
    api.call("/notes/" + note["id"], "PUT", {"version": 1, "text": BASE + "- [ ] از گوشی\n"})

    result = sync_once(root, state, api)

    merged = "- [x] الف\n- [ ] ب\n- [ ] پ\n- [ ] ت\n- [ ] از گوشی\n"
    assert result.conflicts == 0
    assert (root / "tasks.md").read_text(encoding="utf-8") == merged
    assert api.notes[note["id"]]["text"] == merged
    assert not list(root.glob("*.sync-conflict-*"))
    # Both sides now agree, so the next pass has nothing to do.
    again = sync_once(root, state, api)
    assert (again.uploaded, again.downloaded, again.conflicts) == (0, 0, 0)


def test_the_same_line_on_both_sides_still_keeps_both_copies(tmp_path: Path):
    root, state, api, note = _agreed(tmp_path)
    (root / "tasks.md").write_text(BASE.replace("- [ ] ب", "- [x] ب"), encoding="utf-8", newline="")
    api.call("/notes/" + note["id"], "PUT", {"version": 1, "text": BASE.replace("- [ ] ب", "- [ ] ب!")})

    assert sync_once(root, state, api).conflicts == 1
    assert (root / "tasks.md").read_text(encoding="utf-8") == BASE.replace("- [ ] ب", "- [x] ب")
    assert (root / ("tasks.sync-conflict-" + note["id"][:8] + ".md")).exists()


def test_a_journal_from_before_merging_falls_back_to_a_copy(tmp_path: Path):
    """Entries written by 4.3.0 and earlier have no base text to merge from."""
    root, state, api, note = _agreed(tmp_path)
    journal = json.loads(state.read_text(encoding="utf-8"))
    del journal["items"][note["id"]]["text"]
    state.write_text(json.dumps(journal), encoding="utf-8", newline="")
    (root / "tasks.md").write_text(BASE.replace("- [ ] الف", "- [x] الف"), encoding="utf-8", newline="")
    api.call("/notes/" + note["id"], "PUT", {"version": 1, "text": BASE + "- [ ] از گوشی\n"})

    assert sync_once(root, state, api).conflicts == 1


def test_an_old_journal_learns_its_base_from_an_unchanged_file(tmp_path: Path):
    """After one quiet pass, a pre-merge journal can merge like a new one."""
    root, state, api, note = _agreed(tmp_path)
    journal = json.loads(state.read_text(encoding="utf-8"))
    del journal["items"][note["id"]]["text"]
    state.write_text(json.dumps(journal), encoding="utf-8", newline="")
    sync_once(root, state, api)  # nothing changed anywhere: just learns the base

    (root / "tasks.md").write_text(BASE.replace("- [ ] الف", "- [x] الف"), encoding="utf-8", newline="")
    api.call("/notes/" + note["id"], "PUT", {"version": 1, "text": BASE + "- [ ] از گوشی\n"})
    assert sync_once(root, state, api).conflicts == 0
