#!/usr/bin/env python3
"""Translate person data (life events, ego networks, and registry entries) to a target language using OpenAI API."""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from openai import OpenAI, APIStatusError
from pydantic import BaseModel

from config import DEFAULT_MODEL

# Constants
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
REGISTER_PATH = DATA_DIR / "persons.json"
PEOPLE_DIR = DATA_DIR / "people"

# Language name mapping for better prompts
LANGUAGE_NAMES = {
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
    "pl": "Polish",
    "ru": "Russian",
    "ja": "Japanese",
    "zh": "Chinese",
    "ko": "Korean",
}


# Pydantic models for translation (matching existing data schemas)


class ImageMetadata(BaseModel):
    """Metadata for an image associated with an event."""

    url: str
    caption: str
    source: str


class Annotation(BaseModel):
    """Explanation for an annotated term in event description."""

    explanation: str
    wikipedia_url: Optional[str] = None


class LocationCoordinate(BaseModel):
    """Geographic coordinates for a location."""

    label: str
    name: str
    primary: bool
    centroid: List[float]
    source: str
    bbox: Optional[List[float]] = None


class LifeEvent(BaseModel):
    """A significant life event."""

    date: str
    date_precision: str
    date_end: Optional[str] = None
    date_end_precision: Optional[str] = None
    date_note: Optional[str] = None
    age: Optional[int] = None
    title: str
    description: str
    locations: Optional[List[str]] = None
    sources: Optional[List[str]] = None
    images: Optional[List[ImageMetadata]] = None
    location_coordinates: Optional[List[LocationCoordinate]] = None
    chapter: Optional[str] = None
    categories: Optional[List[str]] = None
    annotations: Optional[Dict[str, Annotation]] = None


class LifeChapter(BaseModel):
    """A chapter grouping a sequence of life events."""

    id: str
    headline: str
    bridge_statement: str
    date_start: str
    date_start_precision: str
    date_end: str
    date_end_precision: str
    age_start: Optional[int] = None
    age_end: Optional[int] = None


class Portrait(BaseModel):
    """Portrait information for the person."""

    image: Optional[str] = None
    source: Optional[str] = None


class Person(BaseModel):
    """Metadata about the person."""

    name: str
    birth_date: Optional[str] = None
    death_date: Optional[str] = None
    primary_roles: List[str]
    summary: str
    wikipedia: Optional[str] = None
    portrait: Optional[Portrait] = None


class LifeDataset(BaseModel):
    """Complete structured dataset for a person's life events."""

    dataset: str
    created_on: str
    person: Person
    chapters: Optional[List[LifeChapter]] = None
    events: List[LifeEvent]


class EgoConnection(BaseModel):
    """A connection in the ego network."""

    person_name: str
    relationship_type: str
    relationship_description: str
    start_year: Optional[int] = None
    end_year: Optional[int] = None
    strength: Optional[str] = None
    interaction_frequency: Optional[str] = None
    influence_direction: Optional[str] = None
    shared_activities: Optional[List[str]] = None
    sources: Optional[List[str]] = None
    notes: Optional[str] = None


class EgoPerson(BaseModel):
    """Central person in ego network."""

    name: str
    birth_year: Optional[int] = None
    death_year: Optional[int] = None
    primary_roles: List[str]
    summary: str
    wikipedia: Optional[str] = None


class CategorySummary(BaseModel):
    """Summary for a relationship category."""

    relationship_type: str
    summary: str


class EgoNetwork(BaseModel):
    """Complete ego network dataset."""

    dataset: str
    created_on: str
    ego: EgoPerson
    connections: List[EgoConnection]
    category_summaries: Optional[List[CategorySummary]] = None


class PersonRegistryEntry(BaseModel):
    """Person entry in the registry."""

    id: str
    name: str
    summary: str
    portrait: Optional[Portrait] = None
    primaryRoles: List[str]
    birthDate: Optional[str] = None
    deathDate: Optional[str] = None
    created: str
    lastUpdated: str


def slugify(name: str) -> str:
    """Convert a person name to a slug (person_id)."""
    # Remove parenthetical content
    name = name.split("(")[0].strip()
    # Convert to lowercase and replace spaces/special chars with underscores
    slug = name.lower().replace(" ", "_").replace(".", "_").replace("-", "_")
    # Remove consecutive underscores
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug.strip("_")


def find_person_by_name_or_id(name_or_id: str) -> Optional[Dict[str, Any]]:
    """Find a person in the registry by name or ID."""
    if not REGISTER_PATH.exists():
        print(f"Error: Registry file not found: {REGISTER_PATH}")
        return None

    with open(REGISTER_PATH, "r", encoding="utf-8") as f:
        registry = json.load(f)

    people = registry.get("people", [])

    # Try exact ID match first
    for person in people:
        if person.get("id") == name_or_id:
            return person

    # Try slugified name match
    slug = slugify(name_or_id)
    for person in people:
        if person.get("id") == slug:
            return person

    # Try name match (case-insensitive)
    search_lower = name_or_id.lower()
    for person in people:
        if person.get("name", "").lower().replace("_", " ") == search_lower:
            return person

    return None


