"""Tests for the review's reading of the slides in order.

A slide is read after the ones before it, and the reader knows what those
said and nothing else. The research refined each description with only its own
event in view, so a slide could lean on a name the story never introduced
("Hut 8") or tell again what the slide before it told, and the review, the
one pass that sees the finished sequence, was not asked to look. These hold
that the definition of a description carries the rule, that every writer
reads it from there, that the review is asked for the reading event by event,
and that what it finds reaches the person running it.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from events.prompts.research import build_research_prompt_base  # noqa: E402
from events.schemas import EventSkeleton  # noqa: E402
from utils.prose_style import description_contract_prompt  # noqa: E402
from utils.review_helpers import continuity_notes  # noqa: E402
from utils.review_models import CombinedReviewOutput, EventReview  # noqa: E402
from utils.review_prompts import get_combined_review_prompt  # noqa: E402

EVENTS = {
    "person": {"name": "Alan Turing"},
    "events": [
        {
            "title": "Joined Bletchley Park",
            "description": "Turing reports to Bletchley.",
        },
        {
            "title": "Designs the Bombe for Enigma",
            "description": "Turing designs the bombe.",
        },
        {
            "title": "Takes Charge of Hut 8",
            "description": "Turing leads Hut 8 at Bletchley Park.",
        },
    ],
}


def review(index: int, **fields) -> EventReview:
    return EventReview(
        event_index=index,
        source_verification="ok",
        icon_appropriateness="ok",
        **fields,
    )


class ContractTests(unittest.TestCase):
    def test_the_contract_says_a_description_is_read_in_sequence(self) -> None:
        contract = description_contract_prompt()
        self.assertIn("It is read in sequence", contract)
        self.assertIn("what happened on an earlier slide is not told again", contract)
        self.assertIn("Hut 8", contract)

    def test_the_research_reads_the_rule_from_the_contract(self) -> None:
        skeleton = EventSkeleton(
            date="1940",
            date_precision="year",
            age=28,
            title="Takes Charge of Hut 8",
            description="Turing leads Hut 8 at Bletchley Park.",
        )
        prompt = build_research_prompt_base(skeleton, "Alan Turing", [])
        self.assertIn("It is read in sequence", prompt)


class ReviewPromptTests(unittest.TestCase):
    def test_the_review_is_asked_to_read_the_slides_in_order(self) -> None:
        prompt = get_combined_review_prompt(EVENTS, {}, "", [])
        self.assertIn("**Story Continuity**", prompt)
        self.assertIn("**The Story So Far**", prompt)
        for field in (
            "contribution",
            "unintroduced_terms",
            "restated_facts",
            "redundant_with",
        ):
            self.assertIn(f"`{field}`", prompt)
        self.assertIn("Give every event an `event_reviews` entry, in order", prompt)

    def test_the_output_schema_carries_the_reading(self) -> None:
        fields = CombinedReviewOutput.model_json_schema()["$defs"]["EventReview"][
            "properties"
        ]
        self.assertEqual(
            {"contribution", "unintroduced_terms", "restated_facts", "redundant_with"}
            - set(fields),
            set(),
        )


class ContinuityNotesTests(unittest.TestCase):
    def test_a_clean_reading_prints_nothing(self) -> None:
        reviews = [review(i, contribution="something") for i in range(3)]
        self.assertEqual(continuity_notes(reviews, EVENTS["events"]), [])

    def test_the_hut_8_reading_reaches_the_terminal(self) -> None:
        reviews = [
            review(0, contribution="arrival"),
            review(1, contribution="the machine"),
            review(
                2,
                contribution="",
                unintroduced_terms=["Hut 8"],
                restated_facts=["at Bletchley Park"],
                redundant_with=0,
            ),
        ]
        notes = continuity_notes(reviews, EVENTS["events"])
        self.assertEqual(len(notes), 3)
        self.assertIn('event 2 "Takes Charge of Hut 8"', notes[0])
        self.assertIn('beyond event 0 "Joined Bletchley Park"', notes[0])
        self.assertIn("leans on 'Hut 8'", notes[1])
        self.assertIn("restates 'at Bletchley Park'", notes[2])

    def test_an_empty_contribution_without_a_verdict_is_still_reported(self) -> None:
        notes = continuity_notes([review(2, contribution=" ")], EVENTS["events"])
        self.assertEqual(len(notes), 1)
        self.assertIn("could not say what the slide adds", notes[0])

    def test_an_index_outside_the_story_is_ignored(self) -> None:
        self.assertEqual(
            continuity_notes([review(7, contribution="")], EVENTS["events"]), []
        )


if __name__ == "__main__":
    unittest.main()
