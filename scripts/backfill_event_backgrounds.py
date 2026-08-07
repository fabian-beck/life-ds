#!/usr/bin/env python3
"""Backfill the ``background`` passage into existing life-event datasets.

New datasets get the passage from Phase 2 of ``generate_person_events.py``,
which researches every event anyway. Datasets generated before the field
existed are filled here rather than regenerated: regeneration rewrites the
events themselves, and a corpus whose descriptions and chapters drift under a
purely additive change is a corpus nobody can review.

The passage is the one thing in the pipeline written for a reader rather than
extracted for a schema. The prompt is the pipeline's own — imported, not copied,
so the two cannot drift — and the material is the same material Phase 2 sees:
the event, the subject, and the cached related articles filtered down to the
ones about this event.

Only the events a story actually offers a depth layer for are worth the call,
and the application decides that in JavaScript. ``--selection`` takes the list
it computes, so the two agree; without one, every event is filled.

Usage:
    python scripts/backfill_event_backgrounds.py alan_turing
    python scripts/backfill_event_backgrounds.py                    # every person
    python scripts/backfill_event_backgrounds.py alan_turing --dry-run
    python scripts/backfill_event_backgrounds.py --selection deep_events.json
    python scripts/backfill_event_backgrounds.py --overwrite        # redo filled ones
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

from openai import OpenAI
from pydantic import BaseModel, Field

from config import enable_utf8_console
from generate_person_events import (
    PEOPLE_DIR,
    PHASE2_MODEL,
    PHASE2_REASONING_EFFORT,
    EventSkeleton,
    build_background_avoidance,
    build_phase2_prompt_base,
    filter_related_articles_for_event,
)
from utils.model_calls import parse_structured
from utils.wikipedia_cache import get_cache_dir

enable_utf8_console()

# ``[[term|display]]`` markers are an interface detail; a neighbouring event is
# shown to the model as the reader reads it.
_MARKER = re.compile(r"\[\[[^\[\]|]+\|([^\[\]]+)\]\]")


class BackgroundOnly(BaseModel):
    """Phase 2's background field, asked for on its own."""

    background: Optional[str] = Field(
        None,
        description=(
            "A short passage of background for this event: the situation it "
            "sat in, why it mattered, what followed from it. Prose, not a "
            "list. Null when the sources do not support one."
        ),
    )


SYSTEM = (
    "You are a research assistant specializing in biographical event details. "
    "You are writing one field: a short passage of background, in prose, for a "
    "reader who has just read the event's own description and wants to know "
    "what surrounded it. It must add to that description rather than restate "
    "it. All output must be in American English only."
)


