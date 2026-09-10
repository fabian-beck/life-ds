#!/usr/bin/env python3
"""Check that English event titles are actually written in English.

An event title is written once, in the proposal, and nothing downstream revisits it:
the research schema carries no title field, so a title that came back half in
German stays that way. The translation step then renders it into idiomatic
German, which is why the German corpus reads correctly while the English one
keeps the odd German preposition or place name — the defect is only visible in
the language nobody re-reads.

The two shapes this catches:

  - a German function word left standing in an otherwise English title, which
    is what happens when the model translates around a German work title
    instead of translating it ("Wolf under Wolfen published")
  - a city written the German way where English has its own established name
    ("Warschau" for Warsaw, "Zurich" spelled with the umlaut)

Quoted text is exempt: a German work title in quotation marks is quoted, not
mistranslated, and the corpus deliberately keeps those. A lowercase particle
between two capitalized words ("Nina von Lerchenfeld") is part of a personal
name rather than a preposition. What survives both exemptions and is still
correct as written belongs in ACCEPTED below, with the reason.

Usage:
    python scripts/validate_event_titles.py
    python scripts/validate_event_titles.py emmy_noether
    python scripts/validate_event_titles.py --verbose
"""

from __future__ import annotations

import re
import sys
from typing import Any, Dict, List, Optional, Tuple

from config import PEOPLE_DIR  # noqa: F401  (re-exported for the tests)
from utils.validation import run_dataset_check

# German function words that no English title has a reason to contain. Matched
# lowercase only, so "Das" opening a German work title and the acronym "MIT"
# are both left alone.
GERMAN_FUNCTION_WORDS = (
    "und",
    "unter",
    "über",
    "der",
    "die",
    "das",
    "den",
    "dem",
    "des",
    "ein",
    "eine",
    "einen",
    "einem",
    "eines",
    "für",
    "von",
    "vom",
    "zum",
    "zur",
    "aus",
    "mit",
    "nach",
    "bei",
    "beim",
    "auf",
    "ins",
    "als",
    "wird",
    "werden",
    "durch",
    "gegen",
    "ohne",
)

# Cities whose English name is established and different. Historic German names
# for places that later changed country (Danzig, Breslau, Königsberg) are left
# out on purpose: English uses those too when writing about the period.
GERMAN_CITY_NAMES = {
    "Warschau": "Warsaw",
    "München": "Munich",
    "Köln": "Cologne",
    "Wien": "Vienna",
    "Zürich": "Zurich",
    "Nürnberg": "Nuremberg",
    "Prag": "Prague",
    "Genf": "Geneva",
    "Mailand": "Milan",
    "Rom": "Rome",
    "Moskau": "Moscow",
    "Kopenhagen": "Copenhagen",
    "Florenz": "Florence",
    "Venedig": "Venice",
    "Lissabon": "Lisbon",
    "Neapel": "Naples",
    "Athen": "Athens",
    "Brüssel": "Brussels",
    "Antwerpen": "Antwerp",
    "Braunschweig": "Brunswick",
    "Bukarest": "Bucharest",
    "Belgrad": "Belgrade",
    "Krakau": "Krakow",
    "Straßburg": "Strasbourg",
    "Lüttich": "Liège",
    "Den Haag": "The Hague",
}

# Titles that trip a rule above and are nonetheless right as written. Keyed by
# person id so a title moving to another dataset is looked at again.
ACCEPTED: Dict[str, Tuple[str, ...]] = {
    # The name of the company Nixdorf founded, not a description of it.
    "heinz_nixdorf": ("Founds Labor für Impulstechnik",),
    # Noddack's monograph, carried untranslated the way the corpus carries
    # every other German work title.
    "ida_noddack": ("Published Das Rhenium",),
}

QUOTED_TEXT = re.compile(r"[\"“”„»«'’][^\"“”„»«'’]*[\"“”„»«'’]")
FUNCTION_WORD = re.compile(
    r"(?<![\w-])(" + "|".join(GERMAN_FUNCTION_WORDS) + r")(?![\w-])"
)
NAME_PARTICLE = re.compile(
    r"\b[A-ZÄÖÜ][\wäöüß-]*\s+(von|van|vom|zu|zur|de|der)\s+[A-ZÄÖÜ]"
)


class TitleFinding:
    def __init__(self, person_id: str, date: str, title: str, message: str):
        self.person_id = person_id
        self.date = date
        self.title = title
        self.message = message

    def __str__(self) -> str:
        return f'{self.person_id} {self.date} "{self.title}": {self.message}'


def _strip_exempt_spans(title: str) -> str:
    """Blank out the parts of a title a German word may legitimately occupy."""
    masked = QUOTED_TEXT.sub(lambda m: " " * len(m.group(0)), title)
    while True:
        match = NAME_PARTICLE.search(masked)
        if match is None:
            return masked
        start, end = match.span(1)
        masked = masked[:start] + " " * (end - start) + masked[end:]


def check_title(person_id: str, date: str, title: str) -> List[TitleFinding]:
    if title in ACCEPTED.get(person_id, ()):
        return []

    findings: List[TitleFinding] = []
    searchable = _strip_exempt_spans(title)

    for match in FUNCTION_WORD.finditer(searchable):
        findings.append(
            TitleFinding(
                person_id,
                date,
                title,
                f"German function word '{match.group(1)}' in an English title",
            )
        )

    for german, english in GERMAN_CITY_NAMES.items():
        if re.search(rf"(?<![\w-]){re.escape(german)}(?![\w-])", searchable):
            findings.append(
                TitleFinding(
                    person_id,
                    date,
                    title,
                    f"German city name '{german}' — English writes '{english}'",
                )
            )

    return findings


def check_person(person_id: str, data: Dict[str, Any]) -> List[TitleFinding]:
    findings: List[TitleFinding] = []
    for event in data.get("events") or []:
        title = event.get("title")
        if not isinstance(title, str):
            continue
        findings.extend(check_title(person_id, event.get("date") or "?", title))
    return findings


def main(argv: Optional[List[str]] = None) -> int:
    return run_dataset_check(check_person, description=__doc__, argv=argv)


if __name__ == "__main__":
    sys.exit(main())
