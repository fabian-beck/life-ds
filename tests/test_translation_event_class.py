"""An event's classification is data the reader sees, so it is translated.

``event_class`` holds both prose and machine tokens. The prose — a marriage's
characterization, an invention's description, a publication's significance —
used to be excluded from the payload with the coordinates and the URLs, which
left a German slide reading "Marriage · close collaboration · 6 children". The
tokens still stay verbatim: the interface names them from its locale files, and
``partner`` is a name the interface looks the spouse up in the network by, so
it follows the name glossary rather than the translator.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from translate_person import (  # noqa: E402
    apply_life_events_translations,
    collect_person_names,
    compute_fingerprint,
    extract_life_events_translatables,
)


def _document(event_class: dict) -> dict:
    return {
        "person": {"summary": "A summary.", "primary_roles": ["Physicist"]},
        "chapters": [],
        "events": [
            {
                "title": "Marries Margrethe Nørlund",
                "description": "The couple married in a civil ceremony.",
                "locations": [],
                "images": [],
                "event_class": event_class,
            }
        ],
    }


def _payload(event_class: dict) -> dict:
    return {
        "person": {"summary": "Eine Zusammenfassung.", "primary_roles": ["Physiker"]},
        "chapters": [],
        "events": [
            {
                "title": "Heiratet Margrethe Nørlund",
                "description": "Das Paar heiratete standesamtlich.",
                "locations": [],
                "images": [],
                "annotations": [],
                "event_class": event_class,
            }
        ],
    }


MARRIAGE = {
    "type": "marriage_partnership",
    "subtype": "marriage",
    "partner": "Margrethe Nørlund",
    "duration": "until his death",
    "children": 6,
    "characterization": "devoted partnership",
}


class EventClassExtractionTests(unittest.TestCase):
    def test_only_the_prose_reaches_the_model(self) -> None:
        payload = extract_life_events_translatables(_document(dict(MARRIAGE)))
        self.assertEqual(
            payload["events"][0]["event_class"],
            {"duration": "until his death", "characterization": "devoted partnership"},
        )

    def test_an_unclassified_event_carries_no_block(self) -> None:
        """Absent rather than null, so those documents keep their fingerprint."""
        document = _document(dict(MARRIAGE))
        del document["events"][0]["event_class"]
        payload = extract_life_events_translatables(document)
        self.assertNotIn("event_class", payload["events"][0])

    def test_a_block_with_no_prose_is_left_out(self) -> None:
        payload = extract_life_events_translatables(
            _document({"type": "publication", "publication_type": "book"})
        )
        self.assertNotIn("event_class", payload["events"][0])

    def test_a_technical_edit_does_not_invalidate_a_translation(self) -> None:
        before = compute_fingerprint(
            extract_life_events_translatables(_document(dict(MARRIAGE)))
        )
        changed = dict(MARRIAGE)
        changed["children"] = 7
        after = compute_fingerprint(
            extract_life_events_translatables(_document(changed))
        )
        self.assertEqual(before, after)

    def test_rewritten_prose_does_invalidate_it(self) -> None:
        before = compute_fingerprint(
            extract_life_events_translatables(_document(dict(MARRIAGE)))
        )
        changed = dict(MARRIAGE)
        changed["characterization"] = "close collaboration"
        after = compute_fingerprint(
            extract_life_events_translatables(_document(changed))
        )
        self.assertNotEqual(before, after)


class EventClassMergeTests(unittest.TestCase):
    def test_the_prose_is_overlaid(self) -> None:
        result = apply_life_events_translations(
            _document(dict(MARRIAGE)),
            _payload(
                {
                    "duration": "bis zu seinem Tod",
                    "characterization": "innige Partnerschaft",
                }
            ),
            {},
        )
        event_class = result["events"][0]["event_class"]
        self.assertEqual(event_class["duration"], "bis zu seinem Tod")
        self.assertEqual(event_class["characterization"], "innige Partnerschaft")

    def test_the_tokens_survive_untouched(self) -> None:
        result = apply_life_events_translations(
            _document(dict(MARRIAGE)),
            _payload({"type": "Ehe", "subtype": "Ehe", "children": 3}),
            {},
        )
        event_class = result["events"][0]["event_class"]
        self.assertEqual(event_class["type"], "marriage_partnership")
        self.assertEqual(event_class["subtype"], "marriage")
        self.assertEqual(event_class["children"], 6)

    def test_a_field_the_source_lacks_is_not_invented(self) -> None:
        source = dict(MARRIAGE)
        del source["characterization"]
        result = apply_life_events_translations(
            _document(source),
            _payload({"characterization": "innige Partnerschaft"}),
            {},
        )
        self.assertNotIn("characterization", result["events"][0]["event_class"])

    def test_the_partner_follows_the_name_glossary(self) -> None:
        """The spouse chip is an exact-name lookup into the localized network."""
        source = dict(MARRIAGE)
        source["partner"] = "Henry II"
        result = apply_life_events_translations(
            _document(source), _payload({}), {"Henry II": "Heinrich II."}
        )
        self.assertEqual(
            result["events"][0]["event_class"]["partner"], "Heinrich II."
        )

    def test_the_partner_is_in_the_glossary_to_begin_with(self) -> None:
        names = collect_person_names(_document(dict(MARRIAGE)), None, None)
        self.assertIn("Margrethe Nørlund", names)


if __name__ == "__main__":
    unittest.main()
