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
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Tuple,
    Set,
    Union,
    Literal,
    cast,
)
from urllib.parse import quote

import requests
from openai import APIStatusError, OpenAI
from pydantic import BaseModel, Field

from config import (
    BULK_MODEL,
    BULK_REASONING_EFFORT,
    DEFAULT_MODEL,
    DEFAULT_REASONING_EFFORT,
    LOW_REASONING_EFFORT,
    enable_utf8_console,
)
from icon_categories import (
    format_icon_categories_for_prompt,
    normalize_icon,
)
from utils.model_calls import parse_structured
from utils.wikipedia_cache import (
    get_cached_wikipedia_page,
    get_cached_wikipedia_summary,
    ensure_cache,
    get_cache_dir,
)

enable_utf8_console()

# ============================================================================
# AI MODEL AND REASONING EFFORT CONFIGURATION
# ============================================================================
# Configure model and reasoning effort for each phase of the generation
# pipeline. This ensures consistent configuration between AI calls and logging.
#
# Phase 1 and the chapter pass decide what the life is and read the whole
# article set, so they take the default model and a reasoning budget. The three
# phases below them work from material those calls already settled, and every
# field they return is checked afterwards — icons against the catalog, involved
# people against known entities, places against the geocoder, image filenames
# against the fetched candidates — so they take the small model.

PHASE1_REASONING_EFFORT = DEFAULT_REASONING_EFFORT  # Event skeleton generation (medium)

# Event detail research. Back on the larger model since the phase began writing
# the background passage: every other field it returns is checked afterwards —
# icons against the catalog, people against known entities, places against the
# geocoder — which is what qualified it for the small model, and a passage of
# prose is checked by nobody. The small model is also weakest exactly where this
# passage is won or lost, at recalling detail out of a long context, and a
# background that recalls nothing is a background that restates the event.
PHASE2_MODEL = DEFAULT_MODEL
# Low rather than none for the extraction; the passage is the part that needs
# the deliberation, and it is written in the same call.
PHASE2_REASONING_EFFORT = DEFAULT_REASONING_EFFORT

# Image search string generation: writing Commons queries, which the search
# itself judges by returning something or nothing.
PHASE3_IMAGE_SEARCH_MODEL = BULK_MODEL
PHASE3_IMAGE_SEARCH_REASONING = LOW_REASONING_EFFORT

# Image-to-event matching. Low rather than none because the same call picks the
# reference portrait — the one output of this phase that a reader sees on every
# slide, and the input the portrait step spends an image call on.
PHASE3_IMAGE_MATCH_MODEL = BULK_MODEL
PHASE3_IMAGE_MATCH_REASONING = BULK_REASONING_EFFORT

CHAPTER_REASONING_EFFORT = DEFAULT_REASONING_EFFORT  # Chapter generation (medium)
RELATED_ARTICLES_REASONING = LOW_REASONING_EFFORT  # Related article discovery (none)

# Import from cache_wikipedia_materials for related articles functionality
try:
    from cache_wikipedia_materials import fetch_related_articles
except ImportError:
    fetch_related_articles = None  # type: ignore[assignment]

# Import Deutsche Biographie utilities
try:
    from utils.deutsche_biographie import (
        ensure_deutsche_biographie_cache,
        get_cached_deutsche_biographie,
        format_for_prompt as format_db_for_prompt,
    )
except ImportError:
    ensure_deutsche_biographie_cache = None  # type: ignore[assignment]
    get_cached_deutsche_biographie = None  # type: ignore[assignment]
    format_db_for_prompt = None  # type: ignore[assignment]

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
GEOCODER_MAX_ATTEMPTS = max(1, int(os.getenv("LIFE_DS_GEOCODER_ATTEMPTS", "3")))
GEOCODE_CACHE_PATH = Path(
    os.getenv("LIFE_DS_GEOCODE_CACHE", str(DATA_DIR / "_cache" / "geocode.json"))
)
UNKNOWN_LOCATION_LABEL = "Location unknown"

# Global caches
# Definitive answers, including "this place cannot be resolved". Persisted to
# GEOCODE_CACHE_PATH, so a later run does not ask Nominatim about Berlin again.
_geocode_cache: Dict[str, Optional[Dict[str, Any]]] = {}
_geocode_cache_loaded = False
# Queries whose lookup kept failing for what looks like a transient reason.
# Held for this run only, so the next run gets to try them again.
_geocode_failures: Set[str] = set()
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
    # The image search reads all three off the file page, and ImageViewer
    # renders all three. They are declared here because a field this model does
    # not name is dropped by the model dump on the way to disk — which is how
    # the corpus came to ship CC BY-SA images with the attribution their
    # licenses require stripped out.
    creator: Optional[str] = Field(
        None, description="Who made the image, as the file page credits them"
    )
    license: Optional[str] = Field(
        None, description="License name, e.g. 'CC BY-SA 3.0' or 'Public domain'"
    )
    licenseUrl: Optional[str] = Field(  # noqa: N815 - the field the UI reads
        None, description="Link to the license text, when the file page gives one"
    )


class Annotation(BaseModel):
    """Explanation for an annotated term in event description."""

    explanation: str = Field(description="Clear, concise explanation (1-2 sentences)")
    wikipedia_url: Optional[str] = Field(
        None, description="Optional Wikipedia URL for further reading"
    )


# ============================================================================
# EVENT CLASSIFICATION MODELS (Phase 2 - Optional)
# ============================================================================


class BirthClassification(BaseModel):
    """Classification for the birth event that opens a life story."""

    type: Literal["birth"] = Field(default="birth", description="Always 'birth'")
    father: Optional[str] = Field(
        None, description="Full name of the father, if documented"
    )
    mother: Optional[str] = Field(
        None,
        description="Full name of the mother, including her maiden name when documented",
    )
    birth_name: Optional[str] = Field(
        None,
        description="Full name given at birth, only when it differs from the name the person is known by",
    )
    characterization: Optional[str] = Field(
        None,
        description="Brief characterization of the household born into (e.g., 'academic family', 'farming household') - 1-4 words",
    )


class DeathClassification(BaseModel):
    """Classification for the death event that closes a life story."""

    type: Literal["death"] = Field(default="death", description="Always 'death'")
    cause: Optional[str] = Field(
        None,
        description="Brief cause of death (e.g., 'heart failure', 'cyanide poisoning') - 1-6 words. "
        "Omit when the sources do not give one; never guess a cause",
    )
    characterization: Optional[str] = Field(
        None,
        description="Brief characterization of the circumstances (e.g., 'after long illness', 'sudden', "
        "'ruled a suicide', 'in exile') - 1-4 words",
    )
    place_of_rest: Optional[str] = Field(
        None,
        description="Burial or resting place, when documented (e.g., 'Assistens Cemetery, Copenhagen')",
    )


class MarriagePartnershipClassification(BaseModel):
    """Classification for marriage/partnership events."""

    type: Literal["marriage_partnership"] = Field(
        default="marriage_partnership", description="Always 'marriage_partnership'"
    )
    subtype: Literal["marriage", "partnership"] = Field(
        description="Marriage (legal/ceremonial) or partnership (domestic/romantic)"
    )
    partner: str = Field(description="Full name of spouse/partner")
    duration: Optional[str] = Field(
        None, description="Duration if applicable (e.g., 'until death', '17 years')"
    )
    children: Optional[int] = Field(
        None, description="Number of children from this union, if mentioned"
    )
    characterization: Optional[str] = Field(
        None,
        description=(
            "Brief characterization of the bond between the partners (e.g., 'devoted partnership', "
            "'political alliance', 'strained') - 1-4 words. Describe the relationship itself, not "
            "only the work the partners did together; a purely professional label such as 'close "
            "collaboration' does not characterize a marriage"
        ),
    )


class MigrationClassification(BaseModel):
    """Classification for migration events (emigration, immigration, relocation, exile, etc.)."""

    type: Literal["migration"] = Field(
        default="migration", description="Always 'migration'"
    )
    from_location: str = Field(description="Origin location (city/region/country)")
    to_location: str = Field(description="Destination location (city/region/country)")
    characterization: Optional[str] = Field(
        None,
        description="Nature of move (e.g., 'political exile', 'career opportunity') - 1-4 words",
    )


class InventionClassification(BaseModel):
    """Classification for invention/innovation events."""

    type: Literal["invention"] = Field(
        default="invention", description="Always 'invention'"
    )
    title: str = Field(description="Name/title of invention")
    description: str = Field(description="Brief technical description (1-2 sentences)")
    impact: Optional[str] = Field(
        None, description="Historical/practical impact (1-2 sentences)"
    )


class PublicationClassification(BaseModel):
    """Classification for publication events (books, papers, articles, etc.)."""

    type: Literal["publication"] = Field(
        default="publication", description="Always 'publication'"
    )
    title: str = Field(description="Title of the work")
    publication_type: Literal[
        "book", "paper", "article", "manuscript", "thesis", "essay"
    ] = Field(description="Type of publication")
    publisher: Optional[str] = Field(
        None,
        description="Publisher or journal name (e.g., 'Nature', 'Cambridge University Press')",
    )
    significance: Optional[str] = Field(
        None,
        description="Brief significance note (e.g., 'seminal work', 'controversial', 'bestseller') - 1-4 words",
    )
    impact: Optional[str] = Field(
        None, description="Historical/intellectual impact (1-2 sentences)"
    )


# Union of all classification types
# Note: Using standard Union instead of discriminated union for OpenAI compatibility
EventClassification = Union[
    BirthClassification,
    DeathClassification,
    MarriagePartnershipClassification,
    MigrationClassification,
    InventionClassification,
    PublicationClassification,
]


# ============================================================================
# EVENT CLASSIFICATION CONFIGURATION
# ============================================================================
# Centralized configuration for event classifications.
#
# HOW TO ADD A NEW CLASSIFICATION:
# 1. Create a Pydantic model above (e.g., AwardClassification)
# 2. Add it to the EventClassification Union
# 3. Add a configuration entry below
#
# The system automatically handles:
# - Phase 1 prompts (detection guidelines)
# - Phase 2 prompts (class-specific research guidance)
# - Logging (formatted output)
#
# CONFIGURATION KEYS:
# - name: UPPERCASE name for prompts
# - display_name: Name for logs/UI
# - description: Brief description of classification
# - keywords: Detection keywords (documentation only)
# - detection_rules: When to apply this classification
# - fields: {field_name: description} of what classification contains
# - phase1_guidance: Multi-line detection guidelines for AI
# - phase2_focus: List of research focus areas (emphasize what NOT to repeat)
# - log_format: lambda cls: str for formatting log output

EVENT_CLASS_CONFIG: Dict[str, Dict[str, Any]] = {
    "birth": {
        "name": "BIRTH",
        "display_name": "BIRTH",
        "description": "The subject's own birth — the event that opens the story",
        "keywords": ["born", "birth", "birthplace"],
        "detection_rules": [
            "The event describes the SUBJECT being born (not the birth of a child, sibling, or anyone else)",
            "Usually the first event, dated on the subject's birth date, with age 0",
        ],
        "fields": {
            "father": "Full name of the father, if documented",
            "mother": "Full name of the mother, with maiden name when documented",
            "birth_name": "Optional: full name given at birth, only when it differs from the known name",
            "characterization": "Optional: the household born into, e.g. 'academic family', 'farming household' (1-4 words)",
        },
        "phase1_guidance": (
            "- BIRTH: The SUBJECT's own birth — never the birth of a child, sibling, or anyone else\n"
            "  * Exactly one event per life story carries this classification\n"
            "  * father: Full name of the father, omit when undocumented\n"
            "  * mother: Full name of the mother, with maiden name when documented, omit when undocumented\n"
            "  * Optional: birth_name (only when it differs from the name the person is known by), "
            "characterization (the household born into, 1-4 words)\n"
        ),
        "phase2_focus": [
            "DESCRIPTION: Focus on the circumstances — the household, the city, what the family did",
            "  * DO NOT repeat the parents' names or the birth name (classification has these)",
            "  * DO NOT annotate the parents' names (use INVOLVED_PEOPLE field instead)",
            "  * Good: 'The household was an intellectually active one, with regular gatherings of "
            "university colleagues.'",
            "  * Bad: 'He was born to Christian Bohr, a physiologist, and Ellen Adler Bohr...'",
            "LOCATIONS: Place of birth (city level)",
            "INVOLVED_PEOPLE: The parents (already in the classification, but also list here) and siblings",
            "ANNOTATIONS: Never annotate person names (including the parents)",
        ],
        "log_format": lambda cls: (
            "BIRTH ("
            + (
                " & ".join(name for name in (cls.father, cls.mother) if name)
                or "parents unknown"
            )
            + ")"
        ),
    },
    "death": {
        "name": "DEATH",
        "display_name": "DEATH",
        "description": "The subject's own death — the event that closes the story",
        "keywords": ["died", "death", "killed", "executed", "passed away"],
        "detection_rules": [
            "The event describes the SUBJECT dying (not the death of a parent, spouse, child, or anyone else)",
            "Usually the last event, dated on or near the subject's death date",
        ],
        "fields": {
            "cause": "Cause of death in 1-6 words, omitted when the sources do not give one",
            "characterization": "Optional: the circumstances, e.g. 'after long illness', 'sudden' (1-4 words)",
            "place_of_rest": "Optional: burial or resting place",
        },
        "phase1_guidance": (
            "- DEATH: The SUBJECT's own death — never the death of a parent, spouse, child, or anyone else\n"
            "  * Exactly one event per life story carries this classification\n"
            "  * cause: The cause of death as a noun phrase of 1-6 words ('heart failure', "
            "'cyanide poisoning', 'gunshot wound from a duel') — no pronouns, no 'complications "
            "related to'\n"
            "  * OMIT cause when the sources do not state one — never guess, and never infer it from old age\n"
            "  * When the cause is contested, give the documented one and say so in characterization "
            "('ruled a suicide', 'cause disputed')\n"
            "  * Optional: characterization (1-4 words), place_of_rest (burial or resting place)\n"
        ),
        "phase2_focus": [
            "DESCRIPTION: Focus on the final days, the setting, and who was there",
            "  * DO NOT repeat the cause of death or the resting place (classification has these)",
            "  * DO NOT add legacy analysis or career retrospectives — those belong in the conclusion",
            "  * Good: 'He spent his last afternoon at home in Carlsberg, resting after lunch.'",
            "  * Bad: 'Bohr died of heart failure in Copenhagen, closing a career that had reshaped physics.'",
            "LOCATIONS: Where the person died (city level)",
            "INVOLVED_PEOPLE: People present or closely involved at the end",
            "ANNOTATIONS: A medical term may be annotated; never annotate the person's own name",
        ],
        "log_format": lambda cls: f"DEATH ({cls.cause or 'cause undocumented'})",
    },
    "marriage_partnership": {
        "name": "MARRIAGE_PARTNERSHIP",
        "display_name": "MARRIAGE",
        "description": "Wedding, marriage ceremony, or start of documented partnership",
        "keywords": ["married", "marriage", "wed", "wedding", "spouse"],
        "detection_rules": [
            "Event title/description contains 'married', 'marriage', 'wed', 'wedding', 'spouse'",
        ],
        "fields": {
            "subtype": "marriage (legal/ceremonial) OR partnership (domestic/romantic)",
            "partner": "Full name of spouse/partner",
            "duration": "Optional: e.g., 'until death', '17 years'",
            "children": "Optional: integer count",
            "characterization": "Optional: character of the bond, e.g., 'devoted partnership', 'political alliance', 'strained' (1-4 words); not a purely professional label",
        },
        "phase1_guidance": (
            "- MARRIAGE_PARTNERSHIP: Event title/description contains 'married', 'marriage', 'wed', 'wedding', 'spouse'\n"
            "  * subtype: 'marriage' (legal/ceremonial) OR 'partnership' (domestic/romantic)\n"
            "  * partner: Full name of spouse/partner\n"
            "  * Optional: duration (e.g., 'until death', '17 years'), children (integer), characterization (1-4 words)\n"
            "  * characterization describes the bond itself (e.g., 'devoted partnership', 'political alliance', 'strained'),\n"
            "    never a purely professional label such as 'close collaboration' or 'work partnership'\n"
        ),
        "phase2_focus": [
            "INVOLVED_PEOPLE: Include the partner's name (already in classification, but also list here)",
            "LOCATIONS: Wedding venue city (keep to city level, e.g., 'London' not full venue name)",
            "DESCRIPTION: Focus on ceremony details, circumstances, social context",
            "  * DO NOT repeat partner name, duration, children count (classification has these)",
            "  * DO NOT annotate the partner's name (use INVOLVED_PEOPLE field instead)",
            "  * Example: 'The ceremony took place at a small chapel, attended by close family.'",
            "ANNOTATIONS: Never annotate person names (including partner)",
        ],
        "log_format": lambda cls: f"MARRIAGE ({cls.partner})",
    },
    "migration": {
        "name": "MIGRATION",
        "display_name": "MIGRATION",
        "description": "Permanent or significant relocation (emigration, immigration, exile, refugee movement)",
        "keywords": [
            "emigrated",
            "immigrated",
            "fled",
            "moved to",
            "settled in",
            "exile",
            "refuge",
            "relocated",
        ],
        "detection_rules": [
            "Permanent or significant relocation to different country/region",
            "Words like: 'emigrated', 'immigrated', 'fled', 'moved to', 'settled in', 'exile', 'refuge', 'relocated'",
            "Includes: emigration, immigration, exile, refugee movement, major relocations",
            "NOT temporary: conferences, visits, tours, business trips, brief study abroad",
        ],
        "fields": {
            "from_location": "Origin country/region",
            "to_location": "Destination country/region",
            "characterization": "Optional: e.g., 'political exile', 'career opportunity', 'refugee flight' (1-4 words)",
        },
        "phase1_guidance": (
            "- MIGRATION: Permanent or significant relocation to different country/region\n"
            "  * Words like: 'emigrated', 'immigrated', 'fled', 'moved to', 'settled in', 'exile', 'refuge', 'relocated'\n"
            "  * Includes: emigration, immigration, exile, refugee movement, major relocations\n"
            "  * NOT temporary: conferences, visits, tours, business trips, brief study abroad\n"
            "  * from_location: Origin country/region\n"
            "  * to_location: Destination country/region\n"
            "  * Optional: characterization (e.g., 'political exile', 'career opportunity', 'refugee flight')\n"
        ),
        "phase2_focus": [
            "LOCATIONS: Provide TWO locations (departure and arrival cities)",
            "  * First location: Origin city/region (mark as primary=false)",
            "  * Second location: Destination city/region (mark as primary=true)",
            "  * Use city-level names (e.g., 'Berlin, Germany' → 'New York, USA')",
            "  * name_historic: City name at time of migration",
            "  * name_modern: Modern name for geocoding",
            "DESCRIPTION: Focus on reasons, journey details, immediate aftermath",
            "  * DO NOT repeat from/to locations or characterization (classification has these)",
            "  * DO NOT annotate destination country (classification provides location context)",
            "  * Example: 'Fleeing political persecution, the family traveled by ship, arriving with few possessions.'",
            "INVOLVED_PEOPLE: People who traveled together or helped with migration",
        ],
        "log_format": lambda cls: f"MIGRATION ({cls.from_location} → {cls.to_location})",
    },
    "invention": {
        "name": "INVENTION",
        "display_name": "INVENTION",
        "description": "Creation of novel device, machine, algorithm, or technique",
        "keywords": ["invented", "patented", "built", "designed", "created"],
        "detection_rules": [
            "Creating/building/patenting tangible invention, device, machine, algorithm",
            "Words like: 'invented', 'patented', 'built', 'designed', 'created' + technical artifact",
            "MUST be novel creation with clear technical output (not just ideas/theories)",
        ],
        "fields": {
            "title": "Name of invention",
            "description": "What it is and how it works (1 sentence, 15-25 words)",
            "impact": "Optional: Historical/practical impact (1 sentence, 12-20 words)",
        },
        "phase1_guidance": (
            "- INVENTION: Creating/building/patenting tangible invention, device, machine, algorithm\n"
            "  * Words like: 'invented', 'patented', 'built', 'designed', 'created' + technical artifact\n"
            "  * MUST be novel creation with clear technical output (not just ideas/theories)\n"
            "  * title: Name of invention\n"
            "  * description: What it is and how it works (1 sentence, 15-25 words)\n"
            "  * Optional: impact (1 sentence, 12-20 words)\n"
        ),
        "phase2_focus": [
            "DESCRIPTION: Focus ONLY on narrative context (where, when, why, with whom)",
            "  * DO NOT repeat technical specifications or features (classification has these)",
            "  * DO NOT annotate the invention name (classification provides full technical details)",
            "  * DO NOT use technical adjectives from classification (e.g., 'mechanical', 'binary', 'relay-based')",
            "  * Good: 'In his parents' Berlin apartment, Zuse built the Z1 using scavenged materials over two years.'",
            "  * Bad: 'Zuse built the Z1, a mechanical binary calculating machine using 20,000 parts...'",
            "  * The classification provides ALL technical details - description is pure narrative context",
            "LOCATIONS: Where invention was created/built (workshop, laboratory, city)",
            "INVOLVED_PEOPLE: Collaborators, assistants, financial sponsors, advisors",
            "ANNOTATIONS: Absolutely DO NOT annotate the invention itself",
            "  * ❌ FORBIDDEN: Annotating 'Z1', 'Z3', 'S1 and S2', etc.",
            "  * The classification already explains what the invention is",
        ],
        "log_format": lambda cls: f"INVENTION ({cls.title})",
    },
    "publication": {
        "name": "PUBLICATION",
        "display_name": "PUBLICATION",
        "description": "Publishing books, papers, articles, manuscripts, theses, or essays",
        "keywords": [
            "published",
            "wrote",
            "authored",
            "paper",
            "book",
            "article",
            "thesis",
            "manuscript",
        ],
        "detection_rules": [
            "Publication of written work (book, paper, article, manuscript, thesis, essay)",
            "Words like: 'published', 'wrote', 'authored', 'released', 'paper', 'book', 'article'",
            "MUST be actual publication event (not just writing/working on it)",
        ],
        "fields": {
            "title": "Title of the work",
            "publication_type": "book, paper, article, manuscript, thesis, or essay",
            "publisher": "Optional: Publisher or journal name (e.g., 'Nature', 'Cambridge University Press')",
            "significance": "Optional: e.g., 'seminal work', 'controversial', 'bestseller' (1-4 words)",
            "impact": "Optional: Historical/intellectual impact (1-2 sentences)",
        },
        "phase1_guidance": (
            "- PUBLICATION: Publishing books, papers, articles, manuscripts, theses, or essays\n"
            "  * Words like: 'published', 'wrote', 'authored', 'released', 'paper', 'book', 'article'\n"
            "  * MUST be actual publication event (not just writing/working on it)\n"
            "  * title: Title of the work\n"
            "  * publication_type: 'book', 'paper', 'article', 'manuscript', 'thesis', or 'essay'\n"
            "  * Optional: publisher (e.g., 'Nature', 'Cambridge University Press'), significance (1-4 words), impact (1-2 sentences)\n"
        ),
        "phase2_focus": [
            "DESCRIPTION: Focus on publication context, reception, circumstances",
            "  * DO NOT repeat title, publication type, or publisher (classification has these)",
            "  * DO NOT annotate the work's title (classification provides this)",
            "  * DO NOT describe the content in detail (classification's impact field covers this)",
            "  * Good: 'The paper was presented at a mathematics symposium and initially met with skepticism.'",
            "  * Bad: 'Turing published \"On Computable Numbers\", a groundbreaking paper on theoretical computation...'",
            "  * The classification provides publication details - description is narrative context only",
            "LOCATIONS: Where published, presented, or written (city level)",
            "INVOLVED_PEOPLE: Co-authors, editors, collaborators, reviewers",
            "ANNOTATIONS: DO NOT annotate the publication title (it's in classification)",
            "  * Focus on technical terms or concepts mentioned in the description",
        ],
        "log_format": lambda cls: f"PUBLICATION ({cls.title})",
    },
}


