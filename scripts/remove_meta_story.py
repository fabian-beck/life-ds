#!/usr/bin/env python3
"""Remove a meta-story from the Life Data Stories dataset."""

import argparse
import json
import shutil
import sys
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
META_STORIES_REGISTER = DATA_DIR / "meta_stories.json"
META_STORIES_DIR = DATA_DIR / "meta_stories"


def remove_meta_story(story_id: str, *, dry_run: bool = False) -> bool:
    """Remove a meta-story from the dataset.

    Args:
        story_id: The ID of the meta-story to remove
        dry_run: If True, only print what would be done without making changes

    Returns:
        True if successful, False otherwise
    """
    # Check if register exists
    if not META_STORIES_REGISTER.exists():
        print(f"Error: Register file not found at {META_STORIES_REGISTER}", file=sys.stderr)
        return False

    # Load register
    try:
        register = json.loads(META_STORIES_REGISTER.read_text(encoding="utf-8"))
    except Exception as error:
        print(f"Error: Failed to read register file: {error}", file=sys.stderr)
        return False

    meta_stories = register.get("meta_stories", [])

    # Find the meta-story in the register
    story_entry = None
    story_index = None
    for idx, entry in enumerate(meta_stories):
        if entry.get("id") == story_id:
            story_entry = entry
            story_index = idx
            break

    if story_entry is None:
        print(
            f"Error: Meta-story with ID '{story_id}' not found in register",
            file=sys.stderr,
        )
        return False

    print(f"Found meta-story: {story_entry.get('title', story_id)}")
    print(f"  Tagline: {story_entry.get('tagline', 'N/A')}")
    print(f"  People: {story_entry.get('person_count', 0)}")

    # Check for meta-story files
    story_file = META_STORIES_DIR / f"{story_id}.json"
    story_dir = META_STORIES_DIR / story_id  # For translations
    files_to_delete = []

    # Main story file
    if story_file.exists():
        files_to_delete.append(story_file)
        print(f"Found meta-story file: {story_file.relative_to(DATA_DIR)}")

    # Translation directory (if exists)
    if story_dir.exists() and story_dir.is_dir():
        for file_path in story_dir.rglob("*"):
            if file_path.is_file():
                files_to_delete.append(file_path)
        print(f"Found translation directory: {story_dir.relative_to(DATA_DIR)}")
        print(f"  Translation files: {len(list(story_dir.rglob('*')))} file(s)")

    if not files_to_delete:
        print(f"Warning: No files found for meta-story '{story_id}'")

    if dry_run:
        print("\n--- DRY RUN MODE ---")
        print("Would perform the following actions:")
        print(f"1. Remove entry from register: {story_entry}")
        if files_to_delete:
            print(f"2. Delete files:")
            for file_path in files_to_delete:
                print(f"   - {file_path.relative_to(DATA_DIR)}")
        if story_dir.exists():
            print(f"3. Delete directory: {story_dir.relative_to(DATA_DIR)}")
        print("\nNo changes made. Run without --dry-run to apply changes.")
        return True

    # Remove from register
    print(f"\nRemoving '{story_id}' from register...")
    meta_stories.pop(story_index)

    try:
        META_STORIES_REGISTER.write_text(
            json.dumps(register, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"Updated register at {META_STORIES_REGISTER.relative_to(DATA_DIR)}")
    except Exception as error:
        print(f"Error: Failed to write register file: {error}", file=sys.stderr)
        return False

    # Delete meta-story file
    if story_file.exists():
        try:
            story_file.unlink()
            print(f"Deleted file {story_file.relative_to(DATA_DIR)}")
        except Exception as error:
            print(f"Error: Failed to delete file: {error}", file=sys.stderr)
            return False

    # Delete translation directory
    if story_dir.exists() and story_dir.is_dir():
        try:
            shutil.rmtree(story_dir)
            print(f"Deleted directory {story_dir.relative_to(DATA_DIR)}")
        except Exception as error:
            print(f"Error: Failed to delete directory: {error}", file=sys.stderr)
            return False

    print(f"\nSUCCESS: Removed meta-story '{story_id}'")
    return True


def list_meta_stories() -> None:
    """List all meta-stories in the register."""
    if not META_STORIES_REGISTER.exists():
        print(f"Error: Register file not found at {META_STORIES_REGISTER}", file=sys.stderr)
        return

    try:
        register = json.loads(META_STORIES_REGISTER.read_text(encoding="utf-8"))
    except Exception as error:
        print(f"Error: Failed to read register file: {error}", file=sys.stderr)
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
