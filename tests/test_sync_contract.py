import pytest

from core.sync_contract import LocalSyncStore, VersionConflict


def test_create_edit_and_reload_keep_identity_and_versions(tmp_path):
    state = tmp_path / "sync.json"
    store = LocalSyncStore(state)
    first = store.create("Daily/1405-07-01.md", "# امروز\n")
    assert first.version == 1
    assert store.create("other.txt", "second").id != first.id

    edited = store.change(first.id, first.version, text="# امروز\n- [ ] خرید")
    assert edited.id == first.id
    assert edited.version == 2
    assert LocalSyncStore(state).get(first.id) == edited


def test_stale_edit_preserves_both_versions_until_resolution(tmp_path):
    state = tmp_path / "sync.json"
    desktop = LocalSyncStore(state)
    original = desktop.create("note.md", "شروع")
    phone = LocalSyncStore(state)
    desktop.change(original.id, original.version, text="تغییر ویندوز")

    with pytest.raises(VersionConflict) as error:
        phone.change(original.id, original.version, text="تغییر گوشی")

    conflict = error.value.conflict
    restarted = LocalSyncStore(state)
    assert restarted.get(original.id).text == "تغییر ویندوز"
    assert restarted.conflicts()[0].proposed_text == "تغییر گوشی"
    assert restarted.conflicts()[0].current.text == "تغییر ویندوز"

    merged = restarted.resolve(conflict.id, "merge", "تغییر ویندوز\nتغییر گوشی")
    assert merged.version == 3
    assert merged.text == "تغییر ویندوز\nتغییر گوشی"
    assert LocalSyncStore(state).conflicts()[0].status == "resolved"


def test_delete_is_versioned_and_stale_delete_cannot_erase_edit(tmp_path):
    store = LocalSyncStore(tmp_path / "sync.json")
    note = store.create("note.txt", "متن اصلی")
    store.change(note.id, 1, text="ویرایش جدید")

    with pytest.raises(VersionConflict) as error:
        store.change(note.id, 1, delete=True)
    assert store.get(note.id).text == "ویرایش جدید"
    assert error.value.conflict.proposed_delete

    store.resolve(error.value.conflict.id, "keep_current")
    deleted = store.change(note.id, 2, delete=True)
    assert deleted.version == 3
    assert deleted.deleted
    assert deleted.text == "ویرایش جدید"  # tombstone retains recoverable text
    assert LocalSyncStore(store.state_file).get(note.id) == deleted


def test_stale_update_after_delete_is_saved_as_conflict(tmp_path):
    store = LocalSyncStore(tmp_path / "sync.json")
    note = store.create("note.md", "before")
    store.change(note.id, 1, delete=True)

    with pytest.raises(VersionConflict) as error:
        store.change(note.id, 1, text="offline edit")
    assert error.value.conflict.current.deleted
    restored = store.resolve(error.value.conflict.id, "use_proposed")
    assert restored.text == "offline edit"
    assert not restored.deleted
    assert restored.version == 3


def test_paths_are_relative_unique_and_supported(tmp_path):
    store = LocalSyncStore(tmp_path / "sync.json")
    store.create("Folder/Note.md", "a")
    for path in ("Folder/note.md", "../escape.md", "/absolute.md", "C:/note.md", "a\\b.md", "image.png"):
        with pytest.raises(ValueError):
            store.create(path, "bad")
