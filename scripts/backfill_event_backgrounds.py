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
    python scripts/backfill_event_backgrounds.py --images-only      # redo illustrations
    python scripts/backfill_event_backgrounds.py --headings-only    # divide the passages
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
from pydantic import BaseModel, Field, ValidationError

from config import (
    DEFAULT_MODEL,
    DEFAULT_REASONING_EFFORT,
    enable_utf8_console,
)
from utils.datasets import person_ids
from utils.json_io import read_json, write_json
from generate_person_events import (
    CLASSIFICATION_MODELS,
    PEOPLE_DIR,
    PHASE2_MODEL,
    PHASE2_REASONING_EFFORT,
    RELATED_ARTICLE_COUNT,
    EventSkeleton,
    build_background_avoidance,
    build_phase2_prompt_base,
    build_phase2_prompt_classified,
    filter_related_articles_for_event,
    illustrate_event,
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
            "A background report for this event, 350-550 words in 3-5 "
            "paragraphs separated by blank lines: the situation it sat in, the "
            "concrete specifics, a scene or episode told at length, and what "
            "came of it. One or two '## Section heading' lines may divide it "
            "where it turns to a different thing, never above the first "
            "paragraph. Prose for a reader, not a list. Null when the sources "
            "give nothing beyond the description."
        ),
    )
    sources: List[str] = Field(
        default_factory=list,
        description=(
            "1-3 Wikipedia URLs that document THIS event. The subject's own "
            "article when no related article covers it specifically."
        ),
    )
    background_image_queries: List[str] = Field(
        default_factory=list,
        description=(
            "3-4 Wikimedia Commons search queries, each for a DIFFERENT thing "
            "the background report names — the machine, the building, the "
            "document, the place. Not portraits of the subject."
        ),
    )


