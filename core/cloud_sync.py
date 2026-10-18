"""Small, opt-in file mirror for the versioned Cloudflare note API.

The journal records the last agreed hash and version. A local file and a
remote revision may only replace one another when the other side still has
that agreed content. Conflicts are retained as extra files, never discarded.
"""

import difflib
import hashlib
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener, urlopen

from PyQt6.QtCore import QLockFile

from core.file_service import read_text_file, write_text_file_atomic
from core import trash


log = logging.getLogger("notepad.cloud_sync")


class SyncError(Exception):
    # The HTTP status, when the server answered at all.
    status = None

    def __init__(self, message="", *, code="sync_error"):
        super().__init__(message)
        self.diagnostic_code = code


@dataclass
class SyncResult:
    downloaded: int = 0
    uploaded: int = 0
    deleted: int = 0
    conflicts: int = 0
    skipped: int = 0


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class Merged:
    text: str
    # Where both sides changed the same lines differently: (kept, dropped).
    clashes: list


def merge_lines(base: str, local: str, remote: str, prefer_local: bool = True) -> Merged:
    """Combine two edits of one text, line by line, against their common base.

    Edits on different lines are all kept. Lines added at the same place on
    both sides are all kept, this side's first. Where both sides changed the
    same lines (or lines right beside each other) differently:

    - both replaced the same number of lines — one task ticked here, re-dated
      there — the more recent side wins, and what it replaced is returned in
      `clashes` so it can be logged;
    - otherwise — a side added or removed lines — both versions are kept,
      this side's first, so nothing written is lost.

    It never gives up: a conflict that only a person can settle, and that has
    no place to be settled, just stays conflicted for ever. The result keeps
    this side's line endings.
    """
    newline = "\r\n" if "\r\n" in local else "\n"
    b, mine, theirs = (t.replace("\r\n", "\n").split("\n") for t in (base, local, remote))

    def edits(other):
        matcher = difflib.SequenceMatcher(None, b, other, autojunk=False)
        return [(i1, i2, other[j1:j2]) for tag, i1, i2, j1, j2 in matcher.get_opcodes()
                if tag != "equal"]

    tagged = sorted([(*e, 0) for e in edits(mine)] + [(*e, 1) for e in edits(theirs)],
                    key=lambda e: (e[0], e[1], e[3]))

    def apply(region_start, region_end, side_edits):
        lines, at = [], region_start
        for start, end, replacement, _ in side_edits:
            lines.extend(b[at:start])
            lines.extend(replacement)
            at = end
        lines.extend(b[at:region_end])
        return lines

    clusters = []
    for edit in tagged:
        # Edits that touch or overlap belong to one cluster; so do insertions
        # at one spot. The right order of neighbours is a guess either way.
        if clusters and edit[0] <= clusters[-1][1]:
            clusters[-1][2].append(edit)
            clusters[-1][1] = max(clusters[-1][1], edit[1])
        else:
            clusters.append([edit[0], edit[1], [edit]])

    out, at, clashes = [], 0, []
    for start, end, members in clusters:
        out.extend(b[at:start])
        ours = [e for e in members if e[3] == 0]
        theirs_ = [e for e in members if e[3] == 1]
        mine_lines = apply(start, end, ours)
        their_lines = apply(start, end, theirs_)
        if not theirs_ or mine_lines == their_lines:
            out.extend(mine_lines)
        elif not ours:
            out.extend(their_lines)
        elif len(mine_lines) == len(their_lines) and all(e[0] < e[1] for e in members):
            kept, dropped = (mine_lines, their_lines) if prefer_local else (their_lines, mine_lines)
            out.extend(kept)
            clashes.append((kept, dropped))
        else:
            out.extend(mine_lines + [x for x in their_lines if x not in mine_lines])
        at = end
    out.extend(b[at:])
    return Merged(newline.join(out), clashes)


