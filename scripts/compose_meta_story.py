#!/usr/bin/env python3
"""Story composer agent (Phase 8) — top-down composition of a meta story.

Every text in a meta story is written bottom-up by an earlier phase that only
sees its own slice: the description and conclusion are planned before any
event is selected (Phase 1), theme connections are judged per batch (Phase 3),
and the network narration only sees the graph (Phase 6). Nothing ever reads
the *assembled* story. This module adds that missing final step: one AI call
that is shown the whole dataset — including focused Wikipedia excerpts for
every main person — and writes the story it adds up to.

ONE CALL, AND WHY
-----------------

Earlier versions split this into four calls (curation, caption layer, article
layer, redundancy pass) to keep the running prose from restating the texts
printed on the components. The split bought that separation with roughly four
hundred lines of prompt telling the model how to write, and the evidence did
not support the price: across the whole corpus the curation call never once
excluded a person and the redundancy pass rewrote three slots. A single call
sees both kinds of text at the same time, which is exactly what makes "do not
say the same thing twice" checkable — so it is now simply asked, once.

What the prompt still carries is what the model cannot infer:

- **The page map** — every text this story contains, in the order a reader
  meets it. Placement is invisible from field names alone (the reader hits a
  chapter's lead-in one at a time inside a horizontally scroll-locked
  timeline; circle and stop texts arrive as cards), and it is what makes the
  adjacency of article prose and component captions self-evident.
- **The material** — the assembled story, the historical context recorded for
  it, Wikipedia excerpts, and the selectable images.
- **The mechanical contract** — ids copied verbatim, quotes verbatim, the
  image budget, third person, no address of the reader.

Everything about *craft* is left to the model.

Everything it returns is applied deterministically and defensively:

- Images are only ever *selected by key* from the people's own story slides
  (``collect_image_candidates``) and copied verbatim — the model cannot
  introduce a URL. A shared budget (``MAX_IMAGES_PER_STORY``) covers every
  prose region, and no image is used twice.
- Quote blocks are verified **verbatim against the source material** (the
  story brief plus the Wikipedia excerpts, whitespace/punctuation
  normalized); a quote that does not appear in the material is dropped.
- Composed circles may only contain existing main people, each person joins
  at most one circle, circles need at least two members, and if the composed
  organization covers less than half of the connected cast it is rejected in
  favor of the previous narration.
- Composed map stops are matched by cluster key, unknown keys are ignored,
  unmentioned stops are kept (carrying their previous narration), and
  discards are honored only while at least ``MIN_MAP_CLUSTERS`` stops
  survive (re-kept by score). Discards are recorded under
  ``geo_map.discarded`` with the composer's reason.
- Facts, dates, IDs, event indices, coordinates, and the graph itself are
  never sent to the model as editable fields, so they cannot drift.

The call operates on a working copy; the original dataset is returned
unchanged if it fails, so the composer is safe to run as a non-fatal pipeline
phase. Provenance (model, throughline) is stamped into a top-level
``composition`` block.

PROSE IS BLOCKS, EVERYWHERE
---------------------------

All four prose regions — opening, description, the section bodies, and the
closing — are lists of ``paragraph``/``image``/``quote`` blocks. Previously
only the section bodies were, so the opening could carry an image but not a
quote and the description could carry neither, for no reason a reader could
perceive. One shape means one renderer, one translation path, and one set of
guarantees.

Standalone usage (recompose an existing meta story):

    python scripts/compose_meta_story.py computing_pioneers --verbose
    python scripts/compose_meta_story.py --all --dry-run
"""

import argparse
import copy
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, cast

from openai import OpenAI
from pydantic import BaseModel, Field

from config import (
    COMPOSER_DEFAULT_MODEL,
    DEFAULT_REASONING_EFFORT,
    enable_utf8_console,
)
from meta_story_map import MIN_MAP_CLUSTERS
from meta_story_network import derive_clusters
from meta_story_network_review import build_wikipedia_context

enable_utf8_console()

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
REGISTER_PATH = DATA_DIR / "persons.json"
PEOPLE_DIR = DATA_DIR / "people"
META_STORIES_DIR = DATA_DIR / "meta_stories"

# Image guardrails: the composer only ever *selects* images by key from the
# people's own story slides; URLs are copied deterministically, so it can
# never invent one. The budget is shared by every prose region.
MAX_IMAGE_CANDIDATES = 80
MAX_IMAGES_PER_STORY = 6

# Wikipedia grounding: the composer reads a larger slice of each person's
# article lead than the network review does — it writes the story's prose,
# not just tie edits, so it needs the narrative substance.
WIKI_LEAD_CHARS = 1200
WIKI_MAX_CHARS = 6000

# How much of each story event's own description the brief quotes — the
# events carry the documented facts the composer must build the story from.
EVENT_DESCRIPTION_CHARS = 320

# The prose regions, in reading order. One name per region, used by the
# schema, the page map, the application path and the diagnostics alike.
PROSE_REGIONS = ("opening", "description", "timeline", "network", "map", "conclusion")

# Section bodies are stored per component section; the opening, description
# and closing are stored top-level.
BODY_SECTIONS = ("timeline", "network", "map")


# ============================================================================
# PYDANTIC MODELS
# ============================================================================


class StoryBlock(BaseModel):
    """One block of prose. Every prose region on the page is a list of these."""

    type: Literal["paragraph", "image", "quote"] = Field(
        description="Block kind: narrative paragraph, image (selected by key), "
        "or a verbatim quote from the material"
    )
    text: Optional[str] = Field(
        default=None,
        description="Paragraph or quote text; null for image blocks",
    )
    image_key: Optional[str] = Field(
        default=None,
        description="For image blocks: a key copied verbatim from the image "
        "candidate list; null otherwise",
    )
    image_layout: Optional[Literal["left", "right", "full"]] = Field(
        default=None,
        description="For image blocks: 'left'/'right' floats the figure beside "
        "the following text on wide screens, 'full' spans the column",
    )
    attribution: Optional[str] = Field(
        default=None,
        description="For quote blocks: who said or wrote it (short); null otherwise",
    )


class ComposedChapter(BaseModel):
    """Texts for one timeline chapter."""

    id: str = Field(description="Chapter id, copied verbatim from the input")
    headline: str = Field(
        description="2-5 words, WITHOUT a date range (it is appended automatically)"
    )
    lead_in: str = Field(description="1-2 sentences")


class ComposedCircle(BaseModel):
    """One circle of the composer's own network organization."""

    member_ids: List[str] = Field(
        description="Person ids copied verbatim from the cast: at least two, "
        "each person in at most one circle across all circles"
    )
    title: str = Field(description="2-5 words")
    text: str = Field(description="2-4 sentences")


class ComposedMapStop(BaseModel):
    """A kept map stop, in presentation order."""

    key: str = Field(description="Stop key, copied verbatim from the input")
    title: str = Field(description="2-5 words")
    text: str = Field(description="2-4 sentences")


