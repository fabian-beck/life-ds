"""Tests for the event-date checker.

The checker's risky part is not comparing two numbers. It is deciding which
numbers in a description are claims about the event and which are context, and
every sentence below is one the corpus actually holds.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import validate_event_dates as dates  # noqa: E402


def check(event: dict) -> list[str]:
    return [str(f) for f in dates.check_event("someone", event)]


class YearReadingTests(unittest.TestCase):
    def test_a_decade_is_not_a_year(self) -> None:
        self.assertEqual(dates.years_named("By the mid-1880s, it was in focus."), [])
        self.assertEqual(dates.years_named("Exhibitions across the 1950s."), [])

    def test_a_range_covers_every_year_it_names(self) -> None:
        self.assertIn(1919, dates.years_named("the 1918–1919 German Revolution"))
        self.assertIn(1780, dates.years_named("During the winter of 1779–1780"))
        self.assertIn(1929, dates.years_named("plans for the Turku Fair of 1928–29"))

    def test_a_plain_year_is_a_year(self) -> None:
        self.assertEqual(dates.years_named("In 1922, Bush helped found it."), [1922])


class SentenceTests(unittest.TestCase):
    def test_only_the_opening_sentence_is_read(self) -> None:
        # The stray year belongs to the family, not to the birth.
        self.assertEqual(
            check(
                {
                    "date": "1890-03-11",
                    "title": "Born in Everett",
                    "description": (
                        "Vannevar Bush was born in Everett, Massachusetts, the "
                        "third child of a Universalist minister. The family "
                        "moved to nearby Chelsea in 1892."
                    ),
                }
            ),
            [],
        )

    def test_a_life_span_in_parentheses_belongs_to_somebody_else(self) -> None:
        self.assertEqual(
            check(
                {
                    "date": "1891-11-22",
                    "title": "Born in Vienna",
                    "description": (
                        "His mother was Anna Freud Bernays (1858–1955), Freud's "
                        "sister, and his father was Eli Bernays (1860–1921)."
                    ),
                }
            ),
            [],
        )

    def test_annotation_markup_is_read_as_the_text_it_renders(self) -> None:
        self.assertEqual(
            check(
                {
                    "date": "1926-05",
                    "title": "Entered Sherborne School",
                    "description": (
                        "Turing began boarding at [[Sherborne School|Sherborne "
                        "School]] during the [[1926 United Kingdom general "
                        "strike|General Strike]] disruption."
                    ),
                }
            ),
            [],
        )


class ContradictionTests(unittest.TestCase):
    def test_a_year_outside_the_event_is_reported(self) -> None:
        findings = check(
            {
                "date": "1924",
                "title": "Founds company that becomes Raytheon",
                "description": (
                    "In 1922, Bush helped found the business that would become "
                    "the Raytheon Company."
                ),
            }
        )
        self.assertEqual(len(findings), 1)
        self.assertIn("1922", findings[0])

    def test_a_year_inside_the_event_span_is_not_a_contradiction(self) -> None:
        self.assertEqual(
            check(
                {
                    "date": "1977-04",
                    "date_end": "1980-12",
                    "title": "Apple II and IPO boom",
                    "description": "Apple's growth culminated in its 1980 offering.",
                }
            ),
            [],
        )

    def test_an_undated_or_yearless_description_is_left_alone(self) -> None:
        self.assertEqual(
            check({"date": "1930", "title": "x", "description": "No year here."}), []
        )
        self.assertEqual(check({"title": "x", "description": "In 1930 it began."}), [])

    def test_a_reviewed_exception_is_accepted_for_its_own_event_only(self) -> None:
        event = {
            "date": "1935",
            "title": "Completes Viipuri Library",
            "description": "The library was completed after a 1927 competition.",
        }
        self.assertEqual(dates.check_event("alvar_aalto", event), [])
        self.assertTrue(dates.check_event("someone_else", event))


class CorpusTests(unittest.TestCase):
    def test_no_shipped_event_contradicts_its_own_opening_sentence(self) -> None:
        findings = []
        for path in sorted(dates.PEOPLE_DIR.glob("*/life_events.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            findings.extend(dates.check_person(path.parent.name, data))
        self.assertEqual([str(f) for f in findings], [])


if __name__ == "__main__":
    unittest.main()
