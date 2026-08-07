#!/usr/bin/env python3
"""Backfill the ``weight`` of each event into existing life-event datasets.

New datasets get the weight from Phase 1 of ``generate_person_events.py``, which
proposes the events of a life and is therefore the one call that sees them all
at once. Weight is comparative — how much of *this* life an event turns on — so
it cannot be judged an event at a time, and this backfill keeps that property:
one call per person, shown the whole timeline, returning one number per event in
order.

The application used to derive the number instead, from the traces an important
event leaves behind: a classification, a picture, annotations, a long
description. That reads the documentation rather than the life, and it ranked
Turing's Princeton doctorate above the paper that founded computer science,
because the doctorate had more people attached to it. The weights are what
decides which events open a depth layer, so the misjudgment was visible.

Usage:
    python scripts/backfill_event_weights.py alan_turing
    python scripts/backfill_event_weights.py                  # every person
    python scripts/backfill_event_weights.py --dry-run
    python scripts/backfill_event_weights.py --overwrite      # re-weigh
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

from openai import OpenAI
from pydantic import BaseModel, Field

from config import DEFAULT_MODEL, DEFAULT_REASONING_EFFORT, enable_utf8_console
from generate_person_events import PEOPLE_DIR
from utils.model_calls import parse_structured

enable_utf8_console()

SYSTEM = (
    "You are a meticulous biographer. You judge how much of a life each of its "
    "events turns on, weighing the events of one life against each other rather "
    "than against history at large."
)

# The rubric Phase 1 is given, kept in one place so the backfill and the
# pipeline cannot come to mean different things by the same number.
RUBRIC = (
    "Give every event a weight from 0.0 to 1.0.\n"
    "- Judge each against the OTHER EVENTS OF THIS LIFE, not against history at "
    "large: the most consequential thing this person did is near 1.0 even if the "
    "world barely noticed, and a minor episode is near 0.1 even if it happened "
    "somewhere famous.\n"
    "- 0.9-1.0: the events the life is remembered for; without them the story is "
    "not this person's.\n"
    "- 0.6-0.8: turning points — the work, the appointment, the loss that changed "
    "the direction.\n"
    "- 0.3-0.5: substantial but not pivotal; a post taken, a degree earned, a "
    "move made.\n"
    "- 0.1-0.2: context and texture — real events that a short telling would "
    "leave out.\n"
    "- SPREAD THEM OUT. A life has a few peaks and many foothills, and a flat set "
    "of weights is the same as no weights at all.\n"
    "- Weigh what the event MEANT, not how well documented it is: a quiet "
    "decision that redirected the work outranks a well-attended ceremony that "
    "changed nothing.\n"
)


class EventWeight(BaseModel):
    index: int = Field(description="The event's position in the list, as given")
    weight: float = Field(description="0.0 to 1.0")


class Weights(BaseModel):
    weights: List[EventWeight] = Field(description="One entry per event, in order")


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


def _event_files(person_id: str) -> List[Path]:
    """The English life events file plus every translated copy.

    A weight is a number, not prose, so it is written to all of them: it decides
    which events open a depth layer, and a German reader arriving at different
    events than an English one would be reading a differently edited story.
    """
    files = []
    english = PEOPLE_DIR / person_id / "life_events.json"
    if english.exists():
        files.append(english)
    for lang_dir in sorted((PEOPLE_DIR / person_id).iterdir()):
        if lang_dir.is_dir() and not lang_dir.name.startswith("_"):
            translated = lang_dir / "life_events.json"
            if translated.exists():
                files.append(translated)
    return files


def build_prompt(person_name: str, events: List[Dict[str, Any]]) -> str:
    lines = [
        f"Weigh the events of the life of {person_name}.",
        "",
        RUBRIC,
        "",
        "Return one weight per event, using the index given here.",
        "",
        "=" * 60,
        "EVENTS:",
        "=" * 60,
        "",
    ]
    for index, event in enumerate(events):
        lines.append(f"[{index}] {event.get('date', '?')} — {event.get('title', '')}")
        description = (event.get("description") or "").strip()
        if description:
            lines.append(f"    {description}")
        lines.append("")
    return "\n".join(lines)


def backfill_person(
    person_id: str,
    client: Optional[OpenAI],
    *,
    overwrite: bool = False,
    dry_run: bool = False,
) -> int:
    path = PEOPLE_DIR / person_id / "life_events.json"
    data = _load(path)
    events = data.get("events") or []
    if not events:
        return 0

    already = sum(
        1 for event in events if isinstance(event.get("weight"), (int, float))
    )
    if already == len(events) and not overwrite:
        print(f"  {person_id}: already weighed")
        return 0

    if dry_run:
        print(f"  {person_id}: would weigh {len(events)} events")
        return 0

    assert client is not None
    person_name = (data.get("person") or {}).get("name") or person_id
    parsed = parse_structured(
        client,
        model=DEFAULT_MODEL,
        reasoning_effort=DEFAULT_REASONING_EFFORT,
        input=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": build_prompt(person_name, events)},
        ],
        text_format=Weights,
        label=f"Weights for {person_id}",
    )
    if parsed is None:
        print(f"  {person_id}: not weighed; the derived weight still stands in")
        return 0

    by_index = {entry.index: entry.weight for entry in parsed.weights}
    missing = [index for index in range(len(events)) if index not in by_index]
    if missing:
        # A partial answer would weigh some events and leave others to the
        # derived fallback, and the two scales are not the same scale. Better
        # to leave the whole life on one of them.
        print(f"  {person_id}: incomplete ({len(missing)} events unweighed), skipping")
        return 0

    weights = [
        round(min(max(by_index[index], 0.0), 1.0), 2) for index in range(len(events))
    ]

    for target in _event_files(person_id):
        payload = data if target == path else _load(target)
        target_events = payload.get("events") or []
        if len(target_events) != len(events):
            print(
                f"    [!] {target.parent.name}/{target.name}: different event count, skipped"
            )
            continue
        for event, weight in zip(target_events, weights):
            event["weight"] = weight
        _save(target, payload)

    spread = sorted(weights)
    print(
        f"  {person_id}: weighed {len(events)} events "
        f"({spread[0]:.2f}–{spread[-1]:.2f})"
    )
    return len(events)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill per-event weights into life-event datasets."
    )
    parser.add_argument("person_ids", nargs="*", help="Person IDs (default: all)")
    parser.add_argument(
        "--overwrite", action="store_true", help="Re-weigh lives already weighed."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Say what would be weighed, call nothing.",
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
    for person_id in args.person_ids or _person_ids():
        if not (PEOPLE_DIR / person_id / "life_events.json").exists():
            print(f"  {person_id}: no dataset, skipping")
            continue
        total += backfill_person(
            person_id, client, overwrite=args.overwrite, dry_run=args.dry_run
        )

    print(f"\nWeighed {total} event(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
