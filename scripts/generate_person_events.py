#!/usr/bin/env python3
"""
Generate life event datasets using a two-phase approach:
1. Phase 1: Generate event skeletons (title, date, description) + chapters
2. Phase 2: Research details for each event (location, people, images, sources, icon)

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

from config import DEFAULT_MODEL, DEFAULT_REASONING_EFFORT
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
    headline: str = Field(description="Short, evocative chapter headline (3-6 words)")
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
    chapter: Optional[str] = Field(None, description="Chapter ID this event belongs to")


class LifePlan(BaseModel):
    """Phase 1 output: Person metadata, chapters, and event skeletons."""
    dataset: str = Field(description="Name of the dataset")
    created_on: str = Field(description="Creation date in ISO-8601 format")
    person: Person = Field(description="Person metadata")
    chapters: Optional[List[LifeChapter]] = Field(
        None, description="Optional list of life chapters grouping events"
    )
    event_skeletons: List[EventSkeleton] = Field(
        description="List of event skeletons (minimal event data)"
    )


# Phase 2 Models

class EventDetails(BaseModel):
    """Phase 2: Research details for a specific event."""
    location: Optional[str] = Field(
        None,
        description="Historic location name at time of event (e.g., 'Königsberg')"
    )
    location_modern: Optional[str] = Field(
        None,
        description="Modern geographic name for geocoding (e.g., 'Kaliningrad, Russia'). "
        "Always provide even if same as historic location."
    )
    involved_people: Optional[List[str]] = Field(
        None,
        description="Names of people directly involved in this event (exclude the main subject)"
    )
    images: Optional[List[ImageMetadata]] = Field(
        None,
        description="At most ONE relevant image for this event"
    )
    sources: List[str] = Field(
        default_factory=list,
        description="Array of Wikipedia URLs or references supporting this event"
    )
    event_type_icon: Optional[str] = Field(
        None,
        description="MDI icon identifier (e.g., 'mdi-crown', 'mdi-book')"
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
    locations: List[str] = Field(
        description="Human-readable location names"
    )
    location_modern: Optional[str] = Field(
        None,
        description="Modern location name for geocoding"
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
        LifePlan with person metadata, chapters, and event skeletons
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY environment variable is not set.")

    client = OpenAI(api_key=api_key)

    system = (
        "You are a meticulous historian creating biographical timeline outlines. "
        "Focus on identifying the most significant events and organizing them into "
        "coherent life chapters. Use ISO-8601 dates, include date_precision as 'day', "
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
        "\n\nIMPORTANT - Chapter Organization:\n"
        "- Group the events into 3-5 meaningful life chapters (periods/phases)\n"
        "- Each chapter should represent a distinct phase of the person's life (e.g., 'Early Years and Education', 'Wartime Service', 'Academic Career', 'Later Life')\n"
        "- Create chapter objects with: id (snake_case), headline (3-6 words), description (1-2 sentences about this life period), "
        "date_start, date_start_precision, date_end, date_end_precision, age_start, age_end\n"
        "- Assign each event to a chapter by setting its 'chapter' field to the chapter's 'id'\n"
        "- Chapters should be chronological and non-overlapping\n"
        "- The first chapter should start with or before the first event, and the last chapter should end with or after the last event\n"
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
        "title, description, and chapter (the chapter id this event belongs to). "
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
    commons_images: List[Dict[str, Any]],
) -> str:
    """
    Build Phase 2 prompt for single event detail research.

    Focus on specific details for THIS event only.
    """
    prompt = f"Research details for this specific event:\n\n"
    prompt += f"Title: {event_skeleton.title}\n"
    prompt += f"Date: {event_skeleton.date}\n"
    prompt += f"Description: {event_skeleton.description}\n"
    prompt += f"Subject: {person_name}\n\n"

    prompt += "="*60 + "\n"
    prompt += "TASK: Provide the following details for THIS specific event:\n"
    prompt += "="*60 + "\n\n"

    prompt += "1. LOCATION (historic name at time of event):\n"
    prompt += "   - Provide the location name as it was known at the time\n"
    prompt += "   - Be as specific as possible (e.g., 'Königsberg' not just 'Prussia')\n"
    prompt += "   - If truly unknown, leave null\n\n"

    prompt += "2. LOCATION_MODERN (for geocoding):\n"
    prompt += "   - ALWAYS provide the modern geographic name\n"
    prompt += "   - Even if same as historic (e.g., 'London' → 'London')\n"
    prompt += "   - Examples: 'Königsberg' → 'Kaliningrad, Russia'\n"
    prompt += "   - Include country for disambiguation\n\n"

    prompt += "3. INVOLVED_PEOPLE:\n"
    prompt += "   - List people DIRECTLY involved in THIS specific event\n"
    prompt += f"   - EXCLUDE the main subject ({person_name})\n"
    prompt += "   - Examples: collaborators, opponents, witnesses, family members present\n"
    prompt += "   - Leave null if no other people directly involved\n\n"

    prompt += "4. IMAGES:\n"
    prompt += "   - Select AT MOST ONE relevant image from the list below\n"
    prompt += "   - Prefer images of buildings, documents, artifacts, or locations\n"
    prompt += "   - DO NOT use generic portraits\n"
    prompt += "   - Leave null if no suitable image\n\n"

    prompt += "5. SOURCES:\n"
    prompt += "   - Provide 1-3 Wikipedia URLs from the related articles below\n"
    prompt += "   - Only include articles that specifically support THIS event\n\n"

    prompt += "6. EVENT_TYPE_ICON:\n"
    prompt += "   - Select the most appropriate MDI icon from the categories below\n"
    prompt += "   - Based on the semantic type of this event\n\n"

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

    # Add Commons images
    if commons_images and len(commons_images) > 0:
        prompt += "\n" + "="*60 + "\n"
        prompt += "AVAILABLE IMAGES:\n"
        prompt += "="*60 + "\n\n"
        # Limit to 20 images
        for idx, img_data in enumerate(commons_images[:20], 1):
            prompt += f"{idx}. {img_data.get('caption', 'Image')}\n"
            prompt += f"   URL: {img_data['url']}\n"
            if img_data.get("source"):
                prompt += f"   Source: {img_data['source']}\n"
            prompt += "\n"

    return prompt


def research_event_details(
    event_skeleton: EventSkeleton,
    person_name: str,
    all_related_articles: List[Dict[str, Any]],
    commons_images: List[Dict[str, Any]],
    model: str,
    retry_count: int = 2
) -> EventDetails:
    """
    Research details for a single event with retry logic.

    Returns:
        EventDetails with location, location_modern, involved_people, images, sources, icon
    """
    # Filter articles
    filtered_articles = filter_related_articles_for_event(
        event_skeleton, all_related_articles, max_articles=5
    )

    # Build prompt
    prompt = build_phase2_prompt(
        event_skeleton, person_name, filtered_articles, commons_images
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
                reasoning={"effort": DEFAULT_REASONING_EFFORT},
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
                    location=None,
                    location_modern=None,
                    involved_people=None,
                    images=None,
                    sources=[],
                    event_type_icon="mdi-calendar"
                )

    # Should never reach here, but fallback just in case
    return EventDetails(
        location=None,
        location_modern=None,
        involved_people=None,
        images=None,
        sources=[],
        event_type_icon="mdi-calendar"
    )


def research_all_event_details(
    event_skeletons: List[EventSkeleton],
    person_name: str,
    all_related_articles: List[Dict[str, Any]],
    commons_images: List[Dict[str, Any]],
    model: str,
) -> List[EventDetails]:
    """Research details for all events sequentially."""
    details = []
    for idx, skeleton in enumerate(event_skeletons, 1):
        print(f"  [{idx}/{len(event_skeletons)}] Researching: {skeleton.title}")
        detail = research_event_details(
            skeleton, person_name, all_related_articles, commons_images, model
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
    """Merge Phase 1 skeleton with Phase 2 details."""

    # Build locations array
    locations = []
    if details.location:
        locations.append(details.location)
    else:
        locations.append(UNKNOWN_LOCATION_LABEL)

    # Create merged event
    return LifeEvent(
        date=skeleton.date,
        date_precision=skeleton.date_precision,
        date_end=skeleton.date_end,
        date_end_precision=skeleton.date_end_precision,
        date_note=skeleton.date_note,
        age=skeleton.age,
        title=skeleton.title,
        description=skeleton.description,
        locations=locations,
        location_modern=details.location_modern,
        involved_people=details.involved_people,
        sources=details.sources if details.sources else [],
        images=details.images,
        event_type_icon=details.event_type_icon or "mdi-calendar",
        chapter=skeleton.chapter,
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
# ENHANCED GEOCODING
# ============================================================================

def geocode_event_location_v2(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Geocode event location with location_modern priority.

    Priority:
    1. Try location_modern (better for changed names)
    2. Fall back to locations[0] (historic name)
    3. Return None if unsuccessful
    """
    # Try modern location first
    if event.get("location_modern"):
        result = geocode_location(event["location_modern"])
        if result:
            return result

    # Fall back to historic location
    locations = event.get("locations") or []
    if locations and len(locations) > 0:
        result = geocode_location(locations[0])
        if result:
            return result

    return None