def load_json_file(file_path: Path) -> Optional[Dict[str, Any]]:
    """Load a JSON file, return None if it doesn't exist."""
    if not file_path.exists():
        return None

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {file_path}: {e}")
        return None


def save_json_file(data: Dict[str, Any], file_path: Path, indent: int = 2) -> bool:
    """Save data to a JSON file."""
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error: Failed to save {file_path}: {e}")
        return False


def translate_life_events(
    source_data: Dict[str, Any],
    target_lang: str,
    client: OpenAI,
    model: str,
    verbose: bool = False,
) -> Optional[Dict[str, Any]]:
    """Translate life events dataset to target language."""
    lang_name = LANGUAGE_NAMES.get(target_lang, target_lang)

    prompt = """Translate this biographical life events document to {lang_name}.

TRANSLATION RULES:
1. Translate all text content: titles, descriptions, chapter headlines, image captions, summary, roles, annotation explanations
2. PERSON NAMES - Keep in original form UNLESS:
   - The translated version is very common in {lang_name} (e.g., Henry II → Heinrich II in German)
   - The English version is not the original (e.g., non-English historical figures whose names were anglicized)
3. PLACE NAMES - Translate where it makes sense:
   - Use native/localized versions when they exist (e.g., "London" → "Londres" in French, "Munich" → "München" in German)
   - Translate geographic descriptors (e.g., "England" → "Inglaterra" in Spanish)
   - Keep specific street names and addresses mostly intact but translate generic terms (e.g., "Street", "Avenue")
4. ANNOTATION MARKERS - CRITICAL:
   - Descriptions may contain [[term|display]] markers for annotations
   - KEEP the marker syntax [[term|display]] EXACTLY as-is
   - Translate ONLY the display text (after the |)
   - Translate the explanation in the annotations object
   - Do NOT translate the term keys (before the |)
   - Example: "worked on [[Entscheidungsproblem|decision problem]]" → "arbeitete am [[Entscheidungsproblem|Entscheidungsproblem]]"
5. Preserve ALL non-text fields EXACTLY as they are:
   - ALL dates (date, date_precision, date_end, date_end_precision, birth_date, death_date, created_on)
   - ALL coordinates (location_coordinates, centroid, bbox)
   - ALL URLs (sources, images.url, images.source, wikipedia, annotations.*.wikipedia_url)
   - ALL IDs (chapter IDs in events[].chapter, dataset, annotation term keys)
   - ALL technical fields (age, date_note if it's technical)
6. Maintain the exact JSON structure
7. Use natural, fluent {lang_name}

Here is the JSON document to translate:

{json.dumps(source_data, indent=2, ensure_ascii=False)}

Return ONLY the complete translated JSON document with the same structure."""

    if verbose:
        print(f"  Translating life events to {lang_name}...")

    try:
        response = client.beta.chat.completions.parse(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": f"You are a professional translator specializing in biographical content. Translate accurately to {lang_name} while preserving all technical data and structure.",
                },
                {"role": "user", "content": prompt},
            ],
            response_format=LifeDataset,
        )

        result = response.choices[0].message
        if result.parsed:
            return result.parsed.model_dump(exclude_none=False)
        elif result.refusal:
            print(f"  Error: Model refused to translate: {result.refusal}")
            return None
        else:
            print("  Error: No parsed result returned")
            return None

    except APIStatusError as e:
        print(f"  Error: OpenAI API error: {e}")
        return None
    except Exception as e:
        print(f"  Error: Translation failed: {e}")
        return None


