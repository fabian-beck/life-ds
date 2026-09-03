"""Which events of one life open a depth layer, ported for the generation side.

The rule lives in ``src/utils/story/eventDepth.js``: each chapter offers its
heaviest event, an event below the weight floor or with too little material
behind the fold offers nothing, and the story shows a layer only where the
selected event also carries a written report. This module is the pipeline's
port of that selection, so background reports are written exactly for the
events the story will offer them on; keep it in sync with the JavaScript when
the rule changes.

Two deliberate differences from the interface:

- The interface still derives a fallback weight for datasets written before
  Phase 1 weighed the events. The pipeline never sees such a dataset — Phase 1
  writes the weight — so an event without one simply scores zero here, and a
  dataset where that happens is outdated data to flag in ``data/outdated.md``
  and regenerate, not to select against.
- For an event with no ``involved_people`` the interface falls back to the
  names its text mentions. That matcher is heavyweight; here a connection
  counts when its normalized full name appears in the event's title or
  description, which errs only on the rare unlisted-mention case. The cost of
  a miss is one unwritten report, and the story then offers no layer there —
  the same quiet outcome as an unfilled life.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Set

from utils.person_matching import (
    MATCH_THRESHOLD,
    interface_score,
    normalize_person_name,
)

# Keep all three in sync with src/utils/story/eventDepth.js.
DEEP_EVENT_FLOOR = 0.35
MIN_DEPTH_SECTIONS = 2
MIN_DEPTH_ITEMS = 3

_TIFF = re.compile(r"\.tiff?(\?|$)", re.I)


def get_event_weight(event: Dict[str, Any]) -> float:
    """The stored Phase 1 weight, clamped to 0..1. Zero when absent."""
    weight = event.get("weight")
    if isinstance(weight, (int, float)):
        return min(max(float(weight), 0.0), 1.0)
    return 0.0


def _valid_images(images: Any) -> List[Dict[str, Any]]:
    """The images the interface would show: a parseable, non-TIFF URL."""
    if not isinstance(images, list):
        return []
    kept = []
    for image in images:
        url = image if isinstance(image, str) else (image or {}).get("url")
        if not isinstance(url, str) or not url or _TIFF.search(url):
            continue
        if "://" not in url:
            continue
        kept.append({"url": url} if isinstance(image, str) else image)
    return kept


def _relevant_people(
    event: Dict[str, Any], ego_network: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """The connections the story would offer as chips on this event."""
    connections = (ego_network or {}).get("connections")
    if not isinstance(connections, list):
        return []

    involved = [
        normalized
        for name in (event.get("involved_people") or [])
        if isinstance(name, str)
        and (normalized := normalize_person_name(name)) is not None
    ]
    if involved:
        matched = []
        for connection in connections:
            conn_name = normalize_person_name(str(connection.get("person_name") or ""))
            if conn_name is None:
                continue
            best = max(
                (interface_score(person, conn_name) for person in involved),
                default=0.0,
            )
            if best < MATCH_THRESHOLD:
                continue
            matched.append(connection)
        return matched[:5]

    # Mention fallback, approximated: the connection's normalized full name
    # somewhere in the event's own text.
    text = f"{event.get('title') or ''} {event.get('description') or ''}".lower()
    mentioned = []
    for connection in connections:
        name = normalize_person_name(str(connection.get("person_name") or ""))
        if name is None or not name["fullName"]:
            continue
        if name["fullName"].lower() in text:
            mentioned.append(connection)
    return mentioned[:5]


def get_event_depth_counts(
    event: Dict[str, Any], ego_network: Dict[str, Any]
) -> Dict[str, int]:
    """How much material a layer under this event would have to show.

    The background itself is deliberately not counted, exactly as in the
    interface: the counts decide which events get a report, and letting a
    written report feed the selection would make it drift as the corpus fills.
    """
    places = [
        location
        for location in (event.get("locations") or [])
        if isinstance(location, dict)
        and (location.get("name_historic") or location.get("name_modern"))
    ]
    terms = [
        term
        for term, annotation in (event.get("annotations") or {}).items()
        if isinstance(annotation, dict) and annotation.get("explanation")
    ]
    images = [
        image
        for image in _valid_images(event.get("images"))
        if image.get("caption") or image.get("creator") or image.get("source")
    ]
    people = _relevant_people(event, ego_network)
    sources = [
        url for url in (event.get("sources") or []) if isinstance(url, str) and url
    ]
    sections = [places, terms, images, people, sources]
    return {
        "item_count": sum(len(section) for section in sections),
        "section_count": sum(1 for section in sections if section),
    }


def select_deep_event_indexes(
    events: List[Dict[str, Any]], ego_network: Dict[str, Any]
) -> Set[int]:
    """Which events of one life open a depth layer: the story's own rule."""
    best: Dict[str, Dict[str, Any]] = {}
    for index, event in enumerate(events):
        weight = get_event_weight(event)
        if weight < DEEP_EVENT_FLOOR:
            continue
        depth = get_event_depth_counts(event, ego_network)
        if (
            depth["section_count"] < MIN_DEPTH_SECTIONS
            or depth["item_count"] < MIN_DEPTH_ITEMS
        ):
            continue
        chapter = str(event.get("chapter") or "")
        held = best.get(chapter)
        # Ties go to the earlier event, exactly as in the interface.
        if held is None or weight > held["weight"]:
            best[chapter] = {"index": index, "weight": weight}
    return {candidate["index"] for candidate in best.values()}
