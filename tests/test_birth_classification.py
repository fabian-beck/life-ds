"""Tests for how a run finds and classifies the birth event.

The birth is what the story slide styles as a birth, so a missed one costs the
reader the parents and a stray one styles a child's birth as the subject's.
Both are decided deterministically rather than left to the model, and that is
what these tests hold.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import backfill_birth_events as backfill  # noqa: E402
from generate_person_events import (  # noqa: E402
    BirthClassification,
    EventSkeleton,
    MarriagePartnershipClassification,
    ensure_birth_classification,
    find_birth_event_index,
)


def skeleton(title, date, age, event_class=None, description=""):
    return EventSkeleton(
        date=date,
        date_precision="day" if len(date) == 10 else "year",
        age=age,
        title=title,
        description=description,
        event_class=event_class,
    )


class FindBirthEventTests(unittest.TestCase):
    def test_finds_the_event_dated_at_age_zero(self) -> None:
        events = [
            skeleton("Birth in Copenhagen", "1885-10-07", 0),
            skeleton("Enters university", "1903", 17),
        ]
        self.assertEqual(find_birth_event_index(events, "1885-10-07"), 0)

    def test_reads_plain_dicts_from_a_stored_dataset(self) -> None:
        events = [
            {"date": "1885-10-07", "age": 0, "title": "Birth in Copenhagen"},
            {"date": "1912", "age": 26, "title": "Marries"},
        ]
        self.assertEqual(find_birth_event_index(events, "1885-10-07"), 0)

    def test_falls_back_to_the_models_classification(self) -> None:
        # No event is dated at the birth — a medieval life whose events carry
        # no ages at all — so what the model classified is all there is.
        events = [
            {"date": "0999", "title": "Crowned queen"},
            {"date": "0975", "title": "Born", "event_class": {"type": "birth"}},
        ]
        self.assertEqual(find_birth_event_index(events), 1)

    def test_the_date_outranks_a_misplaced_classification(self) -> None:
        events = [
            {"date": "1885-10-07", "age": 0, "title": "Birth in Copenhagen"},
            {
                "date": "1916",
                "age": 30,
                "title": "A son",
                "event_class": {"type": "birth"},
            },
        ]
        self.assertEqual(find_birth_event_index(events, "1885-10-07"), 0)

    def test_a_childs_birth_is_not_the_subjects(self) -> None:
        events = [
            skeleton("Enters university", "1903", 17),
            skeleton("Birth of his first son", "1916", 30),
        ]
        self.assertIsNone(find_birth_event_index(events, "1885-10-07"))

    def test_a_story_that_opens_after_the_birth_has_none(self) -> None:
        events = [skeleton("Crowned queen", "1002", 27)]
        self.assertIsNone(find_birth_event_index(events))


class EnsureBirthClassificationTests(unittest.TestCase):
    def test_classifies_a_birth_the_model_left_plain(self) -> None:
        events = [
            skeleton("Birth in Copenhagen", "1885-10-07", 0),
            skeleton("Enters university", "1903", 17),
        ]
        self.assertEqual(ensure_birth_classification(events, "1885-10-07"), 0)
        self.assertEqual(events[0].event_class.type, "birth")
        self.assertIsNone(events[1].event_class)

    def test_keeps_what_the_model_researched(self) -> None:
        classified = BirthClassification(father="Christian Bohr")
        events = [skeleton("Birth in Copenhagen", "1885-10-07", 0, classified)]
        ensure_birth_classification(events, "1885-10-07")
        self.assertIs(events[0].event_class, classified)

    def test_drops_a_birth_class_from_a_later_event(self) -> None:
        events = [
            skeleton("Birth in Copenhagen", "1885-10-07", 0),
            skeleton("His son is born", "1916", 30, BirthClassification()),
        ]
        ensure_birth_classification(events, "1885-10-07")
        self.assertEqual(events[0].event_class.type, "birth")
        self.assertIsNone(events[1].event_class)

    def test_leaves_other_classifications_alone(self) -> None:
        marriage = MarriagePartnershipClassification(
            subtype="marriage", partner="Margrethe Nørlund"
        )
        events = [
            skeleton("Birth in Copenhagen", "1885-10-07", 0),
            skeleton("Marries", "1912", 26, marriage),
        ]
        ensure_birth_classification(events, "1885-10-07")
        self.assertIs(events[1].event_class, marriage)


class BackfillTests(unittest.TestCase):
    def test_reads_a_qualified_parent_role(self) -> None:
        self.assertEqual(backfill.family_role("family/step_father"), "father")
        self.assertEqual(backfill.family_role("family/adoptive-mother"), "mother")
        self.assertIsNone(backfill.family_role("academic/mentor"))
        self.assertIsNone(backfill.family_role("family"))

    def test_stored_values_win_over_derived_ones(self) -> None:
        built = backfill.build_birth_class(
            {"type": "birth", "father": "Christian Bohr", "birth_name": "Niels Henrik"},
            {"father": "C. Bohr", "mother": "Ellen Adler Bohr"},
        )
        self.assertEqual(
            built,
            {
                "type": "birth",
                "father": "Christian Bohr",
                "birth_name": "Niels Henrik",
                "mother": "Ellen Adler Bohr",
            },
        )

    def test_replaces_a_classification_of_another_type(self) -> None:
        built = backfill.build_birth_class(
            {"type": "migration", "from_location": "Denmark"},
            {"mother": "Ellen Adler Bohr"},
        )
        self.assertEqual(built, {"type": "birth", "mother": "Ellen Adler Bohr"})


if __name__ == "__main__":
    unittest.main()
