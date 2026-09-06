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


class ThinProse(unittest.TestCase):
    def test_the_shipped_sentence_is_the_finding(self) -> None:
        found = prose.thin_description(
            event("In 1930, she married a New York University professor.")
        )
        self.assertEqual(len(found), 1)

    def test_two_sentences_carrying_facts_are_enough(self) -> None:
        self.assertEqual(
            prose.thin_description(
                event(
                    "In 1930 she married Vincent Foster Hopper, who taught English at "
                    "New York University. She had just finished her master's degree."
                )
            ),
            [],
        )

    def test_a_long_single_sentence_is_not_thin(self) -> None:
        self.assertEqual(
            prose.thin_description(
                event(
                    "In 1842, Schönlein was appointed personal physician to King "
                    "Friedrich Wilhelm IV of Prussia, a role that brought him into "
                    "regular contact with the Prussian court while he continued his "
                    "clinical and teaching work in Berlin."
                )
            ),
            [],
        )

    def test_an_initial_or_a_title_does_not_end_a_sentence(self) -> None:
        self.assertEqual(
            prose.count_sentences("He met J. Robert Oppenheimer and Dr. Bohr there."),
            1,
        )
        self.assertEqual(prose.count_sentences("It cost 3.5 million marks."), 1)

    def test_a_quoted_sentence_end_counts(self) -> None:
        self.assertEqual(
            prose.count_sentences(
                'She called the linker a "compiler." The name stuck.'
            ),
            2,
        )

    def test_a_one_sentence_conclusion_is_a_finding(self) -> None:
        data = {
            "events": [],
            "conclusion": "COBOL remains in use today in business and government computing.",
        }
        found = prose.check_person("x", data)
        self.assertEqual([f.rule for f in found], [prose.CONCLUSION_RULE])

    def test_a_missing_conclusion_is_not_thin(self) -> None:
        self.assertEqual(prose.check_person("x", {"events": [], "conclusion": ""}), [])


class Findings(unittest.TestCase):
    def test_an_accepted_sentence_is_skipped(self) -> None:
        data = {"events": [event("They moved in 1808.")]}
        later = "a later year in the event's own prose"
        self.assertEqual(
            [f.rule for f in prose.check_person("x", data)],
            [later, "a description under twenty words"],
        )
        prose.ACCEPTED[("x", "1791-12-26", later)] = "test"
        prose.ACCEPTED[("x", "1791-12-26", "a description under twenty words")] = "test"
        try:
            self.assertEqual(prose.check_person("x", data), [])
        finally:
            del prose.ACCEPTED[("x", "1791-12-26", later)]
            del prose.ACCEPTED[("x", "1791-12-26", "a description under twenty words")]


class RestatedAnnotations(unittest.TestCase):
    def test_a_gloss_in_the_slides_own_words_is_a_restatement(self) -> None:
        found = prose.restated_annotations(
            event(
                "Mackintosh exhibits with The Four, the Glasgow group of Mackintosh, "
                "Margaret Macdonald, Frances Macdonald, and Herbert MacNair.",
                annotations={
                    "The Four": {
                        "explanation": "A Glasgow group of Mackintosh, Margaret "
                        "Macdonald, Frances Macdonald, and Herbert MacNair."
                    }
                },
            )
        )
        self.assertEqual(len(found), 1)
        self.assertTrue(found[0].startswith("The Four: "))

    def test_a_gloss_that_goes_past_the_sentence_is_left_alone(self) -> None:
        found = prose.restated_annotations(
            event(
                "Turing develops Banburismus to reduce bombe work on naval Enigma.",
                annotations={
                    "Banburismus": {
                        "explanation": "A Bayesian scoring procedure on punched "
                        "sheets printed in Banbury, which is where the name comes "
                        "from; it weighed the likelihood of rotor orders in units "
                        "Turing called bans."
                    }
                },
            )
        )
        self.assertEqual(found, [])

    def test_naming_the_term_is_not_charged(self) -> None:
        found = prose.restated_annotations(
            event(
                "He passes the Abitur.",
                annotations={
                    "Abitur": {
                        "explanation": "The Abitur is the German school-leaving "
                        "examination that qualifies for university admission."
                    }
                },
            )
        )
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