class Portrait(BaseModel):
    """Portrait information for the person."""

    image: Optional[str] = Field(None, description="URL of the portrait image")
    source: Optional[str] = Field(None, description="Source URL for the portrait")


class Person(BaseModel):
    """Metadata about the person."""

    name: str = Field(description="Full name of the person")
    birth_date: Optional[str] = Field(None, description="Birth date in ISO-8601 format")
    death_date: Optional[str] = Field(None, description="Death date in ISO-8601 format")
    primary_roles: List[str] = Field(
        description="2-3 primary roles/professions. Use short, generic, lowercase single words or two-word phrases. "
        "Examples: 'mathematician', 'physicist', 'writer', 'composer', 'computer scientist', 'monarch', 'inventor'. "
        "Avoid specific titles, company names, or idiosyncratic descriptions."
    )
    tagline: str = Field(
        description="Catchy, memorable phrase capturing the person's essence (3-7 words)"
    )
    summary: str = Field(description="Brief biographical summary")
    wikipedia: Optional[str] = Field(None, description="Wikipedia URL")
    portrait: Optional[Portrait] = Field(None, description="Portrait information")


class LifeChapter(BaseModel):
    """A chapter grouping a sequence of life events."""

    id: str = Field(
        description="Unique identifier for the chapter (lowercase, snake_case)"
    )
    headline: str = Field(
        description="Catchy, story-like chapter headline (2-5 words). Make it engaging and evocative, like a book chapter title. Avoid using 'and' - prefer vivid, specific headlines."
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
        description="Names of key people involved during this life chapter (aggregated from events, exclude the main subject)",
    )
    location: Optional[str] = Field(
        None,
        description="Summary of the main geographic area for this chapter (e.g., 'England', 'United States', 'Central Europe') - not a list of places",
    )