def _safe_path(root: Path, rel: str) -> Path:
    parts = rel.split("/")
    if (not rel or "\\" in rel or ":" in rel or "\x00" in rel
            or any(not x or x in (".", "..") or x.startswith(".") for x in parts)
            or Path(rel).suffix.lower() not in (".md", ".txt", ".markdown")):
        raise SyncError("Unsafe cloud path", code="unsafe_path")
    path = root.joinpath(*parts)
    if not path.resolve().is_relative_to(root.resolve()):
        raise SyncError("Cloud path escapes notes folder", code="unsafe_path")
    return path


class CloudApi:
    def __init__(self, url: str, key: str, proxy: str = ""):
        if not url.startswith("https://") or not key:
            raise SyncError("Cloud sync is not configured", code="unconfigured")
        self.url = url.rstrip("/")
        self.key = key
        # Where the Worker is filtered, it is reached through the VPN's local
        # port. Named here, sync keeps working when the VPN's "system proxy"
        # switch is off; left empty, the system's own proxy settings apply.
        self._open = (build_opener(ProxyHandler({"http": proxy, "https": proxy})).open
                      if proxy else urlopen)

    def call(self, path: str, method: str = "GET", body: dict | None = None) -> dict:
        started = time.monotonic()
        # Paths are templates, never request bodies, URLs, keys or pairing codes.
        route = re.sub(r'/[0-9a-f-]{36}(?=/|$)', '/{id}', path.split('?', 1)[0])
        fields = {'route': route, 'method': method, 'request_id': str(uuid.uuid4())}
        log.debug('Server request started', extra={'event': 'http.started', **fields})
        http_status = None
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        request = Request(self.url + "/api" + path, data=payload, method=method,
                          headers={"Authorization": "Bearer " + self.key,
                                   "Content-Type": "application/json",
                                   "User-Agent": "Mozilla/5.0 NotepadPlusSync/1"})
        try:
            with self._open(request, timeout=15) as response:
                http_status = getattr(response, 'status', 200)
                result = json.load(response)
                log.debug('Server request completed', extra={'event': 'http.completed', **fields,
                    'duration_ms': (time.monotonic() - started) * 1000, 'http_status': http_status})
                return result
        except HTTPError as exc:
            log.warning('Server rejected request', extra={'event': 'http.rejected', **fields,
                'http_status': exc.code, 'duration_ms': (time.monotonic() - started) * 1000})
            if exc.code == 409:
                raise SyncError("Cloud version conflict", code="version_conflict") from exc
            message = {413: "ظرفیت آزمایشی دفترچه یا اندازهٔ متن بیش از حد است؛ فایل محلی محفوظ است.",
                       429: "درخواست زیاد است؛ همگام‌سازی کمی بعد دوباره انجام می‌شود."}.get(exc.code)
            error = SyncError(message or f"Cloud request failed ({exc.code})", code="http_error")
            error.status = exc.code
            raise error from exc
        except (OSError, ValueError) as exc:
            log.warning('Network or response decoding failed', exc_info=True, extra={'event': 'http.failed', **fields,
                'duration_ms': (time.monotonic() - started) * 1000, 'http_status': http_status})
            # Say which way it failed: a timeout, a refused proxy and a page
            # that is not JSON all need different fixes.
            reason = getattr(exc, "reason", None) or exc
            raise SyncError(f"Cloud is unavailable ({type(reason).__name__}: {reason})"[:150], code="network_unavailable") from exc


def _journal(path: Path) -> dict:
    if not path.exists():
        return {"items": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data.get("items"), dict):
            return data
    except (ValueError, OSError):
        pass
    raise SyncError("Sync journal is damaged; no files were changed", code="journal_damaged")


def sync_once(root: Path, journal_file: Path, api: CloudApi,
              protected: set[str] | None = None, excluded_paths: tuple[str, ...] = ()) -> SyncResult:
    journal_file.parent.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(journal_file) + ".lock")
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        return SyncResult(skipped=1)
    try:
        return _sync_once(root, journal_file, api, protected, excluded_paths)
    finally:
        lock.unlock()


