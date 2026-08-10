"""Tests for what may become the picture on an event slide.

The slide's picture is the largest thing on it, and it was chosen with less
care than the pictures under the fold: the report critic rejected "a modern
memorial, plaque, or reenactment standing in for the thing itself" while the
slide matcher listed "Memorial/plaque -> later events or death" among its good
matches, and asked for 40-60% of slides to be filled. The corpus recorded the
result—a gravestone on fifteen deaths, a plaque on Kafka's birth, a
commemorative sparrow on Einstein's.

Nothing here calls a model. These are assertions about the instructions and
about which searches are run, which is where those pictures were decided.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import generate_person_events as pipeline  # noqa: E402

SKELETONS = [
    pipeline.EventSkeleton(
        date="1912",
        date_precision="year",
        title="Birth in London",
        description="Born in Maida Vale.",
    ),
    pipeline.EventSkeleton(
        date="1940",
        date_precision="year",
        title="Built the bombe",
        description="The machine that broke Enigma traffic.",
    ),
]


def match_prompt(candidates=None) -> str:
    return pipeline.build_image_match_prompt(
        (
            candidates
            if candidates is not None
            else [{"filename": "Bombe.jpg", "caption": "A bombe rebuild"}]
        ),
        SKELETONS,
        "Alan Turing",
    )


class StandInRejectionTests(unittest.TestCase):
    """One rule, reached by both calls that choose a picture."""

    def test_both_prompts_carry_the_same_rejections(self) -> None:
        source = Path(pipeline.__file__).read_text(encoding="utf-8")
        chooser = source[source.index("def fetch_background_images") :]
        chooser = chooser[: chooser.index("\ndef ")]
        self.assertIn("STAND_IN_REJECTION_INSTRUCTIONS", chooser)
        self.assertIn(pipeline.STAND_IN_REJECTION_INSTRUCTIONS, match_prompt())

    def test_the_commemorative_forms_are_named(self) -> None:
        rules = pipeline.STAND_IN_REJECTION_INSTRUCTIONS.lower()
        for form in ("plaque", "gravestone", "tomb", "statue", "bust", "stamp"):
            with self.subTest(form=form):
                self.assertIn(form, rules)

    def test_an_event_about_the_object_keeps_its_picture(self) -> None:
        """A monument is a picture of its own unveiling.

        Without the exception the rule would strip the medal from the event
        that awarded it, which is a real picture of a real event.
        """
        self.assertIn("ABOUT the object", pipeline.STAND_IN_REJECTION_INSTRUCTIONS)


class MatchPromptTests(unittest.TestCase):
    def test_no_quota_is_asked_for(self) -> None:
        prompt = match_prompt()
        self.assertNotIn("40-60", prompt)
        self.assertIn("no quota", prompt)

    def test_plaques_are_not_offered_as_a_good_match(self) -> None:
        good = match_prompt()
        good = good[good.index("GOOD MATCHES:") : good.index("NEVER ASSIGN:")]
        self.assertNotIn("plaque", good.lower())
        self.assertNotIn("memorial", good.lower())

    def test_a_candidate_says_which_event_it_was_searched_for(self) -> None:
        prompt = match_prompt(
            [
                {"filename": "Bombe.jpg", "caption": "A bombe", "for_event": 1},
                {"filename": "Anything.jpg", "caption": "Something else"},
            ]
        )
        listing = prompt[prompt.index("AVAILABLE IMAGES:") : prompt.index("TASK:")]
        self.assertIn("Searched for: Event 1", listing)
        # The untagged candidate came from the searches written for the whole
        # life and belongs to no event in particular; inventing a number for it
        # would be the hint pointing at nothing.
        self.assertEqual(listing.count("Searched for:"), 1)


class SearchPlanningTests(unittest.TestCase):
    def test_commemoration_is_forbidden_to_the_planner(self) -> None:
        """The pool decides the outcome before the matcher ever reads it.

        'Franz Kafka Prague'—the person-and-city form the prompt used to
        require—answers with a birthplace plaque, a bronze head, a kinetic
        sculpture, and a statue.
        """
        source = Path(pipeline.__file__).read_text(encoding="utf-8")
        planner = source[source.index("def generate_image_search_strings") :]
        planner = planner[: planner.index("\ndef ")]
        self.assertIn("NEVER search for a commemoration", planner)
        for banned in ("memorial", "grave", "birthplace", "plaque", "statue"):
            with self.subTest(banned=banned):
                self.assertIn(f"'X {banned}'", planner)

    def test_the_researched_searches_are_kept_two_per_event(self) -> None:
        planned = pipeline.plan_event_image_searches(
            [
                ["bombe machine", "Hut 8 Bletchley", "Enigma rotor", "Banbury sheet"],
                [],
                ["  Manchester Mark I  "],
            ]
        )
        self.assertEqual(
            planned, {0: ["bombe machine", "Hut 8 Bletchley"], 2: ["Manchester Mark I"]}
        )

    def test_an_event_with_no_searches_is_left_out(self) -> None:
        self.assertEqual(pipeline.plan_event_image_searches([[], [""], ["  "]]), {})

    def test_a_repeated_search_is_not_run_twice(self) -> None:
        planned = pipeline.plan_event_image_searches([["bombe", "bombe", "Hut 8"]])
        self.assertEqual(planned, {0: ["bombe", "Hut 8"]})


class BatchSearchTests(unittest.TestCase):
    """The per-event searches run first, and their hits carry the tag."""

    def setUp(self) -> None:
        self.commons: List[str] = []
        self.openverse: List[str] = []

    def _commons(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        self.commons.append(query)
        return [{"url": f"https://example.org/{query}.jpg", "filename": f"{query}.jpg"}]

    def _one_picture(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        self.commons.append(query)
        return [{"url": "https://example.org/one.jpg", "filename": "one.jpg"}]

    def _openverse(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        self.openverse.append(query)
        return []

    def _search(self, commons, event_queries) -> List[Dict[str, Any]]:
        with (
            mock.patch.object(pipeline, "search_wikimedia_commons", commons),
            mock.patch.object(pipeline, "search_openverse", self._openverse),
        ):
            return pipeline.execute_batch_image_search(
                ["Alan Turing"], event_queries=event_queries
            )

    def test_event_hits_are_tagged_and_searched_first(self) -> None:
        images = self._search(self._commons, {1: ["bombe machine"]})

        self.assertEqual(self.commons, ["bombe machine", "Alan Turing"])
        # Openverse is not asked for the named things: a query naming a machine
        # is a query Commons indexes, and the aggregator's breadth is what the
        # person searches need instead.
        self.assertEqual(self.openverse, ["Alan Turing"])
        tagged = {img["filename"]: img.get("for_event") for img in images}
        self.assertEqual(tagged, {"bombe machine.jpg": 1, "Alan Turing.jpg": None})

    def test_a_picture_found_twice_keeps_its_event(self) -> None:
        """Deduplication keeps the first sighting, so the tag must be first.

        A picture the life-wide searches would also have found is the picture
        an event's own search found on purpose.
        """
        images = self._search(self._one_picture, {4: ["bombe machine"]})
        self.assertEqual([img.get("for_event") for img in images], [4])


if __name__ == "__main__":
    unittest.main()