class ChapterGenerationOutput(BaseModel):
    """Output model for chapter generation phase."""

    chapters: List[LifeChapter] = Field(
        description="List of life chapters grouping the events"
    )
    conclusion: str = Field(
        description="A crisp, powerful conclusion statement about this person's life story (1-2 sentences). Capture their legacy or the essence of their journey."
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
    description: str = Field(
        description="Detailed description of the event (2-4 sentences)"
    )
    weight: Optional[float] = Field(
        None,
        description=(
            "How much of this life the event turns on, 0.0 to 1.0, judged "
            "against the other events of THIS life rather than against history "
            "at large."
        ),
    )
    event_class: Optional[EventClassification] = Field(
        None,
        description="Structured classification for specific event types (marriage_partnership, migration, invention). Omit for standard biographical events.",
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
        description="Modern geographic name for geocoding (e.g., 'Kaliningrad, Russia')",
    )
    centroid: Optional[List[float]] = Field(
        None, description="[longitude, latitude] coordinates, or null if not geocoded"
    )
    primary: bool = Field(
        default=True, description="True if this is the primary/main location"
    )


class EventDetails(BaseModel):
    """Phase 2: Research details for a specific event (NO images - handled in Phase 3)."""

    description: Optional[str] = Field(
        None,
        description="Event description with [[term|display]] markers for annotations. If no annotations, return the original description unchanged.",
    )
    locations: Optional[List[LocationInfo]] = Field(
        None,
        description="Array of location objects. Can be empty or contain multiple locations.",
    )
    involved_people: Optional[List[str]] = Field(
        None,
        description="Names of people directly involved in this event (exclude the main subject)",
    )
    sources: List[str] = Field(
        default_factory=list,
        description="Array of Wikipedia URLs or references supporting this event",
    )
    event_type_icon: Optional[str] = Field(
        None, description="MDI icon identifier (e.g., 'mdi-crown', 'mdi-book')"
    )
    annotations: Optional[Dict[str, Annotation]] = Field(
        None, description="Dictionary mapping term keys to their explanations"
    )
    background: Optional[str] = Field(
        None,
        description=(
            "A short passage of background for this event: the situation it "
            "sat in, why it mattered, what followed from it. Prose, not a "
            "list. Null when the sources do not support one."
        ),
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
        description="Unified location array with name_historic/name_modern/centroid/primary",
    )
    involved_people: Optional[List[str]] = Field(
        None, description="People directly involved in this event"
    )
    sources: List[str] = Field(description="Array of Wikipedia URLs or references")
    images: Optional[List[ImageMetadata]] = None
    event_type_icon: Optional[str] = Field(None, description="MDI icon identifier")
    chapter: Optional[str] = Field(None, description="Chapter ID this event belongs to")
    annotations: Optional[Dict[str, Annotation]] = Field(
        None, description="Dictionary mapping term keys to their explanations"
    )
    background: Optional[str] = Field(
        None, description="Short passage of background behind the event"
    )
    weight: Optional[float] = Field(
        None, description="How much of the life this event turns on, 0.0 to 1.0"
    )
    event_class: Optional[EventClassification] = Field(
        None, description="Structured classification for specific event types"
    )


# ============================================================================
# UTILITY FUNCTIONS (copied from generate_person_dataset.py)
# ============================================================================


def _fix_control_characters(text: str) -> str:
    """
    Replace ASCII control characters with proper Unicode typographic characters.

    OpenAI API sometimes returns control characters instead of proper Unicode:
    - \\x14 (DC4) should be — (em dash, U+2014)
    - \\x19 (EM) should be ' (right single quotation mark, U+2019)
    - \\x1c (FS) should be " (left double quotation mark, U+201C)
    - \\x1d (GS) should be " (right double quotation mark, U+201D)
    - \\x13 (DC3) should be – (en dash, U+2013)
    """
    if not isinstance(text, str):
        return text

    replacements = {
        "\x14": "\u2014",  # DC4 → em dash (—)
        "\x19": "\u2019",  # EM → right single quotation mark (')
        "\x1c": "\u201c",  # FS → left double quotation mark (")
        "\x1d": "\u201d",  # GS → right double quotation mark (")
        "\x13": "\u2013",  # DC3 → en dash (–)
    }

    for bad_char, good_char in replacements.items():
        if bad_char in text:
            text = text.replace(bad_char, good_char)

    return text


def _strip_wrapping_quotes(value: str) -> str:
    trimmed = value.strip()
    quotes = "\"'" "''"
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

        simplified_parentheses = _clean_candidate_name(
            re.sub(r"\s*\([^)]*\)", "", cleaned).strip()
        )
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


def normalize_date_value(value: Optional[str], precision: str) -> tuple[Any, str]:
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


def normalize_date_for_comparison(date_str: str, to_end: bool = False) -> str:
    """
    Normalize a partial date string for comparison.

    Dates can have different precisions (year, month, day). When comparing
    dates for chapter assignment, we need to expand partial dates to full
    dates to ensure correct comparison.

    Args:
        date_str: Date like "1945", "1945-07", or "1945-07-01"
        to_end: If True, pad to end of period; if False, pad to start

    Returns:
        Full date string in "YYYY-MM-DD" format

    Examples:
        normalize_date_for_comparison("1945", to_end=False) -> "1945-01-01"
        normalize_date_for_comparison("1945", to_end=True) -> "1945-12-31"
        normalize_date_for_comparison("1945-07", to_end=False) -> "1945-07-01"
        normalize_date_for_comparison("1945-07", to_end=True) -> "1945-07-31"
    """
    if not date_str:
        return "9999-12-31" if to_end else "0000-01-01"

    parts = date_str.split("-")
    if len(parts) == 1:  # Year only
        return f"{parts[0]}-12-31" if to_end else f"{parts[0]}-01-01"
    elif len(parts) == 2:  # Year-month
        if to_end:
            # Get last day of month
            year, month = int(parts[0]), int(parts[1])
            last_day = monthrange(year, month)[1]
            return f"{parts[0]}-{parts[1]}-{last_day:02d}"
        else:
            return f"{parts[0]}-{parts[1]}-01"
    return date_str  # Already full date


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
    normalized = _normalize_location_text(query or "")
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
    return cast(Dict[str, Any], page)


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
    return cast(Dict[str, Any], response.json())


# ============================================================================
# PHASE 3: COMMONS IMAGE SEARCH AND ASSIGNMENT (New Approach)
# ============================================================================

# Pydantic models for Phase 3


class ImageSearchStrings(BaseModel):
    """AI-generated search strings for finding images across all events."""

    search_strings: List[str] = Field(
        description="List of 20 search strings optimized for Wikimedia Commons"
    )


class ImageEventAssignment(BaseModel):
    """Assignment of a single image to an event."""

    image_id: int = Field(
        description="1-based index of the image from the candidate list"
    )
    event_index: int = Field(
        description="0-based index of the event to assign this image to"
    )
    caption: str = Field(
        description="Clean, concise caption for the image (5-15 words). Describe what the image shows."
    )
    reason: str = Field(
        description="Brief explanation of why this image fits this event"
    )


class PortraitSelection(BaseModel):
    """Selection of a portrait image for the person."""

    image_id: Optional[int] = Field(
        None,
        description="1-based index of the best portrait image, or null if no good portrait found",
    )
    reason: str = Field(description="Brief explanation of portrait selection")


class ImageAssignmentResult(BaseModel):
    """Result of AI image-to-event matching."""

    portrait: Optional[PortraitSelection] = Field(
        None,
        description="Selection of the best portrait image for the person's profile",
    )
    assignments: List[ImageEventAssignment] = Field(
        default_factory=list,
        description="List of image-to-event assignments. Each image can only be assigned once.",
    )


# ============================================================================
# IMAGE QUALITY SCORING FUNCTIONS
# ============================================================================


def parse_year_from_date_string(date_str: str) -> Optional[int]:
    """
    Extract year from various date string formats.

    Handles formats like:
    - "2020-05-15" (ISO)
    - "15 May 2020" (human readable)
    - "2020" (year only)
    - "1912-06-23 00:00:00" (with time)
    """
    if not date_str:
        return None

    # Try to extract 4-digit year
    year_match = re.search(r"\b(1\d{3}|20\d{2})\b", date_str)
    if year_match:
        return int(year_match.group(1))

    return None


def score_resolution(width: int, height: int) -> float:
    """
    Score image resolution (0-10 points).

    Higher resolution = better quality for display.
    """
    if width <= 0 or height <= 0:
        return 0.0

    pixels = width * height

    if pixels >= 4_000_000:  # 4+ MP
        return 10.0
    elif pixels >= 2_000_000:  # 2-4 MP
        return 8.0
    elif pixels >= 1_000_000:  # 1-2 MP
        return 6.0
    elif pixels >= 500_000:  # 0.5-1 MP
        return 4.0
    else:  # <0.5 MP
        return 2.0


def score_file_efficiency(file_size: int, width: int, height: int) -> float:
    """
    Score file size efficiency (0-5 points).

    Detects overly compressed (lossy) or bloated files.
    Sweet spot: 0.5-2 bytes/pixel for JPEG.
    """
    if file_size <= 0 or width <= 0 or height <= 0:
        return 3.0  # Neutral score if data unavailable

    pixels = width * height
    bytes_per_pixel = file_size / pixels

    if 0.5 <= bytes_per_pixel <= 2.0:
        return 5.0  # Well-compressed
    elif 0.2 <= bytes_per_pixel < 0.5:
        return 3.0  # Over-compressed (potential quality loss)
    elif 2.0 < bytes_per_pixel <= 5.0:
        return 4.0  # Slightly bloated but OK
    else:
        return 1.0  # Extremely compressed or bloated


def score_temporal_relevance(
    event_date: str, image_date_original: str, image_date_upload: str
) -> float:
    """
    Score temporal relevance (0-10 points).

    Prefers:
    - Period-appropriate images (contemporary to the event)
    - Recent uploads (better scans/digitization)
    """
    event_year = parse_year_from_date_string(event_date)
    original_year = parse_year_from_date_string(image_date_original)
    upload_year = parse_year_from_date_string(image_date_upload)

    score = 0.0

    # Period-appropriate images (huge bonus)
    if original_year and event_year:
        year_diff = abs(original_year - event_year)
        if year_diff <= 5:
            score += 10.0  # Contemporary image
        elif year_diff <= 20:
            score += 7.0  # Near-contemporary
        elif year_diff <= 50:
            score += 4.0  # Same era
        elif year_diff <= 100:
            score += 2.0  # Within lifetime

    # Recent uploads bonus (better scans/digitization)
    if upload_year:
        if upload_year >= 2020:
            score += 3.0  # Very recent upload
        elif upload_year >= 2015:
            score += 2.0  # Recent upload
        elif upload_year >= 2010:
            score += 1.0  # Modern upload

    return min(score, 10.0)  # Cap at 10


def extract_keywords_from_text(text: str, min_length: int = 4) -> List[str]:
    """
    Extract meaningful keywords from text.

    Filters out common words and keeps substantive terms.
    """
    if not text:
        return []

    # Common stopwords to filter out
    stopwords = {
        "the",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "as",
        "is",
        "was",
        "are",
        "were",
        "been",
        "be",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "must",
        "can",
        "this",
        "that",
        "these",
        "those",
        "a",
        "an",
    }

    # Extract words, lowercase, filter by length and stopwords
    words = re.findall(r"\b\w+\b", text.lower())
    keywords = [w for w in words if len(w) >= min_length and w not in stopwords]

    return list(set(keywords))  # Unique keywords


def score_categories(
    categories: List[str], person_name: str, event_keywords: List[str]
) -> float:
    """
    Score category relevance (0-5 points).

    Uses Wikimedia Commons categories to assess relevance.
    """
    if not categories:
        return 0.0

    score = 0.0
    categories_lower = [c.lower() for c in categories]

    # Person name in categories
    person_name_parts = person_name.lower().split()
    for part in person_name_parts:
        if len(part) >= 3:  # Skip very short name parts
            if any(part in cat for cat in categories_lower):
                score += 2.0
                break

    # Event keywords in categories
    for keyword in event_keywords[:10]:  # Check first 10 keywords
        if any(keyword in cat for cat in categories_lower):
            score += 1.0
            break

    # Penalty for modern/generic categories
    penalty_categories = [
        "modern",
        "statue",
        "monument",
        "memorial",
        "plaque",
        "street",
        "postage",
        "stamp",
    ]
    for penalty in penalty_categories:
        if any(penalty in cat for cat in categories_lower):
            score -= 2.0
            break

    return max(0.0, min(score, 5.0))  # Clamp to 0-5


def score_filename(filename: str) -> float:
    """
    Score filename informativeness (0-5 points).

    Penalizes auto-generated names, rewards descriptive names.
    """
    if not filename:
        return 3.0  # Neutral

    score = 3.0  # Start neutral
    filename_lower = filename.lower()

    # Penalize generic/auto-generated names
    if re.match(r"^[a-f0-9]{32}", filename_lower):  # MD5 hash
        score -= 2.0
    elif re.match(r"^\d{8}_\d{6}", filename_lower):  # Timestamp only
        score -= 2.0
    elif re.match(r"^img_\d+|dsc_\d+|image\d+", filename_lower):
        score -= 1.0

    # Reward descriptive names (multiple words)
    word_count = (
        len(filename.split("_")) + len(filename.split()) + len(filename.split("-"))
    )
    if word_count >= 5:
        score += 2.0

    # Penalize likely screenshots/crops
    if "screenshot" in filename_lower or "crop" in filename_lower:
        score -= 2.0

    return max(0.0, min(score, 5.0))  # Clamp to 0-5


def calculate_image_quality_score(
    image_metadata: Dict[str, Any],
    person_name: str = "",
    event_date: str = "",
    event_text: str = "",
) -> float:
    """
    Calculate overall image quality score (0-45 points).

    Combines multiple quality metrics:
    - Resolution (0-10)
    - File efficiency (0-5)
    - Filename quality (0-5)
    - Temporal relevance (0-10, if event data provided)
    - Category relevance (0-5, if event data provided)
    - Hard filters (aspect ratio, file size, MIME type)

    Returns score (higher is better), or -1 if image fails hard filters.
    """
    width = image_metadata.get("width", 0)
    height = image_metadata.get("height", 0)
    file_size = image_metadata.get("size", 0)
    mime_type = image_metadata.get("mime", "")

    # Hard filters (permissive thresholds based on user preference)
    MIN_WIDTH = 400
    MIN_HEIGHT = 300
    MIN_PIXELS = 120_000  # 400×300 minimum
    MIN_ASPECT_RATIO = 0.3
    MAX_ASPECT_RATIO = 3.0
    MIN_FILE_SIZE = 10_000  # 10 KB
    MAX_FILE_SIZE = 50_000_000  # 50 MB

    # Check hard filters
    if width < MIN_WIDTH or height < MIN_HEIGHT:
        return -1.0  # Too small

    if width * height < MIN_PIXELS:
        return -1.0  # Too few pixels

    aspect_ratio = width / height if height > 0 else 0
    if aspect_ratio < MIN_ASPECT_RATIO or aspect_ratio > MAX_ASPECT_RATIO:
        return -1.0  # Extreme aspect ratio

    if file_size < MIN_FILE_SIZE or file_size > MAX_FILE_SIZE:
        return -1.0  # File size out of range

    # Strongly prefer JPEG/PNG, but don't reject others (permissive)
    if mime_type == "image/svg+xml":
        return -1.0  # SVGs are usually logos/diagrams

    # Calculate quality scores
    score = 0.0
    score += score_resolution(width, height)
    score += score_file_efficiency(file_size, width, height)
    score += score_filename(image_metadata.get("filename", ""))

    # Add event-specific scores if provided
    if event_date or event_text:
        score += score_temporal_relevance(
            event_date,
            image_metadata.get("dateTimeOriginal", ""),
            image_metadata.get("dateTimeUpload", ""),
        )

        if person_name and event_text:
            event_keywords = extract_keywords_from_text(event_text)
            score += score_categories(
                image_metadata.get("categories", []), person_name, event_keywords
            )

    return score


def filter_images_by_quality(
    images: List[Dict[str, Any]],
    person_name: str = "",
    event_date: str = "",
    event_text: str = "",
    min_score: float = 10.0,
) -> List[Dict[str, Any]]:
    """
    Filter images by quality score, keeping only those above threshold.

    Args:
        images: List of image metadata dicts
        person_name: Person's name for category matching
        event_date: Event date for temporal relevance
        event_text: Event title + description for keyword extraction
        min_score: Minimum quality score (default: 10.0 out of 45)

    Returns:
        Filtered list of images with quality scores attached.
    """
    filtered = []

    for img in images:
        score = calculate_image_quality_score(
            img, person_name=person_name, event_date=event_date, event_text=event_text
        )

        if score >= min_score:
            # Attach score to image metadata for debugging/logging
            img["quality_score"] = score
            filtered.append(img)

    # Sort by quality score (descending)
    filtered.sort(key=lambda x: x.get("quality_score", 0), reverse=True)

    return filtered


def search_wikimedia_commons(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Search Wikimedia Commons using MediaWiki API.

    Returns list of image metadata dicts with url, caption, source, filename,
    and quality metrics (width, height, size, mime, dates, categories).
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
        "iiprop": "url|size|mime|extmetadata",
        "iiurlwidth": 800,
        "cllimit": 50,  # Get up to 50 categories per image
    }

    try:
        response = requests.get(
            api_url, params=params, timeout=30, headers=wikipedia_headers()
        )
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"    Commons API error for '{query}': {e}")
        return []

    pages = data.get("query", {}).get("pages", {})
    images = []

    for page_id, page_data in pages.items():
        image_info = page_data.get("imageinfo", [{}])[0]

        # For SVGs, prefer thumburl (PNG render) over url (raw SVG)
        # thumburl is provided when iiurlwidth is set
        url = image_info.get("thumburl") or image_info.get("url")

        if not url:
            continue

        # Extract filename from page title
        filename = page_data.get("title", "").replace("File:", "")

        # Extract quality metrics
        width = image_info.get("width", 0)
        height = image_info.get("height", 0)
        file_size = image_info.get("size", 0)
        mime_type = image_info.get("mime", "")

        # Extract caption and attribution from metadata
        extmetadata = image_info.get("extmetadata", {})
        caption = (
            extmetadata.get("ImageDescription", {}).get("value", "")
            or extmetadata.get("ObjectName", {}).get("value", "")
            or filename
        )
        caption = _strip_html_tags(caption)

        # Extract creator (artist)
        creator_raw = extmetadata.get("Artist", {}).get("value", "")
        creator = _strip_html_tags(creator_raw) if creator_raw else None

        # Extract license info
        license_name = extmetadata.get("LicenseShortName", {}).get("value", "")
        license_url = extmetadata.get("LicenseUrl", {}).get("value", "")

        # Extract temporal metadata
        date_time_original = extmetadata.get("DateTimeOriginal", {}).get("value", "")
        date_time_upload = extmetadata.get("DateTime", {}).get("value", "")

        # Extract categories
        categories_raw = page_data.get("categories", [])
        categories = [
            cat.get("title", "").replace("Category:", "") for cat in categories_raw
        ]

        # Build source URL
        source = f"https://commons.wikimedia.org/wiki/{page_data.get('title', '').replace(' ', '_')}"

        images.append(
            {
                "url": url,
                "filename": filename,
                "caption": caption,
                "source": source,
                "creator": creator,
                "license": license_name if license_name else None,
                "licenseUrl": license_url if license_url else None,
                # Quality metrics
                "width": width,
                "height": height,
                "size": file_size,
                "mime": mime_type,
                "dateTimeOriginal": date_time_original,
                "dateTimeUpload": date_time_upload,
                "categories": categories,
            }
        )

    return images


