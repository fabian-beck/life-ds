"""Tests for the repairs every string passes on its way into a data file."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from utils.json_io import write_json  # noqa: E402
from utils.text import (
    clean_strings,
    fix_control_characters,
    strip_markdown,
)  # noqa: E402


class ControlCharacterTests(unittest.TestCase):
    def test_the_punctuation_a_model_drops_to_one_byte_is_restored(self) -> None:
        self.assertEqual(fix_control_characters("1914\x131918"), "1914–1918")

    def test_a_high_byte_before_two_hex_digits_is_one_character(self) -> None:
        self.assertEqual(fix_control_characters("Vukovi\x0107"), "Vuković")

    def test_any_other_control_character_is_removed(self) -> None:
        self.assertEqual(fix_control_characters("a\x00b\x7fc"), "abc")

    def test_line_breaks_and_tabs_stay(self) -> None:
        self.assertEqual(fix_control_characters("a\nb\tc\r"), "a\nb\tc\r")


class MarkdownTests(unittest.TestCase):
    def test_emphasis_bold_code_and_links_keep_their_text(self) -> None:
        text = "She read *Childe Harold* and **Don Juan**, `code`, [Byron](https://x.org/Byron)."
        self.assertEqual(
            strip_markdown(text), "She read Childe Harold and Don Juan, code, Byron."
        )

    def test_a_star_that_is_not_markup_stays(self) -> None:
        for text in ("Manchester_Mk1*.jpg", "* EM3880", "*BlankEurope1989.png"):
            self.assertEqual(strip_markdown(text), text)

    def test_a_url_is_left_as_it_is(self) -> None:
        url = "https://commons.wikimedia.org/wiki/File:*a*.jpg"
        self.assertEqual(strip_markdown(url), url)

    def test_annotation_markers_stay(self) -> None:
        text = "She met [[Charles_Babbage|Babbage]]."
        self.assertEqual(strip_markdown(text), text)

    def test_a_heading_is_markup_only_inside_a_background(self) -> None:
        self.assertEqual(
            strip_markdown("## Context\nText", "background"), "## Context\nText"
        )
        self.assertEqual(
            strip_markdown("## Context\nText", "description"), "Context\nText"
        )

    def test_every_string_of_a_document_is_cleaned_by_its_field(self) -> None:
        document = {"events": [{"description": "*A*\x14B", "background": "## H\nT"}]}
        self.assertEqual(
            clean_strings(document),
            {"events": [{"description": "A—B", "background": "## H\nT"}]},
        )


class WriterTests(unittest.TestCase):
    def test_a_data_file_is_cleaned_and_a_cache_is_not(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data_file = root / "life_events.json"
            cache_file = root / "_cache" / "wikipedia_page.json"
            cache_file.parent.mkdir()
            for path in (data_file, cache_file):
                write_json(path, {"text": "*quoted*"})

            self.assertEqual(
                json.loads(data_file.read_text(encoding="utf-8")), {"text": "quoted"}
            )
            self.assertEqual(
                json.loads(cache_file.read_text(encoding="utf-8")), {"text": "*quoted*"}
            )


if __name__ == "__main__":
    unittest.main()
