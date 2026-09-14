"""The frame vocabulary and the gate a meta story style is written through.

A malformed color, an unloadable font or broken SVG markup would degrade the
article silently, so ``normalize_payload`` is where each of those is caught —
on the way into the registry, in the one step that writes it. What it lets
through is checked here, together with the frame names, which have to mean the
same thing in the generator, in ``metaStoryStyles.js``, and in the stylesheet
that draws them.
"""

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from generate_meta_story_style import (  # noqa: E402
    FRAME_CHOICES,
    normalize_payload,
)

FRAMES_JS = ROOT / "src" / "utils" / "metaStoryStyles.js"
FRAMES_CSS = ROOT / "src" / "meta-frames.css"


class MetaStoryFrameTests(unittest.TestCase):
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

    def test_every_frame_is_actually_drawn(self):
        """A name with no rules is a frame that silently looks like the default.

        `FRAMES` gives a name its geometry; `meta-frames.css` gives it the
        line work and the ornament that make it that frame rather than a
        rounded rectangle.
        """
        css = FRAMES_CSS.read_text(encoding="utf-8")
        for name in FRAME_CHOICES:
            with self.subTest(frame=name):
                self.assertIn(f'[data-ms-frame="{name}"]', css)

    def test_frame_decoration_never_swallows_a_click(self):
        """The panels carry links; a decoration that eats one is invisible."""
        css = FRAMES_CSS.read_text(encoding="utf-8")
        rules = re.findall(r"([^{}]*)\{([^{}]*)\}", css)
        decorations = [
            (selector.strip(), body)
            for selector, body in rules
            if "::before" in re.sub(r"/\*.*?\*/", "", selector, flags=re.S)
            or "::after" in re.sub(r"/\*.*?\*/", "", selector, flags=re.S)
        ]
        self.assertTrue(decorations)
        for selector, body in decorations:
            with self.subTest(selector=selector.splitlines()[-1][:60]):
                self.assertIn("pointer-events: none", body)


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
