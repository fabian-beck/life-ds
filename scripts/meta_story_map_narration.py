#!/usr/bin/env python3
"""AI agents for the meta-story map section, plus the pipeline orchestrator.

The map section shows the story's key places on an auto-zooming map while
narration cards scroll over it (mirroring the social-network scrollytelling).
Building it is a small multi-agent pipeline around the deterministic
clustering in ``meta_story_map.py``:

1. **Rating agent** (:func:`rate_map_events`, batched AI calls) — every
   located event the story uses is rated 0–3 for how strongly it anchors the
   story *geographically*: whether the place is part of the contribution
   (Bletchley Park for wartime codebreaking) or incidental (the city a paper
   happened to be published in). Ratings become the event weights of the
   clustering, so a single landmark event can carry a cluster while
   incidental events (rated 0) drop off the map entirely.
2. **Deterministic clustering** (``meta_story_map.cluster_located_events``)
   — complete-linkage geographic clustering with the rated weights; top
   clusters are selected and ordered chronologically.
3. **Narration agent** (:func:`narrate_map_clusters`, one AI call) — writes
   one card (headline + short story text) per cluster,
   and **curates how many stops the map has**: it keeps only the places that
   genuinely matter to the story (usually no more than ~5), discarding both
   accidental groupings (events merely sharing a city) and real-but-secondary
   places that would only pad the map. Discards are applied defensively:
   unknown keys are ignored and a minimum number of clusters is always kept
   (the model can curate, not empty the section).

Everything is applied deterministically: the model never invents places,
coordinates, or events — it only rates, keeps/discards, and writes prose.
The whole pipeline is non-fatal; on any failure the story simply has no (or
an un-narrated) map section.

Standalone CLI (rebuilds ``geo_map`` for existing stories and refreshes
translations, mirroring ``compose_meta_story.py``):

    python scripts/meta_story_map_narration.py computing_pioneers --verbose
    python scripts/meta_story_map_narration.py --all
    python scripts/meta_story_map_narration.py computing_pioneers --dry-run
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

from pydantic import BaseModel, Field

from meta_story_map import (
    MIN_MAP_CLUSTERS,
    cluster_located_events,
    collect_located_events,
)

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
META_STORIES_DIR = DATA_DIR / "meta_stories"

RATING_BATCH_SIZE = 40


# ---------------------------------------------------------------------------
# Structured-output schemas
# ---------------------------------------------------------------------------


class MapEventRating(BaseModel):
    """Geographic-contribution rating for one located event."""

    event_id: str = Field(description="Event id, copied verbatim from the input")
    weight: int = Field(
        ge=0,
        le=3,
        description="0 = location incidental or event too weak for the map; "
        "1 = minor; 2 = solid, the place is genuinely part of the story; "
        "3 = landmark, the place is inseparable from the contribution",
    )
    reason: str = Field(
        description="One short sentence justifying the rating (for the log)"
    )


class MapEventRatings(BaseModel):
    ratings: List[MapEventRating]


class MapStopNarration(BaseModel):
    """The narration agent's decision and text for one geographic cluster."""

    key: str = Field(description="The cluster's key, copied verbatim from the input")
    keep: bool = Field(
        description="True only for the places that genuinely matter to the "
        "story and belong on the map. Set False both for geographically "
        "accidental groupings (events merely sharing a place) AND for real but "
        "secondary places that would only pad the map — the surviving stops "
        "should be the meaningful few, usually no more than about five"
    )
    discard_reason: Optional[str] = Field(
        default=None,
        description="Required when keep=false: why this place is not among the "
        "story's meaningful stops (accidental grouping, or real but secondary "
        "and cuttable)",
    )
    title: Optional[str] = Field(
        default=None,
        description="Required when keep=true: a short, evocative headline "
        "(2-5 words) for this place's role in the story — NOT a list of "
        "people or place names",
    )
    text: Optional[str] = Field(
        default=None,
        description="Required when keep=true: 2-4 sentence story text weaving "
        "the cluster's events into what happened at this place",
    )


class MapNarrationResult(BaseModel):
    """AI-written narration for the map scroll-over cards."""

    stops: List[MapStopNarration]


# ---------------------------------------------------------------------------
# Agent 1: event rating
# ---------------------------------------------------------------------------


def _story_context(dataset: Dict[str, Any]) -> str:
    meta = dataset.get("meta_story", {}) or {}
    description = (meta.get("description") or "").strip()
    if len(description) > 900:
        description = description[:897] + "..."
    return (
        f"Story: {meta.get('title', '')} ({meta.get('tagline', '')})\n" f"{description}"
    )