def translate_ego_network(
    source_data: Dict[str, Any],
    target_lang: str,
    client: OpenAI,
    model: str,
    verbose: bool = False,
) -> Optional[Dict[str, Any]]:
    """Translate ego network dataset to target language."""
    lang_name = LANGUAGE_NAMES.get(target_lang, target_lang)

    prompt = """Translate this social network document to {lang_name}.

TRANSLATION RULES:
1. Translate: relationship_description, shared_activities, notes, category summaries, ego.summary, ego.primary_roles
2. PERSON NAMES - Apply consistent rules:
   - Keep in original form by default
   - ONLY translate if the person is very well-known and has a standard {lang_name} name version
   - Examples for German: Henry II → Heinrich II (German emperor), Queen Elizabeth → Königin Elisabeth
   - Keep modern English names as-is (e.g., Max Newman, Joan Clarke, Alan Turing)
   - Apply THE SAME rule to ALL occurrences of the same person throughout the document
   - BE CONSISTENT: if you translate a name once, translate it everywhere; if you keep it once, keep it everywhere
3. RELATIONSHIP TYPES - Translate the MAIN CATEGORY only:
   - Relationship types have the format "category/subcategory" (e.g., "professional/mentor", "family/father")
   - Translate the CATEGORY (part before the slash) to {lang_name}
   - Keep the SUBCATEGORY (part after the slash) in English
   - Examples for German: "professional/mentor" → "beruflich/mentor", "family/father" → "familie/father"
   - For category_summaries, also translate the relationship_type field using the same rule
4. Preserve ALL non-text fields EXACTLY:
   - ALL dates (birth_year, death_year, start_year, end_year, created_on)
   - ALL URLs (wikipedia, sources)
   - Strength values (weak, moderate, strong) - keep in English
   - Interaction frequencies (rare, occasional, regular, frequent) - keep in English
   - Influence directions (alter_to_ego, ego_to_alter, bidirectional) - keep in English
   - Dataset name - keep in English
5. Maintain the exact JSON structure
6. Use natural, fluent {lang_name}

Here is the JSON document to translate:

{json.dumps(source_data, indent=2, ensure_ascii=False)}

Return ONLY the complete translated JSON document with the same structure."""

    if verbose:
        print(f"  Translating ego network to {lang_name}...")

    try:
        response = client.beta.chat.completions.parse(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": f"You are a professional translator specializing in social network and relationship data. Translate accurately to {lang_name} while preserving all technical classifications.",
                },
                {"role": "user", "content": prompt},
            ],
            response_format=EgoNetwork,
        )

        result = response.choices[0].message
        if result.parsed:
            return result.parsed.model_dump(exclude_none=False)
        elif result.refusal:
            print(f"  Error: Model refused to translate: {result.refusal}")
            return None
        else:
            print("  Error: No parsed result returned")
            return None

    except APIStatusError as e:
        print(f"  Error: OpenAI API error: {e}")
        return None
    except Exception as e:
        print(f"  Error: Translation failed: {e}")
        return None


def translate_registry_entry(
    source_entry: Dict[str, Any],
    target_lang: str,
    client: OpenAI,
    model: str,
    verbose: bool = False,
) -> Optional[Dict[str, Any]]:
    """Translate person registry entry to target language."""
    lang_name = LANGUAGE_NAMES.get(target_lang, target_lang)

    prompt = """Translate this person registry entry to {lang_name}.

TRANSLATION RULES:
1. Translate: summary, primaryRoles
2. PERSON NAME - Keep in original form UNLESS:
   - The person is very well-known and has a standard {lang_name} name version
   - Examples for German: Henry II → Heinrich II (German emperor)
   - Keep modern English names as-is (e.g., Alan Turing, Ada Lovelace)
3. Preserve ALL non-text fields EXACTLY:
   - id (must be identical)
   - portrait URLs (image, source)
   - dates (birthDate, deathDate, created)
4. Update lastUpdated to current timestamp
5. Use natural, fluent {lang_name}

Here is the JSON entry to translate:

{json.dumps(source_entry, indent=2, ensure_ascii=False)}

Return ONLY the complete translated JSON entry with the same structure."""

    if verbose:
        print(f"  Translating registry entry to {lang_name}...")

    try:
        response = client.beta.chat.completions.parse(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": f"You are a professional translator specializing in biographical data. Translate accurately to {lang_name} while preserving all identifiers and URLs.",
                },
                {"role": "user", "content": prompt},
            ],
            response_format=PersonRegistryEntry,
        )

        result = response.choices[0].message
        if result.parsed:
            translated = result.parsed.model_dump(exclude_none=False)
            # Ensure lastUpdated is current
            translated["lastUpdated"] = datetime.now().astimezone().isoformat()
            return translated
        elif result.refusal:
            print(f"  Error: Model refused to translate: {result.refusal}")
            return None
        else:
            print("  Error: No parsed result returned")
            return None

    except APIStatusError as e:
        print(f"  Error: OpenAI API error: {e}")
        return None
    except Exception as e:
        print(f"  Error: Translation failed: {e}")
        return None


def update_language_registry(
    person_entry: Dict[str, Any], target_lang: str, verbose: bool = False
) -> bool:
    """Update or create the language-specific registry file."""
    registry_path = DATA_DIR / f"persons_{target_lang}.json"

    # Load existing registry or create new one
    if registry_path.exists():
        with open(registry_path, "r", encoding="utf-8") as f:
            registry = json.load(f)
    else:
        registry = {"people": []}

    # Find and update or append
    person_id = person_entry["id"]
    found = False
    for i, person in enumerate(registry["people"]):
        if person["id"] == person_id:
            registry["people"][i] = person_entry
            found = True
            if verbose:
                print(f"  Updated {person_id} in {registry_path.name}")
            break

    if not found:
        registry["people"].append(person_entry)
        if verbose:
            print(f"  Added {person_id} to {registry_path.name}")

    # Save registry
    return save_json_file(registry, registry_path)


