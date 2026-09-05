"""A term is explained once, where the story first makes it a subject.

Phase 2 researches every event in isolation, so an event three slides after
the one titled for the Analytical Engine annotated the engine again. The
normalize step drops such repeats deterministically; the review save path
applies the same rule.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from events.normalize import drop_repeated_annotations  # noqa: E402
from utils.review_helpers import apply_event_changes  # noqa: E402
from utils.review_models import EventsChanges  # noqa: E402


def _gloss(text: str) -> dict:
    return {"explanation": text, "wikipedia_url": "https://en.wikipedia.org/wiki/X"}


class RepeatedAnnotationTests(unittest.TestCase):
    def test_term_titled_earlier_is_not_glossed_again(self) -> None:
        events = [
            {
                "title": "Designs Analytical Engine",
                "description": "Babbage began developing plans for the Analytical Engine.",
                "event_class": {"type": "invention", "title": "Analytical Engine"},
            },
            {
                "title": "Lectures in Turin",
                "description": "Babbage traveled to Turin to explain the [[Analytical Engine]] to an audience.",
                "annotations": {
                    "Analytical Engine": _gloss("Its design separated mill and store.")
                },
            },
        ]
        self.assertEqual(drop_repeated_annotations(events), ["Analytical Engine"])
        self.assertNotIn("annotations", events[1])
        self.assertEqual(
            events[1]["description"],
            "Babbage traveled to Turin to explain the Analytical Engine to an audience.",
        )

    def test_first_annotation_stays_and_later_ones_go(self) -> None:
        events = [
            {
                "title": "Joins the codebreakers",
                "description": "He reported to [[Bletchley Park|the Park]] in September.",
                "annotations": {
                    "Bletchley Park": _gloss("Britain's wartime codebreaking center.")
                },
            },
            {
                "title": "Leads Hut 8",
                "description": "At [[Bletchley Park]] he led the naval section, using the [[Bombe]].",
                "annotations": {
                    "Bletchley Park": _gloss("The codebreaking site."),
                    "Bombe": _gloss(
                        "An electromechanical device for finding Enigma settings."
                    ),
                },
            },
        ]
        self.assertEqual(drop_repeated_annotations(events), ["Bletchley Park"])
        self.assertEqual(list(events[0]["annotations"]), ["Bletchley Park"])
        self.assertEqual(list(events[1]["annotations"]), ["Bombe"])
        self.assertEqual(
            events[1]["description"],
            "At Bletchley Park he led the naval section, using the [[Bombe]].",
        )

    def test_matching_reads_slugged_keys_as_whole_words(self) -> None:
        events = [
            {
                "title": "Takes part in the Greek War of Independence",
                "description": "…",
            },
            {
                "title": "Returns home",
                "description": "He returned after the war and took up his art again.",
                "annotations": {
                    "Greek_War_of_Independence": _gloss("The 1821 uprising."),
                    "art": _gloss("Kept: 'part' in the earlier title is not the word."),
                },
            },
        ]
        self.assertEqual(
            drop_repeated_annotations(events), ["Greek_War_of_Independence"]
        )
        self.assertEqual(list(events[1]["annotations"]), ["art"])

    def test_review_save_path_applies_the_rule(self) -> None:
        data = {
            "events": [
                {"title": "Conceives Difference Engine", "description": "…"},
                {
                    "title": "Secures funding",
                    "description": "Funding for the [[Difference Engine]] followed.",
                    "annotations": {
                        "Difference Engine": _gloss("A mechanical calculator.")
                    },
                },
            ]
        }
        updated, _applied, _skipped = apply_event_changes(data, EventsChanges())
        self.assertNotIn("annotations", updated["events"][1])
        self.assertEqual(
            updated["events"][1]["description"],
            "Funding for the Difference Engine followed.",
        )


if __name__ == "__main__":
    unittest.main()
