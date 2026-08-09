#!/usr/bin/env python3
"""Compare the events two people in the corpus lived together.

Person generation is per-person by construction: ``generate_person_events.py``
reads one subject's cached articles and never looks at the datasets already in
``data/people/``. Two records of one wedding, battle, or coronation are
therefore written independently and never compared, and the corpus can tell the
same event differently depending on which slide the reader is standing on.

Two events are treated as candidates for the same occasion when they name a
participant in common — or name each other's subject — and fall within a year
of each other. Candidates are printed for a human to scan; there is no way to
decide deterministically whether "Makes the Case for Constitution" and
"Presides Over Constitutional Convention" are one occasion or two.

``--check`` reports only the shape that is a contradiction rather than a
judgment: two candidates that name the same primary place and whose dates
cannot both be true — periods that do not overlap once each date is read at its
own precision. That is what a coronation recorded on two different days looks
like. A pair matching that shape and still correct belongs in ACCEPTED below.

Usage:
    python scripts/validate_cross_person_events.py            # scan list
    python scripts/validate_cross_person_events.py --check    # exit 1 on a contradiction
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
PEOPLE_DIR = REPO_ROOT / "data" / "people"

# Pairs that share a place and a participant, cannot both be true as dated, and
# are nonetheless two separate occasions. Keyed by both people and both dates,
# with the reason. Empty today: every pair the corpus holds that meets one half
# of the shape survives the other half, mostly because an event that spans a
# range is dated as a range and overlaps its neighbour honestly.
ACCEPTED: Dict[Tuple[str, str, str, str], str] = {
    ("claus_schenk_graf_von_stauffenberg", "1944-07-01", "max_planck", "1945-01-23"): (
        "Stauffenberg's staff appointment and Erwin Planck's execution are"
        " separate occasions; they share Berlin and Hitler through the plot."
    ),
    ("claus_schenk_graf_von_stauffenberg", "1944-07-20", "max_planck", "1945-01-23"): (
        "The assassination attempt and Erwin Planck's execution for his part"
        " in it are separate occasions months apart."
    ),
}

WITHIN_YEARS = 1


def period(
    date_str: str, precision: Optional[str]
) -> Optional[Tuple[datetime, datetime]]:
    """The instants a date covers, read at its own precision — as the app reads it."""
    parts = (date_str or "").split("-")
    if not parts or not parts[0].isdigit():
        return None
    year = int(parts[0])
    level = (precision or "day").lower()
    try:
        if level == "year" or len(parts) == 1:
            return datetime(year, 1, 1), datetime(year + 1, 1, 1)
        month = int(parts[1])
        if level == "month" or len(parts) == 2:
            end = (
                datetime(year + 1, 1, 1)
                if month == 12
                else datetime(year, month + 1, 1)
            )
            return datetime(year, month, 1), end
        start = datetime(year, month, int(parts[2]))
        return start, start + timedelta(days=1)
    except (ValueError, IndexError):
        return None


def event_period(event: Dict[str, Any]) -> Optional[Tuple[datetime, datetime]]:
    start = period(event.get("date") or "", event.get("date_precision"))
    if start is None:
        return None
    end_date = event.get("date_end")
    if isinstance(end_date, str) and end_date:
        end = period(
            end_date, event.get("date_end_precision") or event.get("date_precision")
        )
        if end is not None:
            return start[0], max(start[1], end[1])
    return start


def primary_place(event: Dict[str, Any]) -> Optional[str]:
    locations = event.get("locations") or []
    chosen = next((loc for loc in locations if loc.get("primary")), None)
    if chosen is None and locations:
        chosen = locations[0]
    if not isinstance(chosen, dict):
        return None
    name = chosen.get("name_historic") or chosen.get("name_modern")
    return name.strip().lower() if isinstance(name, str) else None


def display_name(person_id: str, data: Dict[str, Any]) -> str:
    name = (data.get("person") or {}).get("name") or person_id
    return name.replace("_", " ")


def participants(event: Dict[str, Any]) -> Set[str]:
    return {
        name.strip()
        for name in (event.get("involved_people") or [])
        if isinstance(name, str) and name.strip()
    }


def names_subject(event: Dict[str, Any], subject: str) -> bool:
    """Whether an event names the other dataset's subject among its participants."""
    surname = subject.split()[-1].lower()
    return any(
        person.lower() == subject.lower()
        or (
            len(surname) > 3
            and person.lower().startswith(subject.split()[0].lower())
            and surname in person.lower()
        )
        for person in participants(event)
    )


