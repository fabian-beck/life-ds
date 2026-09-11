"""Tests for how a meta-story translation is asked to handle the story's images.

A meta story argues in a few recurring images, and a translation call that
meets each one first in the title, renders it word for word, and then carries
that rendering faithfully through every passage is how an architecture story
about "the box" reached German readers as "Kasten", a crate. The decision is
made inside the one translation call, so what matters here is that the prompt
asks for it: meaning over words, decided for the whole story, the title
included, and held to everywhere.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import meta_story_translation  # noqa: E402
from meta_story_translation import (  # noqa: E402
    MetaStoryTranslation,
    TranslationReference,
    apply_meta_story_translations,
    translate_meta_story,
)

SOURCE = {
    "meta_story": {"title": "Beyond the Box", "tagline": "Nine designers"},
    "subtopics": [],
    "chapters": [],
}


def _extra_rules() -> str:
    """The meta-story rules as the translation call is shown them."""
    captured = {}

    def fake_call(**kwargs):
        captured.update(kwargs)
        return None

    with mock.patch.object(
        meta_story_translation, "_call_translation_model", fake_call
    ), mock.patch.object(
        meta_story_translation,
        "build_meta_story_reference",
        lambda *args, **kwargs: TranslationReference(),
    ):
        translate_meta_story(SOURCE, "de", client=object())
    return captured["extra_rules"]


class ImageRuleTest(unittest.TestCase):
    def test_no_separate_glossary_call_remains(self):
        self.assertFalse(hasattr(meta_story_translation, "build_image_glossary"))
        self.assertFalse(
            hasattr(meta_story_translation, "format_image_glossary_for_prompt")
        )

    def test_the_translator_decides_the_images_for_the_whole_story(self):
        rules = _extra_rules()

        self.assertIn("read the whole story", rules)
        self.assertIn("drop the picture and say what it meant", rules)
        self.assertIn("hold to it everywhere the image appears", rules)

    def test_the_title_does_not_settle_the_image_first(self):
        rules = _extra_rules()

        self.assertIn("not settled by the passage it first appears in", rules)
        self.assertIn("The title is part of the same decision", rules)


class NothingButTheDocumentTest(unittest.TestCase):
    """The image decision is made in the call, not returned as a field."""

    def test_the_translation_schema_carries_only_the_document(self):
        self.assertNotIn("recurring_images", MetaStoryTranslation.model_fields)
        self.assertNotIn("images", MetaStoryTranslation.model_fields)

    def test_the_merge_ignores_keys_the_story_does_not_have(self):
        result = apply_meta_story_translations(
            SOURCE,
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
