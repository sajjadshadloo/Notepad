import json

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


def test_save_and_load_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTEPAD_DATA_DIR", str(tmp_path))
    note_path = tmp_path / "note.md"
    note_path.write_text("hello", encoding="utf-8")

    index = {}
    note_index.touch(index, str(note_path))

    loaded = note_index.load()
    assert str(note_path.resolve()) in loaded


def test_retired_tag_and_pin_fields_are_dropped_on_load(tmp_path, monkeypatch):
    """Indexes written by 2.6.0 and earlier carry tags/pinned. They are gone
    from the app, so the file should shed them rather than keep dead data."""
    monkeypatch.setenv("NOTEPAD_DATA_DIR", str(tmp_path))
    (tmp_path / "notes_index.json").write_text(
        json.dumps(
            {
                "C:/notes/a.md": {
                    "tags": ["old"],
                    "pinned": True,
                    "last_opened": "2026-01-01T00:00:00+00:00",
                }
            }
        ),
        encoding="utf-8",
    )

    entry = note_index.load()["C:/notes/a.md"]
    assert entry == {"last_opened": "2026-01-01T00:00:00+00:00"}


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


def test_direction_is_remembered_per_file(tmp_path, monkeypatch):
    """Documents default to RTL, so an English file is switched once and the
    choice has to survive closing and reopening it."""
    monkeypatch.setenv("NOTEPAD_DATA_DIR", str(tmp_path))
    note_path = tmp_path / "english.md"
    note_path.write_text("hello", encoding="utf-8")

    index = {}
    assert note_index.direction_for(index, str(note_path)) is None

    note_index.set_direction(index, str(note_path), "ltr")
    assert note_index.direction_for(index, str(note_path)) == "ltr"

    # It is written through to disk, not just held in memory.
    assert note_index.direction_for(note_index.load(), str(note_path)) == "ltr"


def test_direction_lookup_normalizes_the_path(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTEPAD_DATA_DIR", str(tmp_path))
    note_path = tmp_path / "note.md"
    note_path.write_text("hello", encoding="utf-8")

    index = {}
    note_index.set_direction(index, str(note_path), "ltr")
    indirect = tmp_path / "sub" / ".." / "note.md"
    assert note_index.direction_for(index, str(indirect)) == "ltr"
