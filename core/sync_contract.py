"""Local prototype of the versioned note contract used by future sync clients.

This store models the online authority without a network connection. Desktop
file mirroring and the remote API can use the same compare-and-swap rules.
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from uuid import uuid4

from core.file_service import write_text_file_atomic


@dataclass(frozen=True)
class Note:
    id: str
    path: str
    text: str
    version: int
    deleted: bool = False


@dataclass(frozen=True)
class Conflict:
    id: str
    note_id: str
    current: Note
    proposed_text: str | None
    proposed_delete: bool
    expected_version: int
    status: str = "open"
    resolution: str | None = None


class VersionConflict(Exception):
    def __init__(self, conflict: Conflict):
        super().__init__(f"Note changed since version {conflict.expected_version}")
        self.conflict = conflict


def _note_path(path: str) -> str:
    """Only relative note paths can enter a future sync API."""
    if not path or "\\" in path or ":" in path or "\x00" in path or path.startswith("/"):
        raise ValueError("Note path must be relative and use forward slashes")
    parts = PurePosixPath(path).parts
    if any(part in (".", "..") for part in parts) or PurePosixPath(path).suffix.lower() not in (".md", ".txt"):
        raise ValueError("Invalid note path")
    return str(PurePosixPath(path))


class LocalSyncStore:
    """Persistent local stand-in for the future server's revisioned note store."""

    def __init__(self, state_file: str | Path):
        self.state_file = Path(state_file)
        self._refresh()

    def _refresh(self) -> None:
        if self.state_file.exists():
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
        else:
            data = {"notes": {}, "conflicts": {}}
        self._notes = {key: Note(**item) for key, item in data["notes"].items()}
        self._conflicts = {
            key: Conflict(**{**item, "current": Note(**item["current"])})
            for key, item in data["conflicts"].items()
        }

    def _save(self) -> None:
        data = {
            "notes": {key: asdict(note) for key, note in self._notes.items()},
            "conflicts": {key: asdict(conflict) for key, conflict in self._conflicts.items()},
        }
        write_text_file_atomic(self.state_file, json.dumps(data, ensure_ascii=False, indent=2))

    def get(self, note_id: str) -> Note:
        self._refresh()
        return self._notes[note_id]

    def notes(self) -> list[Note]:
        self._refresh()
        return list(self._notes.values())

    def conflicts(self) -> list[Conflict]:
        self._refresh()
        return list(self._conflicts.values())

    def create(self, path: str, text: str) -> Note:
        self._refresh()
        path = _note_path(path)
        if any(note.path.casefold() == path.casefold() and not note.deleted for note in self._notes.values()):
            raise ValueError("An active note already uses this path")
        note = Note(id=str(uuid4()), path=path, text=text, version=1)
        self._notes[note.id] = note
        self._save()
        return note

    def change(
        self,
        note_id: str,
        expected_version: int,
        *,
        text: str | None = None,
        delete: bool = False,
    ) -> Note:
        if delete == (text is not None):
            raise ValueError("Provide either new text or delete=True")
        current = self.get(note_id)
        if current.version != expected_version or current.deleted:
            conflict = Conflict(
                id=str(uuid4()), note_id=note_id, current=current,
                proposed_text=text, proposed_delete=delete,
                expected_version=expected_version,
            )
            self._conflicts[conflict.id] = conflict
            self._save()
            raise VersionConflict(conflict)
        updated = Note(
            id=current.id, path=current.path,
            text=current.text if delete else text,
            version=current.version + 1, deleted=delete,
        )
        self._notes[note_id] = updated
        self._save()
        return updated

    def resolve(self, conflict_id: str, choice: str, merged_text: str | None = None) -> Note:
        """Retain both versions in conflict history after a user decision."""
        self._refresh()
        conflict = self._conflicts[conflict_id]
        if conflict.status != "open":
            raise ValueError("Conflict is already resolved")
        if choice not in ("keep_current", "use_proposed", "merge"):
            raise ValueError("Unknown resolution")
        if choice == "merge" and merged_text is None:
            raise ValueError("Merged text is required")
        current = self.get(conflict.note_id)
        if current.version != conflict.current.version:
            raise ValueError("Note changed again; refresh the conflict")
        if choice == "keep_current":
            result = current
        else:
            result = Note(
                id=current.id, path=current.path,
                text=merged_text if choice == "merge" else (
                    current.text if conflict.proposed_delete else conflict.proposed_text
                ),
                version=current.version + 1,
                deleted=choice == "use_proposed" and conflict.proposed_delete,
            )
            self._notes[result.id] = result
        self._conflicts[conflict_id] = Conflict(
            **{**asdict(conflict), "current": conflict.current,
               "status": "resolved", "resolution": choice}
        )
        self._save()
        return result
