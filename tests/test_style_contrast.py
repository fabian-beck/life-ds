"""The generator holds a palette to a computed contrast floor.

Primary and secondary are set as heading, label, and glyph colors directly on
the story's background. The prompt asks for readable text colors, and a small
model at low effort sometimes answers with a secondary a shade off the
background. A critic pass used to follow the generator and was asked to check
WCAG ratios by reading hex strings, which is not a check; the ratio is
arithmetic, so `normalize_payload` computes it and rejects a palette under the
floor, and `generate_valid_style` asks the model once more with the reason.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import generate_person_style  # noqa: E402
from generate_person_style import generate_valid_style, normalize_payload  # noqa: E402
from utils.person_style import (  # noqa: E402
    MIN_TEXT_CONTRAST,
    contrast_ratio,
    palette_problems,
    relative_luminance,
)

TILE = (
    '<svg width="160" height="160" viewBox="0 0 160 160" '
    'xmlns="http://www.w3.org/2000/svg"><rect width="160" height="160" '
    'fill="#000000"/><path d="M0 80H160" stroke="#FFFFFF" stroke-width="4"/></svg>'
)
GLYPH = (
    '<svg width="32" height="32" viewBox="0 0 32 32" '
    'xmlns="http://www.w3.org/2000/svg"><circle cx="16" cy="16" r="8" '
    'fill="#49D6FF"/></svg>'
)


def _payload(**overrides):
    payload = {
        "primary": "#49D6FF",
        "secondary": "#FFC857",
        "background": "#08121F",
        "palette_rationale": "the brass and enamel of a Königsberg lecture-hall instrument",
        "background_pattern_svg": TILE,
        "separator_glyph_svg": GLYPH,
        "heading_font": "Space Grotesk",
        "body_font": "IBM Plex Sans",
    }
    payload.update(overrides)
    return payload


class ContrastArithmeticTests(unittest.TestCase):
    def test_white_on_black_is_the_maximum(self):
        self.assertAlmostEqual(contrast_ratio("#FFFFFF", "#000000"), 21.0, places=6)
        self.assertAlmostEqual(contrast_ratio("#000000", "#FFFFFF"), 21.0, places=6)

    def test_luminance_spans_black_to_white(self):
        self.assertEqual(relative_luminance("#000000"), 0.0)
        self.assertAlmostEqual(relative_luminance("#FFFFFF"), 1.0, places=6)

    def test_a_readable_palette_has_no_problems(self):
        self.assertEqual(palette_problems("#49D6FF", "#FFC857", "#08121F"), [])

    def test_every_problem_is_named_at_once(self):
        """A retry prompt should carry everything the model got wrong."""
        problems = palette_problems("#1A2A3A", "#0A1420", "#F0F0F0")
        self.assertEqual(len(problems), 1)  # a light background: text on it reads
        problems = palette_problems("#0A1626", "#0C1A2C", "#08121F")
        self.assertEqual(len(problems), 2)
        self.assertTrue(problems[0].startswith("primary"))
        self.assertTrue(problems[1].startswith("secondary"))


class NormalizeGateTests(unittest.TestCase):
    def test_a_readable_palette_passes(self):
        style = normalize_payload(_payload())
        self.assertEqual(style["primary"], "#49D6FF")

    def test_a_secondary_lost_in_the_background_is_rejected(self):
        with self.assertRaises(ValueError) as caught:
            normalize_payload(_payload(secondary="#0C1A2C"))
        self.assertIn("secondary", str(caught.exception))
        self.assertIn(f"{MIN_TEXT_CONTRAST:g}:1", str(caught.exception))

    def test_a_light_background_is_rejected(self):
        with self.assertRaises(ValueError) as caught:
            normalize_payload(_payload(background="#F4F4F4", primary="#102030"))
        self.assertIn("background", str(caught.exception))


class RetryTests(unittest.TestCase):
    def test_a_rejected_answer_is_asked_again_with_the_reason(self):
        answers = [_payload(secondary="#0C1A2C"), _payload()]
        prompts = []

        def fake_call(prompt, model):
            prompts.append(prompt)
            return answers.pop(0)

        with mock.patch.object(generate_person_style, "call_openai", fake_call):
            style = generate_valid_style("PROMPT", "model")
        self.assertEqual(style["secondary"], "#FFC857")
        self.assertEqual(len(prompts), 2)
        self.assertEqual(prompts[0], "PROMPT")
        self.assertTrue(prompts[1].startswith("PROMPT"))
        self.assertIn("secondary #0C1A2C", prompts[1])

    def test_an_answer_that_never_clears_fails_the_step(self):
        """The budget is spent, then the step fails rather than shipping it."""
        calls = []

        def fake_call(prompt, model):
            calls.append(prompt)
            return _payload(secondary="#0C1A2C")

        with mock.patch.object(generate_person_style, "call_openai", fake_call):
            with self.assertRaises(ValueError):
                generate_valid_style("PROMPT", "model")
        self.assertEqual(len(calls), generate_person_style.STYLE_ATTEMPTS)

    def test_a_palette_without_its_derivation_is_asked_again(self):
        """The rejection names the missing field, so the retry can supply it."""
        answers = [_payload(palette_rationale="warm and cool"), _payload()]
        prompts = []

        def fake_call(prompt, model):
            prompts.append(prompt)
            return answers.pop(0)

        with mock.patch.object(generate_person_style, "call_openai", fake_call):
            style = generate_valid_style("PROMPT", "model")
        self.assertIn("Königsberg", style["palette_rationale"])
        self.assertIn("palette_rationale", prompts[1])


class CorpusContrastTests(unittest.TestCase):
    def test_every_shipped_style_clears_the_floor(self):
        """The floor is set where the corpus already stands; a style under it
        would be a regression the reader sees as unreadable labels."""
        styles = json.loads(
            (
                Path(__file__).resolve().parents[1] / "data" / "person_styles.json"
            ).read_text(encoding="utf-8")
        )["styles"]
        failing = {
            person_id: palette_problems(
                style["primary"], style["secondary"], style["background"]
            )
            for person_id, style in styles.items()
        }
        self.assertEqual({k: v for k, v in failing.items() if v}, {})


if __name__ == "__main__":
    unittest.main()
