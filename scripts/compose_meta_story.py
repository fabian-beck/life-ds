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

TWO LAYERS, NOT ONE
-------------------

A meta story page carries two kinds of text, and conflating them is what made
earlier versions of this composer read as a wrapper around its own components:

- The **caption layer** is bound one-to-one to something the reader is looking
  at: a chapter of the timeline, an event on it, a circle in the graph, a stop
  on the map. Its job is to say what *that item* is — concretely, briefly,
  factually.
- The **article layer** is the continuous prose the reader meets *between* the
  components: the opening, the description, the section bodies, the
  conclusion. Its job is **context** — the world these
  lives happened inside, the conditions that produced the sequence, what
  changed between one section and the next, what it cost. Not the items.

When one call writes both layers from one brief of items, it writes the items
twice: measured on the previously composed stories, article paragraphs
overlapped the caption texts sitting right below them at a Dice score of 0.53,
roughly twice the paraphrase band seen *within* the article layer. So the
layers are now written by separate calls, and the article call is shown the
finished caption layer as text that is **already on the page**.

The composer works in four AI calls:

1. **Curation** — reads the assembled story and decides on a *throughline*
   (the arc that anchors all prose) and, exceptionally, which clearly
   disconnected people to drop from the story. Exclusions are applied
   deterministically with hard guardrails (at most ~25% of the cast, never
   below ``MIN_REMAINING_PEOPLE`` people) and cascade through ``person_ids``,
   subtopics, chapter events, the social network, and the map. The network is
   *pruned* (not re-derived), so Phase 5b review edits on surviving ties are
   kept.
2. **Caption layer** (``run_component_narration``) — the texts bound to items:
   chapter headlines plus lead-ins, subtopic texts, sparse refinements of
   event theme connections, the network circles — which this call may
   **reorganize** (merge, split, reorder, or discard clusters via explicit
   ``member_ids``) — and the map stops, which it may likewise reorder and
   discard. Nothing here states the story's thesis; that belongs to call 3.
3. **Article layer** (``run_article``) — the running prose, written with the
   caption layer in front of it and explicitly forbidden to retell it: title,
   tagline, an ``opening`` cold-open scene, the description, story-specific
   ``section_headings``, free-form **``section_bodies``** (paragraph / image
   / quote blocks rendered between each section's heading and its interactive
   component — a section carries no other prose), and the conclusion. Two tests govern it — delete every component and the article
   must still read as one continuous essay; and no paragraph of it may read
   as a description of the thing below it.
4. **Redundancy pass** — a focused editing call that rewrites article slots
   repeating one another *or* repeating the caption layer. The caption texts
   are passed as fixed reference slots: they can be repeated *against*, never
   rewritten. Revisions are patched back into the composition result before it
   is applied, so they pass through the same defensive application path as
   everything else. Non-fatal, and opt out with ``--skip-redundancy-pass``.

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
- Prose revisions from the redundancy pass are addressed by slot id and may
  only replace the text of a slot that already exists; an unknown id is
  ignored with a warning, so the pass can rewrite but never add or remove.

All calls operate on a working copy; the original dataset is returned
unchanged if either required call (curation, caption layer, article layer)
fails, so the composer is safe to run as a non-fatal pipeline phase.
Provenance (model, throughline, exclusions) is stamped into a top-level
``composition`` block.

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

from config import DEFAULT_MODEL, DEFAULT_REASONING_EFFORT, enable_utf8_console
from meta_story_map import MIN_MAP_CLUSTERS
from meta_story_network import derive_clusters
from meta_story_network_review import build_wikipedia_context