class DiscardedMapStop(BaseModel):
    """A map stop dropped from the story."""

    key: str = Field(description="Stop key, copied verbatim from the input")
    reason: str = Field(description="Why this place adds nothing to the story")


class ComposedSectionHeadings(BaseModel):
    """Headings replacing the generic section labels."""

    timeline: str = Field(description="2-6 words")
    network: str = Field(description="2-6 words")
    map: Optional[str] = Field(
        default=None, description="2-6 words; null when the story has no map"
    )
    conclusion: str = Field(description="2-6 words")


class CompositionResult(BaseModel):
    """Everything the composer writes, in the order it appears on the page."""

    throughline: str = Field(
        description="2-4 sentences naming this story's arc, for your own use. "
        "Never displayed."
    )
    title: str = Field(description="2-5 words")
    tagline: str = Field(description="3-10 words")
    opening: List[StoryBlock] = Field(description="The story's opening prose")
    description: List[StoryBlock] = Field(
        description="The prose following the opening, still in the page header"
    )
    section_headings: ComposedSectionHeadings = Field(
        description="Headings for the four sections"
    )
    timeline_body: List[StoryBlock] = Field(
        description="Prose between the chronology heading and the timeline"
    )
    network_body: List[StoryBlock] = Field(
        description="Prose between the network heading and the graph"
    )
    map_body: List[StoryBlock] = Field(
        description="Prose between the places heading and the map; empty when "
        "the story has no map"
    )
    conclusion: List[StoryBlock] = Field(
        description="The closing section's prose — the last prose on the page"
    )
    chapters: List[ComposedChapter] = Field(
        description="One entry per chapter, same order as given"
    )
    circles: List[ComposedCircle] = Field(
        description="The network's circles, in presentation order"
    )
    map_stops: List[ComposedMapStop] = Field(
        description="The kept map stops in presentation order; empty when the "
        "story has no map"
    )
    discarded_map_stops: List[DiscardedMapStop] = Field(
        description="Map stops to drop; an empty list is fine"
    )

    def blocks(self, region: str) -> List[StoryBlock]:
        """The block list for a region name from ``PROSE_REGIONS``."""
        if region in BODY_SECTIONS:
            return getattr(self, f"{region}_body") or []
        return cast(List[StoryBlock], getattr(self, region) or [])


# ============================================================================
# INPUT MATERIAL
# ============================================================================


