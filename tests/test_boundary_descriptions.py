"""Tests for what the birth and death descriptions are asked to tell.

The two boundary slides already show the fact itself, the parents on the birth
card and the cause on the death card, so their prose is defined as the
household the child enters and the road to the death. The definition lives once
in the class table; these tests hold that every phase that writes or judges a
description reads it from there, and that Phase 2 is allowed to widen a
skeleton that only restated the slide.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from events.event_classes import (  # noqa: E402
    BIRTH_DESCRIPTION_GUIDANCE,
    BOUNDARY_REWRITE_NOTE,
    DEATH_DESCRIPTION_GUIDANCE,
    EVENT_CLASS_CONFIG,
    boundary_description_prompt,
)
from events.prompts.phase2 import build_phase2_prompt_classified  # noqa: E402
from events.schemas import (  # noqa: E402
    BirthClassification,
    DeathClassification,
    EventSkeleton,
    MarriagePartnershipClassification,
)
from utils.review_prompts import get_combined_review_prompt  # noqa: E402


def skeleton(title, date, event_class):
    return EventSkeleton(
        date=date,
        date_precision="day",
        age=0,
        title=title,
        description=f"{title}.",
        event_class=event_class,
    )


class GuidanceTests(unittest.TestCase):
    def test_birth_guidance_asks_for_the_household(self) -> None:
        self.assertIn("grows up in", BIRTH_DESCRIPTION_GUIDANCE)
        self.assertIn("what the parents did", BIRTH_DESCRIPTION_GUIDANCE)
        self.assertIn("restates the slide", BIRTH_DESCRIPTION_GUIDANCE)

    def test_death_guidance_asks_for_what_led_to_it(self) -> None:
        self.assertIn("what led to the death", DEATH_DESCRIPTION_GUIDANCE)
        self.assertIn("conditions of the end", DEATH_DESCRIPTION_GUIDANCE)
        self.assertIn("restates the slide", DEATH_DESCRIPTION_GUIDANCE)

    def test_only_the_boundary_kinds_define_the_prose(self) -> None:
        defined = {
            kind
            for kind, config in EVENT_CLASS_CONFIG.items()
            if config.get("description_guidance")
        }
        self.assertEqual(defined, {"birth", "death"})


class Phase1Tests(unittest.TestCase):
    def test_detection_guidance_carries_the_definition(self) -> None:
        self.assertIn(
            BIRTH_DESCRIPTION_GUIDANCE.split("\n")[0],
            EVENT_CLASS_CONFIG["birth"]["phase1_guidance"],
        )
        self.assertIn(
            DEATH_DESCRIPTION_GUIDANCE.split("\n")[0],
            EVENT_CLASS_CONFIG["death"]["phase1_guidance"],
        )

    def test_examples_are_nested_under_the_description_bullet(self) -> None:
        guidance = EVENT_CLASS_CONFIG["birth"]["phase1_guidance"]
        self.assertIn("\n  * DESCRIPTION:", guidance)
        self.assertIn("\n    * GOOD:", guidance)


class Phase2Tests(unittest.TestCase):
    def test_birth_prompt_lifts_the_never_longer_rule(self) -> None:
        prompt = build_phase2_prompt_classified(
            skeleton("Born in London", "1912-06-23", BirthClassification()),
            "Alan Turing",
            [],
        )
        self.assertIn(BIRTH_DESCRIPTION_GUIDANCE, prompt)
        self.assertIn(BOUNDARY_REWRITE_NOTE, prompt)
        self.assertLess(
            prompt.index("never longer"), prompt.index(BOUNDARY_REWRITE_NOTE)
        )

    def test_death_prompt_carries_the_definition(self) -> None:
        prompt = build_phase2_prompt_classified(
            skeleton("Dies in Wilmslow", "1954-06-07", DeathClassification()),
            "Alan Turing",
            [],
        )
        self.assertIn(DEATH_DESCRIPTION_GUIDANCE, prompt)
        self.assertIn(BOUNDARY_REWRITE_NOTE, prompt)

    def test_other_classes_keep_the_shortening_rule(self) -> None:
        prompt = build_phase2_prompt_classified(
            skeleton(
                "Marries Joan Clarke",
                "1941-01-01",
                MarriagePartnershipClassification(
                    subtype="marriage", partner="Joan Clarke"
                ),
            ),
            "Alan Turing",
            [],
        )
        self.assertNotIn(BOUNDARY_REWRITE_NOTE, prompt)
        self.assertNotIn(BIRTH_DESCRIPTION_GUIDANCE, prompt)


class ReviewTests(unittest.TestCase):
    def test_review_holds_both_descriptions_to_the_definition(self) -> None:
        prompt = get_combined_review_prompt(
            {"person": {"name": "Alan Turing"}, "events": [], "chapters": []},
            {"connections": []},
            "",
            [],
        )
        self.assertIn(boundary_description_prompt(), prompt)
        self.assertIn("BIRTH " + BIRTH_DESCRIPTION_GUIDANCE, prompt)
        self.assertIn("DEATH " + DEATH_DESCRIPTION_GUIDANCE, prompt)


if __name__ == "__main__":
    unittest.main()
