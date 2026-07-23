#!/usr/bin/env python3
"""Story composer agent (Phase 8) — top-down composition of a meta story.

Every text in a meta story is written bottom-up by an earlier phase that only
sees its own slice: the description and conclusion are planned before any
event is selected (Phase 1), theme connections are judged per batch (Phase 3),
and the network narration only sees the graph (Phase 6). Nothing ever reads
the *assembled* story. This module adds that missing final step: a composer
that reviews the whole dataset from the top down — including focused
Wikipedia excerpts for every main person — and writes one coherent,
journalistic narrative around the timeline, the network, and the map.

The composer works in two AI calls:

1. **Curation** — reads the assembled story and decides on a *throughline*
   (the arc that anchors all prose) and, exceptionally, which clearly
   disconnected people to drop from the story. Exclusions are applied
   deterministically with hard guardrails (at most ~25% of the cast, never
   below ``MIN_REMAINING_PEOPLE`` people) and cascade through ``person_ids``,
   subtopics, chapter events, the social network, and the map. The network is
   *pruned* (not re-derived), so Phase 5b review edits on surviving ties are
   kept.
2. **Composition** — writes the story's full prose in one voice, guided by
   the throughline and grounded in the source material: title, tagline, an
   ``opening`` cold-open scene, the description, story-specific
   ``section_headings`` (now including the map), the per-section standfirst
   intros, free-form **``section_bodies``** (flexible sequences of
   paragraph / image / quote blocks rendered between each section's heading
   and its interactive component), chapter headlines plus lead-ins, subtopic
   texts, sparse refinements of event theme connections, the network
   narration — where the composer may now **reorganize the circles** (merge,
   split, reorder, or discard clusters via explicit ``member_ids``) — the
   map narration — where it may likewise **reorder and discard stops** — and
   the conclusion.

Everything the model returns is applied deterministically and defensively:

- Images are only ever *selected by key* from the people's own story slides
  (``collect_image_candidates``) and copied verbatim — the model cannot
  introduce a URL. A shared budget (``MAX_IMAGES_PER_STORY``) covers the
  opening and all body images, and no image is used twice.
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

Both calls operate on a working copy; the original dataset is returned
unchanged if anything fails, so the composer is safe to run as a non-fatal
pipeline phase. Provenance (model, throughline, exclusions) is stamped into a
top-level ``composition`` block.

Standalone usage (recompose an existing meta story):

    python scripts/compose_meta_story.py computing_pioneers --verbose
    python scripts/compose_meta_story.py --all --dry-run
    python scripts/compose_meta_story.py computing_pioneers --no-exclusions
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

from config import DEFAULT_MODEL, DEFAULT_REASONING_EFFORT
from meta_story_map import MIN_MAP_CLUSTERS
from meta_story_network import derive_clusters
from meta_story_network_review import build_wikipedia_context

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
REGISTER_PATH = DATA_DIR / "persons.json"
PEOPLE_DIR = DATA_DIR / "people"
META_STORIES_DIR = DATA_DIR / "meta_stories"

# Exclusion guardrails: the composer may only drop clearly disconnected
# people, never gut the cast.
MIN_REMAINING_PEOPLE = 3
MAX_EXCLUSION_FRACTION = 0.25

# Image guardrails: the composer only ever *selects* images by key from the
# people's own story slides; URLs are copied deterministically, so it can
# never invent one. The budget is shared by the opening and all body images.
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


# ============================================================================
# PYDANTIC MODELS
# ============================================================================


class ExclusionDecision(BaseModel):
    """A person the composer wants to drop from the story."""

    person_id: str = Field(description="Person ID exactly as listed in the cast")
    reason: str = Field(
        description="1-2 sentence justification grounded in the cast sheet "
        "(few story events, no ties to the rest of the cast, forced fit)"
    )


class CurationResult(BaseModel):
    """First composer call: the story's throughline and optional exclusions."""

    throughline: str = Field(
        description="2-4 sentences naming the story's central arc — the "
        "tension or transformation that every text should serve. Written for "
        "the composer itself, not for display."
    )
    excluded_people: List[ExclusionDecision] = Field(
        description="People to drop because they stay disconnected from the "
        "story. Exclusion is EXCEPTIONAL — an empty list is the normal outcome."
    )


class StoryBlock(BaseModel):
    """One building block of a section body (flexible layout)."""

    type: Literal["paragraph", "image", "quote"] = Field(
        description="Block kind: narrative paragraph, image (selected by "
        "key), or a verbatim quote from the source material"
    )
    text: Optional[str] = Field(
        default=None,
        description="Paragraph or quote text; null for image blocks. Quote "
        "text must appear VERBATIM in the provided material or it is dropped.",
    )
    image_key: Optional[str] = Field(
        default=None,
        description="For image blocks: key copied verbatim from the image "
        "candidate list; null otherwise.",
    )
    image_layout: Optional[Literal["left", "right", "full"]] = Field(
        default=None,
        description="For image blocks: 'left'/'right' floats the figure "
        "beside the following text on wide screens, 'full' spans the column.",
    )
    attribution: Optional[str] = Field(
        default=None,
        description="For quote blocks: who said/wrote it and where (short); "
        "null otherwise.",
    )