def enrich_event_coordinates_v2(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Enhanced geocoding with location_modern support."""
    events = payload.get("events") or []
    enriched = []
    resolved_count = 0

    for event in events:
        if not isinstance(event, dict):
            enriched.append(event)
            continue

        # Geocode using enhanced logic
        geocoded = geocode_event_location_v2(event)

        updated = {**event}
        if geocoded:
            # Display historic name, use modern coords
            display_name = event.get("locations", [UNKNOWN_LOCATION_LABEL])[0]

            entry = {
                "label": geocoded.get("display_name") or display_name,
                "name": display_name,  # Keep historic name
                "primary": True,
                "centroid": [geocoded["lon"], geocoded["lat"]],
                "source": "nominatim",
            }
            if geocoded.get("bbox"):
                entry["bbox"] = geocoded["bbox"]

            updated["location_coordinates"] = [entry]
            resolved_count += 1
        else:
            updated.pop("location_coordinates", None)

        enriched.append(updated)

    payload["events"] = enriched
    return payload, resolved_count


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

        raw_locations = event.get("locations") or []
        sanitized_locations = []
        seen_locations: Set[str] = set()
        for location in raw_locations:
            if not isinstance(location, str):
                continue
            trimmed = location.strip()
            if not trimmed:
                continue
            key = trimmed.casefold()
            if key in seen_locations:
                continue
            seen_locations.add(key)
            sanitized_locations.append(trimmed)
        if not sanitized_locations:
            sanitized_locations = [UNKNOWN_LOCATION_LABEL]
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

    print(f"[Step 1/9] Fetching Wikipedia article for '{subject}'...")
    page_data = fetch_wikipedia_extract(subject)
    article_title = page_data.get("title", subject)
    print(f"[Step 1/9] Found article '{article_title}'")

    person_id = slugify(article_title)

    # Load cache
    print(f"[Step 2/9] Loading cached materials for '{person_id}'...")
    commons_images = None
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
            commons_images = get_cached_commons_images(
                person_id, article_title, limit=30, use_cache=True
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
                        f"[Step 2/9] Using cached materials ({len(commons_images)} Commons images, {len(related_articles)} related articles)"
                    )
                except json.JSONDecodeError:
                    print(
                        f"[Step 2/9] Using cached materials ({len(commons_images)} Commons images)"
                    )
            else:
                print(
                    f"[Step 2/9] Using cached materials ({len(commons_images)} Commons images)"
                )

            page_data = cached_page
            summary_data = cached_summary
        except Exception as e:
            print(f"[Step 2/9] Cache unavailable ({e}), fetching directly...")
            summary_data = fetch_wikipedia_summary(article_title)
    else:
        print("[Step 2/9] Retrieving summary details...")
        summary_data = fetch_wikipedia_summary(article_title)

    # Fetch related articles if not already loaded from cache
    if related_articles is None and fetch_related_articles is not None:
        print("[Step 3/9] Fetching related articles...")
        try:
            related_articles = fetch_related_articles(
                article_title,
                max_related=15,
                model=model,
                use_cache=use_cache,
                person_id=person_id,
            )
            print(f"[Step 3/9] Found {len(related_articles)} related articles")

            if related_articles and use_cache:
                cache_dir = get_cache_dir(person_id)
                related_path = cache_dir / "related_articles.json"
                cache_dir.mkdir(parents=True, exist_ok=True)
                related_path.write_text(
                    json.dumps(related_articles, indent=2, ensure_ascii=True) + "\n",
                    encoding="utf-8",
                )
                print(f"[Step 3/9] Cached {len(related_articles)} related articles")
        except Exception as e:
            print(f"[Step 3/9] Warning: Failed to fetch related articles ({e})")
            related_articles = []
    else:
        print(f"[Step 3/9] Using {len(related_articles) if related_articles else 0} related articles from cache")

    # PHASE 1: Generate event skeletons
    print("[Step 4/9] PHASE 1: Generating event skeletons and chapters...")
    phase1_prompt = build_phase1_prompt(page_data, summary_data, subject, related_articles)
    life_plan = call_openai_phase1(phase1_prompt, model)
    print(f"[Step 4/9] Generated {len(life_plan.event_skeletons)} event skeletons")

    # PHASE 2: Research event details
    print("[Step 5/9] PHASE 2: Researching event details...")
    event_details_list = research_all_event_details(
        event_skeletons=life_plan.event_skeletons,
        person_name=life_plan.person.name,
        all_related_articles=related_articles or [],
        commons_images=commons_images or [],
        model=model,
    )
    print(f"[Step 5/9] Researched details for {len(event_details_list)} events")

    # MERGE: Combine skeletons + details
    print("[Step 6/9] Merging event skeletons with details...")
    merged_events = merge_all_events(life_plan.event_skeletons, event_details_list)

    # Build final payload
    payload = {
        "dataset": life_plan.dataset,
        "created_on": life_plan.created_on,
        "person": life_plan.person.model_dump(),
        "chapters": [ch.model_dump() for ch in life_plan.chapters] if life_plan.chapters else None,
        "events": [ev.model_dump() for ev in merged_events],
    }

    # Normalize metadata
    print("[Step 7/9] Normalizing dataset metadata...")
    payload = enforce_metadata(payload, page_data, summary_data)
    print(f"[Step 7/9] Dataset includes {len(payload['events'])} events")

    # Geocode with enhanced logic
    print("[Step 8/9] Resolving event location coordinates...")
    payload, geocoded_events = enrich_event_coordinates_v2(payload)
    print(f"[Step 8/9] Coordinates resolved for {geocoded_events} events")

    # Write to file
    print(f"[Step 9/9] Writing dataset for '{person_id}'...")
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
