#!/usr/bin/env python3
"""Generate person network datasets for notable people using Wikipedia content and the OpenAI API."""

import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, cast

import requests
from openai import OpenAI
from pydantic import BaseModel, Field

from config import DEFAULT_MODEL, DEFAULT_REASONING_EFFORT
from utils.http import QueryParams
from utils.json_io import write_json
from utils.model_calls import parse_structured_or_raise
from utils.registry import Registry
from utils.relationship_vocabulary import (
    CATEGORIES,
    ROLES,
    RelationshipCategory,
    RelationshipRole,
    normalize_relationship_type,
    plain_parent_roles,
)
from utils.citations import citable_urls, keep_citable
from utils.text import slugify
from utils.wikipedia_cache import (
    ensure_cache,
    extract_wikipedia_title,
    fetch_wikipedia_extract,
    get_cache_dir,
    get_cached_wikipedia_page,
    wikipedia_headers,
)

# Import from cache_wikipedia_materials for related articles functionality
try:
    from cache_wikipedia_materials import fetch_related_articles
except ImportError:
    fetch_related_articles = None  # type: ignore[assignment]

DATASET_NAME = "Life Data Stories"
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
REGISTER_PATH = DATA_DIR / "persons.json"
PEOPLE_DIR = DATA_DIR / "people"
MEDIAWIKI_API = "https://en.wikipedia.org/w/api.php"
DEFAULT_USER_AGENT = (
    "life-ds-data-generator/1.0 (+https://github.com/fabian-beck/life-ds)"
)


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


