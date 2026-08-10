"""The shared registry document: what an upsert keeps, and what order it leaves.

Five scripts wrote the same four steps around `persons.json`,
`meta_stories.json` and their per-language derivations — read, find by id,
replace or append, write. The parts that differed between them were the parts
that mattered, so they are the parts pinned here: which fields survive an
update, and how the entries end up ordered.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from utils.registry import META_STORIES, Registry  # noqa: E402


class RegistryDocumentTests(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.path = Path(self._dir.name) / "persons.json"

    def write(self, document: dict) -> None:
        self.path.write_text(
            json.dumps(document, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def read(self) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def test_a_registry_that_does_not_exist_yet_reads_as_empty(self) -> None:
        registry = Registry(self.path)
        self.assertEqual(registry.entries, [])
        registry.upsert({"id": "ada_lovelace", "name": "Ada Lovelace"})
        registry.save()
        self.assertEqual(len(self.read()["people"]), 1)

    def test_a_new_entry_is_appended(self) -> None:
        self.write({"people": [{"id": "a", "name": "A"}]})
        registry = Registry(self.path)
        registry.upsert({"id": "b", "name": "B"})
        registry.save()
        self.assertEqual([p["id"] for p in self.read()["people"]], ["a", "b"])

    def test_an_existing_entry_is_replaced_in_place(self) -> None:
        # Position matters: an update must not move a person to the end of a
        # list another script keeps ordered.
        self.write({"people": [{"id": "a"}, {"id": "b"}, {"id": "c"}]})
        registry = Registry(self.path)
        registry.upsert({"id": "b", "name": "Bee"})
        registry.save()
        people = self.read()["people"]
        self.assertEqual([p["id"] for p in people], ["a", "b", "c"])
        self.assertEqual(people[1]["name"], "Bee")

    def test_merging_keeps_fields_the_writer_knows_nothing_about(self) -> None:
        # The portrait script and the events script both write this entry, and
        # neither may drop what the other put there.
        self.write({"people": [{"id": "a", "name": "A", "portrait": {"image": "x"}}]})
        registry = Registry(self.path)
        registry.upsert({"id": "a", "summary": "S"})
        registry.save()
        entry = self.read()["people"][0]
        self.assertEqual(entry["portrait"], {"image": "x"})
        self.assertEqual(entry["summary"], "S")

    def test_merge_false_replaces_the_entry_outright(self) -> None:
        # A translated entry is derived whole from the English one, so a field
        # it does not carry was dropped on purpose.
        self.write({"people": [{"id": "a", "name": "A", "stale": True}]})
        registry = Registry(self.path)
        registry.upsert({"id": "a", "name": "Ä"}, merge=False)
        registry.save()
        self.assertEqual(self.read()["people"][0], {"id": "a", "name": "Ä"})

    def test_preserved_fields_come_from_the_existing_entry(self) -> None:
        # `created` records when a person first appeared and must survive every
        # later write, even one that names a different value.
        self.write({"people": [{"id": "a", "created": "2020", "lastUpdated": "2020"}]})
        registry = Registry(self.path)
        registry.upsert(
            {"id": "a", "created": "2026", "lastUpdated": "2026"},
            preserve=("created",),
        )
        registry.save()
        entry = self.read()["people"][0]
        self.assertEqual(entry["created"], "2020")
        self.assertEqual(entry["lastUpdated"], "2026")

    def test_a_preserved_field_the_existing_entry_lacks_takes_the_new_value(
        self,
    ) -> None:
        # An entry written before `created` existed gets one now, rather than
        # being left without.
        self.write({"people": [{"id": "a"}]})
        registry = Registry(self.path)
        registry.upsert({"id": "a", "created": "2026"}, preserve=("created",))
        registry.save()
        self.assertEqual(self.read()["people"][0]["created"], "2026")

    def test_sort_by_name_is_how_the_person_registries_are_kept(self) -> None:
        self.write({"people": [{"id": "c", "name": "Zoe"}, {"id": "a", "name": "Ada"}]})
        registry = Registry(self.path)
        registry.sort_by_name()
        registry.save()
        self.assertEqual([p["name"] for p in self.read()["people"]], ["Ada", "Zoe"])

    def test_sort_like_aligns_a_language_registry_with_the_english_one(self) -> None:
        self.write({"people": [{"id": "c"}, {"id": "a"}, {"id": "b"}]})
        registry = Registry(self.path)
        registry.sort_like(["a", "b", "c"])
        registry.save()
        self.assertEqual([p["id"] for p in self.read()["people"]], ["a", "b", "c"])

    def test_an_id_the_reference_does_not_know_sorts_to_the_end(self) -> None:
        # Otherwise a locally added entry would displace the aligned ones.
        self.write({"people": [{"id": "x"}, {"id": "a"}, {"id": "b"}]})
        registry = Registry(self.path)
        registry.sort_like(["a", "b"])
        registry.save()
        self.assertEqual([p["id"] for p in self.read()["people"]], ["a", "b", "x"])

    def test_keys_beside_the_collection_survive(self) -> None:
        # The file belongs to its writer, not to this class.
        self.write({"dataset": "persons", "people": [{"id": "a"}]})
        registry = Registry(self.path)
        registry.upsert({"id": "b"})
        registry.save()
        self.assertEqual(self.read()["dataset"], "persons")

    def test_a_meta_story_registry_uses_its_own_collection(self) -> None:
        path = Path(self._dir.name) / "meta_stories.json"
        registry = Registry(path, collection=META_STORIES)
        registry.upsert({"id": "computing_pioneers"})
        registry.save()
        document = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(
            [s["id"] for s in document["meta_stories"]], ["computing_pioneers"]
        )

    def test_remove_reports_whether_there_was_anything_to_remove(self) -> None:
        self.write({"people": [{"id": "a"}]})
        registry = Registry(self.path)
        self.assertTrue(registry.remove("a"))
        self.assertFalse(registry.remove("a"))


class UpdateRegisterTests(unittest.TestCase):
    """`generate_person_events.update_register` through the shared registry.

    This is the writer that owns a person's registry entry, and the one whose
    rules are easiest to break quietly: a lost `created` timestamp, a `null`
    portrait written where the key should simply be absent, or an entry that
    stops sorting where the rest of the file expects it.
    """

    def setUp(self) -> None:
        import generate_person_events as gpe

        self.gpe = gpe
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.path = Path(self._dir.name) / "persons.json"
        patched = unittest.mock.patch.object(gpe, "REGISTER_PATH", self.path)
        patched.start()
        self.addCleanup(patched.stop)

    def run_update(self, person_id: str, person: dict) -> dict:
        self.gpe.update_register(person_id, {"person": person}, self.path)
        return json.loads(self.path.read_text(encoding="utf-8"))

    def test_a_new_person_is_stamped_and_written(self) -> None:
        people = self.run_update("ada_lovelace", {"name": "Ada Lovelace"})["people"]
        self.assertEqual(people[0]["id"], "ada_lovelace")
        self.assertEqual(people[0]["created"], people[0]["lastUpdated"])

    def test_created_survives_a_second_write(self) -> None:
        self.path.write_text(
            json.dumps(
                {
                    "people": [
                        {
                            "id": "ada_lovelace",
                            "name": "Ada Lovelace",
                            "created": "2020-01-01T00:00:00+00:00",
                            "lastUpdated": "2020-01-01T00:00:00+00:00",
                        }
                    ]
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        entry = self.run_update("ada_lovelace", {"name": "Ada Lovelace"})["people"][0]
        self.assertEqual(entry["created"], "2020-01-01T00:00:00+00:00")
        self.assertNotEqual(entry["lastUpdated"], "2020-01-01T00:00:00+00:00")

    def test_no_portrait_means_no_portrait_key(self) -> None:
        # Not `"portrait": null` — the interface reads the key's absence.
        entry = self.run_update("ada_lovelace", {"name": "Ada Lovelace"})["people"][0]
        self.assertNotIn("portrait", entry)

    def test_an_existing_portrait_is_dropped_when_the_new_entry_has_none(self) -> None:
        # `update_register` sets the portrait explicitly, so a person whose
        # portrait went away must not keep the old one.
        self.path.write_text(
            json.dumps(
                {"people": [{"id": "a", "name": "A", "portrait": {"image": "old"}}]},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        entry = self.run_update("a", {"name": "A"})["people"][0]
        self.assertNotIn("portrait", entry)

    def test_the_register_stays_sorted_by_name(self) -> None:
        self.run_update("zoe", {"name": "Zoe"})
        people = self.run_update("ada_lovelace", {"name": "Ada Lovelace"})["people"]
        self.assertEqual([p["name"] for p in people], ["Ada Lovelace", "Zoe"])

    def test_fields_another_script_wrote_are_not_dropped(self) -> None:
        self.path.write_text(
            json.dumps(
                {"people": [{"id": "a", "name": "A", "tagline": "kept"}]}, indent=2
            )
            + "\n",
            encoding="utf-8",
        )
        entry = self.run_update("a", {"name": "A"})["people"][0]
        self.assertEqual(entry["tagline"], "kept")


class ShippedRegistryTests(unittest.TestCase):
    """Reading and writing a real registry has to change nothing.

    Three of the five writers used a bare `json.dumps` instead of the
    repository's canonical writer. If `Registry.save()` disagreed with the
    bytes already on disk, the first script to touch a registry would rewrite
    the whole file and bury its own change in the diff.
    """

    def test_every_registry_round_trips_byte_for_byte(self) -> None:
        data_dir = REPO_ROOT / "data"
        paths = sorted(data_dir.glob("persons*.json")) + sorted(
            data_dir.glob("meta_stories*.json")
        )
        self.assertGreater(len(paths), 2, "expected the shipped registries")
        for path in paths:
            with self.subTest(registry=path.name):
                original = path.read_text(encoding="utf-8")
                collection = (
                    META_STORIES if path.name.startswith("meta_stories") else "people"
                )
                with tempfile.TemporaryDirectory() as tmp:
                    copy = Path(tmp) / path.name
                    copy.write_text(original, encoding="utf-8")
                    Registry(copy, collection=collection).save()
                    self.assertEqual(copy.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