def rate_map_events(
    dataset: Dict[str, Any],
    events: List[Dict[str, Any]],
    client: Any,
    model: str,
    reasoning_effort: str = "medium",
    verbose: bool = False,
) -> Dict[str, float]:
    """Rate each located event's geographic contribution to the story (0–3).

    Non-fatal: events missing from a failed or partial response keep the
    default weight (1.0) in the clustering.
    """
    context = _story_context(dataset)
    weights: Dict[str, float] = {}

    for start in range(0, len(events), RATING_BATCH_SIZE):
        batch = events[start : start + RATING_BATCH_SIZE]
        listing = json.dumps(
            [
                {
                    "event_id": e["id"],
                    "person": e["person_name"],
                    "date": e["event_date"],
                    "title": e["event_title"],
                    "place": e["place"],
                    "why_it_is_in_the_story": e.get("theme_connection", ""),
                }
                for e in batch
            ],
            ensure_ascii=False,
            indent=2,
        )
        prompt = f"""{context}

The story ends with a map section that travels to the places where it
happened. Below are the story's events that have a known location. Rate each
event 0-3 for how strongly it anchors the story GEOGRAPHICALLY — i.e. how
much this event, AT THIS PLACE, contributes to the story:

- 3 (landmark): the place is inseparable from the contribution; this event
  alone would justify visiting the place on the map.
- 2 (solid): the event matters and the place is genuinely part of it (where
  the work was actually done, where the people actually gathered).
- 1 (minor): the event contributes, but the place is interchangeable
  background.
- 0 (skip): the location is incidental (e.g. a publication venue's city, an
  award ceremony) or the event is too weak to help the map's story.

Weigh BOTH the event's importance to the story AND how meaningful its place
is. Rate every event; copy each event_id verbatim.

EVENTS:
{listing}"""

        try:
            response = client.responses.parse(
                model=model,
                reasoning={"effort": reasoning_effort},
                input=[
                    {
                        "role": "system",
                        "content": "You rate how strongly biographical events "
                        "anchor a story geographically, judging strictly from "
                        "the given material.",
                    },
                    {"role": "user", "content": prompt},
                ],
                text_format=MapEventRatings,
            )
            parsed = response.output_parsed
            if parsed is None:
                print("Warning: map event rating returned no result for a batch")
                continue
            valid_ids = {e["id"] for e in batch}
            for rating in parsed.ratings:
                if rating.event_id in valid_ids:
                    weights[rating.event_id] = float(rating.weight)
                    if verbose:
                        print(
                            f"    [{rating.weight}] {rating.event_id}: "
                            f"{rating.reason}"
                        )
        except Exception as e:
            print(f"Warning: map event rating failed for a batch: {e}")

    return weights


# ---------------------------------------------------------------------------
# Agent 2: cluster narration + curation (with discard option)
# ---------------------------------------------------------------------------


def _cluster_brief(cluster: Dict[str, Any]) -> str:
    span = (
        f"{cluster['year_start']}–{cluster['year_end']}"
        if cluster.get("year_start") is not None
        else "undated"
    )
    events = "\n".join(
        f"  - {e['event_date']} | {e['person_name']}: {e['event_title']} "
        f"@ {e['place']} (weight {e['weight']})"
        for e in cluster.get("events") or []
    )
    return (
        f"Stop key: {cluster['key']}\n"
        f"Place: {cluster['label']} ({span}; score {cluster['score']})\n"
        f"Events:\n{events}"
    )


