"""The hidden flag: what it may say, and that every registry says the same.

A person or collection the deployed site should not show carries
``"hidden": true`` in its registry entry, and nothing otherwise. The
application reads the English registries as the reference; the localized
ones are derived from them whole, so a flag the two disagree on is a
derivation that has fallen behind. Both are counted here, along with the
registry writer that has to carry the flag through a regeneration.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
sys.path.insert(0, str(ROOT / "scripts"))

import generate_meta_story  # noqa: E402
import set_hidden  # noqa: E402
from utils.registry import META_STORIES, PEOPLE  # noqa: E402


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def flags(path, collection):
    return {
        entry["id"]: entry.get("hidden")
        for entry in load_json(path)[collection]
        if "hidden" in entry
    }


REGISTRIES = (
    ("persons.json", "persons_*.json", PEOPLE),
    ("meta_stories.json", "meta_stories_*.json", META_STORIES),
)


class HiddenFlagTests(unittest.TestCase):
    def test_the_flag_is_the_boolean_true_or_absent(self):
        for english, localized, collection in REGISTRIES:
            for path in [DATA_DIR / english] + sorted(DATA_DIR.glob(localized)):
                with self.subTest(registry=path.name):
                    for entry_id, value in flags(path, collection).items():
                        self.assertIs(value, True, entry_id)

    def test_localized_registries_hide_what_the_english_one_hides(self):
        for english, localized, collection in REGISTRIES:
            reference = flags(DATA_DIR / english, collection)
            for path in sorted(DATA_DIR.glob(localized)):
                with self.subTest(registry=path.name):
                    self.assertEqual(flags(path, collection), reference)


class SetHiddenTests(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.data_dir = Path(self._dir.name)
        for name in ("persons.json", "persons_de.json"):
            (self.data_dir / name).write_text(
                json.dumps({"people": [{"id": "ada"}, {"id": "hans"}]}),
                encoding="utf-8",
            )
        self.addCleanup(
            unittest.mock.patch.object(set_hidden, "DATA_DIR", self.data_dir).start
        )
        unittest.mock.patch.object(set_hidden, "DATA_DIR", self.data_dir).start()
        self.addCleanup(unittest.mock.patch.stopall)

    def entry(self, name, entry_id):
        return next(
            e for e in load_json(self.data_dir / name)["people"] if e["id"] == entry_id
        )

    def test_hiding_marks_every_registry_and_showing_removes_the_key(self):
        self.assertEqual(set_hidden.main(["--person", "hans"]), 0)
        for name in ("persons.json", "persons_de.json"):
            self.assertIs(self.entry(name, "hans").get("hidden"), True)
            self.assertNotIn("hidden", self.entry(name, "ada"))
        self.assertEqual(set_hidden.main(["--show", "--person", "hans"]), 0)
        for name in ("persons.json", "persons_de.json"):
            self.assertNotIn("hidden", self.entry(name, "hans"))

    def test_an_unknown_id_is_reported_and_fails(self):
        self.assertEqual(set_hidden.main(["--person", "nobody"]), 1)
        self.assertEqual(
            [e["id"] for e in load_json(self.data_dir / "persons.json")["people"]],
            ["ada", "hans"],
        )


class MetaStoryRegistryWriterTests(unittest.TestCase):
    def test_regenerating_a_hidden_collection_keeps_it_hidden(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "meta_stories.json"
            path.write_text(
                json.dumps(
                    {
                        "meta_stories": [
                            {"id": "bamberg", "created": "2025", "hidden": True}
                        ]
                    }
                ),
                encoding="utf-8",
            )
            meta_story = {
                "meta_story": {
                    "title": "Bamberg",
                    "tagline": "A city",
                    "person_ids": ["henry_ii"],
                    "date_range_start": 1000,
                    "date_range_end": 1944,
                    "lastUpdated": "2026",
                }
            }
            with unittest.mock.patch.object(
                generate_meta_story, "META_STORIES_REGISTER", path
            ):
                self.assertTrue(
                    generate_meta_story.update_meta_stories_registry(
                        "bamberg", meta_story
                    )
                )
            (entry,) = load_json(path)["meta_stories"]
            self.assertIs(entry.get("hidden"), True)
            self.assertEqual(entry["created"], "2025")


if __name__ == "__main__":
    unittest.main()
