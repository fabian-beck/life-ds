"""Chapter assignment must not lose event fields.

`assign_events_to_chapters` used to rebuild each event through a field-by-field
constructor, which silently dropped every field it did not name. It did, three
times: image attribution first, then background, weight, and background_images
— a whole generation run's Phase 2 prose paid for and discarded two steps
later. The function now copies the event, and this test holds it to that: the
sample below populates every field `LifeEvent` declares, so a field the schema
grows fails the coverage check until a sample proves it survives.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from events.schemas import LifeChapter, LifeEvent  # noqa: E402
from events.pipeline import (  # noqa: E402
    assign_events_to_chapters,
    clamp_chapter_bounds,
)

# One value for every field of LifeEvent, all of them distinguishable from the
# field's default, so a dropped field cannot hide behind a default that happens
# to match. `chapter` carries a stale value the assignment must overwrite.
EVENT_SAMPLE = {
    "date": "1936-11-12",
    "date_precision": "day",
    "date_end": "1937-01-30",
    "date_end_precision": "day",
    "date_note": "published in two parts",
    "age": 24,
    "title": "Publishes On Computable Numbers",
    "description": "The paper introduces the [[universal_machine|universal machine]].",
    "locations": [
        {
            "name_historic": "Cambridge",
            "name_modern": "Cambridge, United Kingdom",
            "centroid": [52.2053, 0.1218],
            "primary": True,
        }
    ],
    "involved_people": ["Max Newman"],
    "sources": ["https://en.wikipedia.org/wiki/On_Computable_Numbers"],
    "images": [
        {
            "url": "https://upload.wikimedia.org/turing_paper.jpg",
            "caption": "First page of the 1936 paper",
            "source": "https://commons.wikimedia.org/wiki/File:Turing_paper.jpg",
            "creator": "London Mathematical Society",
            "license": "Public domain",
            "licenseUrl": "https://creativecommons.org/publicdomain/mark/1.0/",
        }
    ],
    "event_type_icon": "mdi-file-document",
    "chapter": "stale_chapter_id",
    "annotations": {
        "universal_machine": {
            "explanation": "A machine that can simulate any other machine.",
            "wikipedia_url": "https://en.wikipedia.org/wiki/Universal_Turing_machine",
        }
    },
    "background": "Hilbert's Entscheidungsproblem had stood open since 1928.\n\nNewman's lectures posed it to the class that spring.",
    "background_images": [
        {
            "url": "https://upload.wikimedia.org/hilbert.jpg",
            "caption": "David Hilbert in 1912",
            "source": "https://commons.wikimedia.org/wiki/File:Hilbert.jpg",
        }
    ],
    "weight": 0.9,
    "event_class": {
        "type": "publication",
        "title": "On Computable Numbers",
        "publication_type": "paper",
        "publisher": "Proceedings of the London Mathematical Society",
        "significance": "seminal work",
        "impact": "Founded computability theory.",
    },
}

CHAPTERS = [
    LifeChapter(
        id="cambridge_years",
        headline="The Cambridge Years",
        date_start="1931",
        date_start_precision="year",
        date_end="1938",
        date_end_precision="year",
    ),
    LifeChapter(
        id="war_years",
        headline="The War Years",
        date_start="1939",
        date_start_precision="year",
        date_end="1945",
        date_end_precision="year",
    ),
]


class FieldPreservationTests(unittest.TestCase):
    def test_sample_covers_every_field(self) -> None:
        self.assertEqual(
            set(EVENT_SAMPLE),
            set(LifeEvent.model_fields),
            "LifeEvent grew or lost a field. Update EVENT_SAMPLE so this test "
            "can prove the field survives chapter assignment.",
        )

    def test_every_field_survives_chapter_assignment(self) -> None:
        event = LifeEvent(**EVENT_SAMPLE)
        expected = event.model_dump()
        expected["chapter"] = "cambridge_years"

        (updated,) = assign_events_to_chapters([event], CHAPTERS)

        self.assertEqual(updated.model_dump(), expected)

    def test_fallback_to_last_chapter_preserves_fields_too(self) -> None:
        event = LifeEvent(**{**EVENT_SAMPLE, "date": "1952-03-31"})
        expected = event.model_dump()
        expected["chapter"] = "war_years"

        (updated,) = assign_events_to_chapters([event], CHAPTERS)

        self.assertEqual(updated.model_dump(), expected)


if __name__ == "__main__":
    unittest.main()


class ChapterBoundClampTests(unittest.TestCase):
    """The Planck failure, replayed: a chapter opened on the day his son was
    executed while the Göttingen move carried only a year, so the move began
    before the chapter that held it."""

    def chapter(self, **overrides):
        fields = {
            "id": "after_the_ruins",
            "headline": "After the Ruins",
            "date_start": "1945-01-23",
            "date_start_precision": "day",
            "date_end": "1947-10-04",
            "date_end_precision": "day",
        }
        fields.update(overrides)
        return LifeChapter(**fields)

    def event(self, date, precision, **overrides):
        fields = {
            **EVENT_SAMPLE,
            "date": date,
            "date_precision": precision,
            "date_end": None,
            "date_end_precision": None,
            "chapter": "after_the_ruins",
        }
        fields.update(overrides)
        return LifeEvent(**fields)

    def test_a_coarse_event_widens_the_chapter_start(self) -> None:
        events = [
            self.event("1945-01-23", "day"),
            self.event("1945", "year"),
            self.event("1947-10-04", "day"),
        ]
        (clamped,) = clamp_chapter_bounds([self.chapter()], events)
        self.assertEqual(clamped.date_start, "1945")
        self.assertEqual(clamped.date_start_precision, "year")
        self.assertEqual(clamped.date_end, "1947-10-04")

    def test_a_spilling_date_end_widens_the_chapter_end(self) -> None:
        events = [
            self.event(
                "1945-01-23",
                "day",
                date_end="1948",
                date_end_precision="year",
            )
        ]
        (clamped,) = clamp_chapter_bounds([self.chapter()], events)
        self.assertEqual(clamped.date_end, "1948")
        self.assertEqual(clamped.date_end_precision, "year")

    def test_covered_events_leave_the_chapter_alone(self) -> None:
        events = [
            self.event("1945-01-23", "day"),
            self.event("1946-05", "month"),
        ]
        (clamped,) = clamp_chapter_bounds([self.chapter()], events)
        self.assertEqual(clamped.date_start, "1945-01-23")
        self.assertEqual(clamped.date_start_precision, "day")

    def test_an_empty_chapter_is_untouched(self) -> None:
        (clamped,) = clamp_chapter_bounds([self.chapter()], [])
        self.assertEqual(clamped.date_start, "1945-01-23")
