"""The person registries and the places that have to agree with them.

A person is described in four places at once: the English registry, the German
one, the per-person data directory, and the style registry the app reads to
paint the story. Nothing in the build fails when one of them falls behind, so
drift is invisible until a reader opens the story that lost its palette — or
until someone counts the people in the project and gets a different number
depending on which file they counted. These tests are the counting.
"""

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
PERSONS_PATH = DATA_DIR / "persons.json"
PERSON_STYLES_PATH = DATA_DIR / "person_styles.json"
PEOPLE_DIR = DATA_DIR / "people"
META_STORIES_DIR = DATA_DIR / "meta_stories"


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def registry_ids(path):
    return {person["id"] for person in load_json(path)["people"]}


def localized_registries():
    """Every persons_<language>.json next to the English registry."""
    return sorted(DATA_DIR.glob("persons_*.json"))


class PersonRegistryTests(unittest.TestCase):
    def setUp(self):
        self.person_ids = registry_ids(PERSONS_PATH)

    def test_the_registry_is_not_empty(self):
        # Every other assertion here is a set comparison, and comparing empty
        # sets would pass while saying nothing.
        self.assertTrue(self.person_ids)

    def test_localized_registries_describe_the_same_people(self):
        for path in localized_registries():
            with self.subTest(registry=path.name):
                self.assertEqual(registry_ids(path), self.person_ids)

    def test_every_person_has_a_data_directory(self):
        directories = {
            entry.name for entry in PEOPLE_DIR.iterdir() if entry.is_dir()
        }
        self.assertEqual(directories, self.person_ids)

    def test_every_person_has_life_events(self):
        for person_id in sorted(self.person_ids):
            with self.subTest(person_id=person_id):
                self.assertTrue((PEOPLE_DIR / person_id / "life_events.json").is_file())

    def test_style_registry_and_person_registry_hold_the_same_ids(self):
        styles = load_json(PERSON_STYLES_PATH)["styles"]
        self.assertEqual(set(styles), self.person_ids)

    def test_meta_stories_only_reference_people_that_exist(self):
        for path in sorted(META_STORIES_DIR.glob("*.json")):
            person_ids = load_json(path).get("meta_story", {}).get("person_ids", [])
            with self.subTest(meta_story=path.stem):
                self.assertLessEqual(set(person_ids), self.person_ids)


if __name__ == "__main__":
    unittest.main()
