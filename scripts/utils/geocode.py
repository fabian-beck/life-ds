#!/usr/bin/env python3
"""Resolving a place name to coordinates, through Nominatim and a cache.

Lifted out of ``generate_person_events.py``, where it sat among the dataset's
prompts and schemas as roughly two hundred lines that had nothing to do with
either. It is a client for an external service with a rate limit and an
on-disk cache — the same shape as ``wikipedia_cache``, and it belongs beside
it rather than inside the generator, which is also why ``review_person.py``
could reach it without importing a 5,600-line module.

Three things the module is careful about, all of them about not asking twice:

**The throttle.** Nominatim's usage policy allows one request a second, so
requests are spaced by wall clock rather than by politeness in the caller.

**The cache.** A definitive answer — including "this place does not resolve" —
is written to disk, so a later run never asks about Berlin again.

**The difference between a miss and an outage.** A place that genuinely cannot
be resolved is remembered forever; a lookup that failed for what looks like a
transient reason is remembered only for this run, so the next one tries again.
That distinction is why the failure set is separate from the cache.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import requests

from .wikipedia_cache import wikipedia_headers

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

GEOCODER_ENDPOINT = os.getenv(
    "LIFE_DS_GEOCODER_ENDPOINT",
    "https://nominatim.openstreetmap.org/search",
)
GEOCODER_DELAY_SECONDS = float(os.getenv("LIFE_DS_GEOCODER_DELAY", "1.0"))
GEOCODER_MAX_RESULTS = 1
GEOCODER_MAX_ATTEMPTS = max(1, int(os.getenv("LIFE_DS_GEOCODER_ATTEMPTS", "3")))
GEOCODE_CACHE_PATH = Path(
    os.getenv("LIFE_DS_GEOCODE_CACHE", str(DATA_DIR / "_cache" / "geocode.json"))
)
UNKNOWN_LOCATION_LABEL = "Location unknown"

# Definitive answers, including "this place cannot be resolved". Persisted to
# GEOCODE_CACHE_PATH, so a later run does not ask Nominatim about Berlin again.
_geocode_cache: Dict[str, Optional[Dict[str, Any]]] = {}
_geocode_cache_loaded = False
# Queries whose lookup kept failing for what looks like a transient reason.
# Held for this run only, so the next run gets to try them again.
_geocode_failures: Set[str] = set()
_last_geocode_at: float = 0.0


def normalize_location_text(value: str) -> str:
    """Collapse whitespace and strip the punctuation a list leaves behind."""
    return re.sub(r"\s+", " ", value).strip(",; ")


def geocoder_headers() -> Dict[str, str]:
    headers = wikipedia_headers()
    headers.setdefault("Accept-Language", "en")
    headers.setdefault("Accept", "application/json")
    return headers


def _throttle_geocoder() -> None:
    global _last_geocode_at
    if GEOCODER_DELAY_SECONDS <= 0:
        return
    now = time.monotonic()
    elapsed = now - _last_geocode_at
    if elapsed < GEOCODER_DELAY_SECONDS:
        time.sleep(GEOCODER_DELAY_SECONDS - elapsed)
    _last_geocode_at = time.monotonic()


def _generate_location_candidates(query: str) -> List[str]:
    candidates: List[str] = []
    seen: Set[str] = set()

    def add(value: str) -> None:
        if not value:
            return
        key = value.casefold()
        if key in seen:
            return
        seen.add(key)
        candidates.append(value)

    normalized = normalize_location_text(query)
    add(normalized)

    without_parentheses = re.sub(r"\s*\([^)]*\)", "", normalized)
    without_parentheses = normalize_location_text(without_parentheses)
    if without_parentheses and without_parentheses != normalized:
        add(without_parentheses)

    base_for_segments = without_parentheses or normalized
    segments = [
        segment.strip()
        for segment in re.split(r"\s*,\s*", base_for_segments)
        if segment.strip()
    ]
    if len(segments) > 1:
        for length in range(len(segments) - 1, 0, -1):
            add(", ".join(segments[:length]))
    if segments:
        add(segments[0])

    dashed = re.sub(r"\s*[-–—]\s*.*$", "", normalized)
    dashed = normalize_location_text(dashed)
    if dashed and dashed != normalized:
        add(dashed)

    return candidates


def _load_geocode_cache() -> None:
    """Read the persisted geocoder answers once per run."""
    global _geocode_cache_loaded
    if _geocode_cache_loaded:
        return
    _geocode_cache_loaded = True
    try:
        stored = json.loads(GEOCODE_CACHE_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return
    except (OSError, json.JSONDecodeError) as error:
        print(f"Warning: ignoring unreadable geocode cache: {error}")
        return
    if isinstance(stored, dict):
        for key, value in stored.items():
            if isinstance(key, str) and (value is None or isinstance(value, dict)):
                _geocode_cache[key] = value


def _remember_geocode(query: str, result: Optional[Dict[str, Any]]) -> None:
    """Record a definitive answer — a hit or a confirmed miss — and persist it."""
    if query in _geocode_cache and _geocode_cache[query] == result:
        return
    _geocode_cache[query] = result
    try:
        GEOCODE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        GEOCODE_CACHE_PATH.write_text(
            json.dumps(_geocode_cache, indent=2, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
    except OSError as error:
        print(f"Warning: could not write geocode cache: {error}")


def _request_geocoder(query: str) -> Optional[List[Dict[str, Any]]]:
    """Ask Nominatim for a place, retrying transient failures.

    Returns the result list, or None when every attempt failed — a failure that
    says nothing about whether the place exists, so it is not cached as a miss.
    """
    for attempt in range(1, GEOCODER_MAX_ATTEMPTS + 1):
        try:
            _throttle_geocoder()
            response = requests.get(
                GEOCODER_ENDPOINT,
                params={
                    "q": query,
                    "format": "jsonv2",
                    "limit": GEOCODER_MAX_RESULTS,
                },
                timeout=30,
                headers=geocoder_headers(),
            )
            response.raise_for_status()
            results: List[Dict[str, Any]] = response.json()
            return results
        except Exception as error:
            if attempt >= GEOCODER_MAX_ATTEMPTS:
                print(
                    f"Warning: geocoding lookup failed for '{query}' "
                    f"after {attempt} attempt(s): {error}"
                )
                return None
            time.sleep(GEOCODER_DELAY_SECONDS * attempt)
    return None


def _geocode_candidate(query: str) -> Optional[Dict[str, Any]]:
    _load_geocode_cache()
    if query in _geocode_cache:
        return _geocode_cache[query]
    if query in _geocode_failures:
        return None
    results = _request_geocoder(query)
    if results is None:
        _geocode_failures.add(query)
        return None
    if not results:
        _remember_geocode(query, None)
        return None
    primary = results[0]
    try:
        lon = float(str(primary.get("lon")))
        lat = float(str(primary.get("lat")))
    except (TypeError, ValueError):
        _remember_geocode(query, None)
        return None
    bbox_values: Optional[List[float]] = None
    raw_bbox = primary.get("boundingbox")
    if isinstance(raw_bbox, list) and len(raw_bbox) == 4:
        try:
            south, north, west, east = [float(value) for value in raw_bbox]
            bbox_values = [west, south, east, north]
        except (TypeError, ValueError):
            bbox_values = None
    result = {
        "name": query,
        "display_name": primary.get("display_name"),
        "lon": lon,
        "lat": lat,
        "bbox": bbox_values,
    }
    _remember_geocode(query, result)
    return result


def geocode_location(query: str) -> Optional[Dict[str, Any]]:
    normalized = normalize_location_text(query or "")
    if not normalized:
        return None
    if normalized.casefold() == UNKNOWN_LOCATION_LABEL.casefold():
        return None
    _load_geocode_cache()
    if normalized in _geocode_cache:
        return _geocode_cache[normalized]
    if normalized in _geocode_failures:
        return None

    for candidate in _generate_location_candidates(normalized):
        result = _geocode_candidate(candidate)
        if result:
            _remember_geocode(normalized, result)
            return result

    # Every spelling was tried. Remember the miss only when each one came back
    # with a real answer; a transient failure must not become a permanent no.
    if any(
        candidate in _geocode_failures
        for candidate in _generate_location_candidates(normalized)
    ):
        _geocode_failures.add(normalized)
    else:
        _remember_geocode(normalized, None)
    return None
