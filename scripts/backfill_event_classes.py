#!/usr/bin/env python3
"""Backfill the ``event_class`` block onto events that should carry one.

Phase 1 of ``generate_person_events.py`` classifies as it proposes, but a
dataset written before a class existed — or one where the call simply passed an
event over — carries none, and the interface then shows a landmark publication
as an ordinary event: no panel, no title of the work, no link to it. Turing's
two famous papers were both unclassified.

Only the four kinds that describe something a life did are handled here.
``birth`` and ``death`` are the two boundaries, exactly one of each per life,
and they have backfills of their own that know that rule.

One call per person rather than per event, because two of the rules are about
the life as a whole: the same work must not be classified twice, and a class is
only worth applying where the event really is one of these kinds. The rubric is
Phase 1's own, imported rather than restated, so the two cannot drift.

Usage:
    python scripts/backfill_event_classes.py alan_turing
    python scripts/backfill_event_classes.py                  # every person
    python scripts/backfill_event_classes.py --dry-run
"""

from __future__ import annotations

import argparse
import os
import re
from typing import Any, Dict, List, Optional, cast

from openai import OpenAI
from pydantic import BaseModel, Field

from config import (
    DEFAULT_MODEL,
    DEFAULT_REASONING_EFFORT,
    PEOPLE_DIR,
    enable_utf8_console,
)
from generate_person_events import (
    EVENT_CLASS_CONFIG,
    InventionClassification,
    MarriagePartnershipClassification,
    MigrationClassification,
    PublicationClassification,
)
from utils.datasets import person_ids
from utils.json_io import read_json, write_json
from utils.model_calls import parse_structured

enable_utf8_console()

_MARKER = re.compile(r"\[\[[^\[\]|]+\|([^\[\]]+)\]\]")

# The boundaries are not ours: one birth and one death per life, each with a
# dedicated backfill that enforces it.
CLASSES = ("publication", "invention", "marriage_partnership", "migration")

SYSTEM = (
    "You are a meticulous biographer classifying life events against a fixed "
    "rubric. You classify only what clearly matches, and you leave everything "
    "else alone: a wrong classification puts a panel of invented detail on a "
    "slide, which is worse than no panel at all."
)


class ClassifiedEvent(BaseModel):
    """One event the call decided to classify."""

    index: int = Field(description="The event's position in the list, as given")
    publication: Optional[PublicationClassification] = None
    invention: Optional[InventionClassification] = None
    marriage_partnership: Optional[MarriagePartnershipClassification] = None
    migration: Optional[MigrationClassification] = None


class Classifications(BaseModel):
    events: List[ClassifiedEvent] = Field(
        description="Only the events that clearly match one of the four kinds"
    )


def build_prompt(person_name: str, events: List[Dict[str, Any]]) -> str:
    """The rubric Phase 1 uses, over the events that carry no block yet."""
    lines = [
        f"Classify the events of the life of {person_name}.",
        "",
        "Each event either matches one of these kinds exactly, or matches none:",
        "",
    ]
    for name in CLASSES:
        config = EVENT_CLASS_CONFIG[name]
        lines.append(config["phase1_guidance"])
        lines.append("")

    lines += [
        "RULES:",
        "- Return an entry ONLY for an event that clearly is one of these kinds.",
        "  Most events are not. Education, appointments, awards, honors, deaths of",
        "  others, moves that are not migrations: leave all of them out entirely.",
        "- An event that presents a written work — a paper, a book, an article, a",
        "  thesis — is a PUBLICATION even when its title does not contain the word",
        "  'published'. 'Completed X paper' and 'Presented Y to the society' are",
        "  publications; 'Began work on X' is not.",
        "- Fill only the one field matching the kind you chose, and leave the",
        "  other three null.",
        "- Every value must come from the event text or from what the sources",
        "  plainly state. Do not invent a publisher, a partner, or a date.",
        "- Use the index given here.",
        "",
        "=" * 60,
        "UNCLASSIFIED EVENTS:",
        "=" * 60,
        "",
    ]
    for event in events:
        description = _MARKER.sub(r"\1", event.get("description") or "")
        lines.append(
            f"[{event['_index']}] {event.get('date', '?')} — {event.get('title', '')}"
        )
        if description:
            lines.append(f"    {description}")
        lines.append("")
    return "\n".join(lines)


def _chosen(entry: ClassifiedEvent) -> Optional[Dict[str, Any]]:
    """The one block the call filled, as a plain dict."""
    for name in CLASSES:
        value = getattr(entry, name, None)
        if value is not None:
            return cast(Dict[str, Any], value.model_dump(exclude_none=True))
    return None


def backfill_person(
    person_id: str,
    client: Optional[OpenAI],
    *,
    dry_run: bool = False,
) -> int:
    path = PEOPLE_DIR / person_id / "life_events.json"
    data = read_json(path)
    events = data.get("events") or []

    pending = [
        {**event, "_index": index}
        for index, event in enumerate(events)
        if not (event.get("event_class") or {}).get("type")
    ]
    if not pending:
        print(f"  {person_id}: every event already classified or left alone")
        return 0

    if dry_run:
        print(f"  {person_id}: would offer {len(pending)} unclassified events")
        return 0

    assert client is not None
    person_name = (data.get("person") or {}).get("name") or person_id
    parsed = parse_structured(
        client,
        model=DEFAULT_MODEL,
        reasoning_effort=DEFAULT_REASONING_EFFORT,
        input=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": build_prompt(person_name, pending)},
        ],
        text_format=Classifications,
        label=f"Classes for {person_id}",
    )
    if parsed is None:
        print(f"  {person_id}: not classified")
        return 0

    applied = 0
    for entry in parsed.events:
        if not 0 <= entry.index < len(events):
            continue
        event = events[entry.index]
        if (event.get("event_class") or {}).get("type"):
            continue
        block = _chosen(entry)
        if not block:
            continue
        event["event_class"] = block
        title = str(event.get("title", "")).encode("ascii", "replace").decode("ascii")
        print(f"    [{entry.index}] {block['type']}: {title}")
        applied += 1

    if applied:
        write_json(path, data)
        print(f"  {person_id}: classified {applied} event(s)")
    else:
        print(f"  {person_id}: nothing matched")
    return applied


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill event_class blocks onto unclassified events."
    )
    parser.add_argument("person_ids", nargs="*", help="Person IDs (default: all)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Say what would be offered, call nothing.",
    )
    args = parser.parse_args()

    client = None
    if not args.dry_run:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("OPENAI_API_KEY is not set.")
            return 1
        client = OpenAI(api_key=api_key)

    total = 0
    for person_id in args.person_ids or person_ids():
        if not (PEOPLE_DIR / person_id / "life_events.json").exists():
            print(f"  {person_id}: no dataset, skipping")
            continue
        total += backfill_person(person_id, client, dry_run=args.dry_run)

    print(f"\nClassified {total} event(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
