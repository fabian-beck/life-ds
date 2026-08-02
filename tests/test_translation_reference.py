"""Tests for the naming evidence a translation is given.

A translator working from English alone invents plausible names: a Copenhagen
cemetery became the "Assistenzfriedhof", a German compound that reads perfectly
and does not exist. The fix is to show the model what the target language's own
encyclopedia writes — which is only worth having if the lookup is honest about
what it found, so these tests hold the two places it could quietly lie: a link
that landed on the wrong subject, and a localization that renames the person.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import translate_person as tp  # noqa: E402
from utils import wikipedia_cache as wiki  # noqa: E402


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def api_answer(pages, normalized=None):
    query = {"pages": {str(i): page for i, page in enumerate(pages)}}
    if normalized:
        query["normalized"] = normalized
    return FakeResponse({"query": query})


def article(title, langlink=None, description=None, **extra):
    page = {"title": title}
    if langlink:
        page["langlinks"] = [{"lang": "de", "*": langlink}]
    if description:
        page["description"] = description
    page.update(extra)
    return page


class LanguageLinkTests(unittest.TestCase):
    def test_answers_under_the_title_that_was_asked_about(self) -> None:
        with patch.object(
            wiki.requests,
            "get",
            return_value=api_answer(
                [article("Bamberg Cathedral", "Bamberger Dom", "Church in Bavaria")]
            ),
        ):
            links = wiki.fetch_language_links(["Bamberg Cathedral"], "de")
        self.assertEqual(
            links,
            {
                "Bamberg Cathedral": {
                    "title": "Bamberger Dom",
                    "description": "Church in Bavaria",
                }
            },
        )

    def test_follows_a_normalization_back_to_the_query(self) -> None:
        with patch.object(
            wiki.requests,
            "get",
            return_value=api_answer(
                [article("Bamberg cathedral", "Bamberger Dom")],
                normalized=[{"from": "bamberg cathedral", "to": "Bamberg cathedral"}],
            ),
        ):
            links = wiki.fetch_language_links(["bamberg cathedral"], "de")
        self.assertIn("bamberg cathedral", links)

    def test_a_page_that_stands_for_a_string_names_nobody(self) -> None:
        # "Christian Christiansen" is a disambiguation page; "Adalbero" a name
        # list. Both link to their counterpart and neither is a person.
        pages = [
            article(
                "Christian Christiansen",
                "Christian Christiansen",
                pageprops={"disambiguation": ""},
            ),
            article("Adalbero", "Adalbero", "Name list"),
            article("Niels Bohr", "Niels Bohr", "Danish physicist"),
        ]
        with patch.object(wiki.requests, "get", return_value=api_answer(pages)):
            links = wiki.fetch_language_links(
                ["Christian Christiansen", "Adalbero", "Niels Bohr"], "de"
            )
        self.assertEqual(list(links), ["Niels Bohr"])

    def test_a_name_without_an_article_yields_nothing(self) -> None:
        # "Ellen Adler Bohr" is a redirect to her son's article. Redirects are
        # not followed, so the page carries no language link of its own.
        with patch.object(
            wiki.requests,
            "get",
            return_value=api_answer([article("Ellen Adler Bohr")]),
        ):
            self.assertEqual(wiki.fetch_language_links(["Ellen Adler Bohr"], "de"), {})

    def test_a_failed_lookup_costs_evidence_not_the_run(self) -> None:
        with patch.object(wiki.requests, "get", side_effect=OSError("no network")):
            self.assertEqual(wiki.fetch_language_links(["Niels Bohr"], "de"), {})

    def test_asks_nothing_when_the_target_is_the_source(self) -> None:
        with patch.object(wiki.requests, "get", side_effect=AssertionError("called")):
            self.assertEqual(wiki.fetch_language_links(["Niels Bohr"], "en"), {})

    def test_a_title_sheds_its_disambiguator(self) -> None:
        self.assertEqual(
            wiki.strip_title_disambiguator("Heinrich II. (HRR)"), "Heinrich II."
        )
        self.assertEqual(
            wiki.strip_title_disambiguator("Bamberger Dom"), "Bamberger Dom"
        )


class PlaceCollectionTests(unittest.TestCase):
    def test_collects_the_places_a_document_names(self) -> None:
        document = {
            "chapters": [{"location": "Denmark"}],
            "events": [
                {
                    "locations": [
                        {"name_historic": "Copenhagen", "name_modern": "Copenhagen"}
                    ],
                },
                {
                    "locations": [],
                    "event_class": {
                        "type": "death",
                        "place_of_rest": "Assistens Cemetery, Copenhagen",
                    },
                },
                {
                    "event_class": {
                        "type": "migration",
                        "from_location": "Denmark",
                        "to_location": "Sweden",
                    }
                },
            ],
        }
        self.assertEqual(
            tp.collect_place_names(document),
            [
                "Denmark",
                "Copenhagen",
                "Assistens Cemetery, Copenhagen",
                "Sweden",
            ],
        )

    def test_an_empty_document_names_no_places(self) -> None:
        self.assertEqual(tp.collect_place_names(None), [])


class ReferenceTests(unittest.TestCase):
    def test_asks_about_the_leading_part_of_a_qualified_place(self) -> None:
        # "Assistens Cemetery, Copenhagen" is nobody's article title, but what
        # stands before the comma is — and the answer is recorded under that,
        # so the qualifier is still translated rather than dropped with it.
        document = {
            "person": {"name": "Niels Bohr", "wikipedia": None},
            "events": [
                {
                    "event_class": {
                        "type": "death",
                        "place_of_rest": "Assistens Cemetery, Copenhagen",
                    }
                }
            ],
        }
        asked = []

        def links(titles, target_lang, source_lang="en"):
            asked.append(list(titles))
            if "Assistens Cemetery" in titles:
                return {"Assistens Cemetery": {"title": "Assistens Kirkegård"}}
            return {}

        with (
            patch.object(tp, "fetch_language_links", side_effect=links),
            patch.object(tp, "get_cached_article_in_language", return_value=None),
        ):
            reference = tp.build_translation_reference("niels_bohr", document, [], "de")

        self.assertEqual(
            reference.links, {"Assistens Cemetery": {"title": "Assistens Kirkegård"}}
        )
        self.assertEqual(asked[0], ["Assistens Cemetery, Copenhagen"])
        self.assertEqual(asked[1], ["Assistens Cemetery"])

    def test_the_full_name_wins_over_its_leading_part(self) -> None:
        # "Washington, D.C." is an article of its own; it must never fall back
        # to the state it shares a first word with.
        document = {
            "person": {"name": "Vannevar Bush"},
            "events": [{"locations": [{"name_modern": "Washington, D.C."}]}],
        }
        asked = []

        def links(titles, target_lang, source_lang="en"):
            asked.append(list(titles))
            return {"Washington, D.C.": {"title": "Washington, D.C."}}

        with (
            patch.object(tp, "fetch_language_links", side_effect=links),
            patch.object(tp, "get_cached_article_in_language", return_value=None),
        ):
            reference = tp.build_translation_reference(
                "vannevar_bush", document, [], "de"
            )

        self.assertEqual(len(asked), 1)
        self.assertEqual(list(reference.links), ["Washington, D.C."])

    def test_the_prompt_separates_what_changes_from_what_does_not(self) -> None:
        reference = tp.TranslationReference(
            article_title="Niels Bohr",
            article_excerpt="Niels Henrik David Bohr war ein dänischer Physiker.",
            links={
                "Copenhagen": {"title": "Kopenhagen", "description": "Capital"},
                "Albert Einstein": {"title": "Albert Einstein", "description": ""},
                "Henry II, Holy Roman Emperor": {"title": "Heinrich II. (HRR)"},
            },
        )
        block = tp.format_reference_for_prompt(reference, "German")
        self.assertIn("dänischer Physiker", block)
        self.assertIn('"Copenhagen" -> "Kopenhagen"', block)
        # The disambiguator is title bookkeeping, never part of the name.
        self.assertIn('-> "Heinrich II."', block)
        self.assertNotIn("(HRR)", block)
        # A name the language writes identically is listed as such, which is
        # the evidence that stops one from being invented.
        self.assertIn('"Albert Einstein"', block)
        self.assertNotIn('"Albert Einstein" -> ', block)

    def test_no_evidence_means_no_section_at_all(self) -> None:
        self.assertEqual(
            tp.format_reference_for_prompt(tp.TranslationReference(), "German"), ""
        )
        self.assertFalse(tp.TranslationReference())


class MetaStoryReferenceTests(unittest.TestCase):
    """A meta story's people already have translations; those are the evidence."""

    STORY = {
        "meta_story": {"person_ids": ["cunigunde_of_luxembourg", "hans_erlwein"]},
        "geo_map": {"clusters": [{"label": "Bamberg"}]},
    }

    def _registry(self, path):
        if path == tp.REGISTER_PATH:
            return {
                "people": [
                    {
                        "id": "cunigunde_of_luxembourg",
                        "name": "Cunigunde_of_Luxembourg",
                    },
                    {"id": "hans_erlwein", "name": "Hans_Erlwein"},
                    {"id": "someone_else", "name": "Someone_Else"},
                ]
            }
        return {
            "people": [
                {"id": "cunigunde_of_luxembourg", "name": "Kunigunde_von_Luxemburg"},
                {"id": "hans_erlwein", "name": "Hans_Erlwein"},
                {"id": "someone_else", "name": "Jemand_Anderes"},
            ]
        }

    def test_takes_each_name_from_that_persons_own_translation(self) -> None:
        with (
            patch.object(tp, "load_json_file", side_effect=self._registry),
            patch.object(tp, "fetch_language_links", return_value={}),
        ):
            reference = tp.build_meta_story_reference(self.STORY, "de")

        # Only the story's own cast, and each under the name their story shows.
        self.assertEqual(
            reference.links,
            {
                "Cunigunde of Luxembourg": {
                    "title": "Kunigunde von Luxemburg",
                    "description": "as this person's own story names them",
                },
                "Hans Erlwein": {
                    "title": "Hans Erlwein",
                    "description": "as this person's own story names them",
                },
            },
        )

    def test_asks_the_encyclopedia_only_about_the_map_labels(self) -> None:
        asked = []

        def links(titles, target_lang, source_lang="en"):
            asked.append(list(titles))
            return {"Bamberg": {"title": "Bamberg"}}

        with (
            patch.object(tp, "load_json_file", side_effect=self._registry),
            patch.object(tp, "fetch_language_links", side_effect=links),
        ):
            tp.build_meta_story_reference(self.STORY, "de")

        self.assertEqual(asked, [["Bamberg"]])


class NumeralGuardTests(unittest.TestCase):
    def test_a_renumbered_ruler_is_not_the_same_person(self) -> None:
        # Cunigunde's brother is Henry V as Count of Luxembourg and Henry I in
        # the German article about his Bavarian title.
        self.assertFalse(
            tp.localization_keeps_the_person(
                "Henry V, Count of Luxembourg", "Heinrich I. von Luxemburg"
            )
        )

    def test_a_respelling_that_keeps_the_numeral_passes(self) -> None:
        for original, localized in [
            ("Henry II, Holy Roman Emperor", "Heinrich II., römisch-deutscher Kaiser"),
            ("Otto III, Holy Roman Emperor", "Otto III."),
            ("Pope Benedict VIII", "Papst Benedikt VIII."),
            ("Charlemagne", "Karl der Große"),
        ]:
            self.assertTrue(
                tp.localization_keeps_the_person(original, localized),
                f"{original} -> {localized}",
            )

    def test_the_trailing_german_dot_is_not_a_difference(self) -> None:
        self.assertEqual(tp.name_numerals("Heinrich II."), ["II"])
        self.assertEqual(tp.name_numerals("Henry II"), ["II"])


if __name__ == "__main__":
    unittest.main()
