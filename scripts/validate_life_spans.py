#!/usr/bin/env python3
"""Check the years the data gives people against the spans their sources state.

The cached Wikipedia articles write life spans in parentheses — "Karl
(1888–1916)", "Albert Einstein (1879–1955)" — and the generator reads those
articles, yet nothing afterwards holds it to them: Planck's son Karl fell at
Verdun in 1916 with the span on the prompt's own page, and the dataset shipped
"killed at Verdun in 1917" in the event prose and ``end_year: 1917`` in the
network. The chronological check orders events against each other, and
``validate_event_dates.py`` reads an event's first sentence against its own
date; neither can see a wrong year attached to a *different* person.

This check is deterministic and runs only as far as the evidence goes. It
collects every parenthesised span from the person's ``_cache`` — the main
article in both languages and the related articles — and verifies two things
against them:

- **Network years.** A connection whose name carries a span in the sources
  must not end after that person's death or start before their birth. The
  generator writes death years as end years, so a mismatch is a wrong year,
  not a different convention.
- **Death sentences in event prose.** A sentence that says a named person
  died, fell, or was killed must name a year the sources give as that
  person's death year. Sentences naming several people and years pass when
  every year is someone's death year ("Grete and Emma died in 1917 and 1919").

A person without a cache — every machine but the one that generated them —
produces no findings, so the check is a generation-time gate: run it right
after generating or regenerating a person, while the cache that fed the
prompts is still on disk.

A finding that is right despite the sources belongs in ACCEPTED below, with
the reason.

Usage:
    python scripts/validate_life_spans.py
    python scripts/validate_life_spans.py max_planck
    python scripts/validate_life_spans.py --verbose
"""

from __future__ import annotations

import re
import sys
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from config import PEOPLE_DIR
from utils.json_io import read_json
from utils.validation import run_dataset_check

# Findings that are right despite the sources. Keyed by person id and the
# exact text the finding names (a connection's name or an event date), so a
# regenerated value is looked at again.
ACCEPTED: Dict[Tuple[str, str], str] = {}

# "Karl (1888–1916)", "Albert Einstein (14 March 1879 – 18 April 1955)" — a
# name directly before a parenthesised span, with or without days and months.
# Particles stay lowercase inside a name.
NAME_SPAN = re.compile(
    r"([A-ZÄÖÜ][\w'’.-]*(?:\s+(?:von|van|de|zu|da|of|the)\s+[A-ZÄÖÜ][\w'’.-]*"
    r"|\s+[A-ZÄÖÜ][\w'’.-]*)*)\s*"
    r"\(\s*(?:\d{1,2}\.?\s+[A-Za-zÄÖÜäöüé]+\s+)?(1[0-9]{3}|20[0-9]{2})"
    r"\s*[–—-]\s*(?:\d{1,2}\.?\s+[A-Za-zÄÖÜäöüé]+\s+)?(1[0-9]{3}|20[0-9]{2})\s*\)"
)

# The German lead's "(* 23. April 1858 in Kiel; † 4. Oktober 1947 in
# Göttingen)" — full dates, so the year-range pattern above cannot read it.
GERMAN_LEAD_SPAN = re.compile(
    r"([A-ZÄÖÜ][\w'’.-]*(?:\s+[A-ZÄÖÜ][\w'’.-]*)*)\s*"
    r"\(\*\s*[^;()]*?(1[0-9]{3}|20[0-9]{2})[^;()]*;\s*†[^()]*?(1[0-9]{3}|20[0-9]{2})"
)

SENTENCE_BREAK = re.compile(r"(?<=[.!?])[\s\n]")
ANNOTATION = re.compile(r"\[\[([^\]|]+)\|([^\]]+)\]\]|\[\[([^\]]+)\]\]")
DEATH_VERB = re.compile(r"\b(died|dies|death|killed|fell|executed|perished)\b")
YEAR = re.compile(r"(?<!\d)(1[0-9]{3}|20[0-9]{2})(?!\d)")
NAME_TOKEN = re.compile(r"[A-ZÄÖÜ][\w'’.-]+")

