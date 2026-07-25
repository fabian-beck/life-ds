#!/usr/bin/env python3
"""Validate event-to-chapter assignments in life_events.json files.

StoryView.svelte sorts a person's events chronologically (by toTimestamp())
and inserts a chapter slide whenever the current event's chapter id differs
from the previous event's. That rendering assumes every chapter forms one
contiguous chronological block. An event whose `chapter` reference is missing,
outside the chapter's declared date range, or that breaks a chapter into two
separate runs violates that assumption and produces duplicated chapter slides
in the rendered story.

This script checks every data/people/*/life_events.json file (the English
reference data) for:

  - event `chapter` values that don't match any declared chapter id
  - events whose date falls outside their chapter's [date_start, date_end]
    range, using date precision (year/month/day) the same way the app does
  - chapters that would render as more than one contiguous run once events
    are sorted the way StoryView.svelte sorts them

Usage:
    python scripts/validate_event_chapters.py
    python scripts/validate_event_chapters.py alan_turing
    python scripts/validate_event_chapters.py --verbose
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from itertools import groupby
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
PEOPLE_DIR = DATA_DIR / "people"


class ValidationError:
    def __init__(self, person_id: str, message: str):
        self.person_id = person_id
        self.message = message

    def __str__(self) -> str:
        return f"{self.person_id}: {self.message}"


def _period_bounds(date_str: str, precision: str) -> Tuple[datetime, datetime]:
    """Return (inclusive start, exclusive end) instants covered by a date+precision."""
    parts = date_str.split("-")
    year = int(parts[0])
    if precision == "year":
        start = datetime(year, 1, 1)
        end = datetime(year + 1, 1, 1)
    elif precision == "month":
        month = int(parts[1])
        start = datetime(year, month, 1)
        end = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
    else:  # day
        month = int(parts[1])
        day = int(parts[2])
        start = datetime(year, month, day)
        end = start + timedelta(days=1)
    return start, end


def _event_timestamp(date_str: Optional[str], precision: Optional[str]) -> Optional[datetime]:
    """Mirror toTimestamp() in src/utils/storyHelpers.js: start of the date's period."""
    if not date_str:
        return None
    start, _ = _period_bounds(date_str, precision or "day")
    return start


def _chapter_range(chapter: Dict[str, Any]) -> Optional[Tuple[datetime, datetime]]:
    date_start = chapter.get("date_start")
    date_end = chapter.get("date_end")
    if not date_start or not date_end:
        return None
    start, _ = _period_bounds(date_start, chapter.get("date_start_precision") or "year")
    _, end_exclusive = _period_bounds(date_end, chapter.get("date_end_precision") or "year")
    return start, end_exclusive


def validate_person(person_id: str, data: Dict[str, Any]) -> List[ValidationError]:
    errors: List[ValidationError] = []
    chapters = data.get("chapters") or []
    events = data.get("events") or []
    chapters_by_id = {c.get("id"): c for c in chapters if c.get("id")}

    for index, event in enumerate(events):
        chapter_id = event.get("chapter")
        if not chapter_id:
            continue

        label = f"event {index} ({event.get('date', '?')} \"{event.get('title', '?')}\")"

        chapter = chapters_by_id.get(chapter_id)
        if chapter is None:
            errors.append(
                ValidationError(
                    person_id, f"{label} references nonexistent chapter id '{chapter_id}'"
                )
            )
            continue

        event_ts = _event_timestamp(event.get("date"), event.get("date_precision"))
        chapter_range = _chapter_range(chapter)
        if event_ts is not None and chapter_range is not None:
            start, end_exclusive = chapter_range
            if not (start <= event_ts < end_exclusive):
                errors.append(
                    ValidationError(
                        person_id,
                        f"{label} is outside chapter '{chapter_id}' "
                        f"range [{chapter.get('date_start')}, {chapter.get('date_end')}]",
                    )
                )

    # Contiguity: simulate the same chronological sort StoryView.svelte applies,
    # then check no chapter id forms more than one run.
    def sort_key(event: Dict[str, Any]) -> datetime:
        ts = _event_timestamp(event.get("date"), event.get("date_precision"))
        return ts if ts is not None else datetime.max

    sorted_events = sorted(events, key=sort_key)
    chapter_sequence = [e.get("chapter") for e in sorted_events if e.get("chapter")]
    runs_by_chapter: Dict[str, int] = {}
    for chapter_id, _ in groupby(chapter_sequence):
        runs_by_chapter[chapter_id] = runs_by_chapter.get(chapter_id, 0) + 1
    for chapter_id, run_count in runs_by_chapter.items():
        if run_count > 1:
            errors.append(
                ValidationError(
                    person_id,
                    f"chapter '{chapter_id}' is split into {run_count} non-contiguous "
                    "runs once events are sorted chronologically",
                )
            )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "person_ids", nargs="*", help="Specific person ids to check (default: all)"
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if args.person_ids:
        paths = [PEOPLE_DIR / person_id / "life_events.json" for person_id in args.person_ids]
    else:
        paths = sorted(PEOPLE_DIR.glob("*/life_events.json"))

    all_errors: List[ValidationError] = []
    checked = 0
    for path in paths:
        if not path.exists():
            print(f"warning: {path} not found", file=sys.stderr)
            continue
        person_id = path.parent.name
        data = json.loads(path.read_text(encoding="utf-8"))
        errors = validate_person(person_id, data)
        checked += 1
        if args.verbose and not errors:
            print(f"{person_id}: OK")
        all_errors.extend(errors)

    for error in all_errors:
        print(f"ERROR: {error}")

    print(f"\nChecked {checked} person dataset(s), {len(all_errors)} error(s) found.")
    return 1 if all_errors else 0


if __name__ == "__main__":
    sys.exit(main())
