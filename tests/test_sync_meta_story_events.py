import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from sync_meta_story_events import (  # noqa: E402
    describe_dropped,
    sync_meta_story_events,
)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


class SyncMetaStoryEventsTests(unittest.TestCase):
    def test_reorders_updates_and_removes_only_person_event_references(self):
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory)
            old_person = {
                "events": [
                    {"date": "1900", "date_precision": "year", "title": "Born"},
                    {
                        "date": "1920",
                        "date_precision": "year",
                        "title": "Built Engine",
                    },
                    {"date": "1930", "date_precision": "year", "title": "Award"},
                ]
            }
            new_person = {
                "events": [
                    {"date": "1910", "date_precision": "year", "title": "Studied"},
                    {
                        "date": "1920",
                        "date_precision": "month",
                        "title": "Built the Engine",
                    },
                    {"date": "1900", "date_precision": "year", "title": "Born"},
                ]
            }
            story = {
                "meta_story": {"id": "machines", "lastUpdated": "old"},
                "chapters": [
                    {
                        "title": "A chapter that must stay",
                        "person_events": [
                            {
                                "person_id": "person_a",
                                "event_date": "1920",
                                "event_date_precision": "year",
                                "event_title": "Built Engine",
                                "event_index": 1,
                                "theme_connection": "Keep this curation.",
                            },
                            {
                                "person_id": "person_a",
                                "event_date": "1930",
                                "event_date_precision": "year",
                                "event_title": "Award",
                                "event_index": 2,
                                "theme_connection": "Deleted event.",
                            },
                            {
                                "person_id": "person_b",
                                "event_date": "1950",
                                "event_date_precision": "year",
                                "event_title": "Untouched",
                                "event_index": 0,
                                "theme_connection": "Other person.",
                            },
                        ],
                    }
                ],
            }
            translated_story = json.loads(json.dumps(story))
            translated_story["chapters"][0]["person_events"][0][
                "event_title"
            ] = "Baute Maschine"
            translated_story["translation"] = {"source_fingerprint": "stale"}
            translated_person = {
                "events": [
                    {"title": "Studierte"},
                    {"title": "Baute die Maschine"},
                    {"title": "Geboren"},
                ]
            }

            write_json(data_dir / "meta_stories" / "machines.json", story)
            write_json(
                data_dir / "meta_stories" / "de" / "machines.json",
                translated_story,
            )
            write_json(
                data_dir / "people" / "person_a" / "de" / "life_events.json",
                translated_person,
            )

            report = sync_meta_story_events(
                "person_a",
                old_person_data=old_person,
                new_person_data=new_person,
                data_dir=data_dir,
            )

            result = json.loads(
                (data_dir / "meta_stories" / "machines.json").read_text()
            )
            references = result["chapters"][0]["person_events"]
            self.assertEqual(2, len(references))
            self.assertEqual("Built the Engine", references[0]["event_title"])
            self.assertEqual("month", references[0]["event_date_precision"])
            self.assertEqual("Keep this curation.", references[0]["theme_connection"])
            self.assertEqual("person_b", references[1]["person_id"])
            self.assertEqual("A chapter that must stay", result["chapters"][0]["title"])

            localized = json.loads(
                (data_dir / "meta_stories" / "de" / "machines.json").read_text()
            )
            localized_refs = localized["chapters"][0]["person_events"]
            self.assertEqual("Baute die Maschine", localized_refs[0]["event_title"])
            self.assertEqual(1, localized_refs[0]["event_index"])
            self.assertNotEqual("stale", localized["translation"]["source_fingerprint"])
            self.assertEqual(16, len(localized["translation"]["source_fingerprint"]))
            self.assertEqual(1, report["stories"])
            self.assertEqual(2, report["removed"])

    def test_refreshes_translation_when_english_reference_is_already_current(self):
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory)
            person = {
                "events": [
                    {"date": "1920", "date_precision": "year", "title": "Engine"}
                ]
            }
            reference = {
                "person_id": "person_a",
                "event_date": "1920",
                "event_date_precision": "year",
                "event_title": "Engine",
                "event_index": 0,
                "theme_connection": "Preserved",
            }
            story = {
                "meta_story": {"id": "machines"},
                "chapters": [{"person_events": [reference]}],
            }
            localized = json.loads(json.dumps(story))
            localized["chapters"][0]["person_events"][0]["event_title"] = "Alt"
            write_json(data_dir / "meta_stories" / "machines.json", story)
            write_json(data_dir / "meta_stories" / "de" / "machines.json", localized)
            write_json(
                data_dir / "people" / "person_a" / "de" / "life_events.json",
                {"events": [{"title": "Maschine"}]},
            )

            sync_meta_story_events(
                "person_a", new_person_data=person, data_dir=data_dir
            )

            result = json.loads(
                (data_dir / "meta_stories" / "de" / "machines.json").read_text()
            )
            self.assertEqual(
                "Maschine",
                result["chapters"][0]["person_events"][0]["event_title"],
            )


if __name__ == "__main__":
    unittest.main()