# Words a name never starts with, however capitalized the sentence leaves
# them. Keeps "During", "His", "The" out of the lookback window.
NOT_NAMES = {
    "After",
    "Although",
    "And",
    "At",
    "Before",
    "But",
    "During",
    "He",
    "Her",
    "His",
    "In",
    "It",
    "On",
    "She",
    "The",
    "Their",
    "They",
    "When",
    "While",
    "World",
    "War",
}

# A parenthesised range this short beside a name is a tenure or a reign as
# often as a life, and a range this long is a dynasty; neither is evidence
# about one person's years.
MIN_LIFE_SPAN = 15
MAX_LIFE_SPAN = 110


class SpanFinding:
    def __init__(self, person_id: str, where: str, claim: str, evidence: str):
        self.person_id = person_id
        self.where = where
        self.claim = claim
        self.evidence = evidence

    def __str__(self) -> str:
        return (
            f"{self.person_id} {self.where}: {self.claim}, "
            f"but the sources say {self.evidence}"
        )


def cache_texts(person_id: str) -> List[str]:
    """Every article text the generation prompts were built from."""
    cache_dir = PEOPLE_DIR / person_id / "_cache"
    texts: List[str] = []
    if not cache_dir.is_dir():
        return texts
    for path in sorted(cache_dir.glob("wikipedia_page*.json")):
        page = read_json(path)
        extract = page.get("extract") if isinstance(page, dict) else None
        if isinstance(extract, str):
            texts.append(extract)
    related = cache_dir / "related_articles.json"
    if related.exists():
        articles = read_json(related)
        if isinstance(articles, list):
            for article in articles:
                if not isinstance(article, dict):
                    continue
                for field in ("summary", "fullText"):
                    value = article.get(field)
                    if isinstance(value, str):
                        texts.append(value)
    return texts


def collect_spans(texts: Iterable[str]) -> Dict[str, Set[Tuple[int, int]]]:
    """Name → the life spans the sources attach to it, first names included."""
    spans: Dict[str, Set[Tuple[int, int]]] = {}

    def record(name: str, birth: int, death: int) -> None:
        if not MIN_LIFE_SPAN <= death - birth <= MAX_LIFE_SPAN:
            return
        tokens = name.split()
        while tokens and tokens[0] in NOT_NAMES:
            tokens = tokens[1:]
        if not tokens:
            return
        cleaned = " ".join(tokens)
        for key in {cleaned, tokens[0], tokens[-1]}:
            spans.setdefault(key, set()).add((birth, death))

    for text in texts:
        for match in NAME_SPAN.finditer(text):
            record(match.group(1), int(match.group(2)), int(match.group(3)))
        for match in GERMAN_LEAD_SPAN.finditer(text):
            record(match.group(1), int(match.group(2)), int(match.group(3)))
    return spans


def death_years_for(name: str, spans: Dict[str, Set[Tuple[int, int]]]) -> Set[int]:
    """The death years the sources offer for a name.

    Resolution stops at the most specific key that answers: the full name,
    then the first name, then the last. A union across all three would let
    the family name drown a first-name match — "Karl Planck" must resolve to
    Karl's own span, not to every Planck the articles date.
    """
    tokens = name.split()
    for key in (name, tokens[0], tokens[-1]):
        candidates = {death for _, death in spans.get(key, set())}
        if candidates:
            return candidates
    return set()


