"""Small, opt-in file mirror for the versioned Cloudflare note API.

The journal records the last agreed hash and version. A local file and a
remote revision may only replace one another when the other side still has
that agreed content. Conflicts are retained as extra files, never discarded.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from PyQt6.QtCore import QLockFile

from core.file_service import read_text_file, write_text_file_atomic


class SyncError(Exception):
    pass


@dataclass
class SyncResult:
    downloaded: int = 0
    uploaded: int = 0
    deleted: int = 0
    conflicts: int = 0
    skipped: int = 0


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _safe_path(root: Path, rel: str) -> Path:
    parts = rel.split("/")
    if (not rel or "\\" in rel or ":" in rel or "\x00" in rel
            or any(not x or x in (".", "..") or x.startswith(".") for x in parts)
            or Path(rel).suffix.lower() not in (".md", ".txt", ".markdown")):
        raise SyncError("Unsafe cloud path")
    path = root.joinpath(*parts)
    if not path.resolve().is_relative_to(root.resolve()):
        raise SyncError("Cloud path escapes notes folder")
    return path


class CloudApi:
    def __init__(self, url: str, key: str):
        if not url.startswith("https://") or not key:
            raise SyncError("Cloud sync is not configured")
        self.url = url.rstrip("/")
        self.key = key

    def call(self, path: str, method: str = "GET", body: dict | None = None) -> dict:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        request = Request(self.url + "/api" + path, data=payload, method=method,
                          headers={"Authorization": "Bearer " + self.key,
                                   "Content-Type": "application/json",
                                   "User-Agent": "Mozilla/5.0 NotepadPlusSync/1"})
        try:
            with urlopen(request, timeout=15) as response:
                return json.load(response)
        except HTTPError as exc:
            if exc.code == 409:
                raise SyncError("Cloud version conflict") from exc
            raise SyncError(f"Cloud request failed ({exc.code})") from exc
        except (OSError, ValueError) as exc:
            raise SyncError("Cloud is unavailable") from exc


def _journal(path: Path) -> dict:
    if not path.exists():
        return {"items": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data.get("items"), dict):
            return data
    except (ValueError, OSError):
        pass
    raise SyncError("Sync journal is damaged; no files were changed")


def sync_once(root: Path, journal_file: Path, api: CloudApi,
              protected: set[str] | None = None) -> SyncResult:
    journal_file.parent.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(journal_file) + ".lock")
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        return SyncResult(skipped=1)
    try:
        return _sync_once(root, journal_file, api, protected)
    finally:
        lock.unlock()


def _sync_once(root: Path, journal_file: Path, api: CloudApi,
               protected: set[str] | None = None) -> SyncResult:
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    protected = {str(Path(p).resolve()).casefold() for p in (protected or set())}
    journal = _journal(journal_file)
    if journal.get("root") and journal["root"] != str(root):
        raise SyncError("Notes folder changed; sync needs a new pairing")
    journal["root"] = str(root)
    items = journal["items"]
    result = SyncResult()

    def save():
        write_text_file_atomic(journal_file, json.dumps(journal, ensure_ascii=False, indent=2))

    def mark(note, text):
        items[note["id"]] = {"path": note["path"], "version": note["version"],
                              "hash": _hash(text) if text is not None else None}
        save()

    def conflict(path, note):
        suffix = path.suffix
        copy = path.with_name(path.stem + ".sync-conflict-" + note["id"][:8] + suffix)
        if not copy.exists():
            write_text_file_atomic(copy, note["text"])
        result.conflicts += 1

    remote = api.call("/notes")["notes"]
    remote_by_path = {n["path"].casefold(): n for n in remote}
    if len(remote_by_path) != len(remote):
        raise SyncError("Duplicate cloud paths")
    for note in remote:
        path = _safe_path(root, note["path"])
        previous = items.get(note["id"])
        if previous and previous["path"] != note["path"]:
            raise SyncError("Cloud note path changed")
        is_protected = str(path.resolve()).casefold() in protected
        existing = path.exists()
        if existing and (path.is_symlink() or not path.is_file()):
            result.skipped += 1
            continue
        loaded = read_text_file(path) if existing else None
        local = loaded.text if loaded else None
        unchanged = previous is not None and (
            (_hash(local) if local is not None else None) == previous["hash"])
        remote_changed = previous is None or note["version"] != previous["version"]
        if is_protected:
            if remote_changed or not unchanged:
                result.skipped += 1
            continue
        if note["deleted"]:
            if (previous and existing and previous["hash"] is None and
                    not remote_changed and not is_protected):
                restored = api.call("/notes", "POST", {"path": note["path"],
                                                      "text": local})["note"]
                mark(restored, local)
                result.uploaded += 1
            elif previous and unchanged and not is_protected and (remote_changed or existing):
                if existing:
                    path.unlink()
                    result.deleted += 1
                mark(note, None)
            elif previous and not existing and remote_changed:
                mark(note, None)
            elif existing:
                result.conflicts += 1
            continue
        if previous is None:
            if existing and local != note["text"]:
                conflict(path, note)
            elif not is_protected:
                if not existing:
                    write_text_file_atomic(path, note["text"])
                    result.downloaded += 1
                mark(note, note["text"])
            else:
                result.skipped += 1
        elif unchanged and remote_changed:
            if is_protected:
                result.skipped += 1
            else:
                write_text_file_atomic(path, note["text"], loaded.encoding if loaded else "utf-8")
                mark(note, note["text"])
                result.downloaded += 1
        elif not unchanged and not remote_changed:
            try:
                updated = api.call("/notes/" + note["id"], "PUT" if existing else "DELETE",
                                   {"version": note["version"], **({"text": local} if existing else {})})["note"]
                mark(updated, local)
                result.uploaded += 1
            except SyncError:
                result.conflicts += 1
        elif not unchanged and remote_changed:
            conflict(path, note)

    tracked_paths = {v["path"].casefold() for v in items.values()}
    for path in root.rglob("*"):
        if (not path.is_file() or path.is_symlink() or
                path.suffix.lower() not in (".md", ".txt", ".markdown") or
                re.search(r"\.sync-conflict-[0-9a-f]{8}\.", path.name)):
            continue
        rel = path.relative_to(root).as_posix()
        if rel.casefold() in tracked_paths or rel.casefold() in remote_by_path:
            continue
        if str(path.resolve()).casefold() in protected:
            result.skipped += 1
            continue
        text = read_text_file(path).text
        if len(text) > 200000:
            result.skipped += 1
            continue
        created = api.call("/notes", "POST", {"path": rel, "text": text})["note"]
        mark(created, text)
        result.uploaded += 1
    return result