SYSTEM = (
    "You are a research assistant specializing in biographical event details. "
    "You are writing one field: a short passage of background, in prose, for a "
    "reader who has just read the event's own description and wants to know "
    "what surrounded it. It must add to that description rather than restate "
    "it. All output must be in American English only."
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
    """The parts of a stored event Phase 2's prompt builders read.

    The classification comes along. It used to be dropped here, which quietly
    made every event look unclassified to the prompt: a publication was
    researched as though the interface were not already showing its title,
    publisher and impact in a panel of their own, and the report was free to
    repeat them. A background has to work for every kind of event, and knowing
    which kind it is is how.
    """
    return EventSkeleton(
        date=event.get("date", ""),
        date_precision=event.get("date_precision", "day"),
        date_end=event.get("date_end"),
        date_end_precision=event.get("date_end_precision"),
        date_note=event.get("date_note"),
        age=event.get("age"),
        title=event.get("title", ""),
        description=event.get("description", ""),
        event_class=_classification(event.get("event_class")),
    )


def _classification(raw: Any) -> Optional[Any]:
    """The stored classification as the model Phase 2 expects, or nothing."""
    if not isinstance(raw, dict) or not raw.get("type"):
        return None
    model = CLASSIFICATION_MODELS.get(raw["type"])
    if model is None:
        return None
    try:
        return model(**raw)
    except ValidationError:
        # A block the schema has since moved on from is not worth failing a
        # background over; the event is simply researched unclassified.
        return None


def _story_outline(events: List[Dict[str, Any]], index: int) -> List[str]:
    """Every other slide of this story, as the reader can swipe to them.

    The two either side come with their descriptions, because those are what a
    report is most likely to run straight into. The rest come as a line each,
    which is enough to mark the ground as taken: shown only its neighbours, the
    report for Turing's death spent half its length on the morphogenesis paper,
    two slides back and a landmark with a report of its own.
    """
    lines = []
    for position, event in enumerate(events):
        if position == index:
            continue
        entry = f"{event.get('date', '?')} — {event.get('title', '')}"
        if abs(position - index) == 1:
            description = _MARKER.sub(r"\1", event.get("description") or "")
            if description:
                entry += f": {description}"
        lines.append(entry)
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
    filtered = filter_related_articles_for_event(
        skeleton, related, max_articles=RELATED_ARTICLE_COUNT
    )
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
    # A classified event goes through the classified builder, exactly as the
    # pipeline routes it: the class-specific guidance is what tells the call
    # which fields the interface already presents in a panel of its own.
    builder = (
        build_phase2_prompt_classified
        if skeleton.event_class
        else build_phase2_prompt_base
    )
    return builder(
        skeleton,
        person_name,
        filtered,
        background_avoidance=build_background_avoidance(
            known_annotations=known,
            story_outline=_story_outline(events, index),
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
    images_only: bool = False,
    headings_only: bool = False,
) -> int:
    """Fill the passage for one person. Returns how many events were written.

    ``images_only`` keeps the passages that are already on disk and redoes only
    their illustrations. The two halves fail differently — a report is good or
    thin, a Commons search is right or a steam engine — and tuning the picture
    critic by rewriting every report is both expensive and a way of never
    seeing whether the critic improved.

    ``headings_only`` divides passages already on disk, and touches nothing
    else. Phase 2 writes the headings itself now, but the reports written
    before it did are good reports, and rewriting them to gain a heading is a
    way of losing prose that has already been reviewed.
    """
    path = PEOPLE_DIR / person_id / "life_events.json"
    data = read_json(path)
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
        and _wanted_here(
            event,
            overwrite=overwrite,
            images_only=images_only,
            headings_only=headings_only,
        )
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

        if headings_only:
            passage = (event.get("background") or "").strip()
            divided = _with_headings(client, passage)
            if divided == passage:
                print("    left whole; it runs as one argument")
                continue
            event["background"] = divided
            written += 1
            continue

        if images_only:
            passage = (event.get("background") or "").strip()
            illustrate_event(client, event, passage, _image_queries(client, passage))
            written += 1
            continue

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
        passage = (parsed.background or "").strip() if parsed is not None else ""
        if parsed is None or not passage:
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

        illustrate_event(client, event, passage, parsed.background_image_queries)
        written += 1

    if written:
        write_json(path, data)
        print(f"  {person_id}: wrote {written} passage(s) to {path.name}")
        _propagate_sources(person_id, events)
    return written


def _wanted_here(
    event: Dict[str, Any],
    *,
    overwrite: bool,
    images_only: bool,
    headings_only: bool,
) -> bool:
    """Whether this event is one the requested pass has work to do on."""
    passage = (event.get("background") or "").strip()
    if headings_only:
        # A report that is already divided is left alone: the pass adds
        # headings to prose that has none, and asking it again would only
        # relabel what a reviewer has already seen.
        return bool(passage) and (overwrite or not _HEADING.search(passage))
    if images_only:
        return bool(passage)
    return overwrite or not passage


# A section heading in a report: its own line, opened by a Markdown ``##``.
# The report is otherwise plain prose, and this is the only markup in it.
_HEADING = re.compile(r"^##\s+\S", re.MULTILINE)


class ReportHeading(BaseModel):
    """One heading, and the paragraph it stands above."""

    before_paragraph: int = Field(
        description=(
            "The number of the paragraph this heading introduces, as numbered "
            "in the report below. Never 1: the reader has just arrived from "
            "the event and wants prose before a label."
        )
    )
    heading: str = Field(
        description=(
            "Two to five words naming what the paragraphs under it are about. "
            "The thing itself, never the part of the report it is."
        )
    )


class ReportHeadings(BaseModel):
    """Where a report already on disk divides, if it divides at all."""

    headings: List[ReportHeading] = Field(
        default_factory=list,
        description=(
            "One or two headings, in paragraph order. Empty when the report "
            "runs as a single argument."
        ),
    )


def _with_headings(client: OpenAI, report: str) -> str:
    """The report with section headings inserted, or exactly as it came.

    The prose is not touched. A heading is a line of its own between two
    paragraphs, so this pass can only add lines — which is the point: these
    reports were written and reviewed before the interface could show a
    heading, and rewriting a good report to gain one is a poor trade.
    """
    paragraphs = [
        block.strip() for block in re.split(r"\n\s*\n", report) if block.strip()
    ]
    if len(paragraphs) < 3:
        return report

    listing = "\n\n".join(
        f"[{number}] {paragraph}" for number, paragraph in enumerate(paragraphs, 1)
    )
    parsed = parse_structured(
        client,
        model=DEFAULT_MODEL,
        reasoning_effort=DEFAULT_REASONING_EFFORT,
        input=[
            {
                "role": "system",
                "content": (
                    "You divide a piece of written background into sections. "
                    "You add nothing and rewrite nothing: you say where it "
                    "turns, and what it turns to."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Give this report one or two section headings, so a reader "
                    "scrolling it can see its shape.\n\n"
                    "A heading goes above the paragraph where the report turns "
                    "to a genuinely different thing. Never above paragraph 1. "
                    "Never one per paragraph. If the report runs as a single "
                    "argument, return none — that is a normal answer, and a "
                    "heading over every paragraph is worse than no heading at "
                    "all.\n"
                    "Two to five words, in the report's own language, naming "
                    "the thing rather than the section:\n"
                    "- GOOD: 'The bombe on the floor', 'What Bletchley kept "
                    "quiet'\n"
                    "- BAD: 'Background', 'Aftermath', 'Introduction', "
                    "'The situation'\n\n"
                    f"REPORT:\n{listing}\n"
                ),
            },
        ],
        text_format=ReportHeadings,
        label="Headings for a background report",
    )
    if parsed is None or not parsed.headings:
        return report

    # At most one heading per paragraph, never above the first, and at most two
    # in a report this short — the model is asked for all three and the count
    # is held here, where a stray answer cannot reach the corpus.
    placed: Dict[int, str] = {}
    for heading in parsed.headings:
        text = " ".join(str(heading.heading or "").split()).strip("#").strip()
        position = heading.before_paragraph
        if not text or position < 2 or position > len(paragraphs):
            continue
        if position in placed or len(placed) >= 2:
            continue
        placed[position] = text
    if not placed:
        return report

    blocks: List[str] = []
    for number, paragraph in enumerate(paragraphs, 1):
        if number in placed:
            blocks.append(f"## {placed[number]}")
        blocks.append(paragraph)
    return "\n\n".join(blocks)


class ImageQueries(BaseModel):
    """Fresh Commons searches for a report already on disk."""

    queries: List[str] = Field(
        default_factory=list,
        description=(
            "3-4 Wikimedia Commons search queries, 2-5 words each, one per "
            "DIFFERENT thing the report names. Not portraits, not the subject."
        ),
    )


def _image_queries(client: OpenAI, report: str) -> List[str]:
    """What to search Commons for, read off a report that is already written."""
    parsed = parse_structured(
        client,
        model=DEFAULT_MODEL,
        reasoning_effort=DEFAULT_REASONING_EFFORT,
        input=[
            {
                "role": "system",
                "content": (
                    "You name the things a text describes, in the words a "
                    "photograph of them would be filed under."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Name 3-4 Wikimedia Commons searches for pictures that "
                    "would illustrate this report: the machine, the building, "
                    "the document, the instrument, the place it describes. "
                    "Each query names a DIFFERENT thing, from a different part "
                    "of the report. 2-5 words each. Name the thing, never a "
                    "person — a portrait illustrates nothing here. Only things "
                    "the report actually names.\n\n"
                    f"REPORT:\n{report}\n"
                ),
            },
        ],
        text_format=ImageQueries,
        label="Illustration searches for a background report",
    )
    return list(parsed.queries) if parsed else []


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
        payload = read_json(target)
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
            write_json(target, payload)
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
        "--images-only",
        action="store_true",
        help="Keep the passages on disk and redo only their illustrations.",
    )
    parser.add_argument(
        "--headings-only",
        action="store_true",
        help="Keep the passages on disk and only divide them with headings.",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Say what would be filled, call nothing."
    )
    args = parser.parse_args()

    selection: Dict[str, List[int]] = {}
    if args.selection:
        selection = json.loads(args.selection.read_text(encoding="utf-8"))

    ids = args.person_ids or (sorted(selection) if selection else person_ids())

    client = None
    if not args.dry_run:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("OPENAI_API_KEY is not set.")
            return 1
        client = OpenAI(api_key=api_key)

    total = 0
    for person_id in ids:
        if not (PEOPLE_DIR / person_id / "life_events.json").exists():
            print(f"  {person_id}: no dataset, skipping")
            continue
        total += backfill_person(
            person_id,
            client,
            wanted=selection.get(person_id) if selection else None,
            overwrite=args.overwrite,
            dry_run=args.dry_run,
            images_only=args.images_only,
            headings_only=args.headings_only,
        )

    print(f"\nWrote {total} passage(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
