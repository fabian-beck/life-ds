"""Tests for the vocabulary a meta-story translation settles before it starts.

A meta story argues in a few recurring images, and the translation call used to
meet each one first in the title, render it word for word, and then carry that
rendering faithfully through every passage — which is how an architecture story
about "the box" reached German readers as "Kasten", a crate. The decision is now
made in its own call and handed to the translation as fixed vocabulary, so what
matters here is that the handover says what was settled.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from meta_story_translation import (  # noqa: E402
    MetaStoryTranslation,
    RecurringImage,
    apply_meta_story_translations,
    format_image_glossary_for_prompt,
)


def _image(english: str, usage: str, rendering: str) -> RecurringImage:
    return RecurringImage(
        english=english, target_language_usage=usage, rendering=rendering
    )


class FormatImageGlossaryTest(unittest.TestCase):
    def test_names_the_english_image_and_what_replaces_it(self):
        rendered = format_image_glossary_for_prompt(
            [
                _image(
                    "the box",
                    "German architecture writing has no such word; 'Kasten' is a crate",
                    "abgeschlossenes, isoliertes Objekt",
                )
            ]
        )

        self.assertIn('"the box"', rendered)
        self.assertIn('"abgeschlossenes, isoliertes Objekt"', rendered)
        self.assertIn("crate", rendered)

    def test_gives_every_image_its_own_line(self):
        rendered = format_image_glossary_for_prompt(
            [
                _image("the box", "no equivalent", "geschlossenes Objekt"),
                _image("form follows function", "established", "Form folgt Funktion"),
            ]
        )

        self.assertEqual(len(rendered.splitlines()), 2)

    def test_says_so_when_no_image_needed_deciding(self):
        """A story without a governing metaphor is normal, not a failed call."""
        rendered = format_image_glossary_for_prompt([])

        self.assertIn("none", rendered)
        self.assertNotIn("->", rendered)


class GlossaryStaysOutOfTheDocumentTest(unittest.TestCase):
    """The settled wording is scaffolding for the call, not a field of the story."""

    def test_the_translation_schema_carries_only_the_document(self):
        self.assertNotIn("recurring_images", MetaStoryTranslation.model_fields)
        self.assertNotIn("images", MetaStoryTranslation.model_fields)

    def test_the_merge_ignores_keys_the_story_does_not_have(self):
        source = {
            "meta_story": {"title": "Beyond the Box", "tagline": "Nine designers"},
            "subtopics": [],
            "chapters": [],
        }

        result = apply_meta_story_translations(
            source,
            {
                "title": "Architektur im Kontext",
                "tagline": "Neun Gestalter",
                "recurring_images": [{"english": "the box"}],
                "subtopics": [],
                "chapters": [],
            },
            "de",
        )

        self.assertEqual(result["meta_story"]["title"], "Architektur im Kontext")
        self.assertNotIn("recurring_images", result)
        self.assertNotIn("recurring_images", result["meta_story"])


if __name__ == "__main__":
    unittest.main()
