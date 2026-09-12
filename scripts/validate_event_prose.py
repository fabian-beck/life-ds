#!/usr/bin/env python3
"""Check the event prose against the description contract.

Every step that writes a description reads the same definition of one
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
  - a sentence that restates a sentence of one of the three slides before it
    in its content words — "He prepares plans for the Automatic Computing
    Engine, a stored-program electronic computer" on one slide and "The design
    sets out a stored-program electronic computer" on the next — where the
    reader has just read the earlier slide and the later one should carry what
    changed. The research refined each description with only its own event in view,
    so this is the shape a per-event rewrite produces, and the review is the
    one pass that can see it. The event's own place and people are not counted
    as shared words, since the contract asks for them in every sentence

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
from utils.word_overlap import content_words, restates

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
    context = f"{event.get('title') or ''} {event.get('description') or ''}"
    found = []
    for term, annotation in annotations.items():
        explanation = str((annotation or {}).get("explanation") or "")
        if restates(explanation, context, term):
            found.append(f"{term}: {explanation}".replace("\n", " "))
    return found


def split_sentences(text: str) -> List[str]:
    """The sentences a reader counts, cut where count_sentences counts them."""
    text = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", text)
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    sentences: List[str] = []
    start = 0
    for match in SENTENCE_END.finditer(text):
        before = text[: match.start()]
        word = re.search(r"([A-Za-z]+)\.$", before)
        if word and (len(word.group(1)) == 1 or word.group(1) in ABBREVIATIONS):
            continue
        sentences.append(text[start : match.end()].strip())
        start = match.end()
    sentences.append(text[start:].strip())
    return [sentence for sentence in sentences if sentence]


# How many slides back a reader still has in mind. A sentence that re-places
# the subject at an institution six slides after the story first arrived there
# is re-anchoring, and the reader needs it; the same sentence on the next
# slide is repetition.
LOOKBACK = 3
RESTATED_SENTENCE_SHARE = 0.55
RESTATED_SENTENCE_WORDS = 4


def _own_words(event: Dict[str, Any], subject_name: str) -> set:
    """The words the contract asks every sentence to carry: who and where."""
    names = [subject_name]
    for location in event.get("locations") or []:
        if isinstance(location, dict):
            names.append(str(location.get("name_historic") or ""))
            names.append(str(location.get("name_modern") or ""))
    names.extend(str(name) for name in event.get("involved_people") or [])
    return content_words(" ".join(names))


def restated_sentences(
    event: Dict[str, Any],
    earlier_events: List[Dict[str, Any]],
    subject_name: str = "",
    lookback: int = LOOKBACK,
) -> List[str]:
    """Sentences of this event that repeat a sentence of a recent earlier event.

    Two sentences restate each other when most of the shorter one's content
    words stand in the longer one's. The subject's name, the event's own
    places, and its own people are not content words here, because the
    contract asks for them in the sentence and a slide that names where it
    happens has not retold the slide before it; a match needs enough shared
    words beyond those that two sentences about one laboratory are not
    counted as the same sentence. Only the last few events are compared; see
    LOOKBACK. The excerpt names the earlier slide, so the finding can be
    judged without opening the dataset.
    """
    own = _own_words(event, subject_name)
    recent = earlier_events[-lookback:] if lookback else []
    earlier = [
        (
            str(other.get("title") or ""),
            sentence,
            content_words(sentence) - own,
        )
        for other in recent
        for sentence in split_sentences(str(other.get("description") or ""))
    ]
    found: List[str] = []
    for sentence in split_sentences(str(event.get("description") or "")):
        words = content_words(sentence) - own
        if len(words) < RESTATED_SENTENCE_WORDS:
            continue
        for title, other_sentence, other_words in earlier:
            if len(other_words) < RESTATED_SENTENCE_WORDS:
                continue
            shared = len(words & other_words)
            if (
                shared >= RESTATED_SENTENCE_WORDS
                and shared / min(len(words), len(other_words))
                >= RESTATED_SENTENCE_SHARE
            ):
                found.append(f'{sentence} (after "{title}": {other_sentence})')
                break
    return found


RULES = (
    ("a later year in the event's own prose", later_years),
    ("the language of weighing sources", source_talk),
    ("street-level place in a city-level slide", street_level),
    ("a description under twenty words", thin_description),
    ("an annotation that restates the description", restated_annotations),
)
CONCLUSION_RULE = "a conclusion of one sentence"
SEQUENCE_RULE = "restates an earlier slide"


def check_person(person_id: str, data: Dict[str, Any]) -> List[ProseFinding]:
    findings: List[ProseFinding] = []
    events = data.get("events") or []
    subject_name = str((data.get("person") or {}).get("name") or "")
    for index, event in enumerate(events):
        date = str(event.get("date") or "")
        for rule, read in RULES:
            if (person_id, date, rule) in ACCEPTED:
                continue
            for quote in read(event):
                findings.append(ProseFinding(person_id, event, rule, quote))
        if (person_id, date, SEQUENCE_RULE) in ACCEPTED:
            continue
        for quote in restated_sentences(event, events[:index], subject_name):
            findings.append(ProseFinding(person_id, event, SEQUENCE_RULE, quote))
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
    rules = [rule for rule, _ in RULES] + [CONCLUSION_RULE, SEQUENCE_RULE]
    by_rule = {rule: sum(f.rule == rule for f in findings) for rule in rules}
    print(
        f"\nChecked {checked} person dataset(s), {len(findings)} finding(s): {by_rule}"
    )
    return 1 if args.check and findings else 0


if __name__ == "__main__":
    sys.exit(main())
