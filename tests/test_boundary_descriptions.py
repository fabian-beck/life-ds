"""Tests for what the birth and death descriptions are asked to tell.

The two boundary slides already show the fact itself, the parents on the birth
card and the cause on the death card, so their prose is written toward a goal of
its own: what this life began from, and how it ended. The goal lives once in the
class table; these tests hold that every step that writes or judges a
description reads it from there, that the research may widen a skeleton that
only restated the slide, and that neither goal forbids the prose to name the
people the card names, since the card alone cannot say how they stand to each
other.
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
from events.prompts.research import build_research_prompt_classified  # noqa: E402
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
    def test_birth_guidance_states_the_goal(self) -> None:
        self.assertIn("GOAL", BIRTH_DESCRIPTION_GUIDANCE)
        self.assertIn("what this life began from", BIRTH_DESCRIPTION_GUIDANCE)
        self.assertIn("whoever actually raised the child", BIRTH_DESCRIPTION_GUIDANCE)
        self.assertIn("says the card again and stops", BIRTH_DESCRIPTION_GUIDANCE)

    def test_death_guidance_states_the_goal(self) -> None:
        self.assertIn("GOAL", DEATH_DESCRIPTION_GUIDANCE)
        self.assertIn("how this life ended", DEATH_DESCRIPTION_GUIDANCE)
        self.assertIn("conditions of the end", DEATH_DESCRIPTION_GUIDANCE)
        self.assertIn("says the card again and stops", DEATH_DESCRIPTION_GUIDANCE)

    def test_the_prose_may_name_the_people_the_card_names(self) -> None:
        """The Jobs birth slide: four parents on the card, an adoption in none of the prose.

        The guidance that produced it forbade the description to carry a parent
        at all, so the one sentence that would have made the slide legible could
        not be written. Both goals now say the prose names whoever it must.
        """
        self.assertIn("names whoever it must name", BIRTH_DESCRIPTION_GUIDANCE)
        for guidance in (BIRTH_DESCRIPTION_GUIDANCE, DEATH_DESCRIPTION_GUIDANCE):
            self.assertNotIn("the prose carries none of them", guidance)
        self.assertNotIn(
            "the prose carries none of them",
            "\n".join(EVENT_CLASS_CONFIG["birth"]["research_focus"]),
        )

    def test_only_the_boundary_kinds_define_the_prose(self) -> None:
        defined = {
            kind
            for kind, config in EVENT_CLASS_CONFIG.items()
            if config.get("description_guidance")
        }
        self.assertEqual(defined, {"birth", "death"})


class ProposalTests(unittest.TestCase):
    def test_detection_guidance_carries_the_goal(self) -> None:
        self.assertIn(
            BIRTH_DESCRIPTION_GUIDANCE.split("\n")[0],
            EVENT_CLASS_CONFIG["birth"]["proposal_guidance"],
        )
        self.assertIn(
            DEATH_DESCRIPTION_GUIDANCE.split("\n")[0],
            EVENT_CLASS_CONFIG["death"]["proposal_guidance"],
        )

    def test_examples_are_nested_under_the_description_bullet(self) -> None:
        guidance = EVENT_CLASS_CONFIG["birth"]["proposal_guidance"]
        self.assertIn("\n  * DESCRIPTION GOAL:", guidance)
        self.assertIn("\n    * GOOD:", guidance)


class ResearchTests(unittest.TestCase):
    def test_birth_prompt_may_rewrite_the_skeleton(self) -> None:
        prompt = build_research_prompt_classified(
            skeleton("Born in London", "1912-06-23", BirthClassification()),
            "Alan Turing",
            [],
        ).text
        self.assertIn(BIRTH_DESCRIPTION_GUIDANCE, prompt)
        self.assertIn(BOUNDARY_REWRITE_NOTE, prompt)
        self.assertLess(
            prompt.index("0. DESCRIPTION"), prompt.index(BOUNDARY_REWRITE_NOTE)
        )

    def test_death_prompt_carries_the_goal(self) -> None:
        prompt = build_research_prompt_classified(
            skeleton("Dies in Wilmslow", "1954-06-07", DeathClassification()),
            "Alan Turing",
            [],
        ).text
        self.assertIn(DEATH_DESCRIPTION_GUIDANCE, prompt)
        self.assertIn(BOUNDARY_REWRITE_NOTE, prompt)

    def test_other_classes_keep_their_own_guidance(self) -> None:
        prompt = build_research_prompt_classified(
            skeleton(
                "Marries Joan Clarke",
                "1941-01-01",
                MarriagePartnershipClassification(
                    subtype="marriage", partner="Joan Clarke"
                ),
            ),
            "Alan Turing",
            [],
        ).text
        self.assertNotIn(BOUNDARY_REWRITE_NOTE, prompt)
        self.assertNotIn(BIRTH_DESCRIPTION_GUIDANCE, prompt)


class ReviewTests(unittest.TestCase):
    def test_review_holds_both_descriptions_to_the_goal(self) -> None:
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