# Pydantic models for structured outputs
class Connection(BaseModel):
    """A connection/relationship in the ego network.

    Every connection is a mutual tie: two people who dealt with each other
    directly. The schema therefore carries no direction of influence, no
    years, and no activity tags — the type, the description, and the two
    weights say what the tie was.
    """

    person_name: str = Field(
        description="Full name of the connected individual. Every connection is "
        "one human being: never an organization, an institution, a company, a "
        "state, a regime, an office, a staff, a team, or any other collective. "
        "The two people dealt with each other directly; someone the subject "
        "only read, admired, or was later taken up by is not a connection. "
        "Never append an explanatory parenthetical."
    )
    relationship_category: RelationshipCategory = Field(
        description="The circle this connection belongs to. Stored joined with "
        "the role as 'category/role', e.g. 'family/father' or 'political/censor'."
    )
    relationship_role: RelationshipRole = Field(
        description="What the other party is or did toward the subject — the "
        "reader's one-word tag for the tie. The unqualified role is the default; "
        "a qualified one needs a reason the sources document."
    )
    relationship_description: str = Field(
        description="Brief description of the nature of the relationship"
    )
    strength: str = Field(
        description="Strength of the relationship: 'strong', 'moderate', or 'weak'"
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
    birth_year: Optional[int] = Field(None, description="Birth year of the ego")
    death_year: Optional[int] = Field(
        None, description="Death year of the ego (null if still alive)"
    )
    primary_roles: List[str] = Field(
        description="Primary roles or professions of the ego"
    )
    summary: str = Field(description="Brief biographical summary of the ego")
    wikipedia: Optional[str] = Field(None, description="Wikipedia URL for the ego")


class CategorySummary(BaseModel):
    """Summary for a specific relationship category."""

    relationship_type: RelationshipCategory = Field(
        description="The main relationship category being summarized (without the role), "
        "e.g. 'family', 'professional', 'social', 'artistic', 'academic', 'political'"
    )
    summary: str = Field(
        description="Contextualizing prose about what this circle of relationships meant for the person's "
        "life and work. Explain roles, dynamics, and consequences instead of enumerating names. "
        "Length follows the evidence: one or two sentences when the record is thin, a fuller paragraph "
        "when it is rich."
    )


class EgoNetwork(BaseModel):
    """Complete ego network dataset for a person."""

    dataset: str = Field(description="Name of the dataset")
    created_on: str = Field(description="Creation date in ISO-8601 format")
    ego: EgoNetworkMetadata = Field(description="Metadata about the central person")
    connections: List[Connection] = Field(
        description="List of connections/relationships in the ego network"
    )
    category_summaries: List[CategorySummary] = Field(
        description="Brief summaries for each relationship category present in the network, starting with family"
    )


def _fetch_wikipedia_page(title: str, lang: Optional[str] = None) -> Dict[str, Any]:
    """Fetch Wikipedia page data."""
    # Use English by default
    language = lang or "en"
    api_url = f"https://{language}.wikipedia.org/w/api.php"

    params: QueryParams = {
        "action": "query",
        "format": "json",
        "prop": "extracts|info",
        "explaintext": 1,
        "redirects": 1,
        "inprop": "url",
        "titles": title,
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


def load_existing_dataset(person_id: str) -> Optional[Dict[str, Any]]:
    """Load existing life events dataset if available."""
    person_dir = PEOPLE_DIR / person_id
    dataset_path = person_dir / "life_events.json"
    if dataset_path.exists():
        try:
            return cast(
                Optional[Dict[str, Any]],
                json.loads(dataset_path.read_text(encoding="utf-8")),
            )
        except json.JSONDecodeError:
            return None
    return None


def build_prompt(
    page_data: Dict[str, Any],
    existing_dataset: Optional[Dict[str, Any]],
    subject: str,
    related_articles: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Build the prompt for OpenAI API."""
    extract_text = page_data.get("extract", "").strip()

    combined = f"Page title: {page_data.get('title', subject)}\nPage URL: {page_data.get('fullurl', '')}\n\n"

    if existing_dataset:
        person_info = existing_dataset.get("person", {})
        combined += "Known information about the person:\n"
        combined += json.dumps(person_info, indent=2, ensure_ascii=False)
        combined += "\n\nSample life events:\n"
        events = existing_dataset.get("events", [])[:10]
        combined += json.dumps(events, indent=2, ensure_ascii=False)
        combined += "\n\n"

    if extract_text:
        truncated = extract_text[:15000]
        combined += f"Full Wikipedia extract (truncated to 15k characters if needed):\n{truncated}\n"

    if related_articles and len(related_articles) > 0:
        combined += f"\n\n{'='*60}\nRELATED WIKIPEDIA ARTICLES - Additional context:\n{'='*60}\n"
        combined += "The following related articles may mention additional connections and relationships:\n\n"
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


def call_openai(prompt: str, model: str) -> Dict[str, Any]:
    """Call OpenAI API with structured output."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY environment variable is not set.")
    client = OpenAI(api_key=api_key)

    system = (
        "You are a meticulous social network analyst who converts raw Wikipedia content into structured JSON ego networks. "
        "Focus on identifying significant relationships in a person's life, including family members, colleagues, mentors, "
        "students, collaborators, friends, rivals, and other important connections. "
        "Every node of the network is one individual human being; an organization, a state, a regime, or a group of people is never a node. "
        "Every tie of the network is mutual: the two people dealt with each other directly. "
        "IMPORTANT: All output text must be in American English only, regardless of the source language. "
        "IMPORTANT: Use only 3-5 main relationship categories maximum to keep the network organized and focused. "
        "Every text field is plain text rendered verbatim by the interface: never write "
        "Markdown in it — no *emphasis* or **bold**, no `code`, no [links](url). A "
        "person's name or a work's title stands plain in the sentence, without "
        "asterisks around it."
    )

    instructions = (
        "Analyze the provided Wikipedia content and extract an ego network for the subject. "
        "Include 10-25 significant connections/relationships. For each connection provide:\n"
        "- person_name: Full name of the connected person (IMPORTANT: Each person should appear ONLY ONCE in the network - do not create separate entries for the same person in different roles). "
        "Never put an explanatory parenthetical into the name.\n"
        "  INDIVIDUALS ONLY: every connection is a single, named human being — someone who could be the subject of a biography. "
        "Never make an organization, an institution, a company, a university, a government, a state, a regime, a party, a police force, "
        "a committee, a movement, or an unnamed collective ('editorial staff', 'programming team', 'colleagues at X', 'members of Y') into a connection. "
        "When the sources tie the subject to a collective — an employer, a committee, a regime that persecuted them — name the individual through whom the tie ran "
        "(the director who hired them, the official who dismissed them, the chair they served under) if the sources name one; "
        "otherwise leave the tie out of the connections and let the category summary carry it in prose.\n"
        "  MUTUAL TIES ONLY: a connection is a relationship both people took part in — they met, corresponded, worked, lived, "
        "studied, or fought with one another, and the sources document the contact. Someone the subject only read, admired, "
        "or was shaped by from afar is not a connection, and neither is someone who only later drew on the subject's work "
        "or memory without ever dealing with them. Such one-sided influence belongs in the category summary as prose, if anywhere. "
        "The 'influence', 'inspiration', and 'legacy' roles therefore name a documented direct tie — a teacher whose ideas the "
        "subject took up in their classroom, a student who carried the subject's work on — never a distant reading.\n"
        "- relationship_category and relationship_role: the two halves of the closed vocabulary; "
        "the stored type is 'category/role':\n"
        f"  Categories (select the 3-5 that best represent this person's network): {', '.join(sorted(CATEGORIES))}\n"
        "  Each category becomes one circle the reader sees, so keep them coarse: 'academic' holds every tie of "
        "scholarship and ideas — teachers, students, colleagues, influences, and the opponents of a scientific "
        "debate alike — and there is no separate intellectual circle.\n"
        f"  Roles: {', '.join(sorted(ROLES))}\n"
        "  The role names what the other party is or did toward the subject, as the reader's one-word tag for the tie. "
        "The unqualified role is the default — 'father', 'colleague', 'friend' — and a qualified one "
        "('adoptive_father', 'close_colleague', 'stepmother') needs a reason the sources document. "
        "A parent is 'father' or 'mother'; 'biological_father'/'biological_mother' exist only for the "
        "birth parents of a subject raised by adoptive or step parents, who then take those roles.\n"
        "  CONFLICT DIRECTION: for a relationship with a state or regime official, the role must name the ACTION toward the subject, never the office. "
        "The persecutor, censor, or patron is the person who acted — a minister, a police chief, a denouncing colleague — never the regime, the state, or the police force as such. "
        "Use 'political/censor' (banned or suppressed the subject's work), 'political/persecutor' (interrogated, denounced, drove out, or otherwise acted against the subject), "
        "'political/banned_by' (excluded the subject from a profession, guild, or publication), or 'political/patron' (protected or promoted them). "
        "Never a neutral role word like 'gatekeeper' or 'authority', and never 'opponent' or 'rival' for one-sided persecution — "
        "'opponent', 'rival', and 'adversary' are reserved for genuinely two-sided conflicts.\n"
        "- relationship_description: Brief description of the relationship — what the two did with or to each other, "
        "and when, if the sources date it\n"
        "- strength: 'strong', 'moderate', or 'weak'\n"
        "- sources: Wikipedia URLs supporting this connection\n"
        "- notes: Additional context (optional)\n\n"
        "IMPORTANT BALANCE CONSIDERATIONS:\n"
        "- Family relationships: Include BOTH parents (father AND mother) when information is available. "
        "Treat maternal and paternal relationships with equal importance.\n"
        "- Gender balance: When sufficient information is available, aim for diverse representation across genders "
        "in the network (not just male-dominated networks). Include significant women in the person's life.\n"
        "- Work-life balance: Strive for a balanced network that includes BOTH professional/academic connections "
        "AND personal/family/social relationships when information is available. "
        "Avoid over-representing one sphere at the expense of the other.\n"
        "- Quality over quantity: Only include relationships where sufficient information exists. "
        "Do not artificially inflate representation - balance should emerge naturally from available evidence.\n\n"
        "Focus on well-documented relationships with clear evidence in the Wikipedia text. "
        "Prioritize quality over quantity - include only connections with sufficient information.\n\n"
        "Also provide:\n"
        "- Ego metadata (name, birth/death years, roles, summary)\n"
        "- Category summaries: one for each of the 3-5 MAIN categories you used in the network. "
        "Start with family if present, then order the rest by importance or prevalence. "
        "Remember: use exactly 3-5 categories total, no more.\n\n"
        "WRITING THE CATEGORY SUMMARIES:\n"
        "The reader sees every name in the category as a labeled chip directly beside the summary, so a "
        "roll call of names adds nothing. Write the context the chips cannot show: what this circle of "
        "people meant for the person's life and work.\n"
        "- Contextualize: give each named person a reason to be there — what they changed, taught, funded, "
        "opposed, or made possible. Name a place, an institution, a year, or a work when it anchors the point.\n"
        "- Structure: open with the claim that holds the category together (what role these ties played), "
        "then develop it — the decisive figures first, the shift over time, the tension or contrast, "
        "and where it led. Do not stack parallel clauses of the form 'X was his teacher, Y was his colleague'.\n"
        "- Be selective: mention the few people who carry the story. Leaving someone unnamed is fine; "
        "the chips already list everyone.\n"
        "- Let the evidence set the length. Choose it yourself rather than filling a quota: one or two "
        "sentences when the sources say little, a substantial paragraph of five or six when they support it. "
        "A short, dense summary beats a padded one; never invent detail to reach a length.\n"
        "- Vary the shape across categories. A family summary is not a professional summary in different "
        "words, and the summaries for two different people should not read from the same template.\n"
        "- Do not repeat the relationship_description text verbatim; the summary is the layer above them.\n"
        "- Plain prose only: no markdown, no bullet lists, no headings."
    )

    parsed = parse_structured_or_raise(
        client,
        model=model,
        reasoning_effort=DEFAULT_REASONING_EFFORT,
        input=[
            {"role": "system", "content": system},
            {"role": "user", "content": instructions},
            {"role": "user", "content": prompt},
        ],
        text_format=EgoNetwork,
        label="Ego network",
    )
    payload = parsed.model_dump()
    # The schema carries the two vocabulary segments separately, so the model
    # cannot leave the closed vocabulary; the stored token is the joined form
    # the interface localizes.
    for conn in payload.get("connections", []):
        conn["relationship_type"] = (
            f"{conn.pop('relationship_category')}/{conn.pop('relationship_role')}"
        )
    return payload


def _normalize_person_name(name: str) -> str:
    """
    Normalize a person name for deduplication.

    Removes parenthetical notes, extra whitespace, and normalizes case.
    Examples:
        'Eugene Wigner' -> 'eugene wigner'
        'Eugene Wigner (as biographer/assessor)' -> 'eugene wigner'
        'Max (Miksa) von Neumann' -> 'max von neumann'
    """
    # Remove parenthetical content (e.g., "(as biographer/assessor)", "(Miksa)")
    name = re.sub(r"\s*\([^)]*\)", "", name)
    # Normalize whitespace
    name = " ".join(name.split())
    # Lowercase for comparison
    return name.strip().lower()


# Words that end, or stand as, the name of a collective rather than a person.
# The generation prompt forbids such nodes; this check only reports the ones
# that get through, so a run log shows them before the data ships.
_COLLECTIVE_WORDS = (
    "abbey|academy|agency|army|association|board|bureau|cabaret|club|"
    "college|colleagues|commission|committee|community|company|corporation|"
    "council|court|editors|employees|ensemble|faculty|family|federation|"
    "firm|forum|founders|foundation|government|group|institute|institution|"
    "laboratory|leadership|league|members|ministry|movement|office|officials|"
    "organization|parliament|party|peers|police|professionals|regime|"
    "researchers|school|society|staff|state|students|team|troupe|union|"
    "university|users"
)
_COLLECTIVE_NAME = re.compile(
    rf"(^|\b)(the )?({_COLLECTIVE_WORDS})\b(\s*\(.*\)|,\s.*)?$", re.IGNORECASE
)
# A plurality named by what it does or where it sits: 'Students at ...',
# 'Editors of ...', 'Founders of ...'.
_COLLECTIVE_HEAD = re.compile(
    rf"^(the )?({_COLLECTIVE_WORDS})\s+(at|of|in|from)\b", re.IGNORECASE
)
# Two people joined into one entry: 'Philip Johnson and Mark Wigley'.
_CONJUNCTION = re.compile(r"\s(and|&)\s")
_INITIALISM = re.compile(r"^[A-Z][A-Z0-9&.]{1,}$")


def looks_collective(name: str) -> bool:
    """Report whether a connection name reads as a collective, not a person.

    A name ends in, or opens with, a word that names an institution, a body,
    or a plurality of people ('Nazi regime', 'IBM', 'Students at ...' — a
    plain 'Gestapo' escapes it), is a bare initialism, or joins two people
    with 'and'. The check is a heuristic that only reports; the schema and
    the prompt are what keep collectives out of a fresh run.
    """
    text = " ".join(str(name or "").split())
    if not text:
        return False
    if _INITIALISM.match(text) or _CONJUNCTION.search(text):
        return True
    return bool(_COLLECTIVE_NAME.search(text) or _COLLECTIVE_HEAD.match(text))


def _deduplicate_connections(connections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Deduplicate connections by person name, merging information from duplicates.

    When duplicates are found (same normalized name):
    - Keep the first occurrence as the base
    - Merge relationship descriptions
    - Combine sources (deduplicated)
    - Prefer 'strong' over 'moderate' over 'weak' strength
    """
    seen_names: Dict[str, int] = {}  # normalized_name -> index in result
    result: List[Dict[str, Any]] = []

    strength_priority = {"strong": 3, "moderate": 2, "weak": 1}

    for conn in connections:
        person_name = conn.get("person_name", "")
        normalized = _normalize_person_name(person_name)

        if normalized in seen_names:
            # Merge with existing entry
            idx = seen_names[normalized]
            existing = result[idx]

            # Clean up the person_name (remove parenthetical notes)
            existing["person_name"] = re.sub(r"\s*\([^)]*\)", "", person_name).strip()

            # Merge descriptions
            desc1 = existing.get("relationship_description", "")
            desc2 = conn.get("relationship_description", "")
            if desc2 and desc2 not in desc1:
                existing["relationship_description"] = f"{desc1} {desc2}".strip()

            # Merge sources (deduplicate)
            sources = set(existing.get("sources", []))
            sources.update(conn.get("sources", []))
            existing["sources"] = sorted(sources)

            # Merge notes
            notes1 = existing.get("notes", "")
            notes2 = conn.get("notes", "")
            if notes2 and notes2 not in notes1:
                existing["notes"] = f"{notes1} {notes2}".strip() if notes1 else notes2

            # Use stronger relationship strength
            str1 = strength_priority.get(existing.get("strength", "").lower(), 0)
            str2 = strength_priority.get(conn.get("strength", "").lower(), 0)
            if str2 > str1:
                existing["strength"] = conn["strength"]

        else:
            # First time seeing this person
            # Clean up the person_name (remove parenthetical notes)
            conn["person_name"] = re.sub(r"\s*\([^)]*\)", "", person_name).strip()
            seen_names[normalized] = len(result)
            result.append(conn)

    return result


def _normalize_relationship_types(connections: List[Dict[str, Any]]) -> None:
    """Hold every relationship type to the closed vocabulary, in place.

    The generation schema types the two segments as Literals, so a fresh run
    cannot leave the vocabulary and this pass is a no-op there. It stays as
    the belt-and-braces check for anything that reaches this code around the
    schema; a token outside the vocabulary is kept and reported, so the gap
    surfaces in the run log (and in tests/test_relationship_vocabulary.py)
    instead of shipping silently.
    """
    for conn in connections:
        original = conn.get("relationship_type", "")
        normalized, known = normalize_relationship_type(original)
        if normalized and normalized != original:
            conn["relationship_type"] = normalized
    for name in plain_parent_roles(connections):
        print(
            f"  Note: {name!r} carried a biological parent role with no adoptive "
            "or step parent in the network to contrast it; folded to the plain role."
        )
    for conn in connections:
        if not known:
            print(
                f"  Warning: relationship type outside the vocabulary kept as-is: "
                f"{original!r} ({conn.get('person_name')}) — extend "
                f"scripts/utils/relationship_vocabulary.py and the locales, "
                f"or correct the entry."
            )
        if looks_collective(conn.get("person_name", "")):
            print(
                f"  Warning: connection named like a collective rather than "
                f"an individual kept as-is: {conn.get('person_name')!r} — "
                f"name the person behind the tie or drop the entry."
            )


def _article_key(title: str) -> str:
    """An article title as it compares: underscores spaced out, case folded."""
    return re.sub(r"\s+", " ", str(title or "").replace("_", " ")).strip().casefold()


def cached_article_urls(
    related_articles: Optional[List[Dict[str, Any]]],
) -> Dict[str, str]:
    """The URL the cache holds for each related article, by title."""
    urls: Dict[str, str] = {}
    for article in related_articles or []:
        if not isinstance(article, dict):
            continue
        key = _article_key(article.get("title", ""))
        url = str(article.get("url") or "").strip()
        if key and url:
            urls.setdefault(key, url)
    return urls


def repair_source_urls(
    connections: List[Dict[str, Any]],
    related_articles: Optional[List[Dict[str, Any]]],
) -> List[Tuple[str, str]]:
    """Cite a related article at the URL the cache actually holds for it.

    The cached related articles are not all English: the search falls back to
    the German Wikipedia for a person English Wikipedia does not carry, and
    each cached entry records the URL it came from. The model is shown that
    URL and writes an English one anyway, composing
    ``en.wikipedia.org/wiki/<cached title>`` — and a German title is rarely
    the English one. Babbage's network cited
    ``en.wikipedia.org/wiki/Georg_Scheutz``, which is no article at all:
    English Wikipedia calls him Per Georg Scheutz, so the chip's source link
    led the reader to a "no article" page.

    A cited title the cache holds is therefore pointed back at the cache's own
    URL. A title the cache does not hold is left alone — guessing which
    article was meant is what produced the dead link.  Returns the
    ``(before, after)`` pairs it rewrote.
    """
    urls = cached_article_urls(related_articles)
    if not urls:
        return []
    repaired: List[Tuple[str, str]] = []
    for connection in connections:
        sources = connection.get("sources")
        if not isinstance(sources, list):
            continue
        rewritten: List[str] = []
        for source in sources:
            url = str(source or "").strip()
            parsed = extract_wikipedia_title(url) if url else None
            if parsed:
                cached = urls.get(_article_key(parsed[0]))
                if cached and cached != url:
                    repaired.append((url, cached))
                    url = cached
            if url and url not in rewritten:
                rewritten.append(url)
        connection["sources"] = rewritten
    return repaired


def enforce_metadata(
    payload: Dict[str, Any],
    page_data: Dict[str, Any],
    person_id: str,
    related_articles: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Ensure consistent metadata in the payload."""
    payload.setdefault("dataset", DATASET_NAME)
    payload["created_on"] = date.today().isoformat()

    ego = payload.setdefault("ego", {})
    ego.setdefault("name", page_data.get("title"))

    if page_data.get("fullurl"):
        ego.setdefault("wikipedia", page_data["fullurl"])

    # Deduplicate connections by person name (case-insensitive, normalized)
    connections = payload.get("connections", [])
    connections = _deduplicate_connections(connections)
    _normalize_relationship_types(connections)

    # Sort connections by relationship strength; the sort is stable, so ties
    # keep the order the model gave them.

    def connection_sort_key(conn: Dict[str, Any]) -> int:
        strength_order = {"strong": 0, "moderate": 1, "weak": 2}
        return strength_order.get(conn.get("strength", "").lower(), 3)

    connections.sort(key=connection_sort_key)

    for before, after in repair_source_urls(connections, related_articles):
        print(f"    Source cited as {before} -> {after}")

    # A source is kept only when the call was shown its article; any other is a
    # URL the model composed. Without cached articles there is nothing to
    # compare against, and the sources stand as written.
    if related_articles:
        allowed = citable_urls(page_data.get("fullurl"), related_articles)
        for connection in connections:
            connection["sources"] = keep_citable(connection.get("sources"), allowed)

    payload["connections"] = connections

    return payload


def write_ego_network(payload: Dict[str, Any], person_id: str) -> Path:
    """Write ego network to a JSON file."""
    person_dir = PEOPLE_DIR / person_id
    person_dir.mkdir(parents=True, exist_ok=True)
    output_path = person_dir / "ego_network.json"
    write_json(output_path, payload)
    return output_path


def update_register(person_id: str, payload: Dict[str, Any], file_path: Path) -> None:
    """Update the persons register - ensure person exists and update lastUpdated timestamp."""
    from datetime import datetime

    current_timestamp = datetime.now().astimezone().isoformat()
    registry = Registry(REGISTER_PATH)
    existing = registry.find(person_id)

    if existing is not None:
        # The dataset generator owns this entry's contents; a network run only
        # records that it touched the person.
        existing["lastUpdated"] = current_timestamp
    else:
        # Nothing has generated life events for this person yet, so leave a
        # minimal entry for that run to fill in — and put it in its place,
        # which is only needed when the list actually grew.
        registry.upsert(
            {
                "id": person_id,
                "name": payload.get("ego", {}).get(
                    "name", person_id.replace("_", " ").title()
                ),
                "summary": payload.get("ego", {}).get("summary", ""),
                "created": current_timestamp,
                "lastUpdated": current_timestamp,
            }
        )
        registry.sort_by_name()

    registry.save()


def generate_person_network(
    subject: str,
    *,
    person_id: Optional[str] = None,
    update_registry: bool = True,
    model: str = DEFAULT_MODEL,
    use_cache: bool = True,
) -> Path:
    """Generate a person network dataset for a person."""
    print(f"[1/6] Fetching Wikipedia article for '{subject}'...")
    page_data = fetch_wikipedia_extract(subject, _fetch_wikipedia_page)
    article_title = page_data.get("title", subject)
    print(f"[1/6] Found article '{article_title}'.")

    if person_id is None:
        person_id = slugify(article_title)

    # Try to use cache if enabled
    related_articles = None
    if use_cache:
        print(f"[2/6] Checking cache for '{person_id}'...")
        try:
            ensure_cache(person_id, article_title, person_name=article_title)
            # Load from cache
            page_data = get_cached_wikipedia_page(
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
                        f"[2/6] Using cached Wikipedia data with {len(related_articles)} related articles"
                    )
                except json.JSONDecodeError:
                    print("[2/6] Using cached Wikipedia data")
            else:
                print("[2/6] Using cached Wikipedia data")
        except Exception as e:
            print(f"[2/6] Cache unavailable ({e}), using fetched data...")

    # Fetch related articles if not already loaded from cache
    if related_articles is None and fetch_related_articles is not None:
        print("[2/6] Fetching related articles...")
        try:
            related_articles = fetch_related_articles(
                article_title,
                max_related=15,
                model=model,
                use_cache=use_cache,
                person_id=person_id,
            )
            print(f"[2/6] Found {len(related_articles)} related articles.")
        except Exception as e:
            print(f"[2/6] Warning: Failed to fetch related articles ({e})")
            related_articles = None

    print("[2/6] Checking for existing life events dataset...")
    existing_dataset = load_existing_dataset(person_id)
    if existing_dataset:
        print(f"[2/6] Found existing dataset for '{person_id}'.")
    else:
        print("[2/6] No existing dataset found (will use only Wikipedia content).")

    print("[3/6] Building prompt for OpenAI response...")
    prompt = build_prompt(
        page_data, existing_dataset, subject, related_articles=related_articles
    )

    print(f"[4/6] Requesting structured ego network from model '{model}'...")
    payload = call_openai(prompt, model)
    print("[4/6] Response received from OpenAI.")

    print("[5/6] Normalizing ego network metadata...")
    payload = enforce_metadata(payload, page_data, person_id, related_articles)
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
        description="Generate person network datasets using Wikipedia and the OpenAI API."
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
        "--model",
        default=DEFAULT_MODEL,
        help=(
            f"OpenAI model to use (default from OPENAI_MODEL env or '{DEFAULT_MODEL}'). "
            "Must support structured outputs. "
            "See https://platform.openai.com/docs/guides/structured-outputs for supported models."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Any = None) -> int:
    """Main entry point."""
    args = parse_args(argv)

    # When URL is provided, use it for fetching but preserve original subject as person_id
    if args.url:
        subject_for_fetch = args.url
        person_id_override = slugify(args.subject)
    else:
        subject_for_fetch = args.subject
        person_id_override = None

    try:
        file_path = generate_person_network(
            subject_for_fetch,
            person_id=person_id_override,
            update_registry=not args.no_register,
            model=args.model,
            use_cache=not args.no_cache,
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