def check_network(
    person_id: str, spans: Dict[str, Set[Tuple[int, int]]]
) -> List[SpanFinding]:
    network_path = PEOPLE_DIR / person_id / "ego_network.json"
    if not network_path.exists():
        return []
    network = read_json(network_path)
    findings: List[SpanFinding] = []
    for connection in network.get("connections") or []:
        name = connection.get("person_name")
        if not isinstance(name, str) or not name or (person_id, name) in ACCEPTED:
            continue
        # For family, death years resolve through the first name too: the
        # articles write a relative as "Karl (1888–1916)" while the network
        # stores "Karl Planck". Everyone else stays exact-name-only — a bare
        # "Albert" in some article is not evidence about Albert Einstein.
        # Birth years are exact-name-only throughout, because a first name
        # shared across generations (mother and daughter Emma) offers the
        # wrong birth far more readily than the wrong death.
        relationship = connection.get("relationship_type") or ""
        if relationship.startswith("family/"):
            deaths = death_years_for(name, spans)
        else:
            deaths = {death for _, death in spans.get(name, set())}
        end_year = connection.get("end_year")
        if (
            deaths
            and isinstance(end_year, int)
            and all(end_year > death for death in deaths)
        ):
            named = ", ".join(str(d) for d in sorted(deaths))
            findings.append(
                SpanFinding(
                    person_id,
                    f'network "{name}"',
                    f"the connection ends in {end_year}",
                    f"{name} died in {named}",
                )
            )
        candidates = spans.get(name) or set()
        start_year = connection.get("start_year")
        if (
            candidates
            and isinstance(start_year, int)
            and all(start_year < birth for birth, _ in candidates)
        ):
            births = ", ".join(str(b) for b, _ in sorted(candidates))
            findings.append(
                SpanFinding(
                    person_id,
                    f'network "{name}"',
                    f"the connection starts in {start_year}",
                    f"{name} was born in {births}",
                )
            )
    return findings


def named_before(verb_start: int, sentence: str) -> List[str]:
    """The capitalized names in the clause directly before a death verb."""
    window = sentence[:verb_start]
    for breaker in (";", " but ", " which ", " who "):
        cut = window.rfind(breaker)
        if cut != -1:
            window = window[cut + len(breaker) :]
    tokens = NAME_TOKEN.findall(window[-80:])
    return [t for t in tokens if t not in NOT_NAMES]


def check_death_sentence(
    person_id: str,
    event: Dict[str, Any],
    sentence: str,
    spans: Dict[str, Set[Tuple[int, int]]],
) -> List[SpanFinding]:
    years = {int(y) for y in YEAR.findall(sentence)}
    if not years:
        return []
    findings: List[SpanFinding] = []
    seen: Set[str] = set()
    for verb in DEATH_VERB.finditer(sentence):
        for name in named_before(verb.start(), sentence):
            if name in seen:
                continue
            seen.add(name)
            candidates = death_years_for(name, spans)
            if not candidates or candidates & years:
                continue
            deaths = ", ".join(str(d) for d in sorted(candidates))
            named = ", ".join(str(y) for y in sorted(years))
            findings.append(
                SpanFinding(
                    person_id,
                    f'event {event.get("date")} "{event.get("title")}"',
                    f"a sentence has {name} dying, naming {named}",
                    f"{name} died in {deaths}",
                )
            )
    return findings


def check_events(
    person_id: str,
    data: Dict[str, Any],
    spans: Dict[str, Set[Tuple[int, int]]],
) -> List[SpanFinding]:
    findings: List[SpanFinding] = []
    for event in data.get("events") or []:
        if (person_id, str(event.get("date"))) in ACCEPTED:
            continue
        description = event.get("description")
        if not isinstance(description, str):
            continue
        plain = ANNOTATION.sub(lambda m: m.group(2) or m.group(3), description)
        for sentence in SENTENCE_BREAK.split(plain):
            findings.extend(check_death_sentence(person_id, event, sentence, spans))
    return findings


def check_person(person_id: str, data: Dict[str, Any]) -> List[SpanFinding]:
    spans = collect_spans(cache_texts(person_id))
    if not spans:
        return []
    return check_events(person_id, data, spans) + check_network(person_id, spans)


def main(argv: Optional[List[str]] = None) -> int:
    return run_dataset_check(check_person, description=__doc__, argv=argv)


if __name__ == "__main__":
    sys.exit(main())
