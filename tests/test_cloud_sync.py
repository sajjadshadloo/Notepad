from pathlib import Path
from uuid import uuid4

import pytest

from core import trash
from core.cloud_sync import sync_once
from core.cloud_sync_status import record_sync_status


@pytest.fixture(autouse=True)
def recycle_bin(monkeypatch):
    """A stand-in Recycle Bin: tests must never fill the real one."""
    binned = []

    def send(path):
        binned.append(Path(path).name)
        Path(path).unlink()
        return True

    monkeypatch.setattr(trash, "send_to_recycle_bin", send)
    return binned


class FakeApi:
    def __init__(self):
        self.notes = {}

    def call(self, path, method="GET", body=None):
        if path == "/notes" and method == "GET":
            return {"notes": list(self.notes.values())}
        if path == "/notes" and method == "POST":
            note = next((n for n in self.notes.values() if n["path"] == body["path"]), None)
            if note:
                assert note["deleted"]
                note.update(text=body["text"], deleted=0, version=note["version"] + 1)
                return {"note": note}
            note = {"id": str(uuid4()), "path": body["path"], "text": body["text"],
                    "version": 1, "deleted": 0}
            self.notes[note["id"]] = note
            return {"note": note}
        note = self.notes[path.removeprefix("/notes/")]
        assert body["version"] == note["version"]
        note.update(version=note["version"] + 1,
                    text=body.get("text", note["text"]),
                    deleted=int(method == "DELETE"))
        return {"note": note}


def test_cloud_file_round_trip_and_delete(tmp_path: Path, recycle_bin):
    root = tmp_path / "notes"
    root.mkdir()
    state = tmp_path / "state.json"
    api = FakeApi()
    remote = api.call("/notes", "POST", {"path": "Telegram/item.md", "text": "خرید دارو"})["note"]
    assert sync_once(root, state, api).downloaded == 1
    path = root / "Telegram" / "item.md"
    assert path.read_text(encoding="utf-8") == "خرید دارو"
    path.write_text("خرید دارو و نان", encoding="utf-8")
    assert sync_once(root, state, api).uploaded == 1
    assert api.notes[remote["id"]]["text"] == "خرید دارو و نان"
    api.call("/notes/" + remote["id"], "DELETE", {"version": 2})
    assert sync_once(root, state, api).deleted == 1
    assert not path.exists()
    # A note deleted in Telegram goes to the Recycle Bin, not away for good.
    assert recycle_bin == ["item.md"]


def test_simultaneous_edits_of_one_line_settle_without_a_conflict_copy(tmp_path: Path):
    root = tmp_path / "notes"
    root.mkdir()
    state = tmp_path / "state.json"
    api = FakeApi()
    remote = api.call("/notes", "POST", {"path": "n.md", "text": "old"})["note"]
    sync_once(root, state, api)
    (root / "n.md").write_text("local", encoding="utf-8")
    api.call("/notes/" + remote["id"], "PUT", {"version": 1, "text": "remote"})
    assert sync_once(root, state, api).conflicts == 0
    # The more recent edit (the file just written here) wins on both sides.
    assert (root / "n.md").read_text(encoding="utf-8") == "local"
    assert api.notes[remote["id"]]["text"] == "local"
    assert not list(root.glob("*.sync-conflict-*"))


def test_recreate_a_deleted_local_file(tmp_path: Path):
    root = tmp_path / "notes"
    root.mkdir()
    state = tmp_path / "state.json"
    api = FakeApi()
    note = api.call("/notes", "POST", {"path": "Tasks/Inbox.md", "text": "old"})["note"]
    sync_once(root, state, api)
    api.call("/notes/" + note["id"], "DELETE", {"version": 1})
    sync_once(root, state, api)
    path = root / "Tasks" / "Inbox.md"
    assert not path.exists()
    path.write_text("new", encoding="utf-8")
    assert sync_once(root, state, api).uploaded == 1
    assert api.notes[note["id"]]["text"] == "new"
    assert not api.notes[note["id"]]["deleted"]


def test_open_file_waits_for_close_before_remote_edit_or_delete(tmp_path: Path):
    root = tmp_path / "notes"
    state = tmp_path / "state.json"
    api = FakeApi()
    note = api.call("/notes", "POST", {"path": "Tasks/Inbox.md", "text": "- [ ] work"})["note"]
    sync_once(root, state, api)
    path = root / "Tasks" / "Inbox.md"
    api.call("/notes/" + note["id"], "PUT", {"version": 1, "text": "- [x] work"})
    assert sync_once(root, state, api, {str(path)}).skipped == 1
    assert path.read_text(encoding="utf-8") == "- [ ] work"
    assert sync_once(root, state, api).downloaded == 1
    assert path.read_text(encoding="utf-8") == "- [x] work"
    api.call("/notes/" + note["id"], "DELETE", {"version": 2})
    assert sync_once(root, state, api, {str(path)}).skipped == 1
    assert path.exists()
    assert sync_once(root, state, api).deleted == 1
    assert not path.exists()


def test_sync_status_keeps_last_completion_after_error(tmp_path: Path):
    class StatusApi:
        calls = []

        def call(self, path, method="GET", body=None):
            self.calls.append((path, method, body))
            return {"ok": True}

    api = StatusApi()
    path = tmp_path / "status.json"
    from core.cloud_sync import SyncResult
    first = record_sync_status(path, api, SyncResult(downloaded=1))
    second = record_sync_status(path, api, error="network unavailable")
    assert first["state"] == "ok"
    assert second["state"] == "error"
    assert second["completed_at"] == first["completed_at"]
    assert api.calls[-1][0:2] == ("/sync-status", "POST")


def test_an_unreachable_cloud_says_why(monkeypatch):
    """"Cloud is unavailable" alone could not tell a timeout from a proxy."""
    from urllib.error import URLError

    import core.cloud_sync as cloud_sync

    def refuse(*_args, **_kwargs):
        raise URLError(ConnectionRefusedError(10061, "refused"))

    monkeypatch.setattr(cloud_sync, "urlopen", refuse)
    api = cloud_sync.CloudApi("https://example.invalid", "key")
    with pytest.raises(cloud_sync.SyncError, match=r"Cloud is unavailable \(ConnectionRefusedError"):
        api.call("/notes")


def test_a_named_proxy_is_used_even_with_the_system_proxy_off(monkeypatch):
    """The VPN's own port, so sync does not hang on its "system proxy" switch."""
    import core.cloud_sync as cloud_sync

    seen = {}

    class Opener:
        def open(self, request, timeout):
            seen["url"] = request.full_url
            raise OSError("stop")

    def build(handler):
        seen["proxies"] = handler.proxies
        return Opener()

    monkeypatch.setattr(cloud_sync, "build_opener", build)
    api = cloud_sync.CloudApi("https://example.invalid", "key", "http://127.0.0.1:10808")
    with pytest.raises(cloud_sync.SyncError):
        api.call("/notes")
    assert seen["proxies"] == {"http": "http://127.0.0.1:10808", "https": "http://127.0.0.1:10808"}
    assert seen["url"] == "https://example.invalid/api/notes"