def narrate_map_clusters(
    dataset: Dict[str, Any],
    clusters: List[Dict[str, Any]],
    client: Any,
    model: str,
    reasoning_effort: str = "medium",
    verbose: bool = False,
) -> Optional[MapNarrationResult]:
    """One AI call: per-cluster card texts, with a discard option."""
    meta = dataset.get("meta_story", {}) or {}
    briefs = "\n\n".join(_cluster_brief(c) for c in clusters)
    max_candidates = len(clusters)

    prompt = f"""Write the narration for the map section of the meta story
"{meta.get("title", "")}" ({meta.get("tagline", "")}).

The section shows a map that automatically travels from place to place; while
the reader scrolls, each geographic "stop" (a cluster of the story's events
at or near one place) is presented with a card containing a short story text.
Write those texts — and curate the stops.

STOPS (in the order they will be shown, chronological):

{briefs}

CURATION — decide how many stops the map should actually have. You are given
up to {max_candidates} candidate places; keep only the ones that genuinely
matter to THIS story — where decisive work was done, machines were built,
people met, history turned. A map that flies through many stops reads as a
gazetteer, not a story, so keep the meaningful few: usually no more than about
FIVE. Keep more only when additional places are truly essential to the arc.

DISCARD a stop (keep=false, with discard_reason) in two cases:
- accidental groupings — events that merely happen to share a place that adds
  nothing to the story (e.g. unrelated works coincidentally published in the
  same city, or a grouping with no thematic thread at that place);
- real but secondary places that would only pad the map — when the story is
  already well told by stronger stops, cut the weaker ones even if the place
  is not strictly accidental.

At least a few stops must survive, so do not discard so aggressively that the
map becomes trivial.

REQUIREMENTS:
- One entry per stop, in the given order, with `key` copied EXACTLY.
- Each kept stop's title: a short, evocative headline (2-5 words) in the
  spirit of a book chapter — capture what this place meant to the story. Do
  NOT simply repeat the place name and do NOT list people's names.
- Each kept stop's text: 2-4 sentences of flowing prose weaving the events at
  this place into a miniature story — who worked here, what was made, why it
  mattered. Mention the people by name and the place naturally. Ground every
  claim in the event data above; do not invent facts. No bullet points.
- Refer to people by natural name forms (e.g. "Babbage" on second mention).
- Tone: vivid but factual, matching a biographical story collection.
- NEVER address the reader. No "you"/"your"/"we"/"us", no imperatives aimed
  at the audience, no references to scrolling, zooming, or the map as an
  interface. Write in the third person, about the people and places."""

    try:
        response = client.responses.parse(
            model=model,
            reasoning={"effort": reasoning_effort},
            input=[
                {
                    "role": "system",
                    "content": "You are a skilled narrative writer turning "
                    "geographic event data into short, factual story texts, "
                    "and a careful curator of which places truly matter.",
                },
                {"role": "user", "content": prompt},
            ],
            text_format=MapNarrationResult,
        )
        return cast(Optional[MapNarrationResult], response.output_parsed)
    except Exception as e:
        print(f"Warning: map narration failed: {e}")
        return None


def apply_map_narration(
    clusters: List[Dict[str, Any]],
    narration: Optional[MapNarrationResult],
    verbose: bool = False,
) -> Dict[str, Any]:
    """Apply the narration agent's decisions defensively.

    Unknown keys are ignored; clusters without a decision are kept without a
    text (the UI falls back to listing the events). Discards are honored only
    while at least ``MIN_MAP_CLUSTERS`` (or all, if fewer) clusters survive —
    re-kept clusters are chosen by score.

    Returns the finished ``geo_map`` block (without the ``generation`` stamp).
    """
    if narration is None:
        return {"clusters": clusters}

    by_key = {s.key: s for s in narration.stops}
    unknown = [
        s.key for s in narration.stops if s.key not in {c["key"] for c in clusters}
    ]
    if unknown:
        print(f"Warning: map narration for unknown stop keys ignored: {unknown}")

    kept: List[Dict[str, Any]] = []
    discarded: List[Dict[str, Any]] = []
    for cluster in clusters:
        decision = by_key.get(cluster["key"])
        if decision is not None and not decision.keep:
            discarded.append(
                {
                    "key": cluster["key"],
                    "label": cluster["label"],
                    "reason": decision.discard_reason or "",
                    "cluster": cluster,
                }
            )
        else:
            kept.append(cluster)

    # Guardrail: the agent curates, it does not empty the section.
    min_kept = min(MIN_MAP_CLUSTERS, len(clusters))
    if len(kept) < min_kept:
        discarded.sort(key=lambda d: -d["cluster"]["score"])
        while len(kept) < min_kept and discarded:
            rekept = discarded.pop(0)
            print(
                f"Note: re-keeping discarded stop '{rekept['key']}' to preserve "
                f"a minimum of {min_kept} map stops"
            )
            kept.append(rekept["cluster"])
        kept.sort(
            key=lambda c: (
                c["year_start"] if c.get("year_start") is not None else 10**9,
                c["label"],
            )
        )

    stops = []
    for cluster in kept:
        decision = by_key.get(cluster["key"])
        if decision is not None and decision.title and decision.text:
            stops.append(
                {
                    "key": cluster["key"],
                    "title": decision.title,
                    "text": decision.text,
                }
            )
        elif verbose:
            print(f"  Stop '{cluster['key']}' kept without narration text")

    if verbose:
        for entry in discarded:
            print(f"  [-] discarded stop {entry['key']}: {entry['reason']}")
        print(f"  Narrated {len(stops)} of {len(kept)} kept stop(s)")

    geo_map: Dict[str, Any] = {"clusters": kept}
    if stops:
        geo_map["narration"] = {"stops": stops}
    if discarded:
        geo_map["discarded"] = [
            {"key": d["key"], "label": d["label"], "reason": d["reason"]}
            for d in discarded
        ]
    return geo_map


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def generate_geo_map(
    dataset: Dict[str, Any],
    registry: Dict[str, Any],
    client: Any,
    model: str,
    reasoning_effort: str = "medium",
    skip_rating: bool = False,
    verbose: bool = False,
) -> Optional[Dict[str, Any]]:
    """Run the full map pipeline for a meta story.

    Returns the ``geo_map`` block, or ``None`` when the story has too few
    located events. Non-fatal throughout: rating and narration failures
    degrade gracefully (default weights / un-narrated stops).
    """
    located = collect_located_events(dataset, registry)
    if verbose:
        print(f"  {len(located)} located event(s) collected")
    if len(located) < 2:
        if verbose:
            print("  Too few located events for a map section, skipping")
        return None

    weights: Dict[str, float] = {}
    if not skip_rating:
        if verbose:
            print("  Rating events (geographic contribution)...")
        weights = rate_map_events(
            dataset, located, client, model, reasoning_effort, verbose
        )

    clusters = cluster_located_events(located, weights)
    if not clusters:
        if verbose:
            print("  No clusters qualified, skipping map section")
        return None
    if verbose:
        for cluster in clusters:
            print(
                f"  Cluster [{cluster['key']}] {cluster['label']}: "
                f"score {cluster['score']}, {len(cluster['events'])} event(s)"
            )

    if verbose:
        print("  Narrating map stops...")
    narration = narrate_map_clusters(
        dataset, clusters, client, model, reasoning_effort, verbose
    )
    geo_map = apply_map_narration(clusters, narration, verbose=verbose)
    geo_map["generation"] = {
        "model": model,
        "generated_at": datetime.now().astimezone().isoformat(),
        "located_events": len(located),
        "rated_events": len(weights),
    }
    return geo_map


