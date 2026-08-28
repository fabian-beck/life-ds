"""Tests for the background reports: which events get one, and their pictures.

The deep-event selection is a port of the story's own rule in
``src/utils/story/eventDepth.js``, and a port that drifts writes reports the
story never shows or leaves a selected event with no way down. The
illustration pass is cheap to get subtly wrong in ways no schema catches: one
that lets the slide's own photograph through prints the same picture twice,
one screen apart, which is the failure the whole layer was designed around.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any, Dict, Optional
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import generate_event_backgrounds as backgrounds  # noqa: E402
import translate_person as translate  # noqa: E402
from utils.event_depth import select_deep_event_indexes  # noqa: E402


def event(
    title: str,
    chapter: str = "one",
    weight: Optional[float] = 0.5,
    places: int = 1,
    sources: int = 2,
    **extra: Any,
) -> Dict[str, Any]:
    """An event with enough material behind the fold, unless told otherwise."""
    built: Dict[str, Any] = {
        "date": "1940-01-01",
        "title": title,
        "description": "Something happened.",
        "chapter": chapter,
        "locations": [{"name_historic": f"Place {i}"} for i in range(places)],
        "sources": [f"https://en.wikipedia.org/wiki/S{i}" for i in range(sources)],
    }
    if weight is not None:
        built["weight"] = weight
    built.update(extra)
    return built


class DeepEventSelectionTests(unittest.TestCase):
    """Keep in step with ``selectDeepEventIndexes`` in eventDepth.js."""

    def test_each_chapter_offers_its_heaviest_event(self) -> None:
        events = [
            event("A", "one", 0.5),
            event("B", "one", 0.8),
            event("C", "two", 0.6),
        ]
        self.assertEqual(select_deep_event_indexes(events, {}), {1, 2})

    def test_below_the_floor_a_chapter_offers_nothing(self) -> None:
        events = [event("A", "one", 0.3), event("B", "two", 0.34)]
        self.assertEqual(select_deep_event_indexes(events, {}), set())

    def test_too_little_material_passes_to_the_next_event_down(self) -> None:
        events = [
            event("Heavy but bare", "one", 0.9, places=0, sources=1),
            event("Lighter but documented", "one", 0.5),
        ]
        self.assertEqual(select_deep_event_indexes(events, {}), {1})

    def test_ties_go_to_the_earlier_event(self) -> None:
        events = [event("First", "one", 0.6), event("Second", "one", 0.6)]
        self.assertEqual(select_deep_event_indexes(events, {}), {0})

    def test_an_unweighted_event_scores_zero(self) -> None:
        # The interface still derives a fallback for datasets that predate
        # Phase 1 weighting; the pipeline never sees one — such a dataset is
        # flagged in data/outdated.md and regenerated instead.
        events = [event("Old data", "one", None)]
        self.assertEqual(select_deep_event_indexes(events, {}), set())

    def test_a_chip_counts_toward_the_material(self) -> None:
        network = {
            "connections": [
                {"person_name": "Joan Clarke", "start_year": 1939, "end_year": 1954}
            ]
        }
        thin = event(
            "Engagement",
            "one",
            0.5,
            places=1,
            sources=1,
            involved_people=["Joan Clarke"],
        )
        # One place and one source are two sections but two items; the matched
        # chip is the third item, exactly as the interface counts it.
        self.assertEqual(select_deep_event_indexes([thin], network), {0})
        self.assertEqual(select_deep_event_indexes([thin], {}), set())


class IllustrationTests(unittest.TestCase):
    def test_the_slide_s_own_picture_is_kept_out_of_the_search(self) -> None:
        event = {
            "images": [
                {"url": "https://upload.wikimedia.org/x/640px-Hut_8.jpg"},
            ]
        }
        with mock.patch.object(
            backgrounds, "fetch_background_images", return_value=[]
        ) as fetch:
            backgrounds.illustrate_event(
                mock.MagicMock(), event, "A report.", ["hut 8"]
            )
        self.assertEqual(fetch.call_args.args[3], {"hut_8.jpg"})

    def test_a_report_with_no_pictures_loses_the_ones_it_had(self) -> None:
        event = {"background_images": [{"url": "https://example.org/stale.jpg"}]}
        with mock.patch.object(
            backgrounds, "fetch_background_images", return_value=[]
        ):
            backgrounds.illustrate_event(
                mock.MagicMock(), event, "A report.", ["query"]
            )
        self.assertNotIn("background_images", event)

    def test_nothing_is_searched_for_a_report_that_named_nothing(self) -> None:
        event: Dict[str, Any] = {}
        with mock.patch.object(backgrounds, "fetch_background_images") as fetch:
            backgrounds.illustrate_event(mock.MagicMock(), event, "A report.", [])
        fetch.assert_not_called()
        self.assertNotIn("background_images", event)


class CaptionTests(unittest.TestCase):
    """The layer prints the caption in the open, under the picture."""

    def test_an_uploader_s_paperwork_gives_way_to_the_filename(self) -> None:
        self.assertEqual(
            backgrounds.background_caption(
                {
                    "caption": "Author: Schadel Source: own work",
                    "filename": "Zuse_Z3_replica.jpg",
                },
                "Zuse Z3",
            ),
            "Zuse Z3 replica",
        )

    def test_a_real_description_is_printed_as_it_stands(self) -> None:
        self.assertEqual(
            backgrounds.background_caption(
                {"caption": "A rebuilt bombe at Bletchley Park", "filename": "b.jpg"},
                "bombe",
            ),
            "A rebuilt bombe at Bletchley Park",
        )

    def test_with_neither_the_query_is_the_caption(self) -> None:
        self.assertEqual(backgrounds.background_caption({}, "Hut 8"), "Hut 8")


class TranslatedHeadingTests(unittest.TestCase):
    """A German reader must not meet an English heading over German prose.

    The report is handed to the translator taken apart — its paragraphs as one
    array, its headings as another — and reassembled here. Neither structure
    survived being trusted: a `## ` line inside the passage reads as formatting
    to preserve, so two of the first five lives came back with German prose
    under English headings, and a passage sent as one string came back with
    four paragraphs merged into three.
    """

    source = "First.\n\n## A label\n\nSecond.\n\nThird."

    def test_the_report_is_taken_apart_for_the_translator(self) -> None:
        self.assertEqual(
            translate._paragraphs_of(self.source), ["First.", "Second.", "Third."]
        )
        self.assertEqual(translate._heading_texts(self.source), ["A label"])
        self.assertEqual(translate._heading_positions(self.source), [1])

    def test_a_translated_heading_lands_above_the_paragraph_it_had(self) -> None:
        self.assertEqual(
            translate._rebuild_background(
                self.source,
                ["Erster.", "Zweiter.", "Dritter."],
                ["Ein Etikett"],
            ),
            "Erster.\n\n## Ein Etikett\n\nZweiter.\n\nDritter.",
        )

    def test_two_headings_keep_their_order_and_places(self) -> None:
        source = "A.\n\n## One\n\nB.\n\n## Two\n\nC."
        self.assertEqual(
            translate._rebuild_background(source, ["A.", "B.", "C."], ["Eins", "Zwei"]),
            "A.\n\n## Eins\n\nB.\n\n## Zwei\n\nC.",
        )

    def test_an_undivided_report_comes_back_undivided(self) -> None:
        self.assertEqual(
            translate._rebuild_background(
                "Plain.\n\nMore.", ["Schlicht.", "Mehr."], []
            ),
            "Schlicht.\n\nMehr.",
        )

    def test_an_event_without_a_report_stays_without_one(self) -> None:
        self.assertIsNone(translate._rebuild_background("", [], []))
        self.assertIsNone(translate._rebuild_background(self.source, None, None))

    def test_a_summarized_report_is_called_out(self) -> None:
        # The small model summarizes the longest documents instead of
        # translating them — every paragraph present, every second detail
        # gone — and nothing else in the merge would notice.
        long_source = "\n\n".join(["Ein langer Absatz voller Einzelheiten." * 4] * 3)
        with mock.patch("builtins.print") as printed:
            translate._rebuild_background(long_source, ["Kurz.", "Kurz.", "Kurz."], [])
        self.assertIn("abridged", " ".join(str(c) for c in printed.call_args_list))

        with mock.patch("builtins.print") as printed:
            translate._rebuild_background(long_source, long_source.split("\n\n"), [])
        printed.assert_not_called()

    def test_a_dropped_field_never_blanks_a_report(self) -> None:
        # The small model omits the paragraphs on the longest documents. An
        # empty list is an unanswered field, not an empty report: returning
        # None leaves the merge holding what the source has, and one run that
        # wrote "" instead emptied every report in a life.
        self.assertIsNone(translate._rebuild_background(self.source, [], ["Etikett"]))
        self.assertIsNone(
            translate._rebuild_background(self.source, ["", "  "], ["Etikett"])
        )

    def test_merged_paragraphs_cost_the_headings_and_nothing_else(self) -> None:
        # The small model merges two paragraphs of a long report about once
        # every dozen events, and then no heading has a place to stand.
        # Discarding the document would trade a whole German story for its
        # section headings, so the prose stands and the report goes undivided.
        self.assertEqual(
            translate._rebuild_background(
                self.source, ["Erster und Zweiter.", "Dritter."], ["Ein Etikett"]
            ),
            "Erster und Zweiter.\n\nDritter.",
        )
        self.assertEqual(
            translate._rebuild_background(
                self.source, ["Erster.", "Zweiter.", "Dritter."], []
            ),
            "Erster.\n\nZweiter.\n\nDritter.",
        )


if __name__ == "__main__":
    unittest.main()
