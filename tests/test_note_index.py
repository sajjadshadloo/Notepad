import os

import core.note_index as note_index


def test_touch_creates_entry_and_sets_timestamp(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTEPAD_DATA_DIR", str(tmp_path))
    note_path = tmp_path / "note.md"
    note_path.write_text("hello", encoding="utf-8")

    index = {}
    note_index.touch(index, str(note_path))

    key = str(note_path.resolve())
    assert key in index
    assert index[key]["last_opened"]
    assert index[key]["pinned"] is False
    assert index[key]["tags"] == []


def test_save_and_load_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTEPAD_DATA_DIR", str(tmp_path))
    note_path = tmp_path / "note.md"
    note_path.write_text("hello", encoding="utf-8")

    index = {}
    note_index.touch(index, str(note_path))

    loaded = note_index.load()
    assert str(note_path.resolve()) in loaded


def test_set_pinned(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTEPAD_DATA_DIR", str(tmp_path))
    note_path = tmp_path / "note.md"
    note_path.write_text("hello", encoding="utf-8")

    index = {}
    note_index.set_pinned(index, str(note_path), True)
    key = str(note_path.resolve())
    assert index[key]["pinned"] is True

    note_index.set_pinned(index, str(note_path), False)
    assert index[key]["pinned"] is False


def test_add_and_remove_tag(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTEPAD_DATA_DIR", str(tmp_path))
    note_path = tmp_path / "note.md"
    note_path.write_text("hello", encoding="utf-8")

    index = {}
    note_index.add_tag(index, str(note_path), "کار")
    note_index.add_tag(index, str(note_path), "کار")  # duplicate, no-op
    key = str(note_path.resolve())
    assert index[key]["tags"] == ["کار"]

    note_index.add_tag(index, str(note_path), "شخصی")
    assert set(index[key]["tags"]) == {"کار", "شخصی"}

    note_index.remove_tag(index, str(note_path), "کار")
    assert index[key]["tags"] == ["شخصی"]


def test_all_tags_dedup_and_sorted(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTEPAD_DATA_DIR", str(tmp_path))
    note_a = tmp_path / "a.md"
    note_b = tmp_path / "b.md"
    note_a.write_text("a", encoding="utf-8")
    note_b.write_text("b", encoding="utf-8")

    index = {}
    note_index.add_tag(index, str(note_a), "b-tag")
    note_index.add_tag(index, str(note_b), "a-tag")
    note_index.add_tag(index, str(note_b), "b-tag")

    assert note_index.all_tags(index) == ["a-tag", "b-tag"]


def test_prune_removes_missing_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTEPAD_DATA_DIR", str(tmp_path))
    kept = tmp_path / "kept.md"
    removed = tmp_path / "removed.md"
    kept.write_text("kept", encoding="utf-8")
    removed.write_text("removed", encoding="utf-8")

    index = {}
    note_index.touch(index, str(kept))
    note_index.touch(index, str(removed))

    note_index.prune(index, {str(kept.resolve())})

    assert str(kept.resolve()) in index
    assert str(removed.resolve()) not in index