def search_openverse(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Search Openverse API for CC-licensed images.

    Openverse aggregates images from Flickr, Wikimedia, museums, and other sources.
    Returns list of image metadata dicts with url, caption, source, filename.
    """
    api_url = "https://api.openverse.org/v1/images/"

    params = {
        "q": query,
        "page_size": limit,
        # Filter for licenses that allow reuse
        "license_type": "commercial,modification",
    }

    headers = {"User-Agent": "life-ds-project/1.0 (biographical timeline generator)"}

    try:
        response = requests.get(api_url, params=params, timeout=30, headers=headers)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"    Openverse API error for '{query}': {e}")
        return []

    results = data.get("results", [])
    images = []

    for item in results:
        url = item.get("url")
        if not url:
            continue

        # Extract filename from URL or title
        title = item.get("title", "")
        filename = title or url.split("/")[-1]

        # Use title as caption, fall back to attribution
        caption = title or item.get("attribution", filename)

        # Source is the foreign landing URL (original page)
        source = item.get("foreign_landing_url", url)

        # Add provider info to help with deduplication
        provider = item.get("provider", "openverse")

        # Extract creator and license info
        creator = item.get("creator")
        license_code = item.get("license", "")
        license_version = item.get("license_version", "")
        license_url = item.get("license_url", "")

        # Format license name (e.g., "by-sa" + "3.0" -> "CC BY-SA 3.0")
        license_name = None
        if license_code:
            license_name = f"CC {license_code.upper()}"
            if license_version:
                license_name += f" {license_version}"

        images.append(
            {
                "url": url,
                "filename": filename,
                "caption": caption,
                "source": source,
                "provider": provider,
                "creator": creator,
                "license": license_name,
                "licenseUrl": license_url if license_url else None,
            }
        )

    return images


def generate_image_search_strings(
    event_skeletons: List[EventSkeleton],
    person_name: str,
    model: str = PHASE3_IMAGE_SEARCH_MODEL,
) -> List[str]:
    """
    Use AI to generate 20 optimized search strings for finding images
    across all events at once.
    """
    # Build prompt with all events
    prompt = f"PERSON: {person_name}\n\n"
    prompt += "LIFE EVENTS:\n"
    prompt += "=" * 60 + "\n\n"

    for idx, skeleton in enumerate(event_skeletons):
        prompt += f"Event {idx}: {skeleton.title} ({skeleton.date})\n"
        prompt += f"  Description: {skeleton.description[:200]}...\n\n"

    prompt += "=" * 60 + "\n"
    prompt += "TASK: Generate exactly 20 search strings for Wikimedia Commons\n"
    prompt += "=" * 60 + "\n\n"

    prompt += "CRITICAL: Wikimedia Commons uses SIMPLE keyword matching, not semantic search.\n"
    prompt += "Your search strings must be SHORT and SIMPLE (2-4 words max).\n\n"

    prompt += "SEARCH STRING RULES:\n"
    prompt += "  • Use 2-4 words MAXIMUM per search string\n"
    prompt += "  • At least 5 searches should include the person's name\n"
    prompt += (
        "  • Focus on: building names, artwork names, award names, institution names\n"
    )
    prompt += "  • ALWAYS combine the person's name with generic terms (city names, professions, etc.)\n"
    prompt += "  • NO standalone city names, countries, or professions without the person's name\n"
    prompt += "  • NO adjectives, NO years, NO descriptive phrases\n"
    prompt += "  • NO long phrases like 'exterior view of' or 'night view'\n\n"

    prompt += "GOOD EXAMPLES (2-4 words):\n"
    prompt += "  • 'Zaha Hadid'\n"
    prompt += "  • 'Vitra Fire Station'\n"
    prompt += "  • 'MAXXI Rome'\n"
    prompt += "  • 'Heydar Aliyev Center'\n"
    prompt += "  • 'Pritzker Prize'\n"
    prompt += "  • 'Zaha Hadid architecture'\n"
    prompt += "  • 'London Aquatics Centre'\n"
    prompt += "  • 'Béla Bartók portrait' (person + generic term)\n"
    prompt += "  • 'Bartók Budapest' (person + city)\n\n"

    prompt += "BAD EXAMPLES (too generic or too long):\n"
    prompt += "  • 'Budapest' ❌ (too generic - use 'Bartók Budapest' instead)\n"
    prompt += "  • 'composer' ❌ (too generic - use 'Bartók composer' instead)\n"
    prompt += "  • 'Hungary' ❌ (too generic - use 'Bartók Hungary' instead)\n"
    prompt += "  • 'Vitra Fire Station Weil am Rhein exterior 1993 Zaha Hadid' ❌ (too long)\n"
    prompt += "  • 'Deconstructivist Architecture exhibition 1988 MoMA New York' ❌ (too long)\n"
    prompt += "  • 'ancient Sumerian city ruins Iraq Ur archaeological site' ❌ (too long)\n\n"

    prompt += "CRITICAL RULE: Never search for standalone generic terms (cities, countries, professions).\n"
    prompt += (
        "Always anchor generic terms to the person's name or specific named entities.\n"
    )

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        # Fallback: generate basic search strings
        return [f"{person_name}", f"{person_name} portrait"]

    client = OpenAI(api_key=api_key)

    try:
        response = client.responses.parse(
            model=model,
            reasoning=cast(Any, {"effort": PHASE3_IMAGE_SEARCH_REASONING}),
            input=[
                {
                    "role": "system",
                    "content": "You are an expert at crafting search queries for Wikimedia Commons to find historically relevant images for biographical timelines.",
                },
                {"role": "user", "content": prompt},
            ],
            text_format=ImageSearchStrings,
        )

        if response.status == "completed" and response.output_parsed:
            return response.output_parsed.search_strings[:20]

    except Exception as e:
        print(f"    Warning: Search string generation failed: {e}")

    # Fallback
    return [person_name]


def execute_batch_image_search(
    search_strings: List[str], images_per_query: int = 10
) -> List[Dict[str, Any]]:
    """
    Execute all search queries against Wikimedia Commons and Openverse.

    Returns deduplicated list of image candidates with metadata.
    """
    all_images = []
    seen_urls: Set[str] = set()

    # Search Wikimedia Commons
    print("    [Source 1/2] Wikimedia Commons:")
    for query in search_strings:
        safe_query = query.encode("ascii", "replace").decode("ascii")
        print(f"      Searching: '{safe_query}'")

        try:
            results = search_wikimedia_commons(query, limit=images_per_query)
            for img in results:
                if img["url"] not in seen_urls:
                    seen_urls.add(img["url"])
                    img["provider"] = "wikimedia"
                    all_images.append(img)
        except Exception as e:
            print(f"        Warning: Search failed: {e}")

    commons_count = len(all_images)
    print(f"      Found {commons_count} unique images from Commons")

    # Search Openverse (aggregates Flickr, museums, etc.)
    print("    [Source 2/2] Openverse (Flickr, museums, etc.):")
    for query in search_strings:
        safe_query = query.encode("ascii", "replace").decode("ascii")
        print(f"      Searching: '{safe_query}'")

        try:
            results = search_openverse(query, limit=images_per_query)
            for img in results:
                if img["url"] not in seen_urls:
                    seen_urls.add(img["url"])
                    all_images.append(img)
        except Exception as e:
            print(f"        Warning: Search failed: {e}")

    openverse_count = len(all_images) - commons_count
    print(f"      Found {openverse_count} unique images from Openverse")

    print(f"    Total unique images found: {len(all_images)}")
    return all_images


def match_images_to_events(
    candidate_images: List[Dict[str, Any]],
    event_skeletons: List[EventSkeleton],
    person_name: str,
    model: str = PHASE3_IMAGE_MATCH_MODEL,
) -> Tuple[Dict[int, Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Use AI to match images to events based on caption and filename.
    Also selects the best portrait image for the person.

    Returns:
        Tuple of (event_assignments dict, portrait dict or None)
    """
    if not candidate_images:
        return {}, None

    # Build prompt
    prompt = f"PERSON: {person_name}\n\n"

    prompt += "LIFE EVENTS:\n"
    prompt += "=" * 60 + "\n"
    for idx, skeleton in enumerate(event_skeletons):
        prompt += f"[Event {idx}] {skeleton.title} ({skeleton.date})\n"
        prompt += f"    {skeleton.description[:150]}...\n\n"

    prompt += "\n" + "=" * 60 + "\n"
    prompt += "AVAILABLE IMAGES:\n"
    prompt += "=" * 60 + "\n\n"

    for idx, img in enumerate(candidate_images, 1):
        prompt += f"[Image {idx}]\n"
        prompt += f"  Filename: {img['filename']}\n"
        prompt += f"  Caption: {img['caption'][:200]}\n\n"

    prompt += "=" * 60 + "\n"
    prompt += "TASK: Select portrait AND assign images to events\n"
    prompt += "=" * 60 + "\n\n"

    prompt += "TWO TASKS:\n"
    prompt += "1. Select the BEST PORTRAIT image for this person's profile\n"
    prompt += "2. Match other images to specific life events\n\n"

    prompt += "PORTRAIT SELECTION:\n"
    prompt += "  • Choose ONE image that depicts this person visually\n"
    prompt += "  • ACCEPTABLE: photographs, paintings OF the person, drawings OF the person, sculptures/statues OF the person\n"
    prompt += "  • Prefer: clear depictions of the face, well-known portraits, professional photos\n"
    prompt += "  • For PRE-PHOTOGRAPHY historical figures: period paintings, sculptures, tomb effigies, coins, seals, medieval manuscripts are acceptable\n"
    prompt += "  • ACCEPTABLE: Statues and sculptures that clearly depict the person's likeness (bust, full statue)\n"
    prompt += "  • NEVER SELECT: buildings, plaques, street signs, memorial plaques without a face/likeness\n"
    prompt += "  • NEVER SELECT: artworks CREATED BY the person (we want depictions OF them, not BY them)\n"
    prompt += "  • NEVER SELECT: costume illustrations from books like 'Costumes of All Nations', 'Trachten der Völker', or similar costume/fashion reference books - these are GENERIC costume drawings, NOT actual portraits\n"
    prompt += "  • NEVER SELECT: modern imaginative recreations where no historical likeness exists (speculative illustrations)\n"
    prompt += "  • If no actual depiction of the person exists, set portrait to null\n"
    prompt += "  • The portrait image will NOT be used for any event\n\n"

    prompt += "EVENT IMAGE MATCHING:\n"

    prompt += "ASSIGNMENT RULES:\n"
    prompt += "  • Each image can be assigned to AT MOST one event\n"
    prompt += "  • Each event can have AT MOST one image\n"
    prompt += "  • Only assign if the image DIRECTLY relates to that specific event\n"
    prompt += "  • Leave events without images if no good match exists\n"
    prompt += "  • Aim for 40-60% of events to have images\n\n"

    prompt += "GOOD MATCHES:\n"
    prompt += "  • Document/publication image → event about publishing that work\n"
    prompt += "  • Building photo → event that took place at that building\n"
    prompt += "  • Machine/device → event about inventing or working with it\n"
    prompt += "  • Memorial/plaque → later events or death (NOT birth/early events)\n"
    prompt += "  • Historical photo from specific year → event from that year\n\n"

    prompt += "AVOID:\n"
    prompt += "  • Generic portraits for any event\n"
    prompt += "  • Modern commemorations for historical events\n"
    prompt += (
        "  • Loosely related images (e.g., city photo for event that happened there)\n"
    )
    prompt += "  • Assigning same type of image (e.g., plaques) to multiple events\n\n"

    prompt += "CAPTION GUIDELINES:\n"
    prompt += "  • IMPORTANT: You CANNOT see the images - only filenames and metadata\n"
    prompt += (
        "  • Base captions ONLY on what the filename/metadata explicitly tells you\n"
    )
    prompt += "  • Do NOT assume or describe visual details you cannot verify\n"
    prompt += "  • Keep captions factual and minimal (5-12 words)\n"
    prompt += "  • Use the original source caption/title if it's descriptive enough\n"
    prompt += "  • For buildings/places: just name the place, don't describe what you can't see\n"
    prompt += "  • Good: 'Bletchley Park, wartime codebreaking headquarters'\n"
    prompt += "  • Good: 'The Olympiastadion Munich roof structure'\n"
    prompt += "  • Bad: 'Aerial view showing the curved tensile membrane' (you can't see this)\n"

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {}, None

    client = OpenAI(api_key=api_key)

    try:
        response = client.responses.parse(
            model=model,
            reasoning=cast(Any, {"effort": PHASE3_IMAGE_MATCH_REASONING}),
            input=[
                {
                    "role": "system",
                    "content": (
                        "You are a meticulous image curator for biographical timelines. "
                        "Match images to life events only when there is a clear, direct connection. "
                        "Quality over quantity - it's better to leave events without images than to make poor matches."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            text_format=ImageAssignmentResult,
        )

        if response.status != "completed" or not response.output_parsed:
            return {}, None

        result = response.output_parsed

        # Extract portrait selection
        portrait_image: Optional[Dict[str, Any]] = None
        portrait_img_idx: Optional[int] = None
        if result.portrait and result.portrait.image_id is not None:
            portrait_img_idx = result.portrait.image_id - 1  # Convert to 0-based
            if 0 <= portrait_img_idx < len(candidate_images):
                portrait_image = candidate_images[portrait_img_idx].copy()
                # Use original source caption for portrait (already in the image dict)
                # The 'caption' field from search results contains the title/description

        # Build mapping, validating indices
        assignments: Dict[int, Dict[str, Any]] = {}
        used_images: Set[int] = set()

        # Mark portrait as used so it won't be assigned to events
        if portrait_img_idx is not None:
            used_images.add(portrait_img_idx)

        for assignment in result.assignments:
            img_idx = assignment.image_id - 1  # Convert to 0-based
            event_idx = assignment.event_index

            # Validate indices
            if img_idx < 0 or img_idx >= len(candidate_images):
                continue
            if event_idx < 0 or event_idx >= len(event_skeletons):
                continue

            # Check if image already used (including portrait)
            if img_idx in used_images:
                continue

            # Check if event already has image
            if event_idx in assignments:
                continue

            used_images.add(img_idx)
            # Store the image with AI-generated caption
            img_with_caption = candidate_images[img_idx].copy()
            img_with_caption["caption"] = assignment.caption
            assignments[event_idx] = img_with_caption

        return assignments, portrait_image

    except Exception as e:
        print(f"    Warning: Image matching failed: {e}")
        return {}, None


# ============================================================================
# PHASE 1: EVENT SKELETON GENERATION
# ============================================================================


def build_phase1_prompt(
    page_data: Dict[str, Any],
    summary_data: Dict[str, Any],
    subject: str,
    related_articles: Optional[List[Dict[str, Any]]] = None,
    deutsche_biographie_text: Optional[str] = None,
) -> str:
    """
    Build Phase 1 prompt for generating event skeletons and chapters.

    Focus on identifying significant life events and organizing them into chapters.
    NO location/image/source details (Phase 2 will research these).
    """
    summary_text = summary_data.get("extract", "").strip()
    extract_text = page_data.get("extract", "").strip()

    main_article_title = page_data.get("title", subject)

    combined = f"TARGET SUBJECT: {main_article_title}\n"
    combined += "=" * 60 + "\n"
    combined += f"You are creating a biographical timeline for {main_article_title}.\n"
    combined += f"Focus ONLY on events from {main_article_title}'s life.\n"
    combined += "=" * 60 + "\n\n"
    combined += f"MAIN ARTICLE\nPage title: {main_article_title}\nPage URL: {page_data.get('fullurl', '')}\n\n"

    if summary_text:
        combined += f"Summary snippet:\n{summary_text}\n\n"

    if extract_text:
        truncated = extract_text[:12000]
        combined += (
            f"Full extract (truncated to 12k characters if needed):\n{truncated}\n"
        )

    # Include Deutsche Biographie data if available
    if deutsche_biographie_text:
        combined += f"\n\n{deutsche_biographie_text}\n"

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


_BIRTH_WORDS = re.compile(r"\b(born|birth|birthplace)\b", re.IGNORECASE)
_DEATH_WORDS = re.compile(
    r"\b(died|dies|death|dying|killed|executed|assassinated|passed away)\b",
    re.IGNORECASE,
)


def _event_field(event: Any, name: str) -> Any:
    """Read a field from an event that may be a model or a plain dict."""
    if isinstance(event, dict):
        return event.get(name)
    return getattr(event, name, None)


def _event_class_type(event: Any) -> Optional[str]:
    """The classification type of an event, whether model or plain dict."""
    event_class = _event_field(event, "event_class")
    if event_class is None:
        return None
    if isinstance(event_class, dict):
        value = event_class.get("type")
    else:
        value = getattr(event_class, "type", None)
    return value if isinstance(value, str) else None


def find_birth_event_index(
    events: List[Any], birth_date: Optional[str] = None
) -> Optional[int]:
    """
    Index of the event that tells the subject's own birth, or None.

    The date decides first: the event must be dated at age 0 (or on the
    person's birth date) *and* open the story or read as a birth. That is what
    keeps a child's or sibling's birth out — those events carry the subject's
    own age, never zero — and it is why the date is asked before the model's
    own classification, which is only consulted when no event is dated there.

    Works on Phase 1 skeletons, merged events, and the plain dicts a stored
    ``life_events.json`` holds.
    """
    birth_day = (birth_date or "").strip()[:10]

    for index, event in enumerate(events):
        age = _event_field(event, "age")
        date = str(_event_field(event, "date") or "")
        dated_at_birth = (age == 0) or (bool(birth_day) and date[:10] == birth_day)
        if not dated_at_birth:
            continue
        text = f"{_event_field(event, 'title') or ''} {_event_field(event, 'description') or ''}"
        if index == 0 or _BIRTH_WORDS.search(text):
            return index

    for index, event in enumerate(events):
        if _event_class_type(event) == "birth":
            return index

    return None


def find_death_event_index(
    events: List[Any], death_date: Optional[str] = None
) -> Optional[int]:
    """
    Index of the event that tells the subject's own death, or None.

    The date decides first, as it does for the birth, but a death is not always
    dated on the day it happened: a duel or a tram accident opens the event days
    earlier. So an event dated on the death date qualifies, and so does the last
    event of the story when it falls in the death year and says someone died.
    Requiring the story's end is what keeps a spouse's or a child's death out.

    The search runs backwards, because a death closes a story the way a birth
    opens one: a plot with three events on the day Stauffenberg died ends with
    the execution, not with the bomb he planted that morning.

    With no death date on record — a life the sources leave open — only a
    closing event whose *title* names a death qualifies. The model's own
    classification is consulted last.

    Works on Phase 1 skeletons, merged events, and the plain dicts a stored
    ``life_events.json`` holds.
    """
    death_day = (death_date or "").strip()[:10]
    last = len(events) - 1

    for index in range(last, -1, -1):
        event = events[index]
        date = str(_event_field(event, "date") or "")
        title = str(_event_field(event, "title") or "")
        text = f"{title} {_event_field(event, 'description') or ''}"
        if death_day:
            dated_at_death = date[:10] == death_day or (
                date[:4] == death_day[:4] and index == last
            )
            if dated_at_death and (index == last or _DEATH_WORDS.search(text)):
                return index
        elif index == last and _DEATH_WORDS.search(title):
            return index

    for index, event in enumerate(events):
        if _event_class_type(event) == "death":
            return index

    return None


def _apply_single_classification(
    events: List[Any],
    index: Optional[int],
    class_type: str,
    build: Callable[[], Any],
) -> None:
    """
    Make exactly the event at ``index`` carry ``class_type``, in place.

    The classification is what the story slide styles, so one the model forgot
    silently costs the reader what the slide would have shown, and one the model
    put on a child's birth or a spouse's death styles the wrong slide. Both are
    repaired here rather than left to the prompt.
    """
    for position, event in enumerate(events):
        classified = _event_class_type(event) == class_type
        if position == index and not classified:
            event.event_class = build()
        elif classified and position != index:
            event.event_class = None


def ensure_birth_classification(
    event_skeletons: List[EventSkeleton], birth_date: Optional[str] = None
) -> Optional[int]:
    """
    Guarantee that at most one event — the subject's own birth — is classified
    as a birth, editing the skeletons in place and returning its index.
    """
    index = find_birth_event_index(event_skeletons, birth_date)
    _apply_single_classification(event_skeletons, index, "birth", BirthClassification)
    return index


def ensure_death_classification(
    event_skeletons: List[EventSkeleton], death_date: Optional[str] = None
) -> Optional[int]:
    """
    Guarantee that at most one event — the subject's own death — is classified
    as a death, editing the skeletons in place and returning its index.
    """
    index = find_death_event_index(event_skeletons, death_date)
    _apply_single_classification(event_skeletons, index, "death", DeathClassification)
    return index


def _validate_chronological_order(event_skeletons: List[EventSkeleton]) -> None:
    """
    Validate that events are in strict chronological order.

    Raises RuntimeError if events are not chronologically ordered.
    """
    # Validate chronological ordering
    for i in range(len(event_skeletons) - 1):
        current_event = event_skeletons[i]
        next_event = event_skeletons[i + 1]

        # Compare dates
        current_date = current_event.date
        next_date = next_event.date

        if current_date > next_date:
            raise RuntimeError(
                f"Events are not in chronological order: "
                f"'{current_event.title}' ({current_date}) comes after "
                f"'{next_event.title}' ({next_date})"
            )

    print(f"  ✓ Chronological order validated ({len(event_skeletons)} events)")


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
        "Write event descriptions that are chronologically accurate, factually focused, "
        "and balance professional achievements with personal human context. "
        "Use ISO-8601 dates, include date_precision as 'day', 'month', or 'year'. "
        "The precision is a claim of its own: use 'day' only when the sources state "
        "the day, 'month' only when they state the month, and fall back to 'year' "
        "otherwise. An honest 1814-07 is better than a wrong 1814-07-02. "
        "The year in an event's description must be the year the event is dated to; "
        "when the sources put the event in a different year than you first assumed, "
        "move the date, do not leave the disagreement in the prose. "
        "All output must be in American English only, regardless of source language."
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
        "\n\nABSOLUTE PROHIBITION: DO NOT create any section, category, or grouping labeled 'Other Events' or similar. "
        "ALL events must be equally important and presented in strict chronological order without any 'miscellaneous' category. "
        "Every event is a main biographical event - there are no 'other' or secondary events. "
        "\n\nIMPORTANT - Event Skeleton Guidelines:\n"
        "- Keep event titles crisp and concise (2-6 words)\n"
        "- Use active, specific language that captures the essence of the event\n"
        "- Avoid generic titles like 'Major Achievement' or 'Important Work'\n"
        "- Examples: 'Birth in London', 'Graduated from Oxford', 'Published First Novel', 'Appointed Prime Minister'\n"
        "- Write rich descriptions (2-4 sentences) that mention context, people involved, and places\n"
        "- DO NOT specify exact locations, images, or detailed sources (Phase 2 will research these)\n"
        "- DO mention places, people, and context in the description naturally\n"
        "- DO NOT add annotations - Phase 2 will handle all annotations\n"
        "\n\nWEIGHT - how much of the life the event turns on:\n"
        "- Give every event a weight from 0.0 to 1.0\n"
        "- Judge it against the OTHER EVENTS OF THIS LIFE, not against history at large: "
        "the most consequential thing this person did is near 1.0 even if the world barely noticed, "
        "and a minor episode is near 0.1 even if it happened somewhere famous\n"
        "- 0.9-1.0: the events the life is remembered for; without them the story is not this person's\n"
        "- 0.6-0.8: turning points — the work, the appointment, the loss that changed the direction\n"
        "- 0.3-0.5: substantial but not pivotal; a post taken, a degree earned, a move made\n"
        "- 0.1-0.2: context and texture — real events that a short telling would leave out\n"
        "- SPREAD THEM OUT. Do not give everything 0.7. A life has a few peaks and many "
        "foothills, and a flat set of weights is the same as no weights at all\n"
        "- Weigh what the event MEANT, not how well documented it is: a quiet decision that "
        "redirected the work outranks a well-attended ceremony that changed nothing\n"
        "\n\nCRITICAL TEMPORAL RULE - Stay in the Moment:\n"
        "- Descriptions must be chronologically confined - describe ONLY what was happening at that time\n"
        "- NEVER reference future events, outcomes, or career retrospectives\n"
        "- FORBIDDEN phrases: 'later he would...', 'this would lead to...', 'in keeping with his future...', 'by the end of his life...'\n"
        "- Write from the perspective of the event itself, not from biographical hindsight\n"
        "- GOOD: 'Schönlein studied medicine in Landshut, learning from Andreas Röschlaub and Friedrich Tiedemann.'\n"
        "- BAD: 'Schönlein studied medicine in Landshut, training that would later shape his bedside teaching method.'\n"
        "\n\nTone and Style Guidelines:\n"
        "- Write as NARRATIVE BIOGRAPHY, not as meta-commentary about biography\n"
        "- Events should flow together to tell a life story, but each event stays focused on itself\n"
        "- FORBIDDEN meta-references: 'the biography records...', 'sources mention...', 'this helps explain why he later...'\n"
        "- FORBIDDEN analytical framing: 'the period mattered less for...', 'these years are significant because...'\n"
        "- Present events as lived experiences, not as literary analysis\n"
        "- Show the story unfolding, don't explain the story's structure\n"
        "- GOOD: 'He completed his dissertation on brain development under Döllinger, exploring comparative embryology in mammals.'\n"
        "- BAD: 'The period mattered less for any single exam than for the intellectual tensions it exposed him to.'\n"
        "- GOOD: 'He studied medicine in Landshut and Würzburg, learning anatomy from Döllinger and clinical methods from Walther.'\n"
        "- BAD: 'Among the teachers named in his biography are Andreas Röschlaub, Friedrich Tiedemann, and...'\n"
        "\n\nPersonal and Human Context:\n"
        "- Balance professional achievements with personal life, relationships, and human experiences\n"
        "- Include family, friendships, emotional impacts, life circumstances where relevant\n"
        "- Don't make EVERY event about career milestones and professional accomplishments\n"
        "- Consider: What was their personal life like? Who were they close to? What challenges did they face?\n"
        "- Professional events can still mention human context (e.g., who supported them, personal motivations)\n"
        "\n\nConciseness Requirements:\n"
        "- Target 2-4 sentences, but make each sentence DIRECT and ECONOMICAL\n"
        "- Avoid verbose constructions, unnecessary clauses, and abstract philosophical framing\n"
        "- Prefer active voice and concrete details over interpretive summaries\n"
        "- Cut any sentence that doesn't add factual information about the event\n"
        "- GOOD: 'He studied in Landshut and Würzburg, learning from anatomists and clinicians.'\n"
        "- BAD: 'This mix of theoretical ambition and concrete anatomical instruction helps explain why he later insisted...'\n"
        "\n\nDEATH EVENT SPECIAL RULE:\n"
        "- Death descriptions must be FACTUAL ONLY: date, location, age, immediate circumstances, cause if known\n"
        "- DO NOT include legacy analysis, historical impact, or career summaries in the death event\n"
        "- Save ALL interpretive retrospectives for the separate 'conclusion' field\n"
        "- The conclusion field exists specifically for legacy - keep death factual\n"
        "- GOOD: 'Schönlein died in Bamberg on 23 January 1864 after years of declining health.'\n"
        "- BAD: 'His death closed a career that helped reshape German clinical training... The most durable part of his legacy was...'\n"
        "\n\nCONCLUSION FIELD (1-2 sentences):\n"
        "- This is WHERE legacy, impact, and retrospective analysis belong\n"
        "- Event descriptions = factual, chronological, in-the-moment\n"
        "- Conclusion = interpretive, retrospective, legacy-focused\n"
        "- The conclusion summarizes the person's life significance AFTER all events are told\n"
        "\n\nEVENT CLASSIFICATION (optional):\n"
        f"For each event skeleton, determine if it matches one of these {len(EVENT_CLASS_CONFIG)} specific biographical event types:\n"
        + "".join(
            [
                f"  {i+1}. {config['name']} - {config['description']}\n"
                for i, config in enumerate(EVENT_CLASS_CONFIG.values())
            ]
        )
        + "\n"
        "Detection guidelines:\n"
        + "".join(
            [config["phase1_guidance"] + "\n" for config in EVENT_CLASS_CONFIG.values()]
        )
        + "For other events (education, appointments, awards): OMIT classification.\n"
        f"Only classify when event CLEARLY matches one of the {len(EVENT_CLASS_CONFIG)} types above.\n"
        "\n\nEach event skeleton must provide: date (start of the event), date_precision, optional date_end/date_end_precision "
        "when the event spans a range, optional date_note for uncertainty, age (null if not applicable), "
        "title, and description. "
        "\nInclude person metadata with name, birth_date, death_date when known, primary_roles, tagline, summary, "
        "wikipedia URL, and portrait info if available.\n"
        "\nPRIMARY_ROLES GUIDELINES (CRITICAL):\n"
        "- Provide exactly 2-3 roles, never more\n"
        "- Use SHORT, GENERIC, LOWERCASE role names (1-2 words max)\n"
        "- Roles must be comparable across different people (standard profession/role names)\n"
        "- GOOD examples: 'mathematician', 'physicist', 'writer', 'composer', 'architect', 'monarch', 'inventor', 'computer scientist', 'philosopher', 'entrepreneur'\n"
        "- BAD examples: 'Founder of Apple Inc' (too specific), 'King of Germany' (use 'monarch'), 'theoretical biologist' (too niche, use 'biologist'), 'Computer pioneer' (use 'computer scientist')\n"
        "- For royalty/rulers: use 'monarch', 'emperor', or 'ruler' - not specific titles\n"
        "- Avoid adjectives and qualifiers: 'scientist' not 'renowned scientist'\n"
        "\nThe tagline should be a catchy, memorable phrase (3-7 words) that captures the person's essence or most notable contribution. "
        "Examples: 'Father of Computer Science', 'The First Programmer', 'Architect of Relativity', 'Pioneer of Structured Programming'."
    )

    try:
        response = client.responses.parse(
            model=model,
            reasoning=cast(Any, {"effort": PHASE1_REASONING_EFFORT}),
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
            # error.response is an httpx.Response, which has no .get(); the body
            # has to be parsed first. Any failure here (non-JSON body, unexpected
            # shape) just means falling back to the exception's own text.
            message = error.response.json().get("error", {}).get("message", "")
        except Exception:
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
        raise RuntimeError(
            f"Phase 1: Response has unexpected status: {response.status}"
        )

    parsed = response.output_parsed
    if parsed is None:
        raise RuntimeError("Failed to parse structured output from model (Phase 1)")

    # Ensure events are sorted chronologically (defensive programming)
    parsed.event_skeletons.sort(key=lambda e: e.date)

    # The birth opens a story and the death closes it, so both are detected
    # rather than hoped for
    birth_index = ensure_birth_classification(
        parsed.event_skeletons, parsed.person.birth_date
    )
    if birth_index is None:
        print("  Phase 1: No birth event found in the plan")
    death_index = ensure_death_classification(
        parsed.event_skeletons, parsed.person.death_date
    )
    if death_index is None:
        print("  Phase 1: No death event found in the plan")

    # Log classifications from Phase 1 (using centralized config)
    classified_count = sum(
        1 for skeleton in parsed.event_skeletons if skeleton.event_class
    )
    if classified_count > 0:
        print(
            f"  Phase 1: Classified {classified_count}/{len(parsed.event_skeletons)} events"
        )
        for skeleton in parsed.event_skeletons:
            if skeleton.event_class:
                class_type = skeleton.event_class.type
                if class_type in EVENT_CLASS_CONFIG:
                    log_format = EVENT_CLASS_CONFIG[class_type]["log_format"]
                    print(f"    - {skeleton.title}: {log_format(skeleton.event_class)}")
                else:
                    # Fallback for unknown types
                    print(f"    - {skeleton.title}: {class_type.upper()}")

    # Validate chronological ordering
    _validate_chronological_order(parsed.event_skeletons)

    return parsed


# ============================================================================
# PHASE 2: EVENT DETAIL RESEARCH
# ============================================================================


def filter_related_articles_for_event(
    event_skeleton: EventSkeleton,
    all_related_articles: List[Dict[str, Any]],
    max_articles: int = 5,
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
    event_words = set(re.findall(r"\b\w{4,}\b", event_text))  # Words 4+ chars

    scored_articles = []
    for article in all_related_articles:
        title = article.get("title", "").lower()
        summary = article.get("summary", "").lower()

        title_words = set(re.findall(r"\b\w{4,}\b", title))
        summary_words = set(re.findall(r"\b\w{4,}\b", summary))

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


# How much of each related article Phase 2 is shown. It used to be 1000, which
# is a lead paragraph — enough to place a term, not enough to say what changed
# because of an event. The background passage is written from this material, so
# it is the budget that decides whether that passage can carry a detail the
# description does not already have.
RELATED_ARTICLE_CHARS = 2500


def build_phase2_prompt_base(
    event_skeleton: EventSkeleton,
    person_name: str,
    filtered_related_articles: List[Dict[str, Any]],
    deutsche_biographie_text: Optional[str] = None,
) -> str:
    """
    Build base Phase 2 prompt (common sections for all event types).

    Used for standard events (no classification) and as foundation for class-specific prompts.
    Focus on specific details for THIS event only (NO images - Phase 3).
    """
    prompt = "Research details for this specific event:\n\n"
    prompt += f"Title: {event_skeleton.title}\n"
    prompt += f"Date: {event_skeleton.date}\n"
    prompt += f"Description: {event_skeleton.description}\n"
    prompt += f"Subject: {person_name}\n"

    # Add event class info if present
    if event_skeleton.event_class:
        class_type = event_skeleton.event_class.type
        prompt += f"Event Class: {class_type}\n"

    prompt += "\n" + "=" * 60 + "\n"
    prompt += "TASK: Provide the following details for THIS specific event:\n"
    prompt += "=" * 60 + "\n\n"

    prompt += "0. DESCRIPTION (with annotation markers):\n"
    prompt += "   - Return the event description with [[term|display]] markers inserted for any annotations\n"
    prompt += "   - If you create annotations (section 5 below), you MUST insert the markers into this description\n"
    prompt += "   - If no annotations, return the original description text unchanged\n"
    prompt += "   - Example: If annotating 'Leopoldstadt', change 'Leopoldstadt district' to '[[Leopoldstadt|Leopoldstadt district]]'\n"
    prompt += "   \n"
    # Build dynamic list of classification types
    class_types_str = "/".join(
        [config["display_name"].lower() for config in EVENT_CLASS_CONFIG.values()]
    )
    prompt += f"   - CRITICAL ANTI-REDUNDANCY RULE for CLASSIFIED events ({class_types_str}):\n"
    prompt += "     * If this event has a classification (see Event Class above), DO NOT describe technical details\n"
    prompt += "     * The classification already provides structured metadata - keep description narrative only\n"
    prompt += "     * Focus ONLY on narrative context: where, when, why, with whom\n"
    prompt += "     * Good (classified event): 'In his parents' Berlin apartment, Zuse built the Z1 using scavenged materials.'\n"
    prompt += "     * Bad (classified event): 'Zuse built the Z1, an electrically driven mechanical binary calculating machine...'\n"
    prompt += "   \n"
    prompt += "   - DESCRIPTION QUALITY CHECKLIST (when refining descriptions):\n"
    prompt += (
        "     * ✓ Temporal: No forward references, stays in the chronological moment\n"
    )
    prompt += "     * ✓ Tone: Event-focused narrative, not meta-commentary or interpretive analysis\n"
    prompt += "     * ✓ Personal: Includes human context where relevant, not purely professional\n"
    prompt += "     * ✓ Concise: Direct sentences, no verbose philosophical framing\n"
    prompt += "     * ✓ Death events: Factual only if this is a death event (save legacy for conclusion)\n"
    prompt += "     * If Phase 1 description violates these rules, refine it to fix the issues\n"
    prompt += "     * Refinements should make descriptions BETTER (more concise, more balanced), not longer\n\n"

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
    prompt += (
        "   - For single-location events, provide one location with primary=true\n\n"
    )

    prompt += "2. INVOLVED_PEOPLE:\n"
    prompt += "   - List people DIRECTLY involved in THIS specific event\n"
    prompt += f"   - EXCLUDE the main subject ({person_name})\n"
    prompt += (
        "   - Examples: collaborators, opponents, witnesses, family members present\n"
    )
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
    prompt += (
        "   - ⚠️ UNIQUENESS RULE: Each term can be annotated AT MOST ONCE per event\n"
    )
    prompt += "   - ⚠️ If a term appears multiple times in the description, only annotate the FIRST occurrence\n"
    prompt += "   \n"
    prompt += "   ⛔ CRITICAL PROHIBITION FOR CLASSIFIED EVENTS:\n"
    prompt += "   - If this event has a classification (see Event Class above), DO NOT annotate the classification subject\n"
    prompt += "   - Examples of FORBIDDEN annotations for classified events:\n"
    prompt += "     * ❌ Don't annotate 'Z1', 'Z3' for invention events - classification provides technical details\n"
    prompt += "     * ❌ Don't annotate partner's name for marriage events - use INVOLVED_PEOPLE instead\n"
    prompt += "     * ❌ Don't annotate destination country for migration events - classification provides locations\n"
    prompt += "   - The classification provides all necessary details - annotations would be redundant\n"
    prompt += "   \n"
    prompt += "   - Annotate ONLY:\n"
    prompt += "     * Highly technical/specialized concepts (e.g., 'Entscheidungsproblem', 'Difference Engine', 'Analytical Engine', 'transautomatism')\n"
    prompt += "     * Historical inventions/machines requiring explanation (e.g., 'Difference Engine' - mechanical calculator, 'Jacquard loom' - programmable weaving machine)\n"
    prompt += "     * Obscure institutions with significant historical context (e.g., 'Bletchley Park' - secret codebreaking facility)\n"
    prompt += "     * Specialized movements/events requiring context (e.g., 'Anschluss' - Nazi annexation, 'documenta' - contemporary art exhibition)\n"
    prompt += "     * Regional/cultural terms unknown outside specific areas (e.g., 'Matura' - Austrian graduation exam, 'soirée' - French social gathering)\n"
    prompt += "   - ABSOLUTE PROHIBITIONS (NEVER annotate):\n"
    prompt += "     * ❌ NEVER ANNOTATE PERSON NAMES - Person names belong in INVOLVED_PEOPLE field (section 2), NOT in annotations\n"
    prompt += "     * ❌ This includes: full names, first names, last names, titles (e.g., '8th Baron King'), nicknames, or any reference to a human being\n"
    prompt += "     * ❌ Examples of FORBIDDEN person annotations: 'William', 'William King', '8th Baron King', 'King William', 'Ada', 'Lord Byron', etc.\n"
    prompt += f"     * ❌ NEVER ANNOTATE CLASSIFIED SUBJECTS - If classifying this event ({class_types_str}), DO NOT annotate the subject\n"
    prompt += "     * ❌ Examples: Don't annotate 'Z3', 'S1 and S2' if you're creating an invention classification for them\n"
    prompt += "     * ❌ The classification provides full details - annotations would be redundant\n"
    prompt += "     * ANY major cities - these are well-known and need no explanation (Tokyo, Hamburg, Paris, Prague, London, Vienna, Berlin, Munich, New York, Rome, etc.)\n"
    prompt += (
        "     * ANY countries or continents (Japan, Germany, USA, Europe, Asia, etc.)\n"
    )
    prompt += "     * ANY common places (university, school, museum, gallery, studio, farmhouse, etc.)\n"
    prompt += "     * ANY well-known historical periods or events (WWII, Renaissance, Cold War, etc.)\n"
    prompt += "     * ANY basic artistic/cultural terms (exhibition, retrospective, painting, prize, award, etc.)\n"
    prompt += "     * ANY geographic features everyone knows (rivers, seas, mountains, islands, etc.)\n"
    prompt += "   - CRITICAL REDUNDANCY CHECK - Read the FULL event description before annotating:\n"
    prompt += "     * ❌ NEVER annotate if the description already provides the same or similar information\n"
    prompt += (
        "     * ❌ NEVER annotate if the surrounding context makes the term clear\n"
    )
    prompt += "     * ❌ BAD: Annotating 'Architectural Association School of Architecture' as 'prestigious architecture school' when description says 'hotbed of avant-garde experimentation' - context already explains it\n"
    prompt += "     * ❌ BAD: Annotating 'Kaufungen' as 'royal estate' when description says 'royal estate of Kaufungen'\n"
    prompt += "     * ❌ BAD: Annotating 'Hitler Youth' if description says 'Nazi youth organization'\n"
    prompt += "     * ❌ BAD: Annotating 'Montessori' if description says 'child-centered education'\n"
    prompt += "     * ✓ GOOD: Annotating 'Leopoldstadt' if description only says 'district' without historical context\n"
    prompt += "   - STRICT VALUE TEST: Annotation must add SUBSTANTIAL NEW information the description completely lacks\n"
    prompt += "   - If the description provides adequate context (even implicitly), DO NOT annotate - no matter how obscure the term is\n"
    prompt += "   - When in doubt about redundancy, SKIP the annotation\n"
    prompt += "   - GEOGRAPHY RULE: Only annotate very specific/obscure places with crucial historical significance\n"
    prompt += "     * GOOD: 'Leopoldstadt' (specific district with Holocaust context that's not obvious from name)\n"
    prompt += "     * GOOD: 'Bletchley Park' (specific historic site with special significance)\n"
    prompt += "     * BAD: 'Prague' (major European city everyone knows)\n"
    prompt += "     * BAD: 'Hamburg' (major German city everyone knows)\n"
    prompt += "     * BAD: 'Japan' (country everyone knows)\n"
    prompt += "     * BAD: 'Normandy' (well-known French region)\n"
    prompt += "   - EXAMPLES of GOOD annotations:\n"
    prompt += "     * 'Difference Engine' - Babbage's mechanical calculator (historical invention requiring context)\n"
    prompt += "     * 'Entscheidungsproblem' - mathematical concept requiring technical explanation\n"
    prompt += "     * 'soirée' - French evening social gathering (cultural term)\n"
    prompt += "     * 'Matura' - Austrian-specific term not used elsewhere\n"
    prompt += "     * 'documenta' - specific art event most people don't know\n"
    prompt += "   - EXAMPLES of BAD annotations (NEVER annotate):\n"
    prompt += "     * ❌ 'William' - person name (use INVOLVED_PEOPLE instead)\n"
    prompt += (
        "     * ❌ '8th Baron King' - person title (use INVOLVED_PEOPLE instead)\n"
    )
    prompt += "     * ❌ 'Lord Byron' - person name (use INVOLVED_PEOPLE instead)\n"
    prompt += "     * ❌ ANY other person name or title\n"
    prompt += "     * ❌ 'Architectural Association School of Architecture' - REDUNDANT if description says 'hotbed of avant-garde experimentation' (context is clear)\n"
    prompt += "     * ❌ 'Kaufungen' - REDUNDANT if description already says 'royal estate of Kaufungen'\n"
    prompt += "     * ❌ ANY term already explained or made clear by surrounding context (redundancy)\n"
    prompt += "     * 'Prague' - major European city (well-known)\n"
    prompt += "     * 'Hamburg' - major city (well-known)\n"
    prompt += "     * 'Japan' - country (well-known)\n"
    prompt += "     * 'Paris' - major city (well-known)\n"
    prompt += "     * 'exhibition' - common term\n"
    prompt += "     * 'university' - common term\n"
    prompt += "   - ANNOTATION LENGTH RULE: Annotate ONLY the minimal technical term, not entire phrases\n"
    prompt += "     * ✓ GOOD: [[general relativity|general theory of relativity]]\n"
    prompt += "     * ❌ BAD: [[Einstein presents the final form of the field equations of the general theory of relativity|Einstein presents...]]\n"
    prompt += "     * Keep annotations SHORT - typically 1-4 words maximum\n"
    prompt += "     * Annotate the NOUN PHRASE that needs explanation, not the entire sentence\n"
    prompt += "   - Mark terms using [[term|display_text]] syntax\n"
    prompt += (
        "   - Explanations must ADD information not in description (no redundancy)\n"
    )
    prompt += "   - Optional: Include wikipedia_url for further reading\n"
    prompt += "   - DEFAULT to 0 annotations - when in doubt, DO NOT annotate\n\n"

    # The slide already carries the event. This is the one part of the run
    # asked to write rather than to extract, and every rule here exists to keep
    # it from restating what the reader has just read: the description is given
    # as the thing to go beyond, and the questions name what the reader cannot
    # get from it.
    prompt += "6. BACKGROUND (a short passage, prose):\n"
    prompt += "   - Write 3-5 sentences of background a curious reader would want AFTER reading the description above\n"
    prompt += "   - This is prose for a reader, not notes: complete sentences, no bullets, no headings, no lists\n"
    prompt += "   - Answer as many of these as the sources support, in whatever order reads best:\n"
    prompt += "     * What was going on around this event - the institution, the field, the political or personal situation it sat in\n"
    prompt += "     * Why it mattered at the time, and to whom\n"
    prompt += "     * What it led to, or what changed because of it\n"
    prompt += "     * What is surprising, contested, or easily misunderstood about it\n"
    prompt += "   - HARD RULE - ADD, NEVER RESTATE:\n"
    prompt += "     * The reader has just read the description. Repeating any of it is a failure\n"
    prompt += "     * Do not re-tell what happened, who was there, when, or where - all of that is already on the page\n"
    prompt += "     * Do not define the annotated terms from section 5; their explanations are shown separately\n"
    prompt += "     * Every sentence must carry a fact, a consequence, or a tension the description does not\n"
    prompt += "   - GROUNDING: use only the subject's article, the related articles below, and well-established\n"
    prompt += "     history. Do not speculate, do not invent numbers, names, or dates. Prefer the concrete\n"
    prompt += "     (what a place held, what a method changed, how long something took) over the evaluative\n"
    prompt += "   - Do NOT use [[term|display]] markers here - they belong in the description only\n"
    prompt += "   - Write for someone who does not know the field. Name what an insider would assume\n"
    prompt += "   - American English. No headings, no bullet points, no meta-commentary about sources\n"
    prompt += "   - Return null if the material would only repeat the description or would have to be invented\n\n"

    # Add icon categories
    prompt += "\n" + "=" * 60 + "\n"
    prompt += "AVAILABLE ICONS:\n"
    prompt += "=" * 60 + "\n"
    prompt += format_icon_categories_for_prompt()
    prompt += "\n"

    # Add Deutsche Biographie context if available
    if deutsche_biographie_text:
        prompt += "\n" + deutsche_biographie_text + "\n"

    # Add filtered related articles
    if filtered_related_articles and len(filtered_related_articles) > 0:
        prompt += "\n" + "=" * 60 + "\n"
        prompt += f"RELATED ARTICLES (filtered for this event, top {len(filtered_related_articles)}):\n"
        prompt += "=" * 60 + "\n\n"
        for idx, article in enumerate(filtered_related_articles, 1):
            prompt += f"\nARTICLE {idx}: {article.get('title', 'Unknown')}\n"
            prompt += f"URL: {article.get('url', '')}\n"
            prompt += "-" * 60 + "\n"

            full_text = article.get("fullText", "")
            if full_text:
                truncated = full_text[:RELATED_ARTICLE_CHARS]
                prompt += f"{truncated}...\n\n"
            else:
                summary = article.get("summary", "")
                if summary:
                    prompt += f"{summary}\n\n"

    return prompt


def _add_related_articles_section(
    filtered_related_articles: List[Dict[str, Any]],
) -> str:
    """Helper to add related articles section to Phase 2 prompts."""
    if not filtered_related_articles:
        return ""

    prompt = "\n" + "=" * 60 + "\n"
    prompt += f"RELATED ARTICLES (filtered for this event, top {len(filtered_related_articles)}):\n"
    prompt += "=" * 60 + "\n\n"

    for idx, article in enumerate(filtered_related_articles, 1):
        prompt += f"\nARTICLE {idx}: {article.get('title', 'Unknown')}\n"
        prompt += f"URL: {article.get('url', '')}\n"
        prompt += "-" * 60 + "\n"

        full_text = article.get("fullText", "")
        if full_text:
            truncated = full_text[:RELATED_ARTICLE_CHARS]
            prompt += f"{truncated}...\n\n"
        else:
            summary = article.get("summary", "")
            if summary:
                prompt += f"{summary}\n\n"

    return prompt


def build_phase2_prompt_classified(
    event_skeleton: EventSkeleton,
    person_name: str,
    filtered_related_articles: List[Dict[str, Any]],
    deutsche_biographie_text: Optional[str] = None,
) -> str:
    """
    Generic Phase 2 prompt builder for classified events.
    Uses EVENT_CLASS_CONFIG to generate event-class-specific guidance.
    """
    # Get base prompt (sections 0-5) — DB text included via base
    base = build_phase2_prompt_base(
        event_skeleton,
        person_name,
        [],
        deutsche_biographie_text=deutsche_biographie_text,
    )

    # event_class is None for standard events. The only caller checks before
    # routing here, so this is belt-and-braces — but an unclassified event has
    # the same answer as an unrecognised class, so let it take that same path.
    class_type = event_skeleton.event_class.type if event_skeleton.event_class else None
    if class_type not in EVENT_CLASS_CONFIG:
        # Fallback to base prompt if config not found
        return base + _add_related_articles_section(filtered_related_articles)

    config = EVENT_CLASS_CONFIG[class_type]

    # Build class-specific guidance section
    prompt = base + f"\n\n{config['display_name']} EVENT SPECIFIC GUIDANCE:\n"
    prompt += "=" * 60 + "\n"
    prompt += f"This event has been classified as {config['name']} in Phase 1.\n"

    # List what the classification already contains
    fields_list = ", ".join(config["fields"].keys())
    prompt += f"The classification already contains: {fields_list}.\n\n"

    prompt += "Your Phase 2 research should focus on:\n"
    for focus_item in config["phase2_focus"]:
        prompt += f"{focus_item}\n"
    prompt += "\n"

    return prompt + _add_related_articles_section(filtered_related_articles)


def research_event_details(
    event_skeleton: EventSkeleton,
    person_name: str,
    all_related_articles: List[Dict[str, Any]],
    model: str = PHASE2_MODEL,
    retry_count: int = 2,
    deutsche_biographie_text: Optional[str] = None,
) -> EventDetails:
    """
    Research details for a single event with retry logic.
    Uses event-class-specific prompts for targeted research.

    Returns:
        EventDetails with locations, involved_people, sources, icon (NO images - Phase 3)
    """
    # Filter articles
    filtered_articles = filter_related_articles_for_event(
        event_skeleton, all_related_articles, max_articles=5
    )

    # Route to event-class-specific prompt builder (using centralized config)
    if event_skeleton.event_class:
        # All classified events use the generic builder with config
        prompt = build_phase2_prompt_classified(
            event_skeleton,
            person_name,
            filtered_articles,
            deutsche_biographie_text=deutsche_biographie_text,
        )
    else:
        # Standard event (no classification)
        prompt = build_phase2_prompt_base(
            event_skeleton,
            person_name,
            filtered_articles,
            deutsche_biographie_text=deutsche_biographie_text,
        )

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY environment variable is not set.")

    system = (
        "You are a research assistant specializing in biographical event details. "
        "Provide specific, factual information for the given event. "
        "Ensure descriptions are chronologically confined, concise, and balanced. "
        "All output must be in American English only. Be precise with locations and people. "
        "One field, the background, is written prose rather than extracted data: "
        "it is read by someone who has just read the event and wants to know what "
        "surrounded it, so it must add to the description rather than restate it."
    )

    details = parse_structured(
        OpenAI(api_key=api_key),
        model=model,
        reasoning_effort=PHASE2_REASONING_EFFORT,
        input=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        text_format=EventDetails,
        label=f"Phase 2 research of '{event_skeleton.title}'",
        attempts=retry_count + 1,
    )
    if details is not None:
        return details

    # The event keeps its place in the story with nothing researched about it:
    # no place, nobody involved, no sources, and the neutral icon. Said plainly
    # here because the record itself cannot say it — the story renders a
    # degraded event exactly like a thin one.
    safe_title = event_skeleton.title.encode("ascii", "replace").decode("ascii")
    print(f"    [!] Event not researched, keeping it unresolved: {safe_title}")
    return EventDetails(
        locations=None, involved_people=None, sources=[], event_type_icon="mdi-calendar"
    )


def research_all_event_details(
    event_skeletons: List[EventSkeleton],
    person_name: str,
    all_related_articles: List[Dict[str, Any]],
    model: str = PHASE2_MODEL,
    deutsche_biographie_text: Optional[str] = None,
) -> List[EventDetails]:
    """Research details for all events sequentially (NO images - Phase 3)."""
    # Log classification routing info
    classified_count = sum(1 for skeleton in event_skeletons if skeleton.event_class)
    print(
        f"  Phase 2: Using class-specific prompts for {classified_count}/{len(event_skeletons)} classified events"
    )

    details = []
    for idx, skeleton in enumerate(event_skeletons, 1):
        safe_title = skeleton.title.encode("ascii", "replace").decode("ascii")

        # Show which prompt type is being used
        prompt_type = "STANDARD"
        if skeleton.event_class:
            prompt_type = skeleton.event_class.type.upper()

        print(
            f"  [{idx}/{len(event_skeletons)}] Researching: {safe_title} [{prompt_type}]"
        )

        detail = research_event_details(
            skeleton,
            person_name,
            all_related_articles,
            model,
            deutsche_biographie_text=deutsche_biographie_text,
        )
        details.append(detail)

    return details


# ============================================================================
# EVENT MERGING
# ============================================================================


def merge_event_skeleton_and_details(
    skeleton: EventSkeleton, details: EventDetails
) -> LifeEvent:
    """Merge Phase 1 skeleton with Phase 2 details (NO images - Phase 3)."""

    # Build locations array from EventDetails.locations
    locations = []
    if details.locations and len(details.locations) > 0:
        for loc in details.locations:
            locations.append(
                {
                    "name_historic": loc.name_historic,
                    "name_modern": loc.name_modern,
                    "centroid": loc.centroid,
                    "primary": loc.primary,
                }
            )

    # Annotations come ONLY from Phase 2 (Phase 1 doesn't generate them)
    annotations = details.annotations

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
        # The model invents icon names that render nothing, so resolve whatever
        # it returned to an icon that exists before it reaches disk.
        event_type_icon=normalize_icon(details.event_type_icon),
        chapter=None,  # Chapter assigned in Chapter generation phase
        annotations=annotations,
        background=details.background,
        weight=skeleton.weight,  # From Phase 1, which sees the whole life
        event_class=skeleton.event_class,  # From Phase 1, not Phase 2
    )


def merge_all_events(
    skeletons: List[EventSkeleton], details_list: List[EventDetails]
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
            locations_str = ", ".join(
                [
                    loc.get("name_modern") or loc.get("name_historic", "Unknown")
                    for loc in event.locations
                ]
            )
            prompt += f"  Locations: {locations_str}\n"

        if event.involved_people:
            prompt += f"  Involved people: {', '.join(event.involved_people)}\n"

        prompt += "\n"

    prompt += f"{'='*60}\n"
    prompt += f"Total: {len(merged_events)} events\n"

    return prompt


def call_openai_chapter_generation(
    prompt: str, model: str, retry_count: int = 2
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
        "You are a skilled biographer crafting a compelling narrative from life events. "
        "Your task is to organize events into engaging chapters that read like a well-told story. "
        "Write with energy and insight, making each chapter feel like part of a coherent journey. "
        "All output must be in American English only."
    )

    instructions = (
        "Based on the established life events provided, create 3-6 compelling life chapters that tell this person's story.\n\n"
        "CHAPTER REQUIREMENTS:\n"
        "- Each chapter represents a distinct phase with a UNIFIED THEME or focus (e.g., education, war service, exile, creative peak, final years)\n"
        "- ABSOLUTE PROHIBITION: NO chapter headline may contain 'Other', 'Miscellaneous', 'Additional', or 'Various' - these are generic categorizations, not meaningful life phases\n"
        "- Every chapter must be equally important with a specific, concrete theme - there are no 'other' or secondary chapters\n"
        "- Chapters must be chronologically ordered and non-overlapping\n"
        "- Events within a chapter should feel related - avoid mixing disparate life phases (e.g., don't combine education + early career + major achievement)\n"
        "- Aim for 3-6 chapters total - too few lacks nuance, too many fragments the story\n"
        "- The first chapter should start with or before the first event\n"
        "- The last chapter should end with or after the last event\n"
        "- Every event must belong to exactly one chapter based on its date\n"
        "- Chapters should flow into each other, creating narrative momentum\n"
        "- If a life phase spans many years with different themes, consider splitting into multiple chapters\n\n"
        "CHAPTER STRUCTURE:\n"
        "- id: Unique identifier (lowercase, snake_case)\n"
        "- headline: CATCHY, story-like chapter title (2-5 words, VARY THE LENGTH). Each headline should express ONE unified concept or theme - NOT a list. "
        "Think like a book chapter - vivid, evocative, intriguing. AVOID 'and', commas, or other punctuation that creates lists. "
        "Be specific and focused on a single idea.\n"
        "  GOOD examples: 'Breaking the Code' (3), 'Exile in Paris' (3), 'The Vienna Circle' (3), 'Rise to Power' (3), "
        "'Final Reckoning' (2), 'A Mind Divided' (3), 'Into the Unknown' (3), 'Wartime Service' (2), "
        "'Building the Future' (3), 'Years of Struggle' (3), 'The Last Battle' (3), 'New Beginnings' (2).\n"
        "  BAD examples: 'Adoption, Valley Spark' (comma creates list), 'Return, Reinvention, Last Act' (multiple concepts), "
        "'Dropout, Zen Fire' (comma splits concepts), 'Early Life and Education' ('and' creates list).\n"
        "- date_start, date_start_precision: When this chapter begins\n"
        "- date_end, date_end_precision: When this chapter ends\n"
        "- age_start, age_end: Subject's age at chapter start/end (null if not applicable)\n"
        "- involved_people: Aggregate the key people mentioned across all events in this chapter "
        "(exclude the main subject, include only significant individuals). "
        "IMPORTANT: Use each person's most canonical name form ONLY ONCE - avoid duplicates or name variations "
        "(e.g., use 'Anna Lloyd Jones' not both 'Anna Lloyd Jones' and 'Anna Lloyd Jones Wright')\n"
        "- location: A summary of the main geographic area for this chapter - NOT a list of cities, but a regional summary. "
        "For example: 'England' (not 'London, Cambridge, Manchester'), 'United States' (not 'Princeton, New York, Boston'), "
        "'Central Europe' (not 'Vienna, Prague, Budapest'). Use the broadest appropriate region.\n\n"
        "CONCLUSION:\n"
        "- After all chapters, provide a crisp, powerful conclusion statement (1-2 sentences)\n"
        "- Capture the person's legacy, lasting impact, or the essence of their life journey\n"
        "- Make it memorable and meaningful - this is the final word on their story\n\n"
        "STORYTELLING GUIDELINES:\n"
        "- Headlines should intrigue and invite the reader in - ONE clear concept, NO lists or comma-separated phrases\n"
        "- VARY headline length (mix 2-word, 3-word, 4-word, and 5-word titles) to create rhythm and avoid monotony\n"
        "- Each chapter should have thematic coherence - events should share a common thread or life phase\n"
        "- Connect chapters so they flow as a continuous story, with each building on the previous\n"
        "- Use vivid, concrete language over abstract generalities\n"
        "- The conclusion should resonate and leave a lasting impression\n\n"
        "Craft chapters that feel like distinct, meaningful phases of this person's journey - not arbitrary date ranges."
    )

    chapters = parse_structured(
        client,
        model=model,
        reasoning_effort=CHAPTER_REASONING_EFFORT,
        input=[
            {"role": "system", "content": system},
            {"role": "user", "content": instructions},
            {"role": "user", "content": prompt},
        ],
        text_format=ChapterGenerationOutput,
        label="chapter generation",
        attempts=retry_count + 1,
    )
    if chapters is None:
        # Unlike a thin event, a story without chapters has no shape at all,
        # so this is the one Phase that fails the run rather than degrading.
        raise RuntimeError("Chapter generation failed")
    return chapters


def deduplicate_person_names(names: List[str]) -> List[str]:
    """
    Deduplicate person names by removing variations of the same person.

    Uses fuzzy matching to identify names that are likely the same person
    (e.g., "Anna Lloyd Jones" and "Anna Lloyd Jones Wright").
    Keeps the shorter, more canonical form.
    """
    if not names:
        return []

    # Normalize names for comparison
    def normalize(name: str) -> str:
        # Remove common suffixes, lowercase, strip whitespace
        normalized = name.lower().strip()
        # Remove parentheticals like "(Lady Byron)"
        normalized = re.sub(r"\s*\([^)]*\)\s*", " ", normalized)
        # Normalize whitespace
        normalized = " ".join(normalized.split())
        return normalized

    # Group similar names
    seen: Dict[str, str] = {}
    result: List[str] = []

    for name in names:
        norm = normalize(name)

        # Check if this is a variation of an existing name
        found_match = False
        for existing_norm, existing_name in seen.items():
            # If one is a substring of the other, they're likely the same person
            if norm in existing_norm or existing_norm in norm:
                # Keep the shorter (more canonical) name
                if len(norm) < len(existing_norm):
                    # Replace with shorter name
                    seen[norm] = name
                    result[result.index(existing_name)] = name
                found_match = True
                break

        if not found_match:
            seen[norm] = name
            result.append(name)

    return result


def assign_events_to_chapters(
    events: List[LifeEvent], chapters: List[LifeChapter]
) -> List[LifeEvent]:
    """
    Assign each event to the appropriate chapter based on date.

    Events are assigned to the chapter whose date range contains the event date.
    Uses normalized date comparison to handle different date precisions correctly
    (e.g., "1945-07" vs "1945-07-01").
    """
    # Sort chapters by normalized start date
    sorted_chapters = sorted(
        chapters,
        key=lambda c: normalize_date_for_comparison(c.date_start, to_end=False),
    )

    updated_events = []
    for event in events:
        # Normalize event date to start of period for comparison
        event_date_normalized = normalize_date_for_comparison(event.date, to_end=False)
        assigned_chapter = None

        # Find the chapter that contains this event's date
        for chapter in sorted_chapters:
            chapter_start = normalize_date_for_comparison(
                chapter.date_start, to_end=False
            )
            chapter_end = normalize_date_for_comparison(chapter.date_end, to_end=True)

            if chapter_start <= event_date_normalized <= chapter_end:
                assigned_chapter = chapter.id
                break

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
            event_class=event.event_class,  # CRITICAL: Preserve event classification
        )
        updated_events.append(updated_event)

    return updated_events


def _validate_chapter_headlines(chapters: List[LifeChapter]) -> None:
    """
    Validate that chapter headlines don't contain generic "Other" categorizations.

    Raises RuntimeError if any chapter headline contains prohibited terms.
    """
    import re

    # Patterns to detect generic "other" categorizations in chapter headlines
    # Note: We check for "other" as a chapter-starting word to catch patterns like
    # "Other Events", "Other Achievements", etc., while allowing "Mother of All Demos"
    prohibited_patterns = [
        r"^\s*other\s+",  # "other" at the start of the headline
        r"\bother\s+events?\b",  # "other event" or "other events"
        r"\bother\s+achievements?\b",  # "other achievement" or "other achievements"
        r"\bmiscellaneous\b",
        r"\badditional\s+events?\b",
        r"\bvarious\s+events?\b",
    ]

    for chapter in chapters:
        headline_lower = chapter.headline.lower()
        for pattern in prohibited_patterns:
            if re.search(pattern, headline_lower):
                raise RuntimeError(
                    f"Chapter headline contains prohibited categorization term: '{chapter.headline}'. "
                    f"All chapters must represent meaningful life phases, not generic 'other' or 'miscellaneous' groupings."
                )

    print(f"  ✓ Chapter headlines validated ({len(chapters)} chapters)")


def generate_chapters_for_events(
    merged_events: List[LifeEvent],
    person_name: str,
    birth_date: Optional[str],
    death_date: Optional[str],
    model: str,
) -> Tuple[List[LifeChapter], List[LifeEvent], str]:
    """
    Generate chapters for the established events and assign events to chapters.

    Returns:
        Tuple of (chapters, events_with_chapter_assignments, conclusion)
    """
    # Build prompt with all event information
    prompt = build_chapter_generation_prompt(
        merged_events, person_name, birth_date, death_date
    )

    # Call AI to generate chapters
    chapter_output = call_openai_chapter_generation(prompt, model)

    # Validate chapter headlines don't contain generic categorization terms
    _validate_chapter_headlines(chapter_output.chapters)

    # Deduplicate involved_people in chapters (remove name variations)
    deduplicated_chapters = []
    for chapter in chapter_output.chapters:
        if chapter.involved_people:
            deduplicated_people = deduplicate_person_names(chapter.involved_people)
            chapter = LifeChapter(
                id=chapter.id,
                headline=chapter.headline,
                date_start=chapter.date_start,
                date_start_precision=chapter.date_start_precision,
                date_end=chapter.date_end,
                date_end_precision=chapter.date_end_precision,
                age_start=chapter.age_start,
                age_end=chapter.age_end,
                involved_people=deduplicated_people,
                location=chapter.location,
            )
        deduplicated_chapters.append(chapter)

    # Assign events to chapters
    events_with_chapters = assign_events_to_chapters(
        merged_events, deduplicated_chapters
    )

    return deduplicated_chapters, events_with_chapters, chapter_output.conclusion


def research_images_for_all_events(
    merged_events: List[LifeEvent],
    event_skeletons: List[EventSkeleton],
    event_details_list: List[EventDetails],
    person_name: str,
) -> Tuple[List[LifeEvent], Optional[Dict[str, Any]]]:
    """
    Phase 3: Batch image discovery and AI-driven assignment.

    New approach:
    1. AI generates 20 optimized search strings for all events
    2. Execute all Commons searches and collect unique images
    3. AI selects portrait AND matches images to events
    4. Return events with assigned images and portrait

    Returns:
        Tuple of (enriched_events, portrait_dict or None)
    """
    print("  [Phase 3a] Generating image search strings...")
    search_strings = generate_image_search_strings(event_skeletons, person_name)
    print(f"    Generated {len(search_strings)} search strings")

    print("  [Phase 3b] Searching image sources (Commons + Openverse)...")
    candidate_images = execute_batch_image_search(search_strings, images_per_query=10)

    if not candidate_images:
        print("    No images found, skipping assignment")
        return merged_events, None

    print(f"    Found {len(candidate_images)} candidate images")

    # Quality pre-filtering (permissive - AI makes final decisions)
    print("  [Phase 3b+] Applying quality pre-filtering...")
    filtered_images = filter_images_by_quality(
        candidate_images,
        person_name=person_name,
        min_score=10.0,  # Permissive threshold (out of 45 possible)
    )

    if not filtered_images:
        print("    No images passed quality filters, skipping assignment")
        return merged_events, None

    filtered_count = len(candidate_images) - len(filtered_images)
    print(
        f"    Filtered out {filtered_count} low-quality images ({len(filtered_images)} remaining)"
    )

    # Show quality score distribution
    if filtered_images:
        scores = [img.get("quality_score", 0) for img in filtered_images]
        avg_score = sum(scores) / len(scores)
        max_score = max(scores)
        min_score = min(scores)
        print(
            f"    Quality scores: avg={avg_score:.1f}, range={min_score:.1f}-{max_score:.1f}"
        )

    print(
        f"  [Phase 3c] AI matching {len(filtered_images)} images to {len(event_skeletons)} events..."
    )
    assignments, portrait = match_images_to_events(
        filtered_images, event_skeletons, person_name
    )
    print(f"    Assigned images to {len(assignments)} events")
    if portrait:
        print("    ✓ Portrait selected")

    # Apply assignments to events
    enriched_events = []
    for idx, event in enumerate(merged_events):
        event_dict = event.model_dump()

        if idx in assignments:
            img = assignments[idx]
            event_dict["images"] = [
                {
                    "url": img["url"],
                    "caption": img["caption"],
                    "source": img["source"],
                    "creator": img.get("creator"),
                    "license": img.get("license"),
                    "licenseUrl": img.get("licenseUrl"),
                }
            ]
            safe_title = event.title.encode("ascii", "replace").decode("ascii")
            print(f"    ✓ Event {idx}: {safe_title}")
        else:
            event_dict.pop("images", None)

        enriched_events.append(LifeEvent(**event_dict))

    return enriched_events, portrait


# ============================================================================
# ENHANCED GEOCODING
# ============================================================================


def enrich_event_coordinates_v2(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Enhanced geocoding for unified location structure."""
    events = payload.get("events") or []
    enriched = []
    geocoded_count = 0
    unresolved: List[str] = []

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
                geocoded_locations.append(
                    {**loc, "centroid": [geocoded["lon"], geocoded["lat"]]}
                )
                geocoded_count += 1
            else:
                unresolved.append(name_to_geocode)
                geocoded_locations.append(loc)

        updated["locations"] = geocoded_locations
        enriched.append(updated)

    if unresolved:
        distinct = sorted(set(unresolved))
        print(
            f"  ⚠ {len(unresolved)} location(s) left without coordinates: "
            + ", ".join(distinct)
        )

    payload["events"] = enriched
    return payload, geocoded_count


# ============================================================================
# METADATA ENFORCEMENT (adapted from generate_person_dataset.py)
# ============================================================================


def _clean_all_strings(data: Any) -> Any:
    """
    Recursively fix control characters in all strings within a data structure.

    This ensures AI-generated text doesn't contain incorrect Unicode control
    characters that should be typographic punctuation.
    """
    if isinstance(data, dict):
        return {key: _clean_all_strings(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [_clean_all_strings(item) for item in data]
    elif isinstance(data, str):
        return _fix_control_characters(data)
    else:
        return data


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

    # Only set Wikipedia portrait if we don't already have a generated portrait
    # (generated portraits have image paths starting with /portraits/)
    existing_portrait = person.get("portrait", {})
    has_generated_portrait = (
        isinstance(existing_portrait, dict)
        and isinstance(existing_portrait.get("image"), str)
        and existing_portrait["image"].startswith("/portraits/")
    )

    if not has_generated_portrait:
        # No generated portrait - use Wikipedia page image if available
        original = page_data.get("original", {})
        if original:
            # Extract image URL from Wikipedia's pageimages API response
            image_url = original.get("source")
            if image_url:
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

            name_historic = (
                loc.get("name_historic", "").strip()
                if loc.get("name_historic")
                else None
            )
            name_modern = (
                loc.get("name_modern", "").strip() if loc.get("name_modern") else None
            )
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
                sanitized_locations.append(
                    {
                        "name_historic": name_historic,
                        "name_modern": name_modern,
                        "centroid": valid_centroid,
                        "primary": bool(loc.get("primary", False)),
                    }
                )

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
                            # Attribution is a license condition for the CC
                            # BY-SA material here, so it survives sanitizing.
                            "creator": image_data.get("creator") or None,
                            "license": image_data.get("license") or None,
                            "licenseUrl": image_data.get("licenseUrl") or None,
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
                    wikipedia_url = (
                        annotation.get("wikipedia_url", "").strip()
                        if annotation.get("wikipedia_url")
                        else None
                    )

                    # Only keep annotations with valid explanations
                    if explanation:
                        sanitized_annotations[term_key] = {"explanation": explanation}
                        if wikipedia_url and (
                            wikipedia_url.startswith("http://")
                            or wikipedia_url.startswith("https://")
                        ):
                            sanitized_annotations[term_key][
                                "wikipedia_url"
                            ] = wikipedia_url

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

    # Fix any control characters in all strings throughout the payload
    payload = _clean_all_strings(payload)

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
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return output_path


def pad_year(date: Optional[str]) -> Optional[str]:
    """Zero-pad a pre-1000 year so the date sorts and parses like every other.

    A bare ``973-05-06`` is not an ISO 8601 date: JavaScript's date parser
    rejects it, and a four-character slice of it reads ``973-``. The registry
    therefore stores ``0973-05-06``.
    """
    if not isinstance(date, str):
        return date
    match = re.match(r"^(-?)(\d{1,4})(\b.*)$", date.strip())
    if not match:
        return date
    sign, year, rest = match.groups()
    return f"{sign}{year.zfill(4)}{rest}"


def update_register(person_id: str, payload: Dict[str, Any], file_path: Path) -> None:
    """Update persons register."""
    person = payload.get("person", {})

    portrait = person.get("portrait")
    birth_date = pad_year(person.get("birth_date"))
    death_date = pad_year(person.get("death_date"))

    primary_roles = person.get("primary_roles", [])
    if isinstance(primary_roles, list):
        primary_roles = primary_roles[:3]

    current_timestamp = datetime.now().astimezone().isoformat()

    entry = {
        "id": person_id,
        "name": person.get("name", person_id.replace("_", " ").title()),
        "summary": person.get("summary"),
    }

    # Only include tagline if it's actually set (to preserve existing tagline when updating)
    tagline = person.get("tagline")
    if tagline is not None:
        entry["tagline"] = tagline

    # Explicitly set portrait (or None to remove it)
    entry["portrait"] = portrait
    if birth_date:
        entry["birthDate"] = birth_date
    if death_date:
        entry["deathDate"] = death_date
    if primary_roles:
        entry["primaryRoles"] = primary_roles

    register: Dict[str, Any] = {"people": []}
    if REGISTER_PATH.exists():
        register = json.loads(REGISTER_PATH.read_text(encoding="utf-8"))
    people = register.setdefault("people", [])

    for idx, existing in enumerate(people):
        if existing.get("id") == person_id:
            created_timestamp = existing.get("created", current_timestamp)
            updated_entry = {
                **existing,
                **entry,
                "created": created_timestamp,
                "lastUpdated": current_timestamp,
            }
            # Remove portrait key entirely if it's None
            if updated_entry.get("portrait") is None:
                updated_entry.pop("portrait", None)
            people[idx] = updated_entry
            break
    else:
        # Remove portrait key if None for new entries
        if entry.get("portrait") is None:
            entry.pop("portrait", None)
        entry["created"] = current_timestamp
        entry["lastUpdated"] = current_timestamp
        people.append(entry)

    people.sort(key=lambda item: item.get("name", ""))
    REGISTER_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTER_PATH.write_text(
        json.dumps(register, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


# ============================================================================
# MAIN ORCHESTRATION
# ============================================================================


def generate_person_events(
    subject: str,
    *,
    person_id: Optional[str] = None,
    update_registry: bool = True,
    model: str = DEFAULT_MODEL,
    use_cache: bool = True,
    use_deutsche_biographie: bool = True,
) -> Tuple[Path, str]:
    """
    Generate person life events dataset using two-phase approach.

    Args:
        subject: Person name or Wikipedia URL to research
        person_id: Optional person ID to use instead of auto-generating from article title
        update_registry: Whether to update persons.json registry
        model: OpenAI model to use
        use_cache: Whether to use cached Wikipedia materials
        use_deutsche_biographie: Whether to fetch/use Deutsche Biographie data

    Returns:
        Tuple of (file_path, person_id)
    """

    print(f"[Step 1/10] Fetching Wikipedia article for '{subject}'...")
    page_data = fetch_wikipedia_extract(subject)
    article_title = page_data.get("title", subject)
    print(f"[Step 1/10] Found article '{article_title}'")

    # Use provided person_id or generate from article title
    identifier = person_id or slugify(article_title)

    # Load cache (NO Commons images - fetched later in Phase 3)
    print(f"[Step 2/10] Loading cached materials for '{identifier}'...")
    related_articles = None
    summary_data = {}

    if use_cache:
        try:
            ensure_cache(identifier, article_title, person_name=article_title)
            cached_page = get_cached_wikipedia_page(
                identifier, article_title, use_cache=True
            )
            cached_summary = get_cached_wikipedia_summary(
                identifier, article_title, use_cache=True
            )

            # Load related articles if available
            cache_dir = get_cache_dir(identifier)
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
                    print("[Step 2/10] Using cached materials (no related articles)")
            else:
                print("[Step 2/10] Using cached materials (no related articles)")

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
        print(
            f"[Step 3/10] Fetching related articles (model: {model}, reasoning: {RELATED_ARTICLES_REASONING})..."
        )
        try:
            related_articles = fetch_related_articles(
                article_title,
                max_related=15,
                model=model,
                use_cache=use_cache,
                person_id=identifier,
            )
            print(f"[Step 3/10] Found {len(related_articles)} related articles")

            if related_articles and use_cache:
                cache_dir = get_cache_dir(identifier)
                related_path = cache_dir / "related_articles.json"
                cache_dir.mkdir(parents=True, exist_ok=True)
                related_path.write_text(
                    json.dumps(related_articles, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
                print(f"[Step 3/10] Cached {len(related_articles)} related articles")
        except Exception as e:
            print(f"[Step 3/10] Warning: Failed to fetch related articles ({e})")
            related_articles = []
    else:
        print(
            f"[Step 3/10] Using {len(related_articles) if related_articles else 0} related articles from cache"
        )

    # Load Deutsche Biographie data (best-effort)
    db_prompt_text = None
    if use_deutsche_biographie and ensure_deutsche_biographie_cache is not None:
        try:
            # Extract birth/death years from Wikipedia for disambiguation
            _db_birth_year = None
            _db_death_year = None
            _wiki_extract = page_data.get("extract", "")
            _year_match = re.search(
                r"\((\d{4})\s*[-–]\s*(\d{4})\)", _wiki_extract[:500]
            )
            if _year_match:
                _db_birth_year = int(_year_match.group(1))
                _db_death_year = int(_year_match.group(2))

            db_data = ensure_deutsche_biographie_cache(
                person_id=identifier,
                person_name=article_title,
                birth_year=_db_birth_year,
                death_year=_db_death_year,
            )
            if db_data and format_db_for_prompt is not None:
                db_prompt_text = format_db_for_prompt(db_data)
                if db_prompt_text:
                    print("[Step 3b/10] Deutsche Biographie data included in prompts")
        except Exception as e:
            print(f"[Step 3b/10] Warning: Deutsche Biographie fetch failed ({e})")
    elif not use_deutsche_biographie:
        print("[Step 3b/10] Deutsche Biographie skipped by request")

    # PHASE 1: Generate event skeletons
    print(
        f"[Step 4/12] PHASE 1: Generating event skeletons (model: {model}, reasoning: {PHASE1_REASONING_EFFORT})..."
    )
    phase1_prompt = build_phase1_prompt(
        page_data,
        summary_data,
        subject,
        related_articles,
        deutsche_biographie_text=db_prompt_text,
    )
    life_plan = call_openai_phase1(phase1_prompt, model)
    print(f"[Step 4/12] Generated {len(life_plan.event_skeletons)} event skeletons")

    # PHASE 2: Research event details (NO images - Phase 3)
    print(
        f"[Step 5/12] PHASE 2: Researching event details (model: {PHASE2_MODEL}, reasoning: {PHASE2_REASONING_EFFORT})..."
    )
    event_details_list = research_all_event_details(
        event_skeletons=life_plan.event_skeletons,
        person_name=life_plan.person.name,
        all_related_articles=related_articles or [],
        deutsche_biographie_text=db_prompt_text,
    )
    print(f"[Step 5/12] Researched details for {len(event_details_list)} events")

    # MERGE: Combine skeletons + details
    print("[Step 6/12] Merging event skeletons with details...")
    merged_events = merge_all_events(life_plan.event_skeletons, event_details_list)

    # CHAPTER GENERATION: Create chapters based on established events
    print(
        f"[Step 7/12] Generating life chapters (model: {model}, reasoning: {CHAPTER_REASONING_EFFORT})..."
    )
    chapters, events_with_chapters, conclusion = generate_chapters_for_events(
        merged_events=merged_events,
        person_name=life_plan.person.name,
        birth_date=life_plan.person.birth_date,
        death_date=life_plan.person.death_date,
        model=model,
    )
    print(f"[Step 7/12] Generated {len(chapters)} chapters with conclusion")

    # PHASE 3: Event-specific image discovery
    print(
        f"[Step 8/12] PHASE 3: Discovering and assigning event-specific images (model: {PHASE3_IMAGE_SEARCH_MODEL}, reasoning: {PHASE3_IMAGE_SEARCH_REASONING}/{PHASE3_IMAGE_MATCH_REASONING})..."
    )
    enriched_events, portrait = research_images_for_all_events(
        merged_events=events_with_chapters,
        event_skeletons=life_plan.event_skeletons,
        event_details_list=event_details_list,
        person_name=life_plan.person.name,
    )
    images_assigned = sum(1 for e in enriched_events if e.images)
    print(
        f"[Step 8/12] Assigned images to {images_assigned} / {len(enriched_events)} events"
    )

    # Build final payload
    person_data = life_plan.person.model_dump()

    # Check if there's already a generated portrait in the registry OR on disk
    existing_generated_portrait = None
    try:
        # First check registry
        if REGISTER_PATH.exists():
            registry = json.loads(REGISTER_PATH.read_text(encoding="utf-8"))
            people = registry.get("people", [])
            for person in people:
                if person.get("id") == identifier:
                    existing_portrait = person.get("portrait", {})
                    # Check if it's a generated portrait (local path starting with /portraits/)
                    if existing_portrait and isinstance(
                        existing_portrait.get("image"), str
                    ):
                        if existing_portrait["image"].startswith("/portraits/"):
                            existing_generated_portrait = existing_portrait
                            print(
                                f"  Found existing generated portrait in registry: {existing_portrait['image']}"
                            )
                    break

        # If not in registry, check if portrait files exist on disk
        if not existing_generated_portrait:
            portraits_dir = Path(__file__).resolve().parents[1] / "public" / "portraits"
            thumbnail_path = portraits_dir / f"{identifier}_thumbnail.webp"
            if thumbnail_path.exists():
                # Found generated portrait files - reconstruct portrait data
                existing_generated_portrait = {
                    "image": f"/portraits/{identifier}_thumbnail.webp",
                    "thumbnail": f"/portraits/{identifier}_thumbnail.webp",
                    "medium": f"/portraits/{identifier}_medium.webp",
                    "full": f"/portraits/{identifier}_full.webp",
                    "caption": "Stylized portrait based on historical photograph",
                    "creator": "AI generated artwork",
                }
                print(
                    f"  Found existing generated portrait files on disk: {thumbnail_path.name}"
                )
    except Exception as e:
        print(f"  Warning: Could not check for existing portrait: {e}")

    # Apply AI-selected portrait if available, but preserve generated portraits
    if portrait:
        if existing_generated_portrait:
            # Preserve generated portrait but update originalImage field
            portrait_data = existing_generated_portrait.copy()
            portrait_data["originalImage"] = portrait["url"]
            # Update source to point to the Wikimedia Commons page
            if "source" not in portrait_data or not portrait_data["source"].startswith(
                "http"
            ):
                portrait_data["source"] = portrait["source"]
            print(
                f"  Preserving generated portrait, updating originalImage to: {portrait['url']}"
            )
        else:
            # No generated portrait, use AI-selected Wikimedia portrait
            portrait_data = {
                "image": portrait["url"],
                "source": portrait["source"],
            }
            if portrait.get("caption"):
                portrait_data["caption"] = portrait["caption"]
            if portrait.get("creator"):
                portrait_data["creator"] = portrait["creator"]
            if portrait.get("license"):
                portrait_data["license"] = portrait["license"]
            if portrait.get("licenseUrl"):
                portrait_data["licenseUrl"] = portrait["licenseUrl"]
        person_data["portrait"] = portrait_data
    elif existing_generated_portrait:
        # No AI portrait but we have a generated one - keep it
        person_data["portrait"] = existing_generated_portrait
        print("  No AI portrait found, keeping existing generated portrait")

    payload: Dict[str, Any] = {
        "dataset": life_plan.dataset,
        "created_on": life_plan.created_on,
        "person": person_data,
        "chapters": [ch.model_dump() for ch in chapters] if chapters else None,
        "conclusion": conclusion if conclusion else None,
        "events": [ev.model_dump(exclude_none=True) for ev in enriched_events],
    }

    # Normalize metadata
    print("[Step 9/12] Normalizing dataset metadata...")
    payload = enforce_metadata(payload, page_data, summary_data)
    print(f"[Step 9/12] Dataset includes {len(payload['events'])} events")

    # Geocode with enhanced logic
    print("[Step 10/12] Resolving event location coordinates...")
    payload, geocoded_events = enrich_event_coordinates_v2(payload)
    print(f"[Step 10/12] Coordinates resolved for {geocoded_events} events")

    # Resolve a link for every published work the story names
    print("[Step 11/12] Resolving publication source links...")
    try:
        from enrich_publication_links import enrich_events as enrich_publication_links

        person_block = payload.get("person") or {}
        linked = enrich_publication_links(
            payload["events"],
            person_name=str(person_block.get("name") or identifier).replace("_", " "),
            person_article=person_block.get("wikipedia"),
            person_id=identifier,
        )
        print(f"[Step 11/12] Linked {linked} publication(s) to a source")
    except Exception as error:
        # A missing link costs the reader a click, not the run its dataset.
        print(f"Warning: could not resolve publication links ({error})")

    # Write to file
    print(f"[Step 12/12] Writing dataset for '{identifier}'...")
    existing_path = PEOPLE_DIR / identifier / "life_events.json"
    old_payload = None
    if existing_path.exists():
        try:
            old_payload = json.loads(existing_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    file_path = write_dataset(payload, identifier)

    # Preserve curated meta-story selections when event indexes or text change.
    try:
        from sync_meta_story_events import sync_meta_story_events

        sync_report = sync_meta_story_events(
            identifier, old_person_data=old_payload, new_person_data=payload
        )
        if sync_report["stories"]:
            print(
                f"Incrementally updated {sync_report['stories']} meta story/stories "
                f"({sync_report['updated']} references changed, "
                f"{sync_report['removed']} removed)"
            )
    except Exception as error:
        print(f"Warning: Could not sync meta-story events ({error})")

    if update_registry:
        print("Updating persons register...")
        update_register(identifier, payload, file_path)
        print("Register update complete")
    else:
        print("Register update skipped")

    return file_path, identifier


# ============================================================================
# CLI
# ============================================================================


def parse_args(argv: Any) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate life event datasets using two-phase AI approach."
    )
    parser.add_argument(
        "subject", help="Person to research, e.g. 'Ada Lovelace' or 'henry_II'."
    )
    parser.add_argument(
        "--url",
        help="Wikipedia URL to use for disambiguation (e.g., 'https://en.wikipedia.org/wiki/Henry_II,_Holy_Roman_Emperor').",
    )
    parser.add_argument(
        "--no-register", action="store_true", help="Skip updating the persons register."
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Skip using cached Wikipedia materials and fetch directly from APIs.",
    )
    parser.add_argument(
        "--images-only",
        action="store_true",
        help="Only re-run image search and assignment using existing life_events.json data.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=(
            f"OpenAI model to use (default from OPENAI_MODEL env or '{DEFAULT_MODEL}'). "
            "Must support structured outputs. "
            "See https://platform.openai.com/docs/guides/structured-outputs for supported models."
        ),
    )
    return parser.parse_args(argv)


def regenerate_images_only(subject: str) -> Tuple[Path, str]:
    """
    Re-run only Phase 3 (image search and assignment) using existing life_events.json.

    Returns:
        Tuple of (file_path, person_id)
    """
    # Resolve person_id from subject
    url_info = extract_wikipedia_title(subject)
    if url_info:
        article_title = url_info[0]
    else:
        article_title = subject.replace("_", " ")

    person_id = slugify(article_title)

    # Check if life_events.json exists
    person_dir = PEOPLE_DIR / person_id
    events_path = person_dir / "life_events.json"

    if not events_path.exists():
        raise FileNotFoundError(
            f"No existing data found for '{person_id}'. "
            f"Run without --images-only first to generate initial data."
        )

    print(f"[Step 1/4] Loading existing data for '{person_id}'...")
    payload = json.loads(events_path.read_text(encoding="utf-8"))

    person_data = payload.get("person", {})
    person_name = person_data.get("name", article_title)
    events = payload.get("events", [])

    print(f"[Step 1/4] Loaded {len(events)} events for {person_name}")

    # Convert events to EventSkeleton objects for the image search
    event_skeletons = []
    for event in events:
        skeleton = EventSkeleton(
            date=event.get("date", ""),
            date_precision=event.get("date_precision", "year"),
            date_end=event.get("date_end"),
            date_end_precision=event.get("date_end_precision"),
            date_note=event.get("date_note"),
            age=event.get("age"),
            title=event.get("title", ""),
            description=event.get("description", ""),
            annotations=event.get("annotations"),
        )
        event_skeletons.append(skeleton)

    # Run Phase 3: Image search and assignment
    print(
        f"[Step 2/4] PHASE 3: Discovering and assigning images (model: {PHASE3_IMAGE_SEARCH_MODEL})..."
    )

    print("  [Phase 3a] Generating image search strings...")
    search_strings = generate_image_search_strings(event_skeletons, person_name)
    print(f"    Generated {len(search_strings)} search strings")
    for ss in search_strings:
        safe_ss = ss.encode("ascii", "replace").decode("ascii")
        print(f"      • {safe_ss}")

    print("  [Phase 3b] Searching image sources (Commons + Openverse)...")
    candidate_images = execute_batch_image_search(search_strings, images_per_query=10)

    if not candidate_images:
        print("    No images found")
        return events_path, person_id

    print(f"    Found {len(candidate_images)} candidate images")

    # Quality pre-filtering (permissive - AI makes final decisions)
    print("  [Phase 3b+] Applying quality pre-filtering...")
    filtered_images = filter_images_by_quality(
        candidate_images,
        person_name=person_name,
        min_score=10.0,  # Permissive threshold (out of 45 possible)
    )

    if not filtered_images:
        print("    No images passed quality filters")
        return events_path, person_id

    filtered_count = len(candidate_images) - len(filtered_images)
    print(
        f"    Filtered out {filtered_count} low-quality images ({len(filtered_images)} remaining)"
    )

    # Show quality score distribution
    if filtered_images:
        scores = [img.get("quality_score", 0) for img in filtered_images]
        avg_score = sum(scores) / len(scores)
        max_score = max(scores)
        min_score = min(scores)
        print(
            f"    Quality scores: avg={avg_score:.1f}, range={min_score:.1f}-{max_score:.1f}"
        )

    print(
        f"  [Phase 3c] AI matching {len(filtered_images)} images to {len(event_skeletons)} events..."
    )
    assignments, portrait = match_images_to_events(
        filtered_images, event_skeletons, person_name
    )
    print(f"    Assigned images to {len(assignments)} events")
    if portrait:
        print("    ✓ Portrait selected")

    # Apply portrait to person data
    print("[Step 3/4] Updating events with new image assignments...")

    # Check if there's already a generated portrait in the registry OR on disk
    existing_generated_portrait = None
    try:
        # First check registry
        if REGISTER_PATH.exists():
            registry = json.loads(REGISTER_PATH.read_text(encoding="utf-8"))
            people = registry.get("people", [])
            for person in people:
                if person.get("id") == person_id:
                    existing_portrait = person.get("portrait", {})
                    # Check if it's a generated portrait (local path starting with /portraits/)
                    if existing_portrait and isinstance(
                        existing_portrait.get("image"), str
                    ):
                        if existing_portrait["image"].startswith("/portraits/"):
                            existing_generated_portrait = existing_portrait
                            print(
                                f"    Found existing generated portrait in registry: {existing_portrait['image']}"
                            )
                    break

        # If not in registry, check if portrait files exist on disk
        if not existing_generated_portrait:
            portraits_dir = Path(__file__).resolve().parents[1] / "public" / "portraits"
            thumbnail_path = portraits_dir / f"{person_id}_thumbnail.webp"
            if thumbnail_path.exists():
                # Found generated portrait files - reconstruct portrait data
                existing_generated_portrait = {
                    "image": f"/portraits/{person_id}_thumbnail.webp",
                    "thumbnail": f"/portraits/{person_id}_thumbnail.webp",
                    "medium": f"/portraits/{person_id}_medium.webp",
                    "full": f"/portraits/{person_id}_full.webp",
                    "caption": "Stylized portrait based on historical photograph",
                    "creator": "AI generated artwork",
                }
                print(
                    f"    Found existing generated portrait files on disk: {thumbnail_path.name}"
                )
    except Exception as e:
        print(f"    Warning: Could not check for existing portrait: {e}")

    if portrait:
        if existing_generated_portrait:
            # Preserve generated portrait but update originalImage field
            portrait_data = existing_generated_portrait.copy()
            portrait_data["originalImage"] = portrait["url"]
            # Update source to point to the Wikimedia Commons page
            if "source" not in portrait_data or not portrait_data["source"].startswith(
                "http"
            ):
                portrait_data["source"] = portrait["source"]
            print(
                f"    Preserving generated portrait, updating originalImage to: {portrait['url']}"
            )
        else:
            # No generated portrait, use AI-selected Wikimedia portrait
            portrait_data = {
                "image": portrait["url"],
                "source": portrait["source"],
            }
            if portrait.get("caption"):
                portrait_data["caption"] = portrait["caption"]
            if portrait.get("creator"):
                portrait_data["creator"] = portrait["creator"]
            if portrait.get("license"):
                portrait_data["license"] = portrait["license"]
            if portrait.get("licenseUrl"):
                portrait_data["licenseUrl"] = portrait["licenseUrl"]
        payload["person"]["portrait"] = portrait_data
    elif existing_generated_portrait:
        # No AI portrait but we have a generated one - keep it
        payload["person"]["portrait"] = existing_generated_portrait
        print("    No AI portrait found, keeping existing generated portrait")
    else:
        # AI found no suitable portrait and no generated portrait exists
        payload["person"].pop("portrait", None)
        print("    No suitable portrait found - removed existing portrait")

    # Apply assignments to events
    for idx, event in enumerate(events):
        if idx in assignments:
            img = assignments[idx]
            image_data = {
                "url": img["url"],
                "caption": img["caption"],
                "source": img["source"],
            }
            if img.get("creator"):
                image_data["creator"] = img["creator"]
            if img.get("license"):
                image_data["license"] = img["license"]
            if img.get("licenseUrl"):
                image_data["licenseUrl"] = img["licenseUrl"]
            event["images"] = [image_data]
            safe_title = (
                event.get("title", "").encode("ascii", "replace").decode("ascii")
            )
            print(f"    ✓ Event {idx}: {safe_title}")
        else:
            # Remove old images
            event.pop("images", None)

    payload["events"] = events

    # Write updated file
    print("[Step 4/4] Writing updated dataset...")
    events_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    images_assigned = sum(1 for e in events if e.get("images"))
    print(f"\nDone! Assigned images to {images_assigned} / {len(events)} events")

    # Update persons.json registry with updated portrait (or removed portrait)
    update_register(person_id, payload, events_path)
    print(f"Register updated at {REGISTER_PATH}")

    return events_path, person_id


def main(argv: Any = None) -> int:
    args = parse_args(argv)
    try:
        # When URL is provided, use it for fetching but preserve original subject as person_id
        if args.url:
            subject_for_fetch = args.url
            person_id_override = slugify(args.subject)
        else:
            subject_for_fetch = args.subject
            person_id_override = None

        if args.images_only:
            file_path, person_id = regenerate_images_only(subject_for_fetch)
            print(f"\nDataset updated at {file_path}")
        else:
            file_path, person_id = generate_person_events(
                subject_for_fetch,
                person_id=person_id_override,
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
