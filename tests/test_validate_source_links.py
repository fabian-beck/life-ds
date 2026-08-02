"""Tests for the source-link checker.

The checker's risky part is not asking Wikipedia whether an article exists —
that answer is unambiguous. It is deciding whether a search result may replace
a dead link without a human looking, because search answers every query with
something. Every pair below is one the real sweep over this repository's data
produced.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import validate_source_links as links  # noqa: E402


class ConfidenceTests(unittest.TestCase):
    def test_a_respelling_is_applied(self) -> None:
        for requested, suggested in [
            ("Kunst Haus Wien", "KunstHausWien"),
            ("Maxxi", "MAXXI"),
            ("Austrian Postal Savings Bank Building", "Austrian Postal Savings Bank"),
            ("Samuel Seabury (Anglican bishop)", "Samuel Seabury"),
            ("Historicism (art and architecture)", "Historicism (art)"),
        ]:
            with self.subTest(requested=requested):
                self.assertTrue(links.is_confident(requested, suggested))

    def test_a_different_subject_is_left_for_a_human(self) -> None:
        for requested, suggested in [
            # Search returns something for anything.
            ("Stadtbaurat", "Zwickau"),
            ("Little Curies", "Marie Curie"),
            ("Vincent Foster Hopper", "Grace Hopper"),
            ("Kantonsschule Aarau", "Jost Winteler"),
            ("On the Economy of Machinery and Manufactures", "Charles Babbage"),
            # Broadening a citation about one week into one about a life.
            ("George Washington's journey to the Ohio Country", "George Washington"),
            # Same name, different man.
            ("Lawrence Washington (soldier)", "Lawrence Washington (1659-1698)"),
            # Neighbouring but distinct subjects.
            ("Mainichi Art Award", "Mainichi Film Awards"),
            ("Manhattan Produce Exchange", "New York Produce Exchange"),
            ("Secret Germany", "Secret Reports on Nazi Germany"),
        ]:
            with self.subTest(requested=requested):
                self.assertFalse(links.is_confident(requested, suggested))

    def test_an_empty_title_is_never_confident(self) -> None:
        self.assertFalse(links.is_confident("", "Marie Curie"))
        self.assertFalse(links.is_confident("Marie Curie", ""))


class ParseArticleTests(unittest.TestCase):
    def test_an_article_url_yields_its_wiki_and_title(self) -> None:
        self.assertEqual(
            links.parse_article("https://en.wikipedia.org/wiki/Ada_Lovelace"),
            ("en.wikipedia.org", "Ada Lovelace"),
        )

    def test_percent_escapes_are_decoded(self) -> None:
        parsed = links.parse_article(
            "https://en.wikipedia.org/wiki/George_Washington%27s_journey"
        )
        assert parsed is not None
        self.assertEqual(parsed[1], "George Washington's journey")

    def test_other_hosts_are_not_this_checker_s_business(self) -> None:
        for url in [
            "https://www.deutsche-biographie.de/gnd118560093.html",
            "https://commons.wikimedia.org/wiki/File:Ada.jpg",
            "https://architectuul.com/architect/geoffrey-bawa",
        ]:
            with self.subTest(url=url):
                self.assertIsNone(links.parse_article(url))


class CollectAndRewriteTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.root = Path(self._temp.name)
        self.person = self.root / "data" / "people" / "ada_lovelace"
        self.person.mkdir(parents=True)
        (self.person / "life_events.json").write_text(
            json.dumps(
                {
                    "events": [
                        {
                            "sources": ["https://en.wikipedia.org/wiki/Maxxi"],
                            "annotations": {
                                "MAXXI": {
                                    "explanation": "A museum.",
                                    "wikipedia_url": (
                                        "https://en.wikipedia.org/wiki/Maxxi"
                                    ),
                                }
                            },
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        # A cache directory is generated material, not cited data.
        cache = self.person / "_cache"
        cache.mkdir()
        (cache / "life_events.json").write_text(
            json.dumps(
                {"events": [{"sources": ["https://en.wikipedia.org/wiki/Nope"]}]}
            ),
            encoding="utf-8",
        )
        patch_root = unittest.mock.patch.object(links, "REPO_ROOT", self.root)
        patch_root.start()
        self.addCleanup(patch_root.stop)

    def test_sources_and_annotation_links_are_both_collected(self) -> None:
        found = links.collect_links(self.root / "data" / "people")
        self.assertEqual(list(found), ["https://en.wikipedia.org/wiki/Maxxi"])

    def test_a_cached_copy_is_not_treated_as_cited_data(self) -> None:
        found = links.collect_links(self.root / "data" / "people")
        self.assertNotIn("https://en.wikipedia.org/wiki/Nope", found)

    def test_a_repair_rewrites_both_places_the_link_appears(self) -> None:
        citations = links.collect_links(self.root / "data" / "people")
        changed = links.rewrite(
            citations,
            {
                "https://en.wikipedia.org/wiki/Maxxi": "https://en.wikipedia.org/wiki/MAXXI"
            },
        )
        self.assertEqual(len(changed), 1)

        data = json.loads(
            (self.person / "life_events.json").read_text(encoding="utf-8")
        )
        event = data["events"][0]
        self.assertEqual(event["sources"], ["https://en.wikipedia.org/wiki/MAXXI"])
        self.assertEqual(
            event["annotations"]["MAXXI"]["wikipedia_url"],
            "https://en.wikipedia.org/wiki/MAXXI",
        )


if __name__ == "__main__":
    unittest.main()


class ExistingTitlesTests(unittest.TestCase):
    """The batch reply renames titles; crediting the wrong one loses links."""

    @staticmethod
    def _reply(payload):
        response = unittest.mock.Mock()
        response.json.return_value = payload
        response.raise_for_status.return_value = None
        return response

    def test_a_redirect_to_another_cited_title_credits_both(self) -> None:
        # "Little Curies" redirects to "Marie Curie", which is itself cited.
        # One page comes back for two asked titles.
        reply = self._reply(
            {
                "query": {
                    "redirects": [{"from": "Little Curies", "to": "Marie Curie"}],
                    "pages": {"1": {"title": "Marie Curie"}},
                }
            }
        )
        with (
            unittest.mock.patch.object(links.requests, "get", return_value=reply),
            unittest.mock.patch.object(links.time, "sleep"),
        ):
            alive = links.existing_titles(
                "en.wikipedia.org", ["Little Curies", "Marie Curie"]
            )
        self.assertEqual(alive, {"Little Curies", "Marie Curie"})

    def test_a_missing_page_is_not_credited(self) -> None:
        reply = self._reply(
            {
                "query": {
                    "pages": {
                        "-1": {"title": "Stadtbaurat", "missing": ""},
                        "1": {"title": "Ada Lovelace"},
                    }
                }
            }
        )
        with (
            unittest.mock.patch.object(links.requests, "get", return_value=reply),
            unittest.mock.patch.object(links.time, "sleep"),
        ):
            alive = links.existing_titles(
                "en.wikipedia.org", ["Stadtbaurat", "Ada Lovelace"]
            )
        self.assertEqual(alive, {"Ada Lovelace"})

    def test_an_unreachable_api_is_not_read_as_dead_links(self) -> None:
        with unittest.mock.patch.object(
            links.requests, "get", side_effect=OSError("connection reset")
        ):
            with self.assertRaises(links.WikipediaUnreachable):
                links.existing_titles("en.wikipedia.org", ["Ada Lovelace"])
