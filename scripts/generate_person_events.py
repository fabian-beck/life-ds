#!/usr/bin/env python3
"""
Generate life event datasets using a multi-phase approach:
1. Phase 1: Generate event skeletons (title, date, description)
2. Phase 2: Research details for each event (location, people, sources, icon)
3. Chapter Generation: Create life chapters based on established events (with involved_people, location)
4. Phase 3: Discover and assign event-specific images

This script replaces generate_person_dataset.py with improved accuracy and richer metadata.
"""

import argparse
import json
import os
import re
import sys
import time
from calendar import monthrange
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Set
from urllib.parse import quote

import requests
from openai import APIStatusError, OpenAI
from pydantic import BaseModel, Field

from config import DEFAULT_MODEL, DEFAULT_REASONING_EFFORT, LOW_REASONING_EFFORT
from icon_categories import ICON_CATEGORIES, format_icon_categories_for_prompt
from utils.wikipedia_cache import (
    get_cached_wikipedia_page,
    get_cached_wikipedia_summary,
    get_cached_commons_images,
    ensure_cache,
    get_cache_dir,
)

# Import from cache_wikipedia_materials for related articles functionality
try:
    from cache_wikipedia_materials import fetch_related_articles
except ImportError:
    fetch_related_articles = None

# Constants
DATASET_NAME = "Life Data Stories"
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
REGISTER_PATH = DATA_DIR / "persons.json"
PEOPLE_DIR = DATA_DIR / "people"
MEDIAWIKI_API = "https://en.wikipedia.org/w/api.php"
WIKIPEDIA_SUMMARY_API = "https://en.wikipedia.org/api/rest_v1/page/summary/"
DEFAULT_USER_AGENT = (
    "life-ds-data-generator/1.0 (+https://github.com/fabian-beck/life-ds)"
)
GEOCODER_ENDPOINT = os.getenv(
    "LIFE_DS_GEOCODER_ENDPOINT",
    "https://nominatim.openstreetmap.org/search",
)
GEOCODER_DELAY_SECONDS = float(os.getenv("LIFE_DS_GEOCODER_DELAY", "1.0"))
GEOCODER_MAX_RESULTS = 1
UNKNOWN_LOCATION_LABEL = "Location unknown"

# Global caches
_geocode_cache: Dict[str, Optional[Dict[str, Any]]] = {}
_last_geocode_at: float = 0.0
_wikipedia_lang: Optional[str] = None


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class ImageMetadata(BaseModel):
    """Metadata for an image associated with an event."""
    url: str = Field(description="The full URL of the image")
    caption: str = Field(
        description="A concise, factual description of what the image shows"
    )
    source: str = Field(
        description="The source URL, typically a Wikimedia Commons page"
    )


class Annotation(BaseModel):
    """Explanation for an annotated term in event description."""
    explanation: str = Field(description="Clear, concise explanation (1-2 sentences)")
    wikipedia_url: Optional[str] = Field(
        None,
        description="Optional Wikipedia URL for further reading"
    )


class Portrait(BaseModel):
    """Portrait information for the person."""
    image: Optional[str] = Field(None, description="URL of the portrait image")
    source: Optional[str] = Field(None, description="Source URL for the portrait")


class Person(BaseModel):
    """Metadata about the person."""
    name: str = Field(description="Full name of the person")
    birth_date: Optional[str] = Field(None, description="Birth date in ISO-8601 format")
    death_date: Optional[str] = Field(None, description="Death date in ISO-8601 format")
    primary_roles: List[str] = Field(description="Primary roles or professions")
    summary: str = Field(description="Brief biographical summary")
    wikipedia: Optional[str] = Field(None, description="Wikipedia URL")
    portrait: Optional[Portrait] = Field(None, description="Portrait information")


class LifeChapter(BaseModel):
    """A chapter grouping a sequence of life events."""
    id: str = Field(
        description="Unique identifier for the chapter (lowercase, snake_case)"
    )
    headline: str = Field(
        description="Short, evocative chapter headline (3-6 words). Avoid using 'and' - prefer more specific, focused headlines.")
    description: str = Field(
        description="Brief description of this life period (1-2 sentences)"
    )
    date_start: str = Field(
        description="ISO-8601 date when this chapter begins (YYYY-MM-DD, YYYY-MM, or YYYY)"
    )
    date_start_precision: str = Field(
        description="Precision level for start date: 'day', 'month', or 'year'"
    )
    date_end: str = Field(
        description="ISO-8601 date when this chapter ends (YYYY-MM-DD, YYYY-MM, or YYYY)"
    )
    date_end_precision: str = Field(
        description="Precision level for end date: 'day', 'month', or 'year'"
    )
    age_start: Optional[int] = Field(
        None, description="Subject's age at chapter start, null if not applicable"
    )
    age_end: Optional[int] = Field(
        None, description="Subject's age at chapter end, null if not applicable"
    )
    involved_people: Optional[List[str]] = Field(
        None,
        description="Names of key people involved during this life chapter (aggregated from events, exclude the main subject)"
    )
    location: Optional[str] = Field(
        None,
        description="Summary of the main geographic area for this chapter (e.g., 'England', 'United States', 'Central Europe') - not a list of places"
    )


class ChapterGenerationOutput(BaseModel):
    """Output model for chapter generation phase."""
    chapters: List[LifeChapter] = Field(
        description="List of life chapters grouping the events"
    )


# Phase 1 Models

class EventSkeleton(BaseModel):
    """Phase 1: Minimal event structure for planning the narrative."""
    date: str = Field(description="ISO-8601 date string (YYYY-MM-DD, YYYY-MM, or YYYY)")
    date_precision: str = Field(
        description="Precision level: 'day', 'month', or 'year'"
    )
    date_end: Optional[str] = Field(
        None, description="Optional end date for events spanning a range"
    )
    date_end_precision: Optional[str] = Field(
        None, description="Precision for the end date"
    )
    date_note: Optional[str] = Field(
        None, description="Note about date uncertainty or alternative representations"
    )
    age: Optional[int] = Field(
        None,
        description="Subject's age at the time of the event, null if not applicable",
    )
    title: str = Field(description="Brief title of the event (2-6 words)")
    description: str = Field(description="Detailed description of the event (2-4 sentences)")
    annotations: Optional[Dict[str, Annotation]] = Field(
        None,
        description="Dictionary mapping term keys to their explanations"
    )


class LifePlan(BaseModel):
    """Phase 1 output: Person metadata and event skeletons."""
    dataset: str = Field(description="Name of the dataset")
    created_on: str = Field(description="Creation date in ISO-8601 format")
    person: Person = Field(description="Person metadata")
    event_skeletons: List[EventSkeleton] = Field(
        description="List of event skeletons (minimal event data)"
    )


# Phase 2 Models

class LocationInfo(BaseModel):
    """Location information with historic and modern names."""
    name_historic: str = Field(
        description="Location name at time of event (e.g., 'Königsberg', 'Ceylon')"
    )
    name_modern: Optional[str] = Field(
        None,
        description="Modern geographic name for geocoding (e.g., 'Kaliningrad, Russia')"
    )
    centroid: Optional[List[float]] = Field(
        None,
        description="[longitude, latitude] coordinates, or null if not geocoded"
    )
    primary: bool = Field(
        default=True,
        description="True if this is the primary/main location"
    )


class EventDetails(BaseModel):
    """Phase 2: Research details for a specific event (NO images - handled in Phase 3)."""
    description: Optional[str] = Field(
        None,
        description="Event description with [[term|display]] markers for annotations. If no annotations, return the original description unchanged."
    )
    locations: Optional[List[LocationInfo]] = Field(
        None,
        description="Array of location objects. Can be empty or contain multiple locations."
    )
    involved_people: Optional[List[str]] = Field(
        None,
        description="Names of people directly involved in this event (exclude the main subject)"
    )
    sources: List[str] = Field(
        default_factory=list,
        description="Array of Wikipedia URLs or references supporting this event"
    )
    event_type_icon: Optional[str] = Field(
        None,
        description="MDI icon identifier (e.g., 'mdi-crown', 'mdi-book')"
    )
    annotations: Optional[Dict[str, Annotation]] = Field(
        None,
        description="Dictionary mapping term keys to their explanations"
    )


# Final Model

class LifeEvent(BaseModel):
    """Final merged event (skeleton + details)."""
    date: str = Field(description="ISO-8601 date string")
    date_precision: str = Field(description="Precision level")
    date_end: Optional[str] = None
    date_end_precision: Optional[str] = None
    date_note: Optional[str] = None
    age: Optional[int] = None
    title: str = Field(description="Brief title of the event")
    description: str = Field(description="Detailed description")
    locations: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Unified location array with name_historic/name_modern/centroid/primary"
    )
    involved_people: Optional[List[str]] = Field(
        None,
        description="People directly involved in this event"
    )
    sources: List[str] = Field(description="Array of Wikipedia URLs or references")
    images: Optional[List[ImageMetadata]] = None
    event_type_icon: Optional[str] = Field(
        None,
        description="MDI icon identifier"
    )
    chapter: Optional[str] = Field(None, description="Chapter ID this event belongs to")
    annotations: Optional[Dict[str, Annotation]] = Field(
        None,
        description="Dictionary mapping term keys to their explanations"
    )


# ============================================================================
# UTILITY FUNCTIONS (copied from generate_person_dataset.py)
# ============================================================================

def _strip_wrapping_quotes(value: str) -> str:
    trimmed = value.strip()
    quotes = "\"'""''"
    while len(trimmed) >= 2 and trimmed[0] in quotes and trimmed[-1] in quotes:
        trimmed = trimmed[1:-1].strip()
    return trimmed


def _clean_date_note_text(note: str) -> str:
    cleaned = note.strip()
    prefix_patterns = [
        r"^Described in the source as\s+",
        r"^Described as\s+",
        r"^Documented as\s+",
        r"^Recorded as\s+",
        r"^Listed as\s+",
        r"^Reported as\s+",
        r"^Referenced as\s+",
        r"^(?:The\s+)?source\s+(?:notes|indicates|describes|lists|states)\s+(?:that\s+|it\s+as\s+)?",
        r"^(?:According to|Per)\s+the\s+source,\s*",
    ]
    for pattern in prefix_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    cleaned = _strip_wrapping_quotes(cleaned)
    cleaned = cleaned.rstrip(" .:;")
    return cleaned.strip()


