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
    extract_life_events_translatables,
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


class OrphanAnnotationTests(unittest.TestCase):
    """An annotation the description never marks up is not offered for translation.

    `parseDescriptionSegments` reaches an annotation only through its marker, so
    an orphan renders nowhere. Sending one anyway asks the translator to explain
    a term the text does not mark, and it answers by writing the missing marker
    into the translation — which the guard above then rejects, leaving a whole
    document untranslated over an entry no reader could have seen.
    """

    def test_a_marked_annotation_is_extracted(self) -> None:
        payload = extract_life_events_translatables(
            _source_document("He designed the [[bombe|codebreaking machine]].")
        )
        self.assertEqual(
            payload["events"][0]["annotations"],
            [{"term": "bombe", "explanation": "An electromechanical device."}],
        )

    def test_an_orphan_annotation_is_left_out(self) -> None:
        payload = extract_life_events_translatables(
            _source_document("He designed a codebreaking machine.")
        )
        self.assertEqual(payload["events"][0]["annotations"], [])


if __name__ == "__main__":
    unittest.main()
