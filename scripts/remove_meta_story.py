#!/usr/bin/env python3
"""Remove a meta-story from the Life Data Stories dataset.

Removal cascades through every registry and translated copy, not just the
English detail file and registry entry:

- the English registry (``data/meta_stories.json``)
- every localized registry (``data/meta_stories_{lang}.json``)
- the English detail file (``data/meta_stories/{id}.json``)
- every translated detail file (``data/meta_stories/{lang}/{id}.json`` — not
  ``data/meta_stories/{id}/``, which is not how translations are stored)

Registries are written before any files are deleted, so a mid-operation
failure leaves the data files intact (recoverable) rather than silently
half-removed.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
META_STORIES_REGISTER = DATA_DIR / "meta_stories.json"
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


def _find_registries() -> List[Path]:
    registries = [META_STORIES_REGISTER] if META_STORIES_REGISTER.exists() else []
    registries += sorted(
        p
        for p in DATA_DIR.glob("meta_stories_*.json")
        if p.is_file() and p != META_STORIES_REGISTER
    )
    return registries


def _find_detail_files(story_id: str) -> List[Path]:
    """The English detail file plus every language's translated copy.

    Translations live at ``data/meta_stories/{lang}/{story_id}.json`` — a
    language subdirectory containing one file per story — not at
    ``data/meta_stories/{story_id}/``.
    """
    files = []
    english = META_STORIES_DIR / f"{story_id}.json"
    if english.exists():
        files.append(english)
    if META_STORIES_DIR.exists():
        for lang_dir in sorted(META_STORIES_DIR.iterdir()):
            if not lang_dir.is_dir():
                continue
            translated = lang_dir / f"{story_id}.json"
            if translated.exists():
                files.append(translated)
    return files


def remove_meta_story(story_id: str, *, dry_run: bool = False) -> bool:
    """Remove a meta-story from the dataset.

    Args:
        story_id: The ID of the meta-story to remove
        dry_run: If True, only print what would be done without making changes

    Returns:
        True if successful, False otherwise
    """
    if not META_STORIES_REGISTER.exists():
        print(
            f"Error: Register file not found at {META_STORIES_REGISTER}",
            file=sys.stderr,
        )
        return False

    register = _load_json(META_STORIES_REGISTER)
    if register is None:
        print(
            f"Error: Failed to read register file {META_STORIES_REGISTER}",
            file=sys.stderr,
        )
        return False

    meta_stories = register.get("meta_stories", [])
    story_entry = next((e for e in meta_stories if e.get("id") == story_id), None)
    if story_entry is None:
        print(
            f"Error: Meta-story with ID '{story_id}' not found in register",
            file=sys.stderr,
        )
        return False

    print(f"Found meta-story: {story_entry.get('title', story_id)}")
    print(f"  Tagline: {story_entry.get('tagline', 'N/A')}")
    print(f"  People: {story_entry.get('person_count', 0)}")

    registries = _find_registries()
    registry_entries: Dict[Path, dict] = {}
    for path in registries:
        reg = _load_json(path)
        if reg is None:
            continue
        entry = next(
            (e for e in reg.get("meta_stories", []) if e.get("id") == story_id), None
        )
        if entry is not None:
            registry_entries[path] = reg

    detail_files = _find_detail_files(story_id)

    print(f"\nRegistries referencing '{story_id}':")
    for path in registries:
        marker = "yes" if path in registry_entries else "no"
        print(f"  - {path.relative_to(DATA_DIR)}: {marker}")

    print(f"\nDetail files to delete: {len(detail_files)}")
    for f in detail_files:
        print(f"  - {f.relative_to(DATA_DIR)}")

    if not detail_files:
        print(f"Warning: No detail files found for meta-story '{story_id}'")

    if dry_run:
        print("\n--- DRY RUN MODE ---")
        print("No changes made. Run without --dry-run to apply changes.")
        return True

    # --- Apply: registries first, then files ---------------------------------

    print(f"\nRemoving '{story_id}' from registries...")
    for path, reg in registry_entries.items():
        reg["meta_stories"] = [
            e for e in reg.get("meta_stories", []) if e.get("id") != story_id
        ]
        try:
            _save_json(path, reg)
            print(f"  Updated {path.relative_to(DATA_DIR)}")
        except Exception as error:
            print(f"Error: Failed to write {path}: {error}", file=sys.stderr)
            return False

    for f in detail_files:
        try:
            f.unlink()
            print(f"Deleted {f.relative_to(DATA_DIR)}")
        except Exception as error:
            print(f"Error: Failed to delete {f}: {error}", file=sys.stderr)
            return False

    print(f"\nSUCCESS: Removed meta-story '{story_id}'")
    return True


def list_meta_stories() -> None:
    """List all meta-stories in the register."""
    if not META_STORIES_REGISTER.exists():
        print(
            f"Error: Register file not found at {META_STORIES_REGISTER}",
            file=sys.stderr,
        )
        return

    register = _load_json(META_STORIES_REGISTER)
    if register is None:
        print(
            f"Error: Failed to read register file {META_STORIES_REGISTER}",
            file=sys.stderr,
        )
        return

    meta_stories = register.get("meta_stories", [])

    if not meta_stories:
        print("No meta-stories found in register.")
        return

    print(f"Found {len(meta_stories)} meta-story(ies) in register:\n")
    for story in meta_stories:
        story_id = story.get("id", "unknown")
        title = story.get("title", "Unknown")
        tagline = story.get("tagline", "")
        person_count = story.get("person_count", 0)
        print(f"  {story_id:30} - {title}")
        if tagline:
            print(f"  {' ' * 30}   \"{tagline}\"")
        print(f"  {' ' * 30}   {person_count} people")
        print()


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Remove a meta-story from the Life Data Stories dataset."
    )
    parser.add_argument(
        "story_id",
        nargs="?",
        help="ID of the meta-story to remove (e.g., 'computing_pioneers'). Use --list to see all IDs.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without making changes",
    )
    parser.add_argument(
        "--list", action="store_true", help="List all meta-stories in the register"
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    if args.list:
        list_meta_stories()
        return 0

    if not args.story_id:
        print(
            "Error: story_id is required. Use --list to see available IDs.",
            file=sys.stderr,
        )
        return 1

    success = remove_meta_story(args.story_id, dry_run=args.dry_run)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