class DroppedReferenceReportingTests(unittest.TestCase):
    """A dropped reference is a curated choice the story loses for good.

    The chapter keeps its title, its date range, its lifelines and the composed
    prose that names the person, so the story reads as though nothing happened
    and contributes one marker fewer to the timeline. Three separate stories in
    this corpus lost events that way before anyone noticed, because the run
    reported a bare count.
    """

    def _sync(self, data_dir, story, old_person, new_person):
        write_json(data_dir / "meta_stories" / "story.json", story)
        return sync_meta_story_events(
            "einstein",
            old_person_data=old_person,
            new_person_data=new_person,
            data_dir=data_dir,
        )

    def test_names_the_story_chapter_and_event_it_could_not_carry_over(self):
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory)
            report = self._sync(
                data_dir,
                {
                    "chapters": [
                        {
                            "title": "Quanta Enter the Atom (1905-1913)",
                            "person_events": [
                                {
                                    "person_id": "einstein",
                                    "event_index": 0,
                                    "event_date": "1905-06-30",
                                    "event_title": "Publishes Annus Mirabilis papers",
                                },
                                {
                                    "person_id": "bohr",
                                    "event_index": 5,
                                    "event_date": "1913-07",
                                    "event_title": "Publishes Three Atomic Model Papers",
                                },
                            ],
                        }
                    ]
                },
                {
                    "events": [
                        {
                            "date": "1905-06-30",
                            "title": "Publishes Annus Mirabilis papers",
                        }
                    ]
                },
                {"events": [{"date": "1915", "title": "Formulates General Relativity"}]},
            )

            self.assertEqual(1, report["removed"])
            dropped = report["dropped"]
            self.assertEqual(1, len(dropped))
            self.assertEqual("story", dropped[0].story_id)
            self.assertEqual(
                "Quanta Enter the Atom (1905-1913)", dropped[0].chapter_title
            )
            self.assertEqual(
                "Publishes Annus Mirabilis papers", dropped[0].event_title
            )
            self.assertEqual("1905-06-30", dropped[0].event_date)

    def test_a_chapter_that_keeps_another_persons_event_is_not_reported_as_emptied(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory)
            report = self._sync(
                data_dir,
                {
                    "chapters": [
                        {
                            "title": "Quanta Enter the Atom (1905-1913)",
                            "person_events": [
                                {
                                    "person_id": "einstein",
                                    "event_index": 0,
                                    "event_date": "1905-06-30",
                                    "event_title": "Annus Mirabilis",
                                },
                                {
                                    "person_id": "bohr",
                                    "event_index": 5,
                                    "event_date": "1913-07",
                                    "event_title": "Atomic Model Papers",
                                },
                            ],
                        }
                    ]
                },
                {"events": [{"date": "1905-06-30", "title": "Annus Mirabilis"}]},
                {"events": [{"date": "1915", "title": "General Relativity"}]},
            )

            self.assertFalse(report["dropped"][0].chapter_emptied)

    def test_a_chapter_left_with_no_events_at_all_is_reported_as_emptied(self):
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory)
            report = self._sync(
                data_dir,
                {
                    "chapters": [
                        {
                            "title": "Saintly Memory (1025-1040)",
                            "person_events": [
                                {
                                    "person_id": "einstein",
                                    "event_index": 0,
                                    "event_date": "1905-06-30",
                                    "event_title": "Annus Mirabilis",
                                }
                            ],
                        }
                    ]
                },
                {"events": [{"date": "1905-06-30", "title": "Annus Mirabilis"}]},
                {"events": [{"date": "1915", "title": "General Relativity"}]},
            )

            self.assertTrue(report["dropped"][0].chapter_emptied)
            self.assertIn("no events at all", report["dropped"][0].describe())

    def test_a_sync_that_carries_everything_over_reports_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory)
            report = self._sync(
                data_dir,
                {
                    "chapters": [
                        {
                            "title": "Quanta Enter the Atom (1905-1913)",
                            "person_events": [
                                {
                                    "person_id": "einstein",
                                    "event_index": 0,
                                    "event_date": "1905-06-30",
                                    "event_title": "Annus Mirabilis",
                                }
                            ],
                        }
                    ]
                },
                {"events": [{"date": "1905-06-30", "title": "Annus Mirabilis"}]},
                {
                    "events": [
                        {"date": "1900", "title": "Born"},
                        {"date": "1905-06-30", "title": "Annus Mirabilis"},
                    ]
                },
            )

            self.assertEqual(0, report["removed"])
            self.assertEqual([], report["dropped"])
            self.assertEqual([], describe_dropped(report))


class DescribeDroppedTests(unittest.TestCase):
    def test_the_lines_name_the_command_that_repairs_the_story(self):
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory)
            write_json(
                data_dir / "meta_stories" / "quantum_physics_pioneers.json",
                {
                    "chapters": [
                        {
                            "title": "Quanta",
                            "person_events": [
                                {
                                    "person_id": "einstein",
                                    "event_index": 0,
                                    "event_date": "1905",
                                    "event_title": "Annus Mirabilis",
                                }
                            ],
                        }
                    ]
                },
            )
            report = sync_meta_story_events(
                "einstein",
                old_person_data={"events": [{"date": "1905", "title": "Annus Mirabilis"}]},
                new_person_data={"events": [{"date": "1915", "title": "Relativity"}]},
                data_dir=data_dir,
            )

            lines = describe_dropped(report)

            self.assertIn("Annus Mirabilis", "\n".join(lines))
            self.assertIn(
                "python scripts/generate_meta_story.py quantum_physics_pioneers",
                "\n".join(lines),
            )
