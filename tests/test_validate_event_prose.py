"""Tests for the prose-register checker (issue #141).

Each rule is one shape the corpus shipped; each negative is a sentence the
rule must leave alone, because a validator that flags ordinary prose stops
being read.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import validate_event_prose as prose  # noqa: E402


def event(description: str, title: str = "Event", date: str = "1791-12-26", **more):
    return {"title": title, "date": date, "description": description, **more}


class LaterYears(unittest.TestCase):
    def test_a_later_move_is_a_forward_reference(self) -> None:
        found = prose.later_years(
            event(
                "His father was a banker, and the family later moved to Devon in 1808."
            )
        )
        self.assertEqual(len(found), 1)
        self.assertIn("1808", found[0])

    def test_the_span_end_bounds_the_check(self) -> None:
        # A range event may name its own last year.
        self.assertEqual(
            prose.later_years(
                event("Losses ran into 1919.", date="1914", date_end="1919")
            ),
            [],
        )

    def test_a_life_span_in_parentheses_is_not_a_claim_about_the_event(self) -> None:
        self.assertEqual(
            prose.later_years(event("He studied under Karl Planck (1888–1916).")),
            [],
        )


class SourceTalk(unittest.TestCase):
    def test_the_shipped_sentence_is_the_finding(self) -> None:
        found = prose.source_talk(
            event(
                "He was born in London, most likely at 44 Crosby Row, though the "
                "exact birthplace is disputed."
            )
        )
        self.assertEqual(len(found), 2)

    def test_a_contested_election_is_history_not_historiography(self) -> None:
        self.assertEqual(
            prose.source_talk(
                event("After the contested election he was crowned at Mainz.")
            ),
            [],
        )
        self.assertEqual(
            prose.source_talk(event("A disputed thesis defense followed.")), []
        )


class StreetLevel(unittest.TestCase):
    def test_a_house_number_is_an_address(self) -> None:
        self.assertEqual(
            len(
                prose.street_level(
                    event("He was born at 70 Parson Street in Townhead.")
                )
            ),
            1,
        )

    def test_a_street_in_the_title_is_street_level(self) -> None:
        self.assertEqual(
            len(
                prose.street_level(
                    event("Born in London.", title="Born Near Walworth Road")
                )
            ),
            1,
        )

    def test_a_building_named_after_its_street_is_a_building(self) -> None:
        self.assertEqual(
            prose.street_level(
                event(
                    "He won the commission.", title="Designed Rumbach Street Synagogue"
                )
            ),
            [],
        )


class Findings(unittest.TestCase):
    def test_an_accepted_sentence_is_skipped(self) -> None:
        data = {"events": [event("They moved in 1808.")]}
        self.assertEqual(len(prose.check_person("x", data)), 1)
        key = ("x", "1791-12-26", "a later year in the event's own prose")
        prose.ACCEPTED[key] = "test"
        try:
            self.assertEqual(prose.check_person("x", data), [])
        finally:
            del prose.ACCEPTED[key]


if __name__ == "__main__":
    unittest.main()