class ComposedSectionBodies(BaseModel):
    """Free-form narrative blocks rendered between each section's heading and
    its interactive component."""

    timeline: List[StoryBlock] = Field(
        description="Body of the chronology section (before the timeline)"
    )
    network: List[StoryBlock] = Field(
        description="Body of the social-network section (before the graph)"
    )
    map: List[StoryBlock] = Field(
        description="Body of the places section (before the map); empty when "
        "the story has no map"
    )
    conclusion: List[StoryBlock] = Field(
        description="Body of the closing section (before the closing "
        "statement); may be empty"
    )


class ComposedChapter(BaseModel):
    """Rewritten texts for one timeline chapter."""

    id: str = Field(description="Chapter ID, copied verbatim from the input")
    headline: str = Field(
        description="Era headline (2-5 words) WITHOUT any date range — the "
        "date range is appended automatically. One unified concept, not a list."
    )
    lead_in: str = Field(
        description="1-2 short sentences shown with the chapter on the "
        "timeline, stating what was at stake in this era. Written about the "
        "era, never addressed to the reader. No name-dropping lists, no "
        "dates (they are shown next to it)."
    )


class ComposedSubtopic(BaseModel):
    """Rewritten texts for one thematic subtopic."""

    id: str = Field(description="Subtopic ID, copied verbatim from the input")
    title: str = Field(description="Subtopic title (2-5 words)")
    description: str = Field(description="1-2 sentence subtopic narrative")


class ThemeConnectionRefinement(BaseModel):
    """A rewritten theme connection for a single timeline event."""

    event_key: str = Field(
        description="The event's key exactly as given (person_id:event_index)"
    )
    text: str = Field(
        description="Rewritten theme connection (1-2 sentences), keeping all "
        "factual content of the original"
    )


class ComposedCircle(BaseModel):
    """One circle of the composer's own network organization."""

    member_ids: List[str] = Field(
        description="Person ids of the MAIN people in this circle (at least "
        "two, each person in at most one circle), copied verbatim from the "
        "cast. The circles replace the current organization, in this order."
    )
    title: str = Field(
        description="Short evocative headline (2-5 words), not a list of names"
    )
    text: str = Field(
        description="2-4 sentence story text weaving the circle's ties "
        "together, grounded strictly in the tie descriptions and the "
        "Wikipedia material"
    )


class ComposedMapStop(BaseModel):
    """A kept map stop with its rewritten narration, in presentation order."""

    key: str = Field(description="The stop's key, copied verbatim from the input")
    title: str = Field(
        description="Short evocative headline (2-5 words) for this place"
    )
    text: str = Field(
        description="2-4 sentence story text about what happened at this "
        "place, grounded strictly in the listed events"
    )


class DiscardedMapStop(BaseModel):
    """A map stop the composer wants to drop from the story."""

    key: str = Field(description="The stop's key, copied verbatim from the input")
    reason: str = Field(
        description="Why this place adds nothing to the story (accidental "
        "grouping, incidental location)"
    )


class ComposedOpening(BaseModel):
    """The story's cold open — a specific scene instead of a panorama."""

    text: str = Field(
        description="1-3 short paragraphs (separated by a blank line) that "
        "open the story inside ONE specific documented moment or with ONE "
        "specific person from the material: a dated act, a concrete scene, "
        "an object changing hands. Never a panoramic overview, never a "
        "thesis statement."
    )
    image_key: Optional[str] = Field(
        default=None,
        description="Key of an image candidate that belongs to the opening "
        "scene (copied verbatim from the candidate list), or null if none "
        "genuinely fits.",
    )


class ComposedSectionHeadings(BaseModel):
    """Story-specific headings replacing the generic section labels."""

    timeline: str = Field(
        description="Heading for the chronology section (2-6 words), specific "
        "to this story — never a generic label like 'Timeline' or 'Chapters'"
    )
    network: str = Field(
        description="Heading for the social-network section (2-6 words), "
        "specific to this story — never 'Connections' or 'Network'"
    )
    map: Optional[str] = Field(
        default=None,
        description="Heading for the places section (2-6 words), specific to "
        "this story — never 'Places' or 'Map'. Null when the story has no map.",
    )
    conclusion: str = Field(
        description="Heading for the closing section (2-6 words), specific "
        "to this story — never 'Conclusion' or 'Legacy'"
    )


class CompositionResult(BaseModel):
    """Second composer call: the story's full prose, written in one voice."""

    title: str = Field(description="Story title (2-5 words)")
    tagline: str = Field(description="Short hook (3-10 words)")
    opening: ComposedOpening = Field(
        description="The cold open shown before the description"
    )
    description: str = Field(
        description="Narrative (2-3 paragraphs) that widens the frame after "
        "the opening scene, introducing the topic like a feature article — "
        "no meta-references such as 'this collection', and no repetition of "
        "the opening scene"
    )
    section_headings: ComposedSectionHeadings = Field(
        description="Story-specific headings for the main sections"
    )
    timeline_intro: str = Field(
        description="1-3 sentence standfirst shown right under the "
        "chronology heading. Written about the history itself — never "
        "addressed to the reader, never a meta-reference to the timeline."
    )
    network_intro: str = Field(
        description="1-3 sentence standfirst for the network section, "
        "consistent with the timeline texts. No individual names, no preview "
        "of the circles, no reading guide."
    )
    map_intro: Optional[str] = Field(
        default=None,
        description="1-3 sentence standfirst for the places section, or null "
        "when the story has no map.",
    )
    section_bodies: ComposedSectionBodies = Field(
        description="The story's narrative depth: free-form blocks per "
        "section, rendered between the standfirst and the section's "
        "interactive component"
    )
    chapters: List[ComposedChapter] = Field(
        description="One entry per chapter, same order as given"
    )
    subtopics: List[ComposedSubtopic] = Field(
        description="One entry per subtopic, same order as given"
    )
    theme_connection_refinements: List[ThemeConnectionRefinement] = Field(
        description="SPARSE list of rewritten event theme connections — only "
        "where the existing text clashes with the story's voice or repeats "
        "itself. Most events should NOT appear here."
    )
    circles: List[ComposedCircle] = Field(
        description="The composer's own organization of the network into "
        "circles (replacing the current one), in presentation order"
    )
    map_stops: List[ComposedMapStop] = Field(
        description="The kept map stops in presentation order, each with "
        "rewritten narration; empty when the story has no map"
    )
    discarded_map_stops: List[DiscardedMapStop] = Field(
        description="Map stops to drop because their place adds nothing to "
        "the story; an empty list is the normal outcome"
    )
    conclusion: str = Field(
        description="Closing statement (2-3 sentences) echoing the throughline"
    )


