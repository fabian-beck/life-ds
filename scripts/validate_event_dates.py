#!/usr/bin/env python3
"""Check that an event's date agrees with the year its own description states.

The proposal produces the date, the precision, and the description in one call, and
nothing downstream can revise the date: the research schema carries no date
field, so when the research disagrees the disagreement can only land in
the prose. The reader then sees the date on the slide and a contradicting year
in the sentence directly beneath it.

The chronological check the generator already runs compares each event to its
neighbours, so a wrong year that preserves the ordering passes silently — which
is the shape every case of this defect has had.

What this checks is narrow on purpose. Only the description's FIRST sentence is
read, because that is the sentence that states the event; later sentences carry
context whose years are legitimately outside it (a parent's emigration, a
building's competition, an exhibition's tour). A year there that falls outside
the event's own span — `date` through `date_end` — contradicts the date.

Years are read the way a reader reads them: a decade ("the 1950s") is not a
year, a life span in parentheses ("Anna Freud Bernays (1858-1955)") belongs to
somebody else, and a range ("the winter of 1779-1780") covers every year it
names. A first sentence whose context year is nonetheless correct belongs in
ACCEPTED below, with the reason.

Usage:
    python scripts/validate_event_dates.py
    python scripts/validate_event_dates.py alvar_aalto
    python scripts/validate_event_dates.py --verbose
"""

from __future__ import annotations

import re
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

from config import PEOPLE_DIR  # noqa: F401  (re-exported for the tests)
from utils.validation import run_dataset_check

# Events whose opening sentence names a year outside the event's span and is
# right to. Keyed by person id and event date so a re-dated event is looked at
# again.
ACCEPTED: Dict[Tuple[str, str], str] = {
    ("alan_turing", "1954-06-07"): (
        "The 1952 conviction and its hormone treatment, which the death "
        "description reaches back over."
    ),
    ("alvar_aalto", "1935"): "The 1927 competition the completed library came out of.",
    ("antoni_gaud", "1886"): "The 1878 exhibition where Gaudí and Güell met.",
    ("max_planck", "1919"): "The reserved 1918 prize, awarded to Planck in 1919.",
    ("zaha_hadid", "2011"): "The 2012 Olympic Games the centre was completed for.",
}

ANNOTATION = re.compile(r"\[\[([^\]|]+)\|([^\]]+)\]\]|\[\[([^\]]+)\]\]")
PARENTHETICAL = re.compile(r"\([^)]*\)")
SENTENCE_BREAK = re.compile(r"(?<=[.!?])[\s\n]")
YEAR = r"1[0-9]{3}|20[0-9]{2}"
DECADE = re.compile(rf"(?<!\d)({YEAR})s(?!\w)")
YEAR_RANGE = re.compile(rf"(?<!\d)({YEAR})\s*[-–—]\s*({YEAR}|[0-9]{{2}})(?!\d)")
SINGLE_YEAR = re.compile(rf"(?<!\d)({YEAR})(?!\d)")


class DateFinding:
    def __init__(self, person_id: str, event: Dict[str, Any], years: List[int]):
        self.person_id = person_id
        self.date = event.get("date") or "?"
        self.date_end = event.get("date_end")
        self.title = event.get("title") or "?"
        self.years = years

    def __str__(self) -> str:
        span = self.date if not self.date_end else f"{self.date}..{self.date_end}"
        named = ", ".join(str(y) for y in self.years)
        return (
            f'{self.person_id} {span} "{self.title}": the description opens on '
            f"{named}, outside the event's own date"
        )


def first_sentence(description: str) -> str:
    """The sentence that states the event, with markup and asides removed."""
    plain = ANNOTATION.sub(lambda m: m.group(2) or m.group(3), description)
    plain = PARENTHETICAL.sub(" ", plain)
    return SENTENCE_BREAK.split(plain.strip(), 1)[0]


def years_named(text: str) -> List[int]:
    """Every year the text asserts, ranges expanded and decades left out."""
    remaining = DECADE.sub(" ", text)
    years: Set[int] = set()

    def take_range(match: re.Match[str]) -> str:
        start = int(match.group(1))
        end_text = match.group(2)
        end = int(end_text) if len(end_text) == 4 else int(str(start)[:2] + end_text)
        if end >= start and end - start <= 100:
            years.update(range(start, end + 1))
        else:
            years.update({start, end})
        return " "

    remaining = YEAR_RANGE.sub(take_range, remaining)
    years.update(int(m.group(1)) for m in SINGLE_YEAR.finditer(remaining))
    return sorted(years)


def event_span(event: Dict[str, Any]) -> Optional[Tuple[int, int]]:
    date = event.get("date")
    if not isinstance(date, str) or len(date) < 4 or not date[:4].isdigit():
        return None
    start = int(date[:4])
    end_date = event.get("date_end")
    end = start
    if isinstance(end_date, str) and len(end_date) >= 4 and end_date[:4].isdigit():
        end = max(start, int(end_date[:4]))
    return start, end


def check_event(person_id: str, event: Dict[str, Any]) -> List[DateFinding]:
    if (person_id, event.get("date")) in ACCEPTED:
        return []
    description = event.get("description")
    span = event_span(event)
    if not isinstance(description, str) or span is None:
        return []
    years = years_named(first_sentence(description))
    if not years:
        return []
    start, end = span
    if any(start <= year <= end for year in years):
        return []
    return [DateFinding(person_id, event, years)]


def check_person(person_id: str, data: Dict[str, Any]) -> List[DateFinding]:
    findings: List[DateFinding] = []
    for event in data.get("events") or []:
        findings.extend(check_event(person_id, event))
    return findings


def main(argv: Optional[List[str]] = None) -> int:
    return run_dataset_check(check_person, description=__doc__, argv=argv)


if __name__ == "__main__":
    sys.exit(main())