def _person_index(registry: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {p.get("id", ""): p for p in registry.get("people", [])}


def _truncate(text: str, limit: int = 240) -> str:
    if len(text) <= limit:
        return text
    cut = text[: limit - 3]
    last_period = cut.rfind(".")
    if last_period > limit // 2:
        return cut[: last_period + 1]
    return cut + "..."


def build_cast_sheet(dataset: Dict[str, Any], registry: Dict[str, Any]) -> str:
    """Deterministic per-person summary of who is in the story."""
    index = _person_index(registry)
    person_ids = dataset.get("meta_story", {}).get("person_ids", [])

    event_count: Dict[str, int] = {pid: 0 for pid in person_ids}
    for chapter in dataset.get("chapters") or []:
        for event in chapter.get("person_events") or []:
            pid = event.get("person_id")
            if pid in event_count:
                event_count[pid] += 1

    main_link_count: Dict[str, int] = {pid: 0 for pid in person_ids}
    for link in (dataset.get("social_network") or {}).get("links") or []:
        if link.get("kind") != "main":
            continue
        for pid in (link.get("source"), link.get("target")):
            if pid in main_link_count:
                main_link_count[pid] += 1

    lines = []
    for pid in person_ids:
        person = index.get(pid, {})
        roles = ", ".join(person.get("primaryRoles") or []) or "role unknown"
        birth = person.get("birthDate", "?")
        death = person.get("deathDate", "")
        lifespan = f"{birth} - {death}" if death else f"b. {birth}"
        lines.append(
            f"- {pid}: {person.get('name', pid).replace('_', ' ')} ({roles}; {lifespan})\n"
            f"    story events: {event_count.get(pid, 0)}; "
            f"direct ties to other main people: {main_link_count.get(pid, 0)}\n"
            f"    summary: {_truncate(person.get('summary', ''))}"
        )
    return "\n".join(lines)


def load_person_life_events(person_id: str) -> Optional[Dict[str, Any]]:
    """Load a person's life_events.json (English reference)."""
    path = PEOPLE_DIR / person_id / "life_events.json"
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return cast(Optional[Dict[str, Any]], json.load(f))


def _events_cached(
    cache: Dict[str, Optional[List[Dict[str, Any]]]], person_id: str
) -> Optional[List[Dict[str, Any]]]:
    if person_id not in cache:
        data = load_person_life_events(person_id)
        cache[person_id] = data.get("events") if isinstance(data, dict) else None
    return cache[person_id]


def collect_image_candidates(
    dataset: Dict[str, Any], registry: Dict[str, Any]
) -> Dict[str, Dict[str, Any]]:
    """Collect selectable images from the story events' person slides.

    Returns an ordered mapping of ``person_id:event_index:image_index`` keys
    to image records carrying the actual ``url``/``caption``/``source`` plus
    provenance. The composer only ever picks one of these keys; the record is
    copied deterministically, so a hallucinated URL can never enter the data.
    """
    index = _person_index(registry)
    events_cache: Dict[str, Optional[List[Dict[str, Any]]]] = {}
    candidates: Dict[str, Dict[str, Any]] = {}

    for chapter in dataset.get("chapters") or []:
        for story_event in chapter.get("person_events") or []:
            person_id = story_event.get("person_id", "")
            event_index = story_event.get("event_index")
            if not isinstance(event_index, int):
                continue
            events = _events_cached(events_cache, person_id)
            if not events or not 0 <= event_index < len(events):
                continue
            event = events[event_index]
            person_name = (
                index.get(person_id, {}).get("name", person_id).replace("_", " ")
            )
            for image_index, image in enumerate(event.get("images") or []):
                url = image.get("url")
                if not url:
                    continue
                key = f"{person_id}:{event_index}:{image_index}"
                candidates[key] = {
                    "url": url,
                    "caption": image.get("caption", ""),
                    "source": image.get("source", ""),
                    "person_id": person_id,
                    "event_index": event_index,
                    "image_index": image_index,
                    "person_name": person_name,
                    "event_title": event.get("title", ""),
                    "event_date": story_event.get("event_date", ""),
                }
                if len(candidates) >= MAX_IMAGE_CANDIDATES:
                    return candidates
    return candidates


def image_record(candidate: Dict[str, Any]) -> Dict[str, Any]:
    """The subset of a candidate that is stored in the meta story JSON."""
    return {
        "url": candidate["url"],
        "caption": candidate["caption"],
        "source": candidate["source"],
        "person_id": candidate["person_id"],
        "event_index": candidate["event_index"],
        "image_index": candidate["image_index"],
    }


def build_image_candidates_brief(candidates: Dict[str, Dict[str, Any]]) -> str:
    """Render the image candidates for the composition prompt."""
    if not candidates:
        return "IMAGE CANDIDATES: none available."
    lines = ["IMAGE CANDIDATES (from the people's own story slides; select by key):"]
    for key, cand in candidates.items():
        lines.append(
            f"- [img={key}] {cand['event_date']} — {cand['person_name']}: "
            f"{cand['event_title']} — {_truncate(cand['caption'], 140)}"
        )
    return "\n".join(lines)


def build_story_wikipedia_context(
    dataset: Dict[str, Any], registry: Dict[str, Any]
) -> str:
    """Focused Wikipedia excerpts for the story's main people."""
    index = _person_index(registry)
    people = [
        (pid, str(index.get(pid, {}).get("name", pid)).replace("_", " "))
        for pid in dataset.get("meta_story", {}).get("person_ids", [])
    ]
    return build_wikipedia_context(
        people, lead_chars=WIKI_LEAD_CHARS, max_chars=WIKI_MAX_CHARS
    )


def _current_circles(dataset: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The story's current circle organization, for the brief.

    A composed story stores explicit ``member_ids`` per circle; otherwise the
    circles are the deterministically derived clusters, with any Phase 6
    narration matched by key.
    """
    network = dataset.get("social_network") or {}
    narration = network.get("narration") or {}
    circles = narration.get("circles") or []
    if circles and any(c.get("member_ids") for c in circles):
        return [
            {
                "members": c.get("member_ids") or [],
                "title": c.get("title", ""),
                "text": c.get("text", ""),
            }
            for c in circles
        ]
    drafts_by_key = {c.get("key"): c for c in circles if c.get("key")}
    result = []
    for cluster in derive_clusters(network):
        draft = drafts_by_key.get(cluster["key"]) or {}
        result.append(
            {
                "members": [n["id"] for n in cluster["mains"]],
                "title": draft.get("title", ""),
                "text": draft.get("text", ""),
            }
        )
    return result


def build_historical_context(dataset: Dict[str, Any]) -> str:
    """The chapters' ``historical_context`` entries.

    The only place in the dataset where the world *outside* these lives is
    described, and so the material for any prose that is not about the items.
    """
    contexts = [
        (chapter, ctx)
        for chapter in dataset.get("chapters") or []
        for ctx in chapter.get("historical_context") or []
    ]
    if not contexts:
        return ""
    parts = [
        "HISTORICAL CONTEXT recorded for this story, by era — the "
        "circumstances around the events rather than the events themselves:"
    ]
    for chapter, ctx in contexts:
        span = (
            f"{chapter.get('date_start', '')}-{chapter.get('date_end', '')}"
            if chapter.get("date_start")
            else ""
        )
        parts.append(f"- [{span}] {ctx.get('title', '')}: {ctx.get('description', '')}")
    return "\n".join(parts)


def build_story_brief(dataset: Dict[str, Any], registry: Dict[str, Any]) -> str:
    """Render the assembled story as text for the composer prompt."""
    index = _person_index(registry)
    meta = dataset.get("meta_story", {})
    events_cache: Dict[str, Optional[List[Dict[str, Any]]]] = {}

    def person_name(pid: str) -> str:
        return str(index.get(pid, {}).get("name", pid)).replace("_", " ")

    def event_description(pid: str, event_index: Any) -> str:
        if not isinstance(event_index, int):
            return ""
        events = _events_cached(events_cache, pid)
        if not events or not 0 <= event_index < len(events):
            return ""
        return _truncate(
            str(events[event_index].get("description", "")).replace("\n", " "),
            EVENT_DESCRIPTION_CHARS,
        )

    parts = [
        f"TITLE (draft): {meta.get('title', '')}",
        f"TAGLINE (draft): {meta.get('tagline', '')}",
        f"SPAN: {meta.get('date_range_start', '')} to {meta.get('date_range_end', '')}",
        "",
        "CAST:",
        build_cast_sheet(dataset, registry),
        "",
        "CHAPTERS (the timeline, in order):",
    ]
    for chapter in dataset.get("chapters") or []:
        parts.append(
            f"Chapter [{chapter.get('id', '')}] \"{chapter.get('title', '')}\" "
            f"({chapter.get('date_start', '')}-{chapter.get('date_end', '')})"
        )
        for event in chapter.get("person_events") or []:
            parts.append(
                f"  {event.get('event_date', '')} — "
                f"{person_name(event.get('person_id', ''))}: "
                f"{event.get('event_title', '')}\n"
                f"      shown on the timeline: {event.get('theme_connection', '')}"
            )
            description = event_description(
                event.get("person_id", ""), event.get("event_index")
            )
            if description:
                parts.append(f"      event details: {description}")

    network = dataset.get("social_network") or {}
    if network.get("links"):
        node_name = {
            n.get("id"): n.get("name", n.get("id")) for n in network.get("nodes") or []
        }
        parts.append("")
        parts.append("NETWORK TIES (the full tie set of the social graph):")
        for link in network.get("links") or []:
            s, t = link.get("source", ""), link.get("target", "")
            bridge = " (bridge)" if link.get("kind") != "main" else ""
            parts.append(
                f"  - {s} <-> {t} ({node_name.get(s, s)} <-> {node_name.get(t, t)})"
                f"{bridge} [{link.get('relationship_type', '')}, "
                f"{link.get('strength', '')}]: "
                f"{link.get('relationship_description', '')}"
            )
        circles = _current_circles(dataset)
        if circles:
            parts.append("CURRENT CIRCLES (the network's current organization):")
            for circle in circles:
                members = ", ".join(person_name(pid) for pid in circle["members"])
                parts.append(f"- Members: {members}")
                if circle["title"] or circle["text"]:
                    parts.append(
                        f"  Narration draft: \"{circle['title']}\" — {circle['text']}"
                    )

    geo_map = dataset.get("geo_map")
    if isinstance(geo_map, dict) and geo_map.get("clusters"):
        map_narration = geo_map.get("narration") or {}
        parts.append("")
        parts.append("MAP STOPS (the story's places, currently in this order):")
        stop_drafts = {
            s.get("key"): s for s in map_narration.get("stops") or [] if s.get("key")
        }
        for cluster in geo_map["clusters"]:
            years = (
                f"{cluster.get('year_start', '')}-{cluster.get('year_end', '')}"
                if cluster.get("year_start") is not None
                else ""
            )
            parts.append(
                f"Stop key: {cluster.get('key', '')} — {cluster.get('label', '')} "
                f"({years}; geographic weight {cluster.get('score', 0):.1f})"
            )
            for event in cluster.get("events") or []:
                parts.append(
                    f"  - {event.get('event_date', '')} — "
                    f"{event.get('person_name', '')}: {event.get('event_title', '')} "
                    f"@ {event.get('place', '')}"
                )
            draft = stop_drafts.get(cluster.get("key"))
            if draft:
                parts.append(
                    f"  Narration draft: \"{draft.get('title', '')}\" — "
                    f"{draft.get('text', '')}"
                )

    return "\n".join(parts)


# ============================================================================
# THE COMPOSITION CALL
# ============================================================================


def build_page_map(has_map: bool) -> str:
    """The page, in the order the reader meets it.

    The one thing the model cannot infer from a schema. Field names say what
    a text is; only this says where it lands, what sits next to it, and that a
    chapter's lead-in is met alone rather than as one item of a list.
    """
    map_section = (
        """  ──────────────────────────────────────────────────────
  heading: section_headings.map
  map_body                        ← yours
  THE MAP — pinned full screen while the stops arrive one card at a
    time, in the order you set; each card is a map_stops title + text
"""
        if has_map
        else "  (this story has no map: map_body, map_stops and\n"
        "   section_headings.map stay empty)\n"
    )
    return f"""THE PAGE, IN THE ORDER THE READER MEETS IT

  title
  tagline
  the story's date range (already on the page)
  opening                         ← yours
  description                     ← yours
  ──────────────────────────────────────────────────────
  heading: section_headings.timeline
  timeline_body                   ← yours
  THE TIMELINE — scrolled sideways; the reader meets one chapter at a
    time, seeing that chapter's headline and lead_in alone, with its
    events and their one-line texts
  ──────────────────────────────────────────────────────
  heading: section_headings.network
  network_body                    ← yours
  THE GRAPH — the cast as a graph; circles arrive one card at a time,
    each card a circles title + text
{map_section}  ──────────────────────────────────────────────────────
  heading: section_headings.conclusion
  conclusion                      ← yours, the last prose on the page
  cards linking to each person's own story (already on the page)"""


def run_composition(
    dataset: Dict[str, Any],
    registry: Dict[str, Any],
    wikipedia_context: str,
    image_candidates: Dict[str, Dict[str, Any]],
    client: OpenAI,
    model: str,
    reasoning_effort: str,
    verbose: bool = False,
) -> Optional[CompositionResult]:
    """Compose the whole story in one call."""
    has_map = bool((dataset.get("geo_map") or {}).get("clusters"))

    prompt = f"""You are composing a meta story: one page about several connected lives, told
through a timeline of events, a graph of who knew whom, and a map of places.
Earlier steps drafted its texts bottom-up, one item at a time, never seeing
the whole. You see the whole — write the story they add up to.

{build_page_map(has_map)}

Two kinds of text. The captions — chapter headlines and lead-ins, circle
cards, map stop cards — belong to the things the reader is looking at. The
prose regions run between them and are a piece of writing in its own right.
Decide for yourself what this story is about and how it is best told, as a
journalist or a good teacher would tell it to a curious general reader.

You also decide the shape of two sections: organize the cast into the circles
that tell the relationship story, and keep, order and discard the map stops.

THE ASSEMBLED STORY:

{build_story_brief(dataset, registry)}

{build_historical_context(dataset)}

BACKGROUND MATERIAL (Wikipedia excerpts for the main people):

{wikipedia_context}

{build_image_candidates_brief(image_candidates)}

Ground everything in the material above: no invented events, dates,
relationships or quotations. Quotes verbatim, with attribution. Copy every id
and key exactly, never construct one. At most {MAX_IMAGES_PER_STORY} images in
the whole story, never reused. Third person, about the people and their era —
never address the reader, never mention the page or its parts."""

    if verbose:
        print(f"  Prompt: {len(prompt)} characters")

    try:
        response = client.responses.parse(
            model=model,
            reasoning=cast(Any, {"effort": reasoning_effort}),
            input=[
                {
                    "role": "system",
                    "content": "You are a journalist composing a biographical "
                    "data story from the material you are given. You never "
                    "invent facts.",
                },
                {"role": "user", "content": prompt},
            ],
            text_format=CompositionResult,
        )
        result = response.output_parsed
        if result is None:
            print("Warning: composition returned no parsed result")
            return None
        if verbose:
            print(f"  Throughline: {result.throughline}")
            print(f"  Composed title: {result.title} — {result.tagline}")
            print(
                "  Section headings: "
                f"{result.section_headings.timeline} / "
                f"{result.section_headings.network} / "
                f"{result.section_headings.map or '-'} / "
                f"{result.section_headings.conclusion}"
            )
            print(
                "  Prose blocks: "
                + ", ".join(
                    f"{region}: {len(result.blocks(region))}"
                    for region in PROSE_REGIONS
                )
            )
        return result
    except Exception as e:
        print(f"Warning: composition call failed: {e}")
        return None


# ============================================================================
# DIAGNOSTICS
#
# Reported under --verbose, never gates. They catch the two opposite ways
# composed prose goes wrong: saying what the captions beside it already said,
# and saying nothing checkable at all.
# ============================================================================

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_WORD = re.compile(r"[a-z][a-z'’-]+")
_PROPER_NOUN = re.compile(r"\b[A-Z][a-zA-Z'’-]+")
_NUMBER = re.compile(r"\b\d[\d,.]*\b")

_STOPWORDS = frozenset("""
    the and for that with from this they their them then than when what which
    who whom whose was were been being have has had would could should will
    into over under after before while about against between during through
    such only also more most other some any each both very can may might must
    its his her him she her hers our ours your yours out off down once here
    there where why how all not nor but yet him one two new made make making
    """.split())

# Below this many anchors a passage of any length has stopped saying anything
# checkable. An *anchor* is a proper noun or a number: the named law,
# institution, place, person or year that makes a sentence checkable.
MIN_ANCHORS = 2
# Short passages are exempt: a single line can be concrete without naming
# three institutions, and the anchor count is noisy at that length.
ANCHOR_MIN_WORDS = 25

# A part of the page used as a grammatical subject — "The map asks how...",
# "The chronology follows...". The prose narrates the history, not its own
# presentation, and this is the phrasing that slips through most often.
_INTERFACE_SUBJECT = re.compile(
    r"\b(?:the|this)\s+(?:chronology|timeline|network|graph|map|section|story)\b",
    re.IGNORECASE,
)


def _content_words(text: str) -> set:
    return {
        w for w in _WORD.findall(text.lower()) if w not in _STOPWORDS and len(w) > 2
    }


def collect_prose_slots(composed: CompositionResult) -> List[tuple]:
    """The composed prose as ``(slot_id, text)``, in reading order."""
    slots: List[tuple] = []
    for region in PROSE_REGIONS:
        for index, block in enumerate(composed.blocks(region)):
            if block.type == "paragraph" and (block.text or "").strip():
                slots.append((f"{region}:{index}", (block.text or "").strip()))
    return slots


def collect_caption_slots(composed: CompositionResult) -> List[tuple]:
    """The caption layer as ``(slot_id, text)`` — the prose's neighbours.

    Event texts are left out on purpose: there are dozens, each one sentence
    long, and the chapter, circle and stop texts are the ones that sit as
    blocks of prose right beside the composed paragraphs.
    """
    slots: List[tuple] = []
    for index, chapter in enumerate(composed.chapters):
        if chapter.lead_in.strip():
            slots.append(
                (f"chapter:{index}", f"{chapter.headline} — {chapter.lead_in.strip()}")
            )
    for index, circle in enumerate(composed.circles):
        if circle.text.strip():
            slots.append((f"circle:{index}", f"{circle.title} — {circle.text.strip()}"))
    for index, stop in enumerate(composed.map_stops):
        if stop.text.strip():
            slots.append((f"stop:{index}", f"{stop.title} — {stop.text.strip()}"))
    return slots


def rank_slot_overlaps(
    slots: List[tuple], reference: Optional[List[tuple]] = None, min_shared: int = 3
) -> List[tuple]:
    """Rank cross-slot sentence pairs by content-word overlap (Dice).

    ``reference`` slots (the captions) are compared against ``slots`` but never
    against each other — two captions describing adjacent chapters naturally
    share vocabulary, and that is not a defect of the prose.

    Returns ``(slot_a, slot_b, sentence_a, sentence_b, score)`` sorted by score.

    A **diagnostic, not a detector**: paraphrase and coincidence overlap in the
    0.25-0.30 band, so no cutoff separates them. Where the numbers do separate
    is prose-against-caption — when the composer slipped into recapping its own
    components, the top pairs there sat at 0.43-0.53, near-verbatim restatement
    and well clear of the paraphrase band. A top reference score in that range
    is a strong signal to look at the story.
    """

    def prepare(entries: List[tuple]) -> List[tuple]:
        prepared = []
        for slot_id, text in entries:
            for sentence in _SENTENCE_SPLIT.split(text):
                words = _content_words(sentence)
                if len(words) >= 5:
                    prepared.append((slot_id, sentence.strip(), words))
        return prepared

    prepared = prepare(slots)
    prepared_reference = prepare(reference or [])

    ranked = []
    for i, (slot_a, sent_a, words_a) in enumerate(prepared):
        against = list(prepared[i + 1 :])
        # The opening may narrate a documented moment in full, so it
        # legitimately overlaps whichever caption covers that moment.
        if not slot_a.startswith("opening:"):
            against += prepared_reference
        for slot_b, sent_b, words_b in against:
            if slot_a == slot_b:
                continue
            shared = words_a & words_b
            if len(shared) < min_shared:
                continue
            score = 2 * len(shared) / (len(words_a) + len(words_b))
            ranked.append((slot_a, slot_b, sent_a, sent_b, score))
    return sorted(ranked, key=lambda r: r[4], reverse=True)


def count_anchors(text: str) -> int:
    """Count the concrete anchors in a passage.

    Words at the start of a sentence are capitalized by grammar rather than by
    content, so they are skipped.
    """
    body = " ".join(
        sentence[len(sentence.split(" ")[0]) :]
        for sentence in _SENTENCE_SPLIT.split(text)
    )
    return len(_PROPER_NOUN.findall(body)) + len(_NUMBER.findall(text))


def find_abstract_slots(slots: List[tuple]) -> List[tuple]:
    """``(slot_id, anchors)`` for prose slots with too few specifics."""
    return [
        (slot_id, count_anchors(text))
        for slot_id, text in slots
        if len(text.split()) >= ANCHOR_MIN_WORDS and count_anchors(text) < MIN_ANCHORS
    ]


def find_interface_references(slots: List[tuple]) -> List[tuple]:
    """``(slot_id, phrase)`` for prose slots that describe the page itself."""
    found = []
    for slot_id, text in slots:
        match = _INTERFACE_SUBJECT.search(text)
        if match:
            found.append((slot_id, match.group(0)))
    return found


# ============================================================================
# APPLICATION
#
# Structure is authoritative on the dataset side: everything is matched by
# id/key, unknown entries are ignored with a warning, images are resolved from
# the candidate pool only, and quotes must appear verbatim in the material.
# ============================================================================


def _strip_date_suffix(headline: str) -> str:
    """Remove a trailing "(YYYY-YYYY)" the model may have added anyway."""
    return re.sub(r"\s*\(\d{4}\s*[-–]\s*\d{4}\)\s*$", "", headline).strip()


# Typographic characters normalized away before the verbatim-quote check, so
# a straightened apostrophe or dash never fails an otherwise genuine quote.
_QUOTE_TRANS = str.maketrans(
    {"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-"}
)

# An image candidate key: person_id:event_index:image_index.
_IMAGE_KEY = re.compile(r"[a-z0-9_]+:\d+:\d+")


def _normalize_quote(text: str) -> str:
    return re.sub(r"\s+", " ", text.translate(_QUOTE_TRANS)).strip().lower()


def _render_blocks(
    blocks: List[StoryBlock],
    region: str,
    resolve_image: Any,
    corpus: str,
    dropped: Dict[str, int],
) -> List[Dict[str, Any]]:
    """Validate one prose region's blocks into their stored form."""
    out: List[Dict[str, Any]] = []
    for block in blocks or []:
        if block.type == "paragraph":
            text = (block.text or "").strip()
            if text:
                out.append({"type": "paragraph", "text": text})
        elif block.type == "image":
            image = resolve_image(block.image_key, f"{region} region")
            if image is not None:
                layout = (
                    block.image_layout
                    if block.image_layout in ("left", "right", "full")
                    else "full"
                )
                out.append({"type": "image", "image": image, "layout": layout})
        elif block.type == "quote":
            text = (block.text or "").strip().strip('"“”')
            if not text:
                continue
            if _normalize_quote(text) not in corpus:
                print(
                    f"Warning: quote in {region} is not verbatim in the "
                    f'material, dropped: "{_truncate(text, 80)}"'
                )
                dropped["quotes"] += 1
                continue
            entry: Dict[str, Any] = {"type": "quote", "text": text}
            attribution = (block.attribution or "").strip()
            if attribution:
                entry["attribution"] = attribution
            out.append(entry)
    return out


def _apply_network_circles(
    dataset: Dict[str, Any],
    composed: CompositionResult,
    verbose: bool = False,
) -> None:
    """Replace the network narration with the composer's circle organization.

    Guardrails: members must be existing main people, each person joins at
    most one circle, a circle needs >= 2 valid members, and the composed
    organization must cover at least half of the connected main cast —
    otherwise it is rejected and the previous narration is kept.
    """
    network = dataset.get("social_network")
    if not isinstance(network, dict) or not network.get("nodes"):
        return

    main_nodes = {
        n["id"]: n for n in network.get("nodes") or [] if n.get("type") == "main"
    }
    linked_mains = set()
    for link in network.get("links") or []:
        for nid in (link.get("source"), link.get("target")):
            if nid in main_nodes:
                linked_mains.add(nid)

    used: set = set()
    circles: List[Dict[str, Any]] = []
    for circle in composed.circles:
        ids = []
        for pid in circle.member_ids:
            if pid not in main_nodes:
                print(f"Warning: circle member '{pid}' is not a main person, dropped")
                continue
            if pid in used:
                print(
                    f"Warning: circle member '{pid}' already appears in an "
                    "earlier circle, dropped"
                )
                continue
            ids.append(pid)
        if len(ids) < 2:
            print(
                f"Warning: composed circle '{circle.title}' has fewer than 2 "
                "valid members, dropped"
            )
            continue
        used.update(ids)
        # Members ordered like the derived clusters (birth year, then name) so
        # the stored key stays stable however the model ordered the list.
        ids.sort(
            key=lambda pid: (
                (
                    main_nodes[pid].get("birth_year")
                    if main_nodes[pid].get("birth_year") is not None
                    else 10**9
                ),
                main_nodes[pid].get("name", ""),
            )
        )
        circles.append(
            {
                "key": "+".join(ids),
                "member_ids": ids,
                "title": circle.title.strip(),
                "text": circle.text.strip(),
            }
        )

    required = min(len(linked_mains), max(2, (len(linked_mains) + 1) // 2))
    if not circles or len(used & linked_mains) < required:
        print(
            "Warning: composed circles rejected (cover "
            f"{len(used & linked_mains)} of {len(linked_mains)} connected "
            "people), keeping previous narration"
        )
        return

    left_out = sorted(linked_mains - used)
    if left_out and verbose:
        print(f"  People outside all circles: {', '.join(left_out)}")

    network["narration"] = {"circles": circles}
    if verbose:
        print(f"  Composed {len(circles)} circle(s): {[c['title'] for c in circles]}")


def _apply_map_composition(
    dataset: Dict[str, Any],
    composed: CompositionResult,
    verbose: bool = False,
) -> None:
    """Reorder/curate the map stops per the composer's decisions.

    Unknown keys are ignored, unmentioned stops are kept (carrying their
    previous narration), and discards are honored only while at least
    ``MIN_MAP_CLUSTERS`` stops survive (re-kept by score). Discards are
    recorded under ``geo_map.discarded`` with the composer's reason.
    """
    geo_map = dataset.get("geo_map")
    if not isinstance(geo_map, dict) or not geo_map.get("clusters"):
        return

    clusters = {c.get("key"): c for c in geo_map["clusters"] if c.get("key")}
    stops = {
        s.get("key"): s for s in (geo_map.get("narration") or {}).get("stops") or []
    }

    discard_reasons: Dict[str, str] = {}
    for discarded in composed.discarded_map_stops:
        if discarded.key not in clusters:
            print(f"Warning: discarded map stop '{discarded.key}' is unknown, ignored")
            continue
        discard_reasons[discarded.key] = discarded.reason.strip()

    ordered_keys: List[str] = []
    composed_stops: Dict[str, Dict[str, str]] = {}
    for stop in composed.map_stops:
        if stop.key not in clusters:
            print(f"Warning: composed map stop '{stop.key}' is unknown, ignored")
            continue
        if stop.key in ordered_keys:
            continue
        ordered_keys.append(stop.key)
        composed_stops[stop.key] = {
            "title": stop.title.strip(),
            "text": stop.text.strip(),
        }
    # Stops the composer neither kept nor discarded keep their place and text.
    for key in clusters:
        if key not in ordered_keys and key not in discard_reasons:
            ordered_keys.append(key)

    # Never fall below the floor: re-keep the strongest discarded stops.
    if len(ordered_keys) < MIN_MAP_CLUSTERS:
        by_score = sorted(
            discard_reasons,
            key=lambda k: clusters[k].get("score", 0),
            reverse=True,
        )
        while by_score and len(ordered_keys) < MIN_MAP_CLUSTERS:
            key = by_score.pop(0)
            print(f"Warning: keeping discarded map stop '{key}' (floor reached)")
            discard_reasons.pop(key, None)
            ordered_keys.append(key)

    geo_map["clusters"] = [clusters[key] for key in ordered_keys]
    narration_stops = []
    for key in ordered_keys:
        composed_stop = composed_stops.get(key)
        if composed_stop:
            narration_stops.append({"key": key, **composed_stop})
        elif key in stops:
            narration_stops.append(stops[key])
    if narration_stops:
        geo_map["narration"] = {"stops": narration_stops}
    if discard_reasons:
        geo_map["discarded"] = [
            {"key": key, "label": clusters[key].get("label", ""), "reason": reason}
            for key, reason in discard_reasons.items()
        ]
    else:
        geo_map.pop("discarded", None)
    if verbose:
        print(
            f"  Map: {len(ordered_keys)} stop(s) kept, "
            f"{len(discard_reasons)} discarded"
        )


def apply_composition(
    dataset: Dict[str, Any],
    composed: CompositionResult,
    image_candidates: Optional[Dict[str, Dict[str, Any]]] = None,
    material: str = "",
    verbose: bool = False,
) -> None:
    """Overlay the composed texts onto the dataset (mutates in place)."""
    candidates = image_candidates or {}
    used_image_keys: set = set()

    def resolve_image(key: Optional[str], slot: str) -> Optional[Dict[str, Any]]:
        if not key:
            return None
        # The candidate list renders each key inside a whole line —
        # "[img=person:12:0] 1843 — Ada Lovelace: Publishes Notes ..." — and
        # the model copies back varying amounts of that decoration, from the
        # brackets alone to the entire line. Both forms were observed dropping
        # real selections, so the key is extracted by shape rather than
        # trimmed by prefix.
        match = _IMAGE_KEY.search(key)
        resolved = match.group(0) if match else key.strip()
        candidate = candidates.get(resolved)
        if candidate is None:
            print(f"Warning: unknown image key '{key}' for {slot}, dropped")
            return None
        if resolved in used_image_keys:
            print(f"Warning: image '{resolved}' reused for {slot}, dropped")
            return None
        if len(used_image_keys) >= MAX_IMAGES_PER_STORY:
            print(f"Warning: image budget exhausted, '{resolved}' for {slot} dropped")
            return None
        used_image_keys.add(resolved)
        return image_record(candidate)

    meta = dataset.get("meta_story", {})
    if composed.title.strip():
        meta["title"] = composed.title.strip()
    if composed.tagline.strip():
        meta["tagline"] = composed.tagline.strip()

    has_map = bool((dataset.get("geo_map") or {}).get("clusters"))
    corpus = _normalize_quote(material)
    dropped = {"quotes": 0}

    rendered = {
        region: _render_blocks(
            composed.blocks(region), region, resolve_image, corpus, dropped
        )
        for region in PROSE_REGIONS
        if has_map or region != "map"
    }
    # Always replace rather than merge: an empty region is a legitimate result,
    # so leaving the previous composition's paragraphs in place would silently
    # keep prose the composer deliberately dropped.
    for region in ("opening", "description", "conclusion"):
        if rendered.get(region):
            dataset[region] = rendered[region]
        else:
            dataset.pop(region, None)
    bodies = {
        section: rendered[section] for section in BODY_SECTIONS if rendered.get(section)
    }
    if bodies:
        dataset["section_bodies"] = bodies
    else:
        dataset.pop("section_bodies", None)

    headings = {
        slot: text.strip()
        for slot, text in (
            ("timeline", composed.section_headings.timeline),
            ("network", composed.section_headings.network),
            ("map", composed.section_headings.map or "" if has_map else ""),
            ("conclusion", composed.section_headings.conclusion),
        )
        if text and text.strip()
    }
    if headings:
        dataset["section_headings"] = headings

    chapters_by_id = {c.id: c for c in composed.chapters}
    for chapter in dataset.get("chapters") or []:
        entry = chapters_by_id.pop(chapter.get("id", ""), None)
        if entry is None:
            print(
                f"Warning: no composed texts for chapter '{chapter.get('id', '')}', "
                "keeping existing title"
            )
            continue
        headline = _strip_date_suffix(entry.headline)
        if headline:
            start = str(chapter.get("date_start", "")).split("-")[0]
            end = str(chapter.get("date_end", "")).split("-")[0]
            chapter["title"] = f"{headline} ({start}-{end})"
        if entry.lead_in.strip():
            chapter["lead_in"] = entry.lead_in.strip()
    for unknown_id in chapters_by_id:
        print(f"Warning: composed chapter '{unknown_id}' matches no chapter, ignored")

    _apply_network_circles(dataset, composed, verbose=verbose)
    _apply_map_composition(dataset, composed, verbose=verbose)

    if verbose:
        print(
            "  Prose stored: "
            + ", ".join(
                f"{region}: {len(blocks)}"
                for region, blocks in rendered.items()
                if blocks
            )
        )
        if dropped["quotes"]:
            print(f"  Dropped {dropped['quotes']} unverifiable quote(s)")


# ============================================================================
# CAST MAINTENANCE
#
# Not part of composing — used by remove_person.py to cascade a person's
# deletion through the stories they appear in. Purely deterministic.
# ============================================================================


def prune_network(network: Dict[str, Any], removed_ids: set) -> Dict[str, Any]:
    """Remove people from the social network, returning a new graph.

    The graph is *pruned* rather than re-derived from the ego networks, so
    Phase 5b review edits (added/modified ties) on the surviving links are
    preserved. Secondary nodes that no longer bridge >= 2 main people are
    dropped, mirroring the invariant of the derivation.
    """
    nodes = network.get("nodes") or []
    links = [
        link
        for link in network.get("links") or []
        if link.get("source") not in removed_ids
        and link.get("target") not in removed_ids
    ]

    degree: Dict[str, int] = {}
    for link in links:
        for nid in (link.get("source"), link.get("target")):
            degree[nid] = degree.get(nid, 0) + 1

    dropped_secondaries = set()
    kept_nodes = []
    for node in nodes:
        if node.get("id") in removed_ids:
            continue
        if node.get("type") == "secondary" and degree.get(node.get("id"), 0) < 2:
            dropped_secondaries.add(node.get("id"))
            continue
        kept_nodes.append(node)

    links = [
        link
        for link in links
        if link.get("source") not in dropped_secondaries
        and link.get("target") not in dropped_secondaries
    ]

    result = dict(network)
    result["nodes"] = kept_nodes
    result["links"] = links
    return result


def remove_people_from_story(
    dataset: Dict[str, Any],
    person_ids: List[str],
    verbose: bool = False,
) -> None:
    """Cascade a person removal through a meta story (mutates in place).

    Touches the cast, the subtopics, the chapters' events, the network and the
    map. The prose is left alone — it may still name the removed person, which
    is why callers are told to recompose the story afterwards.
    """
    removed = set(person_ids)
    if not removed:
        return

    meta = dataset.get("meta_story", {})
    meta["person_ids"] = [
        pid for pid in meta.get("person_ids", []) if pid not in removed
    ]

    kept_subtopics = []
    for sub in dataset.get("subtopics") or []:
        sub["person_ids"] = [
            pid for pid in sub.get("person_ids") or [] if pid not in removed
        ]
        if sub["person_ids"]:
            kept_subtopics.append(sub)
        else:
            print(f"Note: subtopic '{sub.get('id', '')}' emptied, dropped")
    dataset["subtopics"] = kept_subtopics

    for chapter in dataset.get("chapters") or []:
        chapter["person_events"] = [
            event
            for event in chapter.get("person_events") or []
            if event.get("person_id") not in removed
        ]
        if not chapter["person_events"] and not chapter.get("historical_context"):
            print(f"Warning: chapter '{chapter.get('id', '')}' has no events left")

    if dataset.get("social_network"):
        dataset["social_network"] = prune_network(dataset["social_network"], removed)

    # Map section: drop the removed people's events; clusters emptied by that
    # lose their narration stop too. Scores go slightly stale, which is fine —
    # re-run the map pipeline (meta_story_map_narration.py) for a fresh
    # derivation.
    geo_map = dataset.get("geo_map")
    if isinstance(geo_map, dict):
        kept_clusters = []
        for cluster in geo_map.get("clusters") or []:
            cluster["events"] = [
                event
                for event in cluster.get("events") or []
                if event.get("person_id") not in removed
            ]
            if cluster["events"]:
                kept_clusters.append(cluster)
            else:
                print(f"Note: map stop '{cluster.get('key', '')}' emptied, dropped")
        geo_map["clusters"] = kept_clusters
        narration = geo_map.get("narration")
        if isinstance(narration, dict):
            kept_keys = {c.get("key") for c in kept_clusters}
            narration["stops"] = [
                stop
                for stop in narration.get("stops") or []
                if stop.get("key") in kept_keys
            ]

    if verbose:
        print(f"  Removed from story: {', '.join(sorted(removed))}")


# ============================================================================
# ORCHESTRATION
# ============================================================================


def compose_meta_story_dataset(
    dataset: Dict[str, Any],
    registry: Dict[str, Any],
    client: OpenAI,
    model: str = COMPOSER_DEFAULT_MODEL,
    reasoning_effort: str = DEFAULT_REASONING_EFFORT,
    verbose: bool = False,
) -> Optional[Dict[str, Any]]:
    """Run the composer over a meta story dataset.

    Returns the composed dataset (a new dict; the input is never mutated), or
    ``None`` when the call fails — callers keep the original dataset, which
    makes the composer safe as a non-fatal pipeline phase.
    """
    working = copy.deepcopy(dataset)

    wikipedia_context = build_story_wikipedia_context(working, registry)
    image_candidates = collect_image_candidates(working, registry)

    composed = run_composition(
        working,
        registry,
        wikipedia_context,
        image_candidates,
        client,
        model,
        reasoning_effort,
        verbose=verbose,
    )
    if composed is None:
        return None

    material = "\n".join(
        [
            build_story_brief(working, registry),
            build_historical_context(working),
            wikipedia_context,
        ]
    )
    apply_composition(
        working,
        composed,
        image_candidates=image_candidates,
        material=material,
        verbose=verbose,
    )

    if verbose:
        slots = collect_prose_slots(composed)
        captions = collect_caption_slots(composed)
        overlaps = rank_slot_overlaps(slots, captions)
        if overlaps:
            print("  Most similar sentence pairs:")
            for slot_a, slot_b, sent_a, _sent_b, score in overlaps[:3]:
                print(
                    f"    {score:.2f} [{slot_a}] ~ [{slot_b}]: {_truncate(sent_a, 70)}"
                )
        abstract = find_abstract_slots(slots)
        if abstract:
            print(
                "  Slots with too few concrete anchors: "
                + ", ".join(f"{slot_id} ({n})" for slot_id, n in abstract)
            )
        interface = find_interface_references(slots)
        if interface:
            print(
                "  Slots describing the page instead of the history: "
                + ", ".join(f'{slot_id} ("{phrase}")' for slot_id, phrase in interface)
            )

    now = datetime.now().astimezone().isoformat()
    working["composition"] = {
        "model": model,
        "composed_at": now,
        "throughline": composed.throughline,
    }
    working.get("meta_story", {})["lastUpdated"] = now
    return working


# ============================================================================
# STANDALONE CLI
# ============================================================================


def load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return cast(Optional[Dict[str, Any]], json.load(f))


def _preview_blocks(label: str, blocks: Optional[List[Dict[str, Any]]]) -> None:
    if not blocks:
        return
    kinds = ", ".join(block.get("type", "?") for block in blocks)
    print(f"    {label}: {kinds}")
    for block in blocks:
        if block.get("type") == "paragraph":
            print(f"      {_truncate(block.get('text', ''), 120)}")


def compose_and_save(
    story_id: str,
    registry: Dict[str, Any],
    client: OpenAI,
    model: str,
    dry_run: bool,
    translate_langs: List[str],
    verbose: bool,
) -> bool:
    """Compose one existing meta story file, then sync registry + translations."""
    path = META_STORIES_DIR / f"{story_id}.json"
    dataset = load_json(path)
    if dataset is None:
        print(f"Error: meta story not found: {path}")
        return False

    composed = compose_meta_story_dataset(
        dataset, registry, client, model=model, verbose=verbose
    )
    if composed is None:
        print(f"Error: composition failed for '{story_id}', file left unchanged")
        return False

    meta = composed.get("meta_story", {})
    print(f"  Title: {meta.get('title', '')} — {meta.get('tagline', '')}")

    if dry_run:
        print(f"  Dry run: not writing {path.name}")
        headings = composed.get("section_headings") or {}
        _preview_blocks("opening", composed.get("opening"))
        _preview_blocks("description", composed.get("description"))
        for section, blocks in (composed.get("section_bodies") or {}).items():
            _preview_blocks(f"{headings.get(section, section)} body", blocks)
        _preview_blocks(
            headings.get("conclusion", "conclusion"), composed.get("conclusion")
        )
        for chapter in composed.get("chapters") or []:
            print(f"    Chapter: {chapter.get('title', '')}")
            if chapter.get("lead_in"):
                print(f"      Lead-in: {chapter['lead_in']}")
        narration = (composed.get("social_network") or {}).get("narration") or {}
        for circle in narration.get("circles") or []:
            print(
                f"    Circle: \"{circle.get('title', '')}\" — "
                f"{', '.join(circle.get('member_ids') or [])}"
            )
        return True

    with open(path, "w", encoding="utf-8") as f:
        json.dump(composed, f, indent=2, ensure_ascii=False)
    print(f"  Saved {path}")

    # Keep the registry entry (title/tagline/person_count) in sync. Imported
    # lazily: generate_meta_story imports this module for the composer phase.
    from generate_meta_story import update_meta_stories_registry

    update_meta_stories_registry(story_id, composed, verbose=verbose)

    # Composition changed English prose, so translations are stale by
    # fingerprint; refresh them right away (non-fatal, like the pipeline).
    for lang in translate_langs:
        from translate_meta_story import translate_meta_story_data

        print(f"  Translating '{story_id}' to '{lang}'...")
        try:
            if not translate_meta_story_data(
                story_id, lang, client, model=model, force=True, verbose=verbose
            ):
                print(f"  WARNING: translation to '{lang}' failed")
        except Exception as e:
            print(f"  WARNING: translation to '{lang}' failed: {e}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compose a meta story's narrative top-down (story composer agent)"
    )
    parser.add_argument(
        "story_id", nargs="?", help="Meta story ID (e.g., 'computing_pioneers')"
    )
    parser.add_argument("--all", action="store_true", help="Compose all meta stories")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the composed story without writing files",
    )
    parser.add_argument(
        "--model",
        default=COMPOSER_DEFAULT_MODEL,
        help=f"OpenAI model (default: {COMPOSER_DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--skip-translate",
        action="store_true",
        help="Skip re-translation after composing",
    )
    parser.add_argument(
        "--translate-langs",
        default="de",
        help="Comma-separated language codes to re-translate (default: de)",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    args = parser.parse_args()

    if not args.all and not args.story_id:
        parser.error("provide a story_id or --all")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY environment variable not set")
        return 1
    client = OpenAI(api_key=api_key)

    registry = load_json(REGISTER_PATH)
    if registry is None:
        print(f"Error: registry not found: {REGISTER_PATH}")
        return 1

    if args.all:
        registry_data = load_json(DATA_DIR / "meta_stories.json") or {}
        story_ids = [
            e["id"] for e in registry_data.get("meta_stories", []) if e.get("id")
        ]
    else:
        story_ids = [args.story_id]

    translate_langs = (
        []
        if args.skip_translate or args.dry_run
        else [c.strip() for c in args.translate_langs.split(",") if c.strip()]
    )

    failures = 0
    for story_id in story_ids:
        print(f"Composing meta story '{story_id}'...")
        if not compose_and_save(
            story_id,
            registry,
            client,
            model=args.model,
            dry_run=args.dry_run,
            translate_langs=translate_langs,
            verbose=args.verbose,
        ):
            failures += 1

    if failures:
        print(f"\n{failures} meta story composition(s) failed")
        return 1
    print("\nComposition complete")
    if not args.dry_run:
        print('Remember: npx prettier --write "data/meta_stories/**/*.json"')
    return 0


if __name__ == "__main__":
    sys.exit(main())