def _split_date_annotation(value: str) -> Tuple[str, Optional[str], bool]:
    text = value.strip()
    prefer_note = False
    note = None
    match = re.match(r"^(.*?)\(([^()]*)\)\s*$", text)
    if match:
        base = match.group(1).strip(",; ")
        note_candidate = _clean_date_note_text(match.group(2))
        if note_candidate:
            note = note_candidate
            prefer_note = True
        text = base or text
    return text.strip(), note, prefer_note


def _normalize_location_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(",; ")


def _strip_html_tags(value: str) -> str:
    clean = re.sub(r"<[^>]+>", "", value)
    clean = clean.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    clean = clean.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
    clean = " ".join(clean.split())
    return clean.strip()


def _clean_candidate_name(value: Optional[str]) -> Optional[str]:
    if not value or not isinstance(value, str):
        return None
    cleaned = _strip_html_tags(value)
    cleaned = cleaned.replace("\xa0", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,;:\u00b7")
    return cleaned or None


def _collect_person_name_candidates(
    person: Dict[str, Any],
    page_data: Dict[str, Any],
    summary_data: Optional[Dict[str, Any]] = None,
) -> List[str]:
    candidates: List[str] = []
    seen: Set[str] = set()

    def push(raw: Optional[str]) -> None:
        cleaned = _clean_candidate_name(raw)
        if not cleaned:
            return
        key = cleaned.casefold()
        if key in seen:
            return
        seen.add(key)
        candidates.append(cleaned)

        if "," in cleaned:
            primary = cleaned.split(",", 1)[0].strip()
            primary_clean = _clean_candidate_name(primary)
            if primary_clean:
                primary_key = primary_clean.casefold()
                if primary_key not in seen:
                    seen.add(primary_key)
                    candidates.append(primary_clean)

        simplified_parentheses = re.sub(r"\s*\([^)]*\)", "", cleaned).strip()
        simplified_parentheses = _clean_candidate_name(simplified_parentheses)
        if simplified_parentheses:
            simple_key = simplified_parentheses.casefold()
            if simple_key not in seen:
                seen.add(simple_key)
                candidates.append(simplified_parentheses)

    push(person.get("name"))
    push(person.get("preferred_name"))
    push(page_data.get("title"))
    push(page_data.get("displaytitle"))

    if summary_data:
        push(summary_data.get("title"))
        push(summary_data.get("displaytitle"))
        titles = summary_data.get("titles")
        if isinstance(titles, dict):
            for value in titles.values():
                push(value)

    return candidates


def _name_score(value: str) -> Tuple[int, int, int]:
    punctuation_penalty = 0
    for symbol, weight in ((",", 3), ("(", 2), (")", 2), (";", 1), (":", 1)):
        punctuation_penalty += value.count(symbol) * weight
    word_count = len(value.split())
    length_penalty = len(value)
    return punctuation_penalty, word_count, length_penalty


def normalize_date_value(value: str, precision: str) -> tuple[Any, str]:
    if value is None:
        return None, precision
    sanitized = str(value).strip()
    if not sanitized:
        return None, precision
    level = precision.lower()
    if level not in {"day", "month", "year"}:
        level = "day"

    if level == "day":
        candidate = sanitized[:10]
        try:
            datetime.strptime(candidate, "%Y-%m-%d")
            return candidate, "day"
        except ValueError:
            level = "month"

    if level == "month":
        candidate = sanitized[:7]
        try:
            datetime.strptime(candidate, "%Y-%m")
            return candidate, "month"
        except ValueError:
            level = "year"

    match = re.search(r"\d{4}", sanitized)
    if match:
        return match.group(0), "year"

    return None, "unknown"


def event_sort_key(event: Dict[str, Any]) -> str:
    date_value = event.get("date")
    precision = (event.get("date_precision") or "day").lower()
    if not date_value:
        return "9999-12-31"
    if precision == "year":
        return f"{date_value}-12-31"
    if precision == "month":
        return f"{date_value}-28"
    return str(date_value)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.strip().lower())
    return slug.strip("_") or "person"


def wikipedia_headers() -> Dict[str, str]:
    user_agent = os.getenv("WIKIPEDIA_USER_AGENT", DEFAULT_USER_AGENT)
    return {"User-Agent": user_agent}


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

    normalized = _normalize_location_text(query)
    add(normalized)

    without_parentheses = re.sub(r"\s*\([^)]*\)", "", normalized)
    without_parentheses = _normalize_location_text(without_parentheses)
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
    dashed = _normalize_location_text(dashed)
    if dashed and dashed != normalized:
        add(dashed)

    return candidates


def _geocode_candidate(query: str) -> Optional[Dict[str, Any]]:
    cached = _geocode_cache.get(query)
    if cached is not None:
        return cached
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
    except Exception as error:
        print(f"Warning: geocoding lookup failed for '{query}': {error}")
        _geocode_cache[query] = None
        return None
    if not results:
        _geocode_cache[query] = None
        return None
    primary = results[0]
    try:
        lon = float(primary.get("lon"))
        lat = float(primary.get("lat"))
    except (TypeError, ValueError):
        _geocode_cache[query] = None
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
    _geocode_cache[query] = result
    return result


def geocode_location(query: str) -> Optional[Dict[str, Any]]:
    normalized = _normalize_location_text(query or "")
    if not normalized:
        return None
    if normalized.casefold() == UNKNOWN_LOCATION_LABEL.casefold():
        return None
    cached = _geocode_cache.get(normalized)
    if cached is not None:
        return cached

    for candidate in _generate_location_candidates(normalized):
        result = _geocode_candidate(candidate)
        if result:
            _geocode_cache[normalized] = result
            return result

    _geocode_cache[normalized] = None
    return None


def _upper_bound_date(value: Optional[str], precision: str) -> Optional[date]:
    """Convert varying precision date strings into a comparable upper bound."""
    if not value:
        return None
    normalized_precision = (precision or "day").lower()
    try:
        if normalized_precision == "day":
            return datetime.strptime(value, "%Y-%m-%d").date()
        if normalized_precision == "month":
            year, month = [int(part) for part in value.split("-")[:2]]
            last_day = monthrange(year, month)[1]
            return date(year, month, last_day)
        if normalized_precision == "year":
            year = int(value[:4])
            return date(year, 12, 31)
    except (ValueError, TypeError):
        return None
    return None


# ============================================================================
# WIKIPEDIA DATA FETCHING (copied from generate_person_dataset.py)
# ============================================================================

def extract_wikipedia_title(url_or_subject: str) -> Optional[Tuple[str, str]]:
    """Extract Wikipedia article title and language code from a URL."""
    from urllib.parse import urlparse, unquote

    url_or_subject = url_or_subject.strip()

    if not (
        url_or_subject.startswith("http://") or url_or_subject.startswith("https://")
    ):
        return None

    try:
        parsed = urlparse(url_or_subject)

        if not parsed.netloc or "wikipedia.org" not in parsed.netloc:
            return None

        domain_parts = parsed.netloc.split(".")
        if (
            len(domain_parts) >= 2
            and domain_parts[-2] == "wikipedia"
            and domain_parts[-1] == "org"
        ):
            lang_code = domain_parts[0]
        else:
            lang_code = "en"

        path_parts = parsed.path.split("/")
        if len(path_parts) >= 3 and path_parts[1] == "wiki":
            title = "/".join(path_parts[2:])
            title = unquote(title)
            title = title.replace("_", " ")
            return (title, lang_code)

        return None
    except Exception:
        return None


def _fetch_wikipedia_page(title: str, lang: Optional[str] = None) -> Dict[str, Any]:
    language = lang or _wikipedia_lang or "en"
    api_url = f"https://{language}.wikipedia.org/w/api.php"

    params = {
        "action": "query",
        "format": "json",
        "prop": "extracts|pageimages|info|images",
        "explaintext": 1,
        "redirects": 1,
        "inprop": "url",
        "piprop": "original",
        "titles": title,
        "imlimit": 100,
    }
    response = requests.get(
        api_url,
        params=params,
        timeout=30,
        headers=wikipedia_headers(),
    )
    response.raise_for_status()
    data = response.json()
    pages = data.get("query", {}).get("pages", {})
    if not pages:
        raise ValueError(f"No Wikipedia page found for '{title}'.")
    page = next(iter(pages.values()))
    if "missing" in page:
        raise ValueError(f"Wikipedia page for '{title}' is missing.")
    return page


def wikipedia_search_titles(query: str, limit: int = 5) -> List[str]:
    params = {
        "action": "query",
        "format": "json",
        "list": "search",
        "srsearch": query,
        "srlimit": limit,
        "srnamespace": 0,
    }
    response = requests.get(
        MEDIAWIKI_API,
        params=params,
        timeout=30,
        headers=wikipedia_headers(),
    )
    response.raise_for_status()
    data = response.json()
    results = data.get("query", {}).get("search", [])
    titles: List[str] = [item.get("title") for item in results if item.get("title")]
    suggestion = data.get("query", {}).get("searchinfo", {}).get("suggestion")
    if suggestion:
        titles.append(suggestion)
    return titles


def fetch_wikipedia_extract(title: str) -> Dict[str, Any]:
    """Fetch Wikipedia article with fallback search."""
    url_info = extract_wikipedia_title(title)
    if url_info:
        article_title, lang_code = url_info
        print(
            f"Detected Wikipedia URL, using article: '{article_title}' (language: {lang_code})"
        )
        return _fetch_wikipedia_page(article_title, lang=lang_code)

    candidates: List[str] = []
    seen: Set[str] = set()
    attempted: List[str] = []

    def add_candidate(value: str) -> None:
        candidate = (value or "").strip()
        if not candidate:
            return
        key = candidate.casefold()
        if key in seen:
            return
        seen.add(key)
        candidates.append(candidate)

    add_candidate(title)
    normalized_title = title.replace("_", " ")
    if normalized_title.casefold() != title.casefold():
        add_candidate(normalized_title)
    parenthetical = re.sub(r"\s*\([^)]*\)", "", normalized_title).strip()
    if parenthetical and parenthetical.casefold() not in {
        title.casefold(),
        normalized_title.casefold(),
    }:
        add_candidate(parenthetical)

    index = 0
    search_enqueued = False
    errors: List[str] = []

    while True:
        while index < len(candidates):
            candidate = candidates[index]
            index += 1
            attempted.append(candidate)
            try:
                return _fetch_wikipedia_page(candidate)
            except ValueError as error:
                errors.append(str(error))

        if search_enqueued:
            break

        search_enqueued = True
        for suggestion in wikipedia_search_titles(title):
            add_candidate(suggestion)

    attempted_titles = ", ".join(attempted) if attempted else title
    error_details = "; ".join(dict.fromkeys(errors)) if errors else ""
    message = (
        "Unable to locate a Wikipedia page for "
        f"'{title}'. Tried titles: {attempted_titles}."
    )
    if error_details:
        message = f"{message} Details: {error_details}."
    raise ValueError(message)


