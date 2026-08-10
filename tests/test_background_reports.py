"""Tests for the background report's two additions: headings and pictures.

Both are cheap to get subtly wrong in ways no schema catches. A heading pass
that rewrites prose, or places a label over the opening paragraph, damages a
report that was already good; an illustration pass that lets the slide's own
photograph through prints the same picture twice, one screen apart, which is
the failure the whole layer was designed around.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import backfill_event_backgrounds as backfill  # noqa: E402
import generate_person_events as pipeline  # noqa: E402

REPORT = (
    "Bletchley ran on shifts.\n\n"
    "Two hundred bombes by 1943.\n\n"
    "The huts were huts.\n\n"
    "It ended with the war."
)


def answer(headings: List[Dict[str, Any]]) -> backfill.ReportHeadings:
    return backfill.ReportHeadings(
        headings=[backfill.ReportHeading(**heading) for heading in headings]
    )


def divided(headings: Optional[backfill.ReportHeadings], report: str = REPORT) -> str:
    with mock.patch.object(backfill, "parse_structured", return_value=headings):
        return backfill._with_headings(mock.MagicMock(), report)


class HeadingTests(unittest.TestCase):
    def test_a_heading_becomes_a_line_above_its_paragraph(self) -> None:
        self.assertEqual(
            divided(answer([{"before_paragraph": 3, "heading": "The huts"}])),
            "Bletchley ran on shifts.\n\n"
            "Two hundred bombes by 1943.\n\n"
            "## The huts\n\n"
            "The huts were huts.\n\n"
            "It ended with the war.",
        )

    def test_the_prose_itself_is_never_touched(self) -> None:
        result = divided(answer([{"before_paragraph": 2, "heading": "The bombes"}]))
        for paragraph in REPORT.split("\n\n"):
            self.assertIn(paragraph, result)

    def test_a_report_that_runs_as_one_argument_is_left_whole(self) -> None:
        self.assertEqual(divided(answer([])), REPORT)
        self.assertEqual(divided(None), REPORT)

    def test_nothing_stands_above_the_opening_paragraph(self) -> None:
        # The reader has just arrived from the event; a label is not what they
        # came down for.
        self.assertEqual(
            divided(answer([{"before_paragraph": 1, "heading": "Bletchley"}])),
            REPORT,
        )

    def test_a_paragraph_the_report_does_not_have_is_dropped(self) -> None:
        self.assertEqual(
            divided(answer([{"before_paragraph": 9, "heading": "Nowhere"}])),
            REPORT,
        )

    def test_a_heading_per_paragraph_is_held_to_two(self) -> None:
        result = divided(
            answer(
                [
                    {"before_paragraph": 2, "heading": "The bombes"},
                    {"before_paragraph": 3, "heading": "The huts"},
                    {"before_paragraph": 4, "heading": "The end"},
                ]
            )
        )
        self.assertEqual(result.count("\n## "), 2)
        self.assertNotIn("## The end", result)

    def test_a_report_of_two_paragraphs_is_too_short_to_divide(self) -> None:
        short = "One paragraph.\n\nAnd a second."
        headings = answer([{"before_paragraph": 2, "heading": "The second"}])
        self.assertEqual(divided(headings, short), short)


class SelectionTests(unittest.TestCase):
    """Which events each pass has work to do on."""

    written = {"background": "A report.", "images": []}
    divided_already = {"background": "A report.\n\n## A turn\n\nMore of it."}
    empty: Dict[str, Any] = {}

    def wanted(self, event: Dict[str, Any], **flags: bool) -> bool:
        return backfill._wanted_here(
            event,
            overwrite=flags.get("overwrite", False),
            images_only=flags.get("images_only", False),
            headings_only=flags.get("headings_only", False),
        )

    def test_the_writing_pass_fills_what_is_empty(self) -> None:
        self.assertTrue(self.wanted(self.empty))
        self.assertFalse(self.wanted(self.written))
        self.assertTrue(self.wanted(self.written, overwrite=True))

    def test_the_picture_pass_wants_a_report_to_read(self) -> None:
        self.assertTrue(self.wanted(self.written, images_only=True))
        self.assertFalse(self.wanted(self.empty, images_only=True))

    def test_the_heading_pass_leaves_a_divided_report_alone(self) -> None:
        self.assertTrue(self.wanted(self.written, headings_only=True))
        self.assertFalse(self.wanted(self.divided_already, headings_only=True))
        self.assertFalse(self.wanted(self.empty, headings_only=True))
        self.assertTrue(
            self.wanted(self.divided_already, headings_only=True, overwrite=True)
        )


class IllustrationTests(unittest.TestCase):
    def test_the_slide_s_own_picture_is_kept_out_of_the_search(self) -> None:
        event = {
            "images": [
                {"url": "https://upload.wikimedia.org/x/640px-Hut_8.jpg"},
            ]
        }
        with mock.patch.object(
            pipeline, "fetch_background_images", return_value=[]
        ) as fetch:
            pipeline.illustrate_event(mock.MagicMock(), event, "A report.", ["hut 8"])
        self.assertEqual(fetch.call_args.args[3], {"hut_8.jpg"})

    def test_a_report_with_no_pictures_loses_the_ones_it_had(self) -> None:
        event = {"background_images": [{"url": "https://example.org/stale.jpg"}]}
        with mock.patch.object(pipeline, "fetch_background_images", return_value=[]):
            pipeline.illustrate_event(mock.MagicMock(), event, "A report.", ["query"])
        self.assertNotIn("background_images", event)

    def test_nothing_is_searched_for_a_report_that_named_nothing(self) -> None:
        event: Dict[str, Any] = {}
        with mock.patch.object(pipeline, "fetch_background_images") as fetch:
            pipeline.illustrate_event(mock.MagicMock(), event, "A report.", [])
        fetch.assert_not_called()
        self.assertNotIn("background_images", event)


class CaptionTests(unittest.TestCase):
    """The layer prints the caption in the open, under the picture."""

    def test_an_uploader_s_paperwork_gives_way_to_the_filename(self) -> None:
        self.assertEqual(
            pipeline.background_caption(
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
            pipeline.background_caption(
                {"caption": "A rebuilt bombe at Bletchley Park", "filename": "b.jpg"},
                "bombe",
            ),
            "A rebuilt bombe at Bletchley Park",
        )

    def test_with_neither_the_query_is_the_caption(self) -> None:
        self.assertEqual(pipeline.background_caption({}, "Hut 8"), "Hut 8")


if __name__ == "__main__":
    unittest.main()
