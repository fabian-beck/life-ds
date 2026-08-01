"""The meta story style registry and the generator that writes into it.

The registry is data the app reads directly — an entry with a malformed color,
an unloadable font or broken SVG markup would degrade the article silently, so
the shape is checked here rather than discovered in the browser.
"""

import json
import re
import sys
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from generate_meta_story_style import (  # noqa: E402
    BODY_FONT_CHOICES,
    FRAME_CHOICES,
    HEADING_FONT_CHOICES,
    normalize_payload,
)

STYLES_PATH = ROOT / "data" / "meta_story_styles.json"
FRAMES_JS = ROOT / "src" / "utils" / "metaStoryStyles.js"
META_STORIES_REGISTER = ROOT / "data" / "meta_stories.json"

HEX = re.compile(r"^#[0-9A-F]{6}$")

MARK_FIELDS = ("separator_glyph_svg", "ornament_svg")


def load_styles():
    data = json.loads(STYLES_PATH.read_text(encoding="utf-8"))
    return data["styles"]


class MetaStoryStyleRegistryTests(unittest.TestCase):
    def test_every_meta_story_has_a_style(self):
        register = json.loads(META_STORIES_REGISTER.read_text(encoding="utf-8"))
        story_ids = {entry["id"] for entry in register["meta_stories"]}
        self.assertTrue(story_ids <= set(load_styles()))

    def test_styles_belong_to_existing_meta_stories(self):
        register = json.loads(META_STORIES_REGISTER.read_text(encoding="utf-8"))
        story_ids = {entry["id"] for entry in register["meta_stories"]}
        for story_id in load_styles():
            with self.subTest(story_id=story_id):
                self.assertIn(story_id, story_ids)

    def test_colors_are_uppercase_hex(self):
        for story_id, style in load_styles().items():
            for field in ("primary", "secondary", "background"):
                with self.subTest(story_id=story_id, field=field):
                    self.assertRegex(style[field], HEX)

    def test_fonts_are_in_the_choice_lists(self):
        """A stored face outside the vocabulary is a font nothing will style.

        That the app also *loads* each face is checked in
        tests/test_font_coverage.py, which owns parsing src/fonts.css. This
        assertion used to search index.html for the Google Fonts link; the
        fonts are self-hosted now, so there is no link tag to search.
        """
        for story_id, style in load_styles().items():
            with self.subTest(story_id=story_id):
                self.assertIn(style["heading_font"], HEADING_FONT_CHOICES)
                self.assertIn(style["body_font"], BODY_FONT_CHOICES)

    def test_frames_are_in_the_vocabulary(self):
        for story_id, style in load_styles().items():
            with self.subTest(story_id=story_id):
                self.assertIn(style["frame"], FRAME_CHOICES)

    def test_the_generator_and_the_app_know_the_same_frames(self):
        """The name in the data is only meaningful if both sides define it.

        The generator picks a frame; `metaStoryStyles.js` turns it into the
        radii and border widths every box reads. A name in one list and not in
        the other is a box that silently keeps the default cut.
        """
        source = FRAMES_JS.read_text(encoding="utf-8")
        block = source.split("export const FRAMES = {", 1)[1].split("\n};", 1)[0]
        in_app = set(re.findall(r"^  (\w+): \{", block, re.MULTILINE))
        self.assertEqual(in_app, set(FRAME_CHOICES))

    def test_marks_are_valid_single_color_svg(self):
        """The glyph and the ornament are drawn in the story's primary color."""
        for story_id, style in load_styles().items():
            for field in MARK_FIELDS:
                with self.subTest(story_id=story_id, field=field):
                    root = ET.fromstring(style[field])
                    self.assertTrue(root.tag.endswith("svg"))
                    colors = {
                        value
                        for element in root.iter()
                        for key, value in element.attrib.items()
                        if key in {"fill", "stroke"} and value != "none"
                    }
                    self.assertEqual(colors, {style["primary"]})

    def test_background_pattern_is_black_and_white_only(self):
        for story_id, style in load_styles().items():
            with self.subTest(story_id=story_id):
                root = ET.fromstring(style["background_pattern_svg"])
                self.assertEqual(root.attrib.get("viewBox"), "0 0 160 160")
                colors = {
                    value
                    for element in root.iter()
                    for key, value in element.attrib.items()
                    if key in {"fill", "stroke"}
                }
                self.assertTrue(colors <= {"#000000", "#FFFFFF", "none"}, colors)


class NormalizePayloadTests(unittest.TestCase):
    payload = {
        "primary": "#5ed0ff",
        "secondary": "#ffb454",
        "background": "#050b16",
        "background_pattern_svg": (
            '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="160" '
            'viewBox="0 0 160 160"><rect width="160" height="160" fill="#000000"/>'
            '<path stroke="#FFFFFF" stroke-width="4" d="M0 80h160"/></svg>'
        ),
        "separator_glyph_svg": (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
            '<circle cx="16" cy="16" r="8" fill="#123456"/></svg>'
        ),
        "ornament_svg": (
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<path d="M0 12h240" stroke="#654321" stroke-opacity="0.5"/></svg>'
        ),
        "frame": "square",
        "heading_font": "Space Grotesk",
        "body_font": "IBM Plex Sans",
    }

    def test_recolors_both_marks_and_supplies_the_ornament_view_box(self):
        result = normalize_payload(dict(self.payload))
        self.assertEqual(result["primary"], "#5ED0FF")
        self.assertEqual(result["frame"], "square")
        self.assertIn('fill="#5ED0FF"', result["separator_glyph_svg"])
        self.assertIn('stroke="#5ED0FF"', result["ornament_svg"])
        self.assertIn('viewBox="0 0 240 24"', result["ornament_svg"])
        # Opacity is controlled by the stylesheet, never by the generated mark.
        self.assertNotIn("stroke-opacity", result["ornament_svg"])

    def test_rejects_a_missing_ornament(self):
        payload = dict(self.payload)
        del payload["ornament_svg"]
        with self.assertRaises(ValueError):
            normalize_payload(payload)

    def test_rejects_a_frame_outside_the_vocabulary(self):
        payload = dict(self.payload)
        payload["frame"] = "brutalist"
        with self.assertRaises(ValueError):
            normalize_payload(payload)

    def test_rejects_a_font_the_app_does_not_load(self):
        payload = dict(self.payload)
        payload["body_font"] = "Comic Sans MS"
        with self.assertRaises(ValueError):
            normalize_payload(payload)


if __name__ == "__main__":
    unittest.main()