def fetch_wikipedia_summary(title: str) -> Dict[str, Any]:
    """Fetch Wikipedia summary from REST API."""
    url = WIKIPEDIA_SUMMARY_API + quote(title.replace(" ", "_"))
    response = requests.get(url, timeout=30, headers=wikipedia_headers())
    if response.status_code != 200:
        return {}
    return response.json()


# ============================================================================
# COMMONS IMAGE SEARCH (for Phase 3)
# ============================================================================

def extract_keywords_from_description(
    description: str,
    max_keywords: int = 3
) -> List[str]:
    """
    Extract key terms from event description for image search.

    Focuses on proper nouns, technical terms, and significant concepts.
    """
    # Remove common words
    stopwords = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "as", "is", "was", "were", "been", "be",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "must", "this", "that", "these", "those"
    }

    # Extract capitalized terms (likely proper nouns)
    words = description.split()
    keywords = []

    for word in words:
        # Clean punctuation
        clean_word = re.sub(r'[^\w\s-]', '', word)

        # Keep if capitalized (but not sentence-start) or contains hyphen
        if clean_word and (clean_word[0].isupper() or '-' in clean_word):
            if clean_word.lower() not in stopwords:
                keywords.append(clean_word)

    # Deduplicate and limit
    seen = set()
    unique_keywords = []
    for kw in keywords:
        if kw.lower() not in seen:
            seen.add(kw.lower())
            unique_keywords.append(kw)

    return unique_keywords[:max_keywords]


def search_wikimedia_commons(
    query: str,
    limit: int = 5
) -> List[Dict[str, Any]]:
    """
    Search Wikimedia Commons using MediaWiki API.

    Returns list of image metadata dicts with url, caption, source, categories.
    """
    api_url = "https://commons.wikimedia.org/w/api.php"

    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": f"filetype:bitmap|drawing {query}",
        "gsrnamespace": 6,  # File namespace
        "gsrlimit": limit,
        "prop": "imageinfo|categories",
        "iiprop": "url|extmetadata",
        "iiurlwidth": 800,
        "cllimit": 50,
    }

    try:
        response = requests.get(
            api_url,
            params=params,
            timeout=30,
            headers=wikipedia_headers()
        )
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"    Commons API error: {e}")
        return []

    pages = data.get("query", {}).get("pages", {})
    images = []

    for page_id, page_data in pages.items():
        image_info = page_data.get("imageinfo", [{}])[0]
        url = image_info.get("url")

        if not url:
            continue

        # Extract caption from metadata
        extmetadata = image_info.get("extmetadata", {})
        caption = (
            extmetadata.get("ImageDescription", {}).get("value", "")
            or extmetadata.get("ObjectName", {}).get("value", "")
            or page_data.get("title", "").replace("File:", "")
        )
        caption = _strip_html_tags(caption)

        # Extract categories
        categories = [
            cat.get("title", "").replace("Category:", "")
            for cat in page_data.get("categories", [])
        ]

        # Build source URL
        source = f"https://commons.wikimedia.org/wiki/{page_data.get('title', '').replace(' ', '_')}"

        images.append({
            "url": url,
            "caption": caption,
            "source": source,
            "categories": categories,
        })

    return images


def search_commons_images_for_event(
    event_skeleton: EventSkeleton,
    event_details: EventDetails,
    person_name: str,
    max_results: int = 10
) -> List[Dict[str, Any]]:
    """
    Search Wikimedia Commons for images specifically relevant to this event.

    Builds targeted search queries from event context and fetches images.
    """
    # Build search queries from event context
    search_queries = []

    # Query 1: Event title + person name
    search_queries.append(f"{event_skeleton.title} {person_name}")

    # Query 2: Location names (if available)
    if event_details.locations:
        for loc in event_details.locations[:2]:  # Top 2 locations
            if loc.name_historic:
                search_queries.append(f"{loc.name_historic} {person_name}")

    # Query 3: Extract key terms from description
    description_keywords = extract_keywords_from_description(
        event_skeleton.description, max_keywords=3
    )
    if description_keywords:
        search_queries.append(f"{' '.join(description_keywords)} {person_name}")

    # Fetch images for each query
    all_images = []
    for query in search_queries[:3]:  # Max 3 queries per event
        try:
            images = search_wikimedia_commons(query, limit=5)
            all_images.extend(images)
        except Exception as e:
            print(f"    Warning: Commons search failed for '{query}': {e}")

    # Deduplicate by URL
    seen_urls = set()
    unique_images = []
    for img in all_images:
        if img['url'] not in seen_urls:
            seen_urls.add(img['url'])
            unique_images.append(img)

    return unique_images[:max_results]


def is_caption_similar_to_any(
    caption: str,
    used_captions: Set[str],
    threshold: float = 0.7
) -> bool:
    """Check if caption is too similar to any used caption."""
    from difflib import SequenceMatcher

    caption_lower = caption.lower()

    for used in used_captions:
        similarity = SequenceMatcher(None, caption_lower, used.lower()).ratio()
        if similarity > threshold:
            return True

    return False


def is_generic_portrait(img: Dict[str, Any]) -> bool:
    """Detect generic portrait photos."""
    caption = img.get('caption', '').lower()
    categories = [cat.lower() for cat in img.get('categories', [])]

    # Pattern matching in caption
    portrait_patterns = [
        r'\bportrait\b',
        r'\bphoto(?:graph)?\s+of\b',
        r'\bheadshot\b',
        r'\bhead\s+and\s+shoulders\b',
        r'\b(?:formal|official)\s+photo',
    ]

    for pattern in portrait_patterns:
        if re.search(pattern, caption):
            return True

    # Check categories
    portrait_category_keywords = ['portrait', 'headshot', 'photograph of']
    for cat in categories:
        if any(keyword in cat for keyword in portrait_category_keywords):
            return True

    return False


def score_image_relevance(
    img: Dict[str, Any],
    event_skeleton: EventSkeleton
) -> float:
    """
    Score image relevance to event (0.0 to 1.0).

    Higher scores for:
    - Caption words matching event title/description
    - Categories matching event keywords
    - Specific artifacts/documents over generic scenes
    """
    score = 0.0

    caption = img.get('caption', '').lower()
    categories = [cat.lower() for cat in img.get('categories', [])]

    # Event context
    event_text = f"{event_skeleton.title} {event_skeleton.description}".lower()
    event_words = set(re.findall(r'\b\w{4,}\b', event_text))

    # Caption word overlap (weight: 0.5)
    caption_words = set(re.findall(r'\b\w{4,}\b', caption))
    overlap = len(event_words & caption_words)
    score += min(overlap * 0.1, 0.5)

    # Category relevance (weight: 0.3)
    category_text = ' '.join(categories)
    category_words = set(re.findall(r'\b\w{4,}\b', category_text))
    category_overlap = len(event_words & category_words)
    score += min(category_overlap * 0.1, 0.3)

    # Bonus for specific artifact types (weight: 0.2)
    artifact_keywords = [
        'manuscript', 'document', 'book', 'publication', 'letter',
        'building', 'monument', 'memorial', 'plaque', 'artifact',
        'machine', 'device', 'instrument', 'equipment'
    ]
    if any(keyword in caption or keyword in category_text for keyword in artifact_keywords):
        score += 0.2

    return min(score, 1.0)


def filter_images_for_event(
    images: List[Dict[str, Any]],
    event_skeleton: EventSkeleton,
    used_urls: Set[str],
    used_captions: Set[str]
) -> List[Dict[str, Any]]:
    """
    Apply intelligent filtering to remove poor candidates before AI selection.

    Filters out:
    - Already used URLs
    - Semantically similar captions
    - Generic portraits
    - Low relevance images
    """
    filtered = []

    for img in images:
        # Filter by URL
        if img['url'] in used_urls:
            continue

        # Filter by caption similarity
        if is_caption_similar_to_any(img['caption'], used_captions, threshold=0.7):
            continue

        # Filter generic portraits
        if is_generic_portrait(img):
            continue

        # Score relevance
        relevance = score_image_relevance(img, event_skeleton)
        img['relevance_score'] = relevance

        # Only include if meets threshold
        if relevance >= 0.3:  # Moderate threshold for pre-filtering
            filtered.append(img)

    # Sort by relevance
    filtered.sort(key=lambda x: x['relevance_score'], reverse=True)

    # Return top 5
    return filtered[:5]


# ============================================================================
# PHASE 1: EVENT SKELETON GENERATION
# ============================================================================

