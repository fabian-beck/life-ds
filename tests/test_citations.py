"""Tests for the rule that a step cites only the articles it was shown."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from utils.citations import citable_urls, keep_citable  # noqa: E402

SUBJECT = "https://en.wikipedia.org/wiki/Charles_Babbage"
RELATED = [
    {
        "title": "Per Georg Scheutz",
        "url": "https://en.wikipedia.org/wiki/Per_Georg_Scheutz",
    }
]


class CitationTests(unittest.TestCase):
    def test_a_composed_url_is_dropped_and_a_shown_one_kept(self) -> None:
        allowed = citable_urls(SUBJECT, RELATED)
        sources = [
            "https://en.wikipedia.org/wiki/Georg_Scheutz",
            "https://en.wikipedia.org/wiki/Per%20Georg%20Scheutz",
            "https://en.wikipedia.org/wiki/Charles_Babbage/",
        ]
        self.assertEqual(keep_citable(sources, allowed), sources[1:])

    def test_what_the_record_already_cites_stays_citable(self) -> None:
        existing = [
            "https://en.wikipedia.org/wiki/Computing_Machinery_and_Intelligence"
        ]
        self.assertEqual(
            keep_citable(existing, citable_urls(None, [], existing)), existing
        )

    def test_a_single_url_string_is_read_as_one_source(self) -> None:
        self.assertEqual(keep_citable(SUBJECT, citable_urls(SUBJECT, [])), [SUBJECT])


if __name__ == "__main__":
    unittest.main()
