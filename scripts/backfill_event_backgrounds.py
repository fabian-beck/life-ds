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
from urllib.parse import unquote

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
    """Phase 2's background field, asked for on its own — and its sources.

    The sources come along because the depth layer prints them under the
    passage, which is the first time in this application that an event's own
    provenance is put in front of a reader: they used to be pooled on the
    conclusion slide, where a wrong one was invisible. Several are wrong. The
    prompt that produced them said "provide 1-3 Wikipedia URLs from the related
    articles below", so an event no related article documents got the closest
    one anyway — Morcom's death, in 1930, cited the article on Turing's 1936
    proof. Re-deciding them costs nothing here: the call is already looking at
    this event and at those same articles.
    """

    background: Optional[str] = Field(
        None,
        description=(
            "A short passage of background for this event: the situation it "
            "sat in, why it mattered, what followed from it. Prose, not a "
            "list. Null when the sources do not support one."
        ),
    )
    sources: List[str] = Field(
        default_factory=list,
        description=(
            "1-3 Wikipedia URLs that document THIS event. The subject's own "
            "article when no related article covers it specifically."
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


def _normalize(url: str) -> str:
    """Compare URLs the way Wikipedia treats them: percent-encoding and
    underscores are spelling, not identity."""
    return unquote(str(url or "")).replace("_", " ").rstrip("/").lower()


def _citable(
    person_wikipedia: Optional[str],
    related: List[Dict[str, Any]],
    existing: Optional[List[str]] = None,
) -> set:
    """Every URL this call is allowed to cite.

    The subject's article, the related articles it was shown, and whatever the
    event already cites — the last because a citation already in the corpus is a
    real article whether or not this event's article filter happened to surface
    it, and dropping a good one for being absent from a five-item shortlist is
    how "Published the Turing test paper" lost its citation of the paper.
    """
    urls = {_normalize(person_wikipedia)} if person_wikipedia else set()
    for article in related:
        url = article.get("url")
        if url:
            urls.add(_normalize(url))
    for url in existing or []:
        if url:
            urls.add(_normalize(url))
    urls.discard("")
    return urls


def _ego_network(person_id: str) -> Dict[str, Any]:
    """The network the chips are drawn from, or nothing."""
    path = PEOPLE_DIR / person_id / "ego_network.json"
    if not path.exists():
        return {}
    try:
        return cast(Dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    except json.JSONDecodeError:
        return {}


def _connections_for(
    event: Dict[str, Any], network: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """The network entries for the people this event names.

    Matched on the name as the event writes it, which is how the interface
    matches them too: a person the network does not know gets no chip, and so
    is not something the passage has to avoid introducing.
    """
    involved = {str(name).strip() for name in (event.get("involved_people") or [])}
    if not involved:
        return []
    return [
        connection
        for connection in (network.get("connections") or [])
        if str(connection.get("person_name", "")).strip() in involved
    ]


def _prompt(
    event: Dict[str, Any],
    person_name: str,
    related: List[Dict[str, Any]],
    *,
    events: List[Dict[str, Any]],
    index: int,
    person_summary: Optional[str] = None,
    network: Optional[Dict[str, Any]] = None,
) -> str:
    skeleton = _skeleton(event)
    network = network or {}
    filtered = filter_related_articles_for_event(skeleton, related, max_articles=5)
    cited = [url for url in (event.get("sources") or []) if url]
    known = {
        term: (annotation or {}).get("explanation", "")
        for term, annotation in (event.get("annotations") or {}).items()
        if (annotation or {}).get("explanation")
    }
    people = {
        connection.get("person_name", ""): connection.get(
            "relationship_description", ""
        )
        for connection in _connections_for(event, network)
        if connection.get("relationship_description")
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
            known_people=people,
            cited_sources=cited,
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
    person_wikipedia = person.get("wikipedia")
    related = _related_articles(person_id)
    network = _ego_network(person_id)

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
                        network=network,
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

        # Only URLs the call was actually shown. A model asked for a citation
        # will write a plausible one, and a plausible Wikipedia URL that 404s is
        # worse than the wrong-but-real article it replaces.
        allowed = _citable(person_wikipedia, related, event.get("sources"))
        chosen = [url for url in (parsed.sources or []) if _normalize(url) in allowed]
        if chosen and chosen != event.get("sources"):
            print(f"    sources: {event.get('sources')} -> {chosen}")
            event["sources"] = chosen
        written += 1

    if written:
        _save(path, data)
        print(f"  {person_id}: wrote {written} passage(s) to {path.name}")
        _propagate_sources(person_id, events)
    return written


def _propagate_sources(person_id: str, events: List[Dict[str, Any]]) -> None:
    """Carry corrected citations into the translated copies.

    A URL is not prose and is never translated, so a translated copy keeps
    whatever citation it was written with — which, for these events, is the
    wrong one. The passage itself is prose and waits for the translator.
    """
    for lang_dir in sorted((PEOPLE_DIR / person_id).iterdir()):
        if not lang_dir.is_dir() or lang_dir.name.startswith("_"):
            continue
        target = lang_dir / "life_events.json"
        if not target.exists():
            continue
        payload = _load(target)
        target_events = payload.get("events") or []
        if len(target_events) != len(events):
            print(f"    [!] {lang_dir.name}: different event count, sources not synced")
            continue
        changed = False
        for target_event, event in zip(target_events, events):
            if event.get("sources") and target_event.get("sources") != event["sources"]:
                target_event["sources"] = list(event["sources"])
                changed = True
        if changed:
            _save(target, payload)
            print(f"    sources synced to {lang_dir.name}")


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
