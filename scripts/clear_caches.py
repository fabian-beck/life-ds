#!/usr/bin/env python3
"""Clear cached Wikipedia materials based on age or force clear all."""

import argparse
import re
import shutil
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional


# Data directory
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
PEOPLE_DIR = DATA_DIR / "people"


def parse_duration(duration_str: str) -> Optional[timedelta]:
    """
    Parse a duration string like '1h', '30m', '2d', '1w' into a timedelta.

    Supported units:
    - s, sec, seconds: seconds
    - m, min, minutes: minutes
    - h, hour, hours: hours
    - d, day, days: days
    - w, week, weeks: weeks

    Examples:
    - '1h' -> 1 hour
    - '30m' -> 30 minutes
    - '2d' -> 2 days
    - '1w' -> 1 week
    """
    if not duration_str:
        return None

    # Parse pattern like "30m", "1h", "2d", "1w"
    pattern = r'^(\d+(?:\.\d+)?)\s*([a-z]+)$'
    match = re.match(pattern, duration_str.strip().lower())

    if not match:
        raise ValueError(
            f"Invalid duration format: '{duration_str}'. "
            "Expected format like '1h', '30m', '2d', '1w'"
        )

    value = float(match.group(1))
    unit = match.group(2)

    # Map units to timedelta kwargs
    unit_map = {
        's': 'seconds',
        'sec': 'seconds',
        'second': 'seconds',
        'seconds': 'seconds',
        'm': 'minutes',
        'min': 'minutes',
        'minute': 'minutes',
        'minutes': 'minutes',
        'h': 'hours',
        'hr': 'hours',
        'hour': 'hours',
        'hours': 'hours',
        'd': 'days',
        'day': 'days',
        'days': 'days',
        'w': 'weeks',
        'wk': 'weeks',
        'week': 'weeks',
        'weeks': 'weeks',
    }

    if unit not in unit_map:
        raise ValueError(
            f"Unknown time unit: '{unit}'. "
            f"Supported units: {', '.join(sorted(set(unit_map.values())))}"
        )

    kwargs = {unit_map[unit]: value}
    return timedelta(**kwargs)


def get_cache_age(cache_dir: Path) -> Optional[timedelta]:
    """Get the age of a cache directory based on its newest file."""
    if not cache_dir.exists() or not cache_dir.is_dir():
        return None

    # Find the newest modification time among all files in cache
    newest_mtime = 0
    for file_path in cache_dir.rglob('*'):
        if file_path.is_file():
            mtime = file_path.stat().st_mtime
            if mtime > newest_mtime:
                newest_mtime = mtime

    if newest_mtime == 0:
        return None

    now = time.time()
    age_seconds = now - newest_mtime
    return timedelta(seconds=age_seconds)


def clear_cache(cache_dir: Path, person_id: str, dry_run: bool = False) -> bool:
    """Clear a single cache directory."""
    if not cache_dir.exists():
        return False

    if dry_run:
        print(f"  [DRY RUN] Would delete: {cache_dir}")
        return True

    try:
        shutil.rmtree(cache_dir)
        print(f"  Deleted cache: {person_id}")
        return True
    except Exception as error:
        print(f"  Error deleting {person_id}: {error}")
        return False


