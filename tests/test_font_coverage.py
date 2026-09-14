"""The fonts the generator may pick must be the fonts the app actually loads.

`scripts/generate_person_style.py` offers a fixed vocabulary of heading and body
faces, and `src/fonts.css` self-hosts them. Those two lists are edited in
different languages, in different directories, for different reasons — so they
drift. A face the generator can choose but the app never loads does not fail
anything loudly: the story just renders in the fallback font, which looks
plausible enough to survive review.

Both lists are implementation, so both are checked here. What a stored style
happens to name is not: the vocabulary is closed at the point the style is
written, and a choice outside it is rejected there.
"""

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from generate_person_style import (  # noqa: E402
    BODY_FONT_CHOICES,
    HEADING_FONT_CHOICES,
)

FONTS_CSS = ROOT / "src" / "fonts.css"

# "@fontsource/space-grotesk/latin-ext-700.css" -> ("space-grotesk", "latin-ext-700")
# Both @import notations are accepted: stylelint-config-standard rewrites the
# bare string form to url(), and Vite resolves either against node_modules.
IMPORT_RE = re.compile(
    r'@import\s+(?:url\(\s*)?"@fontsource/([^/"]+)/([^"]+)\.css"', re.IGNORECASE
)


def loaded_packages():
    """Map each @fontsource package in src/fonts.css to the cuts it imports."""
    packages: dict[str, set[str]] = {}
    for package, cut in IMPORT_RE.findall(FONTS_CSS.read_text(encoding="utf-8")):
        packages.setdefault(package, set()).add(cut)
    return packages


def package_name(font_family):
    """"Source Serif 4" -> "source-serif-4", matching @fontsource's naming."""
    return re.sub(r"[^a-z0-9]+", "-", font_family.lower()).strip("-")


class FontCoverageTests(unittest.TestCase):
    def test_every_generator_choice_is_self_hosted(self):
        packages = loaded_packages()
        missing = [
            font
            for font in HEADING_FONT_CHOICES + BODY_FONT_CHOICES
            if package_name(font) not in packages
        ]
        self.assertEqual(
            missing,
            [],
            "generate_person_style.py may pick these, but src/fonts.css does not "
            "load them, so they would render in the fallback font",
        )

    def test_no_font_is_loaded_that_nothing_can_use(self):
        """The reverse drift: a face kept alive in CSS after nothing selects it."""
        selectable = {
            package_name(font) for font in HEADING_FONT_CHOICES + BODY_FONT_CHOICES
        }
        unused = sorted(set(loaded_packages()) - selectable)
        self.assertEqual(
            unused,
            [],
            "src/fonts.css loads these, but the generator can no longer pick them",
        )

    def test_latin_ext_is_loaded_wherever_latin_is(self):
        """Latin Extended carries "ł" (Skłodowska) and 12 other letters the
        content needs; loading `latin` alone would mangle those names."""
        for package, cuts in sorted(loaded_packages().items()):
            latin = {cut for cut in cuts if not cut.startswith("latin-ext")}
            for cut in sorted(latin):
                expected = cut.replace("latin-", "latin-ext-", 1)
                self.assertIn(
                    expected,
                    cuts,
                    f"{package} imports {cut} without its latin-ext counterpart",
                )


if __name__ == "__main__":
    unittest.main()
