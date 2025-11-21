#!/usr/bin/env python3
"""Generate life event datasets for notable people using Wikipedia content and the OpenAI API."""

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

DATASET_NAME = "Life Data Stories"
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
REGISTER_PATH = DATA_DIR / "persons.json"
PEOPLE_DIR = DATA_DIR / "people"
MEDIAWIKI_API = "https://en.wikipedia.org/w/api.php"
WIKIPEDIA_SUMMARY_API = "https://en.wikipedia.org/api/rest_v1/page/summary/"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
# Structured outputs require gpt-4o-mini, gpt-4o-2024-08-06, or later models
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
DEFAULT_USER_AGENT = "life-ds-data-generator/1.0 (+https://github.com/fabian-beck/life-ds)"
GEOCODER_ENDPOINT = os.getenv(
    "LIFE_DS_GEOCODER_ENDPOINT",
    "https://nominatim.openstreetmap.org/search",
)
GEOCODER_DELAY_SECONDS = float(os.getenv("LIFE_DS_GEOCODER_DELAY", "1.0"))
GEOCODER_MAX_RESULTS = 1
UNKNOWN_LOCATION_LABEL = "Location unknown"

_geocode_cache: Dict[str, Optional[Dict[str, Any]]] = {}
_last_geocode_at: float = 0.0


# Pydantic models for structured outputs
class ImageMetadata(BaseModel):
    """Metadata for an image associated with an event."""
    url: str = Field(description="The full URL of the image")
    caption: str = Field(
        description="A concise, factual description of what the image shows")
    source: str = Field(
        description="The source URL, typically a Wikimedia Commons page")


class LifeEvent(BaseModel):
    """A significant life event."""
    date: str = Field(
        description="ISO-8601 date string (YYYY-MM-DD, YYYY-MM, or YYYY)")
    date_precision: str = Field(
        description="Precision level: 'day', 'month', or 'year'")
    date_end: Optional[str] = Field(
        None, description="Optional end date for events spanning a range")
    date_end_precision: Optional[str] = Field(
        None, description="Precision for the end date")
    date_note: Optional[str] = Field(
        None, description="Note about date uncertainty or alternative representations")
    age: Optional[int] = Field(
        None, description="Subject's age at the time of the event, null if not applicable")
    title: str = Field(description="Brief title of the event")
    description: str = Field(description="Detailed description of the event")
    locations: List[str] = Field(
        description="Human-readable location names, use 'Location unknown' if uncertain")
    sources: List[str] = Field(
        description="Array of Wikipedia URLs or references")
    images: Optional[List[ImageMetadata]] = Field(
        None, description="Optional array of relevant images")


class Portrait(BaseModel):
    """Portrait information for the person."""
    image: Optional[str] = Field(None, description="URL of the portrait image")
    source: Optional[str] = Field(
        None, description="Source URL for the portrait")


class Person(BaseModel):
    """Metadata about the person."""
    name: str = Field(description="Full name of the person")
    birth_date: Optional[str] = Field(
        None, description="Birth date in ISO-8601 format")
    death_date: Optional[str] = Field(
        None, description="Death date in ISO-8601 format")
    primary_roles: List[str] = Field(
        description="Primary roles or professions")
    summary: str = Field(description="Brief biographical summary")
    wikipedia: Optional[str] = Field(None, description="Wikipedia URL")
    portrait: Optional[Portrait] = Field(
        None, description="Portrait information")


class LifeDataset(BaseModel):
    """Complete structured dataset for a person's life events."""
    dataset: str = Field(description="Name of the dataset")
    created_on: str = Field(description="Creation date in ISO-8601 format")
    person: Person = Field(description="Person metadata")
    events: List[LifeEvent] = Field(
        description="List of significant life events")


def _strip_wrapping_quotes(value: str) -> str:
    trimmed = value.strip()
    quotes = "\"'“”‘’"
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
    # Remove HTML tags
    clean = re.sub(r"<[^>]+>", "", value)
    # Decode HTML entities
    clean = clean.replace("&lt;", "<").replace(
        "&gt;", ">").replace("&amp;", "&")
    clean = clean.replace("&quot;", '"').replace(
        "&#39;", "'").replace("&nbsp;", " ")
    # Remove excessive whitespace
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
    except Exception as error:  # noqa: BLE001
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


