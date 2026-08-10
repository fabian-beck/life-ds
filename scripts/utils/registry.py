#!/usr/bin/env python3
"""The registries: ``persons.json``, ``meta_stories.json`` and their
per-language derivations.

All of them are the same document — ``{"people": [...]}`` or
``{"meta_stories": [...]}``, a list of entries identified by ``id`` — and
every writer performed the same four steps around it: read the file (or start
an empty one), find the entry by id, replace or append it, write the file
back. That shape was written out five times, and the copies had drifted in the
ways copies do. Three of them wrote with a bare ``json.dumps`` rather than
``json_io.write_json``, which is the one thing that must not vary: a writer
that disagrees about the trailing newline churns the whole file the next time
another script touches it.

What is *not* shared, and stays with each caller, is how an entry is built and
in what order the entries end up. The dataset generator sorts by name, the
translations sort to match the English registry, and the portrait writer does
not reorder at all — so ordering is asked for rather than assumed.

    registry = Registry(REGISTER_PATH)
    registry.upsert(entry, preserve=("created",))
    registry.sort_by_name()
    registry.save()
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .json_io import read_json, write_json

PEOPLE = "people"
META_STORIES = "meta_stories"


@dataclass
class Registry:
    """One registry document, loaded on first use and written on ``save()``.

    Loading is lazy and mutation is in memory, because every caller does
    several things to the document before writing it once.
    """

    path: Path
    collection: str = PEOPLE
    _document: Optional[Dict[str, Any]] = field(default=None, init=False, repr=False)

    # -- reading ----------------------------------------------------------

    @property
    def document(self) -> Dict[str, Any]:
        """The whole file. A registry that does not exist yet reads as empty.

        Keys other than the collection are preserved untouched: the file is
        the caller's, not this class's.
        """
        if self._document is None:
            loaded = read_json(self.path) if self.path.exists() else None
            self._document = loaded if isinstance(loaded, dict) else {}
            self._document.setdefault(self.collection, [])
        return self._document

    @property
    def entries(self) -> List[Dict[str, Any]]:
        """The registry's entries, live — mutating this mutates the document."""
        entries = self.document.setdefault(self.collection, [])
        if not isinstance(entries, list):  # a malformed file is an empty one
            entries = []
            self.document[self.collection] = entries
        return entries

    def find(self, entry_id: str) -> Optional[Dict[str, Any]]:
        """The entry with this id, or ``None``."""
        for entry in self.entries:
            if isinstance(entry, dict) and entry.get("id") == entry_id:
                return entry
        return None

    def ids(self) -> List[str]:
        """Every entry's id, in file order — a reference for `sort_like`."""
        return [
            str(entry["id"])
            for entry in self.entries
            if isinstance(entry, dict) and entry.get("id") is not None
        ]

    # -- writing ----------------------------------------------------------

    def upsert(
        self,
        entry: Dict[str, Any],
        *,
        preserve: Sequence[str] = (),
        merge: bool = True,
    ) -> Dict[str, Any]:
        """Store ``entry``, replacing the one with its id or appending it.

        ``merge`` keeps fields the existing entry has and the new one does
        not, which is how a script that knows about portraits can update a
        registry entry without dropping the roles a different script wrote.
        ``preserve`` names fields the *existing* entry always wins on —
        ``created`` being the whole point: it records when the entry first
        appeared and must survive every later write.

        Returns the stored entry, so a caller can go on adjusting it.
        """
        entry_id = entry.get("id")
        existing = self.find(entry_id) if entry_id is not None else None
        if existing is None:
            self.entries.append(entry)
            return entry

        stored = {**existing, **entry} if merge else dict(entry)
        for key in preserve:
            if key in existing:
                stored[key] = existing[key]
        self.entries[self.entries.index(existing)] = stored
        return stored

    def remove(self, entry_id: str) -> bool:
        """Drop the entry with this id. True when there was one."""
        existing = self.find(entry_id)
        if existing is None:
            return False
        self.entries.remove(existing)
        return True

    # -- ordering ---------------------------------------------------------

    def sort_by_name(self) -> None:
        """Alphabetical by display name, how the person registries are kept."""
        self.entries.sort(key=lambda item: (item or {}).get("name", ""))

    def sort_like(self, order: Iterable[str]) -> None:
        """Reorder to match a reference list of ids.

        The language registries are kept in the English registry's order so
        the two can be read side by side. An id the reference does not know
        sorts to the end rather than to the front, so a locally added entry
        never displaces the aligned ones.
        """
        positions = {entry_id: index for index, entry_id in enumerate(order)}
        self.entries.sort(
            key=lambda item: positions.get(str((item or {}).get("id")), len(positions))
        )

    # -- persisting -------------------------------------------------------

    def save(self) -> None:
        """Write the document in the repository's canonical JSON format."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        write_json(self.path, self.document)
