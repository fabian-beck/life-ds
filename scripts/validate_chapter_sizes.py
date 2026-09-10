#!/usr/bin/env python3
"""Check that every chapter of a life holds at least two events.

A chapter slide announces a phase of the life, and the event slides after it
tell that phase. A chapter with one event announces the event and then tells
it once more on the next slide, with the same year and the same place on both;
the Turing dataset opened "Across the Atlantic" on his Princeton doctorate
alone. A chapter with no event never renders at all, because the interface
inserts a chapter slide only where an event names it, so the reader loses the
chapter and its illustration without a trace.

The proposal in ``scripts/events/pipeline.py`` now refuses such a plan
(``MIN_CHAPTER_EVENTS``), so this reads the corpus for the datasets written
before that floor. It reports and never edits: a finding names a dataset for
``data/outdated.md``, and ``--check`` turns it into a gate once the count
reads zero.

Usage:
    python scripts/validate_chapter_sizes.py            # report
    python scripts/validate_chapter_sizes.py --check    # exit 1 on any finding
    python scripts/validate_chapter_sizes.py alan_turing
"""

from __future__ import annotations

import sys
from collections import Counter
from typing import Any, Dict, List

from events.pipeline import MIN_CHAPTER_EVENTS
from utils.validation import run_dataset_check


class SizeFinding:
    def __init__(self, person_id: str, chapter_id: str, count: int):
        self.person_id = person_id
        self.chapter_id = chapter_id
        self.count = count

    def __str__(self) -> str:
        if self.count == 0:
            held = "no event"
        elif self.count == 1:
            held = "a single event"
        else:
            held = f"{self.count} events"
        return (
            f"{self.person_id}: chapter '{self.chapter_id}' holds {held}, "
            f"fewer than {MIN_CHAPTER_EVENTS}"
        )


def check_person(person_id: str, data: Dict[str, Any]) -> List[SizeFinding]:
    """One finding per chapter below the floor, in the chapters' own order."""
    chapters = data.get("chapters") or []
    events = data.get("events") or []
    counts = Counter(event.get("chapter") for event in events if event.get("chapter"))
    return [
        SizeFinding(person_id, chapter["id"], counts.get(chapter["id"], 0))
        for chapter in chapters
        if chapter.get("id") and counts.get(chapter["id"], 0) < MIN_CHAPTER_EVENTS
    ]


def main(argv: List[str] | None = None) -> int:
    return run_dataset_check(
        check_person, description=__doc__, argv=argv, report_only=True
    )


if __name__ == "__main__":
    sys.exit(main())