def build_phase1_prompt(
    page_data: Dict[str, Any],
    summary_data: Dict[str, Any],
    subject: str,
    related_articles: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    Build Phase 1 prompt for generating event skeletons and chapters.

    Focus on identifying significant life events and organizing them into chapters.
    NO location/image/source details (Phase 2 will research these).
    """
    summary_text = summary_data.get("extract", "").strip()
    extract_text = page_data.get("extract", "").strip()

    main_article_title = page_data.get('title', subject)

    combined = f"TARGET SUBJECT: {main_article_title}\n"
    combined += f"="*60 + "\n"
    combined += f"You are creating a biographical timeline for {main_article_title}.\n"
    combined += f"Focus ONLY on events from {main_article_title}'s life.\n"
    combined += f"="*60 + "\n\n"
    combined += f"MAIN ARTICLE\nPage title: {main_article_title}\nPage URL: {page_data.get('fullurl', '')}\n\n"

    if summary_text:
        combined += f"Summary snippet:\n{summary_text}\n\n"

    if extract_text:
        truncated = extract_text[:12000]
        combined += (
            f"Full extract (truncated to 12k characters if needed):\n{truncated}\n"
        )

    # Include related articles for broad context
    if related_articles and len(related_articles) > 0:
        combined += f"\n\n{'='*60}\nRELATED WIKIPEDIA ARTICLES - Additional context:\n{'='*60}\n"
        combined += f"IMPORTANT: These articles are for CONTEXT ONLY. They provide background information about topics, places, and people connected to {main_article_title}.\n"
        combined += f"DO NOT generate events about the people mentioned in these related articles. Generate events ONLY for {main_article_title}.\n\n"
        for idx, article in enumerate(related_articles, 1):
            combined += f"\n{'='*60}\n"
            combined += f"ARTICLE {idx}: {article.get('title', 'Unknown')}\n"
            combined += f"URL: {article.get('url', '')}\n"
            combined += f"{'='*60}\n\n"

            full_text = article.get("fullText", "")
            if full_text:
                combined += f"{full_text}\n"
            else:
                summary = article.get("summary", "")
                if summary:
                    combined += f"{summary}\n"

        combined += f"\n{'='*60}\n"
        combined += f"END OF RELATED ARTICLES ({len(related_articles)} total)\n"
        combined += f"{'='*60}\n"

    return combined


def call_openai_phase1(prompt: str, model: str) -> LifePlan:
    """
    Call OpenAI for Phase 1 using structured outputs.

    Returns:
        LifePlan with person metadata and event skeletons
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY environment variable is not set.")

    client = OpenAI(api_key=api_key)

    system = (
        "You are a meticulous historian creating biographical timeline outlines. "
        "Focus on identifying the most significant events in a person's life. "
        "Use ISO-8601 dates, include date_precision as 'day', "
        "'month', or 'year'. All output must be in English only, regardless of source language."
    )

    instructions = (
        "You will receive a main Wikipedia article about a specific person (the TARGET SUBJECT), plus several related articles for context. "
        "Your task is to create a biographical timeline for the TARGET SUBJECT ONLY - not any of the people mentioned in related articles. "
        "\n\nCRITICAL REQUIREMENT: Produce EXACTLY 12-16 significant life events for the TARGET SUBJECT. NO MORE, NO LESS. "
        "Quality over quantity - select only the most historically significant moments from the TARGET SUBJECT's life. "
        "\n\nCover the TARGET SUBJECT's early life, education, major accomplishments, and later years. "
        "Do not include events that occur after the TARGET SUBJECT's death or that focus on their legacy. "
        "\n\nREMINDER: You must output between 12 and 16 events total. If you find yourself creating more than 16 events, "
        "consolidate related events or remove less significant ones. "
        "\n\nIMPORTANT - Event Skeleton Guidelines:\n"
        "- Keep event titles crisp and concise (2-6 words)\n"
        "- Use active, specific language that captures the essence of the event\n"
        "- Avoid generic titles like 'Major Achievement' or 'Important Work'\n"
        "- Examples: 'Birth in London', 'Graduated from Oxford', 'Published First Novel', 'Appointed Prime Minister'\n"
        "- Write rich descriptions (2-4 sentences) that mention context, people involved, and places\n"
        "- DO NOT specify exact locations, images, or detailed sources (Phase 2 will research these)\n"
        "- DO mention places, people, and context in the description naturally\n"
        "\n\nEach event skeleton must provide: date (start of the event), date_precision, optional date_end/date_end_precision "
        "when the event spans a range, optional date_note for uncertainty, age (null if not applicable), "
        "title, and description. "
        "\nInclude person metadata with name, birth_date, death_date when known, primary_roles, summary, "
        "wikipedia URL, and portrait info if available."
    )

    try:
        response = client.responses.parse(
            model=model,
            reasoning={"effort": DEFAULT_REASONING_EFFORT},
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": instructions},
                {"role": "user", "content": prompt},
            ],
            text_format=LifePlan,
        )
    except APIStatusError as error:
        message = ""
        try:
            message = error.response.get("error", {}).get("message", "")
        except AttributeError:
            message = str(error)
        raise RuntimeError(
            "OpenAI API request failed (Phase 1). Verify model name, account access, and billing status. "
            f"Details: {error.status_code} {message}"
        ) from error

    if response.status == "failed":
        error_msg = (
            f"Response generation failed: {response.error}"
            if response.error
            else "Unknown error"
        )
        raise RuntimeError(f"Phase 1 AI call failed: {error_msg}")
    elif response.status != "completed":
        raise RuntimeError(f"Phase 1: Response has unexpected status: {response.status}")

    parsed = response.output_parsed
    if parsed is None:
        raise RuntimeError("Failed to parse structured output from model (Phase 1)")

    return parsed


# ============================================================================
# PHASE 2: EVENT DETAIL RESEARCH
# ============================================================================

def filter_related_articles_for_event(
    event_skeleton: EventSkeleton,
    all_related_articles: List[Dict[str, Any]],
    max_articles: int = 5
) -> List[Dict[str, Any]]:
    """
    Score and filter related articles for a specific event.

    Scoring:
    - Title keyword match: weight 3
    - Summary keyword match: weight 1
    - Title mentioned in event description: +100 boost

    Returns top N articles by score.
    """
    event_text = f"{event_skeleton.title} {event_skeleton.description}".lower()
    event_words = set(re.findall(r'\b\w{4,}\b', event_text))  # Words 4+ chars

    scored_articles = []
    for article in all_related_articles:
        title = article.get("title", "").lower()
        summary = article.get("summary", "").lower()

        title_words = set(re.findall(r'\b\w{4,}\b', title))
        summary_words = set(re.findall(r'\b\w{4,}\b', summary))

        title_overlap = len(event_words & title_words)
        summary_overlap = len(event_words & summary_words)

        score = (title_overlap * 3) + summary_overlap

        # Boost if article title mentioned in event description
        if title in event_skeleton.description.lower():
            score += 100

        scored_articles.append((score, article))

    # Sort by score descending, take top N
    scored_articles.sort(reverse=True, key=lambda x: x[0])
    return [article for score, article in scored_articles[:max_articles]]


