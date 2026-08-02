"""Annotation markers must survive translation with their terms intact.

A description carries its annotations inline as ``[[term|display]]``: the
display text is translated, the term is an id that the document's
``annotations`` map is keyed by. The merge overlays translated text onto a copy
of the English document, so a term the model rewrote is not repaired by
anything downstream — the marker still renders and simply resolves to nothing.

This guard is what makes it safe to translate on the small model: a weaker
translator is allowed to produce flatter prose, not a half-linked document.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from translate_person import (  # noqa: E402
    TranslationMergeError,
    apply_life_events_translations,
)


def _source_document(description: str) -> dict:
    return {
        "person": {"summary": "A summary.", "primary_roles": ["Mathematician"]},
        "chapters": [],
        "events": [
            {
                "title": "A title",
                "description": description,
                "locations": [],
                "images": [],
                "annotations": {
                    "bombe": {"explanation": "An electromechanical device."}
                },
            }
        ],
    }


def _translated_payload(description: str) -> dict:
    return {
        "person": {
            "summary": "Eine Zusammenfassung.",
            "primary_roles": ["Mathematiker"],
        },
        "chapters": [],
        "events": [
            {
                "title": "Ein Titel",
                "description": description,
                "locations": [],
                "images": [],
                "annotations": [
                    {"term": "bombe", "explanation": "Ein elektromechanisches Gerät."}
                ],
            }
        ],
    }


class AnnotationMarkerTests(unittest.TestCase):
    def test_translated_display_text_is_kept(self) -> None:
        result = apply_life_events_translations(
            _source_document("He designed the [[bombe|codebreaking machine]]."),
            _translated_payload("Er entwarf die [[bombe|Entzifferungsmaschine]]."),
            {},
        )
        self.assertEqual(
            result["events"][0]["description"],
            "Er entwarf die [[bombe|Entzifferungsmaschine]].",
        )

    def test_a_reordered_marker_is_not_a_mismatch(self) -> None:
        """German word order moves a marker; only the set of terms is checked."""
        source = _source_document(
            "He designed the [[bombe|machine]] at [[bletchley|the park]]."
        )
        source["events"][0]["annotations"]["bletchley"] = {"explanation": "A site."}
        result = apply_life_events_translations(
            source,
            _translated_payload(
                "In [[bletchley|dem Park]] entwarf er die [[bombe|Maschine]]."
            ),
            {},
        )
        self.assertIn("[[bombe|Maschine]]", result["events"][0]["description"])

    def test_a_renamed_term_is_rejected(self) -> None:
        with self.assertRaises(TranslationMergeError):
            apply_life_events_translations(
                _source_document("He designed the [[bombe|machine]]."),
                _translated_payload("Er entwarf die [[Bombe|Maschine]]."),
                {},
            )

    def test_a_dropped_marker_is_rejected(self) -> None:
        with self.assertRaises(TranslationMergeError):
            apply_life_events_translations(
                _source_document("He designed the [[bombe|machine]]."),
                _translated_payload("Er entwarf die Maschine."),
                {},
            )

    def test_an_invented_marker_is_rejected(self) -> None:
        with self.assertRaises(TranslationMergeError):
            apply_life_events_translations(
                _source_document("He designed the machine."),
                _translated_payload("Er entwarf die [[maschine|Maschine]]."),
                {},
            )


if __name__ == "__main__":
    unittest.main()
