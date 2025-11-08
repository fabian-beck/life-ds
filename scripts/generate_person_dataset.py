#!/usr/bin/env python3
"""Generate life event datasets for notable people using Wikipedia content and the OpenAI API."""

import argparse
import json
import os
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Set
from urllib.parse import quote

import requests
from openai import APIStatusError, OpenAI

DATASET_NAME = "Life Data Stories"
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
REGISTER_PATH = DATA_DIR / "persons.json"
DATASETS_DIR = DATA_DIR / "people"
MEDIAWIKI_API = "https://en.wikipedia.org/w/api.php"
WIKIPEDIA_SUMMARY_API = "https://en.wikipedia.org/api/rest_v1/page/summary/"
# Adjust the default model if your account has access to newer releases.
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-5")
DEFAULT_USER_AGENT = "life-ds-data-generator/1.0 (+https://github.com/fabian-beck/life-ds)"
GEOCODER_ENDPOINT = os.getenv(
    "LIFE_DS_GEOCODER_ENDPOINT",
    "https://nominatim.openstreetmap.org/search",
)
GEOCODER_DELAY_SECONDS = float(os.getenv("LIFE_DS_GEOCODER_DELAY", "1.0"))
GEOCODER_MAX_RESULTS = 1

_geocode_cache: Dict[str, Optional[Dict[str, Any]]] = {}
_last_geocode_at: float = 0.0


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
        "prop": "extracts|pageimages|info",
        "explaintext": 1,
        "redirects": 1,
        "inprop": "url",
        "piprop": "original",
        "titles": title,
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


def build_prompt(page_data: Dict[str, Any], summary_data: Dict[str, Any], subject: str) -> str:
    summary_text = summary_data.get("extract", "").strip()
    extract_text = page_data.get("extract", "").strip()
    combined = f"Page title: {page_data.get('title', subject)}\nPage URL: {page_data.get('fullurl', '')}\n\n"
    if summary_text:
        combined += f"Summary snippet:\n{summary_text}\n\n"
    if extract_text:
        truncated = extract_text[:12000]
        combined += f"Full extract (truncated to 12k characters if needed):\n{truncated}\n"
    return combined


def call_openai(prompt: str, model: str) -> Dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY environment variable is not set.")
    client = OpenAI(api_key=api_key)
    system = (
        "You are a meticulous historian who converts raw Wikipedia content into structured JSON. "
        "Return a JSON object with keys: dataset, created_on, person, events. "
        "Use ISO-8601 dates, include date_precision as 'day', 'month', or 'year'. "
        "Align event ages with the subject's birth date."
    )
    instructions = (
        "Produce 12-16 significant life events covering the subject's early life, "
        "education, major accomplishments, later years, and posthumous recognition if relevant. "
        "Each event needs: date, date_precision, age (null if not applicable), title, description, "
        "locations (array), sources (array of URLs pulled from Wikipedia). "
        "Include person metadata with name, birth_date, death_date when known, primary_roles, summary, "
        "wikipedia URL, and portrait info if available."
    )
    request_kwargs: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": instructions},
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
    }
    if not model.lower().startswith("gpt-5"):
        request_kwargs["temperature"] = 0.2
    else:
        print("Using model default temperature (unsupported override).")
    try:
        response = client.chat.completions.create(**request_kwargs)
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
    content = response.choices[0].message.content
    return json.loads(content)


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
    normalized = (query or "").strip()
    if not normalized:
        return None
    cached = _geocode_cache.get(normalized)
    if cached is not None:
        return cached
    try:
        _throttle_geocoder()
        response = requests.get(
            GEOCODER_ENDPOINT,
            params={
                "q": normalized,
                "format": "jsonv2",
                "limit": GEOCODER_MAX_RESULTS,
            },
            timeout=30,
            headers=geocoder_headers(),
        )
        response.raise_for_status()
        results: List[Dict[str, Any]] = response.json()
    except Exception as error:  # noqa: BLE001
        print(f"Warning: geocoding lookup failed for '{normalized}': {error}")
        _geocode_cache[normalized] = None
        return None
    if not results:
        _geocode_cache[normalized] = None
        return None
    primary = results[0]
    try:
        lon = float(primary.get("lon"))
        lat = float(primary.get("lat"))
    except (TypeError, ValueError):
        _geocode_cache[normalized] = None
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
        "name": normalized,
        "display_name": primary.get("display_name"),
        "lon": lon,
        "lat": lat,
        "bbox": bbox_values,
    }
    _geocode_cache[normalized] = result
    return result


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


def enforce_metadata(payload: Dict[str, Any], page_data: Dict[str, Any]) -> Dict[str, Any]:
    payload.setdefault("dataset", DATASET_NAME)
    payload["created_on"] = date.today().isoformat()
    person = payload.setdefault("person", {})
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
    events = []
    for event in payload.get("events", []) or []:
        normalized_date, normalized_precision = normalize_date_value(
            event.get("date"), event.get("date_precision", "day")
        )
        event = {**event}
        event["date"] = normalized_date
        event["date_precision"] = normalized_precision
        events.append(event)
    events.sort(key=event_sort_key)
    payload["events"] = events
    return payload


def write_dataset(payload: Dict[str, Any], person_id: str) -> Path:
    DATASETS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = DATASETS_DIR / f"{person_id}_life_events.json"
    output_path.write_text(json.dumps(
        payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return output_path


def update_register(person_id: str, payload: Dict[str, Any], file_path: Path) -> None:
    relative_file = file_path.relative_to(DATA_DIR)
    entry = {
        "id": person_id,
        "name": payload.get("person", {}).get("name", person_id.replace("_", " ").title()),
        "file": relative_file.as_posix(),
        "wikipedia": payload.get("person", {}).get("wikipedia"),
        "summary": payload.get("person", {}).get("summary"),
    }
    register = {"people": []}
    if REGISTER_PATH.exists():
        register = json.loads(REGISTER_PATH.read_text(encoding="utf-8"))
    people = register.setdefault("people", [])
    for idx, existing in enumerate(people):
        if existing.get("id") == person_id:
            people[idx] = {**existing, **entry}
            break
    else:
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

    print("[3/7] Building prompt for OpenAI response...")
    prompt = build_prompt(page_data, summary_data, subject)

    print(f"[4/7] Requesting structured dataset from model '{model}'...")
    payload = call_openai(prompt, model)
    print(f"[4/7] Response received from OpenAI.")

    print("[5/7] Normalizing dataset metadata...")
    payload = enforce_metadata(payload, page_data)
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
            "OpenAI model to use (default from OPENAI_MODEL env or 'gpt-5'). "
            "Run `openai models list` or see https://platform.openai.com/docs/models for options."
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
