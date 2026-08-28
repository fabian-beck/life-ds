"""The map must draw itself out of this repository, not out of a CDN.

`public/basemap.pmtiles` has always been served from the site, but the style
that renders it pointed its sprite and glyph URLs at protomaps.github.io, so
every map view still disclosed the visitor's IP to a third party and lost its
icons and letterforms whenever that host was unreachable.

`scripts/vendor_basemap_assets.mjs` downloads those assets into
`public/basemap-assets/`. Nothing fails loudly when the vendored tree is
incomplete: MapLibre logs a warning and draws the missing letterforms itself,
which looks close enough to survive review. So the tree is checked here
instead — no network, just what the repository ships.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASEMAP_JS = ROOT / "src" / "utils" / "basemap.js"
ASSETS = ROOT / "public" / "basemap-assets"
SPRITES = ASSETS / "sprites" / "v4"
FONTS = ASSETS / "fonts"

SPRITE_FILES = ("dark.json", "dark.png", "dark@2x.json", "dark@2x.png")

# The range every label needs, whatever script it is written in.
FIRST_RANGE = "0-255.pbf"

RANGE_RE = re.compile(r"^(\d+)-(\d+)\.pbf$")


class BasemapAssetTests(unittest.TestCase):
    """The vendored sprite and glyph tree, and the style that points at it."""

    def test_the_style_names_no_third_party_host(self):
        source = BASEMAP_JS.read_text(encoding="utf-8")
        # The quote and scheme are part of the needle so that prose about the
        # host it replaced does not count as the host itself.
        self.assertNotIn(
            '"https://protomaps.github.io',
            source,
            "the basemap style must draw from public/basemap-assets/, not a CDN",
        )
        self.assertIn('"/basemap-assets/fonts/{fontstack}/{range}.pbf"', source)
        self.assertIn('absoluteAssetUrl("/basemap-assets/sprites/v4/dark")', source)

    def test_every_sprite_the_style_may_ask_for_is_present(self):
        for name in SPRITE_FILES:
            with self.subTest(sprite=name):
                self.assertTrue((SPRITES / name).is_file(), f"missing {name}")

    def test_the_font_stacks_carry_the_same_ranges(self):
        stacks = sorted(path.name for path in FONTS.iterdir() if path.is_dir())
        self.assertTrue(stacks, "no vendored font stacks")

        ranges_per_stack = {}
        for stack in stacks:
            ranges = sorted(path.name for path in (FONTS / stack).glob("*.pbf"))
            with self.subTest(stack=stack):
                self.assertIn(FIRST_RANGE, ranges, f"{stack} has no {FIRST_RANGE}")
                for name in ranges:
                    self.assertRegex(name, RANGE_RE, f"{stack}/{name}")
            ranges_per_stack[stack] = ranges

        # A stack that lost half its ranges renders in a fallback face for
        # exactly the places whose names fall in them, which is the kind of
        # gap a screenshot does not show.
        first, *rest = stacks
        for stack in rest:
            with self.subTest(stack=stack):
                self.assertEqual(
                    ranges_per_stack[stack],
                    ranges_per_stack[first],
                    f"{stack} and {first} were vendored from different runs",
                )

    def test_no_glyph_range_is_an_error_page(self):
        # An upstream 404 saved verbatim is a small HTML file rather than a
        # protobuf, and the map then draws nothing for that range.
        for path in FONTS.glob("*/*.pbf"):
            with self.subTest(range=str(path.relative_to(FONTS))):
                head = path.read_bytes()[:16]
                self.assertNotIn(b"<", head, f"{path.name} is not a glyph range")


if __name__ == "__main__":
    unittest.main()
