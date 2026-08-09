"""Tests for the review pass's date_end correction.

The Planck review saw a family-losses event whose prose reached 1919 while
its metadata ended in 1917, and its schema had no date field to fix it with.
The field exists now, held to three rules: the anchor date stays untouchable,
the precision is read off the value rather than trusted, and an end before
the anchor is refused.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from utils.review_helpers import apply_event_changes  # noqa: E402
from utils.review_models import EventChanges, EventsChanges  # noqa: E402


def losses_event():
    return {
        "events": [
            {
                "date": "1909-10-17",
                "date_precision": "day",
                "date_end": "1917",
                "date_end_precision": "year",
                "title": "Endured Family Losses",
                "description": "…died in childbirth in 1917 and 1919.",
            }
        ]
    }


def propose(date_end):
    return EventsChanges(
        events=[
            EventChanges(
                event_index=0,
                new_date_end=date_end,
                confidence=5,
                rationale="the prose reaches 1919",
            )
        ]
    )


class DateEndTests(unittest.TestCase):
    def test_the_planck_correction_is_applied(self) -> None:
        updated, applied, skipped = apply_event_changes(losses_event(), propose("1919"))
        self.assertEqual(updated["events"][0]["date_end"], "1919")
        self.assertEqual(updated["events"][0]["date_end_precision"], "year")
        self.assertEqual((applied, skipped), (1, 0))

    def test_precision_is_read_off_the_value(self) -> None:
        updated, _, _ = apply_event_changes(losses_event(), propose("1919-07"))
        self.assertEqual(updated["events"][0]["date_end_precision"], "month")

    def test_an_end_before_the_anchor_is_refused(self) -> None:
        updated, applied, skipped = apply_event_changes(losses_event(), propose("1905"))
        self.assertEqual(updated["events"][0]["date_end"], "1917")
        self.assertEqual((applied, skipped), (0, 1))

    def test_a_non_date_is_refused(self) -> None:
        updated, applied, skipped = apply_event_changes(
            losses_event(), propose("circa 1919")
        )
        self.assertEqual(updated["events"][0]["date_end"], "1917")
        self.assertEqual((applied, skipped), (0, 1))


if __name__ == "__main__":
    unittest.main()