def build_phase2_prompt(
    event_skeleton: EventSkeleton,
    person_name: str,
    filtered_related_articles: List[Dict[str, Any]],
) -> str:
    """
    Build Phase 2 prompt for single event detail research.

    Focus on specific details for THIS event only (NO images - Phase 3).
    """
    prompt = f"Research details for this specific event:\n\n"
    prompt += f"Title: {event_skeleton.title}\n"
    prompt += f"Date: {event_skeleton.date}\n"
    prompt += f"Description: {event_skeleton.description}\n"
    prompt += f"Subject: {person_name}\n\n"

    prompt += "="*60 + "\n"
    prompt += "TASK: Provide the following details for THIS specific event:\n"
    prompt += "="*60 + "\n\n"

    prompt += "0. DESCRIPTION (with annotation markers):\n"
    prompt += "   - Return the event description with [[term|display]] markers inserted for any annotations\n"
    prompt += "   - If you create annotations (section 6 below), you MUST insert the markers into this description\n"
    prompt += "   - If no annotations, return the original description text unchanged\n"
    prompt += "   - Example: If annotating 'Leopoldstadt', change 'Leopoldstadt district' to '[[Leopoldstadt|Leopoldstadt district]]'\n\n"

    prompt += "1. LOCATIONS (can be multiple):\n"
    prompt += "   - Identify ALL significant locations for THIS specific event\n"
    prompt += "   - IMPORTANT: Keep location names SHORT and at CITY LEVEL at maximum\n"
    prompt += "   - Do NOT include street addresses, building names, or exact venues\n"
    prompt += "   - For EACH location, provide:\n"
    prompt += "     * name_historic: City/region name at time (e.g., 'Königsberg', 'Ceylon', 'Cambridge')\n"
    prompt += "     * name_modern: Modern city/region for geocoding (e.g., 'Kaliningrad, Russia', 'Cambridge, UK')\n"
    prompt += "     * primary: true for main location, false for secondary\n"
    prompt += "   - Examples of GOOD location names:\n"
    prompt += "     * 'London' not 'Bletchley Park, Milton Keynes'\n"
    prompt += "     * 'Paris' not 'Sorbonne University, Paris'\n"
    prompt += "     * 'Berlin' not '10 Downing Street, Berlin'\n"
    prompt += "   - Multi-location examples:\n"
    prompt += "     * Voyages: departure port city + arrival port city\n"
    prompt += "     * Conferences: host city only (not venue name)\n"
    prompt += "     * Battles/campaigns: battle location cities/regions\n"
    prompt += "   - If truly unknown or non-geographic, return empty array\n"
    prompt += "   - For single-location events, provide one location with primary=true\n\n"

    prompt += "2. INVOLVED_PEOPLE:\n"
    prompt += "   - List people DIRECTLY involved in THIS specific event\n"
    prompt += f"   - EXCLUDE the main subject ({person_name})\n"
    prompt += "   - Examples: collaborators, opponents, witnesses, family members present\n"
    prompt += "   - Leave null if no other people directly involved\n\n"

    prompt += "3. SOURCES:\n"
    prompt += "   - Provide 1-3 Wikipedia URLs from the related articles below\n"
    prompt += "   - Only include articles that specifically support THIS event\n\n"

    prompt += "4. EVENT_TYPE_ICON:\n"
    prompt += "   - Select the most appropriate MDI icon from the categories below\n"
    prompt += "   - Based on the semantic type of this event\n\n"

    prompt += "5. ANNOTATIONS (0-3 per event, MOST EVENTS HAVE 0):\n"
    prompt += "   - CRITICAL: Be extremely conservative - only annotate truly obscure terms that need explanation\n"
    prompt += "   - STRICT CRITERIA: Term must be BOTH obscure AND provide non-obvious context\n"
    prompt += "   - Annotate ONLY:\n"
    prompt += "     * Highly technical/specialized concepts (e.g., 'Entscheidungsproblem', 'transautomatism')\n"
    prompt += "     * Obscure institutions with significant historical context (e.g., 'Bletchley Park' - secret codebreaking facility)\n"
    prompt += "     * Specialized movements/events requiring context (e.g., 'Anschluss' - Nazi annexation, 'documenta' - contemporary art exhibition)\n"
    prompt += "     * Regional terms unknown outside specific areas (e.g., 'Matura' - Austrian graduation exam)\n"
    prompt += "   - ABSOLUTE PROHIBITIONS (NEVER annotate):\n"
    prompt += "     * ANY person names - these are ALWAYS handled separately\n"
    prompt += "     * ANY major cities (Tokyo, Hamburg, Paris, London, Vienna, Berlin, New York, etc.)\n"
    prompt += "     * ANY countries or continents (Japan, Germany, USA, Europe, Asia, etc.)\n"
    prompt += "     * ANY common places (university, school, museum, gallery, studio, farmhouse, etc.)\n"
    prompt += "     * ANY well-known historical periods or events (WWII, Renaissance, Cold War, etc.)\n"
    prompt += "     * ANY basic artistic/cultural terms (exhibition, retrospective, painting, prize, award, etc.)\n"
    prompt += "     * ANY geographic features everyone knows (rivers, seas, mountains, islands, etc.)\n"
    prompt += "   - REDUNDANCY CHECK: Do NOT annotate if the description already explains the term\n"
    prompt += "     * BAD: Annotating 'Hitler Youth' if description says 'Nazi youth organization'\n"
    prompt += "     * BAD: Annotating 'Montessori' if description says 'child-centered education'\n"
    prompt += "     * GOOD: Annotating 'Leopoldstadt' if description only says 'district' without historical context\n"
    prompt += "   - VALUE TEST: Does this annotation add meaningful information the description lacks?\n"
    prompt += "   - GEOGRAPHY RULE: Only annotate very specific/obscure places with crucial historical significance\n"
    prompt += "     * GOOD: 'Leopoldstadt' (specific district with Holocaust context)\n"
    prompt += "     * BAD: 'Hamburg' (major German city everyone knows)\n"
    prompt += "     * BAD: 'Japan' (country everyone knows)\n"
    prompt += "     * BAD: 'Normandy' (well-known French region)\n"
    prompt += "   - EXAMPLES of GOOD annotations:\n"
    prompt += "     * 'Entscheidungsproblem' - mathematical concept requiring technical explanation\n"
    prompt += "     * 'Matura' - Austrian-specific term not used elsewhere\n"
    prompt += "     * 'documenta' - specific art event most people don't know\n"
    prompt += "   - EXAMPLES of BAD annotations (NEVER annotate):\n"
    prompt += "     * 'Hamburg' - major city\n"
    prompt += "     * 'Japan' - country\n"
    prompt += "     * 'Paris' - major city\n"
    prompt += "     * 'exhibition' - common term\n"
    prompt += "     * 'university' - common term\n"
    prompt += "     * Any person name\n"
    prompt += "   - Mark terms using [[term|display_text]] syntax\n"
    prompt += "   - Explanations must ADD information not in description (no redundancy)\n"
    prompt += "   - Optional: Include wikipedia_url for further reading\n"
    prompt += "   - DEFAULT to 0 annotations - when in doubt, DO NOT annotate\n\n"

    # Add icon categories
    prompt += "\n" + "="*60 + "\n"
    prompt += "AVAILABLE ICONS:\n"
    prompt += "="*60 + "\n"
    prompt += format_icon_categories_for_prompt()
    prompt += "\n"

    # Add filtered related articles
    if filtered_related_articles and len(filtered_related_articles) > 0:
        prompt += "\n" + "="*60 + "\n"
        prompt += f"RELATED ARTICLES (filtered for this event, top {len(filtered_related_articles)}):\n"
        prompt += "="*60 + "\n\n"
        for idx, article in enumerate(filtered_related_articles, 1):
            prompt += f"\nARTICLE {idx}: {article.get('title', 'Unknown')}\n"
            prompt += f"URL: {article.get('url', '')}\n"
            prompt += "-"*60 + "\n"

            full_text = article.get("fullText", "")
            if full_text:
                # Truncate to 1000 chars for prompt size
                truncated = full_text[:1000]
                prompt += f"{truncated}...\n\n"
            else:
                summary = article.get("summary", "")
                if summary:
                    prompt += f"{summary}\n\n"

    return prompt


def research_event_details(
    event_skeleton: EventSkeleton,
    person_name: str,
    all_related_articles: List[Dict[str, Any]],
    model: str,
    retry_count: int = 2
) -> EventDetails:
    """
    Research details for a single event with retry logic.

    Returns:
        EventDetails with locations, involved_people, sources, icon (NO images - Phase 3)
    """
    # Filter articles
    filtered_articles = filter_related_articles_for_event(
        event_skeleton, all_related_articles, max_articles=5
    )

    # Build prompt
    prompt = build_phase2_prompt(
        event_skeleton, person_name, filtered_articles
    )

    # Call AI with retries
    for attempt in range(retry_count + 1):
        try:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise RuntimeError("OPENAI_API_KEY environment variable is not set.")

            client = OpenAI(api_key=api_key)

            system = (
                "You are a research assistant specializing in biographical event details. "
                "Provide specific, factual information for the given event. "
                "All output must be in English only. Be precise with locations and people."
            )

            response = client.responses.parse(
                model=model,
                reasoning={"effort": LOW_REASONING_EFFORT},
                input=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                text_format=EventDetails,
            )

            if response.status == "completed" and response.output_parsed:
                return response.output_parsed

        except Exception as error:
            if attempt < retry_count:
                print(f"    Retry {attempt + 1}/{retry_count}")
                time.sleep(2)
            else:
                print(f"    Warning: Failed after {retry_count + 1} attempts, using fallback minimal details")
                # Fallback: minimal details
                return EventDetails(
                    locations=None,
                    involved_people=None,
                    sources=[],
                    event_type_icon="mdi-calendar"
                )

    # Should never reach here, but fallback just in case
    return EventDetails(
        locations=None,
        involved_people=None,
        sources=[],
        event_type_icon="mdi-calendar"
    )


def research_all_event_details(
    event_skeletons: List[EventSkeleton],
    person_name: str,
    all_related_articles: List[Dict[str, Any]],
    model: str,
) -> List[EventDetails]:
    """Research details for all events sequentially (NO images - Phase 3)."""
    details = []

    for idx, skeleton in enumerate(event_skeletons, 1):
        # Use ASCII-safe encoding for console output
        safe_title = skeleton.title.encode('ascii', 'replace').decode('ascii')
        print(f"  [{idx}/{len(event_skeletons)}] Researching: {safe_title}")

        detail = research_event_details(
            skeleton, person_name, all_related_articles, model
        )

        details.append(detail)

    return details


# ============================================================================
# EVENT MERGING
# ============================================================================

def merge_event_skeleton_and_details(
    skeleton: EventSkeleton,
    details: EventDetails
) -> LifeEvent:
    """Merge Phase 1 skeleton with Phase 2 details (NO images - Phase 3)."""

    # Build locations array from EventDetails.locations
    locations = []
    if details.locations and len(details.locations) > 0:
        for loc in details.locations:
            locations.append({
                "name_historic": loc.name_historic,
                "name_modern": loc.name_modern,
                "centroid": loc.centroid,
                "primary": loc.primary
            })

    # Merge annotations (prefer Phase 2 details, fallback to Phase 1 skeleton)
    annotations = details.annotations if details.annotations else skeleton.annotations

    # Merge description (prefer Phase 2 if provided with markers, else Phase 1)
    description = details.description if details.description else skeleton.description

    # Create merged event (NO images yet - assigned in Phase 3, NO chapter yet - assigned in Chapter phase)
    return LifeEvent(
        date=skeleton.date,
        date_precision=skeleton.date_precision,
        date_end=skeleton.date_end,
        date_end_precision=skeleton.date_end_precision,
        date_note=skeleton.date_note,
        age=skeleton.age,
        title=skeleton.title,
        description=description,
        locations=locations,
        involved_people=details.involved_people,
        sources=details.sources if details.sources else [],
        images=None,  # Images assigned in Phase 3
        event_type_icon=details.event_type_icon or "mdi-calendar",
        chapter=None,  # Chapter assigned in Chapter generation phase
        annotations=annotations,
    )


def merge_all_events(
    skeletons: List[EventSkeleton],
    details_list: List[EventDetails]
) -> List[LifeEvent]:
    """Merge all skeletons with their details."""
    if len(skeletons) != len(details_list):
        raise ValueError("Skeleton and details lists must have same length")

    return [
        merge_event_skeleton_and_details(skeleton, details)
        for skeleton, details in zip(skeletons, details_list)
    ]


# ============================================================================
# CHAPTER GENERATION PHASE
# ============================================================================

def build_chapter_generation_prompt(
    merged_events: List[LifeEvent],
    person_name: str,
    birth_date: Optional[str] = None,
    death_date: Optional[str] = None,
) -> str:
    """
    Build prompt for chapter generation based on established events.

    The prompt includes all event details so the AI can create meaningful chapters
    with involved_people and location aggregated from the events.
    """
    prompt = f"PERSON: {person_name}\n"
    if birth_date:
        prompt += f"Born: {birth_date}\n"
    if death_date:
        prompt += f"Died: {death_date}\n"
    prompt += f"\n{'='*60}\n"
    prompt += "ESTABLISHED LIFE EVENTS (chronologically ordered):\n"
    prompt += f"{'='*60}\n\n"

    for idx, event in enumerate(merged_events, 1):
        prompt += f"EVENT {idx}:\n"
        prompt += f"  Date: {event.date}"
        if event.date_end:
            prompt += f" to {event.date_end}"
        prompt += f" (precision: {event.date_precision})\n"
        if event.age is not None:
            prompt += f"  Age: {event.age}\n"
        prompt += f"  Title: {event.title}\n"
        prompt += f"  Description: {event.description}\n"

        if event.locations:
            locations_str = ", ".join([
                loc.get("name_modern") or loc.get("name_historic", "Unknown")
                for loc in event.locations
            ])
            prompt += f"  Locations: {locations_str}\n"

        if event.involved_people:
            prompt += f"  Involved people: {', '.join(event.involved_people)}\n"

        prompt += "\n"

    prompt += f"{'='*60}\n"
    prompt += f"Total: {len(merged_events)} events\n"

    return prompt


