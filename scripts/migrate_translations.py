#!/usr/bin/env python3
"""Migrate legacy translation files onto the current English data structure.

Older translation runs produced files that were full AI rewrites of an earlier
English schema: they drifted structurally (different event counts, missing
event_type_icon / involved_people / annotations / conclusion, legacy flat
relationship types) and are not aligned with the current English reference.

This script rebases each legacy translated document onto a deep copy of the
CURRENT English document — deterministically, without any API calls:

- life events: English structure and technical data; the legacy translated
  title/description/caption texts are carried over where an event can be
  matched (by date, in order); everything unmatched stays English.
- ego network: English structure and connections; legacy translated
  relationship descriptions and notes are carried over where the connection's
  person matches; everything unmatched stays English.
- registry (persons_{lang}.json): rebuilt from the English registry structure
  with legacy translated summaries/roles/names carried over.

Migrated files get a ``translation`` provenance block WITHOUT a source
fingerprint, so ``translate_all_persons.py --check`` reports them as stale and
a later AI translation run replaces them with a full, current translation.
Files that already carry a translation block are left untouched.

Usage:
    python scripts/migrate_translations.py --lang de [--dry-run]
"""

import argparse
import copy
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

from translate_person import (
    DATA_DIR,
    PEOPLE_DIR,
    REGISTER_PATH,
    load_json_file,
    save_json_file,
)


def make_migration_block(target_lang: str) -> Dict[str, Any]:
    return {
        "source_lang": "en",
        "target_lang": target_lang,
        "source_fingerprint": None,
        "translated_on": datetime.now().astimezone().isoformat(),
        "translator": "migration",
        "note": (
            "Rebased from a legacy translation of an older English dataset; "
            "text may be outdated or partially English. Re-run translation to "
            "bring it fully up to date."
        ),
    }


def overlay_text(target: Dict[str, Any], key: str, value: Any) -> bool:
    """Copy a legacy translated text value onto the rebased document."""
    if key in target and isinstance(value, str) and value.strip():
        target[key] = value
        return True
    return False


def migrate_life_events(
    english: Dict[str, Any], legacy: Dict[str, Any], target_lang: str
) -> Dict[str, Any]:
    result = copy.deepcopy(english)

    # Person block: keep translated summary and roles
    person = result.get("person", {})
    legacy_person = legacy.get("person", {}) or {}
    overlay_text(person, "summary", legacy_person.get("summary"))
    legacy_roles = legacy_person.get("primary_roles")
    if "primary_roles" in person and isinstance(legacy_roles, list) and legacy_roles:
        person["primary_roles"] = legacy_roles
    overlay_text(person, "name", legacy_person.get("name"))

    # Chapters: match by id
    legacy_chapters = {
        chapter.get("id"): chapter for chapter in (legacy.get("chapters") or [])
    }
    for chapter in result.get("chapters") or []:
        legacy_chapter = legacy_chapters.get(chapter.get("id"))
        if legacy_chapter:
            overlay_text(chapter, "headline", legacy_chapter.get("headline"))

    # Events: match by date, consuming legacy events in order so repeated
    # dates pair up one-to-one
    legacy_by_date: Dict[str, List[Dict[str, Any]]] = {}
    for event in legacy.get("events") or []:
        legacy_by_date.setdefault(str(event.get("date")), []).append(event)

    matched = 0
    for event in result.get("events") or []:
        candidates = legacy_by_date.get(str(event.get("date")))
        if not candidates:
            continue
        legacy_event = candidates.pop(0)
        overlay_text(event, "title", legacy_event.get("title"))
        overlay_text(event, "description", legacy_event.get("description"))
        legacy_images = legacy_event.get("images") or []
        images = event.get("images") or []
        if len(images) == len(legacy_images):
            for img, legacy_img in zip(images, legacy_images):
                overlay_text(img, "caption", legacy_img.get("caption"))
        matched += 1

    result["translation"] = make_migration_block(target_lang)
    result["translation"]["matched_events"] = matched
    result["translation"]["total_events"] = len(result.get("events") or [])
    return result


