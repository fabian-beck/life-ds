"""Tests for how a run finds and classifies the death event.

The death closes a story the way the birth opens it, and the same rule applies:
what the slide styles is decided from the dates, not from whether the model
remembered to classify it. The cases below are the ones the corpus actually
holds — a death dated days after the accident that caused it, three events on
the day Stauffenberg died, a life whose sources give no death date at all.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from events.schemas import (  # noqa: E402
    BirthClassification,
    DeathClassification,
    EventSkeleton,
)
from generate_person_events import (  # noqa: E402
    ensure_death_classification,
    find_death_event_index,
)


def skeleton(title, date, age=None, event_class=None, description=""):
    return EventSkeleton(
        date=date,
        date_precision="day" if len(date) == 10 else "year",
        age=age,
        title=title,
        description=description,
        event_class=event_class,
    )


class FindDeathEventTests(unittest.TestCase):
    def test_finds_the_event_dated_on_the_death_date(self) -> None:
        events = [
            skeleton("Opens Copenhagen Institute", "1920", 34),
            skeleton("Death in Copenhagen", "1962-11-18", 77),
        ]
        self.assertEqual(find_death_event_index(events, "1962-11-18"), 1)

    def test_finds_a_death_the_event_opens_days_before(self) -> None:
        # Gaudí was struck by a tram on 7 June and died on 10 June; the event
        # is dated when it started.
        events = [
            skeleton("Works on the Sagrada Família", "1914", 61),
            skeleton(
                "Tram accident and death",
                "1926-06-07",
                73,
                description="He died on 10 June 1926.",
            ),
        ]
        self.assertEqual(find_death_event_index(events, "1926-06-10"), 1)

    def test_takes_the_last_of_several_events_on_the_day(self) -> None:
        # Stauffenberg's plot, its collapse, and his execution share a date.
        events = [
            {"date": "1944-07-20", "title": "Planted bomb at Wolfsschanze"},
            {"date": "1944-07-20", "title": "Tried to trigger Operation Valkyrie"},
            {"date": "1944-07-20", "title": "Executed at Bendlerblock"},
        ]
        self.assertEqual(find_death_event_index(events, "1944-07-20"), 2)

    def test_someone_elses_death_is_not_the_subjects(self) -> None:
        events = [
            skeleton("His wife dies in Zurich", "1948", 69),
            skeleton("Publishes a final paper", "1950", 71),
        ]
        self.assertIsNone(find_death_event_index(events, "1962-11-18"))

    def test_without_a_death_date_the_closing_title_decides(self) -> None:
        named = [{"date": "1962", "title": "Death in Copenhagen"}]
        self.assertEqual(find_death_event_index(named), 0)
        # A closing event that merely mentions a death in its prose does not.
        mentioned = [
            {
                "date": "1962",
                "title": "Final years",
                "description": "He spoke at the memorial after his brother died.",
            }
        ]
        self.assertIsNone(find_death_event_index(mentioned))

    def test_falls_back_to_the_models_classification(self) -> None:
        events = [
            {"date": "1040", "title": "Retires to Kaufungen"},
            {"date": "1040", "title": "Her last day", "event_class": {"type": "death"}},
        ]
        self.assertEqual(find_death_event_index(events), 1)


class EnsureDeathClassificationTests(unittest.TestCase):
    def test_classifies_a_death_the_model_left_plain(self) -> None:
        events = [
            skeleton("Birth in Copenhagen", "1885-10-07", 0, BirthClassification()),
            skeleton("Death in Copenhagen", "1962-11-18", 77),
        ]
        self.assertEqual(ensure_death_classification(events, "1962-11-18"), 1)
        self.assertEqual(events[1].event_class.type, "death")
        # The birth at the other end of the life is left alone.
        self.assertEqual(events[0].event_class.type, "birth")

    def test_keeps_the_cause_the_model_researched(self) -> None:
        classified = DeathClassification(cause="heart failure")
        events = [skeleton("Death in Copenhagen", "1962-11-18", 77, classified)]
        ensure_death_classification(events, "1962-11-18")
        self.assertIs(events[0].event_class, classified)

    def test_drops_a_death_class_from_someone_elses_death(self) -> None:
        events = [
            skeleton("His wife dies", "1948", 69, DeathClassification()),
            skeleton("Death in Copenhagen", "1962-11-18", 77),
        ]
        ensure_death_classification(events, "1962-11-18")
        self.assertIsNone(events[0].event_class)
        self.assertEqual(events[1].event_class.type, "death")


if __name__ == "__main__":
    unittest.main()
