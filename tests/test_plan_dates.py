"""Tests for the dates the proposal and the normalizer must agree on.

The proposal checks its chapters against an order and against the events it
holds, and `enforce_metadata` then writes the file in an order of its own and
drops events it cannot keep. Where the two disagreed, an accepted plan reached
the story with a chapter shown twice or holding a single event.
"""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from events.normalize import (  # noqa: E402
    death_cutoff_date,
    dropped_date_reason,
    enforce_metadata,
    event_sort_key,
    timeline_key,
)


class TimelineKeyTests(unittest.TestCase):
    def test_a_year_and_a_day_of_that_year_order_by_the_start_of_their_period(
        self,
    ) -> None:
        year = {"date": "1945", "date_precision": "year"}
        day = {"date": "1945-01-01", "date_precision": "day"}
        self.assertLess(event_sort_key(day), event_sort_key(year))
        self.assertEqual(event_sort_key(year), timeline_key("1945", "year"))

    def test_an_annotated_date_is_read_by_its_date(self) -> None:
        self.assertEqual(
            timeline_key("1850 (baptized)", "year"), timeline_key("1850", "year")
        )


class DroppedDateTests(unittest.TestCase):
    def test_a_year_only_death_date_allows_the_whole_year(self) -> None:
        self.assertEqual(death_cutoff_date("1954"), date(1954, 12, 31))

    def test_an_unreadable_date_is_dropped(self) -> None:
        self.assertIsNotNone(dropped_date_reason({"date": "unknown"}, None))

    def test_a_period_past_the_death_is_dropped(self) -> None:
        cutoff = death_cutoff_date("1954-06-07")
        event = {"date": "1954", "date_precision": "year"}
        self.assertIn("past the death", dropped_date_reason(event, cutoff) or "")

    def test_the_death_itself_is_kept(self) -> None:
        cutoff = death_cutoff_date("1954-06-07")
        event = {"date": "1954-06-07", "date_precision": "day"}
        self.assertIsNone(dropped_date_reason(event, cutoff))

    def test_the_normalizer_drops_exactly_what_the_reason_names(self) -> None:
        payload = {
            "person": {"name": "Alan Turing", "death_date": "1954-06-07"},
            "events": [
                {"date": "1952-03-31", "date_precision": "day", "title": "Kept"},
                {"date": "1954", "date_precision": "year", "title": "Past the death"},
                {"date": "unknown", "title": "Unreadable"},
            ],
        }
        kept = enforce_metadata(payload, {"title": "Alan Turing"})["events"]
        self.assertEqual([event["title"] for event in kept], ["Kept"])


if __name__ == "__main__":
    unittest.main()
