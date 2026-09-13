"""Translation is asked for judgment, so it runs on the tier that has one.

The small model is for the steps whose output is checked against something
afterwards, rewritten later, or replaceable by a deterministic fallback. A
translation is none of these: extract-translate-merge guards the document's
structure, not its language, and the sentence a German reader sees is whatever
the one call wrote. What it is asked for — the idiom of the target language,
and the difference between a phrase that describes something and one that names
it — is what a small model at low effort does worst. "Publishes Augmentation
Framework" reached German readers as "Rahmen für Erweiterung veröffentlicht",
the words of a report's short name rendered one by one into a heading that names
nothing.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import config  # noqa: E402
import translate_person  # noqa: E402

SOURCE = {
    "person": {"summary": "A summary.", "primary_roles": ["Engineer"]},
    "chapters": [],
    "events": [
        {
            "title": "Publishes Augmentation Framework",
            "description": "He published the report in 1962.",
            "locations": [],
            "images": [],
        }
    ],
}


def _call() -> dict:
    """The keyword arguments the translation call hands the API wrapper."""
    captured: dict = {}

    def fake_parse_structured(client, **kwargs):
        captured.update(kwargs)
        return None

    with mock.patch.object(
        translate_person, "parse_structured", fake_parse_structured
    ):
        translate_person.translate_life_events(
            SOURCE,
            "de",
            client=object(),
            model=translate_person.TRANSLATION_MODEL,
            glossary={},
        )
    return captured


class ModelTierTest(unittest.TestCase):
    def test_translation_runs_on_the_reasoning_tier(self):
        self.assertEqual(translate_person.TRANSLATION_MODEL, config.DEFAULT_MODEL)
        self.assertEqual(
            translate_person.TRANSLATION_REASONING_EFFORT,
            config.DEFAULT_REASONING_EFFORT,
        )

    def test_the_call_site_asks_for_that_tier(self):
        call = _call()

        self.assertEqual(call["model"], config.DEFAULT_MODEL)
        self.assertEqual(call["reasoning_effort"], config.DEFAULT_REASONING_EFFORT)


class HeadlineNamesTheWorkTest(unittest.TestCase):
    """A headline that shortens a work's name is a name, not a phrase."""

    def _prompt(self) -> str:
        return self._user_message(_call())

    @staticmethod
    def _user_message(call: dict) -> str:
        return next(
            message["content"]
            for message in call["input"]
            if message["role"] == "user"
        )

    def test_the_headline_rule_covers_the_names_of_works(self):
        prompt = self._prompt()

        self.assertIn("A headline that names a work", prompt)
        self.assertIn(
            "Name the thing rather than translating the English words for it",
            prompt,
        )

    def test_the_headline_may_be_recast_around_the_name(self):
        self.assertIn("recast the headline around the name", self._prompt())


if __name__ == "__main__":
    unittest.main()
