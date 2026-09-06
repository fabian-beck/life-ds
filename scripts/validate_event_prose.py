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
  - a description under twenty words, and a conclusion of one sentence — the
    prompts ask for two to four sentences each carrying a fact, and a text
    under that has left out a fact the sources hold: "In 1930, she married a
    New York University professor." under a card naming the partner, "COBOL
    remains in use today in business and government computing." for a whole
    life
  - an annotation whose explanation restates the description: when most of
    its content words already stand in the description, the title, or the
    term, the reader taps the term and learns nothing (Turing's Banburismus
    slide defined the method in the sentence and again in the popup)

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
# A sentence ends on a terminal mark followed by space and a capital, a quote,
# or the end of the text. A single capital before the period is an initial
# ("J. Robert Oppenheimer"), and a title or a rank is an abbreviation; neither
# ends a sentence.
ABBREVIATIONS = {
    "Dr",
    "Mr",
    "Mrs",
    "Ms",
    "St",
    "Jr",
    "Sr",
    "No",
    "Prof",
    "Gen",
    "Col",
    "Capt",
    "Lt",
    "Sgt",
    "Rev",
    "Hon",
    "Mt",
    "Ft",
    "ca",
    "vs",
    "cf",
    "etc",
}
SENTENCE_END = re.compile(r"(?<=[.!?])[\"'’”)]*(?=\s+[A-Z\"'“(]|\s*$)")
# Two sentences that each carry a fact run to twenty words and more; the
# descriptions the corpus shipped under that name the event and nothing
# around it. A conclusion is measured in sentences, since one sentence is one
# strand of a life whatever its length.
MIN_DESCRIPTION_WORDS = 20
MIN_CONCLUSION_SENTENCES = 2


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


def count_sentences(text: str) -> int:
    """How many sentences a reader counts in the text."""
    count = 0
    for match in SENTENCE_END.finditer(text):
        before = text[: match.start()]
        word = re.search(r"([A-Za-z]+)\.$", before)
        if word and (len(word.group(1)) == 1 or word.group(1) in ABBREVIATIONS):
            continue
        count += 1
    return count


def thin_description(event: Dict[str, Any]) -> List[str]:
    text = str(event.get("description") or "").strip()
    if not text or len(text.split()) >= MIN_DESCRIPTION_WORDS:
        return []
    return [text]


def thin_conclusion(data: Dict[str, Any]) -> List[str]:
    """The conclusion as a finding when it is one sentence; absent is not thin."""
    text = str(data.get("conclusion") or "").strip()
    if not text or count_sentences(text) >= MIN_CONCLUSION_SENTENCES:
        return []
    return [text]


STOPWORDS = frozenset(
    """a an the of to in on at for and or by with from as is was were be been
    being it its this that these those his her their he she they them into over
    under than then there here which who whom whose what when where while not
    no nor so such but if also very more most much many some any each both all
    one first later early after before during between within without through
    about against among across per via up out off""".split()
)
RESTATED_SHARE = 0.6
_SUFFIXES = (
    "ically",
    "ical",
    "ing",
    "ions",
    "ion",
    "ies",
    "ers",
    "er",
    "ed",
    "es",
    "s",
    "al",
    "ly",
)


def _stem(word: str) -> str:
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word


def _content_words(text: str) -> set:
    return {
        _stem(word)
        for word in re.findall(r"[a-z0-9]+", text.lower())
        if word not in STOPWORDS and len(word) > 1
    }


def restated_annotations(event: Dict[str, Any]) -> List[str]:
    """Explanations whose content words mostly already stand in the slide.

    A lexical share catches the restatement written in the same words; a
    paraphrase in fresh words passes, which is why the reviewer reads the
    rest. The share is against the description, the title, and the term, so
    a gloss that names the term it explains is not charged for that.
    """
    annotations = event.get("annotations")
    if not isinstance(annotations, dict):
        return []
    context = _content_words(
        f"{event.get('title') or ''} {event.get('description') or ''}"
    )
    found = []
    for term, annotation in annotations.items():
        explanation = str((annotation or {}).get("explanation") or "")
        words = _content_words(explanation)
        if not words:
            continue
        known = words & (context | _content_words(term))
        if len(known) / len(words) >= RESTATED_SHARE:
            found.append(f"{term}: {explanation}".replace("\n", " "))
    return found


RULES = (
    ("a later year in the event's own prose", later_years),
    ("the language of weighing sources", source_talk),
    ("street-level place in a city-level slide", street_level),
    ("a description under twenty words", thin_description),
    ("an annotation that restates the description", restated_annotations),
)
CONCLUSION_RULE = "a conclusion of one sentence"


def check_person(person_id: str, data: Dict[str, Any]) -> List[ProseFinding]:
    findings: List[ProseFinding] = []
    for event in data.get("events") or []:
        for rule, read in RULES:
            if (person_id, str(event.get("date") or ""), rule) in ACCEPTED:
                continue
            for quote in read(event):
                findings.append(ProseFinding(person_id, event, rule, quote))
    if (person_id, "", CONCLUSION_RULE) not in ACCEPTED:
        for quote in thin_conclusion(data):
            conclusion = {"date": "", "title": "Conclusion"}
            findings.append(ProseFinding(person_id, conclusion, CONCLUSION_RULE, quote))
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
    rules = [rule for rule, _ in RULES] + [CONCLUSION_RULE]
    by_rule = {rule: sum(f.rule == rule for f in findings) for rule in rules}
    print(
        f"\nChecked {checked} person dataset(s), {len(findings)} finding(s): {by_rule}"
    )
    return 1 if args.check and findings else 0


if __name__ == "__main__":
    sys.exit(main())