# ---------------------------------------------------------------------------
# Standalone CLI
# ---------------------------------------------------------------------------


def main() -> int:
    import argparse
    import os

    from openai import OpenAI

    from config import DEFAULT_MODEL, DEFAULT_REASONING_EFFORT

    parser = argparse.ArgumentParser(
        description="(Re)build the geo_map section of existing meta stories "
        "(event rating + geographic clustering + narration)"
    )
    parser.add_argument("story_id", nargs="?", help="Meta story ID; omit with --all")
    parser.add_argument("--all", action="store_true", help="All meta stories")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the pipeline and print the result without writing files",
    )
    parser.add_argument(
        "--skip-rating",
        action="store_true",
        help="Skip the AI event rating (all events weigh 1.0)",
    )
    parser.add_argument(
        "--skip-translate",
        action="store_true",
        help="Skip re-translating the story afterwards",
    )
    parser.add_argument(
        "--translate-langs",
        default="de",
        help="Comma-separated language codes to re-translate (default: de)",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"OpenAI model (default: {DEFAULT_MODEL})",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if not args.all and not args.story_id:
        parser.error("provide a story_id or --all")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY environment variable not set")
        return 1
    client = OpenAI(api_key=api_key)

    with open(DATA_DIR / "persons.json", "r", encoding="utf-8") as f:
        registry = json.load(f)

    if args.all:
        story_ids = sorted(
            p.stem for p in META_STORIES_DIR.glob("*.json") if p.is_file()
        )
    else:
        story_ids = [args.story_id]

    failures = 0
    for story_id in story_ids:
        story_path = META_STORIES_DIR / f"{story_id}.json"
        if not story_path.exists():
            print(f"Error: meta story not found: {story_path}")
            failures += 1
            continue
        print(f"Building map section for '{story_id}'...")
        with open(story_path, "r", encoding="utf-8") as f:
            dataset = json.load(f)

        geo_map = generate_geo_map(
            dataset,
            registry,
            client,
            model=args.model,
            reasoning_effort=DEFAULT_REASONING_EFFORT,
            skip_rating=args.skip_rating,
            verbose=args.verbose,
        )
        if geo_map is None:
            print(f"  No map section for '{story_id}' (too few located events)")
            continue

        if args.dry_run:
            print(json.dumps(geo_map, indent=2, ensure_ascii=False))
            continue

        dataset["geo_map"] = geo_map
        with open(story_path, "w", encoding="utf-8") as f:
            json.dump(dataset, f, indent=2, ensure_ascii=False)
        print(f"  Saved {story_path.name} with {len(geo_map['clusters'])} map stop(s)")

        # The map narration changes the story's translatable English text, so
        # refresh translations right away (mirrors compose_meta_story.py).
        if not args.skip_translate:
            from translate_meta_story import translate_meta_story_data

            for lang in [
                code.strip() for code in args.translate_langs.split(",") if code.strip()
            ]:
                print(f"  Re-translating '{story_id}' to '{lang}'...")
                try:
                    if translate_meta_story_data(
                        story_id,
                        lang,
                        client,
                        model=args.model,
                        verbose=args.verbose,
                    ):
                        print(f"    Translation to '{lang}' complete")
                    else:
                        failures += 1
                        print(f"    WARNING: translation to '{lang}' failed")
                except Exception as e:
                    failures += 1
                    print(f"    WARNING: translation to '{lang}' failed: {e}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
