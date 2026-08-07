"""Tests for the English-title checker.

The checker's risky part is not spotting "Warschau" — that is a table lookup.
It is leaving alone the German that belongs in an English title: a quoted work
title, a name particle, a company name. Every title below is one the corpus
actually holds.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import validate_event_titles as titles  # noqa: E402


def messages(person_id: str, title: str) -> list[str]:
    return [f.message for f in titles.check_title(person_id, "1900", title)]


class GermanLeftStandingTests(unittest.TestCase):
    def test_a_german_city_with_an_english_name_is_flagged(self) -> None:
        for title, german in [
            ("Warschau music and collapse", "Warschau"),
            ("Plenary address at Zürich ICM", "Zürich"),
            ("Appointed in Zürich", "Zürich"),
        ]:
            with self.subTest(title=title):
                self.assertTrue(
                    any(german in m for m in messages("someone", title)), title
                )

    def test_a_german_function_word_is_flagged(self) -> None:
        for title in [
            "Wolf unter Wölfen published",
            "Founds the Institut für Leichtbau",
            "Moves nach Berlin",
        ]:
            with self.subTest(title=title):
                self.assertTrue(messages("someone", title), title)


class LeftAloneTests(unittest.TestCase):
    def test_an_english_city_name_is_not_a_german_one(self) -> None:
        for title in [
            "Crowned Holy Roman Empress",  # Rome, not "Rom"
            "Birth in Prague",  # Prague, not "Prag"
            "KunstHausWien opens",  # Wien inside a proper name
        ]:
            with self.subTest(title=title):
                self.assertEqual(messages("someone", title), [])

    def test_a_german_word_title_in_quotation_marks_stays(self) -> None:
        for title in [
            'Published "Das doppelte Lottchen"',
            'Published "Herz auf Taille"',
            'Publishes "Das hängende Dach" and teaches abroad',
        ]:
            with self.subTest(title=title):
                self.assertEqual(messages("someone", title), [])

    def test_a_name_particle_is_not_a_preposition(self) -> None:
        for title in [
            "Married Nina von Lerchenfeld",
            "Married Marie Helena Susanna von Tucher",
        ]:
            with self.subTest(title=title):
                self.assertEqual(messages("someone", title), [])

    def test_an_uppercase_acronym_is_not_a_german_word(self) -> None:
        for title in ["Teaches at MIT", "Joined MIT faculty"]:
            with self.subTest(title=title):
                self.assertEqual(messages("someone", title), [])

    def test_a_reviewed_exception_is_accepted_for_its_own_person_only(self) -> None:
        self.assertEqual(messages("heinz_nixdorf", "Founds Labor für Impulstechnik"), [])
        self.assertTrue(messages("someone_else", "Founds Labor für Impulstechnik"))


class CorpusTests(unittest.TestCase):
    def test_the_shipped_english_titles_are_english(self) -> None:
        findings = []
        for path in sorted(titles.PEOPLE_DIR.glob("*/life_events.json")):
            import json

            data = json.loads(path.read_text(encoding="utf-8"))
            findings.extend(titles.check_person(path.parent.name, data))
        self.assertEqual([str(f) for f in findings], [])


if __name__ == "__main__":
    unittest.main()