def clear_caches(
    max_age: Optional[str] = None,
    force: bool = False,
    person_ids: Optional[list[str]] = None,
    dry_run: bool = False,
    verbose: bool = False,
) -> int:
    """
    Clear cached Wikipedia materials.

    Args:
        max_age: Maximum age string (e.g., '1h', '2d'). Caches older than this will be deleted.
        force: If True, delete ALL caches regardless of age
        person_ids: Optional list of specific person IDs to clear
        dry_run: If True, show what would be deleted without actually deleting
        verbose: If True, show detailed information

    Returns:
        Number of caches cleared
    """
    if not PEOPLE_DIR.exists():
        print(f"Error: People directory not found: {PEOPLE_DIR}")
        return 0

    # Parse max_age if provided
    max_age_delta: Optional[timedelta] = None
    if max_age:
        try:
            max_age_delta = parse_duration(max_age)
            if verbose or dry_run:
                print(f"Max age: {max_age_delta}")
        except ValueError as error:
            print(f"Error: {error}")
            return 0

    # Determine mode
    if force:
        mode_desc = "ALL caches (forced)"
    elif max_age_delta:
        mode_desc = f"caches older than {max_age}"
    elif person_ids:
        mode_desc = f"{len(person_ids)} specific person(s)"
    else:
        print("Error: Must specify --force, --max-age, or provide person IDs")
        return 0

    if dry_run:
        print(f"[DRY RUN] Would clear: {mode_desc}")
    else:
        print(f"Clearing: {mode_desc}")

    cleared_count = 0
    skipped_count = 0

    # Iterate over all person directories
    for person_dir in sorted(PEOPLE_DIR.iterdir()):
        if not person_dir.is_dir():
            continue

        person_id = person_dir.name
        cache_dir = person_dir / "_cache"

        # Skip if cache doesn't exist
        if not cache_dir.exists():
            continue

        # Filter by person_ids if specified
        if person_ids and person_id not in person_ids:
            continue

        # Check age if max_age specified
        should_clear = False

        if force:
            should_clear = True
        elif person_ids and not max_age_delta:
            # If specific person IDs provided without max_age, clear them
            should_clear = True
        elif max_age_delta:
            cache_age = get_cache_age(cache_dir)
            if cache_age is None:
                if verbose:
                    print(f"  Skipped {person_id}: Could not determine age")
                skipped_count += 1
                continue

            if verbose:
                print(f"  {person_id}: age = {cache_age}")

            if cache_age > max_age_delta:
                should_clear = True

        if should_clear:
            if clear_cache(cache_dir, person_id, dry_run=dry_run):
                cleared_count += 1
        else:
            skipped_count += 1

    # Summary
    print()
    if dry_run:
        print(f"[DRY RUN] Would clear {cleared_count} cache(s)")
    else:
        print(f"Cleared {cleared_count} cache(s)")

    if verbose and skipped_count > 0:
        print(f"Skipped {skipped_count} cache(s)")

    return cleared_count


def parse_args(argv: Any) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Clear cached Wikipedia materials based on age or force clear all.",
        epilog="""
Examples:
  # Clear all caches older than 1 hour
  python clear_caches.py --max-age 1h

  # Clear all caches older than 2 days
  python clear_caches.py --max-age 2d

  # Clear all caches (force)
  python clear_caches.py --force

  # Clear specific person caches
  python clear_caches.py alan_turing ada_lovelace

  # Clear specific person caches only if older than 1 week
  python clear_caches.py --max-age 1w alan_turing

  # Dry run to see what would be deleted
  python clear_caches.py --max-age 1h --dry-run
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        'person_ids',
        nargs='*',
        help='Optional list of specific person IDs to clear (e.g., alan_turing ada_lovelace)'
    )

    parser.add_argument(
        '--max-age',
        help=(
            'Clear caches older than this duration. '
            'Format: <number><unit> where unit is s/m/h/d/w '
            '(e.g., "1h" = 1 hour, "2d" = 2 days, "1w" = 1 week)'
        )
    )

    parser.add_argument(
        '--force',
        action='store_true',
        help='Force clear ALL caches regardless of age'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be deleted without actually deleting'
    )

    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Show detailed information including cache ages'
    )

    return parser.parse_args(argv)


def main(argv: Any = None) -> int:
    """Main entry point."""
    args = parse_args(argv)

    try:
        cleared_count = clear_caches(
            max_age=args.max_age,
            force=args.force,
            person_ids=args.person_ids if args.person_ids else None,
            dry_run=args.dry_run,
            verbose=args.verbose,
        )
        return 0
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