class Candidate:
    def __init__(
        self,
        person_a: str,
        event_a: Dict[str, Any],
        person_b: str,
        event_b: Dict[str, Any],
        shared: Set[str],
    ):
        self.person_a = person_a
        self.person_b = person_b
        self.event_a = event_a
        self.event_b = event_b
        self.shared = shared

    @property
    def key(self) -> Tuple[str, str, str, str]:
        return (
            self.person_a,
            self.event_a.get("date") or "?",
            self.person_b,
            self.event_b.get("date") or "?",
        )

    @property
    def same_place(self) -> bool:
        place_a, place_b = primary_place(self.event_a), primary_place(self.event_b)
        return place_a is not None and place_a == place_b

    @property
    def dates_can_both_be_true(self) -> bool:
        span_a, span_b = event_period(self.event_a), event_period(self.event_b)
        if span_a is None or span_b is None:
            return True
        return span_a[0] < span_b[1] and span_b[0] < span_a[1]

    @property
    def contradicts(self) -> bool:
        return self.same_place and not self.dates_can_both_be_true

    def __str__(self) -> str:
        return (
            f'{self.person_a} {self.event_a.get("date")} "{self.event_a.get("title")}"'
            f' | {self.person_b} {self.event_b.get("date")} "{self.event_b.get("title")}"'
            f' | {primary_place(self.event_a) or "-"} / {primary_place(self.event_b) or "-"}'
            f' | shared: {", ".join(sorted(self.shared)) or "-"}'
        )


def find_candidates(people: Dict[str, Dict[str, Any]]) -> List[Candidate]:
    names = {pid: display_name(pid, data) for pid, data in people.items()}
    candidates: List[Candidate] = []
    for person_a, person_b in itertools.combinations(sorted(people), 2):
        for event_a in people[person_a].get("events") or []:
            span_a = event_period(event_a)
            for event_b in people[person_b].get("events") or []:
                span_b = event_period(event_b)
                if span_a is None or span_b is None:
                    continue
                if abs(span_a[0].year - span_b[0].year) > WITHIN_YEARS:
                    continue
                shared = participants(event_a) & participants(event_b)
                mutual = names_subject(event_a, names[person_b]) and names_subject(
                    event_b, names[person_a]
                )
                if shared or mutual:
                    candidates.append(
                        Candidate(person_a, event_a, person_b, event_b, shared)
                    )
    return candidates


def load_people(person_ids: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    wanted = set(person_ids)
    people: Dict[str, Dict[str, Any]] = {}
    for path in sorted(PEOPLE_DIR.glob("*/life_events.json")):
        person_id = path.parent.name
        if wanted and person_id not in wanted:
            continue
        people[person_id] = json.loads(path.read_text(encoding="utf-8"))
    return people


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "person_ids", nargs="*", help="Restrict to these person ids (default: all)"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 when two records of one occasion cannot both be true",
    )
    args = parser.parse_args(argv)

    people = load_people(args.person_ids)
    candidates = find_candidates(people)
    contradictions = [c for c in candidates if c.contradicts and c.key not in ACCEPTED]

    if args.check:
        for candidate in contradictions:
            print(f"ERROR: same place, dates that cannot both be true\n  {candidate}")
        print(
            f"\nCompared {len(people)} person dataset(s), {len(candidates)} shared "
            f"occasion(s) considered, {len(contradictions)} contradiction(s)."
        )
        return 1 if contradictions else 0

    for candidate in candidates:
        mark = (
            "!!"
            if candidate.contradicts
            else ("  " if candidate.dates_can_both_be_true else " ~")
        )
        print(f"{mark} {candidate}")
    print(
        f"\nCompared {len(people)} person dataset(s), {len(candidates)} shared "
        f"occasion(s) to scan."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
