"""A background pattern goes through the generator's gate before it is stored.

`generate_person_style.py` guarantees a background pattern is two colors, is
free of opacity, measures 160x160, and is painted edge to edge over a black
ground. The story renders it by multiplying the tile against its primary
color under `background-blend-mode: multiply`, so black is the field and white
the marks — and a tile with no ground is not a subtler pattern but an
inverted one, because the primary shows through everywhere the tile is
transparent and the marks multiply to the same color.

A model once proposed, in its own words, "a simpler transparent circuit tile
so the navy page background remains visually continuous", and the whole story
washed flat primary. Model-written SVG is text like any other, so every tile
goes through the sanitiser on its way into the registry, which is the only
place the rule is enforced.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from generate_person_style import sanitise_pattern_svg  # noqa: E402


GROUNDED = (
    '<svg width="160" height="160" viewBox="0 0 160 160" '
    'xmlns="http://www.w3.org/2000/svg"><rect width="160" height="160" '
    'fill="#000000"/><path d="M0 80H160" stroke="#FFFFFF" stroke-width="4"/></svg>'
)
# The shape the model actually proposed: marks, no ground.
TRANSPARENT = (
    '<svg width="160" height="160" viewBox="0 0 160 160" '
    'xmlns="http://www.w3.org/2000/svg"><path d="M0 80H160" stroke="#FFFFFF" '
    'stroke-width="4"/></svg>'
)


class PatternGroundTests(unittest.TestCase):
    def test_a_transparent_tile_gains_the_black_ground(self):
        sanitised = sanitise_pattern_svg(TRANSPARENT)
        self.assertIn('<rect width="160" height="160" fill="#000000"', sanitised)
        self.assertIn('stroke="#FFFFFF"', sanitised)

    def test_a_grounded_tile_is_not_given_a_second_ground(self):
        self.assertEqual(sanitise_pattern_svg(GROUNDED).count('fill="#000000"'), 1)

    def test_a_gray_is_snapped_rather_than_rejected(self):
        """The sanitiser resolves a near-black or near-white to the real one."""
        sanitised = sanitise_pattern_svg(
            TRANSPARENT.replace('stroke="#FFFFFF"', 'stroke="#EEEEEE"')
        )
        self.assertIn('stroke="#FFFFFF"', sanitised)

    def test_an_unusable_tile_is_rejected(self):
        for label, proposed in (
            ("a color the palette has no room for",
             '<svg xmlns="http://www.w3.org/2000/svg" width="160" '
             'height="160"><path d="M0 80H160" stroke="red"/></svg>'),
            ("no white", '<svg xmlns="http://www.w3.org/2000/svg" width="160" '
                         'height="160"><rect width="160" height="160" fill="#000000"/></svg>'),
            ("not svg", "<div>nope</div>"),
        ):
            with self.subTest(label):
                with self.assertRaises(ValueError):
                    sanitise_pattern_svg(proposed)


if __name__ == "__main__":
    unittest.main()