def _fetch_wikipedia_page(title: str) -> Dict[str, Any]:
    params = {
        "action": "query",
        "format": "json",
        "prop": "extracts|pageimages|info|images",
        "explaintext": 1,
        "redirects": 1,
        "inprop": "url",
        "piprop": "original",
        "titles": title,
        "imlimit": 100,  # Fetch up to 100 images from the page
    }
    response = requests.get(
        MEDIAWIKI_API,
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
    titles: List[str] = [
        item.get("title")
        for item in results
        if item.get("title")
    ]
    suggestion = (
        data.get("query", {})
        .get("searchinfo", {})
        .get("suggestion")
    )
    if suggestion:
        titles.append(suggestion)
    # Preserve the reported order while removing duplicates later when enqueuing
    return titles


def fetch_wikipedia_extract(title: str) -> Dict[str, Any]:
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
    if parenthetical and parenthetical.casefold() not in {title.casefold(), normalized_title.casefold()}:
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
    url = WIKIPEDIA_SUMMARY_API + quote(title.replace(" ", "_"))
    response = requests.get(url, timeout=30, headers=wikipedia_headers())
    if response.status_code != 200:
        return {}
    return response.json()


def search_commons_images(person_name: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Search Wikimedia Commons for images related to a person."""
    try:
        # Search Commons for images related to the person
        params = {
            "action": "query",
            "format": "json",
            "list": "search",
            "srsearch": f"{person_name}",
            "srnamespace": "6",  # File namespace
            "srlimit": limit,
            "srprop": "snippet",
        }
        response = requests.get(
            COMMONS_API,
            params=params,
            timeout=30,
            headers=wikipedia_headers(),
        )
        response.raise_for_status()
        data = response.json()

        search_results = data.get("query", {}).get("search", [])
        if not search_results:
            return []

        # Extract file titles
        file_titles = [result.get("title") for result in search_results if result.get("title")]

        # Fetch detailed info for these files
        if not file_titles:
            return []

        image_data = []
        # Process in chunks of 50
        for i in range(0, len(file_titles), 50):
            chunk = file_titles[i:i+50]
            params = {
                "action": "query",
                "format": "json",
                "prop": "imageinfo",
                "iiprop": "url|size|mime|extmetadata",
                "titles": "|".join(chunk),
            }

            try:
                response = requests.get(
                    COMMONS_API,
                    params=params,
                    timeout=30,
                    headers=wikipedia_headers(),
                )
                response.raise_for_status()
                data = response.json()
            except Exception as error:
                print(f"Warning: Failed to fetch Commons image details: {error}")
                continue

            pages = data.get("query", {}).get("pages", {})
            for page in pages.values():
                imageinfo = page.get("imageinfo", [])
                if imageinfo and len(imageinfo) > 0:
                    info = imageinfo[0]
                    url = info.get("url")
                    mime = info.get("mime", "")
                    width = info.get("width", 0)
                    height = info.get("height", 0)

                    # Only include proper images
                    if url and mime.startswith("image/") and width >= 100 and height >= 100:
                        extmetadata = info.get("extmetadata", {})
                        description = None
                        description_url = None

                        if "ImageDescription" in extmetadata:
                            desc_data = extmetadata["ImageDescription"]
                            if isinstance(desc_data, dict) and "value" in desc_data:
                                description = _strip_html_tags(desc_data["value"])

                        if "DescriptionURL" in extmetadata:
                            desc_url_data = extmetadata["DescriptionURL"]
                            if isinstance(desc_url_data, dict) and "value" in desc_url_data:
                                description_url = desc_url_data["value"]
                        elif "descriptionurl" in info:
                            description_url = info["descriptionurl"]

                        image_obj = {
                            "url": url,
                            "caption": description or f"Image from Wikimedia Commons",
                            "source": description_url,
                        }
                        image_data.append(image_obj)

        return image_data
    except Exception as error:
        print(f"Warning: Commons search failed for '{person_name}': {error}")
        return []


def fetch_image_urls(image_titles: List[str]) -> List[str]:
    """Fetch actual URLs for Wikipedia image titles."""
    if not image_titles:
        return []

    # Filter out common non-content images
    excluded_patterns = [
        "commons-logo",
        "wikidata-logo",
        "wikimedia-logo",
        "edit-clear.svg",
        "question_book",
        "ambox",
        "symbol",
        "blue_pencil.svg",
        "increase",
        "decrease",
        "steady",
    ]

    filtered_titles = []
    # Limit to first 60 to get more images
    for title in image_titles[:60]:
        # Skip if title is not a string
        if not isinstance(title, str):
            continue
        title_lower = title.lower()
        if any(pattern in title_lower for pattern in excluded_patterns):
            continue
        # Accept any title - Wikipedia API returns image titles as-is
        filtered_titles.append(title)

    if not filtered_titles:
        return []

    # Batch fetch image info in chunks of 50 (API limit)
    image_data = []
    for i in range(0, len(filtered_titles), 50):
        chunk = filtered_titles[i:i+50]
        params = {
            "action": "query",
            "format": "json",
            "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata",
            "titles": "|".join(chunk),
        }

        try:
            response = requests.get(
                MEDIAWIKI_API,
                params=params,
                timeout=30,
                headers=wikipedia_headers(),
            )
            response.raise_for_status()
            data = response.json()
        except Exception as error:
            print(f"Warning: Failed to fetch image URLs for chunk {i//50 + 1}: {error}")
            continue

        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            imageinfo = page.get("imageinfo", [])
            if imageinfo and len(imageinfo) > 0:
                info = imageinfo[0]
                url = info.get("url")
                mime = info.get("mime", "")
                width = info.get("width", 0)
                height = info.get("height", 0)

                # Only include proper images (not tiny images)
                if url and mime.startswith("image/"):
                    # Lower minimum size to include more images
                    if width >= 100 and height >= 100:
                        # Extract metadata
                        extmetadata = info.get("extmetadata", {})
                        description = None
                        artist = None
                        description_url = None

                        # Try to get description
                        if "ImageDescription" in extmetadata:
                            desc_data = extmetadata["ImageDescription"]
                            if isinstance(desc_data, dict) and "value" in desc_data:
                                # Strip HTML tags from description
                                description = _strip_html_tags(desc_data["value"])

                        # Try to get artist/credit
                        if "Artist" in extmetadata:
                            artist_data = extmetadata["Artist"]
                            if isinstance(artist_data, dict) and "value" in artist_data:
                                artist = _strip_html_tags(artist_data["value"])

                        # Get description URL (Wikimedia Commons page)
                        if "DescriptionURL" in extmetadata:
                            desc_url_data = extmetadata["DescriptionURL"]
                            if isinstance(desc_url_data, dict) and "value" in desc_url_data:
                                description_url = desc_url_data["value"]
                        elif "descriptionurl" in info:
                            description_url = info["descriptionurl"]

                        # Create image object with metadata
                        image_obj = {
                            "url": url,
                            "caption": description or f"Image from Wikimedia Commons",
                            "source": description_url,
                        }
                        image_data.append(image_obj)

    return image_data


def build_prompt(page_data: Dict[str, Any], summary_data: Dict[str, Any], subject: str) -> str:
    summary_text = summary_data.get("extract", "").strip()
    extract_text = page_data.get("extract", "").strip()

    # Get image URLs - images come as list of dicts with 'title' keys
    images_data = page_data.get("images", [])
    image_titles = []
    for img in images_data:
        if isinstance(img, dict) and "title" in img:
            image_titles.append(img["title"])
        elif isinstance(img, str):
            image_titles.append(img)

    image_urls = fetch_image_urls(image_titles) if image_titles else []

    # Also search Wikimedia Commons for additional images
    person_name = page_data.get("title", subject)
    commons_images = search_commons_images(person_name, limit=30)

    # Combine and deduplicate images
    seen_urls = set()
    all_images = []
    for img in image_urls + commons_images:
        url = img.get("url")
        if url and url not in seen_urls:
            seen_urls.add(url)
            all_images.append(img)

    image_urls = all_images

    combined = f"Page title: {page_data.get('title', subject)}\nPage URL: {page_data.get('fullurl', '')}\n\n"
    if summary_text:
        combined += f"Summary snippet:\n{summary_text}\n\n"
    if extract_text:
        truncated = extract_text[:12000]
        combined += f"Full extract (truncated to 12k characters if needed):\n{truncated}\n"

    if image_urls:
        combined += f"\n\n{'='*60}\nAVAILABLE IMAGES - Use these in relevant events:\n{'='*60}\n"
        # Increased limit to 30 to provide more image options
        for idx, img_data in enumerate(image_urls[:30], 1):
            combined += f"\n{idx}. {img_data.get('caption', 'Image')}\n"
            combined += f"   URL: {img_data['url']}\n"
            if img_data.get('source'):
                combined += f"   Source: {img_data['source']}\n"
        combined += f"\nIMPORTANT: Include relevant images in events using this exact JSON format:\n"
        combined += '"images": [{"url": "...full URL...", "caption": "...description of what the image shows...", "source": "...Wikimedia Commons URL..."}]\n'
        combined += "Use the captions provided above or write your own factual description of what the image shows.\n"
        combined += f"\nNote: {len(image_urls)} images available in total (showing first 30). Use images that are directly relevant to specific events.\n"

    return combined


def call_openai(prompt: str, model: str) -> Dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY environment variable is not set.")
    client = OpenAI(api_key=api_key)
    system = (
        "You are a meticulous historian who converts raw Wikipedia content into structured JSON. "
        "Use ISO-8601 dates, include date_precision as 'day', 'month', or 'year'. "
        "Align event ages with the subject's birth date."
    )
    instructions = (
        "Produce 12-16 significant life events covering the subject's early life, "
        "education, major accomplishments, and later years. "
        "Do not include events that occur after the subject's death or that focus on their legacy. "
        "Each event must provide: date (start of the event), date_precision, optional date_end/date_end_precision "
        "when the event spans a range, optional date_note for uncertainty, age (null if not applicable), "
        "title, description, locations (array with at least one human-readable entry, use 'Location unknown' if uncertain), "
        "sources (array of URLs pulled from Wikipedia), and optional images (array of image objects with 'url', 'caption', and 'source' fields). "
        "\n\nIMPORTANT - Event Title Guidelines:\n"
        "- Keep event titles crisp and concise (2-6 words)\n"
        "- Use active, specific language that captures the essence of the event\n"
        "- Avoid generic titles like 'Major Achievement' or 'Important Work'\n"
        "- Examples: 'Birth in London', 'Graduated from Oxford', 'Published First Novel', 'Appointed Prime Minister'\n"
        "\n\nIMPORTANT - Location Guidelines:\n"
        "- Each event should have exactly ONE specific location in the locations array\n"
        "- Be as specific as possible (e.g., 'London' rather than 'England' or 'United Kingdom')\n"
        "- For historical locations with different modern names, use format: 'Historical Name (Modern Name)'\n"
        "- Examples: 'Königsberg (Kaliningrad)', 'Constantinople (Istanbul)', 'Bombay (Mumbai)'\n"
        "- Only use 'Location unknown' if the location truly cannot be determined from the sources\n"
        "\n\nIMPORTANT - Image Guidelines:\n"
        "- When images are provided, actively look for opportunities to include them in relevant events\n"
        "- Each image object must have: 'url' (the image URL), 'caption' (describing what the image shows), and 'source' (Wikimedia Commons URL)\n"
        "- Use the description from the provided image data to write a concise, factual caption\n"
        "- IMPORTANT: Each event should have at most ONE image - choose the most relevant one\n"
        "- Include images of: buildings/places mentioned, artworks/creations, documents/publications, monuments, flags, designs, inventions\n"
        "- For architects: include images of their buildings in construction/completion events\n"
        "- For artists: include images of their artworks in creation events\n"
        "- For inventors: include images of their inventions or patents\n"
        "- For authors: include images of book covers or manuscripts\n"
        "- For historical figures: include images of monuments, locations, or artifacts related to specific events\n"
        "- DO NOT include generic portraits or the person's photo in regular events (those go in the person metadata)\n"
        "- DO include images that show the result, location, or subject matter of the event\n"
        "\nEXAMPLE: For an event about publishing a translated article on the Analytical Engine, you might include:\n"
        '"images": [{"url": "https://upload.wikimedia.org/wikipedia/commons/c/cf/Diagram_for_the_computation_of_Bernoulli_numbers.jpg", "caption": "Diagram of an algorithm for the Analytical Engine for computing Bernoulli numbers", "source": "https://commons.wikimedia.org/wiki/File:Diagram_for_the_computation_of_Bernoulli_numbers.jpg"}]\n'
        "\nKeep date and date_end values as machine-readable ISO-8601 strings (YYYY-MM-DD, YYYY-MM, or YYYY). "
        "If a source uses descriptive phrasing like 'early 1900', place that text in date_note while selecting the closest structured date. "
        "Include person metadata with name, birth_date, death_date when known, primary_roles, summary, "
        "wikipedia URL, and portrait info if available."
    )

    try:
        # Use modern Responses API with structured outputs
        response = client.responses.parse(
            model=model,
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": instructions},
                {"role": "user", "content": prompt},
            ],
            text_format=LifeDataset,
        )
    except APIStatusError as error:
        message = ""
        try:
            message = error.response.get("error", {}).get(
                "message", "")  # type: ignore[attr-defined]
        except AttributeError:
            message = str(error)
        raise RuntimeError(
            "OpenAI API request failed. Verify the model name, account access, and billing status."
            # type: ignore[attr-defined]
            f" Details: {error.status_code} {message}"
        ) from error

    # Handle different response statuses
    if response.status == "failed":
        error_msg = f"Response generation failed: {response.error}" if response.error else "Unknown error"
        raise RuntimeError(error_msg)
    elif response.status != "completed":
        raise RuntimeError(
            f"Response has unexpected status: {response.status}")

    # Parse the structured output from the Responses API
    # The output_parsed property contains the Pydantic model
    parsed = response.output_parsed
    if parsed is None:
        raise RuntimeError("Failed to parse structured output from model")

    # Convert Pydantic model to dict
    return parsed.model_dump()


def _throttle_geocoder() -> None:
    global _last_geocode_at
    if GEOCODER_DELAY_SECONDS <= 0:
        return
    now = time.monotonic()
    elapsed = now - _last_geocode_at
    if elapsed < GEOCODER_DELAY_SECONDS:
        time.sleep(GEOCODER_DELAY_SECONDS - elapsed)
    _last_geocode_at = time.monotonic()


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


def enrich_event_coordinates(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    events = payload.get("events") or []
    if not isinstance(events, list) or not events:
        return payload, 0
    enriched: List[Dict[str, Any]] = []
    resolved_count = 0
    for event in events:
        if not isinstance(event, dict):
            enriched.append(event)
            continue
        locations = event.get("locations") or []
        if not isinstance(locations, list) or not locations:
            enriched.append(event)
            continue
        coordinate_entries = []
        for index, location in enumerate(locations):
            if not isinstance(location, str):
                continue
            geocoded = geocode_location(location)
            if not geocoded:
                continue
            entry: Dict[str, Any] = {
                "label": geocoded.get("display_name") or location,
                "name": location,
                "primary": index == 0,
                "centroid": [geocoded["lon"], geocoded["lat"]],
                "source": "nominatim",
            }
            if geocoded.get("bbox"):
                entry["bbox"] = geocoded["bbox"]
            coordinate_entries.append(entry)
        updated = {**event}
        if coordinate_entries:
            updated["location_coordinates"] = coordinate_entries
            resolved_count += 1
        else:
            updated.pop("location_coordinates", None)
        enriched.append(updated)
    payload["events"] = enriched
    return payload, resolved_count


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


def enforce_metadata(
    payload: Dict[str, Any],
    page_data: Dict[str, Any],
    summary_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload.setdefault("dataset", DATASET_NAME)
    payload["created_on"] = date.today().isoformat()
    person = payload.setdefault("person", {})
    name_candidates = _collect_person_name_candidates(
        person, page_data, summary_data)
    if name_candidates:
        preferred_name = min(name_candidates, key=_name_score)
        person["name"] = preferred_name
    else:
        person.setdefault("name", page_data.get("title"))
    for key in ("birth_date", "death_date"):
        value = person.get(key)
        if value:
            normalized, normalized_precision = normalize_date_value(
                value, "day")
            if normalized and normalized_precision == "day":
                person[key] = normalized
            elif normalized:
                # fallback to first day of the period for upstream consumers requiring ISO day
                suffix = "-01-01" if normalized_precision == "year" else "-01"
                person[key] = f"{normalized}{suffix}"
            else:
                person[key] = None
    if page_data.get("fullurl"):
        person.setdefault("wikipedia", page_data["fullurl"])
    original = page_data.get("original", {})
    if original and isinstance(person.get("portrait"), dict):
        person["portrait"].setdefault("image", original.get("source"))
    elif original:
        person["portrait"] = {"image": original.get(
            "source"), "source": page_data.get("fullurl")}
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
                raw_start_date)
            add_note(start_note)

        precision_value = event.get("date_precision") or "day"
        normalized_date, normalized_precision = normalize_date_value(
            start_input, precision_value
        )
        if not normalized_date:
            # Drop events without a usable date so the timeline remains ordered.
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
            comparison_precision = (
                normalized_end_precision or normalized_precision
            )
            upper_bound = _upper_bound_date(
                comparison_date, comparison_precision
            )
            if upper_bound and upper_bound > death_cutoff:
                # Skip events that extend beyond the subject's lifetime.
                continue

        existing_note_raw = event.get("date_note")
        cleaned_existing_note = None
        if isinstance(existing_note_raw, str):
            cleaned_existing_note = _clean_date_note_text(
                existing_note_raw) or existing_note_raw.strip()
        add_note(cleaned_existing_note)

        if note_values:
            note_output = "; ".join(note_values) if len(
                note_values) > 1 else note_values[0]
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

        # Handle optional images field - expects array of objects with url, caption, source
        raw_images = event.get("images") or []
        sanitized_images = []
        seen_images: Set[str] = set()
        if isinstance(raw_images, list):
            for image_data in raw_images:
                # Support both object format (with metadata) and legacy string format
                if isinstance(image_data, dict):
                    image_url = image_data.get("url", "").strip()
                    caption = image_data.get("caption", "").strip()
                    source = image_data.get("source", "").strip()

                    # Validate URL
                    if not image_url or not (image_url.startswith("http://") or image_url.startswith("https://")):
                        continue

                    # Check for duplicates
                    key = image_url.casefold()
                    if key in seen_images:
                        continue
                    seen_images.add(key)

                    # Store as object with metadata
                    sanitized_images.append({
                        "url": image_url,
                        "caption": caption or "Image from Wikimedia Commons",
                        "source": source or None
                    })
                elif isinstance(image_data, str):
                    # Legacy string format - convert to object
                    trimmed = image_data.strip()
                    if not trimmed or not (trimmed.startswith("http://") or trimmed.startswith("https://")):
                        continue
                    key = trimmed.casefold()
                    if key in seen_images:
                        continue
                    seen_images.add(key)
                    sanitized_images.append({
                        "url": trimmed,
                        "caption": "Image from Wikimedia Commons",
                        "source": None
                    })
        # Enforce maximum of one image per event
        if sanitized_images:
            event["images"] = sanitized_images[:1]
        else:
            event.pop("images", None)

        events.append(event)
    events.sort(key=event_sort_key)
    payload["events"] = events
    return payload


def write_dataset(payload: Dict[str, Any], person_id: str) -> Path:
    person_dir = PEOPLE_DIR / person_id
    person_dir.mkdir(parents=True, exist_ok=True)
    output_path = person_dir / "life_events.json"
    output_path.write_text(json.dumps(
        payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return output_path


def update_register(person_id: str, payload: Dict[str, Any], file_path: Path) -> None:
    person = payload.get("person", {})

    # Extract portrait
    portrait = person.get("portrait")

    # Calculate lifespan from birth and death dates
    lifespan = None
    birth_date = person.get("birth_date")
    death_date = person.get("death_date")
    if birth_date or death_date:
        birth_year = birth_date[:4] if birth_date else "?"
        death_year = death_date[:4] if death_date else "?"
        lifespan = f"{birth_year}–{death_year}"

    # Extract primary roles (limit to first 3)
    primary_roles = person.get("primary_roles", [])
    if isinstance(primary_roles, list):
        primary_roles = primary_roles[:3]

    # Get current ISO timestamp
    current_timestamp = datetime.now().astimezone().isoformat()

    entry = {
        "id": person_id,
        "name": person.get("name", person_id.replace("_", " ").title()),
        "summary": person.get("summary"),
    }

    # Add optional fields only if they have values
    if portrait:
        entry["portrait"] = portrait
    if lifespan:
        entry["lifespan"] = lifespan
    if primary_roles:
        entry["primaryRoles"] = primary_roles

    register = {"people": []}
    if REGISTER_PATH.exists():
        register = json.loads(REGISTER_PATH.read_text(encoding="utf-8"))
    people = register.setdefault("people", [])
    is_new = True
    for idx, existing in enumerate(people):
        if existing.get("id") == person_id:
            # Preserve the original 'created' timestamp if it exists
            created_timestamp = existing.get("created", current_timestamp)
            people[idx] = {**existing, **entry, "created": created_timestamp, "lastUpdated": current_timestamp}
            is_new = False
            break
    else:
        # New entry - set both created and lastUpdated to current timestamp
        entry["created"] = current_timestamp
        entry["lastUpdated"] = current_timestamp
        people.append(entry)
    people.sort(key=lambda item: item.get("name", ""))
    REGISTER_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTER_PATH.write_text(json.dumps(
        register, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def generate_dataset(subject: str, *, update_registry: bool = True, model: str = DEFAULT_MODEL) -> Path:
    print(f"[1/7] Fetching Wikipedia article for '{subject}'...")
    page_data = fetch_wikipedia_extract(subject)
    article_title = page_data.get("title", subject)
    print(f"[1/7] Found article '{article_title}'.")

    print(f"[2/7] Retrieving summary details...")
    summary_data = fetch_wikipedia_summary(article_title)
    if summary_data:
        print("[2/7] Summary retrieved successfully.")
    else:
        print(
            "[2/7] No summary endpoint data available; continuing with page extract only.")

    print("[3/7] Building prompt for OpenAI response (including Commons search)...")
    prompt = build_prompt(page_data, summary_data, subject)

    print(f"[4/7] Requesting structured dataset from model '{model}'...")
    payload = call_openai(prompt, model)
    print(f"[4/7] Response received from OpenAI.")

    print("[5/7] Normalizing dataset metadata...")
    payload = enforce_metadata(payload, page_data, summary_data)
    event_count = len(payload.get("events", []))
    print(f"[5/7] Dataset includes {event_count} events.")

    print("[6/7] Resolving event location coordinates...")
    payload, geocoded_events = enrich_event_coordinates(payload)
    if geocoded_events:
        print(f"[6/7] Coordinates resolved for {geocoded_events} events.")
    else:
        print("[6/7] No event coordinates were resolved.")

    person_id = slugify(payload.get("person", {}).get("name", subject))
    print(f"[7/7] Writing dataset for '{person_id}'...")
    file_path = write_dataset(payload, person_id)
    if update_registry:
        print("Updating persons register...")
        update_register(person_id, payload, file_path)
        print("Register update complete.")
    else:
        print("Register update skipped.")
    return file_path


def parse_args(argv: Any) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate life event datasets using Wikipedia and the OpenAI API.")
    parser.add_argument(
        "subject", help="Person to research, e.g. 'Ada Lovelace'.")
    parser.add_argument("--no-register", action="store_true",
                        help="Skip updating the persons register.")
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
        file_path = generate_dataset(
            args.subject,
            update_registry=not args.no_register,
            model=args.model,
        )
        print(f"Dataset written to {file_path}")
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
