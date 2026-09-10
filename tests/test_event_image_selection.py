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

from events.images import assign, sources  # noqa: E402
from events.schemas import EventSkeleton  # noqa: E402

SKELETONS = [
    EventSkeleton(
        date="1912",
        date_precision="year",
        title="Birth in London",
        description="Born in Maida Vale.",
    ),
    EventSkeleton(
        date="1940",
        date_precision="year",
        title="Built the bombe",
        description="The machine that broke Enigma traffic.",
    ),
]


def match_prompt(candidates=None) -> str:
    return assign.build_image_match_prompt(
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
        import generate_event_backgrounds as backgrounds

        source = Path(backgrounds.__file__).read_text(encoding="utf-8")
        chooser = source[source.index("def fetch_background_images") :]
        chooser = chooser[: chooser.index("\ndef ")]
        self.assertIn("STAND_IN_REJECTION_INSTRUCTIONS", chooser)
        self.assertIn(assign.STAND_IN_REJECTION_INSTRUCTIONS, match_prompt())

    def test_the_commemorative_forms_are_named(self) -> None:
        rules = assign.STAND_IN_REJECTION_INSTRUCTIONS.lower()
        for form in ("plaque", "gravestone", "tomb", "statue", "bust", "stamp"):
            with self.subTest(form=form):
                self.assertIn(form, rules)

    def test_an_event_about_the_object_keeps_its_picture(self) -> None:
        """A monument is a picture of its own unveiling.

        Without the exception the rule would strip the medal from the event
        that awarded it, which is a real picture of a real event.
        """
        self.assertIn("ABOUT the object", assign.STAND_IN_REJECTION_INSTRUCTIONS)


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


class PresentDayPhotographTests(unittest.TestCase):
    """The year a photograph was taken, which a filename never says.

    Turing's 1952 conviction carried "Facade of Manchester County Court
    Offices", photographed in 2016: the research had searched for a court in
    Manchester, Commons answered with the court building that stands there
    today, and the matcher read the name against "a court in Manchester" as
    the building where it happened. The date was in the file's metadata and
    in none of the three lines the matcher was shown.
    """

    def test_the_listing_says_when_a_photograph_was_taken(self) -> None:
        prompt = match_prompt(
            [
                {
                    "filename": "Facade_of_Manchester_County_Court_Offices.jpg",
                    "caption": "Facade of Manchester County Court Offices",
                    "dateTimeOriginal": "2016-01-03",
                },
                {"filename": "Bombe.jpg", "caption": "A bombe"},
            ]
        )
        listing = prompt[prompt.index("AVAILABLE IMAGES:") : prompt.index("TASK:")]
        self.assertIn("Taken: 2016", listing)
        # Openverse reports no date; a line invented for it would be the hint
        # pointing at nothing.
        self.assertEqual(listing.count("Taken:"), 1)

    def test_the_year_is_read_from_the_commons_field(self) -> None:
        self.assertEqual(assign.image_year_taken({"dateTimeOriginal": "1952"}), 1952)
        self.assertEqual(
            assign.image_year_taken({"dateTimeOriginal": "3 January 2016"}), 2016
        )
        self.assertIsNone(assign.image_year_taken({"dateTimeOriginal": ""}))
        self.assertIsNone(assign.image_year_taken({}))

    def test_the_matcher_is_told_what_the_year_means(self) -> None:
        rules = match_prompt()
        rules = rules[rules.index("ASSIGNMENT RULES:") : rules.index("GOOD MATCHES:")]
        self.assertIn("'Taken: YEAR'", rules)
        self.assertIn("decades after the event", rules)

    def test_a_building_of_a_kind_in_a_city_is_a_stand_in(self) -> None:
        """Reached by both choosers, since the rule lives in the shared list."""
        rules = assign.STAND_IN_REJECTION_INSTRUCTIONS
        self.assertIn("'a court in Manchester'", rules)
        self.assertIn("the kind of place and the city is not a match", rules)

    def test_a_building_is_a_good_match_only_when_the_event_names_it(self) -> None:
        good = match_prompt()
        good = good[good.index("GOOD MATCHES:") : good.index("NEVER ASSIGN:")]
        self.assertNotIn("Building photo", good)
        self.assertIn("a building the event NAMES", good)
        self.assertIn("stood at the time", good)

    def test_the_research_is_told_to_name_a_particular_thing(self) -> None:
        """The pool decides the outcome: a query for a kind of place in a city
        returns the building of that kind standing there today."""
        from events.prompts.research import build_research_prompt_base

        prompt = build_research_prompt_base(SKELETONS[1], "Alan Turing", [])
        queries = prompt[prompt.index("6. IMAGE_SEARCH_QUERIES") :]
        queries = queries[: queries.index("AVAILABLE ICONS")]
        self.assertIn("Name a PARTICULAR thing", queries)
        self.assertIn("'Manchester court'", queries)

    def test_the_report_critic_sees_the_year_too(self) -> None:
        import generate_event_backgrounds as backgrounds

        candidates = [
            {
                "url": "https://example.org/facade.jpg",
                "caption": "Facade of Manchester County Court Offices",
                "query": "Manchester court",
                "_filename": "Facade.jpg",
                "_taken": 2016,
            },
            {
                "url": "https://example.org/bombe.jpg",
                "caption": "A bombe",
                "query": "bombe",
                "_filename": "Bombe.jpg",
                "_taken": None,
            },
        ]
        with (
            mock.patch.object(
                backgrounds, "_background_candidates", return_value=candidates
            ),
            mock.patch.object(backgrounds, "parse_structured") as parse,
        ):
            parse.return_value = None
            backgrounds.fetch_background_images(
                mock.MagicMock(), "A report.", ["Manchester court"], set()
            )
        sent = parse.call_args.kwargs["input"][1]["content"]
        self.assertIn(
            "[0] Facade.jpg — Facade of Manchester County Court Offices (taken 2016)",
            sent,
        )
        self.assertIn("[1] Bombe.jpg — A bombe\n", sent)
        self.assertIn("'(taken YEAR)'", sent)


class SearchPlanningTests(unittest.TestCase):
    def test_commemoration_is_forbidden_to_the_planner(self) -> None:
        """The pool decides the outcome before the matcher ever reads it.

        'Franz Kafka Prague'—the person-and-city form the prompt used to
        require—answers with a birthplace plaque, a bronze head, a kinetic
        sculpture, and a statue.
        """
        source = Path(assign.__file__).read_text(encoding="utf-8")
        planner = source[source.index("def generate_image_search_strings") :]
        planner = planner[: planner.index("\ndef ")]
        self.assertIn("NEVER search for a commemoration", planner)
        for banned in ("memorial", "grave", "birthplace", "plaque", "statue"):
            with self.subTest(banned=banned):
                self.assertIn(f"'X {banned}'", planner)

    def test_the_researched_searches_are_kept_two_per_event(self) -> None:
        planned = assign.plan_event_image_searches(
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
        self.assertEqual(assign.plan_event_image_searches([[], [""], ["  "]]), {})

    def test_a_repeated_search_is_not_run_twice(self) -> None:
        planned = assign.plan_event_image_searches([["bombe", "bombe", "Hut 8"]])
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
        # Patched where the searches are defined, not where they are called:
        # `execute_batch_image_search` reaches them through the `sources`
        # module, so the substitutions survive that caller moving into the
        # events package as the split proceeds.
        with (
            mock.patch.object(sources, "search_wikimedia_commons", commons),
            mock.patch.object(sources, "search_openverse", self._openverse),
        ):
            return assign.execute_batch_image_search(
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
