"""A font the reviewer proposes goes through the generator's own gate.

`generate_person_style.py` picks fonts from a fixed vocabulary, and
`src/fonts.css` self-hosts exactly those families; `tests/test_font_coverage.py`
keeps the two lists in step. The review step then accepted whatever family the
reviewer named and wrote it straight into `person_styles.json`, under a prompt
that only asked for a font "available on Google Fonts".

It cost Charles Babbage his headings. The reviewer replaced the heading font
with "Libre Baskerville", a face the app never loads, so the story rendered its
headings in the fallback font, and the font coverage test went red on `main`.
The reviewer's font is now held to the same list the generator is, and a
proposal outside it leaves the existing font standing. Libre Baskerville has
since joined the vocabulary, so the tests reach for another Google Fonts
family the app does not load.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from generate_person_style import (  # noqa: E402
    BODY_FONT_CHOICES,
    HEADING_FONT_CHOICES,
    sanitise_pattern_svg,
)
from utils.review_helpers import apply_style_changes  # noqa: E402
from utils.review_models import StyleChanges  # noqa: E402
from utils.review_prompts import get_style_review_prompt  # noqa: E402

FONT_CHOICES = {
    "heading_font": HEADING_FONT_CHOICES,
    "body_font": BODY_FONT_CHOICES,
}

BASE_STYLE = {
    "primary": "#F2B84B",
    "secondary": "#63D6D1",
    "background": "#0B1014",
    "background_pattern_svg": (
        '<svg width="160" height="160" viewBox="0 0 160 160" '
        'xmlns="http://www.w3.org/2000/svg"><rect width="160" height="160" '
        'fill="#000000"/><path d="M0 80H160" stroke="#FFFFFF" stroke-width="4"/></svg>'
    ),
    "heading_font": "DM Serif Display",
    "body_font": "IBM Plex Sans",
}


def _apply(**fonts):
    return apply_style_changes(
        BASE_STYLE,
        StyleChanges(confidence=5, rationale="test", new_fonts=fonts),
        sanitise_pattern=sanitise_pattern_svg,
        font_choices=FONT_CHOICES,
    )


class ReviewedFontTests(unittest.TestCase):
    def test_the_reviewers_unhosted_font_leaves_the_existing_one_standing(self):
        """The shape of the proposal that put Babbage's headings in the fallback."""
        updated, applied, skipped = _apply(heading_font="Cormorant Garamond")
        self.assertEqual((applied, skipped), (0, 1))
        self.assertEqual(updated["heading_font"], "DM Serif Display")

    def test_a_font_from_the_vocabulary_applies(self):
        updated, applied, skipped = _apply(heading_font="Playfair Display")
        self.assertEqual((applied, skipped), (1, 0))
        self.assertEqual(updated["heading_font"], "Playfair Display")

    def test_the_vocabulary_is_per_field(self):
        """A body face is not a heading face, even though both are loaded."""
        updated, applied, skipped = _apply(heading_font="Lora", body_font="Lora")
        self.assertEqual((applied, skipped), (1, 1))
        self.assertEqual(updated["heading_font"], "DM Serif Display")
        self.assertEqual(updated["body_font"], "Lora")

    def test_surrounding_whitespace_is_trimmed_as_the_generator_trims_it(self):
        updated, applied, _ = _apply(body_font=" Inter ")
        self.assertEqual(applied, 1)
        self.assertEqual(updated["body_font"], "Inter")

    def test_the_other_style_fields_still_apply(self):
        updated, applied, skipped = apply_style_changes(
            BASE_STYLE,
            StyleChanges(
                confidence=5,
                rationale="test",
                new_primary="#FF0000",
                new_fonts={"heading_font": "Cormorant Garamond"},
            ),
            sanitise_pattern=sanitise_pattern_svg,
            font_choices=FONT_CHOICES,
        )
        self.assertEqual((applied, skipped), (1, 1))
        self.assertEqual(updated["primary"], "#FF0000")


class ReviewPromptTests(unittest.TestCase):
    def test_the_prompt_names_the_vocabulary_rather_than_google_fonts(self):
        prompt = get_style_review_prompt(
            BASE_STYLE,
            {"person": {"name": "Charles Babbage"}},
            heading_fonts=HEADING_FONT_CHOICES,
            body_fonts=BODY_FONT_CHOICES,
        )
        self.assertNotIn("Google Fonts", prompt)
        for font in HEADING_FONT_CHOICES + BODY_FONT_CHOICES:
            self.assertIn(font, prompt)


if __name__ == "__main__":
    unittest.main()
