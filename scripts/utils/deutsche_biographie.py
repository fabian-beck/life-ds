#!/usr/bin/env python3
"""Deutsche Biographie (deutsche-biographie.de) data fetching and caching.

Uses the open Solr API at data.deutsche-biographie.de to fetch biographical
metadata and article text.  Licensing per record:

  - Metadata fields (r_* prefix): CC0 — always usable
  - ADB article text (a_le field): CC-BY-NC-SA — usable as AI context
  - NDB article text (n_le field): CC-BY-NC-ND — NOT usable for remixing

The module checks each record individually and only includes article text
when the license permits it (ADB).
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

import requests

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SOLR_API = "https://data.deutsche-biographie.de/beta/solr-open/"
BASE_URL = "https://www.deutsche-biographie.de"
DEFAULT_USER_AGENT = (
    "life-ds-data-generator/1.0 (+https://github.com/fabian-beck/life-ds)"
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
PEOPLE_DIR = DATA_DIR / "people"

CACHE_FILENAME = "deutsche_biographie.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _headers() -> Dict[str, str]:
    import os

    return {"User-Agent": os.getenv("WIKIPEDIA_USER_AGENT", DEFAULT_USER_AGENT)}


def _parse_geo(geo_str: str) -> Optional[List[float]]:
    """Parse 'lat,lng' string into [lat, lng] list."""
    try:
        parts = geo_str.split(",")
        if len(parts) == 2:
            return [float(parts[0].strip()), float(parts[1].strip())]
    except (ValueError, AttributeError):
        pass
    return None


def _first(value: Any) -> Any:
    """Return first element if list, else value itself."""
    if isinstance(value, list) and value:
        return value[0]
    return value


# ---------------------------------------------------------------------------
# Solr API search
# ---------------------------------------------------------------------------


def _solr_query(query: str, rows: int = 5) -> List[Dict[str, Any]]:
    """Execute a Solr query and return the docs list."""
    params = {"q": query, "wt": "json", "rows": str(rows)}
    resp = requests.get(SOLR_API, params=params, timeout=30, headers=_headers())
    resp.raise_for_status()
    data = resp.json()
    return cast(List[Dict[str, Any]], data.get("response", {}).get("docs", []))


def search_person(
    name: str,
    birth_year: Optional[int] = None,
    death_year: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Search Deutsche Biographie for a person by name.

    Tries multiple query strategies and returns the best match.
    Optionally filters by birth/death year for disambiguation.
    """
    candidates: List[Dict[str, Any]] = []

    # Clean name: strip initials like "E.T.A." or "J.S." for surname extraction
    parts = name.strip().split()
    if len(parts) >= 2:
        surname = parts[-1]
        # Build firstname variants (full sequence, first only)
        firstname_full = " ".join(parts[:-1])
        firstname_first = parts[0]

        # Strategy 1: exact full name match "Lastname, Full Firstname"
        docs = _solr_query(f'defnam:"{surname}, {firstname_full}"', rows=5)
        candidates.extend(docs)

        # Strategy 2: shortened "Lastname, Firstname" (first name only)
        if firstname_full != firstname_first and not candidates:
            docs = _solr_query(f'defnam:"{surname}, {firstname_first}"', rows=5)
            candidates.extend(docs)

        # Strategy 3: surname + birth year (great for disambiguation)
        if birth_year and not candidates:
            docs = _solr_query(f"defnam:{surname}* AND byears:{birth_year}", rows=5)
            candidates.extend(docs)

        # Strategy 4: wildcard on surname (broad fallback)
        if not candidates:
            docs = _solr_query(f"defnam:{surname}*", rows=10)
            candidates.extend(docs)
    else:
        docs = _solr_query(f"defnam:{name}*", rows=10)
        candidates.extend(docs)

    if not candidates:
        return None

    # Deduplicate by id
    seen = set()
    unique = []
    for doc in candidates:
        doc_id = doc.get("id")
        if doc_id and doc_id not in seen:
            seen.add(doc_id)
            unique.append(doc)
    candidates = unique

    # Score candidates by name match quality and year match
    target_name = name.lower().strip()
    target_parts = set(re.findall(r"[a-zäöüß]+", target_name))

    best_doc = None
    best_score = -1.0

    for doc in candidates:
        defnam = (doc.get("defnam") or "").lower()
        # Skip family entries
        if doc.get("r_fam"):
            continue

        score = 0.0

        # Name matching: check overlap of name parts
        doc_parts = set(re.findall(r"[a-zäöüß]+", defnam))
        overlap = target_parts & doc_parts
        if overlap:
            score += len(overlap) / max(len(target_parts), 1) * 10

        # Exact firstname+lastname match bonus
        for part in target_parts:
            if part in defnam:
                score += 2

        # Year matching
        if birth_year and doc.get("byears"):
            if doc["byears"] == birth_year:
                score += 5
            elif abs(doc["byears"] - birth_year) <= 2:
                score += 2
        if death_year and doc.get("dyears"):
            if doc["dyears"] == death_year:
                score += 5
            elif abs(doc["dyears"] - death_year) <= 2:
                score += 2

        # Prefer entries with articles
        if doc.get("r_adb"):
            score += 1
        if doc.get("r_ndb"):
            score += 1

        if score > best_score:
            best_score = score
            best_doc = doc

    # Require minimum match quality to avoid false positives
    # A good match (both first+last name) scores ~14+, a partial match ~7
    min_score = 8 if len(target_parts) >= 2 else 5
    if best_score < min_score:
        return None

    return best_doc


