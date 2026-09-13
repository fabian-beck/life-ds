"""The style step is shown what the person's work looked like, and must say so.

The palette used to be derived from nothing. `load_dataset_context` passed the
first five events in chronological order, which for every dataset are the birth,
the childhood, and the schooling: the call that chose Frank Lloyd Wright's colors
saw "born in Richland Center, Wisconsin" and never Taliesin. With no evidence in
front of it and no instruction to look for any, the model answered with the most
legible pair on a near-black ground, and two thirds of the corpus came back amber
and cyan.

These tests hold the two halves of the fix: the events the prompt carries are
chosen for what they depict rather than for coming first, and a palette arrives
with a sentence naming where it came from or it does not arrive at all.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import generate_person_style as style  # noqa: E402


def _event(title: str, date: str, **extra: Any) -> Dict[str, Any]:
    return {"title": title, "date": date, "description": f"{title}.", **extra}


def _life() -> list[Dict[str, Any]]:
    """A dataset shaped like the real ones: life stages first, work later."""
    return [
        _event("Born in Richland Center", "1867", event_class={"type": "birth"}),
        _event("Attends school", "1876"),
        _event("Marries", "1889", event_class={"type": "marriage_partnership"}),
        _event(
            "Builds Taliesin",
            "1911",
            images=[{"caption": "View of Taliesin from below"}],
        ),
        _event(
            "Designs the Imperial Hotel",
            "1915",
            images=[{"caption": "Imperial Hotel Tokyo"}],
        ),
        _event(
            "Publishes An Autobiography", "1932", event_class={"type": "publication"}
        ),
        _event("Opens the Taliesin Fellowship", "1934"),
        _event("Designs Fallingwater", "1935"),
        _event("Builds the Johnson Wax headquarters", "1936"),
        _event("Receives the Guggenheim commission", "1943"),
        _event("Dies in Phoenix", "1959", event_class={"type": "death"}),
    ]


class EventSelectionTests(unittest.TestCase):
    def test_the_work_is_chosen_over_the_childhood(self) -> None:
        titles = [s["title"] for s in style.style_event_samples(_life())]
        self.assertIn("Builds Taliesin", titles)
        self.assertIn("Designs the Imperial Hotel", titles)
        for life_stage in ("Born in Richland Center", "Marries", "Dies in Phoenix"):
            self.assertNotIn(
                life_stage,
                titles,
                "a life stage tells the palette nothing and crowded out the buildings",
            )

    def test_the_captions_of_what_the_story_shows_are_carried(self) -> None:
        """The captions name the works; they are the evidence a palette is read off."""
        samples = style.style_event_samples(_life())
        depicted = [caption for s in samples for caption in s.get("depicted", [])]
        self.assertEqual(
            depicted, ["View of Taliesin from below", "Imperial Hotel Tokyo"]
        )

    def test_the_samples_stay_in_the_order_the_life_ran(self) -> None:
        dates = [s["date"] for s in style.style_event_samples(_life())]
        self.assertEqual(dates, sorted(dates))

    def test_the_selection_is_capped_and_repeatable(self) -> None:
        events = _life() + [
            _event(f"Later work {index}", f"19{40 + index}") for index in range(12)
        ]
        first = style.style_event_samples(events)
        self.assertEqual(len(first), style.STYLE_EVENT_SAMPLES)
        self.assertEqual(first, style.style_event_samples(events))

    def test_a_life_of_nothing_but_life_stages_still_yields_samples(self) -> None:
        """A person whose dataset shows no work is still given what there is."""
        stages = [
            _event("Born", "1801", event_class={"type": "birth"}),
            _event("Marries", "1830", event_class={"type": "marriage_partnership"}),
            _event("Dies", "1870", event_class={"type": "death"}),
        ]
        self.assertEqual(len(style.style_event_samples(stages)), 3)

    def test_malformed_events_are_skipped_rather_than_raised_on(self) -> None:
        events = ["not an event", None, *_life()]
        samples = style.style_event_samples(events)
        self.assertTrue(all(isinstance(sample, dict) for sample in samples))
        self.assertIn("Builds Taliesin", [s["title"] for s in samples])


class VisualRelevanceTests(unittest.TestCase):
    def test_a_depicted_event_outranks_a_life_stage(self) -> None:
        depicted = _event("Builds", "1911", images=[{"caption": "Taliesin"}])
        birth = _event("Born", "1867", event_class={"type": "birth"})
        self.assertGreater(
            style.visual_relevance(depicted), style.visual_relevance(birth)
        )

    def test_a_made_thing_outranks_an_unclassified_event(self) -> None:
        published = _event("Publishes", "1932", event_class={"type": "publication"})
        plain = _event("Travels", "1932")
        self.assertGreater(
            style.visual_relevance(published), style.visual_relevance(plain)
        )


class PaletteRationaleTests(unittest.TestCase):
    """A palette arrives with its derivation or it is rejected."""

    def test_a_derivation_is_kept_as_written(self) -> None:
        self.assertEqual(
            style.normalize_rationale(
                "the ochre sandstone and pale concrete of Fallingwater"
            ),
            "the ochre sandstone and pale concrete of Fallingwater",
        )

    def test_whitespace_is_collapsed(self) -> None:
        self.assertEqual(
            style.normalize_rationale(
                "the  ochre\n and slate\tof Fallingwater's stone"
            ),
            "the ochre and slate of Fallingwater's stone",
        )

    def test_a_missing_derivation_is_rejected(self) -> None:
        for value in (None, "", "   ", 7):
            with self.subTest(value=value):
                with self.assertRaises(ValueError) as raised:
                    style.normalize_rationale(value)
                self.assertIn("palette_rationale", str(raised.exception))

    def test_a_label_is_not_a_derivation(self) -> None:
        with self.assertRaises(ValueError) as raised:
            style.normalize_rationale("warm and cool")
        self.assertIn("too short", str(raised.exception))

    def test_the_prompt_asks_for_the_field_and_warns_off_the_default_pairing(
        self,
    ) -> None:
        prompt = style.build_prompt("Frank Lloyd Wright", "frank_lloyd_wright", {})
        self.assertIn("palette_rationale", prompt)
        self.assertIn("PALETTE DERIVATION", prompt)
        self.assertIn("Cherokee Red", prompt)
        self.assertIn("amber", prompt.lower())

    def test_the_prompt_states_the_floor_the_code_enforces(self) -> None:
        """The prompt used to ask for 4.5:1 while the code rejected under 3:1."""
        from utils.person_style import MIN_TEXT_CONTRAST

        prompt = style.build_prompt("Ada Lovelace", "ada_lovelace", {})
        self.assertIn(f"{MIN_TEXT_CONTRAST:g}:1", prompt)
        self.assertNotIn("4.5:1", prompt)


if __name__ == "__main__":
    unittest.main()
