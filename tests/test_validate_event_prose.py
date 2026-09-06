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


class RestatedSentences(unittest.TestCase):
    """The shape a per-event rewrite produces: the slide before, told again."""

    def test_the_turing_ace_slides_are_the_finding(self) -> None:
        earlier = event(
            "Turing joins the National Physical Laboratory in Teddington. He "
            "prepares plans for the Automatic Computing Engine, a stored-program "
            "electronic computer.",
            title="Joins the National Physical Laboratory",
        )
        later = event(
            "At the National Physical Laboratory in Teddington, Turing completes "
            "the Automatic Computing Engine design. The design sets out a "
            "stored-program electronic computer.",
            title="Completes the Automatic Computing Engine Design",
        )
        found = prose.restated_sentences(later, [earlier], "Alan Turing")
        self.assertEqual(len(found), 2)
        self.assertIn('after "Joins the National Physical Laboratory"', found[0])

    def test_the_event_s_own_place_and_people_are_not_shared_words(self) -> None:
        # The contract asks every sentence to name where and with whom, so a
        # slide that opens at the laboratory the slide before it joined has
        # not retold that slide.
        earlier = event("Turing joins the National Physical Laboratory in Teddington.")
        later = event(
            "At the National Physical Laboratory in Teddington, Turing completes "
            "the design with John Womersley.",
            locations=[
                {"name_historic": "Teddington, Middlesex", "primary": True},
                {"name_historic": "National Physical Laboratory", "primary": False},
            ],
            involved_people=["John Womersley"],
        )
        self.assertEqual(prose.restated_sentences(later, [earlier], "Alan Turing"), [])

    def test_the_subject_name_is_not_a_shared_word(self) -> None:
        earlier = event("Alan Turing wins the school mathematics prize.")
        later = event("Alan Turing runs the Bletchley section.")
        self.assertEqual(prose.restated_sentences(later, [earlier], "Alan Turing"), [])

    def test_a_slide_far_back_is_re_anchoring(self) -> None:
        # Bohr's chair six slides after his enrollment names the university
        # again for a reader who has read five slides since.
        first = event(
            "Bohr enrolled at the University of Copenhagen to study physics "
            "under Christian Christiansen."
        )
        between = [event(f"Sentence {i} about nothing shared.") for i in range(5)]
        later = event(
            "Bohr took the chair of theoretical physics at the University of "
            "Copenhagen, where he had studied under Christian Christiansen."
        )
        self.assertEqual(
            prose.restated_sentences(later, [first, *between], "Niels Bohr"), []
        )
        self.assertEqual(len(prose.restated_sentences(later, [first], "Niels Bohr")), 1)

    def test_annotation_markup_is_read_as_its_display_text(self) -> None:
        earlier = event("Turing develops Banburismus for the naval Enigma traffic.")
        later = event(
            "Turing develops [[Banburismus|the Banburismus method]] for the "
            "naval Enigma traffic."
        )
        self.assertEqual(len(prose.restated_sentences(later, [earlier], "")), 1)

    def test_check_person_reads_the_events_in_order(self) -> None:
        data = {
            "person": {"name": "Alan Turing"},
            "events": [
                event(
                    "Turing joins the National Physical Laboratory in Teddington. "
                    "He prepares plans for the Automatic Computing Engine, a "
                    "stored-program electronic computer with a large mercury memory."
                ),
                event(
                    "Turing completes the design of the Automatic Computing Engine. "
                    "The design sets out a stored-program electronic computer with "
                    "a large mercury memory and a small instruction set.",
                    date="1946",
                ),
            ],
        }
        findings = prose.check_person("alan_turing", data)
        self.assertEqual([f.rule for f in findings], [prose.SEQUENCE_RULE])
        self.assertEqual(findings[0].date, "1946")
        key = ("alan_turing", "1946", prose.SEQUENCE_RULE)
        prose.ACCEPTED[key] = "test"
        try:
            self.assertEqual(prose.check_person("alan_turing", data), [])
        finally:
            del prose.ACCEPTED[key]


if __name__ == "__main__":
    unittest.main()
