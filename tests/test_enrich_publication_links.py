"""Tests for the publication-link enrichment.

The network part of this script is not the risky part: asking a wiki what it
holds gets an unambiguous answer. The risk is everything around that answer —
whether a result names the *work* rather than a neighbouring subject, and which
of an item's many links belongs on a biography slide. Every title pair below
comes from the sweep over this repository's own data.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import enrich_publication_links as enrich  # noqa: E402


class TitleMatchTests(unittest.TestCase):
    def test_the_same_title_matches(self) -> None:
        for requested, candidate in [
            ("The Federalist Papers", "The Federalist Papers"),
            ("Poor Richard's Almanack", "Poor Richard’s Almanack"),
            ("Emil und die Detektive", "Emil und die Detektive"),
            # The encyclopedia's own disambiguator is what separates the book
            # from the practice it is named after; the author check decides.
            ("Propaganda", "Propaganda (book)"),
            ("Science of Logic", "Science of Logic (Hegel)"),
        ]:
            with self.subTest(requested=requested):
                self.assertTrue(enrich.is_same_work(requested, candidate))

    def test_a_neighbouring_subject_does_not(self) -> None:
        for requested, candidate in [
            # A book about a thing is not the thing.
            ("Das Rhenium", "Rhenium"),
            ("Über das Element 93", "Neptunium"),
            # A work is not the life that produced it.
            ("On the Economy of Machinery and Manufactures", "Charles Babbage"),
            ("Moderne Architektur", "Otto Wagner"),
            # The event the pamphlet caused is not the pamphlet.
            ("Reynolds Pamphlet", "Hamilton–Reynolds affair"),
            # An adaptation carries the work's title and names its author.
            ("The Reynolds Pamphlet", "The Reynolds Pamphlet (song)"),
            ("Emil und die Detektive", "Emil und die Detektive (Film)"),
        ]:
            with self.subTest(requested=requested):
                self.assertFalse(enrich.is_same_work(requested, candidate))

    def test_an_empty_title_never_matches(self) -> None:
        self.assertFalse(enrich.is_same_work("", "Propaganda"))
        self.assertFalse(enrich.is_same_work("(book)", "Propaganda"))


class TitleVariantTests(unittest.TestCase):
    def test_a_gloss_is_asked_about_separately(self) -> None:
        # The generated titles carry glosses the catalogue does not, and the
        # gloss is often the work's name in the other language.
        self.assertEqual(
            enrich.title_variants("Wissenschaft der Logik (Science of Logic)"),
            [
                "Wissenschaft der Logik (Science of Logic)",
                "Wissenschaft der Logik",
                "Science of Logic",
            ],
        )

    def test_a_one_word_qualifier_is_not_a_title(self) -> None:
        self.assertEqual(
            enrich.title_variants("Methoden der mathematischen Physik (Vol. 1)"),
            [
                "Methoden der mathematischen Physik (Vol. 1)",
                "Methoden der mathematischen Physik",
            ],
        )

    def test_the_author_is_added_to_the_query_but_not_to_the_match(self) -> None:
        publication = enrich.Publication(
            person_id="edward_bernays",
            person_name="Edward Bernays",
            person_article=None,
            title="Propaganda",
            publication_type="book",
            event_index=3,
        )
        queries = enrich.article_queries(publication)
        self.assertEqual(queries[0], ("Propaganda", "Propaganda"))
        self.assertIn(("Propaganda Edward Bernays", "Propaganda"), queries)


class AuthorshipTests(unittest.TestCase):
    def test_a_particle_does_not_hide_the_surname(self) -> None:
        self.assertTrue(
            enrich.mentions_author(
                "Die Denkschrift wurde von Stauffenberg verfasst.",
                "Claus von Stauffenberg",
            )
        )

    def test_an_unrelated_lead_is_not_an_author(self) -> None:
        self.assertFalse(
            enrich.mentions_author(
                "Propaganda is communication used primarily to influence "
                "an audience.",
                "Edward Bernays",
            )
        )

    def test_the_author_item_confirms_a_work(self) -> None:
        entity = {"claims": {"P50": [_item_claim("P50", "Q17714")]}}
        self.assertTrue(enrich.written_by(entity, "Q17714", "Albert Einstein"))
        self.assertFalse(enrich.written_by(entity, "Q7186", "Marie Curie"))

    def test_an_author_name_string_confirms_a_work(self) -> None:
        entity = {"claims": {"P2093": [_string_claim("P2093", "Ida Noddack")]}}
        self.assertTrue(enrich.written_by(entity, None, "Ida Noddack"))

    def test_an_item_without_an_author_is_refused(self) -> None:
        # A title match on an item that records no author is exactly how the
        # article about an element ends up standing in for a book about it.
        self.assertFalse(enrich.written_by({"claims": {}}, "Q123", "Ida Noddack"))


def _item_claim(prop: str, item_id: str) -> dict:
    return {
        "mainsnak": {
            "snaktype": "value",
            "property": prop,
            "datavalue": {"value": {"id": item_id}, "type": "wikibase-entityid"},
        }
    }


def _string_claim(prop: str, text: str) -> dict:
    return {
        "mainsnak": {
            "snaktype": "value",
            "property": prop,
            "datavalue": {"value": text, "type": "string"},
        }
    }


class LinkChoiceTests(unittest.TestCase):
    """The ranking is for a reader on a slide, not for a catalogue."""

    def test_a_transcription_wins(self) -> None:
        entity = {
            "sitelinks": {
                "enwikisource": {"url": "https://en.wikisource.org/wiki/Work"},
                "enwiki": {"url": "https://en.wikipedia.org/wiki/Work"},
            },
            "claims": {"P356": [_string_claim("P356", "10.1000/xyz")]},
        }
        link = enrich.choose_link(entity, "Q1")
        self.assertEqual(link.kind, "wikisource")
        self.assertEqual(link.url, "https://en.wikisource.org/wiki/Work")

    def test_an_article_beats_an_identifier_that_may_be_paywalled(self) -> None:
        entity = {
            "sitelinks": {"enwiki": {"url": "https://en.wikipedia.org/wiki/Work"}},
            "claims": {"P356": [_string_claim("P356", "10.1000/xyz")]},
        }
        self.assertEqual(enrich.choose_link(entity, "Q1").kind, "wikipedia")

    def test_a_doi_is_better_than_nothing(self) -> None:
        entity = {
            "claims": {"P356": [_string_claim("P356", "10.1080/14786441308634955")]}
        }
        link = enrich.choose_link(entity, "Q1")
        self.assertEqual(link.url, "https://doi.org/10.1080/14786441308634955")

    def test_a_scan_beats_an_article(self) -> None:
        entity = {
            "sitelinks": {"enwiki": {"url": "https://en.wikipedia.org/wiki/Work"}},
            "claims": {"P724": [_string_claim("P724", "workscan00auth")]},
        }
        link = enrich.choose_link(entity, "Q1")
        self.assertEqual(link.kind, "internet_archive")
        self.assertEqual(link.url, "https://archive.org/details/workscan00auth")

    def test_the_item_itself_is_the_last_resort(self) -> None:
        link = enrich.choose_link({}, "Q42")
        self.assertEqual(link.url, "https://www.wikidata.org/wiki/Q42")

    def test_the_reader_s_language_is_preferred_among_sitelinks(self) -> None:
        entity = {
            "sitelinks": {
                "frwiki": {"url": "https://fr.wikipedia.org/wiki/Oeuvre"},
                "dewiki": {"url": "https://de.wikipedia.org/wiki/Werk"},
                "enwiki": {"url": "https://en.wikipedia.org/wiki/Work"},
            }
        }
        self.assertEqual(
            enrich.choose_link(entity, "Q1").url, "https://en.wikipedia.org/wiki/Work"
        )

    def test_a_work_only_documented_elsewhere_still_gets_a_link(self) -> None:
        entity = {
            "sitelinks": {"frwiki": {"url": "https://fr.wikipedia.org/wiki/Oeuvre"}}
        }
        self.assertEqual(
            enrich.choose_link(entity, "Q1").url, "https://fr.wikipedia.org/wiki/Oeuvre"
        )


class WritingTests(unittest.TestCase):
    """The link is written into every copy of a person's events, translations
    included, since `event_class` is copied into them rather than translated."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self._people = root / "people"
        (self._people / "e_b" / "de").mkdir(parents=True)
        document = {
            "person": {"name": "Edward_Bernays"},
            "events": [
                {"title": "A talk"},
                {
                    "title": "Publishes Propaganda",
                    "event_class": {"type": "publication", "title": "Propaganda"},
                },
            ],
        }
        for path in (
            self._people / "e_b" / "life_events.json",
            self._people / "e_b" / "de" / "life_events.json",
        ):
            path.write_text(json.dumps(document), encoding="utf-8")
        self._previous = enrich.PEOPLE_DIR
        enrich.PEOPLE_DIR = self._people

    def tearDown(self) -> None:
        enrich.PEOPLE_DIR = self._previous
        self._tmp.cleanup()

    def _read(self, *parts: str) -> dict:
        return json.loads((self._people.joinpath(*parts)).read_text(encoding="utf-8"))

    def test_every_language_gets_the_same_link(self) -> None:
        link = {
            "url": "https://en.wikipedia.org/wiki/Propaganda_(book)",
            "kind": "wikipedia",
        }
        changed = enrich.write_links("e_b", {1: link}, force=False)
        self.assertEqual(len(changed), 2)
        for parts in (("e_b", "life_events.json"), ("e_b", "de", "life_events.json")):
            data = self._read(*parts)
            self.assertEqual(data["events"][1]["event_class"]["source_link"], link)

    def test_an_existing_link_is_left_alone(self) -> None:
        kept = {"url": "https://example.org/hand-picked", "kind": "full_text"}
        enrich.write_links("e_b", {1: kept}, force=False)
        enrich.write_links(
            "e_b", {1: {"url": "https://en.wikipedia.org/wiki/Other"}}, force=False
        )
        data = self._read("e_b", "life_events.json")
        self.assertEqual(data["events"][1]["event_class"]["source_link"], kept)

    def test_force_replaces_it(self) -> None:
        enrich.write_links("e_b", {1: {"url": "https://example.org/old"}}, force=False)
        fresh = {"url": "https://example.org/new"}
        enrich.write_links("e_b", {1: fresh}, force=True)
        data = self._read("e_b", "life_events.json")
        self.assertEqual(data["events"][1]["event_class"]["source_link"], fresh)

    def test_a_non_publication_event_is_never_written_to(self) -> None:
        enrich.write_links("e_b", {0: {"url": "https://example.org/x"}}, force=True)
        data = self._read("e_b", "life_events.json")
        self.assertNotIn("event_class", data["events"][0])

    def test_publications_are_read_with_their_author(self) -> None:
        publications, article = enrich.publications_of("e_b")
        self.assertEqual(len(publications), 1)
        self.assertEqual(publications[0].person_name, "Edward Bernays")
        self.assertEqual(publications[0].event_index, 1)
        self.assertIsNone(article)


if __name__ == "__main__":
    unittest.main()
