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
    assert merge_lines(BASE, local, remote).text == "- [x] الف\n- [ ] ب\n- [ ] پ\n- [ ] ت @۱۴۰۵/۰۷/۰۶\n"


def test_lines_added_at_the_end_on_both_sides_are_both_kept():
    assert merge_lines(BASE, BASE + "- [ ] رایانه\n", BASE + "- [ ] گوشی\n").text == \
        BASE + "- [ ] رایانه\n- [ ] گوشی\n"


def test_the_same_line_changed_differently_goes_to_the_newer_side():
    local = BASE.replace("- [ ] ب", "- [x] ب")
    remote = BASE.replace("- [ ] ب", "- [ ] ب @۱۴۰۵/۰۷/۰۶")
    mine = merge_lines(BASE, local, remote, prefer_local=True)
    assert mine.text == local
    assert mine.clashes == [(["- [x] ب"], ["- [ ] ب @۱۴۰۵/۰۷/۰۶"])]
    theirs = merge_lines(BASE, local, remote, prefer_local=False)
    assert theirs.text == remote
    assert theirs.clashes == [(["- [ ] ب @۱۴۰۵/۰۷/۰۶"], ["- [x] ب"])]


def test_neighbouring_lines_are_settled_as_one_place():
    """Two ticks side by side: both are real changes, and both are kept."""
    local = BASE.replace("- [ ] ب", "- [x] ب")
    remote = BASE.replace("- [ ] پ", "- [x] پ")
    # Same size on both sides, so the newer side's version of the pair wins.
    assert merge_lines(BASE, local, remote, prefer_local=True).text == local
    assert merge_lines(BASE, local, remote, prefer_local=False).text == remote


def test_when_one_side_added_lines_both_versions_are_kept():
    local = BASE.replace("- [ ] ب\n", "- [ ] ب\n- [ ] تازهٔ رایانه\n")
    remote = BASE.replace("- [ ] ب", "- [x] ب")
    merged = merge_lines(BASE, local, remote).text
    assert "- [x] ب" in merged and "- [ ] ب" in merged and "- [ ] تازهٔ رایانه" in merged
    assert merged.count("- [ ] پ") == 1


def test_nothing_is_ever_returned_unmerged():
    """A conflict nobody can settle stays a conflict for ever."""
    for local, remote in (("", "x\ny\n"), ("a\nb\n", ""), ("q", "r"), (BASE, BASE)):
        assert isinstance(merge_lines(BASE, local, remote).text, str)


def test_the_same_change_on_both_sides_is_taken_once():
    same = BASE.replace("- [ ] پ", "- [x] پ")
    assert merge_lines(BASE, same, same).text == same


def test_a_windows_file_keeps_its_line_endings():
    local = BASE.replace("\n", "\r\n").replace("- [ ] الف", "- [x] الف")
    remote = BASE + "- [ ] جدید\n"
    assert merge_lines(BASE, local, remote).text == \
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


def test_the_same_line_on_both_sides_no_longer_leaves_a_conflict(tmp_path: Path):
    root, state, api, note = _agreed(tmp_path)
    (root / "tasks.md").write_text(BASE.replace("- [ ] ب", "- [x] ب"), encoding="utf-8", newline="")
    api.call("/notes/" + note["id"], "PUT", {"version": 1, "text": BASE.replace("- [ ] ب", "- [ ] ب!")})

    assert sync_once(root, state, api).conflicts == 0
    assert not list(root.glob("*.sync-conflict-*"))
    text = (root / "tasks.md").read_text(encoding="utf-8")
    assert api.notes[note["id"]]["text"] == text
    again = sync_once(root, state, api)
    assert (again.uploaded, again.downloaded, again.conflicts) == (0, 0, 0)


def test_a_conflict_that_piled_up_over_days_still_settles(tmp_path: Path):
    """The phone kept editing while the PC could not take it: many versions
    behind, with the same lines changed on both sides."""
    root, state, api, note = _agreed(tmp_path)
    (root / "tasks.md").write_text(
        BASE.replace("- [ ] ب", "- [ ] ب @۱۴۰۵/۰۷/۱۳").replace("- [ ] ت", "- [x] ت"),
        encoding="utf-8", newline="")
    version = 1
    for n in range(5):
        text = BASE.replace("- [ ] ب", "- [x] ب") + "".join(f"- [ ] از گوشی {k}\n" for k in range(n + 1))
        api.call("/notes/" + note["id"], "PUT", {"version": version, "text": text})
        version += 1

    assert sync_once(root, state, api).conflicts == 0
    text = (root / "tasks.md").read_text(encoding="utf-8")
    assert "- [x] ت" in text and "از گوشی 4" in text
    assert api.notes[note["id"]]["text"] == text


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
