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
    filter_images_by_quality,
    search_wikimedia_commons,
    PEOPLE_DIR,
    PHASE2_MODEL,
    PHASE2_REASONING_EFFORT,
    RELATED_ARTICLE_COUNT,
    EventSkeleton,
    build_background_avoidance,
    build_phase2_prompt_base,
    build_phase2_prompt_classified,
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
            "A background report for this event, 350-550 words in 3-5 "
            "paragraphs separated by blank lines: the situation it sat in, the "
            "concrete specifics, a scene or episode told at length, and what "
            "came of it. Prose for a reader, not a list. Null when the sources "
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
) -> int:
    """Fill the passage for one person. Returns how many events were written.

    ``images_only`` keeps the passages that are already on disk and redoes only
    their illustrations. The two halves fail differently — a report is good or
    thin, a Commons search is right or a steam engine — and tuning the picture
    critic by rewriting every report is both expensive and a way of never
    seeing whether the critic improved.
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
        and (
            (event.get("background") or "").strip()
            if images_only
            else (overwrite or not (event.get("background") or "").strip())
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

        if images_only:
            passage = (event.get("background") or "").strip()
            _illustrate(client, event, passage, _image_queries(client, passage))
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

        _illustrate(client, event, passage, parsed.background_image_queries)
        written += 1

    if written:
        write_json(path, data)
        print(f"  {person_id}: wrote {written} passage(s) to {path.name}")
        _propagate_sources(person_id, events)
    return written


def _illustrate(
    client: OpenAI,
    event: Dict[str, Any],
    report: str,
    queries: List[str],
) -> None:
    """Put the report's illustrations on the event, or take them off."""
    shown = {
        _image_key(image.get("url", ""))
        for image in (event.get("images") or [])
        if isinstance(image, dict)
    }
    pictures = (
        _fetch_background_images(client, report, queries, shown) if queries else []
    )
    if pictures:
        event["background_images"] = pictures
        for picture in pictures:
            print(f"    image: {picture['query']} -> {picture['caption'][:60]}")
    else:
        event.pop("background_images", None)
        print("    no illustrations found for the report")


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


# Three per report: the layer deals them out between the paragraphs, so a
# report of four or five paragraphs can carry three without turning into a
# gallery — and one picture on a page this long reads as a token.
BACKGROUND_IMAGE_LIMIT = 3


class ChosenImages(BaseModel):
    """Which candidates, if any, actually illustrate the report."""

    keep: List[int] = Field(
        default_factory=list,
        description=(
            "Indexes of candidates that genuinely depict what the report "
            "describes, best first, at most three. Empty when none do."
        ),
    )


CHOOSER_SYSTEM = (
    "You decide whether a picture illustrates a text. You are strict: a picture "
    "that merely shares a word with the text illustrates nothing, and an "
    "irrelevant picture printed beside a report is worse than no picture."
)


# A Commons description field is whatever the uploader typed there, and often
# what they typed was their own paperwork. The layer prints the caption under
# the picture, where "Author: Schadel URL: http://turing.izt.uam.mx Made by me
# on..." reads as a bug.
_CAPTION_JUNK = re.compile(
    r"(author\s*:|source\s*:|https?://|own work|made by me|permission\s*:"
    r"|other[_ ]versions|photographer[,:]|owner of|\{\{|\[\[)",
    re.IGNORECASE,
)


def _caption(candidate: Dict[str, Any], query: str) -> str:
    """A line fit to print under the picture.

    The uploader's description when it reads like one, the filename when it
    does not — a filename is at least always about the thing — and the query
    when there is neither.
    """
    caption = " ".join(str(candidate.get("caption") or "").split())
    if caption and not _CAPTION_JUNK.search(caption):
        if len(caption) > 160:
            head = caption[:160].rsplit(". ", 1)[0]
            caption = (head + ".") if len(head) > 40 else caption[:157].rstrip() + "…"
        return caption
    filename = str(candidate.get("filename") or "")
    stem = re.sub(r"\.[A-Za-z0-9]+$", "", filename).replace("_", " ").strip()
    return stem or query


def _candidates(queries: List[str], already_shown: set) -> List[Dict[str, Any]]:
    """What Commons returns for the call's own queries, deduplicated.

    The event's own pictures are excluded: the slide above is already showing
    them, and an illustration the reader has just scrolled past illustrates
    nothing. Only images carrying a license are kept, because the layer prints
    a credit under every picture and one with no credit cannot be published.
    """
    found: List[Dict[str, Any]] = []
    seen = set(already_shown)
    for query in queries[:4]:
        # Commons ranks by keyword match, and the thing itself is often a few
        # places down behind a map, a modern plaque, and somebody's holiday
        # photograph. The critic reads all of them and mostly says no, so a
        # deeper pool costs one longer prompt and is the difference between a
        # report with one illustration and one with three.
        results = filter_images_by_quality(search_wikimedia_commons(query, limit=12))
        for candidate in results[:6]:
            url = candidate.get("url")
            if not url or _image_key(url) in seen or not candidate.get("license"):
                continue
            found.append(
                {
                    "url": url,
                    "caption": _caption(candidate, query),
                    "source": candidate.get("source"),
                    "creator": candidate.get("creator"),
                    "license": candidate.get("license"),
                    "query": query,
                    # Not stored — the filename is shown to the critic and then
                    # dropped. Commons captions are often a sentence about the
                    # upload rather than about the subject, and the filename is
                    # the one field that always names the thing.
                    "_filename": candidate.get("filename") or "",
                }
            )
            seen.add(_image_key(url))
    return found


