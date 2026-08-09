#!/usr/bin/env python3
"""Backfill the ``birth`` classification into existing life-event datasets.

New datasets get the classification from Phase 1 of ``generate_person_events.py``,
which reads the article and can name the parents itself. Datasets generated
before the classification existed are repaired here instead of being
regenerated: the birth event is detected deterministically (the same
``find_birth_event_index`` the generator uses) and the parents are read from the
person's ``ego_network.json``, so no AI call and no API key are involved.

``event_class`` is technical rather than prose — the translator never sees it —
so the same block is written to the English file and to every translated copy
under ``data/people/{person_id}/{lang}/``.

Usage:
    python scripts/backfill_birth_events.py                  # every person
    python scripts/backfill_birth_events.py niels_bohr
    python scripts/backfill_birth_events.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
from typing import Any, Dict, Optional

from config import DATA_DIR, PEOPLE_DIR, enable_utf8_console
from generate_person_events import find_birth_event_index
from utils.datasets import event_files, person_ids
from utils.json_io import read_json, write_json

enable_utf8_console()

# Prefixes and suffixes that qualify a family role without changing which
# generation it belongs to — mirrors normalizeFamilySubcategory() in the UI.
_ROLE_QUALIFIER = re.compile(r"^(step|half|adoptive|adopted|biological|foster)-?")

FATHER_ROLES = {"father"}
MOTHER_ROLES = {"mother"}

# Some ego networks record a parent whose name the sources do not give
# ("Unnamed mother of ..."). That is a placeholder, not a name, and a chip
# carrying it says less than no chip at all.
_PLACEHOLDER_NAME = re.compile(r"^\s*(unnamed|unknown|unidentified)\b", re.IGNORECASE)


def family_role(relationship_type: Optional[str]) -> Optional[str]:
    """Canonical family role of a connection, e.g. ``family/step-father`` -> ``father``."""
    if not relationship_type or "/" not in relationship_type:
        return None
    category, subcategory = relationship_type.split("/", 1)
    if category.lower() != "family":
        return None
    role = subcategory.lower().replace("_", "-").replace(" ", "-")
    role = re.sub(r"-by-marriage$", "", role)
    return _ROLE_QUALIFIER.sub("", role)


def parents_from_network(person_id: str) -> Dict[str, str]:
    """The documented parents of a person, read from their ego network."""
    network_path = PEOPLE_DIR / person_id / "ego_network.json"
    if not network_path.exists():
        return {}

    parents: Dict[str, str] = {}
    for connection in read_json(network_path).get("connections", []):
        role = family_role(connection.get("relationship_type"))
        name = connection.get("person_name")
        if not name or _PLACEHOLDER_NAME.match(name):
            continue
        if role in FATHER_ROLES and "father" not in parents:
            parents["father"] = name
        elif role in MOTHER_ROLES and "mother" not in parents:
            parents["mother"] = name
    return parents


def build_birth_class(
    existing: Optional[Dict[str, Any]], parents: Dict[str, str]
) -> Dict[str, Any]:
    """The birth classification to store, keeping whatever is already there.

    A regenerated dataset may already name a parent the ego network omits (or
    spell one more fully), so stored values win over the derived ones.
    """
    birth_class: Dict[str, Any] = {"type": "birth"}
    if isinstance(existing, dict) and existing.get("type") == "birth":
        birth_class.update({k: v for k, v in existing.items() if v is not None})
    for role, name in parents.items():
        birth_class.setdefault(role, name)
    return birth_class


def backfill_person(person_id: str, dry_run: bool) -> bool:
    """Classify one person's birth event. Returns True when something changed."""
    english_path = PEOPLE_DIR / person_id / "life_events.json"
    if not english_path.exists():
        print(f"  ⚠ Skipping unknown person: {person_id}")
        return False

    english = read_json(english_path)
    events = english.get("events") or []
    birth_date = (english.get("person") or {}).get("birth_date")
    index = find_birth_event_index(events, birth_date)
    if index is None:
        print(f"{person_id}: no birth event found — left unchanged")
        return False

    parents = parents_from_network(person_id)
    birth_class = build_birth_class(events[index].get("event_class"), parents)

    named = " & ".join(
        birth_class[role] for role in ("father", "mother") if birth_class.get(role)
    )
    print(
        f"{person_id}: event {index} '{events[index].get('title')}' "
        f"→ birth ({named or 'parents unknown'})"
    )

    changed = False
    for path in event_files(person_id):
        data = read_json(path)
        file_events = data.get("events") or []
        if len(file_events) != len(events):
            print(
                f"    ⚠ {path.relative_to(DATA_DIR)}: {len(file_events)} events, "
                f"English has {len(events)} — skipped, re-translate first"
            )
            continue

        before = json.dumps(
            [event.get("event_class") for event in file_events], sort_keys=True
        )
        for position, event in enumerate(file_events):
            if position == index:
                event["event_class"] = json.loads(json.dumps(birth_class))
            elif (event.get("event_class") or {}).get("type") == "birth":
                # A birth class on any other event is a misclassification —
                # the story has exactly one birth, the subject's own.
                event.pop("event_class")
        after = json.dumps(
            [event.get("event_class") for event in file_events], sort_keys=True
        )
        if before == after:
            print(f"    = {path.relative_to(DATA_DIR)} (already current)")
            continue

        changed = True
        if dry_run:
            print(f"    [dry-run] would update {path.relative_to(DATA_DIR)}")
        else:
            write_json(path, data)
            print(f"    ✓ {path.relative_to(DATA_DIR)}")

    return changed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill the birth classification into life event datasets"
    )
    parser.add_argument(
        "person_ids",
        nargs="*",
        help="Specific person IDs (default: all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without writing",
    )
    args = parser.parse_args()

    ids = args.person_ids or person_ids()
    updated = sum(backfill_person(person_id, args.dry_run) for person_id in ids)
    print(f"\n{updated} of {len(ids)} person(s) changed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