def call_openai_chapter_generation(
    prompt: str,
    model: str,
    retry_count: int = 2
) -> ChapterGenerationOutput:
    """
    Call OpenAI to generate chapters based on established events.

    Returns:
        ChapterGenerationOutput with list of chapters including involved_people and location
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY environment variable is not set.")

    client = OpenAI(api_key=api_key)

    system = (
        "You are a meticulous historian organizing biographical events into meaningful life chapters. "
        "Create coherent narrative groupings that represent distinct phases of the person's life. "
        "All output must be in English only."
    )

    instructions = (
        "Based on the established life events provided, create 3-5 meaningful life chapters that group these events.\n\n"
        "CHAPTER REQUIREMENTS:\n"
        "- Each chapter represents a distinct phase of the person's life\n"
        "- Chapters must be chronological and non-overlapping\n"
        "- The first chapter should start with or before the first event\n"
        "- The last chapter should end with or after the last event\n"
        "- Every event must belong to exactly one chapter based on its date\n\n"
        "CHAPTER STRUCTURE:\n"
        "- id: Unique identifier (lowercase, snake_case)\n"
        "- headline: Short, evocative headline (3-6 words). IMPORTANT: Avoid using 'and' in headlines - "
        "instead, choose a more focused, specific theme. For example, instead of 'Education and Early Career', "
        "use 'Academic Foundations' or 'Scholarly Beginnings'. Instead of 'War and Persecution', use 'Wartime Struggles'.\n"
        "- description: Brief description of this life period (1-2 sentences)\n"
        "- date_start, date_start_precision: When this chapter begins\n"
        "- date_end, date_end_precision: When this chapter ends\n"
        "- age_start, age_end: Subject's age at chapter start/end (null if not applicable)\n"
        "- involved_people: Aggregate the key people mentioned across all events in this chapter "
        "(exclude the main subject, include only significant individuals)\n"
        "- location: A summary of the main geographic area for this chapter - NOT a list of cities, but a regional summary. "
        "For example: 'England' (not 'London, Cambridge, Manchester'), 'United States' (not 'Princeton, New York, Boston'), "
        "'Central Europe' (not 'Vienna, Prague, Budapest'). Use the broadest appropriate region.\n\n"
        "HEADLINE GUIDELINES:\n"
        "- DO NOT use 'and' to combine two themes - pick the dominant theme\n"
        "- Good examples: 'Early Years in Vienna', 'Wartime Service', 'Academic Career', 'Literary Fame', 'Final Years'\n"
        "- Bad examples: 'Education and Career', 'War and Peace', 'Writing and Teaching'\n"
        "- Each headline should capture the essence of that life period in a focused way\n\n"
        "Analyze the events and create chapters that tell a coherent life story."
    )

    for attempt in range(retry_count + 1):
        try:
            response = client.responses.parse(
                model=model,
                reasoning={"effort": LOW_REASONING_EFFORT},
                input=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": instructions},
                    {"role": "user", "content": prompt},
                ],
                text_format=ChapterGenerationOutput,
            )

            if response.status == "completed" and response.output_parsed:
                return response.output_parsed

        except Exception as error:
            if attempt < retry_count:
                print(f"    Retry {attempt + 1}/{retry_count}")
                time.sleep(2)
            else:
                print(f"    Warning: Chapter generation failed after {retry_count + 1} attempts")
                raise RuntimeError(f"Chapter generation failed: {error}") from error

    raise RuntimeError("Chapter generation failed unexpectedly")


def assign_events_to_chapters(
    events: List[LifeEvent],
    chapters: List[LifeChapter]
) -> List[LifeEvent]:
    """
    Assign each event to the appropriate chapter based on date.

    Events are assigned to the chapter whose date range contains the event date.
    """
    # Sort chapters by start date
    sorted_chapters = sorted(chapters, key=lambda c: c.date_start)

    updated_events = []
    for event in events:
        event_date = event.date
        assigned_chapter = None

        # Find the chapter that contains this event's date
        for chapter in sorted_chapters:
            if chapter.date_start <= event_date:
                if chapter.date_end >= event_date:
                    assigned_chapter = chapter.id
                    break
                # If event is after this chapter's end, check next chapter
                # but keep this as fallback if no better match
                assigned_chapter = chapter.id

        # If no chapter found, assign to last chapter
        if not assigned_chapter and sorted_chapters:
            assigned_chapter = sorted_chapters[-1].id

        # Create updated event with chapter assignment
        updated_event = LifeEvent(
            date=event.date,
            date_precision=event.date_precision,
            date_end=event.date_end,
            date_end_precision=event.date_end_precision,
            date_note=event.date_note,
            age=event.age,
            title=event.title,
            description=event.description,
            locations=event.locations,
            involved_people=event.involved_people,
            sources=event.sources,
            images=event.images,
            event_type_icon=event.event_type_icon,
            chapter=assigned_chapter,
            annotations=event.annotations,
        )
        updated_events.append(updated_event)

    return updated_events


def generate_chapters_for_events(
    merged_events: List[LifeEvent],
    person_name: str,
    birth_date: Optional[str],
    death_date: Optional[str],
    model: str,
) -> Tuple[List[LifeChapter], List[LifeEvent]]:
    """
    Generate chapters for the established events and assign events to chapters.

    Returns:
        Tuple of (chapters, events_with_chapter_assignments)
    """
    # Build prompt with all event information
    prompt = build_chapter_generation_prompt(
        merged_events, person_name, birth_date, death_date
    )

    # Call AI to generate chapters
    chapter_output = call_openai_chapter_generation(prompt, model)

    # Assign events to chapters
    events_with_chapters = assign_events_to_chapters(
        merged_events, chapter_output.chapters
    )

    return chapter_output.chapters, events_with_chapters


# ============================================================================
# PHASE 3: EVENT-SPECIFIC IMAGE ASSIGNMENT
# ============================================================================

def assign_image_to_event(
    event_skeleton: EventSkeleton,
    event_details: EventDetails,
    filtered_images: List[Dict[str, Any]],
    person_name: str,
    model: str
) -> Optional[ImageMetadata]:
    """
    Use AI to select the best image for this event (or none).

    Returns ImageMetadata or None if no suitable image.
    """
    if not filtered_images:
        return None

    # Build conservative prompt
    prompt = f"Event: {event_skeleton.title}\n"
    prompt += f"Date: {event_skeleton.date}\n"
    prompt += f"Description: {event_skeleton.description}\n"
    prompt += f"Subject: {person_name}\n\n"

    prompt += "="*60 + "\n"
    prompt += "TASK: Select ONE image ONLY if truly relevant, otherwise select NONE\n"
    prompt += "="*60 + "\n\n"

    prompt += "STRICT CRITERIA FOR IMAGE SELECTION:\n"
    prompt += "Select an image ONLY if it directly depicts:\n"
    prompt += "  • A specific document/publication mentioned in this event\n"
    prompt += "  • A building/location where this event occurred\n"
    prompt += "  • An artifact/object central to this event\n"
    prompt += "  • A scene/moment directly showing this event\n\n"

    prompt += "ABSOLUTE PROHIBITIONS (NEVER select):\n"
    prompt += "  • Generic portraits of any person\n"
    prompt += "  • Images that could apply to multiple events\n"
    prompt += "  • Images from different time periods\n"
    prompt += "  • Tangentially related images\n\n"

    prompt += "CONSERVATIVE APPROACH:\n"
    prompt += "  • When in doubt, select NO IMAGE (return null)\n"
    prompt += "  • Better to have no image than a loosely related one\n"
    prompt += "  • Only 30-50% of events should have images\n\n"

    prompt += "="*60 + "\n"
    prompt += f"AVAILABLE IMAGES (pre-filtered, top {len(filtered_images)} candidates):\n"
    prompt += "="*60 + "\n\n"

    for idx, img in enumerate(filtered_images, 1):
        prompt += f"{idx}. {img.get('caption', 'Image')}\n"
        prompt += f"   URL: {img['url']}\n"
        prompt += f"   Relevance score: {img.get('relevance_score', 0):.2f}\n"
        if img.get('source'):
            prompt += f"   Source: {img['source']}\n"
        prompt += "\n"

    # Define response model
    class ImageSelectionResponse(BaseModel):
        selected_image_index: Optional[int] = Field(
            None,
            description="1-based index of selected image, or null if none suitable"
        )
        reason: str = Field(
            description="Brief explanation of selection or why no image selected"
        )

    # Call AI
    try:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return None

        client = OpenAI(api_key=api_key)

        system = (
            "You are a conservative image curator for biographical timelines. "
            "Only select images when they are truly relevant and add genuine value. "
            "Most events should have NO image."
        )

        response = client.responses.parse(
            model=model,
            reasoning={"effort": LOW_REASONING_EFFORT},
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            text_format=ImageSelectionResponse,
        )

        if response.status != "completed" or not response.output_parsed:
            return None

        selection = response.output_parsed

        # If no image selected, return None
        if selection.selected_image_index is None:
            return None

        # Validate index
        idx = selection.selected_image_index - 1  # Convert to 0-based
        if idx < 0 or idx >= len(filtered_images):
            return None

        # Return selected image
        selected = filtered_images[idx]
        return ImageMetadata(
            url=selected['url'],
            caption=selected['caption'],
            source=selected.get('source', '')
        )

    except Exception as e:
        print(f"    Warning: Image selection failed: {e}")
        return None


def research_images_for_all_events(
    merged_events: List[LifeEvent],
    event_skeletons: List[EventSkeleton],
    event_details_list: List[EventDetails],
    person_name: str,
    model: str
) -> List[LifeEvent]:
    """
    Phase 3: Event-specific image discovery and conservative assignment.

    For each event:
    1. Search Commons for event-specific images
    2. Apply intelligent filtering
    3. AI selects best image (or none)
    4. Track usage to prevent reuse
    """
    used_urls: Set[str] = set()
    used_captions: Set[str] = set()

    enriched_events = []

    for idx, (event, skeleton, details) in enumerate(
        zip(merged_events, event_skeletons, event_details_list), 1
    ):
        # Use ASCII-safe encoding for console output
        safe_title = skeleton.title.encode('ascii', 'replace').decode('ascii')
        print(f"  [{idx}/{len(merged_events)}] Searching images: {safe_title}")

        # Search for event-specific images
        candidate_images = search_commons_images_for_event(
            skeleton, details, person_name, max_results=10
        )

        # Apply intelligent filtering
        filtered_images = filter_images_for_event(
            candidate_images, skeleton, used_urls, used_captions
        )

        print(f"      Found {len(candidate_images)} candidates, {len(filtered_images)} after filtering")

        # AI selects best image (or none)
        selected_image = assign_image_to_event(
            skeleton, details, filtered_images, person_name, model
        )

        # Update event with image
        event_dict = event.model_dump()
        if selected_image:
            event_dict['images'] = [selected_image.model_dump()]
            used_urls.add(selected_image.url)
            used_captions.add(selected_image.caption)
            print(f"      ✓ Image assigned")
        else:
            event_dict.pop('images', None)
            print(f"      ○ No suitable image")

        enriched_events.append(LifeEvent(**event_dict))

    return enriched_events


# ============================================================================
# ENHANCED GEOCODING
# ============================================================================

def enrich_event_coordinates_v2(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Enhanced geocoding for unified location structure."""
    events = payload.get("events") or []
    enriched = []
    geocoded_count = 0

    for event in events:
        if not isinstance(event, dict):
            enriched.append(event)
            continue

        updated = {**event}
        locations = updated.get("locations", [])

        if not locations:
            enriched.append(updated)
            continue

        # Geocode each location missing coordinates
        geocoded_locations = []
        for loc in locations:
            if not isinstance(loc, dict):
                continue

            # If already has centroid, preserve it
            if loc.get("centroid"):
                geocoded_locations.append(loc)
                geocoded_count += 1
                continue

            # Try geocoding (prefer modern name, fallback to historic)
            name_to_geocode = loc.get("name_modern") or loc.get("name_historic")

            if not name_to_geocode:
                geocoded_locations.append(loc)
                continue

            geocoded = geocode_location(name_to_geocode)

            if geocoded:
                geocoded_locations.append({
                    **loc,
                    "centroid": [geocoded["lon"], geocoded["lat"]]
                })
                geocoded_count += 1
            else:
                geocoded_locations.append(loc)

        updated["locations"] = geocoded_locations
        enriched.append(updated)

    payload["events"] = enriched
    return payload, geocoded_count