def translate_person_data(
    person_id: str,
    target_lang: str,
    client: OpenAI,
    model: str = DEFAULT_MODEL,
    force: bool = False,
    verbose: bool = False,
) -> Dict[str, bool]:
    """
    Translate a person's data to target language.

    Returns:
        Dict with keys: 'life_events', 'ego_network', 'registry'
        Values are True if successful, False otherwise
    """
    results = {"life_events": False, "ego_network": False, "registry": False}

    person_dir = PEOPLE_DIR / person_id
    if not person_dir.exists():
        print(f"Error: Person directory not found: {person_dir}")
        return results

    # Define paths
    target_dir = person_dir / target_lang
    life_events_source = person_dir / "life_events.json"
    life_events_target = target_dir / "life_events.json"
    ego_network_source = person_dir / "ego_network.json"
    ego_network_target = target_dir / "ego_network.json"

    # Check if translation already exists
    if not force and target_dir.exists() and life_events_target.exists():
        if verbose:
            print(
                f"  Translation already exists for {person_id} (use --force to overwrite)"
            )
        return results

    # Create target directory
    target_dir.mkdir(parents=True, exist_ok=True)

    # Translate life events
    if life_events_source.exists():
        source_data = load_json_file(life_events_source)
        if source_data:
            translated = translate_life_events(
                source_data, target_lang, client, model, verbose
            )
            if translated:
                if save_json_file(translated, life_events_target):
                    results["life_events"] = True
                    if verbose:
                        print(f"  ✓ Life events translated: {life_events_target}")
    else:
        if verbose:
            print(f"  ⚠ Life events not found: {life_events_source}")

    # Translate ego network
    if ego_network_source.exists():
        source_data = load_json_file(ego_network_source)
        if source_data:
            translated = translate_ego_network(
                source_data, target_lang, client, model, verbose
            )
            if translated:
                if save_json_file(translated, ego_network_target):
                    results["ego_network"] = True
                    if verbose:
                        print(f"  ✓ Ego network translated: {ego_network_target}")
    else:
        if verbose:
            print(f"  ⚠ Ego network not found: {ego_network_source}")

    # Translate registry entry
    person_entry = find_person_by_name_or_id(person_id)
    if person_entry:
        translated = translate_registry_entry(
            person_entry, target_lang, client, model, verbose
        )
        if translated:
            if update_language_registry(translated, target_lang, verbose):
                results["registry"] = True
                if verbose:
                    print("  ✓ Registry entry updated")
    else:
        if verbose:
            print("  ⚠ Person not found in registry")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Translate a person's data to a target language using OpenAI API"
    )
    parser.add_argument(
        "person_name_or_id",
        help="Person name or ID (e.g., 'Alan Turing' or 'alan_turing')",
    )
    parser.add_argument(
        "--target-lang",
        required=True,
        help="Target language code (e.g., 'de', 'fr', 'es')",
    )
    parser.add_argument(
        "--force", action="store_true", help="Overwrite existing translation"
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"OpenAI model to use (default: {DEFAULT_MODEL})",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")

    args = parser.parse_args()

    # Validate OpenAI API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY environment variable not set")
        sys.exit(1)

    # Initialize OpenAI client
    client = OpenAI(api_key=api_key)

    # Find person
    print(f"Looking up person: {args.person_name_or_id}")
    person = find_person_by_name_or_id(args.person_name_or_id)
    if not person:
        print(f"Error: Person not found: {args.person_name_or_id}")
        sys.exit(1)

    person_id = person["id"]
    person_name = person["name"]
    lang_name = LANGUAGE_NAMES.get(args.target_lang, args.target_lang)

    print(f"Translating {person_name} ({person_id}) to {lang_name}...")

    # Translate
    results = translate_person_data(
        person_id=person_id,
        target_lang=args.target_lang,
        client=client,
        model=args.model,
        force=args.force,
        verbose=args.verbose,
    )

    # Report results
    print("\nTranslation Results:")
    print(f"  Life Events: {'✓' if results['life_events'] else '✗'}")
    print(f"  Ego Network: {'✓' if results['ego_network'] else '✗'}")
    print(f"  Registry:    {'✓' if results['registry'] else '✗'}")

    success = any(results.values())
    if success:
        print(f"\n✓ Translation completed for {person_name}")
        sys.exit(0)
    else:
        print(f"\n✗ Translation failed for {person_name}")
        sys.exit(1)


if __name__ == "__main__":
    main()
