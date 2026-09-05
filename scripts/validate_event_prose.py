#!/usr/bin/env python3
"""Check the event prose against the description contract.

Every phase that writes a description reads the same definition of one
(``scripts/utils/prose_style.py``): it narrates one moment, it
asserts rather than weighs sources, and it stays at the slide's granularity.
Nothing downstream read the output for that register — the validators checked
titles, dates, chapters, names, Markdown, and links, and a description that was
accurate, sourced, and written like an encyclopedia's source apparatus passed
every one of them (issue #141). This reads for the three shapes the corpus
actually shipped:

  - a year later than the event's own span, anywhere in the description — the
    forward reference ("the family later moved to East Teignmouth in 1808" on
    a birth dated 1791); a span in parentheses is a person's dates, not a claim
    about the event, and is skipped
  - the language of weighing sources — "most likely", "is disputed", "according
    to", "some sources" — where the story should have committed to one telling
    and left the evidence to the sources list
  - a street address or house number, in the title or the prose, where the
    slide places the event at city level

It reports and never edits: a finding names a dataset for ``data/outdated.md``,
and a corpus count before and after a prompt change says whether the change
worked. A sentence that trips a rule and is nonetheless right belongs in
ACCEPTED below, with the reason.

Usage:
    python scripts/validate_event_prose.py            # report
    python scripts/validate_event_prose.py --check    # exit 1 on any finding
    python scripts/validate_event_prose.py max_planck
"""

from __future__ import annotations

import argparse
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

from utils.json_io import read_json
from utils.validation import dataset_paths

# (person id, event date, rule) -> why the sentence is right as written.
ACCEPTED: Dict[Tuple[str, str, str], str] = {}

YEAR = re.compile(r"\b(1[0-9]{3}|20[0-2][0-9])\b")
PARENTHESIZED = re.compile(r"\([^)]*\)")
SOURCE_TALK = re.compile(
    r"\b(most likely|probably|possibly|reportedly|allegedly|according to"
    r"|some sources|sources (?:say|differ|disagree|give)"
    r"|(?:is|are|was|were|remains?) (?:disputed|unclear|uncertain|debated|not known))\b",
    re.IGNORECASE,
)
STREET_WORDS = (
    r"(?:Street|Road|Row|Avenue|Lane|Square|Terrace|Straße|Strasse|Gasse|Platz)"
)
# A house number in front of a named street is an address wherever it stands.
ADDRESS = re.compile(
    r"\b\d{1,4}[a-z]?\s+(?:[A-Z][\w'’-]*\s+){1,3}" + STREET_WORDS + r"\b"
)
# A named street in a title is street-level granularity, unless the street
# word is itself part of a longer proper name ("Rumbach Street Synagogue").
TITLE_STREET = re.compile(r"\b[A-Z][\w'’-]*\s+" + STREET_WORDS + r"\b(?!\s+[A-Z])")


class ProseFinding:
    def __init__(self, person_id: str, event: Dict[str, Any], rule: str, quote: str):
        self.person_id = person_id
        self.date = str(event.get("date") or "")
        self.title = str(event.get("title") or "")
        self.rule = rule
        self.quote = quote

    def __str__(self) -> str:
        return (
            f'{self.person_id} {self.date} "{self.title}": {self.rule} — '
            f"…{self.quote}…"
        )


def _span_end(event: Dict[str, Any]) -> Optional[int]:
    for key in ("date_end", "date"):
        value = str(event.get(key) or "")[:4]
        if value.isdigit():
            return int(value)
    return None


def _excerpt(text: str, match: "re.Match[str]", margin: int = 40) -> str:
    return text[max(0, match.start() - margin) : match.end() + margin].replace(
        "\n", " "
    )


def later_years(event: Dict[str, Any]) -> List[str]:
    """Excerpts around each year in the description later than the event."""
    end = _span_end(event)
    text = str(event.get("description") or "")
    if end is None or not text:
        return []
    scanned = PARENTHESIZED.sub(lambda m: " " * len(m.group(0)), text)
    return [
        _excerpt(text, match)
        for match in YEAR.finditer(scanned)
        if int(match.group(1)) > end
    ]


def source_talk(event: Dict[str, Any]) -> List[str]:
    text = str(event.get("description") or "")
    return [_excerpt(text, match) for match in SOURCE_TALK.finditer(text)]


def street_level(event: Dict[str, Any]) -> List[str]:
    found = []
    title = str(event.get("title") or "")
    text = str(event.get("description") or "")
    for match in TITLE_STREET.finditer(title):
        found.append(_excerpt(title, match))
    for field in (title, text):
        for match in ADDRESS.finditer(field):
            found.append(_excerpt(field, match))
    return found


RULES = (
    ("a later year in the event's own prose", later_years),
    ("the language of weighing sources", source_talk),
    ("street-level place in a city-level slide", street_level),
)


def check_person(person_id: str, data: Dict[str, Any]) -> List[ProseFinding]:
    findings: List[ProseFinding] = []
    for event in data.get("events") or []:
        for rule, read in RULES:
            if (person_id, str(event.get("date") or ""), rule) in ACCEPTED:
                continue
            for quote in read(event):
                findings.append(ProseFinding(person_id, event, rule, quote))
    return findings


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "person_ids", nargs="*", help="Person ids to check (default: all)"
    )
    parser.add_argument(
        "--check", action="store_true", help="Exit 1 when anything was found"
    )
    args = parser.parse_args(argv)

    findings: List[ProseFinding] = []
    checked = 0
    for path in dataset_paths(args.person_ids):
        if not path.exists():
            print(f"warning: {path} not found", file=sys.stderr)
            continue
        findings.extend(check_person(path.parent.name, read_json(path)))
        checked += 1

    for finding in findings:
        print(finding)
    by_rule = {rule: sum(f.rule == rule for f in findings) for rule, _ in RULES}
    print(
        f"\nChecked {checked} person dataset(s), {len(findings)} finding(s): {by_rule}"
    )
    return 1 if args.check and findings else 0


if __name__ == "__main__":
    sys.exit(main())
