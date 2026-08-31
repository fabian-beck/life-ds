"""Tests for the dependency of the image steps on the style step.

The portrait and the chapter illustrations name the story's primary and
secondary color in their prompts, so both are downstream of
`generate_person_style.py`. Each image script used to read the style file
through a loader of its own that answered a missing entry with a hardcoded cyan
and violet: the run drew the images in a palette no story uses, cached them
under the person's name, and said nothing. These tests hold the reader to
raising instead, and hold both image steps to stopping rather than drawing.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import generate_chapter_illustrations as chapter_art  # noqa: E402
import generate_person_portrait as portrait  # noqa: E402
from utils import person_style  # noqa: E402


def _styles_file(directory: str, styles: Dict[str, Any]) -> Path:
    """A `person_styles.json` holding exactly the styles given."""
    path = Path(directory) / "person_styles.json"
    path.write_text(json.dumps({"styles": styles}), encoding="utf-8")
    return path


class StoryColorTests(unittest.TestCase):
    def test_the_colors_come_from_the_style(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = _styles_file(
                directory,
                {"ada_lovelace": {"primary": "#ff8800", "secondary": "#1155aa"}},
            )
            with patch.object(person_style, "STYLES_PATH", path):
                self.assertEqual(
                    person_style.story_colors("ada_lovelace"),
                    {"primary": "#FF8800", "secondary": "#1155AA"},
                )

    def test_a_person_without_a_style_raises_rather_than_defaulting(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = _styles_file(directory, {"ada_lovelace": {"primary": "#FF8800"}})
            with patch.object(person_style, "STYLES_PATH", path):
                with self.assertRaises(person_style.MissingStyleError) as raised:
                    person_style.story_colors("alan_turing")
                self.assertIn("generate_person_style.py", str(raised.exception))
                self.assertFalse(person_style.has_style("alan_turing"))

    def test_an_entry_without_usable_colors_raises(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = _styles_file(
                directory,
                {"ada_lovelace": {"primary": "#FF8800", "secondary": "cornflower"}},
            )
            with patch.object(person_style, "STYLES_PATH", path):
                with self.assertRaises(person_style.MissingStyleError) as raised:
                    person_style.story_colors("ada_lovelace")
                self.assertIn("secondary", str(raised.exception))

    def test_a_missing_styles_file_is_a_missing_style(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "person_styles.json"
            with patch.object(person_style, "STYLES_PATH", path):
                self.assertFalse(person_style.has_style("ada_lovelace"))


class ImageStepsWaitForTheStyleTests(unittest.TestCase):
    """Neither image step may draw anything before the style exists."""

    def test_chapter_illustrations_stop_without_a_style(self) -> None:
        dataset = {
            "chapters": [{"id": "first", "headline": "A First Light"}],
            "events": [],
        }
        client = Mock()
        with (
            patch.object(chapter_art, "load_dataset", return_value=dataset),
            patch.object(chapter_art, "OpenAI", client),
            patch.object(
                chapter_art,
                "story_colors",
                side_effect=person_style.MissingStyleError("no style"),
            ),
        ):
            result = chapter_art.generate_chapter_illustrations("ada_lovelace")

        self.assertFalse(result["success"])
        self.assertEqual(result["generated"], [])
        self.assertEqual(result["message"], "no style")
        client.assert_not_called()

    def test_the_portrait_stops_without_a_style(self) -> None:
        registry = Mock()
        with (
            patch.object(portrait, "person_registry", registry),
            patch.object(
                portrait,
                "story_colors",
                side_effect=person_style.MissingStyleError("no style"),
            ),
        ):
            result = portrait.generate_portrait("ada_lovelace")

        self.assertFalse(result["success"])
        self.assertEqual(result["message"], "no style")
        registry.assert_not_called()


if __name__ == "__main__":
    unittest.main()