def migrate_ego_network(
    english: Dict[str, Any], legacy: Dict[str, Any], target_lang: str
) -> Dict[str, Any]:
    result = copy.deepcopy(english)

    ego = result.get("ego", {})
    legacy_ego = legacy.get("ego", {}) or {}
    overlay_text(ego, "summary", legacy_ego.get("summary"))
    legacy_roles = legacy_ego.get("primary_roles")
    if "primary_roles" in ego and isinstance(legacy_roles, list) and legacy_roles:
        ego["primary_roles"] = legacy_roles

    legacy_connections = {
        str(conn.get("person_name", "")).strip().lower(): conn
        for conn in (legacy.get("connections") or [])
    }
    matched = 0
    for conn in result.get("connections") or []:
        key = str(conn.get("person_name", "")).strip().lower()
        legacy_conn = legacy_connections.get(key)
        if not legacy_conn:
            continue
        overlay_text(
            conn,
            "relationship_description",
            legacy_conn.get("relationship_description"),
        )
        overlay_text(conn, "notes", legacy_conn.get("notes"))
        matched += 1

    result["translation"] = make_migration_block(target_lang)
    result["translation"]["matched_connections"] = matched
    result["translation"]["total_connections"] = len(result.get("connections") or [])
    return result


def migrate_registry(target_lang: str, dry_run: bool) -> Optional[int]:
    """Rebuild persons_{lang}.json from the English registry structure."""
    registry_path = DATA_DIR / f"persons_{target_lang}.json"
    legacy_registry = load_json_file(registry_path)
    if legacy_registry is None:
        return None
    english_registry = load_json_file(REGISTER_PATH) or {}

    legacy_by_id = {
        entry.get("id"): entry
        for entry in legacy_registry.get("people", [])
        if isinstance(entry, dict)
    }

    migrated: List[Dict[str, Any]] = []
    count = 0
    for english_entry in english_registry.get("people", []):
        legacy_entry = legacy_by_id.get(english_entry.get("id"))
        if not legacy_entry:
            continue
        if "translation" in legacy_entry:
            migrated.append(legacy_entry)  # already new-style, keep as-is
            continue
        entry = copy.deepcopy(english_entry)
        overlay_text(entry, "summary", legacy_entry.get("summary"))
        overlay_text(entry, "name", legacy_entry.get("name"))
        legacy_roles = legacy_entry.get("primaryRoles")
        if isinstance(legacy_roles, list) and legacy_roles:
            entry["primaryRoles"] = legacy_roles
        entry["translation"] = make_migration_block(target_lang)
        migrated.append(entry)
        count += 1

    if count and not dry_run:
        save_json_file({"people": migrated}, registry_path)
    return count


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rebase legacy translations onto the current English structure"
    )
    parser.add_argument(
        "--lang", required=True, help="Language code of the translations (e.g., 'de')"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be migrated without writing files",
    )
    args = parser.parse_args()

    lang = args.lang
    migrated_any = False

    for person_dir in sorted(PEOPLE_DIR.iterdir()):
        if not person_dir.is_dir():
            continue
        lang_dir = person_dir / lang
        if not lang_dir.is_dir():
            continue
        person_id = person_dir.name

        for filename, migrate in (
            ("life_events.json", migrate_life_events),
            ("ego_network.json", migrate_ego_network),
        ):
            english = load_json_file(person_dir / filename)
            legacy = load_json_file(lang_dir / filename)
            if english is None or legacy is None:
                continue
            if isinstance(legacy.get("translation"), dict):
                print(f"→ {person_id}/{lang}/{filename}: already new-style, skipped")
                continue
            result = migrate(english, legacy, lang)
            stats = ", ".join(
                f"{k}={v}"
                for k, v in result["translation"].items()
                if k.startswith(("matched", "total"))
            )
            if args.dry_run:
                print(
                    f"[dry-run] would migrate {person_id}/{lang}/{filename} ({stats})"
                )
            else:
                save_json_file(result, lang_dir / filename)
                print(f"✓ Migrated {person_id}/{lang}/{filename} ({stats})")
            migrated_any = True

    registry_count = migrate_registry(lang, args.dry_run)
    if registry_count:
        action = "would migrate" if args.dry_run else "migrated"
        print(f"✓ Registry: {action} {registry_count} persons_{lang}.json entr(ies)")
        migrated_any = True

    if not migrated_any:
        print("Nothing to migrate.")
    else:
        print(
            "\nMigrated files are marked stale; run "
            f"'python scripts/translate_all_persons.py --target-lang {lang}' "
            "to complete the translations."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