def search_person_by_gnd(gnd_id: str) -> Optional[Dict[str, Any]]:
    """Look up a person by their GND identifier."""
    docs = _solr_query(f"defgnd:{gnd_id}", rows=1)
    return docs[0] if docs else None


# ---------------------------------------------------------------------------
# Data extraction
# ---------------------------------------------------------------------------


def _extract_metadata(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Extract CC0-licensed metadata fields from a Solr document."""
    metadata: Dict[str, Any] = {}

    # Birth
    birth: Dict[str, Any] = {}
    if doc.get("bdisplay"):
        birth["date"] = doc["bdisplay"].strip()
    if doc.get("byears"):
        birth["year"] = doc["byears"]
    if doc.get("r_bpl"):
        birth["place"] = _first(doc["r_bpl"])
    if doc.get("r_bpl_geo"):
        coords = _parse_geo(_first(doc["r_bpl_geo"]))
        if coords:
            birth["coordinates"] = coords
    if birth:
        metadata["birth"] = birth

    # Death
    death: Dict[str, Any] = {}
    if doc.get("ddisplay"):
        death["date"] = doc["ddisplay"].strip()
    if doc.get("dyears"):
        death["year"] = doc["dyears"]
    if doc.get("r_dpl"):
        death["place"] = _first(doc["r_dpl"])
    if doc.get("r_dpl_geo"):
        coords = _parse_geo(_first(doc["r_dpl_geo"]))
        if coords:
            death["coordinates"] = coords
    if death:
        metadata["death"] = death

    # Professions / roles
    if doc.get("r_ber"):
        metadata["professions"] = doc["r_ber"]

    # Brief summary
    if doc.get("r_bls"):
        metadata["brief_summary"] = (
            doc["r_bls"] if isinstance(doc["r_bls"], str) else "; ".join(doc["r_bls"])
        )

    # Work places
    if doc.get("r_wpl"):
        metadata["work_places"] = doc["r_wpl"]

    # Religion
    if doc.get("r_rel"):
        metadata["religion"] = _first(doc["r_rel"])

    # Relationships (from allbez or bez)
    relationships = []
    for entry in doc.get("allbez", doc.get("bez", [])):
        if isinstance(entry, str):
            relationships.append(entry)
    if relationships:
        metadata["relationships"] = relationships

    # External identifiers
    identifiers: Dict[str, str] = {}
    if doc.get("defgnd"):
        identifiers["gnd"] = str(doc["defgnd"])
    if doc.get("viaf"):
        identifiers["viaf"] = _first(doc["viaf"])
    if doc.get("isni"):
        identifiers["isni"] = _first(doc["isni"])
    if identifiers:
        metadata["identifiers"] = identifiers

    return metadata


def _determine_license(
    doc: Dict[str, Any],
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Determine article license and extract usable text.

    Returns (article_text, license, source):
      - article_text: full text if license allows, else None
      - license: "CC-BY-NC-SA" | "CC-BY-NC-ND" | None
      - source: "ADB" | "NDB" | None
    """
    has_adb = bool(doc.get("r_adb"))
    has_ndb = bool(doc.get("r_ndb"))
    adb_text = doc.get("a_le")
    ndb_text = doc.get("n_le")

    # Prefer ADB (more permissive license)
    if has_adb and adb_text:
        text = adb_text if isinstance(adb_text, str) else "\n".join(adb_text)
        return text, "CC-BY-NC-SA", "ADB"

    if has_ndb and ndb_text:
        # NDB text exists but is CC-BY-NC-ND — NOT included
        return None, "CC-BY-NC-ND", "NDB"

    return None, None, None


# ---------------------------------------------------------------------------
# Main fetch function
# ---------------------------------------------------------------------------


def fetch_deutsche_biographie(
    person_name: str,
    person_id: str,
    birth_year: Optional[int] = None,
    death_year: Optional[int] = None,
    gnd_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Fetch Deutsche Biographie data for a person.

    Args:
        person_name: Person's name (e.g. "Albert Einstein")
        person_id: Internal person_id for caching
        birth_year: Optional birth year for disambiguation
        death_year: Optional death year for disambiguation
        gnd_id: Optional GND identifier for direct lookup

    Returns:
        Structured dict with metadata and (if license allows) article text,
        or None if person not found.
    """
    # Try GND lookup first (most precise)
    doc = None
    if gnd_id:
        doc = search_person_by_gnd(gnd_id)

    # Fall back to name search
    if doc is None:
        doc = search_person(person_name, birth_year=birth_year, death_year=death_year)

    if doc is None:
        return None

    sfz_id = doc.get("id", "")
    gnd = str(doc.get("defgnd", ""))

    # Extract metadata (CC0)
    metadata = _extract_metadata(doc)

    # Determine license and extract usable text
    article_text, article_license, article_source = _determine_license(doc)

    # Genealogy text from n_ge (part of NDB article, same license as n_le)
    # Only include if from ADB context
    genealogy_text = None
    if doc.get("r_adb") and doc.get("a_ge"):
        genealogy_text = (
            doc["a_ge"] if isinstance(doc["a_ge"], str) else "\n".join(doc["a_ge"])
        )
    # n_ge is NDB-licensed, so we skip it

    result: Dict[str, Any] = {
        "sfz_id": sfz_id,
        "gnd_id": gnd,
        "name": doc.get("defnam", person_name),
        "url": f"{BASE_URL}/{sfz_id}.html" if sfz_id else None,
        "metadata": metadata,
        "article_text": article_text,
        "article_license": article_license,
        "article_source": article_source,
    }

    if genealogy_text:
        result["genealogy_text"] = genealogy_text

    return result


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------


def get_cache_path(person_id: str) -> Path:
    """Get the cache file path for Deutsche Biographie data."""
    return PEOPLE_DIR / person_id / "_cache" / CACHE_FILENAME


def cache_deutsche_biographie(person_id: str, data: Dict[str, Any]) -> Path:
    """Save Deutsche Biographie data to cache."""
    path = get_cache_path(person_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return path


def get_cached_deutsche_biographie(person_id: str) -> Optional[Dict[str, Any]]:
    """Load Deutsche Biographie data from cache, or None if not cached."""
    path = get_cache_path(person_id)
    if not path.exists():
        return None
    try:
        return cast(
            Optional[Dict[str, Any]], json.loads(path.read_text(encoding="utf-8"))
        )
    except (json.JSONDecodeError, OSError):
        return None


def ensure_deutsche_biographie_cache(
    person_id: str,
    person_name: str,
    birth_year: Optional[int] = None,
    death_year: Optional[int] = None,
    gnd_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Ensure DB cache exists; fetch if missing. Returns cached data or None."""
    cached = get_cached_deutsche_biographie(person_id)
    if cached is not None:
        return cached

    print(f"  - Fetching Deutsche Biographie for '{person_name}'...")
    data = fetch_deutsche_biographie(
        person_name,
        person_id,
        birth_year=birth_year,
        death_year=death_year,
        gnd_id=gnd_id,
    )

    if data is None:
        print("    Not found in Deutsche Biographie")
        # Cache a "not found" marker to avoid repeated lookups
        marker = {"not_found": True, "searched_name": person_name}
        cache_deutsche_biographie(person_id, marker)
        return None

    license_info = data.get("article_license")
    source = data.get("article_source")
    has_text = data.get("article_text") is not None
    text_len = len(data["article_text"]) if has_text else 0

    if has_text:
        print(
            f"    Found: {data['name']} ({source}, {license_info}, {text_len} chars of article text)"
        )
    elif license_info == "CC-BY-NC-ND":
        print(
            f"    Found: {data['name']} ({source}, {license_info} — article text excluded, metadata only)"
        )
    else:
        print(f"    Found: {data['name']} (metadata only, no article text available)")

    cache_deutsche_biographie(person_id, data)
    return data


# ---------------------------------------------------------------------------
# Prompt formatting
# ---------------------------------------------------------------------------


def format_for_prompt(data: Dict[str, Any]) -> Optional[str]:
    """Format Deutsche Biographie data for inclusion in an AI prompt.

    Returns a formatted text block, or None if only a 'not found' marker.
    """
    if not data or data.get("not_found"):
        return None

    lines = []
    lines.append("=" * 60)
    lines.append("DEUTSCHE BIOGRAPHIE — Additional biographical source")
    lines.append("=" * 60)

    name = data.get("name", "Unknown")
    url = data.get("url", "")
    lines.append(f"Person: {name}")
    if url:
        lines.append(f"URL: {url}")

    # License info
    article_license = data.get("article_license")
    article_source = data.get("article_source")
    if article_license:
        lines.append(f"Article source: {article_source} (License: {article_license})")

    # Metadata section (CC0)
    metadata = data.get("metadata", {})
    if metadata:
        lines.append("")
        lines.append("METADATA (CC0 — dates, places, professions, relationships):")
        lines.append("-" * 40)

        if "birth" in metadata:
            b = metadata["birth"]
            birth_str = f"Born: {b.get('date', b.get('year', '?'))}"
            if b.get("place"):
                birth_str += f" in {b['place']}"
            lines.append(birth_str)

        if "death" in metadata:
            d = metadata["death"]
            death_str = f"Died: {d.get('date', d.get('year', '?'))}"
            if d.get("place"):
                death_str += f" in {d['place']}"
            lines.append(death_str)

        if "professions" in metadata:
            lines.append(f"Professions: {', '.join(metadata['professions'])}")

        if "brief_summary" in metadata:
            lines.append(f"Summary: {metadata['brief_summary']}")

        if "work_places" in metadata:
            lines.append(f"Work places: {', '.join(metadata['work_places'])}")

        if "relationships" in metadata:
            lines.append(f"Relationships: {len(metadata['relationships'])} connections")
            for rel in metadata["relationships"][:20]:
                lines.append(f"  - {rel}")

    # Article text (only if license allows)
    article_text = data.get("article_text")
    if article_text:
        lines.append("")
        lines.append(f"BIOGRAPHICAL ARTICLE ({article_source}, {article_license}):")
        lines.append("-" * 40)
        lines.append(article_text)
    elif article_license == "CC-BY-NC-ND":
        lines.append("")
        lines.append(
            f"NOTE: Biographical article exists ({article_source}) but is licensed as"
        )
        lines.append(f"{article_license} (no derivatives). Article text NOT included.")
        lines.append("Only CC0 metadata above is available for use.")

    # Genealogy
    if data.get("genealogy_text"):
        lines.append("")
        lines.append("GENEALOGY:")
        lines.append("-" * 40)
        lines.append(data["genealogy_text"])

    lines.append("")
    lines.append("END OF DEUTSCHE BIOGRAPHIE DATA")
    lines.append("=" * 60)

    return "\n".join(lines)
