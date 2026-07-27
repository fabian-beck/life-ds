#!/usr/bin/env python3
"""Remove a person from the Life Data Stories dataset.

Removal cascades through every place a person is referenced, not just the
English registry and person directory:

- localized person registries (``data/persons_{lang}.json``)
- ``data/person_styles.json``
- generated portrait assets (``public/portraits/{id}*``)
- every meta story (English and translated) that lists the person, via the
  same deterministic exclusion cascade the story composer uses
  (``person_ids``, subtopics, chapter events, the social network, the map)
- the meta story registries' ``person_count`` field

If removing the person would leave a meta story with no people left, the
whole operation is refused before anything is written — that story needs an
explicit decision (e.g. removing it too, via ``remove_meta_story.py``) rather
than being silently gutted.

Registries are written before any files are deleted, so a mid-operation
failure leaves the data files intact (recoverable) rather than silently
half-removed.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config import enable_utf8_console

enable_utf8_console()

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
PEOPLE_DIR = DATA_DIR / "people"
PORTRAITS_DIR = ROOT_DIR / "public" / "portraits"
REGISTER_PATH = DATA_DIR / "persons.json"
STYLES_PATH = DATA_DIR / "person_styles.json"
META_STORIES_DIR = DATA_DIR / "meta_stories"


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _save_json(path: Path, value: Dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _prune_narration_circles(dataset: Dict[str, Any], removed_id: str) -> None:
    """Drop a removed person from composed network circles' member_ids.

    Non-composed stories derive circles client-side from nodes/links (already
    pruned by the exclusion cascade), so nothing else is needed there; the
    UI's own key-mismatch fallback handles a now-stale cluster key gracefully.
    """
    narration = (dataset.get("social_network") or {}).get("narration")
    if not isinstance(narration, dict):
        return
    kept_circles = []
    for circle in narration.get("circles") or []:
        member_ids = circle.get("member_ids")
        if isinstance(member_ids, list):
            circle["member_ids"] = [m for m in member_ids if m != removed_id]
            if len(circle["member_ids"]) < 2:
                continue
        kept_circles.append(circle)
    narration["circles"] = kept_circles


def _find_meta_story_files(person_id: str) -> List[Tuple[Path, Dict[str, Any]]]:
    """Every meta story detail file (English + all translations) referencing person_id."""
    matches = []
    if not META_STORIES_DIR.exists():
        return matches
    paths = sorted(META_STORIES_DIR.glob("*.json")) + sorted(
        META_STORIES_DIR.glob("*/*.json")
    )
    for path in paths:
        detail = _load_json(path)
        if detail is None:
            continue
        person_ids = detail.get("meta_story", {}).get("person_ids") or []
        if person_id in person_ids:
            matches.append((path, detail))
    return matches


def _find_person_registries() -> List[Path]:
    return [REGISTER_PATH] + sorted(
        p for p in DATA_DIR.glob("persons_*.json") if p.is_file()
    )


def _find_meta_story_registries() -> List[Path]:
    path = DATA_DIR / "meta_stories.json"
    registries = [path] if path.exists() else []
    registries += sorted(
        p for p in DATA_DIR.glob("meta_stories_*.json") if p.is_file() and p != path
    )
    return registries


def _find_portrait_files(person_id: str) -> List[Path]:
    if not PORTRAITS_DIR.exists():
        return []
    return sorted(
        set(PORTRAITS_DIR.glob(f"{person_id}.*"))
        | set(PORTRAITS_DIR.glob(f"{person_id}_*"))
    )


def remove_person(person_id: str, *, dry_run: bool = False) -> bool:
    """Remove a person and cascade the removal through every reference.

    Args:
        person_id: The ID of the person to remove
        dry_run: If True, only print what would be done without making changes

    Returns:
        True if successful, False otherwise
    """
    if not REGISTER_PATH.exists():
        print(f"Error: Register file not found at {REGISTER_PATH}", file=sys.stderr)
        return False

    register = _load_json(REGISTER_PATH)
    if register is None:
        print(f"Error: Failed to read register file {REGISTER_PATH}", file=sys.stderr)
        return False

    people = register.get("people", [])
    person_entry = next((p for p in people if p.get("id") == person_id), None)
    if person_entry is None:
        print(
            f"Error: Person with ID '{person_id}' not found in register",
            file=sys.stderr,
        )
        return False

    print(f"Found person: {person_entry.get('name', person_id)}")

    # --- Discover everything referencing this person ------------------------

    person_registries = _find_person_registries()
    person_registry_entries: Dict[Path, dict] = {}
    for path in person_registries:
        reg = _load_json(path)
        if reg is None:
            continue
        entry = next(
            (p for p in reg.get("people", []) if p.get("id") == person_id), None
        )
        if entry is not None:
            person_registry_entries[path] = reg

    styles = _load_json(STYLES_PATH)
    has_style_entry = bool(styles and person_id in (styles.get("styles") or {}))

    person_dir = PEOPLE_DIR / person_id
    person_files = (
        [f for f in person_dir.rglob("*") if f.is_file()] if person_dir.exists() else []
    )

    portrait_files = _find_portrait_files(person_id)

    meta_story_matches = _find_meta_story_files(person_id)
    meta_registries = _find_meta_story_registries()

    # --- Guardrail: never silently empty a meta story ------------------------

    # Only English detail files determine cast size (translations mirror the
    # same person_ids set verbatim), so check those specifically.
    would_empty = []
    for path, detail in meta_story_matches:
        if path.parent != META_STORIES_DIR:
            continue  # translated copy; the English file already covers this
        remaining = [
            pid
            for pid in detail.get("meta_story", {}).get("person_ids", [])
            if pid != person_id
        ]
        if not remaining:
            would_empty.append(path.stem)

    if would_empty:
        print(
            "Error: removing "
            f"'{person_id}' would leave the following meta stor"
            f"{'y' if len(would_empty) == 1 else 'ies'} with no people left: "
            f"{', '.join(would_empty)}",
            file=sys.stderr,
        )
        print(
            "Remove or update those meta stories first (e.g. with "
            "remove_meta_story.py) before removing this person.",
            file=sys.stderr,
        )
        return False

    # --- Report -------------------------------------------------------------

    print(f"\nRegistries referencing '{person_id}':")
    for path in person_registries:
        marker = "yes" if path in person_registry_entries else "no"
        print(f"  - {path.relative_to(ROOT_DIR)}: {marker}")

    print(f"\nPerson style entry present: {'yes' if has_style_entry else 'no'}")

    if person_dir.exists():
        print(f"\nPerson directory: {person_dir.relative_to(ROOT_DIR)}")
        print(f"  Files to delete: {len(person_files)}")
        for f in person_files:
            print(f"    - {f.relative_to(DATA_DIR)}")
    else:
        print(f"\nWarning: Person directory not found at {person_dir}")

    print(f"\nPortrait assets: {len(portrait_files)}")
    for f in portrait_files:
        print(f"  - {f.relative_to(ROOT_DIR)}")

    print(f"\nMeta stories referencing '{person_id}': {len(meta_story_matches)}")
    for path, detail in meta_story_matches:
        remaining = len(
            [
                pid
                for pid in detail.get("meta_story", {}).get("person_ids", [])
                if pid != person_id
            ]
        )
        print(
            f"  - {path.relative_to(DATA_DIR)} "
            f"({remaining} people remaining after removal)"
        )

    if dry_run:
        print("\n--- DRY RUN MODE ---")
        print("No changes made. Run without --dry-run to apply changes.")
        return True

    # --- Apply: registries first ---------------------------------------------

    print(f"\nRemoving '{person_id}' from person registries...")
    for path, reg in person_registry_entries.items():
        reg["people"] = [p for p in reg.get("people", []) if p.get("id") != person_id]
        try:
            _save_json(path, reg)
            print(f"  Updated {path.relative_to(ROOT_DIR)}")
        except Exception as error:
            print(f"Error: Failed to write {path}: {error}", file=sys.stderr)
            return False

    if has_style_entry:
        print("Removing style entry...")
        del styles["styles"][person_id]
        try:
            _save_json(STYLES_PATH, styles)
            print(f"  Updated {STYLES_PATH.relative_to(ROOT_DIR)}")
        except Exception as error:
            print(f"Error: Failed to write {STYLES_PATH}: {error}", file=sys.stderr)
            return False

    if meta_story_matches:
        print("Cascading removal through meta stories...")
        try:
            from compose_meta_story import remove_people_from_story
        except Exception as error:
            print(
                f"Error: Failed to load removal cascade logic: {error}",
                file=sys.stderr,
            )
            return False

        affected_story_ids = set()
        for path, detail in meta_story_matches:
            remove_people_from_story(detail, [person_id], verbose=False)
            _prune_narration_circles(detail, person_id)
            try:
                _save_json(path, detail)
                print(f"  Updated {path.relative_to(DATA_DIR)}")
            except Exception as error:
                print(f"Error: Failed to write {path}: {error}", file=sys.stderr)
                return False
            if path.parent == META_STORIES_DIR:
                affected_story_ids.add(path.stem)

        print("Updating meta story registries' person_count...")
        for reg_path in meta_registries:
            reg = _load_json(reg_path)
            if reg is None:
                continue
            changed = False
            for entry in reg.get("meta_stories", []) or []:
                if entry.get("id") in affected_story_ids:
                    entry["person_count"] = max(
                        int(entry.get("person_count", 1)) - 1, 0
                    )
                    changed = True
            if changed:
                try:
                    _save_json(reg_path, reg)
                    print(f"  Updated {reg_path.relative_to(ROOT_DIR)}")
                except Exception as error:
                    print(
                        f"Error: Failed to write {reg_path}: {error}",
                        file=sys.stderr,
                    )
                    return False
        print(
            "Note: re-run compose_meta_story.py on affected stories to refresh "
            "prose/narration mentioning the removed person."
        )

    # --- Apply: deletions -----------------------------------------------------

    if person_dir.exists():
        try:
            shutil.rmtree(person_dir)
            print(f"Deleted directory {person_dir.relative_to(ROOT_DIR)}")
        except Exception as error:
            print(f"Error: Failed to delete directory: {error}", file=sys.stderr)
            return False

    for f in portrait_files:
        try:
            f.unlink()
            print(f"Deleted {f.relative_to(ROOT_DIR)}")
        except Exception as error:
            print(f"Error: Failed to delete {f}: {error}", file=sys.stderr)
            return False

    print(f"\nSuccessfully removed person '{person_id}'")
    return True


def list_people() -> None:
    """List all people in the register."""
    if not REGISTER_PATH.exists():
        print(f"Error: Register file not found at {REGISTER_PATH}", file=sys.stderr)
        return

    register = _load_json(REGISTER_PATH)
    if register is None:
        print(f"Error: Failed to read register file {REGISTER_PATH}", file=sys.stderr)
        return

    people = register.get("people", [])

    if not people:
        print("No people found in register.")
        return

    print(f"Found {len(people)} people in register:\n")
    for person in people:
        person_id = person.get("id", "unknown")
        name = person.get("name", "Unknown")
        print(f"  {person_id:30} - {name}")


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Remove a person from the Life Data Stories dataset."
    )
    parser.add_argument(
        "person_id",
        nargs="?",
        help="ID of the person to remove (e.g., 'ada_lovelace'). Use --list to see all IDs.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without making changes",
    )
    parser.add_argument(
        "--list", action="store_true", help="List all people in the register"
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    if args.list:
        list_people()
        return 0

    if not args.person_id:
        print(
            "Error: person_id is required. Use --list to see available IDs.",
            file=sys.stderr,
        )
        return 1

    success = remove_person(args.person_id, dry_run=args.dry_run)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
