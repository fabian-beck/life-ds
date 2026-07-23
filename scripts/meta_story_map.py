#!/usr/bin/env python3
"""Derive the geographic map section ("geo_map") for a meta-story.

This is the deterministic half of the map pipeline (the AI half — event
rating and stop narration — lives in ``meta_story_map_narration.py``):

1. **Collect** every located event the meta-story already uses: the
   ``person_events`` of all chapters are resolved against each person's
   ``life_events.json`` and events with usable coordinates are kept.
2. **Cluster** those events geographically with complete-linkage
   agglomerative clustering on great-circle distance, so events merge only
   while *all* pairwise distances stay below ``MERGE_DISTANCE_KM``. Nearby
   story places (e.g. Cambridge and Bletchley Park, ~66 km apart) therefore
   remain distinct clusters while same-city events merge.
3. **Score** each cluster as the sum of its events' weights. Weights come
   from the AI rating agent (0–3 per event); without ratings every event
   counts 1.0. A single landmark event (weight 3) can carry a cluster on its
   own, and so can several weaker but geographically close events — exactly
   the two shapes a meaningful story place can take.
4. **Select** the top clusters (score threshold + cap) and order them
   chronologically so the map travels through the story in time.

Like the social network, the derived cluster data is technical (names,
dates, coordinates) and is copied verbatim into translated meta-story files;
only the AI-written ``geo_map.narration`` texts are part of the translation
payload.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
PEOPLE_DIR = DATA_DIR / "people"

# Complete-linkage merge threshold: two clusters merge only while every
# cross-pair of events lies within this distance, keeping distinct story
# places (Cambridge vs. Bletchley Park vs. London) from collapsing into one.
MERGE_DISTANCE_KM = 50.0

# How many clusters the map section narrates at most.
MAX_MAP_CLUSTERS = 8

# Minimum cluster score (sum of event weights) to qualify: one landmark event
# (weight 3) or a handful of weaker co-located ones. If fewer than
# MIN_MAP_CLUSTERS qualify, the top clusters are taken regardless, so a story
# with sparse ratings still gets a map.
MIN_CLUSTER_SCORE = 3.0
MIN_MAP_CLUSTERS = 3

# Weight assumed for an event the rating agent did not (or could not) rate.
DEFAULT_EVENT_WEIGHT = 1.0

# Clusters containing a landmark event (weight >= 3) get a selection bonus so
# a single iconic place (Bletchley Park) is not crowded out of the cap by
# clusters that merely accumulate several routine events.
LANDMARK_WEIGHT = 3.0
LANDMARK_BONUS = 1.5


def _slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_only.lower())
    return slug.strip("_") or "place"


def haversine_km(a: List[float], b: List[float]) -> float:
    """Great-circle distance in km between two ``[lon, lat]`` points."""
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    h = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return 2 * 6371.0088 * math.asin(min(1.0, math.sqrt(h)))


def _valid_coordinates(coords: Any) -> Optional[List[float]]:
    if (
        isinstance(coords, (list, tuple))
        and len(coords) == 2
        and all(isinstance(c, (int, float)) for c in coords)
        and -180 <= coords[0] <= 180
        and -90 <= coords[1] <= 90
    ):
        return [float(coords[0]), float(coords[1])]
    return None


def _event_location(event: Dict[str, Any]) -> Optional[Tuple[str, List[float]]]:
    """Resolve an event's primary place label and ``[lon, lat]`` centroid.

    Handles both location schemas found in the data: the current
    ``locations`` list (``name_historic``/``name_modern``/``centroid``) and
    the legacy ``location_coordinates`` list (``name``/``label``/``centroid``).
    """
    candidates = []
    for loc in event.get("locations") or []:
        if isinstance(loc, dict):
            candidates.append(
                (
                    loc.get("name_historic") or loc.get("name_modern") or "",
                    loc.get("centroid"),
                    bool(loc.get("primary")),
                )
            )
    if not candidates:
        for loc in event.get("location_coordinates") or []:
            if isinstance(loc, dict):
                candidates.append(
                    (
                        loc.get("name") or loc.get("label") or "",
                        loc.get("centroid"),
                        bool(loc.get("primary")),
                    )
                )

    # Primary entry first, then first valid fallback.
    candidates.sort(key=lambda c: not c[2])
    for name, centroid, _primary in candidates:
        coords = _valid_coordinates(centroid)
        if coords:
            label = str(name).split(",")[0].strip() or "Unknown place"
            return label, coords
    return None


def _event_year(date_str: Any) -> Optional[int]:
    match = re.match(r"\s*(-?\d{1,4})", str(date_str or ""))
    return int(match.group(1)) if match else None


def collect_located_events(
    dataset: Dict[str, Any], registry: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """All meta-story events that resolve to coordinates.

    Walks the chapters' ``person_events`` (the events that already passed the
    story's relevance rating) and looks each one up in the person's
    ``life_events.json``. Events without a usable location are skipped —
    the map only speaks about places the data actually knows.
    """
    person_names = {
        p.get("id"): str(p.get("name", p.get("id", ""))).replace("_", " ")
        for p in registry.get("people", [])
    }
    events_cache: Dict[str, List[Dict[str, Any]]] = {}

    def life_events_for(person_id: str) -> List[Dict[str, Any]]:
        if person_id not in events_cache:
            path = PEOPLE_DIR / person_id / "life_events.json"
            try:
                with open(path, "r", encoding="utf-8") as f:
                    events_cache[person_id] = json.load(f).get("events") or []
            except Exception:
                events_cache[person_id] = []
        return events_cache[person_id]

    located: List[Dict[str, Any]] = []
    seen = set()
    for chapter in dataset.get("chapters") or []:
        for pe in chapter.get("person_events") or []:
            person_id = pe.get("person_id")
            event_index = pe.get("event_index")
            if not person_id or not isinstance(event_index, int):
                continue
            event_id = f"{person_id}:{event_index}"
            if event_id in seen:
                continue
            seen.add(event_id)

            events = life_events_for(person_id)
            if not (0 <= event_index < len(events)):
                continue
            event = events[event_index]
            location = _event_location(event)
            if location is None:
                continue
            place, coords = location
            located.append(
                {
                    "id": event_id,
                    "person_id": person_id,
                    "person_name": person_names.get(person_id, person_id),
                    "event_index": event_index,
                    "event_title": pe.get("event_title")
                    or event.get("title", ""),
                    "event_date": pe.get("event_date") or event.get("date", ""),
                    "year": _event_year(pe.get("event_date") or event.get("date")),
                    "place": place,
                    "coordinates": coords,
                    "theme_connection": pe.get("theme_connection", ""),
                }
            )
    return located


def _cluster_label(members: List[Dict[str, Any]], weights: Dict[str, float]) -> str:
    """Weighted-majority place name; append the runner-up when no place
    clearly dominates a multi-place cluster."""
    by_place: Dict[str, float] = {}
    for event in members:
        by_place[event["place"]] = by_place.get(event["place"], 0.0) + max(
            weights.get(event["id"], DEFAULT_EVENT_WEIGHT), 0.5
        )
    ranked = sorted(by_place.items(), key=lambda kv: (-kv[1], kv[0]))
    total = sum(by_place.values()) or 1.0
    top_name, top_weight = ranked[0]
    if len(ranked) > 1 and top_weight / total < 0.6:
        return f"{top_name} · {ranked[1][0]}"
    return top_name


def cluster_located_events(
    events: List[Dict[str, Any]],
    weights: Optional[Dict[str, float]] = None,
) -> List[Dict[str, Any]]:
    """Cluster located events geographically and select the top clusters.

    Args:
        events: Output of :func:`collect_located_events`.
        weights: Optional per-event weights (0–3) from the rating agent,
            keyed by event id (``person_id:event_index``). Events rated 0 are
            dropped before clustering; missing ratings default to 1.0.

    Returns:
        The selected clusters in chronological order, each a plain dict ready
        to be stored under ``geo_map.clusters``.
    """
    weights = weights or {}
    pool = [
        e for e in events if weights.get(e["id"], DEFAULT_EVENT_WEIGHT) > 0
    ]
    if not pool:
        return []

    # Complete-linkage agglomerative clustering: repeatedly merge the two
    # closest clusters whose *maximum* cross-pair distance stays below the
    # threshold. O(n^3) worst case is fine for the tens of events a story has.
    clusters: List[List[Dict[str, Any]]] = [[e] for e in pool]

    def linkage(a: List[Dict[str, Any]], b: List[Dict[str, Any]]) -> float:
        return max(
            haversine_km(x["coordinates"], y["coordinates"]) for x in a for y in b
        )

    while len(clusters) > 1:
        best = None
        best_dist = MERGE_DISTANCE_KM
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                dist = linkage(clusters[i], clusters[j])
                if dist <= best_dist:
                    best_dist = dist
                    best = (i, j)
        if best is None:
            break
        i, j = best
        clusters[i] = clusters[i] + clusters[j]
        del clusters[j]

    def weight_of(event: Dict[str, Any]) -> float:
        return weights.get(event["id"], DEFAULT_EVENT_WEIGHT)

    built: List[Dict[str, Any]] = []
    for members in clusters:
        members = sorted(
            members, key=lambda e: (e["year"] if e["year"] is not None else 10**9)
        )
        score = sum(weight_of(e) for e in members)
        total = score or 1.0
        centroid = [
            sum(e["coordinates"][0] * weight_of(e) for e in members) / total,
            sum(e["coordinates"][1] * weight_of(e) for e in members) / total,
        ]
        lons = [e["coordinates"][0] for e in members]
        lats = [e["coordinates"][1] for e in members]
        years = [e["year"] for e in members if e["year"] is not None]
        built.append(
            {
                "label": _cluster_label(members, weights),
                "score": round(score, 2),
                "centroid": [round(centroid[0], 5), round(centroid[1], 5)],
                "bbox": [
                    round(min(lons), 5),
                    round(min(lats), 5),
                    round(max(lons), 5),
                    round(max(lats), 5),
                ],
                "year_start": min(years) if years else None,
                "year_end": max(years) if years else None,
                "mean_year": (sum(years) / len(years)) if years else None,
                "events": [
                    {
                        "person_id": e["person_id"],
                        "person_name": e["person_name"],
                        "event_index": e["event_index"],
                        "event_title": e["event_title"],
                        "event_date": e["event_date"],
                        "place": e["place"],
                        "coordinates": e["coordinates"],
                        "weight": round(weight_of(e), 2),
                    }
                    for e in members
                ],
            }
        )

    # Selection: qualified clusters by score (landmark clusters boosted),
    # topped up to MIN_MAP_CLUSTERS when the threshold leaves too few,
    # capped at MAX_MAP_CLUSTERS.
    def rank_score(cluster: Dict[str, Any]) -> float:
        has_landmark = any(
            e["weight"] >= LANDMARK_WEIGHT for e in cluster["events"]
        )
        return cluster["score"] + (LANDMARK_BONUS if has_landmark else 0.0)

    built.sort(key=lambda c: (-rank_score(c), c["label"]))
    selected = [c for c in built if rank_score(c) >= MIN_CLUSTER_SCORE]
    if len(selected) < MIN_MAP_CLUSTERS:
        selected = built[:MIN_MAP_CLUSTERS]
    selected = selected[:MAX_MAP_CLUSTERS]

    # Chronological order so the camera travels through the story in time.
    selected.sort(
        key=lambda c: (
            c["mean_year"] if c["mean_year"] is not None else float("inf"),
            c["label"],
        )
    )

    # Stable-unique keys derived from the label (ties narration to clusters).
    used = set()
    for cluster in selected:
        base = _slugify(cluster["label"])
        key = base
        suffix = 2
        while key in used:
            key = f"{base}_{suffix}"
            suffix += 1
        used.add(key)
        cluster["key"] = key
        # mean_year was only needed for ordering.
        del cluster["mean_year"]

    return selected


def build_geo_map(
    dataset: Dict[str, Any],
    registry: Dict[str, Any],
    weights: Optional[Dict[str, float]] = None,
) -> Optional[Dict[str, Any]]:
    """Derive the ``geo_map`` block (clusters only, no narration).

    Returns ``None`` when the story has too few located events for a
    meaningful map section.
    """
    located = collect_located_events(dataset, registry)
    clusters = cluster_located_events(located, weights)
    if not clusters:
        return None
    return {"clusters": clusters}


def main() -> int:
    """CLI: print the derived clusters for an existing meta story (debug)."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Derive a meta-story's geographic clusters (no AI)"
    )
    parser.add_argument("story_id", help="Meta story ID (e.g., computing_pioneers)")
    args = parser.parse_args()

    story_path = DATA_DIR / "meta_stories" / f"{args.story_id}.json"
    if not story_path.exists():
        print(f"Error: meta story not found: {story_path}")
        return 1
    with open(story_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)
    with open(DATA_DIR / "persons.json", "r", encoding="utf-8") as f:
        registry = json.load(f)

    located = collect_located_events(dataset, registry)
    clusters = cluster_located_events(located)
    print(f"{len(located)} located event(s)")
    for cluster in clusters:
        span = (
            f"{cluster['year_start']}–{cluster['year_end']}"
            if cluster["year_start"] is not None
            else "?"
        )
        print(
            f"\n[{cluster['key']}] {cluster['label']} "
            f"(score {cluster['score']}, {span})"
        )
        for event in cluster["events"]:
            print(
                f"  - {event['event_date']} {event['person_name']}: "
                f"{event['event_title']} @ {event['place']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
