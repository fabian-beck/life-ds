"""Tests for the cross-person consistency checker.

Two people in the corpus lived the same coronation and the corpus dated it
twice. The checker's risky part is telling that shape apart from the ordinary
case of two people who were in the same city in the same year for different
reasons, which the corpus holds far more of.
"""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import validate_cross_person_events as cross  # noqa: E402


def event(date, precision, place, people, title="x", **extra):
    return {
        "date": date,
        "date_precision": precision,
        "title": title,
        "locations": [{"name_historic": place, "primary": True}],
        "involved_people": people,
        **extra,
    }


def contradictions(people):
    return [
        c
        for c in cross.find_candidates(people)
        if c.contradicts and c.key not in cross.ACCEPTED
    ]


class PeriodTests(unittest.TestCase):
    def test_a_coarse_date_covers_its_whole_period(self) -> None:
        start, end = cross.period("1915", "year")
        self.assertEqual((start.year, start.month), (1915, 1))
        self.assertEqual((end.year, end.month), (1916, 1))
        start, end = cross.period("1787-05", "month")
        self.assertEqual((start.month, end.month), (5, 6))

    def test_december_rolls_into_the_next_year(self) -> None:
        _, end = cross.period("1980-12", "month")
        self.assertEqual((end.year, end.month), (1981, 1))


class ContradictionTests(unittest.TestCase):
    def test_one_occasion_dated_twice_is_reported(self) -> None:
        people = {
            "cunigunde": {
                "person": {"name": "Cunigunde"},
                "events": [
                    event(
                        "1002-07-09", "day", "Mainz", ["Otto III"], "Shares coronation"
                    )
                ],
            },
            "henry": {
                "person": {"name": "Henry II"},
                "events": [
                    event("1002-06-07", "day", "Mainz", ["Otto III"], "Elected king")
                ],
            },
        }
        found = contradictions(people)
        self.assertEqual(len(found), 1)
        self.assertIn("mainz / mainz", str(found[0]))

    def test_agreeing_records_of_one_occasion_are_not_reported(self) -> None:
        people = {
            "ada": {
                "person": {"name": "Ada Lovelace"},
                "events": [event("1833-06-05", "day", "London", ["Mary Somerville"])],
            },
            "babbage": {
                "person": {"name": "Charles Babbage"},
                "events": [event("1833-06-05", "day", "London", ["Mary Somerville"])],
            },
        }
        self.assertEqual(contradictions(people), [])

    def test_a_coarse_date_containing_a_precise_one_is_not_a_contradiction(
        self,
    ) -> None:
        people = {
            "hilbert": {
                "person": {"name": "David Hilbert"},
                "events": [event("1915", "year", "Göttingen", ["Felix Klein"])],
            },
            "noether": {
                "person": {"name": "Emmy Noether"},
                "events": [event("1915-04", "month", "Göttingen", ["Felix Klein"])],
            },
        }
        self.assertEqual(contradictions(people), [])

    def test_different_places_are_two_occasions_however_they_are_dated(self) -> None:
        people = {
            "a": {
                "person": {"name": "A"},
                "events": [event("1776-03-31", "day", "Braintree", ["John Adams"])],
            },
            "b": {
                "person": {"name": "B"},
                "events": [event("1776-07-04", "day", "Philadelphia", ["John Adams"])],
            },
        }
        self.assertEqual(contradictions(people), [])

    def test_events_a_year_apart_are_never_compared(self) -> None:
        people = {
            "a": {
                "person": {"name": "A"},
                "events": [event("1900", "year", "Rome", ["X"])],
            },
            "b": {
                "person": {"name": "B"},
                "events": [event("1910", "year", "Rome", ["X"])],
            },
        }
        self.assertEqual(cross.find_candidates(people), [])

    def test_strangers_who_share_no_participant_are_never_compared(self) -> None:
        people = {
            "a": {
                "person": {"name": "A"},
                "events": [event("1900", "year", "Rome", ["X"])],
            },
            "b": {
                "person": {"name": "B"},
                "events": [event("1900", "year", "Rome", ["Y"])],
            },
        }
        self.assertEqual(cross.find_candidates(people), [])


class CorpusTests(unittest.TestCase):
    def test_the_shipped_corpus_holds_no_contradiction(self) -> None:
        people = cross.load_people([])
        self.assertEqual([str(c) for c in contradictions(people)], [])

    def test_the_check_would_have_caught_the_coronation(self) -> None:
        people = cross.load_people(["cunigunde_of_luxembourg", "henry_ii"])
        people["cunigunde_of_luxembourg"] = copy.deepcopy(
            people["cunigunde_of_luxembourg"]
        )
        people["cunigunde_of_luxembourg"]["events"][2]["date"] = "1002-07-09"
        self.assertEqual(len(contradictions(people)), 1)


if __name__ == "__main__":
    unittest.main()