def _load(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return cast(Dict[str, Any], json.load(f))


def _save(path: Path, data: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _person_ids() -> List[str]:
    return sorted(
        p.name for p in PEOPLE_DIR.iterdir() if (p / "life_events.json").exists()
    )


def _related_articles(person_id: str) -> List[Dict[str, Any]]:
    """The cached related articles, or none — the event alone still works."""
    try:
        path = get_cache_dir(person_id) / "related_articles.json"
    except Exception:  # noqa: BLE001 — an absent cache is a normal state here
        return []
    if not path.exists():
        return []
    try:
        return cast(List[Dict[str, Any]], json.loads(path.read_text(encoding="utf-8")))
    except json.JSONDecodeError:
        return []


def _skeleton(event: Dict[str, Any]) -> EventSkeleton:
    """The parts of a stored event Phase 2's prompt builders read."""
    return EventSkeleton(
        date=event.get("date", ""),
        date_precision=event.get("date_precision", "day"),
        date_end=event.get("date_end"),
        date_end_precision=event.get("date_end_precision"),
        date_note=event.get("date_note"),
        age=event.get("age"),
        title=event.get("title", ""),
        description=event.get("description", ""),
        event_class=None,
    )


def _neighbors(events: List[Dict[str, Any]], index: int) -> List[str]:
    """The events either side of this one, as the reader meets them."""
    lines = []
    for offset in (-1, 1):
        neighbor = events[index + offset] if 0 <= index + offset < len(events) else None
        if not neighbor:
            continue
        description = _MARKER.sub(r"\1", neighbor.get("description") or "")
        lines.append(
            f"{neighbor.get('date', '?')} — {neighbor.get('title', '')}: {description}"
        )
    return lines


def _prompt(
    event: Dict[str, Any],
    person_name: str,
    related: List[Dict[str, Any]],
    *,
    events: List[Dict[str, Any]],
    index: int,
    person_summary: Optional[str] = None,
) -> str:
    skeleton = _skeleton(event)
    filtered = filter_related_articles_for_event(skeleton, related, max_articles=5)
    known = {
        term: (annotation or {}).get("explanation", "")
        for term, annotation in (event.get("annotations") or {}).items()
        if (annotation or {}).get("explanation")
    }
    # The base prompt is the one that asks for the background; the class-specific
    # builder only adds guidance about fields this run does not fill.
    return build_phase2_prompt_base(
        skeleton,
        person_name,
        filtered,
        background_avoidance=build_background_avoidance(
            known_annotations=known,
            neighbors=_neighbors(events, index),
            person_summary=person_summary,
        ),
    )


def backfill_person(
    person_id: str,
    client: Optional[OpenAI],
    *,
    wanted: Optional[List[int]] = None,
    overwrite: bool = False,
    dry_run: bool = False,
) -> int:
    """Fill the passage for one person. Returns how many events were written."""
    path = PEOPLE_DIR / person_id / "life_events.json"
    data = _load(path)
    events = data.get("events") or []
    person = data.get("person") or {}
    person_name = person.get("name") or person_id
    person_summary = person.get("summary")
    related = _related_articles(person_id)

    targets = [
        index
        for index, event in enumerate(events)
        if (wanted is None or index in wanted)
        and (overwrite or not (event.get("background") or "").strip())
    ]
    if not targets:
        print(f"  {person_id}: nothing to fill")
        return 0

    if dry_run:
        for index in targets:
            print(f"  {person_id}[{index}] would fill: {events[index].get('title')}")
        return 0

    assert client is not None
    written = 0
    for index in targets:
        event = events[index]
        title = str(event.get("title", "")).encode("ascii", "replace").decode("ascii")
        print(f"  {person_id}[{index}] {title}")
        parsed = parse_structured(
            client,
            model=PHASE2_MODEL,
            reasoning_effort=PHASE2_REASONING_EFFORT,
            input=[
                {"role": "system", "content": SYSTEM},
                {
                    "role": "user",
                    "content": _prompt(
                        event,
                        person_name,
                        related,
                        events=events,
                        index=index,
                        person_summary=person_summary,
                    ),
                },
            ],
            text_format=BackgroundOnly,
            label=f"Background for '{title}'",
        )
        passage = (parsed.background or "").strip() if parsed else ""
        if not passage:
            print("    [!] no passage; leaving the event without one")
            continue
        event["background"] = passage
        written += 1

    if written:
        _save(path, data)
        print(f"  {person_id}: wrote {written} passage(s) to {path.name}")
    return written


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill the background passage into life-event datasets."
    )
    parser.add_argument("person_ids", nargs="*", help="Person IDs (default: all)")
    parser.add_argument(
        "--selection",
        type=Path,
        help=(
            "JSON mapping person_id to the event indexes to fill, as the "
            "application's own deep-event rule computes them."
        ),
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Rewrite passages that are already there.",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Say what would be filled, call nothing."
    )
    args = parser.parse_args()

    selection: Dict[str, List[int]] = {}
    if args.selection:
        selection = json.loads(args.selection.read_text(encoding="utf-8"))

    person_ids = args.person_ids or (sorted(selection) if selection else _person_ids())

    client = None
    if not args.dry_run:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("OPENAI_API_KEY is not set.")
            return 1
        client = OpenAI(api_key=api_key)

    total = 0
    for person_id in person_ids:
        if not (PEOPLE_DIR / person_id / "life_events.json").exists():
            print(f"  {person_id}: no dataset, skipping")
            continue
        total += backfill_person(
            person_id,
            client,
            wanted=selection.get(person_id) if selection else None,
            overwrite=args.overwrite,
            dry_run=args.dry_run,
        )

    print(f"\nWrote {total} passage(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