def _sync_once(root: Path, journal_file: Path, api: CloudApi,
               protected: set[str] | None = None, excluded_paths: tuple[str, ...] = ()) -> SyncResult:
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    protected = {str(Path(p).resolve()).casefold() for p in (protected or set())}
    journal = _journal(journal_file)
    account = getattr(api, "account_id", "")
    if account:
        if journal.get("account_id") and journal["account_id"] != account:
            raise SyncError("این پوشه به حساب دیگری متصل است؛ هیچ فایلی تغییر نکرد.", code="account_mismatch")
        if not journal.get("account_id") and journal.get("items") and account != "legacy-owner":
            raise SyncError("این پوشه سابقهٔ همگام‌سازی دارد؛ اتصال به حساب تازه نیاز به پوشهٔ جدا دارد.", code="legacy_journal")
        journal["account_id"] = account
    if journal.get("root") and journal["root"] != str(root):
        raise SyncError("Notes folder changed; sync needs a new pairing", code="folder_changed")
    journal["root"] = str(root)
    items = journal["items"]
    result = SyncResult()
    exclusions = tuple(p.replace("\\", "/").strip("/").casefold() for p in excluded_paths if p.strip("/\\"))

    def excluded(relative):
        value = relative.replace("\\", "/").casefold()
        return any(value == p or value.startswith(p + "/") for p in exclusions)

    def save():
        write_text_file_atomic(journal_file, json.dumps(journal, ensure_ascii=False, indent=2))

    def mark(note, text):
        # The agreed text itself is kept too: it is the common base that lets
        # an edit made on both sides be merged instead of set aside.
        items[note["id"]] = {"path": note["path"], "version": note["version"],
                              "hash": _hash(text) if text is not None else None,
                              "text": text}
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
        raise SyncError("Duplicate cloud paths", code="duplicate_paths")
    for note in remote:
        if excluded(note["path"]):
            result.skipped += 1
            continue
        path = _safe_path(root, note["path"])
        previous = items.get(note["id"])
        if previous and previous["path"] != note["path"]:
            raise SyncError("Cloud note path changed", code="remote_path_changed")
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
        if unchanged and local is not None and "text" not in previous:
            # Journals from before merging kept only a hash. A file that still
            # matches it *is* the agreed text, so it can serve as the base.
            previous["text"] = local
            save()
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
                    # Deleted in Telegram: recoverable here, like a delete in the app.
                    if trash.available():
                        if not trash.send_to_recycle_bin(path):
                            result.skipped += 1
                            continue
                    else:
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
            base = previous.get("text")
            if base is None or local is None:
                conflict(path, note)
                continue
            merge = merge_lines(base, local, note["text"],
                                prefer_local=path.stat().st_mtime * 1000 >= (note.get("updated_at") or 0))
            merged = merge.text
            for kept, dropped in merge.clashes:
                log.info("Merged %s: kept %r, set aside %r", note["path"], kept, dropped)
            if merged == note["text"]:
                updated = note
            else:
                try:
                    updated = api.call("/notes/" + note["id"], "PUT",
                                       {"version": note["version"], "text": merged})["note"]
                except SyncError:
                    # Changed again on the way; the next pass merges once more.
                    result.conflicts += 1
                    continue
            write_text_file_atomic(path, merged, loaded.encoding)
            mark(updated, merged)
            result.downloaded += 1
            result.uploaded += 1

    tracked_paths = {v["path"].casefold() for v in items.values()}
    for path in root.rglob("*"):
        if (not path.is_file() or path.is_symlink() or
                path.suffix.lower() not in (".md", ".txt", ".markdown") or
                re.search(r"\.sync-conflict-[0-9a-f]{8}\.", path.name)):
            continue
        rel = path.relative_to(root).as_posix()
        if excluded(rel) or (account and any(part.startswith(".") for part in path.relative_to(root).parts)):
            continue
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
