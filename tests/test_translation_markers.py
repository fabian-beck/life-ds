"""Annotation markers must survive translation with their terms intact.

A description carries its annotations inline as ``[[term|display]]``, or as the
bare ``[[term]]`` the research writes about one marker in eight: the display
text is translated, the term is an id that the document's ``annotations`` map is
keyed by. Both forms are read by the interface, so both are read here. The merge
overlays translated text onto a copy of the English document, so a term the
model dropped or rewrote is not repaired by anything downstream — the annotation
it was the only route to goes dark.

This guard is what makes it safe to translate on the small model: a weaker
translator is allowed to produce flatter prose, not a half-linked document. A
marker the model *added* is the exception, because it costs nothing to undo:
it names no annotation, and both the merge and the interface reduce it to the
display text it wraps.
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

    def test_an_invented_marker_is_stripped_rather_than_fatal(self) -> None:
        """It names nothing, and the interface would strip it at render time."""
        result = apply_life_events_translations(
            _source_document("He designed the machine."),
            _translated_payload("Er entwarf die [[maschine|Maschine]]."),
            {},
        )
        self.assertEqual(result["events"][0]["description"], "Er entwarf die Maschine.")

    def test_a_real_marker_survives_alongside_an_invented_one(self) -> None:
        result = apply_life_events_translations(
            _source_document("He designed the [[bombe|machine]] at the park."),
            _translated_payload("Er entwarf die [[bombe|Maschine]] im [[park|Park]]."),
            {},
        )
        self.assertEqual(
            result["events"][0]["description"],
            "Er entwarf die [[bombe|Maschine]] im Park.",
        )


class BareMarkerTests(unittest.TestCase):
    """`[[term]]` is a marker too, and the translation step has to see it.

    The research is asked for `[[term|display]]` and writes the bare form
    anyway; `parseDescriptionSegments` renders it with the term as its own
    display text. Matched on the pipe alone, such a marker reached neither the
    payload — leaving its explanation in English on a German slide — nor the
    reconciliation that catches a dropped one.
    """

    def test_a_bare_markers_annotation_is_extracted(self) -> None:
        payload = extract_life_events_translatables(
            _source_document("He designed the [[bombe]].")
        )
        self.assertEqual(
            payload["events"][0]["annotations"],
            [{"term": "bombe", "explanation": "An electromechanical device."}],
        )

    def test_a_bare_markers_explanation_is_translated(self) -> None:
        result = apply_life_events_translations(
            _source_document("He designed the [[bombe]]."),
            _translated_payload("Er entwarf die [[bombe]]."),
            {},
        )
        self.assertEqual(
            result["events"][0]["annotations"]["bombe"]["explanation"],
            "Ein elektromechanisches Gerät.",
        )

    def test_a_bare_marker_may_gain_a_display_text(self) -> None:
        """The German wording of the term rides in behind the same id."""
        result = apply_life_events_translations(
            _source_document("He designed the [[bombe]]."),
            _translated_payload("Er entwarf die [[bombe|Entzifferungsmaschine]]."),
            {},
        )
        self.assertEqual(
            result["events"][0]["description"],
            "Er entwarf die [[bombe|Entzifferungsmaschine]].",
        )

    def test_a_dropped_bare_marker_is_rejected(self) -> None:
        with self.assertRaises(TranslationMergeError):
            apply_life_events_translations(
                _source_document("He designed the [[bombe]]."),
                _translated_payload("Er entwarf die Maschine."),
                {},
            )

    def test_an_invented_bare_marker_is_stripped(self) -> None:
        result = apply_life_events_translations(
            _source_document("He designed the machine."),
            _translated_payload("Er entwarf die [[Maschine]]."),
            {},
        )
        self.assertEqual(result["events"][0]["description"], "Er entwarf die Maschine.")


class UnmarkedAnnotationTests(unittest.TestCase):
    """An annotation the description never marks up is offered for translation.

    `parseDescriptionSegments` finds an unmarked term in the prose itself, so
    such an annotation does reach the reader, and roughly one annotation in
    nine is defined without ever being marked. Leaving those out of the payload
    printed their English explanation under a German slide.
    """

    def test_a_marked_annotation_is_extracted(self) -> None:
        payload = extract_life_events_translatables(
            _source_document("He designed the [[bombe|codebreaking machine]].")
        )
        self.assertEqual(
            payload["events"][0]["annotations"],
            [{"term": "bombe", "explanation": "An electromechanical device."}],
        )

    def test_an_unmarked_annotation_is_extracted_too(self) -> None:
        payload = extract_life_events_translatables(
            _source_document("He designed a codebreaking machine.")
        )
        self.assertEqual(
            payload["events"][0]["annotations"],
            [{"term": "bombe", "explanation": "An electromechanical device."}],
        )

    def test_a_marker_answered_for_an_unmarked_annotation_is_stripped(self) -> None:
        """Offering the annotation must not let the translator mark up the text."""
        result = apply_life_events_translations(
            _source_document("He designed a codebreaking machine."),
            _translated_payload("Er entwarf eine [[bombe|Entzifferungsmaschine]]."),
            {},
        )
        self.assertEqual(
            result["events"][0]["description"],
            "Er entwarf eine Entzifferungsmaschine.",
        )
        self.assertEqual(
            result["events"][0]["annotations"]["bombe"]["explanation"],
            "Ein elektromechanisches Gerät.",
        )


if __name__ == "__main__":
    unittest.main()