def _fetch_background_images(
    client: OpenAI,
    report: str,
    queries: List[str],
    already_shown: set,
    wanted: int = BACKGROUND_IMAGE_LIMIT,
) -> List[Dict[str, Any]]:
    """Pictures for the report: searched by its own queries, then read.

    A Commons keyword search is a keyword search. Asking it for "On Computable
    Numbers manuscript" returned a 16th-century Mexican codex, and asking after
    Christopher Morcom returned a steam engine built by Belliss & Morcom.
    Roughly half of what came back shared a word with the report and nothing
    else, so what comes back is now read against the report before any of it is
    kept, and keeping none is a normal outcome.
    """
    candidates = _candidates(queries, already_shown)
    if not candidates:
        return []

    listing = "\n".join(
        f"[{index}] {candidate['_filename'] or '(no filename)'} — {candidate['caption']}"
        for index, candidate in enumerate(candidates)
    )
    parsed = parse_structured(
        client,
        # A critic, and config.py is explicit that a critic weaker than the
        # generator is worse than no critic. On the small model this one kept
        # letting the Belliss & Morcom steam engine through, which is the exact
        # confusion its instructions name.
        model=DEFAULT_MODEL,
        reasoning_effort=DEFAULT_REASONING_EFFORT,
        input=[
            {"role": "system", "content": CHOOSER_SYSTEM},
            {
                "role": "user",
                "content": (
                    "Which of these pictures illustrate the report below?\n\n"
                    "Each candidate is given as its Commons filename and its "
                    "caption. Read both: a caption is often about the upload, "
                    "and the filename is what names the thing.\n\n"
                    "KEEP a picture that shows a thing the report actually "
                    "names: the machine, the building, the room, the document, "
                    "the instrument, the place. Ask of each one: could this "
                    "picture be printed beside this paragraph with a straight "
                    "face? If you have to explain the connection, the answer "
                    "is no.\n"
                    "REJECT, without exception:\n"
                    "- a picture that merely shares a name or a word with the "
                    "report. A firm called Morcom is not Christopher Morcom, "
                    "and a map of the town of Banbury is not the Banbury "
                    "sheets. A place that lent its name to a thing is not that "
                    "thing\n"
                    "- a map, plan, chart, or diagram of somewhere, unless the "
                    "report is about that ground itself\n"
                    "- a montage, collage, poster, book cover, film still, or "
                    "'events of the year' composite: it depicts nothing in "
                    "particular, and a film the report merely alludes to is "
                    "not an illustration of the report\n"
                    "- a portrait of any person, and any picture of the "
                    "subject: the slide above already carries those\n"
                    "- a picture of a different subject from the same era or "
                    "field, however evocative\n"
                    "- a modern memorial, plaque, or reenactment standing in "
                    "for the thing itself\n"
                    "- a present-day photograph of an institution's buildings, "
                    "campus, or signage standing in for the institution the "
                    "report names. A university logo on a wall is a picture of "
                    "a wall\n"
                    "- a generic stock photograph of an everyday object — an "
                    "apple, a cup, a letter, a laboratory bench — standing in "
                    "for the particular one the report describes. The report's "
                    "apple was a particular apple in a particular room, and "
                    "anybody's apple is not a picture of it\n"
                    "- a picture whose caption is about some later incident at "
                    "the place (building works, a protest, a fire) rather than "
                    "the place in the role the report gives it\n"
                    "Keep at most three, and every one you keep must show a "
                    "DIFFERENT thing: two photographs of the same machine are "
                    "one illustration printed twice, so keep the better one "
                    "and move on. Best first.\n"
                    "THREE IS A CEILING, NOT A TARGET. Do not reach for it. "
                    "One picture that plainly shows what the report describes "
                    "beats three that gesture at it, and keeping none is a "
                    "normal answer.\n\n"
                    f"REPORT:\n{report}\n\n"
                    f"CANDIDATES:\n{listing}\n"
                ),
            },
        ],
        text_format=ChosenImages,
        label="Illustrations for a background report",
    )
    if parsed is None:
        return []

    # One picture per query, enforced here rather than asked for: the two
    # queries are the two things the report wanted illustrated, so taking two
    # answers to the same one prints the same thing twice — which is what kept
    # happening with the Manchester Mark I no matter how the instruction was
    # worded.
    kept: List[Dict[str, Any]] = []
    used_queries = set()
    for index in parsed.keep:
        if not 0 <= index < len(candidates) or len(kept) >= wanted:
            continue
        candidate = candidates[index]
        if candidate["query"] in used_queries:
            continue
        used_queries.add(candidate["query"])
        kept.append({k: v for k, v in candidate.items() if not k.startswith("_")})
    return kept


def _image_key(url: str) -> str:
    """A Commons file identified by its filename, not by the size asked for."""
    name = unquote(str(url or "")).split("/")[-1].split("?")[0]
    return re.sub(r"^\d+px-", "", name).lower()


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
        )

    print(f"\nWrote {total} passage(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
