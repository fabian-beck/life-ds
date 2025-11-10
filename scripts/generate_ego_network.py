#!/usr/bin/env python3
"""Generate ego network datasets for notable people using Wikipedia content and the OpenAI API."""

import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import requests
from openai import APIStatusError, OpenAI
from pydantic import BaseModel, Field

DATASET_NAME = "Life Data Stories"
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
REGISTER_PATH = DATA_DIR / "persons.json"
PEOPLE_DIR = DATA_DIR / "people"
MEDIAWIKI_API = "https://en.wikipedia.org/w/api.php"
# Structured outputs require gpt-4o-mini, gpt-4o-2024-08-06, or later models
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
DEFAULT_USER_AGENT = "life-ds-data-generator/1.0 (+https://github.com/fabian-beck/life-ds)"


# Pydantic models for structured outputs
class Connection(BaseModel):
    """A connection/relationship in the ego network."""
    person_name: str = Field(description="Full name of the connected person")
    relationship_type: str = Field(
        description="Type of relationship: 'family', 'colleague', 'mentor', 'student', 'collaborator', 'friend', 'rival', 'patron', 'employee', or 'other'"
    )
    relationship_description: str = Field(
        description="Brief description of the nature of the relationship"
    )
    start_year: Optional[int] = Field(
        None, description="Approximate year when the relationship began"
    )
    end_year: Optional[int] = Field(
        None, description="Approximate year when the relationship ended (null if ongoing or unknown)"
    )
    strength: str = Field(
        description="Strength of the relationship: 'strong', 'moderate', or 'weak'"
    )
    interaction_frequency: str = Field(
        description="How often they interacted: 'daily', 'weekly', 'monthly', 'yearly', 'occasional', or 'rare'"
    )
    influence_direction: str = Field(
        description="Direction of influence: 'bidirectional', 'ego_to_alter' (ego influenced the other), 'alter_to_ego' (other influenced ego)"
    )
    shared_activities: List[str] = Field(
        description="List of shared activities, projects, or contexts (e.g., 'co-authored papers', 'worked at same institution', 'family gatherings')"
    )
    sources: List[str] = Field(
        description="Array of Wikipedia URLs or references supporting this connection"
    )
    notes: Optional[str] = Field(
        None, description="Additional context or notable aspects of the relationship"
    )


class EgoNetworkMetadata(BaseModel):
    """Metadata about the ego (central person) in the network."""
    name: str = Field(description="Full name of the ego (central person)")
    birth_year: Optional[int] = Field(
        None, description="Birth year of the ego"
    )
    death_year: Optional[int] = Field(
        None, description="Death year of the ego (null if still alive)"
    )
    primary_roles: List[str] = Field(
        description="Primary roles or professions of the ego"
    )
    summary: str = Field(description="Brief biographical summary of the ego")
    wikipedia: Optional[str] = Field(None, description="Wikipedia URL for the ego")


class EgoNetwork(BaseModel):
    """Complete ego network dataset for a person."""
    dataset: str = Field(description="Name of the dataset")
    created_on: str = Field(description="Creation date in ISO-8601 format")
    ego: EgoNetworkMetadata = Field(description="Metadata about the central person")
    connections: List[Connection] = Field(
        description="List of connections/relationships in the ego network"
    )
    network_summary: str = Field(
        description="Brief summary of the ego's social network characteristics"
    )


def slugify(value: str) -> str:
    """Convert a string into a URL-friendly slug."""
    slug = re.sub(r"[^a-z0-9]+", "_", value.strip().lower())
    return slug.strip("_") or "person"


def wikipedia_headers() -> Dict[str, str]:
    """Return headers for Wikipedia API requests."""
    user_agent = os.getenv("WIKIPEDIA_USER_AGENT", DEFAULT_USER_AGENT)
    return {"User-Agent": user_agent}


