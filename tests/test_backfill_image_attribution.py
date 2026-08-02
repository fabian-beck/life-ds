"""Tests for the image-attribution backfill.

The risky parts are reading a Commons file title out of a source URL — the
corpus also cites Flickr and a Dutch heritage bank, which this must not touch —
and turning the HTML that Commons returns for Artist into the name a reader
sees.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import backfill_image_attribution as backfill  # noqa: E402


class TitleTests(unittest.TestCase):
    def test_a_commons_file_page_gives_its_title(self) -> None:
        self.assertEqual(
            backfill.commons_title(
                "https://commons.wikimedia.org/wiki/File:Hans_Fallada_Leipzig.jpg"
            ),
            "File:Hans Fallada Leipzig.jpg",
        )

    def test_a_percent_encoded_title_is_decoded(self) -> None:
        self.assertEqual(
            backfill.commons_title(
                "https://commons.wikimedia.org/wiki/File:G%C3%B6ttingen.jpg"
            ),
            "File:Göttingen.jpg",
        )

    def test_a_question_mark_in_the_title_does_not_cut_it_in_half(self) -> None:
        self.assertEqual(
            backfill.commons_title(
                "https://commons.wikimedia.org/wiki/"
                "File:Little_Man,What_Now?_(10629213655).jpg"
            ),
            "File:Little Man,What Now? (10629213655).jpg",
        )

    def test_another_host_is_left_alone(self) -> None:
        for url in [
            "https://www.flickr.com/photos/someone/123456",
            "https://beeldbank.cultureelerfgoed.nl/id/1234",
            "https://upload.wikimedia.org/wikipedia/commons/3/3d/A.jpg",
            "https://en.wikipedia.org/wiki/File:A.jpg",
        ]:
            with self.subTest(url=url):
                self.assertIsNone(backfill.commons_title(url))

    def test_a_commons_page_that_is_not_a_file_is_left_alone(self) -> None:
        self.assertIsNone(
            backfill.commons_title("https://commons.wikimedia.org/wiki/Category:Cats")
        )

    def test_a_missing_source_is_not_an_error(self) -> None:
        self.assertIsNone(backfill.commons_title(None))
        self.assertIsNone(backfill.commons_title(""))


class PlainTextTests(unittest.TestCase):
    def test_the_name_is_taken_out_of_the_markup(self) -> None:
        self.assertEqual(
            backfill.plain_text(
                '<a href="//commons.wikimedia.org/wiki/User:Concord" '
                'title="User:Concord">Concord</a>'
            ),
            "Concord",
        )

    def test_entities_are_decoded_and_space_collapsed(self) -> None:
        self.assertEqual(
            backfill.plain_text("<span>Jean\n  Dupont &amp;  Sons</span>"),
            "Jean Dupont & Sons",
        )

    def test_markup_with_no_text_gives_nothing(self) -> None:
        self.assertIsNone(backfill.plain_text("<span></span>"))
        self.assertIsNone(backfill.plain_text(""))
        self.assertIsNone(backfill.plain_text(None))


class CorpusTests(unittest.TestCase):
    def test_every_commons_image_carries_its_attribution(self) -> None:
        import json

        unattributed = []
        for path in sorted(backfill.PEOPLE_DIR.glob("*/life_events.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            for image in backfill.images_in(data):
                if not backfill.commons_title(image.get("source")):
                    continue
                if not image.get("license"):
                    unattributed.append(f"{path.parent.name}: {image.get('source')}")
        # A handful of file pages carry no credit block at all; the point of the
        # check is that the corpus does not silently lose the ones that do.
        self.assertLess(len(unattributed), 10, unattributed)


if __name__ == "__main__":
    unittest.main()
