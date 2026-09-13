"""A cited Wikipedia URL names the article the cache actually holds.

The related articles behind a network are not all English: the search falls
back to the German Wikipedia for a person English Wikipedia does not carry,
and each cached entry records the URL it came from. The model is shown that
URL and composes an English one from the title anyway, which is a dead link
whenever the two languages spell the name differently — Babbage's network
cited `en.wikipedia.org/wiki/Georg_Scheutz`, while English Wikipedia calls him
Per Georg Scheutz, so the chip's source led to a "no article" page.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import generate_person_network as generator  # noqa: E402

RELATED = [
    {"title": "Georg Scheutz", "url": "https://de.wikipedia.org/wiki/Georg_Scheutz"},
    {"title": "Ada Lovelace", "url": "https://en.wikipedia.org/wiki/Ada_Lovelace"},
]


def _connection(*sources):
    return {"person_name": "Someone", "sources": list(sources)}


class RepairSourceUrlsTests(unittest.TestCase):
    def test_a_german_article_is_cited_at_its_own_url(self) -> None:
        connection = _connection("https://en.wikipedia.org/wiki/Georg_Scheutz")
        repaired = generator.repair_source_urls([connection], RELATED)
        self.assertEqual(
            connection["sources"], ["https://de.wikipedia.org/wiki/Georg_Scheutz"]
        )
        self.assertEqual(
            repaired,
            [
                (
                    "https://en.wikipedia.org/wiki/Georg_Scheutz",
                    "https://de.wikipedia.org/wiki/Georg_Scheutz",
                )
            ],
        )

    def test_an_article_already_cited_correctly_is_left_alone(self) -> None:
        connection = _connection("https://en.wikipedia.org/wiki/Ada_Lovelace")
        self.assertEqual(generator.repair_source_urls([connection], RELATED), [])
        self.assertEqual(
            connection["sources"], ["https://en.wikipedia.org/wiki/Ada_Lovelace"]
        )

    def test_a_title_the_cache_does_not_hold_is_not_guessed_at(self) -> None:
        """Guessing which article was meant is what produced the dead link."""
        connection = _connection("https://en.wikipedia.org/wiki/Someone_Else")
        self.assertEqual(generator.repair_source_urls([connection], RELATED), [])
        self.assertEqual(
            connection["sources"], ["https://en.wikipedia.org/wiki/Someone_Else"]
        )

    def test_a_repair_that_meets_an_existing_citation_does_not_duplicate_it(
        self,
    ) -> None:
        connection = _connection(
            "https://en.wikipedia.org/wiki/Georg_Scheutz",
            "https://de.wikipedia.org/wiki/Georg_Scheutz",
        )
        generator.repair_source_urls([connection], RELATED)
        self.assertEqual(
            connection["sources"], ["https://de.wikipedia.org/wiki/Georg_Scheutz"]
        )

    def test_a_non_wikipedia_source_is_carried_through(self) -> None:
        connection = _connection("https://doi.org/10.1109/MAHC.2003.1253887")
        generator.repair_source_urls([connection], RELATED)
        self.assertEqual(
            connection["sources"], ["https://doi.org/10.1109/MAHC.2003.1253887"]
        )

    def test_nothing_is_rewritten_without_a_cache_to_check_against(self) -> None:
        connection = _connection("https://en.wikipedia.org/wiki/Georg_Scheutz")
        self.assertEqual(generator.repair_source_urls([connection], []), [])
        self.assertEqual(
            connection["sources"], ["https://en.wikipedia.org/wiki/Georg_Scheutz"]
        )


if __name__ == "__main__":
    unittest.main()