def _fetch_wikipedia_page(title: str) -> Dict[str, Any]:
    """Fetch Wikipedia page data."""
    params = {
        "action": "query",
        "format": "json",
        "prop": "extracts|info",
        "explaintext": 1,
        "redirects": 1,
        "inprop": "url",
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
    """Search Wikipedia for page titles matching the query."""
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
    return titles


def fetch_wikipedia_extract(title: str) -> Dict[str, Any]:
    """Fetch Wikipedia extract with fallback search."""
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


def load_existing_dataset(person_id: str) -> Optional[Dict[str, Any]]:
    """Load existing life events dataset if available."""
    person_dir = PEOPLE_DIR / person_id
    dataset_path = person_dir / "life_events.json"
    if dataset_path.exists():
        try:
            return json.loads(dataset_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
    return None


def build_prompt(page_data: Dict[str, Any], existing_dataset: Optional[Dict[str, Any]], subject: str) -> str:
    """Build the prompt for OpenAI API."""
    extract_text = page_data.get("extract", "").strip()

    combined = f"Page title: {page_data.get('title', subject)}\nPage URL: {page_data.get('fullurl', '')}\n\n"
    
    if existing_dataset:
        person_info = existing_dataset.get("person", {})
        combined += "Known information about the person:\n"
        combined += json.dumps(person_info, indent=2, ensure_ascii=True)
        combined += "\n\nSample life events:\n"
        events = existing_dataset.get("events", [])[:10]
        combined += json.dumps(events, indent=2, ensure_ascii=True)
        combined += "\n\n"

    if extract_text:
        truncated = extract_text[:15000]
        combined += f"Full Wikipedia extract (truncated to 15k characters if needed):\n{truncated}\n"

    return combined


def call_openai(prompt: str, model: str) -> Dict[str, Any]:
    """Call OpenAI API with structured output."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY environment variable is not set.")
    client = OpenAI(api_key=api_key)
    
    system = (
        "You are a meticulous social network analyst who converts raw Wikipedia content into structured JSON ego networks. "
        "Focus on identifying significant relationships in a person's life, including family members, colleagues, mentors, "
        "students, collaborators, friends, rivals, and other important connections."
    )
    
    instructions = (
        "Analyze the provided Wikipedia content and extract an ego network for the subject. "
        "Include 10-25 significant connections/relationships. For each connection provide:\n"
        "- person_name: Full name of the connected person\n"
        "- relationship_type: One of 'family', 'colleague', 'mentor', 'student', 'collaborator', 'friend', 'rival', 'patron', 'employee', or 'other'\n"
        "- relationship_description: Brief description of the relationship\n"
        "- start_year: When the relationship began (approximate)\n"
        "- end_year: When it ended (null if ongoing or unknown)\n"
        "- strength: 'strong', 'moderate', or 'weak'\n"
        "- interaction_frequency: How often they interacted ('daily', 'weekly', 'monthly', 'yearly', 'occasional', 'rare')\n"
        "- influence_direction: 'bidirectional', 'ego_to_alter', or 'alter_to_ego'\n"
        "- shared_activities: List of what they did together or shared contexts\n"
        "- sources: Wikipedia URLs supporting this connection\n"
        "- notes: Additional context (optional)\n\n"
        "Focus on well-documented relationships with clear evidence in the Wikipedia text. "
        "Prioritize quality over quantity - include only connections with sufficient information. "
        "Also provide ego metadata and a network summary describing the overall characteristics of the person's social network."
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
            text_format=EgoNetwork,
        )
    except APIStatusError as error:
        message = ""
        try:
            message = error.response.get("error", {}).get("message", "")
        except AttributeError:
            message = str(error)
        raise RuntimeError(
            "OpenAI API request failed. Verify the model name, account access, and billing status. "
            f"Details: {error.status_code} {message}"
        ) from error

    # Handle different response statuses
    if response.status == "failed":
        error_msg = f"Response generation failed: {response.error}" if response.error else "Unknown error"
        raise RuntimeError(error_msg)
    elif response.status != "completed":
        raise RuntimeError(f"Response has unexpected status: {response.status}")

    # Parse the structured output from the Responses API
    parsed = response.output_parsed
    if parsed is None:
        raise RuntimeError("Failed to parse structured output from model")

    # Convert Pydantic model to dict
    return parsed.model_dump()


def enforce_metadata(
    payload: Dict[str, Any],
    page_data: Dict[str, Any],
    person_id: str,
) -> Dict[str, Any]:
    """Ensure consistent metadata in the payload."""
    payload.setdefault("dataset", DATASET_NAME)
    payload["created_on"] = date.today().isoformat()
    
    ego = payload.setdefault("ego", {})
    ego.setdefault("name", page_data.get("title"))
    
    if page_data.get("fullurl"):
        ego.setdefault("wikipedia", page_data["fullurl"])
    
    # Sort connections by start_year (nulls last), then by relationship strength
    connections = payload.get("connections", [])
    
    def connection_sort_key(conn: Dict[str, Any]) -> tuple:
        start_year = conn.get("start_year")
        # Put connections with start_year first, sorted by year
        # Then those without, sorted by strength
        strength_order = {"strong": 0, "moderate": 1, "weak": 2}
        strength = strength_order.get(conn.get("strength", "").lower(), 3)
        
        if start_year is not None:
            return (0, start_year, strength)
        else:
            return (1, 9999, strength)
    
    connections.sort(key=connection_sort_key)
    payload["connections"] = connections
    
    return payload


def write_ego_network(payload: Dict[str, Any], person_id: str) -> Path:
    """Write ego network to a JSON file."""
    person_dir = PEOPLE_DIR / person_id
    person_dir.mkdir(parents=True, exist_ok=True)
    output_path = person_dir / "ego_network.json"
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8"
    )
    return output_path


def update_register(person_id: str, payload: Dict[str, Any], file_path: Path) -> None:
    """Update the persons register with ego network information."""
    # Use consistent path format: people/<person_id>/ego_network.json
    relative_file = f"people/{person_id}/ego_network.json"
    
    register = {"people": []}
    if REGISTER_PATH.exists():
        register = json.loads(REGISTER_PATH.read_text(encoding="utf-8"))
    
    people = register.setdefault("people", [])
    
    # Find existing entry and add ego network reference
    for idx, existing in enumerate(people):
        if existing.get("id") == person_id:
            existing["ego_network_file"] = relative_file
            existing["ego_network_size"] = len(payload.get("connections", []))
            break
    else:
        # Person not in register yet, add basic entry
        people.append({
            "id": person_id,
            "name": payload.get("ego", {}).get("name", person_id.replace("_", " ").title()),
            "ego_network_file": relative_file,
            "ego_network_size": len(payload.get("connections", [])),
            "wikipedia": payload.get("ego", {}).get("wikipedia"),
        })
    
    people.sort(key=lambda item: item.get("name", ""))
    REGISTER_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTER_PATH.write_text(
        json.dumps(register, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8"
    )


def generate_ego_network(
    subject: str,
    *,
    update_registry: bool = True,
    model: str = DEFAULT_MODEL
) -> Path:
    """Generate an ego network dataset for a person."""
    print(f"[1/6] Fetching Wikipedia article for '{subject}'...")
    page_data = fetch_wikipedia_extract(subject)
    article_title = page_data.get("title", subject)
    print(f"[1/6] Found article '{article_title}'.")

    person_id = slugify(article_title)
    
    print(f"[2/6] Checking for existing life events dataset...")
    existing_dataset = load_existing_dataset(person_id)
    if existing_dataset:
        print(f"[2/6] Found existing dataset for '{person_id}'.")
    else:
        print(f"[2/6] No existing dataset found (will use only Wikipedia content).")

    print("[3/6] Building prompt for OpenAI response...")
    prompt = build_prompt(page_data, existing_dataset, subject)

    print(f"[4/6] Requesting structured ego network from model '{model}'...")
    payload = call_openai(prompt, model)
    print(f"[4/6] Response received from OpenAI.")

    print("[5/6] Normalizing ego network metadata...")
    payload = enforce_metadata(payload, page_data, person_id)
    connection_count = len(payload.get("connections", []))
    print(f"[5/6] Ego network includes {connection_count} connections.")

    print(f"[6/6] Writing ego network for '{person_id}'...")
    file_path = write_ego_network(payload, person_id)
    
    if update_registry:
        print("Updating persons register...")
        update_register(person_id, payload, file_path)
        print("Register update complete.")
    else:
        print("Register update skipped.")
    
    return file_path


def parse_args(argv: Any) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate ego network datasets using Wikipedia and the OpenAI API."
    )
    parser.add_argument(
        "subject",
        help="Person to research, e.g. 'Ada Lovelace'."
    )
    parser.add_argument(
        "--no-register",
        action="store_true",
        help="Skip updating the persons register."
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
    """Main entry point."""
    args = parse_args(argv)
    try:
        file_path = generate_ego_network(
            args.subject,
            update_registry=not args.no_register,
            model=args.model,
        )
        print(f"Ego network written to {file_path}")
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
