#!/usr/bin/env python3
"""Story composer agent (Phase 7) — top-down composition of a meta story.

Every text in a meta story is written bottom-up by an earlier phase that only
sees its own slice: the description and conclusion are planned before any
event is selected (Phase 1), theme connections are judged per batch (Phase 3),
and the network narration only sees the graph (Phase 6). Nothing ever reads
the *assembled* story. This module adds that missing final step: a composer
that reviews the whole dataset from the top down and writes one coherent
narrative around the timeline and the network analysis.

The composer works in two AI calls:

1. **Curation** — reads the assembled story and decides on a *throughline*
   (the arc that anchors all prose) and, exceptionally, which clearly
   disconnected people to drop from the story. Exclusions are applied
   deterministically with hard guardrails (at most ~25% of the cast, never
   below ``MIN_REMAINING_PEOPLE`` people) and cascade through ``person_ids``,
   subtopics, chapter events, and the social network. The network is *pruned*
   (not re-derived), so Phase 5b review edits on surviving ties are kept.
2. **Composition** — rewrites the story's prose in one voice, guided by the
   throughline: title, tagline, description, a new ``timeline_intro`` shown
   before the chapters timeline, chapter headlines plus a new per-chapter
   ``lead_in``, subtopic texts, sparse refinements of event theme
   connections, the network narration (intro + circles), and the conclusion.
   Facts, dates, IDs, event indices, and the graph itself are never sent to
   the model as editable fields, so they cannot drift.

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
from typing import Any, Dict, List, Optional, cast

from openai import OpenAI
from pydantic import BaseModel, Field

from config import DEFAULT_MODEL, DEFAULT_REASONING_EFFORT
from meta_story_network import derive_clusters

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
REGISTER_PATH = DATA_DIR / "persons.json"
META_STORIES_DIR = DATA_DIR / "meta_stories"

# Exclusion guardrails: the composer may only drop clearly disconnected
# people, never gut the cast.
MIN_REMAINING_PEOPLE = 3
MAX_EXCLUSION_FRACTION = 0.25


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


class ComposedChapter(BaseModel):
    """Rewritten texts for one timeline chapter."""

    id: str = Field(description="Chapter ID, copied verbatim from the input")
    headline: str = Field(
        description="Era headline (2-5 words) WITHOUT any date range — the "
        "date range is appended automatically. One unified concept, not a list."
    )
    lead_in: str = Field(
        description="1-2 short sentences shown with the chapter while the "
        "reader scrolls the timeline: set the era's stakes and pull the "
        "reader onward. No name-dropping lists, no dates (they are shown "
        "next to it)."
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
    """Rewritten narration for one network cluster ("circle")."""

    key: str = Field(description="The circle's key, copied verbatim from the input")
    title: str = Field(
        description="Short evocative headline (2-5 words), not a list of names"
    )
    text: str = Field(
        description="2-4 sentence story text weaving the circle's ties "
        "together, grounded strictly in the tie descriptions"
    )


class CompositionResult(BaseModel):
    """Second composer call: the story's full prose, written in one voice."""

    title: str = Field(description="Story title (2-5 words)")
    tagline: str = Field(description="Short hook (3-10 words)")
    description: str = Field(
        description="Opening narrative (2-3 paragraphs) introducing the topic "
        "like a feature article — no meta-references such as 'this collection'"
    )
    timeline_intro: str = Field(
        description="2-4 sentence paragraph shown right before the chapters "
        "timeline, inviting the reader into the chronological journey. Do not "
        "enumerate the chapters."
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
    network_intro: str = Field(
        description="2-3 sentence opening paragraph for the network section, "
        "consistent with the timeline texts. No individual names, no preview "
        "of the circles, no reading guide."
    )
    circles: List[ComposedCircle] = Field(
        description="One entry per circle, in the given order, keys verbatim"
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


def build_story_brief(
    dataset: Dict[str, Any],
    registry: Dict[str, Any],
    clusters: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Render the assembled story as text for the composer prompts."""
    index = _person_index(registry)
    meta = dataset.get("meta_story", {})

    def person_name(pid: str) -> str:
        return str(index.get(pid, {}).get("name", pid)).replace("_", " ")

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

    if clusters:
        narration = (dataset.get("social_network") or {}).get("narration") or {}
        draft_by_key = {
            c.get("key"): c for c in narration.get("circles") or [] if c.get("key")
        }
        parts.append("")
        if narration.get("intro"):
            parts.append(f"NETWORK INTRO (draft): {narration['intro']}")
        parts.append("NETWORK CIRCLES (clusters of the social graph):")
        for cluster in clusters:
            members = ", ".join(n["name"] for n in cluster["mains"])
            bridges = ", ".join(n["name"] for n in cluster["secondaries"]) or "none"
            parts.append(
                f"Circle key: {cluster['key']}\n"
                f"  Main people: {members}\n"
                f"  Bridging acquaintances: {bridges}"
            )
            for link in cluster["links"]:
                parts.append(
                    f"  - {link.get('source', '')} <-> {link.get('target', '')} "
                    f"[{link.get('relationship_type', '')}, "
                    f"{link.get('strength', '')}]: "
                    f"{link.get('relationship_description', '')}"
                )
            draft = draft_by_key.get(cluster["key"])
            if draft:
                parts.append(
                    f"  Narration draft: \"{draft.get('title', '')}\" — "
                    f"{draft.get('text', '')}"
                )

    parts.append("")
    parts.append(f"CONCLUSION (draft):\n{dataset.get('conclusion', '')}")
    return "\n".join(parts)


# ============================================================================
# CALL 1: CURATION
# ============================================================================


def run_curation(
    dataset: Dict[str, Any],
    registry: Dict[str, Any],
    client: OpenAI,
    model: str,
    reasoning_effort: str,
    allow_exclusions: bool,
    verbose: bool = False,
) -> Optional[CurationResult]:
    """Ask the composer for the story's throughline and optional exclusions."""
    clusters = derive_clusters(dataset.get("social_network") or {})
    brief = build_story_brief(dataset, registry, clusters)

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
    clusters: List[Dict[str, Any]],
    client: OpenAI,
    model: str,
    reasoning_effort: str,
    verbose: bool = False,
) -> Optional[CompositionResult]:
    """Ask the composer to write the story's full prose in one voice."""
    brief = build_story_brief(dataset, registry, clusters)

    prompt = f"""Compose the final narrative for this meta story. All existing texts are
bottom-up drafts written without seeing the whole; you see everything and
write the story top-down, in one coherent voice, anchored to the throughline.

THROUGHLINE (your anchor, not for display):
{throughline}

{brief}

WRITE THE FOLLOWING (all display-facing, general educated audience):

- title (2-5 words) and tagline (3-10 words): refine the drafts or replace
  them if the throughline calls for it.
- description: 2-3 paragraphs introducing the topic like the opening of a
  feature article. NEVER use meta-references ("This collection...", "These
  figures..."); write directly about the topic.
- timeline_intro: 2-4 sentences shown right before the chronological
  timeline. Invite the reader into the journey the chapters trace — where it
  begins, what changes along the way — WITHOUT enumerating the chapters.
- chapters: for each chapter (same order, ids verbatim) a headline of 2-5
  words WITHOUT any date range (it is appended automatically), one unified
  concept, no lists; and a lead_in of 1-2 short sentences that set the era's
  stakes while the reader scrolls. Chapter headlines must build on one
  another so the sequence reads like a story's chapters.
- subtopics: for each subtopic (same order, ids verbatim) a title and a 1-2
  sentence description that names the thread its members share.
- theme_connection_refinements: rewrite an event's theme connection ONLY
  where the draft clashes with the story's voice, repeats a neighbouring
  event, or buries its point. Keep every factual claim of the draft; never
  add facts. Reference events by their [key=...] value. Most events should
  not appear here — an empty list is acceptable.
- network_intro: 2-3 sentences opening the social-network section, written
  like a chapter opening, consistent with the timeline texts. Do NOT name
  individual people, do NOT preview the circles, do NOT explain the graph.
- circles: one entry per circle (order and keys verbatim): an evocative 2-5
  word title (not a list of names) and 2-4 sentences of flowing prose that
  weave the circle's ties into a miniature story. Ground every claim in the
  tie descriptions; refer to people naturally ("Babbage" on second mention).
- conclusion: 2-3 sentences that close the arc the throughline names.

HARD RULES:
- Stick to the facts in the material above; never invent events, dates,
  relationships, or claims.
- Copy ids and circle keys EXACTLY; keep list order.
- Vivid but factual tone, matching a biographical story collection.
"""

    try:
        response = client.responses.parse(
            model=model,
            reasoning=cast(Any, {"effort": reasoning_effort}),
            input=[
                {
                    "role": "system",
                    "content": "You are a skilled narrative editor composing a "
                    "coherent story from verified biographical material. You "
                    "refine and connect; you never invent facts.",
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
            print(f"  Chapter headlines: {[c.headline for c in result.chapters]}")
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


def apply_composition(
    dataset: Dict[str, Any],
    composed: CompositionResult,
    clusters: List[Dict[str, Any]],
    verbose: bool = False,
) -> None:
    """Overlay the composed texts onto the dataset (mutates in place).

    Structure is authoritative on the dataset side: chapters, subtopics, and
    circles are matched by id/key, unknown entries are ignored with a warning,
    and missing entries keep their existing texts.
    """
    meta = dataset.get("meta_story", {})
    if composed.title.strip():
        meta["title"] = composed.title.strip()
    if composed.tagline.strip():
        meta["tagline"] = composed.tagline.strip()
    if composed.description.strip():
        meta["description"] = composed.description.strip()
    if composed.timeline_intro.strip():
        dataset["timeline_intro"] = composed.timeline_intro.strip()
    if composed.conclusion.strip():
        dataset["conclusion"] = composed.conclusion.strip()

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

    # Network narration: rebuilt from the current clusters so keys always
    # match what the UI derives. Composed circles win; a cluster the model
    # missed falls back to its previous narration (matched by key) if any.
    network = dataset.get("social_network")
    if network is not None and clusters:
        composed_by_key = {c.key: c for c in composed.circles}
        previous_by_key = {
            c.get("key"): c
            for c in (network.get("narration") or {}).get("circles") or []
            if c.get("key")
        }
        circles = []
        for cluster in clusters:
            key = cluster["key"]
            circle_entry = composed_by_key.pop(key, None)
            if circle_entry is not None:
                circles.append(
                    {
                        "key": key,
                        "title": circle_entry.title,
                        "text": circle_entry.text,
                    }
                )
            elif key in previous_by_key:
                print(
                    f"Warning: no composed narration for circle '{key}', "
                    "keeping previous text"
                )
                circles.append(previous_by_key[key])
            else:
                print(f"Warning: circle '{key}' has no narration")
        for unknown_key in composed_by_key:
            print(
                f"Warning: composed circle '{unknown_key}' matches no cluster, ignored"
            )
        network["narration"] = {
            "intro": composed.network_intro.strip()
            or (network.get("narration") or {}).get("intro", ""),
            "circles": circles,
        }


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

    curation = run_curation(
        working,
        registry,
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

    clusters = derive_clusters(working.get("social_network") or {})

    composed = run_composition(
        working,
        registry,
        curation.throughline,
        clusters,
        client,
        model,
        reasoning_effort,
        verbose=verbose,
    )
    if composed is None:
        return None

    apply_composition(working, composed, clusters, verbose=verbose)

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
        for chapter in composed.get("chapters") or []:
            print(f"    Chapter: {chapter.get('title', '')}")
            if chapter.get("lead_in"):
                print(f"      Lead-in: {chapter['lead_in']}")
        print(f"    Timeline intro: {composed.get('timeline_intro', '')}")
        return True

    with open(path, "w", encoding="utf-8") as f:
        json.dump(composed, f, indent=2, ensure_ascii=False)
    print(f"  Saved {path}")

    # Keep the registry entry (title/tagline/person_count) in sync. Imported
    # lazily: generate_meta_story imports this module for Phase 7.
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
