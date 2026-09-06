"""Tests for applying reviewer-proposed changes to person data.

The review step is only worth running if what it decides reaches the
application. Locations are the case that failed silently: they were written to
a key nothing reads, so a corrected place looked applied and changed nothing.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from utils.review_helpers import apply_event_changes  # noqa: E402
from utils.review_models import (  # noqa: E402
    Annotation,
    EventChanges,
    EventsChanges,
    LocationObject,
)


def _events() -> dict:
    return {
        "events": [
            {
                "title": "Passes the Abitur",
                "locations": [
                    {
                        "name_historic": "Berlin",
                        "name_modern": "Berlin, Germany",
                        "centroid": [13.39, 52.51],
                        "primary": True,
                    }
                ],
            }
        ]
    }


def _publication_events(impact: str | None = None) -> dict:
    event_class = {
        "type": "publication",
        "title": "The Metamorphosis",
        "publication_type": "book",
    }
    if impact is not None:
        event_class["impact"] = impact
    return {"events": [{"title": "Publishes The Metamorphosis", "event_class": event_class}]}


def _change(**kwargs) -> EventsChanges:
    defaults = {"event_index": 0, "confidence": 5, "rationale": "because"}
    return EventsChanges(events=[EventChanges(**{**defaults, **kwargs})])


class ApplyEventChangesTests(unittest.TestCase):
    def test_corrected_locations_land_in_the_field_the_app_reads(self) -> None:
        changes = _change(
            new_locations=[
                LocationObject(
                    name_historic="Hoyerswerda",
                    name_modern="Hoyerswerda, Germany",
                    primary=True,
                )
            ]
        )
        updated, applied, _ = apply_event_changes(_events(), changes)
        event = updated["events"][0]

        self.assertEqual(applied, 1)
        self.assertNotIn("location_coordinates", event)
        self.assertEqual(
            event["locations"],
            [
                {
                    "name_historic": "Hoyerswerda",
                    "name_modern": "Hoyerswerda, Germany",
                    "primary": True,
                }
            ],
        )

    def test_the_reviewer_cannot_supply_coordinates(self) -> None:
        self.assertNotIn("centroid", LocationObject.model_fields)

    def test_untouched_locations_keep_their_coordinates(self) -> None:
        updated, _, _ = apply_event_changes(_events(), _change(new_title="Abitur"))
        self.assertEqual(
            updated["events"][0]["locations"][0]["centroid"], [13.39, 52.51]
        )

    def test_the_original_data_is_not_mutated(self) -> None:
        original = _events()
        apply_event_changes(
            original,
            _change(
                new_locations=[LocationObject(name_historic="Dresden", primary=True)]
            ),
        )
        self.assertEqual(
            original["events"][0]["locations"][0]["name_historic"], "Berlin"
        )

    def test_a_content_summary_impact_is_rewritten_in_place(self) -> None:
        events = _publication_events(impact="The novella presented a family crisis.")
        updated, applied, _ = apply_event_changes(
            events, _change(new_impact="The novella became a landmark of modernism.")
        )
        self.assertEqual(applied, 1)
        self.assertEqual(
            updated["events"][0]["event_class"]["impact"],
            "The novella became a landmark of modernism.",
        )

    def test_an_empty_impact_removes_the_key_like_a_fresh_generation(self) -> None:
        events = _publication_events(impact="The novella presented a family crisis.")
        updated, applied, _ = apply_event_changes(events, _change(new_impact=""))
        self.assertEqual(applied, 1)
        self.assertNotIn("impact", updated["events"][0]["event_class"])

    def test_an_impact_without_a_classification_to_carry_it_is_skipped(self) -> None:
        updated, applied, skipped = apply_event_changes(
            _events(), _change(new_impact="Reached a wide readership.")
        )
        self.assertEqual((applied, skipped), (0, 1))
        self.assertNotIn("event_class", updated["events"][0])

    def test_a_low_confidence_location_is_skipped(self) -> None:
        changes = _change(
            confidence=2,
            new_locations=[LocationObject(name_historic="Dresden", primary=True)],
        )
        updated, applied, skipped = apply_event_changes(
            _events(), changes, min_confidence=4
        )
        self.assertEqual((applied, skipped), (0, 1))
        self.assertEqual(
            updated["events"][0]["locations"][0]["name_historic"], "Berlin"
        )

    def test_added_annotation_keeps_the_ones_the_event_already_had(self) -> None:
        """A reviewer returns the gloss it adds, not the whole map."""
        data = {
            "events": [
                {
                    "title": "Graduated from King's College",
                    "description": (
                        "His dissertation proved a version of the [[central limit "
                        "theorem|central limit theorem]] at [[King's College|King's]]."
                    ),
                    "annotations": {
                        "King's College": {"explanation": "A Cambridge college."}
                    },
                }
            ]
        }
        changes = _change(
            new_annotations={
                "central limit theorem": Annotation(
                    explanation="Sums of many independent quantities tend to a normal distribution."
                )
            }
        )
        updated, applied, _ = apply_event_changes(data, changes)
        annotations = updated["events"][0]["annotations"]

        self.assertEqual(applied, 1)
        self.assertEqual(set(annotations), {"King's College", "central limit theorem"})
        self.assertEqual(
            annotations["central limit theorem"]["explanation"],
            "Sums of many independent quantities tend to a normal distribution.",
        )


if __name__ == "__main__":
    unittest.main()
