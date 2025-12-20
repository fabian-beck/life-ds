#!/usr/bin/env python3
"""Remove a person from the Life Data Stories dataset."""

import argparse
import json
import shutil
import sys
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
REGISTER_PATH = DATA_DIR / "persons.json"
PEOPLE_DIR = DATA_DIR / "people"


def remove_person(person_id: str, *, dry_run: bool = False) -> bool:
    """Remove a person from the dataset.

    Args:
        person_id: The ID of the person to remove
        dry_run: If True, only print what would be done without making changes

    Returns:
        True if successful, False otherwise
    """
    # Check if register exists
    if not REGISTER_PATH.exists():
        print(f"Error: Register file not found at {REGISTER_PATH}", file=sys.stderr)
        return False

    # Load register
    try:
        register = json.loads(REGISTER_PATH.read_text(encoding="utf-8"))
    except Exception as error:
        print(f"Error: Failed to read register file: {error}", file=sys.stderr)
        return False

    people = register.get("people", [])

    # Find the person in the register
    person_entry = None
    person_index = None
    for idx, entry in enumerate(people):
        if entry.get("id") == person_id:
            person_entry = entry
            person_index = idx
            break

    if person_entry is None:
        print(
            f"Error: Person with ID '{person_id}' not found in register",
            file=sys.stderr,
        )
        return False

    print(f"Found person: {person_entry.get('name', person_id)}")

    # Check for person directory
    person_dir = PEOPLE_DIR / person_id
    files_to_delete = []

    if person_dir.exists():
        # List all files in the person directory
        for file_path in person_dir.rglob("*"):
            if file_path.is_file():
                files_to_delete.append(file_path)
        print(f"Found person directory: {person_dir}")
        print(f"  Files to delete: {len(files_to_delete)}")
        for file_path in files_to_delete:
            print(f"    - {file_path.relative_to(DATA_DIR)}")
    else:
        print(f"Warning: Person directory not found at {person_dir}")

    if dry_run:
        print("\n--- DRY RUN MODE ---")
        print("Would perform the following actions:")
        print(f"1. Remove entry from register: {person_entry}")
        if person_dir.exists():
            print(f"2. Delete directory: {person_dir}")
            print(f"   (including {len(files_to_delete)} file(s))")
        print("\nNo changes made. Run without --dry-run to apply changes.")
        return True

    # Remove from register
    print(f"\nRemoving '{person_id}' from register...")
    people.pop(person_index)

    try:
        REGISTER_PATH.write_text(
            json.dumps(register, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"✓ Updated register at {REGISTER_PATH}")
    except Exception as error:
        print(f"Error: Failed to write register file: {error}", file=sys.stderr)
        return False

    # Delete person directory
    if person_dir.exists():
        try:
            shutil.rmtree(person_dir)
            print(f"✓ Deleted directory {person_dir}")
        except Exception as error:
            print(f"Error: Failed to delete directory: {error}", file=sys.stderr)
            return False

    print(f"\n✓ Successfully removed person '{person_id}'")
    return True


def list_people() -> None:
    """List all people in the register."""
    if not REGISTER_PATH.exists():
        print(f"Error: Register file not found at {REGISTER_PATH}", file=sys.stderr)
        return

    try:
        register = json.loads(REGISTER_PATH.read_text(encoding="utf-8"))
    except Exception as error:
        print(f"Error: Failed to read register file: {error}", file=sys.stderr)
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
