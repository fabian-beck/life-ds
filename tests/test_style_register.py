"""Tests for the style register as its writer and its reader share it.

`data/person_styles.json` nests its entries under a "styles" key. The reader
in `utils/person_style.py` and the writer in `generate_person_style.py` have to
agree on that, because an entry written beside "styles" instead of inside it
is a style the image steps never find. A review step once read the top level
and reported a review of a style it had never loaded; the review is gone, and
the round trip below is what still has to hold.
"""

from __future__ import annotations

import json
import sys
import unittest
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import generate_person_style  # noqa: E402
import utils.person_style  # noqa: E402
from utils.person_style import load_style  # noqa: E402

STYLE = {
    "primary": "#3366FF",
    "secondary": "#FFAA00",
    "background": "#101014",
    "heading_font": "Lora",
    "body_font": "Inter",
}


class StyleRegisterRoundTripTest(unittest.TestCase):
    """What the generator writes has to be what the image steps read next."""

    def _register(self, stack, payload: dict) -> Path:
        directory = Path(stack.enter_context(TemporaryDirectory()))
        path = directory / "person_styles.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        for module in (utils.person_style, generate_person_style):
            stack.enter_context(patch.object(module, "STYLES_PATH", path))
        return path

    def setUp(self) -> None:
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)

    def test_reads_an_entry_nested_under_styles(self):
        self._register(self.stack, {"styles": {"ada_lovelace": STYLE}})

        self.assertEqual(load_style("ada_lovelace"), STYLE)

    def test_writes_the_entry_where_the_reader_looks(self):
        path = self._register(self.stack, {"styles": {"ada_lovelace": STYLE}})
        revised = {**STYLE, "primary": "#00CC88"}

        register = generate_person_style.load_styles()
        register["styles"]["ada_lovelace"] = revised
        generate_person_style.write_styles(register)

        self.assertEqual(load_style("ada_lovelace"), revised)
        written = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(list(written), ["styles"])

    def test_a_person_with_no_entry_reads_as_none(self):
        self._register(self.stack, {"styles": {"ada_lovelace": STYLE}})

        self.assertIsNone(load_style("grace_hopper"))


class CorpusStyleLookupTest(unittest.TestCase):
    """The register the application ships answers the image steps' lookups."""

    def test_every_registered_style_is_reachable(self):
        data = json.loads(
            utils.person_style.STYLES_PATH.read_text(encoding="utf-8")
        )
        styles = data.get("styles", {})
        self.assertTrue(styles, "person_styles.json carries no styles")
        for person_id in styles:
            with self.subTest(person_id=person_id):
                self.assertIsNotNone(load_style(person_id))


if __name__ == "__main__":
    unittest.main()