# ============================================================================
# STORY BRIEF (shared input for both calls)
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
    """Deterministic per-person connectivity summary used by the curation call."""
    index = _person_index(registry)
    person_ids = dataset.get("meta_story", {}).get("person_ids", [])

    subtopic_of = {}
    for sub in dataset.get("subtopics") or []:
        for pid in sub.get("person_ids") or []:
            subtopic_of[pid] = sub.get("title", sub.get("id", ""))

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
            f"    subtopic: {subtopic_of.get(pid, 'NONE')}; "
            f"story events: {event_count.get(pid, 0)}; "
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


def build_story_brief(dataset: Dict[str, Any], registry: Dict[str, Any]) -> str:
    """Render the assembled story as text for the composer prompts."""
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
        f"TITLE: {meta.get('title', '')}",
        f"TAGLINE: {meta.get('tagline', '')}",
        f"DESCRIPTION (draft):\n{meta.get('description', '')}",
        "",
        "CAST:",
        build_cast_sheet(dataset, registry),
        "",
        "SUBTOPICS:",
    ]
    for sub in dataset.get("subtopics") or []:
        members = ", ".join(person_name(pid) for pid in sub.get("person_ids") or [])
        parts.append(
            f"- [{sub.get('id', '')}] {sub.get('title', '')}: "
            f"{sub.get('description', '')} (members: {members})"
        )

    parts.append("")
    parts.append("CHAPTERS (timeline):")
    for chapter in dataset.get("chapters") or []:
        parts.append(
            f"Chapter [{chapter.get('id', '')}] \"{chapter.get('title', '')}\" "
            f"({chapter.get('date_start', '')}-{chapter.get('date_end', '')})"
        )
        for ctx in chapter.get("historical_context") or []:
            parts.append(
                f"  (context) {ctx.get('title', '')}: {ctx.get('description', '')}"
            )
        for event in chapter.get("person_events") or []:
            key = f"{event.get('person_id', '')}:{event.get('event_index', '')}"
            parts.append(
                f"  [key={key}] {event.get('event_date', '')} — "
                f"{person_name(event.get('person_id', ''))}: "
                f"{event.get('event_title', '')}\n"
                f"      theme connection (draft): {event.get('theme_connection', '')}"
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
        narration = network.get("narration") or {}
        if narration.get("intro"):
            parts.append(f"NETWORK INTRO (draft): {narration['intro']}")
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
        if map_narration.get("intro"):
            parts.append(f"MAP INTRO (draft): {map_narration['intro']}")

    parts.append("")
    parts.append(f"CONCLUSION (draft):\n{dataset.get('conclusion', '')}")
    return "\n".join(parts)


# ============================================================================
# CALL 1: CURATION
# ============================================================================


def run_curation(
    dataset: Dict[str, Any],
    registry: Dict[str, Any],
    wikipedia_context: str,
    client: OpenAI,
    model: str,
    reasoning_effort: str,
    allow_exclusions: bool,
    verbose: bool = False,
) -> Optional[CurationResult]:
    """Ask the composer for the story's throughline and optional exclusions."""
    brief = build_story_brief(dataset, registry)

    exclusion_rules = (
        """
2. EXCLUSIONS — decide whether any person stays DISCONNECTED from the story
   and should be dropped. A person is disconnected when several of these hold:
   - very few story events compared to the rest of the cast
   - no direct ties to other main people in the network
   - their subtopic membership reads as forced, or their events sit apart
     from every chapter's core narrative
   Exclusion is EXCEPTIONAL: an empty list is the normal outcome. Never
   exclude someone merely for being less famous, and never propose more than
   a quarter of the cast. Each exclusion needs a concrete justification
   grounded in the cast sheet."""
        if allow_exclusions
        else """
2. EXCLUSIONS — exclusions are disabled for this run. Return an empty list."""
    )

    prompt = f"""You are reviewing an ASSEMBLED meta story from the top down. All of its
texts were written bottom-up by earlier steps that never saw the whole; your
job is to prepare its final composition.

{brief}

BACKGROUND MATERIAL (Wikipedia excerpts for the main people):

{wikipedia_context}

YOUR TWO DECISIONS:

1. THROUGHLINE — write 2-4 sentences naming this story's central arc: the
   tension, question, or transformation that the material actually supports.
   It will anchor every rewritten text, so make it specific to this cast and
   these events, not a generic statement about the field.
{exclusion_rules}
"""

    try:
        response = client.responses.parse(
            model=model,
            reasoning=cast(Any, {"effort": reasoning_effort}),
            input=[
                {
                    "role": "system",
                    "content": "You are a story editor for a biographical "
                    "visualization. You judge only from the material provided "
                    "and never invent facts.",
                },
                {"role": "user", "content": prompt},
            ],
            text_format=CurationResult,
        )
        result = response.output_parsed
        if result is None:
            print("Warning: curation returned no parsed result")
            return None
        if verbose:
            print(f"  Throughline: {result.throughline}")
            for exc in result.excluded_people:
                print(f"  Proposed exclusion: {exc.person_id} — {exc.reason}")
        return result
    except Exception as e:
        print(f"Warning: curation call failed: {e}")
        return None


def limit_exclusions(
    dataset: Dict[str, Any],
    proposed: List[ExclusionDecision],
    verbose: bool = False,
) -> List[ExclusionDecision]:
    """Apply the exclusion guardrails, returning the accepted subset."""
    person_ids = list(dataset.get("meta_story", {}).get("person_ids", []))
    valid = []
    seen = set()
    for exc in proposed:
        if exc.person_id in seen:
            continue
        seen.add(exc.person_id)
        if exc.person_id in person_ids:
            valid.append(exc)
        else:
            print(f"Warning: ignoring exclusion of unknown person: {exc.person_id}")

    cast_size = len(person_ids)
    allowed = min(
        int(cast_size * MAX_EXCLUSION_FRACTION),
        max(cast_size - MIN_REMAINING_PEOPLE, 0),
    )
    if len(valid) > allowed:
        for exc in valid[allowed:]:
            print(
                f"Warning: exclusion of {exc.person_id} dropped by guardrail "
                f"(at most {allowed} of {cast_size} people may be excluded)"
            )
        valid = valid[:allowed]
    if verbose and valid:
        print(f"  Accepted {len(valid)} exclusion(s) of {cast_size} people")
    return valid


# ============================================================================
# EXCLUSION CASCADE (deterministic)
# ============================================================================


def prune_network(network: Dict[str, Any], removed_ids: set) -> Dict[str, Any]:
    """Remove excluded main people from the social network in place.

    The graph is *pruned* rather than re-derived from the ego networks, so
    Phase 5b review edits (added/modified ties) on the surviving links are
    preserved. Secondary nodes that no longer bridge >= 2 main people are
    dropped, mirroring the invariant of the derivation.
    """
    nodes = network.get("nodes") or []
    links = network.get("links") or []

    links = [
        link
        for link in links
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


def apply_exclusions(
    dataset: Dict[str, Any],
    exclusions: List[ExclusionDecision],
    verbose: bool = False,
) -> None:
    """Cascade accepted exclusions through the dataset (mutates in place)."""
    removed = {exc.person_id for exc in exclusions}
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
            print(
                f"Note: subtopic '{sub.get('id', '')}' emptied by exclusions, dropped"
            )
    dataset["subtopics"] = kept_subtopics

    for chapter in dataset.get("chapters") or []:
        chapter["person_events"] = [
            event
            for event in chapter.get("person_events") or []
            if event.get("person_id") not in removed
        ]
        if not chapter["person_events"] and not chapter.get("historical_context"):
            print(
                f"Warning: chapter '{chapter.get('id', '')}' has no events left "
                "after exclusions"
            )

    if dataset.get("social_network"):
        dataset["social_network"] = prune_network(dataset["social_network"], removed)

    # Map section: drop excluded people's events; clusters emptied by that
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
                print(
                    f"Note: map stop '{cluster.get('key', '')}' emptied by "
                    "exclusions, dropped"
                )
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
        names = ", ".join(sorted(removed))
        print(f"  Excluded from story: {names}")


# ============================================================================
# CALL 2: COMPOSITION
# ============================================================================


def run_composition(
    dataset: Dict[str, Any],
    registry: Dict[str, Any],
    throughline: str,
    wikipedia_context: str,
    image_candidates: Dict[str, Dict[str, Any]],
    client: OpenAI,
    model: str,
    reasoning_effort: str,
    verbose: bool = False,
) -> Optional[CompositionResult]:
    """Ask the composer to write the story's full prose in one voice."""
    brief = build_story_brief(dataset, registry)
    images_brief = build_image_candidates_brief(image_candidates)
    has_map = bool((dataset.get("geo_map") or {}).get("clusters"))

    map_instructions = (
        """
- map_intro: 1-3 sentence standfirst for the places section.
- map_stops: you own the places section's dramaturgy. Keep the stops that
  carry the story, ORDER them so the section reads as a journey (chronology
  is the default, but a deliberate dramaturgical order is allowed), and give
  each kept stop an evocative 2-5 word title plus 2-4 sentences grounded
  strictly in its listed events. Copy keys EXACTLY.
- discarded_map_stops: drop a stop when its geographic grouping is accidental
  or the place is incidental to what happened there (a publisher's city, a
  conference venue). Give a concrete reason per discard. At least three
  stops must remain."""
        if has_map
        else """
- map_intro / map_stops / discarded_map_stops: this story has no map section
  — return null / empty lists."""
    )

    prompt = f"""Compose the final narrative for this meta story. All existing texts are
bottom-up drafts written without seeing the whole; you see everything — the
assembled story AND background material from the people's Wikipedia articles —
and write the story top-down, in one coherent voice, anchored to the
throughline. You are writing a piece of narrative journalism, not a set of
captions: the finished page must read as ONE researched story that happens to
carry interactive components, not as a wrapper around them.

THROUGHLINE (your anchor, not for display):
{throughline}

{brief}

BACKGROUND MATERIAL (Wikipedia excerpts for the main people — use it to
deepen and verify the narrative; every claim you write must be supported by
this material or the story data above):

{wikipedia_context}

{images_brief}

WRITE THE FOLLOWING (all display-facing, general educated audience):

- title (2-5 words) and tagline (3-10 words): refine the drafts or replace
  them if the throughline calls for it.
- opening: the story's cold open, 1-3 short paragraphs. Begin INSIDE the
  material — one specific documented moment, act, or person drawn from the
  events above: a date, a place, a thing being made or said. Choose the
  anchor that best crystallizes the throughline; different stories should
  open differently (a scene, a person at work, an object, a decision). No
  panorama, no thesis, no scene-setting clichés ("It was a time of...").
  If an image candidate shows this exact moment or its protagonist, set its
  key as image_key.
- description: 2-3 paragraphs that widen the frame after the opening scene,
  introducing the topic like a feature article. Do not retell the opening.
  NEVER use meta-references ("This collection...", "These figures...");
  write directly about the topic.
- section_headings: one heading each for the chronology, network,{" map," if has_map else ""}
  and closing sections (2-6 words). They must read like chapter titles of one
  essay — specific to this story, carrying its arc forward. Generic labels
  ("Timeline", "Chapters", "Connections", "Network", "Places", "Map",
  "Conclusion", "Legacy") are forbidden.
- timeline_intro / network_intro: 1-3 sentence standfirsts shown right under
  the respective section heading. Write about the history itself, never
  about the interface ("The chronology begins...", "This story follows..."
  are meta-references and are forbidden).
- section_bodies: THE STORY'S NARRATIVE DEPTH. For each section, a sequence
  of blocks rendered between the standfirst and the section's interactive
  component. This is where the real storytelling happens — write it like the
  running text of a long-form magazine feature:
  - timeline: 2-4 blocks that tell the era's arc as a story — its documented
    turning points, reversals, and what changed hands between the people —
    WITHOUT enumerating the chapters (the timeline itself shows them).
  - network: 1-3 blocks on how the relationships actually carried the ideas:
    who read whom, who hired whom, where the chains broke. No preview of the
    circles.
  - map: 1-3 blocks on how geography shaped the story{"" if has_map else " (empty — no map)"}.
  - conclusion: 0-2 blocks deepening the close (optional).
  Block types and layout options:
  - paragraph: flowing narrative prose (3-6 sentences).
  - image: an image candidate selected by key, with image_layout 'left' or
    'right' (floats beside the following text) or 'full' (spans the column).
    Place an image next to the paragraph it illustrates.
  - quote: a short VERBATIM quotation from the material above (the event
    details, tie descriptions, or Wikipedia excerpts), with an attribution
    naming who wrote or said it. Quotes are checked verbatim against the
    material — a paraphrase or invented quote is dropped. Use at most one
    or two quotes in the whole story, only when the words themselves carry
    weight.
- chapters: for each chapter (same order, ids verbatim) a headline of 2-5
  words WITHOUT any date range (it is appended automatically), one unified
  concept, no lists; and a lead_in of 1-2 short sentences stating what was at
  stake in that era. Chapter headlines must build on one another so the
  sequence reads like a story's chapters.
- subtopics: for each subtopic (same order, ids verbatim) a title and a 1-2
  sentence description that names the thread its members share.
- theme_connection_refinements: rewrite an event's theme connection ONLY
  where the draft clashes with the story's voice, repeats a neighbouring
  event, or buries its point. Keep every factual claim of the draft; never
  add facts. Reference events by their [key=...] value. Most events should
  not appear here — an empty list is acceptable.
- circles: you own the network section's dramaturgy. Organize the cast into
  3-6 circles that best tell the relationship story — you may keep, merge,
  split, reorder, or discard the current circles. Each circle lists the
  member_ids of its MAIN people (ids verbatim from the cast; at least two
  members; each person in at most one circle; a person whose ties are too
  thin may be left out of all circles). For each circle: an evocative 2-5
  word title (not a list of names) and 2-4 sentences of flowing prose that
  weave the members' documented ties into a miniature story. Ground every
  claim in the tie descriptions and the Wikipedia material; refer to people
  naturally ("Babbage" on second mention). Order the circles so the section
  reads as one narrative.{map_instructions}
- conclusion: 2-3 sentences that close the arc the throughline names.

HARD RULES (journalistic standard):
- Stick to the facts in the material above; never invent events, dates,
  relationships, scenes, thoughts, or claims. If the material does not
  support a detail, leave it out.
- Quotes must be verbatim from the material, with attribution. Never
  fabricate or embellish a quotation.
- Copy ids, keys, and image keys EXACTLY; if in doubt about an image key,
  use null/omit the block. Never construct or modify a key.
- Use AT MOST {MAX_IMAGES_PER_STORY} images in the whole story (opening and
  all body images together); never reuse an image. Prefer artifacts, scenes,
  and documents over portraits.
- Vivid but factual tone, matching a work of narrative journalism.
- NEVER address the reader. This is a data story, not a tutorial or a guided
  tour: no "you"/"your"/"we"/"us", no imperatives aimed at the audience
  ("Follow...", "Trace...", "Explore...", "Imagine...", "See how..."), no
  references to scrolling, clicking, or the timeline/graph/map as an
  interface. Write every text in the third person, about the people and
  their era — narrate the history instead of guiding a visitor through it.
"""

    try:
        response = client.responses.parse(
            model=model,
            reasoning=cast(Any, {"effort": reasoning_effort}),
            input=[
                {
                    "role": "system",
                    "content": "You are a long-form journalist composing a "
                    "coherent narrative from verified biographical material. "
                    "You research, refine, and connect; you never invent "
                    "facts, scenes, or quotations.",
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
            print(f"  Composed title: {result.title}")
            print(f"  Opening: {result.opening.text[:90]}...")
            print(
                "  Section headings: "
                f"{result.section_headings.timeline} / "
                f"{result.section_headings.network} / "
                f"{result.section_headings.map or '-'} / "
                f"{result.section_headings.conclusion}"
            )
            print(f"  Chapter headlines: {[c.headline for c in result.chapters]}")
            body_counts = {
                slot: len(getattr(result.section_bodies, slot))
                for slot in ("timeline", "network", "map", "conclusion")
            }
            print(f"  Section body blocks: {body_counts}")
            print(f"  Circles: {[c.title for c in result.circles]}")
            print(f"  Map stops: {[s.key for s in result.map_stops]}")
            if result.discarded_map_stops:
                print(
                    "  Discarded stops: "
                    f"{[d.key for d in result.discarded_map_stops]}"
                )
            print(
                f"  Theme connection refinements: "
                f"{len(result.theme_connection_refinements)}"
            )
        return result
    except Exception as e:
        print(f"Warning: composition call failed: {e}")
        return None


def _strip_date_suffix(headline: str) -> str:
    """Remove a trailing "(YYYY-YYYY)" the model may have added anyway."""
    return re.sub(r"\s*\(\d{4}\s*[-–]\s*\d{4}\)\s*$", "", headline).strip()


# Typographic characters normalized away before the verbatim-quote check, so
# a straightened apostrophe or dash never fails an otherwise genuine quote.
_QUOTE_TRANS = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "“": '"',
        "”": '"',
        "–": "-",
        "—": "-",
    }
)


def _normalize_quote(text: str) -> str:
    return re.sub(r"\s+", " ", text.translate(_QUOTE_TRANS)).strip().lower()


def _apply_section_bodies(
    dataset: Dict[str, Any],
    composed: CompositionResult,
    resolve_image: Any,
    material: str,
    verbose: bool = False,
) -> None:
    """Store the composed section bodies, verifying quotes and images."""
    corpus = _normalize_quote(material)
    has_map = bool((dataset.get("geo_map") or {}).get("clusters"))
    bodies: Dict[str, List[Dict[str, Any]]] = {}
    dropped_quotes = 0

    for slot in ("timeline", "network", "map", "conclusion"):
        if slot == "map" and not has_map:
            continue
        blocks_out: List[Dict[str, Any]] = []
        for block in getattr(composed.section_bodies, slot) or []:
            if block.type == "paragraph":
                text = (block.text or "").strip()
                if text:
                    blocks_out.append({"type": "paragraph", "text": text})
            elif block.type == "image":
                image = resolve_image(block.image_key, f"{slot} body")
                if image is not None:
                    layout = (
                        block.image_layout
                        if block.image_layout in ("left", "right", "full")
                        else "full"
                    )
                    blocks_out.append(
                        {"type": "image", "image": image, "layout": layout}
                    )
            elif block.type == "quote":
                text = (block.text or "").strip().strip('"“”')
                if not text:
                    continue
                if _normalize_quote(text) not in corpus:
                    print(
                        f"Warning: quote in {slot} body is not verbatim in the "
                        f"material, dropped: \"{_truncate(text, 80)}\""
                    )
                    dropped_quotes += 1
                    continue
                entry: Dict[str, Any] = {"type": "quote", "text": text}
                attribution = (block.attribution or "").strip()
                if attribution:
                    entry["attribution"] = attribution
                blocks_out.append(entry)
        if blocks_out:
            bodies[slot] = blocks_out

    if bodies:
        dataset["section_bodies"] = bodies
        # Section images are superseded by body image blocks; leftovers from a
        # previous composition would render twice.
        dataset.pop("section_images", None)
    if verbose:
        print(
            "  Section bodies: "
            + ", ".join(f"{slot}: {len(blocks)}" for slot, blocks in bodies.items())
        )
        if dropped_quotes:
            print(f"  Dropped {dropped_quotes} unverifiable quote(s)")


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

    def set_intro(narration: Dict[str, Any]) -> None:
        intro = composed.network_intro.strip()
        if intro:
            narration["intro"] = intro

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
                main_nodes[pid].get("birth_year")
                if main_nodes[pid].get("birth_year") is not None
                else 10**9,
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
        narration = network.get("narration")
        if isinstance(narration, dict):
            set_intro(narration)
        return

    left_out = sorted(linked_mains - used)
    if left_out and verbose:
        print(f"  People outside all circles: {', '.join(left_out)}")

    narration = {
        "intro": (network.get("narration") or {}).get("intro", ""),
        "circles": circles,
    }
    set_intro(narration)
    network["narration"] = narration
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
    stops = composed.map_stops or []
    discards = composed.discarded_map_stops or []
    if not isinstance(geo_map, dict) or not geo_map.get("clusters"):
        if stops or discards:
            print("Warning: composed map stops but story has no map section, ignored")
        return

    clusters = geo_map["clusters"]
    by_key = {c.get("key"): c for c in clusters}
    previous = geo_map.get("narration") or {}
    prev_stop_by_key = {
        s.get("key"): s for s in previous.get("stops") or [] if s.get("key")
    }

    kept: List[Dict[str, Any]] = []  # clusters in presentation order
    stop_by_key: Dict[str, Dict[str, Any]] = {}
    seen: set = set()
    for stop in stops:
        cluster = by_key.get(stop.key)
        if cluster is None:
            print(f"Warning: composed map stop '{stop.key}' matches no stop, ignored")
            continue
        if stop.key in seen:
            continue
        seen.add(stop.key)
        kept.append(cluster)
        stop_by_key[stop.key] = {
            "key": stop.key,
            "title": stop.title.strip(),
            "text": stop.text.strip(),
        }

    discard_reasons: Dict[str, str] = {}
    for discard in discards:
        if discard.key not in by_key:
            print(f"Warning: discarded map stop '{discard.key}' is unknown, ignored")
        elif discard.key not in seen:
            discard_reasons[discard.key] = discard.reason

    # Stops the model neither kept nor discarded stay, with their previous
    # narration when they have one.
    for cluster in clusters:
        key = cluster.get("key")
        if key in seen or key in discard_reasons:
            continue
        print(f"Warning: map stop '{key}' not mentioned by composer, kept")
        seen.add(key)
        kept.append(cluster)
        if key in prev_stop_by_key:
            stop_by_key[key] = prev_stop_by_key[key]

    # Guardrail: never drop below the minimum stop count; re-keep by score.
    min_kept = min(MIN_MAP_CLUSTERS, len(clusters))
    if len(kept) < min_kept:
        rekeep = sorted(
            (by_key[key] for key in discard_reasons),
            key=lambda c: -(c.get("score") or 0),
        )
        for cluster in rekeep:
            if len(kept) >= min_kept:
                break
            key = cluster.get("key")
            print(
                f"Note: re-keeping composer-discarded stop '{key}' to preserve "
                f"a minimum of {min_kept} map stops"
            )
            del discard_reasons[key]
            kept.append(cluster)
            if key in prev_stop_by_key:
                stop_by_key[key] = prev_stop_by_key[key]

    geo_map["clusters"] = kept
    narration: Dict[str, Any] = {
        "intro": (composed.map_intro or "").strip() or previous.get("intro", ""),
        "stops": [
            stop_by_key[c.get("key")] for c in kept if c.get("key") in stop_by_key
        ],
    }
    geo_map["narration"] = narration

    if discard_reasons:
        discarded_list = geo_map.get("discarded") or []
        for key, reason in discard_reasons.items():
            discarded_list.append(
                {
                    "key": key,
                    "label": by_key[key].get("label", ""),
                    "reason": f"composer: {reason}",
                }
            )
        geo_map["discarded"] = discarded_list
    if verbose:
        print(
            f"  Map: {len(kept)} stop(s) in composed order"
            + (f", {len(discard_reasons)} discarded" if discard_reasons else "")
        )


def apply_composition(
    dataset: Dict[str, Any],
    composed: CompositionResult,
    image_candidates: Optional[Dict[str, Dict[str, Any]]] = None,
    material: str = "",
    verbose: bool = False,
) -> None:
    """Overlay the composed texts onto the dataset (mutates in place).

    Structure is authoritative on the dataset side: chapters, subtopics,
    circles, and map stops are matched by id/key, unknown entries are ignored
    with a warning, and missing entries keep their existing texts. Images are
    resolved from the candidate pool only — an unknown key is dropped with a
    warning, so a hallucinated URL can never enter the data. Quote blocks
    must appear verbatim in ``material`` or they are dropped.
    """
    candidates = image_candidates or {}
    used_image_keys: set = set()

    def resolve_image(key: Optional[str], slot: str) -> Optional[Dict[str, Any]]:
        if not key:
            return None
        candidate = candidates.get(key)
        if candidate is None:
            print(f"Warning: unknown image key '{key}' for {slot}, dropped")
            return None
        if key in used_image_keys:
            print(f"Warning: image '{key}' reused for {slot}, dropped")
            return None
        if len(used_image_keys) >= MAX_IMAGES_PER_STORY:
            print(f"Warning: image budget exhausted, '{key}' for {slot} dropped")
            return None
        used_image_keys.add(key)
        return image_record(candidate)

    meta = dataset.get("meta_story", {})
    if composed.title.strip():
        meta["title"] = composed.title.strip()
    if composed.tagline.strip():
        meta["tagline"] = composed.tagline.strip()
    if composed.opening.text.strip():
        dataset["opening"] = {
            "text": composed.opening.text.strip(),
            "image": resolve_image(composed.opening.image_key, "opening"),
        }
    if composed.description.strip():
        meta["description"] = composed.description.strip()
    has_map = bool((dataset.get("geo_map") or {}).get("clusters"))
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
    if composed.timeline_intro.strip():
        dataset["timeline_intro"] = composed.timeline_intro.strip()
    if composed.conclusion.strip():
        dataset["conclusion"] = composed.conclusion.strip()

    _apply_section_bodies(dataset, composed, resolve_image, material, verbose=verbose)

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

    subtopics_by_id = {s.id: s for s in composed.subtopics}
    for sub in dataset.get("subtopics") or []:
        sub_entry = subtopics_by_id.pop(sub.get("id", ""), None)
        if sub_entry is None:
            print(
                f"Warning: no composed texts for subtopic '{sub.get('id', '')}', "
                "keeping existing texts"
            )
            continue
        if sub_entry.title.strip():
            sub["title"] = sub_entry.title.strip()
        if sub_entry.description.strip():
            sub["description"] = sub_entry.description.strip()
    for unknown_id in subtopics_by_id:
        print(f"Warning: composed subtopic '{unknown_id}' matches no subtopic, ignored")

    refinements = {
        r.event_key: r.text.strip() for r in composed.theme_connection_refinements
    }
    applied = 0
    for chapter in dataset.get("chapters") or []:
        for event in chapter.get("person_events") or []:
            key = f"{event.get('person_id', '')}:{event.get('event_index', '')}"
            text = refinements.pop(key, None)
            if text:
                event["theme_connection"] = text
                applied += 1
    for unknown_key in refinements:
        print(f"Warning: refinement for unknown event '{unknown_key}' ignored")
    if verbose and applied:
        print(f"  Applied {applied} theme connection refinement(s)")

    _apply_network_circles(dataset, composed, verbose=verbose)
    _apply_map_composition(dataset, composed, verbose=verbose)


# ============================================================================
# ORCHESTRATION
# ============================================================================


def compose_meta_story_dataset(
    dataset: Dict[str, Any],
    registry: Dict[str, Any],
    client: OpenAI,
    model: str = DEFAULT_MODEL,
    reasoning_effort: str = DEFAULT_REASONING_EFFORT,
    allow_exclusions: bool = True,
    verbose: bool = False,
) -> Optional[Dict[str, Any]]:
    """Run the full composer over a meta story dataset.

    Returns the composed dataset (a new dict; the input is never mutated), or
    ``None`` when either AI call fails — callers keep the original dataset,
    which makes the composer safe as a non-fatal pipeline phase.
    """
    working = copy.deepcopy(dataset)

    wikipedia_context = build_story_wikipedia_context(working, registry)
    curation = run_curation(
        working,
        registry,
        wikipedia_context,
        client,
        model,
        reasoning_effort,
        allow_exclusions,
        verbose=verbose,
    )
    if curation is None:
        return None

    exclusions = (
        limit_exclusions(working, curation.excluded_people, verbose=verbose)
        if allow_exclusions
        else []
    )
    apply_exclusions(working, exclusions, verbose=verbose)
    if exclusions:
        # The excluded people's articles must not ground any prose.
        wikipedia_context = build_story_wikipedia_context(working, registry)

    # Candidates are collected AFTER exclusions, so a dropped person's images
    # can never be selected.
    image_candidates = collect_image_candidates(working, registry)

    composed = run_composition(
        working,
        registry,
        curation.throughline,
        wikipedia_context,
        image_candidates,
        client,
        model,
        reasoning_effort,
        verbose=verbose,
    )
    if composed is None:
        return None

    # The quote-verification corpus is exactly what the model was shown.
    material = build_story_brief(working, registry) + "\n" + wikipedia_context
    apply_composition(
        working,
        composed,
        image_candidates=image_candidates,
        material=material,
        verbose=verbose,
    )

    now = datetime.now().astimezone().isoformat()
    working["composition"] = {
        "model": model,
        "composed_at": now,
        "throughline": curation.throughline,
        "excluded_people": [
            {"person_id": exc.person_id, "reason": exc.reason} for exc in exclusions
        ],
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


def compose_and_save(
    story_id: str,
    registry: Dict[str, Any],
    client: OpenAI,
    model: str,
    allow_exclusions: bool,
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
        dataset,
        registry,
        client,
        model=model,
        allow_exclusions=allow_exclusions,
        verbose=verbose,
    )
    if composed is None:
        print(f"Error: composition failed for '{story_id}', file left unchanged")
        return False

    meta = composed.get("meta_story", {})
    print(f"  Title: {meta.get('title', '')} — {meta.get('tagline', '')}")
    excluded = (composed.get("composition") or {}).get("excluded_people") or []
    for exc in excluded:
        print(f"  Excluded: {exc['person_id']} — {exc['reason']}")

    if dry_run:
        print(f"  Dry run: not writing {path.name}")
        opening = composed.get("opening") or {}
        if opening.get("text"):
            print(f"    Opening: {opening['text'][:160]}...")
            if opening.get("image"):
                print(f"      Opening image: {opening['image'].get('caption', '')}")
        headings = composed.get("section_headings") or {}
        if headings:
            print(
                "    Section headings: "
                f"{headings.get('timeline', '-')} / "
                f"{headings.get('network', '-')} / "
                f"{headings.get('map', '-')} / "
                f"{headings.get('conclusion', '-')}"
            )
        for slot, blocks in (composed.get("section_bodies") or {}).items():
            kinds = ", ".join(block.get("type", "?") for block in blocks)
            print(f"    {slot} body: {kinds}")
        for chapter in composed.get("chapters") or []:
            print(f"    Chapter: {chapter.get('title', '')}")
            if chapter.get("lead_in"):
                print(f"      Lead-in: {chapter['lead_in']}")
        print(f"    Timeline intro: {composed.get('timeline_intro', '')}")
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
        "--no-exclusions",
        action="store_true",
        help="Never drop people from the story (text composition only)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show composed headlines/exclusions without writing files",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"OpenAI model (default: {DEFAULT_MODEL})",
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
            allow_exclusions=not args.no_exclusions,
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
