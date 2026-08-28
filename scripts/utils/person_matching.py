"""The interface's person-name matching, ported for the generation side.

``getRelevantPeople`` in ``src/utils/story/personMatching.js`` decides which
network connections an event's ``involved_people`` resolve to, and that
decision feeds both the person chips and the deep-event selection. This module
is a faithful port of its name normalization and scoring; keep the two in sync
when the matcher changes. ``scripts/validate_involved_names.py`` holds the
port to the corpus, and ``scripts/utils/event_depth.py`` selects deep events
with it.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

MATCH_THRESHOLD = 0.6

PARENTHETICAL = re.compile(r"\s*\([^)]*\)")
HYPHENS = re.compile(r"[‐‑‒–—−]")
MAIDEN = re.compile(r"\(\s*(?:née|nee|born|geborene|geb\.?)\s+([^)]+)\)", re.I)
BRACKETED = re.compile(r"\s*\[[^\]]*\]")
COMMA_TITLE = re.compile(
    r",\s*(Holy Roman Emperor|Holy Roman Empress|King|Queen|Emperor|Empress"
    r"|Duke|Duchess|Count|Countess|Prince|Princess|Bishop|Archbishop|Pope"
    r"|Saint|Dr\.|Prof\.).*$",
    re.I,
)
SUFFIX = re.compile(r"\s+(Jr|Sr)\.?$", re.I)
TITLE_OF_PLACE = re.compile(
    r",?\s*(Count|Duke|Duchess|Bishop|Archbishop|King|Queen|Prince|Princess"
    r"|Emperor|Empress|Lord|Lady|Earl|Baron|Baroness|Margrave|Landgrave"
    r"|Elector)\s+of\s+[\w\s-]+$",
    re.I,
)
OF_PLACE = re.compile(r"^(.+?)\s+of\s+([\w\s-]+)$", re.I)
ROMAN = re.compile(r"^(I{1,3}|IV|V|VI{0,3}|IX|X|XI{0,3}|XIV|XV)$", re.I)
NAME_PARTICLES = ["von", "van", "de", "del", "della", "di"]


def normalize_person_name(name: str) -> Optional[Dict[str, Any]]:
    normalized = HYPHENS.sub("-", name.strip())
    maiden_match = MAIDEN.search(normalized)
    maiden = maiden_match.group(1).strip() if maiden_match else None
    normalized = PARENTHETICAL.sub("", normalized)
    normalized = BRACKETED.sub("", normalized)
    normalized = COMMA_TITLE.sub("", normalized)
    normalized = SUFFIX.sub("", normalized)
    normalized = TITLE_OF_PLACE.sub("", normalized)
    of_place = OF_PLACE.match(normalized)
    tokens = normalized.split()
    if not tokens:
        return None
    particle_index = next(
        (i for i, t in enumerate(tokens) if t.lower() in NAME_PARTICLES), -1
    )
    if of_place:
        name_tokens = of_place.group(1).split()
        if not name_tokens:
            return None
        last_name = name_tokens[-1]
        first_names = name_tokens[:-1]
    elif 0 <= particle_index < len(tokens) - 1:
        last_name = " ".join(tokens[particle_index:])
        first_names = tokens[:particle_index]
    else:
        last_name = tokens[-1]
        first_names = tokens[:-1]
    return {
        "fullName": normalized,
        "firstName": first_names[0] if first_names else "",
        "lastName": last_name,
        "maidenName": maiden,
        "tokens": [t.lower() for t in tokens],
    }


def interface_score(
    name1: Optional[Dict[str, Any]], name2: Optional[Dict[str, Any]]
) -> float:
    if not name1 or not name2:
        return 0.0
    if name1["fullName"].lower() == name2["fullName"].lower():
        return 1.0
    score = 0.0
    first1, first2 = name1["firstName"].lower(), name2["firstName"].lower()
    first_match = bool(first1) and first1 == first2
    last1, last2 = name1["lastName"].lower(), name2["lastName"].lower()
    last1_roman, last2_roman = bool(ROMAN.match(last1)), bool(ROMAN.match(last2))
    last_match = bool(last1) and not last1_roman and not last2_roman and last1 == last2
    last_contained = (
        bool(last1)
        and bool(last2)
        and not last1_roman
        and not last2_roman
        and (last1 in last2 or last2 in last1)
    )
    roman1 = next((t for t in name1["tokens"] if ROMAN.match(t)), None)
    roman2 = next((t for t in name2["tokens"] if ROMAN.match(t)), None)
    if roman1 and roman2:
        if roman1.upper() != roman2.upper():
            return 0.0
        if not first_match:
            return 0.0
        score += 0.5
    if first_match:
        score += 0.4
    if last_match:
        score += 0.4
    elif last_contained and len(last1) > 3 and len(last2) > 3:
        score += 0.2
    full1, full2 = name1["fullName"].lower(), name2["fullName"].lower()
    if full1 in full2 or full2 in full1:
        score += 0.2
    maiden1 = (name1["maidenName"] or "").lower()
    maiden2 = (name2["maidenName"] or "").lower()
    if first_match:
        if maiden1 and last2 == maiden1:
            score += 0.4
        elif maiden2 and last1 == maiden2:
            score += 0.4
    return min(score, 0.95)


def interface_would_match(involved: str, connection: str) -> bool:
    return (
        interface_score(
            normalize_person_name(involved), normalize_person_name(connection)
        )
        >= MATCH_THRESHOLD
    )