# ============================================================================
# METADATA ENFORCEMENT (adapted from generate_person_dataset.py)
# ============================================================================

def enforce_metadata(
    payload: Dict[str, Any],
    page_data: Dict[str, Any],
    summary_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Normalize and enforce metadata standards."""
    payload.setdefault("dataset", DATASET_NAME)
    payload["created_on"] = date.today().isoformat()

    person = payload.setdefault("person", {})
    name_candidates = _collect_person_name_candidates(person, page_data, summary_data)
    if name_candidates:
        preferred_name = min(name_candidates, key=_name_score)
        person["name"] = preferred_name
    else:
        person.setdefault("name", page_data.get("title"))

    for key in ("birth_date", "death_date"):
        value = person.get(key)
        if value:
            normalized, normalized_precision = normalize_date_value(value, "day")
            if normalized and normalized_precision == "day":
                person[key] = normalized
            elif normalized:
                suffix = "-01-01" if normalized_precision == "year" else "-01"
                person[key] = f"{normalized}{suffix}"
            else:
                person[key] = None

    if page_data.get("fullurl"):
        person.setdefault("wikipedia", page_data["fullurl"])

    original = page_data.get("original", {})
    if original:
        # Extract image URL from Wikipedia's pageimages API response
        image_url = original.get("source")
        if image_url:
            # Always set/overwrite portrait if we have a valid image URL from Wikipedia
            person["portrait"] = {
                "image": image_url,
                "source": page_data.get("fullurl"),
            }
    # If no portrait from Wikipedia API, ensure portrait is None or has proper structure
    if not person.get("portrait") or (
        isinstance(person.get("portrait"), dict)
        and person["portrait"].get("image") is None
    ):
        person["portrait"] = None

    death_cutoff: Optional[date] = None
    death_value = person.get("death_date")
    if isinstance(death_value, str):
        try:
            death_cutoff = datetime.strptime(death_value, "%Y-%m-%d").date()
        except ValueError:
            death_cutoff = None

    events = []
    for event in payload.get("events", []) or []:
        if not isinstance(event, dict):
            continue
        event = {**event}

        note_values: List[str] = []

        def add_note(candidate: Optional[str]) -> None:
            if not candidate:
                return
            if candidate in note_values:
                return
            note_values.append(candidate)

        raw_start_date = event.get("date")
        start_input = raw_start_date
        prefer_note_label = False
        if isinstance(raw_start_date, str):
            start_input, start_note, prefer_note_label = _split_date_annotation(
                raw_start_date
            )
            add_note(start_note)

        precision_value = event.get("date_precision") or "day"
        normalized_date, normalized_precision = normalize_date_value(
            start_input, precision_value
        )
        if not normalized_date:
            continue
        event["date"] = normalized_date
        event["date_precision"] = normalized_precision

        raw_date_end = event.get("date_end") or event.get("end_date")
        end_input = raw_date_end
        if isinstance(raw_date_end, str):
            end_input, end_note, _ = _split_date_annotation(raw_date_end)
            add_note(end_note)

        raw_date_end_precision = (
            event.get("date_end_precision")
            or event.get("end_date_precision")
            or precision_value
        )
        normalized_end_date = None
        normalized_end_precision = raw_date_end_precision
        if end_input:
            normalized_end_date, normalized_end_precision = normalize_date_value(
                end_input, raw_date_end_precision or normalized_precision
            )
        if normalized_end_date:
            event["date_end"] = normalized_end_date
            event["date_end_precision"] = normalized_end_precision
        else:
            event.pop("date_end", None)
            event.pop("date_end_precision", None)
        event.pop("end_date", None)
        event.pop("end_date_precision", None)

        if death_cutoff is not None:
            comparison_date = normalized_end_date or normalized_date
            comparison_precision = normalized_end_precision or normalized_precision
            upper_bound = _upper_bound_date(comparison_date, comparison_precision)
            if upper_bound and upper_bound > death_cutoff:
                continue

        existing_note_raw = event.get("date_note")
        cleaned_existing_note = None
        if isinstance(existing_note_raw, str):
            cleaned_existing_note = (
                _clean_date_note_text(existing_note_raw) or existing_note_raw.strip()
            )
        add_note(cleaned_existing_note)

        if note_values:
            note_output = (
                "; ".join(note_values) if len(note_values) > 1 else note_values[0]
            )
            event["date_note"] = note_output
            if prefer_note_label:
                event["date_label"] = note_values[0]
            else:
                event.pop("date_label", None)
        else:
            event.pop("date_note", None)
            event.pop("date_label", None)

        # Validate locations array
        raw_locations = event.get("locations") or []
        sanitized_locations = []

        for loc in raw_locations:
            if not isinstance(loc, dict):
                continue

            name_historic = loc.get("name_historic", "").strip() if loc.get("name_historic") else None
            name_modern = loc.get("name_modern", "").strip() if loc.get("name_modern") else None
            centroid = loc.get("centroid")

            # Validate centroid if present
            valid_centroid = None
            if isinstance(centroid, list) and len(centroid) == 2:
                try:
                    lon, lat = float(centroid[0]), float(centroid[1])
                    if -180 <= lon <= 180 and -90 <= lat <= 90:
                        valid_centroid = [lon, lat]
                except (TypeError, ValueError):
                    pass

            # Include if has historic name
            if name_historic:
                sanitized_locations.append({
                    "name_historic": name_historic,
                    "name_modern": name_modern,
                    "centroid": valid_centroid,
                    "primary": bool(loc.get("primary", False))
                })

        event["locations"] = sanitized_locations

        # Handle images
        raw_images = event.get("images") or []
        sanitized_images = []
        seen_images: Set[str] = set()
        if isinstance(raw_images, list):
            for image_data in raw_images:
                if isinstance(image_data, dict):
                    image_url = image_data.get("url", "").strip()
                    caption = image_data.get("caption", "").strip()
                    source = image_data.get("source", "").strip()

                    if not image_url or not (
                        image_url.startswith("http://")
                        or image_url.startswith("https://")
                    ):
                        continue

                    key = image_url.casefold()
                    if key in seen_images:
                        continue
                    seen_images.add(key)

                    sanitized_images.append(
                        {
                            "url": image_url,
                            "caption": caption or "Image from Wikimedia Commons",
                            "source": source or None,
                        }
                    )
        # Enforce maximum of one image per event
        if sanitized_images:
            event["images"] = sanitized_images[:1]
        else:
            event.pop("images", None)

        # Validate annotations
        raw_annotations = event.get("annotations")
        if raw_annotations and isinstance(raw_annotations, dict):
            sanitized_annotations = {}
            for term_key, annotation in raw_annotations.items():
                if isinstance(annotation, dict):
                    explanation = annotation.get("explanation", "").strip()
                    wikipedia_url = annotation.get("wikipedia_url", "").strip(
                    ) if annotation.get("wikipedia_url") else None

                    # Only keep annotations with valid explanations
                    if explanation:
                        sanitized_annotations[term_key] = {
                            "explanation": explanation
                        }
                        if wikipedia_url and (wikipedia_url.startswith("http://") or wikipedia_url.startswith("https://")):
                            sanitized_annotations[term_key]["wikipedia_url"] = wikipedia_url

            if sanitized_annotations:
                event["annotations"] = sanitized_annotations
            else:
                event.pop("annotations", None)
        else:
            event.pop("annotations", None)

        events.append(event)

    events.sort(key=event_sort_key)
    payload["events"] = events

    # Process chapters if present
    raw_chapters = payload.get("chapters")
    if raw_chapters and isinstance(raw_chapters, list):
        chapters = []
        for chapter in raw_chapters:
            if not isinstance(chapter, dict):
                continue
            chapter = {**chapter}

            # Normalize chapter start date
            start_date = chapter.get("date_start")
            start_precision = chapter.get("date_start_precision") or "year"
            normalized_start, normalized_start_precision = normalize_date_value(
                start_date, start_precision
            )
            if normalized_start:
                chapter["date_start"] = normalized_start
                chapter["date_start_precision"] = normalized_start_precision
            else:
                continue

            # Normalize chapter end date
            end_date = chapter.get("date_end")
            end_precision = chapter.get("date_end_precision") or "year"
            normalized_end, normalized_end_precision = normalize_date_value(
                end_date, end_precision
            )
            if normalized_end:
                chapter["date_end"] = normalized_end
                chapter["date_end_precision"] = normalized_end_precision
            else:
                continue

            chapters.append(chapter)

        if chapters:
            chapters.sort(key=lambda c: c.get("date_start", "9999"))
            payload["chapters"] = chapters
        else:
            payload.pop("chapters", None)
    else:
        payload.pop("chapters", None)

    return payload


# ============================================================================
# FILE I/O
# ============================================================================

def write_dataset(payload: Dict[str, Any], person_id: str) -> Path:
    """Write dataset to file."""
    person_dir = PEOPLE_DIR / person_id
    person_dir.mkdir(parents=True, exist_ok=True)
    output_path = person_dir / "life_events.json"
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    return output_path


def update_register(person_id: str, payload: Dict[str, Any], file_path: Path) -> None:
    """Update persons register."""
    person = payload.get("person", {})

    portrait = person.get("portrait")
    birth_date = person.get("birth_date")
    death_date = person.get("death_date")

    primary_roles = person.get("primary_roles", [])
    if isinstance(primary_roles, list):
        primary_roles = primary_roles[:3]

    current_timestamp = datetime.now().astimezone().isoformat()

    entry = {
        "id": person_id,
        "name": person.get("name", person_id.replace("_", " ").title()),
        "summary": person.get("summary"),
    }

    if portrait:
        entry["portrait"] = portrait
    if birth_date:
        entry["birthDate"] = birth_date
    if death_date:
        entry["deathDate"] = death_date
    if primary_roles:
        entry["primaryRoles"] = primary_roles

    register = {"people": []}
    if REGISTER_PATH.exists():
        register = json.loads(REGISTER_PATH.read_text(encoding="utf-8"))
    people = register.setdefault("people", [])

    for idx, existing in enumerate(people):
        if existing.get("id") == person_id:
            created_timestamp = existing.get("created", current_timestamp)
            people[idx] = {
                **existing,
                **entry,
                "created": created_timestamp,
                "lastUpdated": current_timestamp,
            }
            break
    else:
        entry["created"] = current_timestamp
        entry["lastUpdated"] = current_timestamp
        people.append(entry)

    people.sort(key=lambda item: item.get("name", ""))
    REGISTER_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTER_PATH.write_text(
        json.dumps(register, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )


# ============================================================================
# MAIN ORCHESTRATION
# ============================================================================

def generate_person_events(
    subject: str,
    *,
    update_registry: bool = True,
    model: str = DEFAULT_MODEL,
    use_cache: bool = True,
) -> Tuple[Path, str]:
    """
    Generate person life events dataset using two-phase approach.

    Returns:
        Tuple of (file_path, person_id)
    """

    print(f"[Step 1/10] Fetching Wikipedia article for '{subject}'...")
    page_data = fetch_wikipedia_extract(subject)
    article_title = page_data.get("title", subject)
    print(f"[Step 1/10] Found article '{article_title}'")

    person_id = slugify(article_title)

    # Load cache (NO Commons images - fetched later in Phase 3)
    print(f"[Step 2/10] Loading cached materials for '{person_id}'...")
    related_articles = None
    summary_data = {}

    if use_cache:
        try:
            ensure_cache(person_id, article_title, person_name=article_title)
            cached_page = get_cached_wikipedia_page(
                person_id, article_title, use_cache=True
            )
            cached_summary = get_cached_wikipedia_summary(
                person_id, article_title, use_cache=True
            )

            # Load related articles if available
            cache_dir = get_cache_dir(person_id)
            related_path = cache_dir / "related_articles.json"
            if related_path.exists():
                try:
                    related_articles = json.loads(
                        related_path.read_text(encoding="utf-8")
                    )
                    print(
                        f"[Step 2/10] Using cached materials ({len(related_articles)} related articles)"
                    )
                except json.JSONDecodeError:
                    print(
                        f"[Step 2/10] Using cached materials (no related articles)"
                    )
            else:
                print(
                    f"[Step 2/10] Using cached materials (no related articles)"
                )

            page_data = cached_page
            summary_data = cached_summary
        except Exception as e:
            print(f"[Step 2/10] Cache unavailable ({e}), fetching directly...")
            summary_data = fetch_wikipedia_summary(article_title)
    else:
        print("[Step 2/10] Retrieving summary details...")
        summary_data = fetch_wikipedia_summary(article_title)

    # Fetch related articles if not already loaded from cache
    if related_articles is None and fetch_related_articles is not None:
        print(f"[Step 3/10] Fetching related articles (model: {model}, reasoning: {LOW_REASONING_EFFORT})...")
        try:
            related_articles = fetch_related_articles(
                article_title,
                max_related=15,
                model=model,
                use_cache=use_cache,
                person_id=person_id,
            )
            print(f"[Step 3/10] Found {len(related_articles)} related articles")

            if related_articles and use_cache:
                cache_dir = get_cache_dir(person_id)
                related_path = cache_dir / "related_articles.json"
                cache_dir.mkdir(parents=True, exist_ok=True)
                related_path.write_text(
                    json.dumps(related_articles, indent=2, ensure_ascii=True) + "\n",
                    encoding="utf-8",
                )
                print(f"[Step 3/10] Cached {len(related_articles)} related articles")
        except Exception as e:
            print(f"[Step 3/10] Warning: Failed to fetch related articles ({e})")
            related_articles = []
    else:
        print(f"[Step 3/10] Using {len(related_articles) if related_articles else 0} related articles from cache")

    # PHASE 1: Generate event skeletons
    print(f"[Step 4/11] PHASE 1: Generating event skeletons (model: {model}, reasoning: {DEFAULT_REASONING_EFFORT})...")
    phase1_prompt = build_phase1_prompt(page_data, summary_data, subject, related_articles)
    life_plan = call_openai_phase1(phase1_prompt, model)
    print(f"[Step 4/11] Generated {len(life_plan.event_skeletons)} event skeletons")

    # PHASE 2: Research event details (NO images - Phase 3)
    print(f"[Step 5/11] PHASE 2: Researching event details (model: {model}, reasoning: {LOW_REASONING_EFFORT})...")
    event_details_list = research_all_event_details(
        event_skeletons=life_plan.event_skeletons,
        person_name=life_plan.person.name,
        all_related_articles=related_articles or [],
        model=model,
    )
    print(f"[Step 5/11] Researched details for {len(event_details_list)} events")

    # MERGE: Combine skeletons + details
    print("[Step 6/11] Merging event skeletons with details...")
    merged_events = merge_all_events(life_plan.event_skeletons, event_details_list)

    # CHAPTER GENERATION: Create chapters based on established events
    print(f"[Step 7/11] Generating life chapters (model: {model}, reasoning: {LOW_REASONING_EFFORT})...")
    chapters, events_with_chapters = generate_chapters_for_events(
        merged_events=merged_events,
        person_name=life_plan.person.name,
        birth_date=life_plan.person.birth_date,
        death_date=life_plan.person.death_date,
        model=model,
    )
    print(f"[Step 7/11] Generated {len(chapters)} chapters")

    # PHASE 3: Event-specific image discovery
    print(
        f"[Step 8/11] PHASE 3: Discovering and assigning event-specific images (model: {model}, reasoning: {LOW_REASONING_EFFORT})...")
    enriched_events = research_images_for_all_events(
        merged_events=events_with_chapters,
        event_skeletons=life_plan.event_skeletons,
        event_details_list=event_details_list,
        person_name=life_plan.person.name,
        model=model,
    )
    images_assigned = sum(1 for e in enriched_events if e.images)
    print(f"[Step 8/11] Assigned images to {images_assigned} / {len(enriched_events)} events")

    # Build final payload
    payload = {
        "dataset": life_plan.dataset,
        "created_on": life_plan.created_on,
        "person": life_plan.person.model_dump(),
        "chapters": [ch.model_dump() for ch in chapters] if chapters else None,
        "events": [ev.model_dump() for ev in enriched_events],
    }

    # Normalize metadata
    print("[Step 9/11] Normalizing dataset metadata...")
    payload = enforce_metadata(payload, page_data, summary_data)
    print(f"[Step 9/11] Dataset includes {len(payload['events'])} events")

    # Geocode with enhanced logic
    print("[Step 10/11] Resolving event location coordinates...")
    payload, geocoded_events = enrich_event_coordinates_v2(payload)
    print(f"[Step 10/11] Coordinates resolved for {geocoded_events} events")

    # Write to file
    print(f"[Step 11/11] Writing dataset for '{person_id}'...")
    file_path = write_dataset(payload, person_id)

    if update_registry:
        print("Updating persons register...")
        update_register(person_id, payload, file_path)
        print("Register update complete")
    else:
        print("Register update skipped")

    return file_path, person_id


# ============================================================================
# CLI
# ============================================================================

def parse_args(argv: Any) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate life event datasets using two-phase AI approach."
    )
    parser.add_argument("subject", help="Person to research, e.g. 'Ada Lovelace'.")
    parser.add_argument(
        "--no-register", action="store_true", help="Skip updating the persons register."
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Skip using cached Wikipedia materials and fetch directly from APIs.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=(
            "OpenAI model to use (default from OPENAI_MODEL env or 'gpt-4o-mini'). "
            "Must support structured outputs: gpt-4o-mini, gpt-4o-2024-08-06, or later. "
            "See https://platform.openai.com/docs/guides/structured-outputs for supported models."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Any = None) -> int:
    args = parse_args(argv)
    try:
        file_path, person_id = generate_person_events(
            args.subject,
            update_registry=not args.no_register,
            model=args.model,
            use_cache=not args.no_cache,
        )
        print(f"\nDataset written to {file_path}")
        if args.no_register:
            print("Register update skipped by request.")
        else:
            print(f"Register updated at {REGISTER_PATH}")
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