enable_utf8_console()

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
    """Free-form narrative blocks rendered between each section's heading
    and its interactive component.

    These carry CONTEXT, never a retelling of the component below them: the
    conditions, causes and consequences the timeline, graph and map cannot
    show. An empty list is a valid answer when a section has no context to add.
    """

    timeline: List[StoryBlock] = Field(
        description="Body of the chronology section (2-3 blocks): what the "
        "world outside these lives was doing, and why the sequence took the "
        "shape it did. Never a recap of the events on the timeline."
    )
    network: List[StoryBlock] = Field(
        description="Body of the social-network section (1-2 blocks): what "
        "kind of network this was — the institutions, media and channels that "
        "carried the ties. Never a walk through who knew whom."
    )
    map: List[StoryBlock] = Field(
        description="Body of the places section (1-2 blocks): why the story "
        "is distributed the way it is. Never a tour of the stops. Empty when "
        "the story has no map."
    )
    conclusion: List[StoryBlock] = Field(
        description="Body of the closing section (0-1 blocks): the afterlife "
        "of this history. May be empty."
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


class ComponentNarration(BaseModel):
    """Second composer call: the CAPTION LAYER — every text bound to an item.

    Chapter headlines and lead-ins, subtopic texts, event theme connections,
    the network circles, and the map stops. Each of these sits directly on the
    thing it describes, so each says what *that* thing is. None of them states
    the story's argument — the article layer (call 3) owns that, and is shown
    this layer's output so it does not repeat it.
    """

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


class StoryArticle(BaseModel):
    """Third composer call: the ARTICLE LAYER — the running prose between the
    components.

    Its subject is not the items on the page but the world they happened in.
    It is written with the finished caption layer in view and must not retell
    any of it.
    """

    title: str = Field(description="Story title (2-5 words)")
    tagline: str = Field(description="Short hook (3-10 words)")
    opening: ComposedOpening = Field(
        description="The cold open shown before the description"
    )
    description: str = Field(
        description="Narrative (2-3 paragraphs) that widens the frame after "
        "the opening scene, introducing the topic like a feature article. It "
        "owns the STAKES: what was at issue, why it was hard, what world "
        "these people worked in. No meta-references such as 'this "
        "collection', no repetition of the opening scene, and no reaching "
        "for the outcome or legacy (the conclusion owns that)."
    )
    section_headings: ComposedSectionHeadings = Field(
        description="Story-specific headings for the main sections"
    )
    section_bodies: ComposedSectionBodies = Field(
        description="The article's context blocks per section, rendered "
        "between the section heading and the section's interactive component"
    )
    conclusion: str = Field(
        description="Closing statement (2-3 sentences) naming what this "
        "history left behind — what it settled, what it did not. Not a "
        "summary of the sections above, not the description restated."
    )


class CompositionResult(ComponentNarration, StoryArticle):
    """The two call results merged — the shape ``apply_composition`` consumes.

    Kept as one model so the application path, the prose-slot addressing and
    the redundancy pass all stay unchanged by the call split.
    """

    @classmethod
    def merge(
        cls, captions: ComponentNarration, article: StoryArticle
    ) -> "CompositionResult":
        return cls.model_validate({**captions.model_dump(), **article.model_dump()})


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


def build_context_notes(dataset: Dict[str, Any], registry: Dict[str, Any]) -> str:
    """Render the story's world-level material for the article call.

    Deliberately *not* the story brief. The brief is a list of items — events,
    ties, stops — and an article call given a list of items writes the list
    back out in nicer prose. This renders the material the article is actually
    for: the span it covers, the threads running through it, and the chapters'
    ``historical_context`` entries, which are the only place in the dataset
    where the world outside these lives is described.
    """
    meta = dataset.get("meta_story", {})
    parts = [
        f"STORY: {meta.get('title', '')} — {meta.get('tagline', '')}",
        f"SPAN: {meta.get('date_range_start', '')} to "
        f"{meta.get('date_range_end', '')}",
    ]

    subtopics = dataset.get("subtopics") or []
    if subtopics:
        parts.append("")
        parts.append("THREADS running through the story:")
        for sub in subtopics:
            parts.append(f"- {sub.get('title', '')}: {sub.get('description', '')}")

    contexts = [
        (chapter, ctx)
        for chapter in dataset.get("chapters") or []
        for ctx in chapter.get("historical_context") or []
    ]
    if contexts:
        parts.append("")
        parts.append(
            "HISTORICAL CONTEXT recorded for this story, by era — the "
            "circumstances around the events rather than the events "
            "themselves:"
        )
        for chapter, ctx in contexts:
            span = (
                f"{chapter.get('date_start', '')}-{chapter.get('date_end', '')}"
                if chapter.get("date_start")
                else ""
            )
            parts.append(
                f"- [{span}] {ctx.get('title', '')}: {ctx.get('description', '')}"
            )

    parts.append("")
    parts.append("THE ARTICLE'S CAST (for reference — do not profile them):")
    parts.append(build_cast_sheet(dataset, registry))
    return "\n".join(parts)


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
# CALL 2: THE CAPTION LAYER
# ============================================================================


def run_component_narration(
    dataset: Dict[str, Any],
    registry: Dict[str, Any],
    throughline: str,
    wikipedia_context: str,
    client: OpenAI,
    model: str,
    reasoning_effort: str,
    verbose: bool = False,
) -> Optional[ComponentNarration]:
    """Write the texts bound to the story's items (call 2 of 4).

    Deliberately narrow: every field here labels something the reader is
    looking at, so the whole call can be told one thing — describe the item,
    never the story. The article layer is written afterwards against this
    output, which is what keeps the two from saying the same thing twice.
    """
    brief = build_story_brief(dataset, registry)
    has_map = bool((dataset.get("geo_map") or {}).get("clusters"))

    map_instructions = (
        """
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
- map_stops / discarded_map_stops: this story has no map section — return
  empty lists."""
    )

    prompt = f"""Write the CAPTION LAYER of this meta story: every text that is attached to a
single item the reader is looking at.

A meta story page has two layers of text. This call writes the first one.
Each text you write sits directly on the thing it describes — a chapter band
of a timeline, one event on it, a circle of people in a graph, a marker on a
map. A separate article runs between the components and carries the story's
argument, its context, and its conclusions. That article is written after
you, and it is written to AVOID whatever you say here. So say the concrete
thing, and only the concrete thing.

THROUGHLINE (background, so your captions point the same way; never state it):
{throughline}

{brief}

BACKGROUND MATERIAL (Wikipedia excerpts for the main people — use it to
deepen and verify; every claim must be supported by this material or the
story data above):

{wikipedia_context}

HOW A CAPTION BEHAVES:
- It describes ITS item: what happened, who was involved, what changed.
  Specific nouns, dated facts, named people.
- It does NOT generalize to the era, the story, or the significance of it
  all. "This marked the beginning of the computer age" is the article's
  sentence, not yours. Stop at what is documented.
- It does not refer to the other components, to the reader, or to the
  interface. No "you", no "we", no imperatives ("Follow...", "Trace...",
  "Explore..."), no mention of scrolling, clicking, timeline, graph or map.
- It is short. These are labels on a visualization, not paragraphs.
- Neighbouring captions must not repeat each other: two chapter lead-ins
  making the same point, or a circle text restating a tie already described,
  is the failure mode to avoid.

WRITE THE FOLLOWING:

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

HARD RULES:
- Stick to the facts in the material above; never invent events, dates,
  relationships, scenes, thoughts, or claims.
- Copy ids and keys EXACTLY. Never construct or modify one.
- Vivid but factual tone. Third person, about the people and their era.
"""

    try:
        response = client.responses.parse(
            model=model,
            reasoning=cast(Any, {"effort": reasoning_effort}),
            input=[
                {
                    "role": "system",
                    "content": "You write the caption layer of a data story: "
                    "short, concrete texts attached to individual items. You "
                    "describe what is there and never editorialize; you never "
                    "invent facts.",
                },
                {"role": "user", "content": prompt},
            ],
            text_format=ComponentNarration,
        )
        result = response.output_parsed
        if result is None:
            print("Warning: caption layer returned no parsed result")
            return None
        if verbose:
            print(f"  Chapter headlines: {[c.headline for c in result.chapters]}")
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
        print(f"Warning: caption layer call failed: {e}")
        return None


# ============================================================================
# CALL 3: THE ARTICLE LAYER
# ============================================================================
#
# The article call is shown the finished caption layer verbatim, under a
# heading that says it is already on the page. This is the whole point of the
# split: "do not repeat the components" is unenforceable when the model has
# only the raw item data and has to guess what the captions will say — it
# writes the items again, in better prose. Given the actual caption texts, the
# instruction becomes checkable, and the article has to go looking for
# something else to say. That something else is context.


def render_component_layer(
    dataset: Dict[str, Any],
    registry: Dict[str, Any],
    captions: ComponentNarration,
) -> str:
    """Render the caption layer as the text that is already on the page.

    Built from the call-2 result rather than the dataset, because that is what
    the reader will actually see; chapters and stops are matched back to the
    dataset only to label them with their dates and places.
    """
    index = _person_index(registry)

    def person_name(pid: str) -> str:
        return str(index.get(pid, {}).get("name", pid)).replace("_", " ")

    lines = [
        "ALREADY ON THE PAGE — THE CAPTION LAYER.",
        "",
        "These texts are finished and will be printed on the components "
        "themselves, interleaved with the article you are about to write. "
        "Every fact, turning point and relationship below has therefore "
        "ALREADY been told to the reader. Do not tell any of it again.",
        "",
        "On the timeline, per chapter:",
    ]
    chapter_dates = {
        c.get("id"): (c.get("date_start", ""), c.get("date_end", ""))
        for c in dataset.get("chapters") or []
    }
    for chapter in captions.chapters:
        start, end = chapter_dates.get(chapter.id, ("", ""))
        span = f" ({start}-{end})" if start else ""
        lines.append(f'- "{chapter.headline}"{span}: {chapter.lead_in}')

    events = [
        (e.get("event_date", ""), person_name(e.get("person_id", "")), e)
        for chapter in dataset.get("chapters") or []
        for e in chapter.get("person_events") or []
    ]
    refined = {r.event_key: r.text for r in captions.theme_connection_refinements}
    if events:
        lines.append("")
        lines.append(
            f"On the timeline, {len(events)} events, each with its own caption. "
            "The reader gets all of them:"
        )
        for date, name, event in events:
            key = f"{event.get('person_id', '')}:{event.get('event_index', '')}"
            caption = refined.get(key) or event.get("theme_connection", "")
            lines.append(
                f"- {date} — {name}: {event.get('event_title', '')}. "
                f"{_truncate(caption, 200)}"
            )

    if captions.circles:
        lines.append("")
        lines.append("In the network graph, one card per circle of people:")
        for circle in captions.circles:
            members = ", ".join(person_name(pid) for pid in circle.member_ids)
            lines.append(f'- "{circle.title}" ({members}): {circle.text}')

    if captions.map_stops:
        stop_labels = {
            c.get("key"): c.get("label", "")
            for c in (dataset.get("geo_map") or {}).get("clusters") or []
        }
        lines.append("")
        lines.append("On the map, one card per stop:")
        for stop in captions.map_stops:
            label = stop_labels.get(stop.key, stop.key)
            lines.append(f'- "{stop.title}" ({label}): {stop.text}')

    return "\n".join(lines)


def run_article(
    dataset: Dict[str, Any],
    registry: Dict[str, Any],
    throughline: str,
    component_layer: str,
    wikipedia_context: str,
    image_candidates: Dict[str, Dict[str, Any]],
    client: OpenAI,
    model: str,
    reasoning_effort: str,
    verbose: bool = False,
) -> Optional[StoryArticle]:
    """Write the running prose between the components (call 3 of 4)."""
    images_brief = build_image_candidates_brief(image_candidates)
    has_map = bool((dataset.get("geo_map") or {}).get("clusters"))
    context_notes = build_context_notes(dataset, registry)

    prompt = f"""Write the ARTICLE of this meta story — the running prose a reader meets
between the interactive components.

The page is built from three components: a timeline of dated events, a graph
of who was connected to whom, and a map of the places involved. Each of them
is already captioned, and those captions are reproduced below. They tell the
reader WHAT happened, WHO was connected, and WHERE.

Your article is not a wrapper around them and not a summary of them. It is
the other half of the page: the WORLD these lives happened inside. The
conditions that made this sequence possible or necessary. What the era had
not solved. What it cost, who paid, and what changed as a result. The things
a dated event list, a graph and a set of map pins structurally cannot show.

THROUGHLINE (your anchor, not for display):
{throughline}

{component_layer}

CONTEXT MATERIAL — this is your subject matter. The captions above own the
events; these own the world around them:

{context_notes}

BACKGROUND MATERIAL (Wikipedia excerpts for the main people — the article's
factual ground; every claim you write must be supported by this material or
by the captions above):

{wikipedia_context}

{images_brief}

TWO TESTS YOUR ARTICLE MUST PASS. Apply them to every paragraph before you
finish:

1. THE REMOVAL TEST. Delete all three components from the page. What remains
   — opening, description, bodies, conclusion, read in that order — must
   still be one continuous, coherent essay that could be published on its
   own. If a paragraph becomes meaningless without the component beside it,
   it was a caption, not an article paragraph.
2. THE CAPTION TEST. No paragraph may read as a description of the thing
   directly below it. If a paragraph in the places section walks through the
   places, or a paragraph in the network section walks through who knew whom,
   it has failed and must be replaced.

THERE ARE TWO WAYS TO FAIL THIS, AND YOU MUST AVOID BOTH.

FAILURE 1 — THE RECAP. A previous version produced: "Philadelphia, Annapolis,
New York City, and western Pennsylvania mark the republic's changing centres
of power. Congress appointed Washington to command an army in Philadelphia;
the same city later hosted the convention that drafted a new Constitution.
Annapolis helped launch the call for that convention..." — a list of the map's
own stops, one clause each, telling the reader what the cards beside it
already said. Every sentence there is on the page twice. If your sentences
each attach to a different item, you are writing a list, not an argument.

FAILURE 2 — THE ESCAPE INTO ABSTRACTION, which is the trap set by the fix for
the first. The same article, told not to recap, produced: "The geography
joined centers of coordination to territories subject to changing control" and
"Unlike correspondence or print, institutional ties could bind decisions to
resources and enforcement across distance." Not one proper noun, not one
checkable fact, nothing a reader can picture. This is worse than the recap: it
is unreadable, and it could be pasted into a story about any century.

CONCRETENESS IS NOT OPTIONAL. Context does not mean generality — it means
DIFFERENT SPECIFICS. Not this story's events, but the world's: the named law,
the institution and what it could not do, the market, the war being fought
elsewhere, the printer who refused the manuscript, the technology that did not
yet exist, the sum of money, the year something became illegal. Every
paragraph you write must contain specifics of that kind, named and checkable
from the material. A paragraph with no proper nouns has failed. If you cannot
find real context for a section, write FEWER paragraphs — an empty body beats
an abstract one.

WHAT EACH SLOT OWNS:

  slot            | owns                        | must NOT contain
  ----------------|-----------------------------|---------------------------
  opening         | ONE documented scene         | the thesis, the arc, any
                  | (a dated moment, an act)     | "and so began..." summary
  description     | the STAKES: what was at      | the opening's scene again,
                  | issue, why it was hard,      | the outcome or legacy
                  | what world these people      | (the conclusion owns that)
                  | worked in                    |
  section bodies  | CONTEXT: causes, conditions, | any retelling of the
                  | constraints, consequences,   | captions; a walk through
                  | the connective tissue        | the chapters, circles or
                  | between the sections         | stops; a list of names
  conclusion      | the CONSEQUENCE: what this   | the description's framing
                  | left behind, what it settled | again; a summary of the
                  | and what it did not          | sections just read

Each slot must ADVANCE the story. The throughline is your anchor but NOT the
content of every slot: state it outright AT MOST ONCE, in the slot that owns
it. A reader who has read the opening must learn something new from the
description, and again from each body, and from the conclusion.

WRITE THE FOLLOWING (all display-facing, general educated audience):

- title (2-5 words) and tagline (3-10 words): refine the drafts or replace
  them if the throughline calls for it.
- opening: the story's cold open, 1-3 short paragraphs. Begin INSIDE the
  material — one specific documented moment, act, or person: a date, a place,
  a thing being made or said. This is the ONE place the article may narrate
  an event in full, because it is the reader's way in. Choose the anchor that
  best crystallizes the throughline; different stories should open
  differently (a scene, a person at work, an object, a decision). No
  panorama, no thesis, no scene-setting clichés ("It was a time of..."). End
  inside the scene — do not close with a sentence explaining what it all
  meant. If an image candidate shows this exact moment or its protagonist,
  set its key as image_key.
- description: 2-3 paragraphs that widen the frame after the opening scene,
  introducing the topic like a feature article: the conditions these people
  worked under, the problem the era had not solved, what was genuinely at
  stake. Do not retell the opening and do not reach for the ending. NEVER use
  meta-references ("This collection...", "These figures..."); write directly
  about the topic.
- section_headings: one heading each for the chronology, network,{" map," if has_map else ""}
  and closing sections (2-6 words). They must read like chapter titles of one
  essay — specific to this story, carrying its arc forward. Generic labels
  ("Timeline", "Chapters", "Connections", "Network", "Places", "Map",
  "Conclusion", "Legacy") are forbidden.
- section_bodies: THE ARTICLE'S SUBSTANCE — the context blocks between each
  section heading and its component. A section carries no other prose, so the
  first block opens the section itself: no standfirst precedes it and nothing
  else introduces it. Write them as the running text of one long-form
  feature, continuous across the sections: each body picks up the argument
  where the previous section left it. Ground every paragraph in a
  specific condition, institution, constraint, or consequence — a paragraph
  that could sit in any story about any era is too general, and one that
  could sit in a caption belongs in a caption.
  - timeline (2-3 blocks): what the world outside these lives was
    doing — the wars, laws, markets, institutions and technologies that set
    the terms — and why the sequence took the shape it did. NOT what happened
    in it.
  - network (1-2 blocks): what KIND of network this was. What carried the
    ties — letters, journals, courts, laboratories, patronage, workshops,
    exile — and what those channels made possible or foreclosed. NOT who knew
    whom.
  - map (1-2 blocks): why this history is distributed the way it is — what
    concentrated people in some places, what moved them, what a place could
    offer that another could not.{"" if has_map else " (empty — this story has no map)"} NOT a
    tour of the stops.
  - conclusion (0-1 blocks): the afterlife — what happened to this world
    afterwards. May be empty.
  A section body may be EMPTY when the article genuinely has no context to
  add there. An empty body is much better than a paragraph of filler, and far
  better than an abstract one.
  Block types and layout options:
  - paragraph: flowing narrative prose (3-6 sentences).
  - image: an image candidate selected by key, with image_layout 'left' or
    'right' (floats beside the following text) or 'full' (spans the column).
    Place an image next to the paragraph it illustrates.
  - quote: a short VERBATIM quotation from the material above, with an
    attribution naming who wrote or said it. Quotes are checked verbatim — a
    paraphrase or invented quote is dropped. Use at most one or two in the
    whole story, only when the words themselves carry weight.
- conclusion: 2-3 sentences naming what this history left behind — what it
  settled, what it did not, what still follows from it. Not a summary of the
  sections above and not the description's framing restated at the end.

HARD RULES (journalistic standard):
- Stick to the facts in the material above; never invent events, dates,
  relationships, scenes, thoughts, or claims. If the material does not
  support a detail, leave it out.
- Do not retell the caption layer. Naming a person, place or event in passing
  as a fixed point ("by the time the Treaty was signed...") is fine;
  recounting it is not.
- Never buy your way out of that rule with vagueness. "Institutional ties
  could bind decisions to resources across distance" is not context, it is
  the absence of content. Name the institution.
- Quotes must be verbatim from the material, with attribution. Never
  fabricate or embellish a quotation.
- Copy image keys EXACTLY; if in doubt, omit the block. Never construct one.
- Use AT MOST {MAX_IMAGES_PER_STORY} images in the whole story (opening and
  all body images together); never reuse an image. Prefer artifacts, scenes,
  and documents over portraits.
- Vivid but factual tone, matching a work of narrative journalism.
- WRITE IT TO BE READ. This is a story, not a policy paper. Prefer concrete
  subjects doing things to abstract nouns in the subject position ("Parliament
  closed the port of Boston", not "the imposition of punitive measures
  affected commercial life"). Vary sentence length; let a short one land after
  a long one. Avoid stacked abstractions, nominalizations, and hedging
  clauses. If a sentence has to be read twice to be understood, rewrite it.
- NEVER address the reader. This is a data story, not a tutorial or a guided
  tour: no "you"/"your"/"we"/"us", no imperatives aimed at the audience
  ("Follow...", "Trace...", "Explore...", "Imagine...", "See how..."), no
  references to scrolling, clicking, or the timeline/graph/map as an
  interface. Write every text in the third person, about the people and
  their era — narrate the history instead of guiding a visitor through it.
- NEVER make a part of this page the subject of a sentence. "The chronology
  follows...", "The map sets...", "This section shows..." are all forbidden,
  in every slot. The subject is always the history, never its presentation.
"""

    try:
        response = client.responses.parse(
            model=model,
            reasoning=cast(Any, {"effort": reasoning_effort}),
            input=[
                {
                    "role": "system",
                    "content": "You are a long-form journalist writing the "
                    "connective essay of a data story. The story's items are "
                    "already captioned; your subject is the world around "
                    "them. You research, contextualize and conclude; you "
                    "never recap, and you never invent facts or quotations.",
                },
                {"role": "user", "content": prompt},
            ],
            text_format=StoryArticle,
        )
        result = response.output_parsed
        if result is None:
            print("Warning: article call returned no parsed result")
            return None
        if verbose:
            print(f"  Composed title: {result.title}")
            print(f"  Opening: {_truncate(result.opening.text, 90)}")
            print(
                "  Section headings: "
                f"{result.section_headings.timeline} / "
                f"{result.section_headings.network} / "
                f"{result.section_headings.map or '-'} / "
                f"{result.section_headings.conclusion}"
            )
            body_counts = {
                slot: len(getattr(result.section_bodies, slot))
                for slot in ("timeline", "network", "map", "conclusion")
            }
            print(f"  Section body blocks: {body_counts}")
        return result
    except Exception as e:
        print(f"Warning: article call failed: {e}")
        return None


# ============================================================================
# REDUNDANCY PASS
# ============================================================================
#
# Two kinds of repetition reach this pass, and the second is the larger one.
#
# Within the article, a call juggling a dozen prose objectives against a single
# throughline tends to restate that throughline in slot after slot, so the same
# thesis lands in the description, the section bodies and the conclusion. The slot contract in the article prompt is the primary fix; this
# pass is the check on it.
#
# Between the article and the captions, the page says the same thing twice in
# two different voices. Measured on the stories composed before the call split,
# article paragraphs matched the caption text sitting below them at a Dice
# score of 0.53 — twice the paraphrase band seen inside the article — and this
# pass could not see it, because it was only ever shown the article. The
# captions are now passed as FIXED reference slots: the pass reads them, may
# rewrite an article slot that repeats one, and can never rewrite a caption
# (their ids are not in the rewritable set, so a revision aimed at one is
# rejected by ``apply_prose_revisions`` like any unknown slot).
#
# In both cases a repeated claim cannot simply be dropped — the slot still has
# to say something — so it is rewritten by a call whose only job is
# de-duplication.


class ProseRevision(BaseModel):
    """A rewritten prose slot that had repeated another slot's point."""

    slot: str = Field(
        description="Slot id, copied EXACTLY from the list of slots given"
    )
    repeats: str = Field(
        description="The slot id this one was repeating, and in one short "
        "phrase the point they shared"
    )
    text: str = Field(
        description="The rewritten text for this slot, same length and voice "
        "as the original, carrying information no other slot carries. Only "
        "facts already present in the story's texts — never new claims."
    )


class RedundancyPassResult(BaseModel):
    """Third composer call: prose slots rewritten to remove repeated claims."""

    revisions: List[ProseRevision] = Field(
        description="Only the slots that genuinely repeated another slot. An "
        "empty list is a valid and good outcome."
    )


# Ordered by reading position: when two slots share a point, the LATER one is
# the one that gets rewritten, because the earlier one established it.
PROSE_SLOT_ORDER = (
    "opening",
    "description",
    "body:timeline",
    "body:network",
    "body:map",
    # The closing section's body is rendered above the closing statement.
    "body:conclusion",
    "conclusion",
)

# Each slot's role AND the mode it must not fall into. The prohibitions matter
# as much as the roles: a rewrite told only "don't repeat" will satisfy that by
# sliding into another failure — the first live run replaced a conclusion that
# echoed the description with one that enumerated the timeline instead.
PROSE_SLOT_ROLES = {
    "opening": (
        "the cold-open scene — ONE documented moment; never the thesis or "
        "an 'and so began' summary"
    ),
    "description": (
        "the stakes: what was at issue, why it was hard, what world these "
        "people worked in; never the outcome or legacy"
    ),
    "conclusion": (
        "the consequence: what this history left behind, what it settled and "
        "what it did not; never a summary or list of what came before"
    ),
    "body:timeline": (
        "context paragraph in the chronology section — the wars, laws, "
        "markets and institutions that set the terms, and why the sequence "
        "took the shape it did; never a recap of the events themselves"
    ),
    "body:network": (
        "context paragraph in the network section — what carried the ties "
        "(letters, journals, courts, laboratories, patronage) and what those "
        "channels made possible; never a walk through who knew whom"
    ),
    "body:map": (
        "context paragraph in the places section — what concentrated people "
        "in some places and moved them from others; never a tour of the stops"
    ),
    "body:conclusion": (
        "context paragraph in the closing section — the afterlife of this "
        "world; never a summary of the sections above"
    ),
}

# The caption layer's roles, for the fixed reference slots. These are never
# rewritten; they are shown so the pass can tell when an article slot is
# saying something the reader has already been given on a component.
CAPTION_SLOT_ROLES = {
    "chapter": "printed on the timeline as a chapter's own text",
    "circle": "printed in the network graph as a circle's own card",
    "stop": "printed on the map as a place's own card",
}

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_WORD = re.compile(r"[a-z][a-z'’-]+")

# Function words carry no topical signal; without them near-duplicate
# sentences and unrelated ones score alike.
_STOPWORDS = frozenset(
    """
    the a an and or but nor for yet so as at by from in into of off on onto out over to
    up with within without upon after before during since until while about against
    among around between through under above below across along
    is was are were be been being am has have had having do does did doing
    will would shall should can could may might must
    that this these those there here it its their his her him she he they them we us our
    you your i me my not no nor than then when where which who whom whose what why how
    all any both each few more most other some such only own same too very
    one two three first second new made make making made became become becomes
    also still just even much many
    """.split()
)


def _content_words(text: str) -> set:
    return {
        w for w in _WORD.findall(text.lower()) if w not in _STOPWORDS and len(w) > 2
    }


def collect_prose_slots(composed: CompositionResult) -> List[tuple]:
    """Return the rewritable prose slots as ``(slot_id, role, text)``.

    Slot ids are stable addresses into ``CompositionResult``: the top-level
    prose fields by name, and body paragraphs as ``body:{section}:{index}``
    where the index is the block's position in that section's block list (so
    image and quote blocks keep their positions and are never addressed).
    """
    slots: List[tuple] = []

    def add(slot_id: str, role_key: str, text: Optional[str]) -> None:
        if text and text.strip():
            slots.append((slot_id, PROSE_SLOT_ROLES[role_key], text.strip()))

    add("opening", "opening", composed.opening.text)
    add("description", "description", composed.description)
    for section in ("timeline", "network", "map", "conclusion"):
        for index, block in enumerate(getattr(composed.section_bodies, section) or []):
            if block.type == "paragraph":
                add(f"body:{section}:{index}", f"body:{section}", block.text)
    add("conclusion", "conclusion", composed.conclusion)

    order = {name: i for i, name in enumerate(PROSE_SLOT_ORDER)}
    return sorted(slots, key=lambda s: order.get(s[0].rsplit(":", 1)[0], 99))


def collect_caption_slots(composed: CompositionResult) -> List[tuple]:
    """Return the caption layer as fixed ``(slot_id, role, text)`` reference.

    These slot ids are deliberately NOT in the rewritable set returned by
    ``collect_prose_slots``: the pass may find that an article slot repeats
    one of them, but a revision addressed to a caption is rejected as unknown.

    Event theme connections are left out on purpose. There are dozens of them,
    each one sentence long, and including them would swamp the prompt with the
    layer the article is least likely to paraphrase wholesale — the chapter,
    circle and stop texts are the ones that sit as blocks of prose right
    beside the article's own paragraphs.
    """
    slots: List[tuple] = []
    for index, chapter in enumerate(composed.chapters):
        if chapter.lead_in.strip():
            slots.append(
                (
                    f"caption:chapter:{index}",
                    CAPTION_SLOT_ROLES["chapter"],
                    f"{chapter.headline} — {chapter.lead_in.strip()}",
                )
            )
    for index, circle in enumerate(composed.circles):
        if circle.text.strip():
            slots.append(
                (
                    f"caption:circle:{index}",
                    CAPTION_SLOT_ROLES["circle"],
                    f"{circle.title} — {circle.text.strip()}",
                )
            )
    for index, stop in enumerate(composed.map_stops):
        if stop.text.strip():
            slots.append(
                (
                    f"caption:stop:{index}",
                    CAPTION_SLOT_ROLES["stop"],
                    f"{stop.title} — {stop.text.strip()}",
                )
            )
    return slots


def rank_slot_overlaps(
    slots: List[tuple], reference: Optional[List[tuple]] = None, min_shared: int = 3
) -> List[tuple]:
    """Rank cross-slot sentence pairs by content-word overlap (Dice).

    ``reference`` slots (the caption layer) are compared against ``slots`` but
    never against each other — two captions describing adjacent chapters
    naturally share vocabulary, and that is not a defect of the article.

    Returns ``(slot_a, slot_b, sentence_a, sentence_b, score)`` sorted by score.

    This is a **diagnostic, not a detector**, and deliberately has no pass/fail
    threshold. Measured against the composed stories, the redundancy that
    actually hurts is paraphrase — "the question was not how to calculate but
    how to instruct" restated as "the problem shifted from what a machine could
    calculate to what people could ask it to do" scores 0.27, while two
    unrelated sentences that merely share two proper names score 0.26. The
    bands overlap, so no cutoff separates them and any threshold here would
    either never fire or fire constantly.

    What it is good for is the RELATIVE comparison: running it before and after
    the redundancy pass shows whether the pass actually pulled the most similar
    pairs apart. Judging whether a repeat is real is left to the AI pass, which
    reads meaning rather than counting words.

    The one place the numbers do separate cleanly is article-against-caption:
    before the caption/article calls were split, the top pairs there sat at
    0.43-0.53 — near-verbatim restatement, not paraphrase — well clear of the
    ~0.27 band. A top reference score in that range is a strong signal that
    the article has slipped back into recapping its own components.
    """

    def prepare(entries: List[tuple]) -> List[tuple]:
        prepared = []
        for slot_id, _role, text in entries:
            for sentence in _SENTENCE_SPLIT.split(text):
                words = _content_words(sentence)
                if len(words) >= 5:
                    prepared.append((slot_id, sentence.strip(), words))
        return prepared

    prepared = prepare(slots)
    prepared_reference = prepare(reference or [])

    ranked = []
    for i, (slot_a, sent_a, words_a) in enumerate(prepared):
        # Article against article (later slots only), then article against
        # every caption — captions are never scored against one another.
        against = list(prepared[i + 1 :])
        # The opening is allowed to narrate one documented moment in full, so
        # it legitimately overlaps whichever caption covers that moment. The
        # redundancy pass is told to leave it alone; scoring it here would
        # only park an unactionable pair at the top of the ranking.
        if slot_a != "opening":
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


_PROPER_NOUN = re.compile(r"\b[A-Z][a-zA-Z'’-]+")
_NUMBER = re.compile(r"\b\d[\d,.]*\b")

# Below this many anchors a passage of any length has stopped saying anything
# checkable. Used both by the diagnostic and by the revision guardrail.
MIN_ANCHORS = 2
# Short passages are exempt: a single line can be concrete without naming
# three institutions, and the anchor count is noisy at that length.
ANCHOR_MIN_WORDS = 25


def count_anchors(text: str) -> int:
    """Count the concrete anchors in a passage.

    An *anchor* is a proper noun or a number: the named law, institution,
    place, person or year that makes a sentence checkable. Words at the start
    of a sentence are capitalized by grammar rather than by content, so they
    are skipped.
    """
    body = " ".join(
        sentence[len(sentence.split(" ")[0]) :]
        for sentence in _SENTENCE_SPLIT.split(text)
    )
    return len(_PROPER_NOUN.findall(body)) + len(_NUMBER.findall(text))


def find_abstract_slots(slots: List[tuple]) -> List[tuple]:
    """Return ``(slot_id, anchors)`` for article slots with too few specifics.

    The counterpart to ``rank_slot_overlaps``, and it exists because the two
    diagnostics catch opposite failures of the same instruction. Told not to
    retell the components, the article call's easiest escape is to stop naming
    anything at all — "the geography joined centers of coordination to
    territories subject to changing control" repeats no caption and says
    nothing. Overlap scoring rates that sentence as a success.

    Reported in ``--verbose``; like the overlap ranking this is a signal for
    the operator, not a gate. The gate is ``_revision_loses_substance``.
    """
    return [
        (slot_id, count_anchors(text))
        for slot_id, _role, text in slots
        if len(text.split()) >= ANCHOR_MIN_WORDS and count_anchors(text) < MIN_ANCHORS
    ]


# A part of the page used as a grammatical subject — "The map asks how...",
# "The chronology follows...". The article is supposed to narrate the history,
# not describe its own presentation, and this is the phrasing that slips
# through the prompt's ban most often.
_INTERFACE_SUBJECT = re.compile(
    r"\b(?:the|this)\s+(?:chronology|timeline|network|graph|map|section|story)\b",
    re.IGNORECASE,
)


def find_interface_references(slots: List[tuple]) -> List[tuple]:
    """Return ``(slot_id, phrase)`` for article slots that describe the page.

    Reported, not repaired: unlike a hollowed-out revision there is no safe
    deterministic fallback (the previous text is usually worse, and dropping
    the sentence can leave a fragment), so this is a signal to recompose.
    """
    found = []
    for slot_id, _role, text in slots:
        match = _INTERFACE_SUBJECT.search(text)
        if match:
            found.append((slot_id, match.group(0)))
    return found


def _revision_loses_substance(original: str, revised: str) -> bool:
    """True when a revision removes a slot's specifics instead of changing them.

    The redundancy pass has a monotone incentive that no prompt can fully
    hold: abstraction *always* reduces overlap. Stripping the names and dates
    from a paragraph reliably satisfies "stop repeating that", which is why an
    early run of the caption-aware pass rewrote ten of twelve slots into prose
    like "a workshop could expose constraints that a laboratory could absorb"
    — repeating nothing, saying nothing, and scoring as a success.

    So the instruction is backed by a check, in the same spirit as the
    verbatim-quote rule: the model proposes, and a revision that leaves the
    slot with fewer anchors than it had *and* below the floor is rejected. A
    legitimate de-duplication swaps one specific for another and passes; only
    the slide into generality is refused. A slot that was already abstract can
    be rewritten freely, since the check compares against its own starting
    point and can only ever hold the line.
    """
    if len(revised.split()) < ANCHOR_MIN_WORDS:
        return False
    return count_anchors(revised) < min(count_anchors(original), MIN_ANCHORS)


def run_redundancy_pass(
    composed: CompositionResult,
    throughline: str,
    source_material: str,
    client: OpenAI,
    model: str,
    reasoning_effort: str,
    verbose: bool = False,
) -> Optional[RedundancyPassResult]:
    """Ask a focused call to rewrite article slots that repeat something.

    Deliberately single-objective: the article call cannot police its own
    repetition while pursuing a dozen other goals, and it cannot see the
    caption layer's finished text as a reader does — as prose already spent.
    This call sees both and has one thing to do.

    ``source_material`` is the article call's own grounding (context notes and
    Wikipedia excerpts). Without it the pass is a trap: told to remove a
    repeated point but restricted to the facts already in the prose, its only
    remaining move is to delete the specifics, which is the one repair
    ``_revision_loses_substance`` refuses. Given the material it can do what
    the instruction actually asks — swap the repeated specifics for different
    ones.
    """
    slots = collect_prose_slots(composed)
    if len(slots) < 2:
        return RedundancyPassResult(revisions=[])
    captions = collect_caption_slots(composed)

    rendered = "\n\n".join(
        f"slot: {slot_id}\nrole: {role}\n{text}" for slot_id, role, text in slots
    )
    rendered_captions = (
        "\n\n".join(
            f"slot: {slot_id}\nrole: {role}\n{text}" for slot_id, role, text in captions
        )
        or "(none)"
    )

    prompt = f"""These texts are the finished prose of one meta story. They come in two layers.

The ARTICLE is the running prose a reader meets between the page's three
interactive components (a timeline, a network graph, a map). It was written
in a single pass, and such a pass tends to restate the story's central idea in
slot after slot.

The CAPTIONS are printed on the components themselves, interleaved with the
article. They are FIXED — you cannot change them — but the reader reads them,
so anything they say is already spent. An article slot that says it again is
the page telling the reader the same thing twice in two voices, which is the
most damaging kind of repetition here.

THROUGHLINE the story was written to (background, not for display):
{throughline}

SOURCE MATERIAL the article was written from. When you rewrite a slot, this
is where its replacement content comes from — a different condition,
institution, law or consequence that no other slot has used yet. Every fact
you write must be supported here or in the texts below:

{source_material}

THE ARTICLE, IN READING ORDER (these you may rewrite):

{rendered}

THE CAPTIONS ALREADY ON THE COMPONENTS (fixed reference — NEVER return a
revision for one of these slots):

{rendered_captions}

YOUR ONLY TASK: find the article slots that make a point an EARLIER article
slot already made, OR that retell something the captions already gave the
reader, and rewrite them so they carry something else.

WHAT COUNTS AS REPETITION:
- The same claim in different words ("the question was not how to calculate
  but how to instruct" and "the problem shifted from what a machine could
  compute to what people could ask of it" are the SAME sentence).
- The same conclusion reached twice, the same formulation reused for effect,
  the same person's significance explained again.
- Two slots that would still say the same thing if you swapped their words.
- An article paragraph narrating an event, relationship or place that a
  caption narrates. The article may name one in passing as a fixed point
  ("by the time the Treaty was signed..."); recounting it is repetition.
- An article paragraph whose sentences each attach to a different item from
  the captions. That is a list of the component's own contents.

WHAT DOES NOT COUNT:
- The same PERSON, PLACE, or EVENT appearing in several slots — recurring
  cast is normal; only a recurring POINT is the problem.
- A body paragraph giving the wider context for something the description
  named in the abstract. That is the intended structure. Only flag it when
  the body merely repeats the abstraction without adding anything.
- Deliberate echoes across a long distance where the later use genuinely
  advances the idea rather than restating it.
- THE OPENING sharing its scene with a caption. The opening is the reader's
  way into the story and is the one slot allowed to narrate a documented
  moment in full. Leave it alone unless it repeats another ARTICLE slot.

WHEN YOU FIND ONE:
- Rewrite the ARTICLE slot. Never the earlier of two article slots, and never
  a caption — captions are fixed, and a revision addressed to one is discarded.
- Keep its assigned role, its approximate length, and the story's voice. The
  "role:" line states both what the slot owns and the mode it must not fall
  into — removing a repetition by sliding into that mode is not a fix. A
  conclusion that stops echoing the description by listing what came before
  has not been repaired, it has been broken differently.
- Fill it with something only it can say — the part of the story that slot is
  responsible for, which for the section bodies is the CONTEXT around the
  components rather than their contents. Draw the replacement from the SOURCE
  MATERIAL above: a different named condition, institution, law, market or
  consequence. Every fact must be supported by the source material or the
  texts below; never invent a claim, date, name, or quotation.
- NEVER fix a repetition by making the slot more abstract. Removing the names
  and dates from a sentence does not remove the repetition, it removes the
  meaning: "the geography joined centers of coordination to territories
  subject to changing control" is a real rewrite this pass once produced, and
  it is worse than what it replaced. Repetition is fixed by swapping the
  repeated specifics for DIFFERENT specifics — a condition, an institution, a
  constraint from the surrounding world — never by generalizing.
- If a slot repeats and there is genuinely nothing else for it to say, make
  it SHORTER. A single concrete sentence is a good outcome; a vague paragraph
  is not.

Return ONLY the article slots you actually rewrote, with the slot id copied
exactly as it appears after "slot:" above (e.g. description,
body:network:1) — bare, with no brackets or other decoration. Never return a
"caption:..." slot.
Most stories need few or no revisions — an empty list is a good outcome, and
is much better than rewriting text that was already doing its job."""

    try:
        response = client.responses.parse(
            model=model,
            reasoning=cast(Any, {"effort": reasoning_effort}),
            input=[
                {
                    "role": "system",
                    "content": "You are a long-form editor with one job: "
                    "removing repetition from a finished piece — both between "
                    "its own sections and against the captions printed beside "
                    "it. You rewrite only what repeats, you never touch a "
                    "caption, you never add facts, and you leave good text "
                    "alone.",
                },
                {"role": "user", "content": prompt},
            ],
            text_format=RedundancyPassResult,
        )
        result = response.output_parsed
        if result is None:
            print("Warning: redundancy pass returned no parsed result, skipped")
            return None
        if verbose:
            for revision in result.revisions:
                print(f"  Rewrote [{revision.slot}] — repeated {revision.repeats}")
            if not result.revisions:
                print("  No repeated claims found")
        return result
    except Exception as e:
        print(f"Warning: redundancy pass failed: {e}")
        return None


def apply_prose_revisions(
    composed: CompositionResult,
    result: RedundancyPassResult,
    verbose: bool = False,
) -> int:
    """Patch revised prose back into the composition result (mutates it).

    Applied before ``apply_composition``, so the revised texts still pass
    through the same defensive application path as everything else. Unknown
    slot ids are ignored with a warning — the pass can only ever replace the
    text of a slot that exists, never create one.

    Slot ids are normalized before matching: the prompt renders each slot as
    ``[slot_id] (role)``, and the model copies the id back in that bracketed
    form often enough that taking it literally silently discarded every
    revision in the first live run.

    Revisions that de-duplicate by going abstract are rejected outright — see
    ``_revision_loses_substance``.
    """
    originals = {
        slot_id: text for slot_id, _role, text in collect_prose_slots(composed)
    }
    applied = 0
    hollowed = 0

    for revision in result.revisions:
        slot_id = revision.slot.strip().strip("[]").strip()
        text = revision.text.strip()
        if not text:
            continue
        if slot_id.startswith("caption:"):
            print(
                f"Warning: revision aimed at caption slot '{slot_id}', ignored "
                "(the caption layer is fixed)"
            )
            continue
        if slot_id not in originals:
            print(f"Warning: revision for unknown prose slot '{slot_id}', ignored")
            continue
        if _revision_loses_substance(originals[slot_id], text):
            print(
                f"Warning: revision for '{slot_id}' removes its specifics "
                f"({count_anchors(originals[slot_id])} concrete anchors -> "
                f"{count_anchors(text)}), rejected"
            )
            hollowed += 1
            continue

        if slot_id == "opening":
            composed.opening.text = text
        elif slot_id.startswith("body:"):
            _, section, index = slot_id.split(":")
            blocks = getattr(composed.section_bodies, section)
            blocks[int(index)].text = text
        else:
            setattr(composed, slot_id, text)
        applied += 1

    if verbose and (applied or hollowed):
        print(
            f"  Applied {applied} prose revision(s)"
            + (f", rejected {hollowed} as substance-losing" if hollowed else "")
        )
    return applied


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


# An image candidate key: person_id:event_index:image_index.
_IMAGE_KEY = re.compile(r"[a-z0-9_]+:\d+:\d+")


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
                        f'material, dropped: "{_truncate(text, 80)}"'
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

    # Always replace rather than merge: an empty body is a legitimate result
    # (a section with no real context to add gets none), so leaving the
    # previous composition's paragraphs in place would silently keep prose the
    # article deliberately dropped.
    if bodies:
        dataset["section_bodies"] = bodies
    else:
        dataset.pop("section_bodies", None)
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
        narration = network.get("narration")
        if isinstance(narration, dict):
            # The section no longer renders an intro paragraph; drop a leftover
            # one from stories composed before that change.
            narration.pop("intro", None)
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
    geo_map["narration"] = {
        "stops": [
            stop_by_key[c.get("key")] for c in kept if c.get("key") in stop_by_key
        ],
    }

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
        # The candidate list renders each key inside a whole line —
        # "[img=person:12:0] 1843 — Ada Lovelace: Publishes Notes ..." — and
        # the model copies back varying amounts of that decoration, from the
        # brackets alone to the entire line. Both forms were observed dropping
        # real selections, so the key is extracted by shape rather than
        # trimmed by prefix. Same class of bug as the prose slot ids.
        match = _IMAGE_KEY.search(key)
        candidate = candidates.get(match.group(0) if match else key.strip())
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
    # Sections carry no standfirst any more; drop one left over from a story
    # composed before that change.
    dataset.pop("timeline_intro", None)
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
    deduplicate: bool = True,
    verbose: bool = False,
) -> Optional[Dict[str, Any]]:
    """Run the full composer over a meta story dataset.

    Returns the composed dataset (a new dict; the input is never mutated), or
    ``None`` when either required AI call fails — callers keep the original
    dataset, which makes the composer safe as a non-fatal pipeline phase. The
    third call (the redundancy pass) is itself non-fatal: if it fails, the
    composed prose is applied unrevised.
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

    # Second call: the caption layer — every text bound to an item.
    captions = run_component_narration(
        working,
        registry,
        curation.throughline,
        wikipedia_context,
        client,
        model,
        reasoning_effort,
        verbose=verbose,
    )
    if captions is None:
        return None

    # Third call: the article between the components, written against the
    # finished captions so it has to find something else to say.
    component_layer = render_component_layer(working, registry, captions)
    context_notes = build_context_notes(working, registry)
    article = run_article(
        working,
        registry,
        curation.throughline,
        component_layer,
        wikipedia_context,
        image_candidates,
        client,
        model,
        reasoning_effort,
        verbose=verbose,
    )
    if article is None:
        return None

    composed = CompositionResult.merge(captions, article)

    # Fourth call: strip the repetition the article call cannot see in itself.
    # Non-fatal — unrevised prose is still a complete story.
    revisions = 0
    if deduplicate:
        caption_slots = collect_caption_slots(composed)
        before = rank_slot_overlaps(collect_prose_slots(composed), caption_slots)
        if verbose and before:
            print("  Most similar slot pairs before pass:")
            for slot_a, slot_b, sent_a, _sent_b, score in before[:3]:
                print(
                    f"    {score:.2f} [{slot_a}] ~ [{slot_b}]: "
                    f"{_truncate(sent_a, 70)}"
                )
        result = run_redundancy_pass(
            composed,
            curation.throughline,
            context_notes + "\n" + wikipedia_context,
            client,
            model,
            reasoning_effort,
            verbose=verbose,
        )
        if result is not None:
            revisions = apply_prose_revisions(composed, result, verbose=verbose)
        if verbose and before:
            after = rank_slot_overlaps(collect_prose_slots(composed), caption_slots)
            now_top = f"{after[0][4]:.2f}" if after else "none"
            print(f"  Top slot overlap: {before[0][4]:.2f} -> {now_top}")

    if verbose:
        final_slots = collect_prose_slots(composed)
        # The other half of the picture: prose that repeats nothing because it
        # says nothing. See find_abstract_slots.
        abstract = find_abstract_slots(final_slots)
        if abstract:
            print(
                "  Slots with too few concrete anchors: "
                + ", ".join(f"{slot_id} ({n})" for slot_id, n in abstract)
            )
        interface = find_interface_references(final_slots)
        if interface:
            print(
                "  Slots describing the page instead of the history: "
                + ", ".join(f'{slot_id} ("{phrase}")' for slot_id, phrase in interface)
            )

    # The quote-verification corpus must be exactly what the ARTICLE call was
    # shown, since it is the call that writes quote blocks. Since the call
    # split that is no longer the story brief: it sees the caption layer and
    # the context notes instead, and a quote lifted from either would fail a
    # brief-only check. The brief stays in the corpus because the captions are
    # derived from it and quoting through them is legitimate.
    material = "\n".join(
        [
            build_story_brief(working, registry),
            context_notes,
            component_layer,
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

    now = datetime.now().astimezone().isoformat()
    working["composition"] = {
        "model": model,
        "composed_at": now,
        "throughline": curation.throughline,
        "excluded_people": [
            {"person_id": exc.person_id, "reason": exc.reason} for exc in exclusions
        ],
        "prose_revisions": revisions,
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
    deduplicate: bool,
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
        deduplicate=deduplicate,
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
        "--skip-redundancy-pass",
        action="store_true",
        help="Skip the third call that rewrites prose slots repeating each other",
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
            deduplicate=not args.skip_redundancy_pass,
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
