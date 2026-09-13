from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import generate_chapter_illustrations as chapter_art  # noqa: E402


def _dataset() -> Dict[str, Any]:
    return {
        "person_id": "ada_lovelace",
        "person": {
            "name": "Ada_Lovelace",
            "primary_roles": ["mathematician"],
            "summary": "A summary.",
        },
        "chapters": [
            {"id": "first", "headline": "A First Light", "date_start": "1815"},
            {"id": "second", "headline": "The Engine", "date_start": "1840"},
        ],
        "events": [
            {"chapter": "first", "title": "Born", "description": "Born in London."},
            {"chapter": "second", "title": "Notes", "description": "Wrote the notes."},
        ],
    }


class ConceptPromptTests(unittest.TestCase):
    def test_prompt_gives_each_chapter_only_its_own_events(self) -> None:
        prompt = chapter_art.build_concept_prompt(_dataset())

        first = prompt.index("id: first")
        second = prompt.index("id: second")
        self.assertIn("Born in London.", prompt[first:second])
        self.assertNotIn("Wrote the notes.", prompt[first:second])
        self.assertIn("Wrote the notes.", prompt[second:])

    def test_prompt_writes_the_name_the_way_a_reader_would(self) -> None:
        # Datasets store the slug the person was created from.
        self.assertIn("SUBJECT: Ada Lovelace", chapter_art.build_concept_prompt(_dataset()))

    def test_prompt_strips_annotation_markup_from_descriptions(self) -> None:
        dataset = _dataset()
        dataset["events"][0]["description"] = "She met [[Charles_Babbage|Babbage]]."
        prompt = chapter_art.build_concept_prompt(dataset)
        self.assertIn("She met Babbage.", prompt)
        self.assertNotIn("[[", prompt)


class ConceptParsingTests(unittest.TestCase):
    def test_a_concept_for_an_unknown_chapter_is_dropped(self) -> None:
        parsed = chapter_art.ChapterConcepts(
            concepts=[
                chapter_art.ChapterConcept(chapter_id="first", concept="A  split orb."),
                chapter_art.ChapterConcept(chapter_id="ghost", concept="A stray."),
            ]
        )
        with patch.object(chapter_art, "parse_structured", return_value=parsed):
            concepts = chapter_art.write_chapter_concepts(Mock(), _dataset())

        self.assertEqual(concepts, {"first": "A split orb."})

    def test_a_call_that_returns_nothing_yields_no_concepts(self) -> None:
        with patch.object(chapter_art, "parse_structured", return_value=None):
            self.assertEqual(chapter_art.write_chapter_concepts(Mock(), _dataset()), {})


class SyncTests(unittest.TestCase):
    """A path is not prose, so every language gets the same one."""

    def test_every_language_copy_is_given_the_illustration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            english = root / "life_events.json"
            german = root / "de" / "life_events.json"
            german.parent.mkdir()
            for path, headline in ((english, "A First Light"), (german, "Erstes Licht")):
                path.write_text(
                    json.dumps(
                        {
                            "chapters": [
                                {"id": "first", "headline": headline},
                                {"id": "second", "headline": "Untouched"},
                            ]
                        }
                    ),
                    encoding="utf-8",
                )

            illustration = {
                "image": "/chapter_art/ada_lovelace/first_medium.webp",
                "full": "/chapter_art/ada_lovelace/first_full.webp",
            }
            files: List[Path] = [english, german]
            with (
                patch.object(chapter_art, "event_files", return_value=files),
                patch.object(chapter_art, "REPO_ROOT", root),
            ):
                updated = chapter_art.sync_chapter_illustrations(
                    "ada_lovelace", {"first": illustration}
                )

            self.assertEqual(len(updated), 2)
            for path in files:
                chapters = json.loads(path.read_text(encoding="utf-8"))["chapters"]
                self.assertEqual(chapters[0]["illustration"], illustration)
                self.assertNotIn("illustration", chapters[1])

            # The translated headline survived being given a picture.
            german_data = json.loads(german.read_text(encoding="utf-8"))
            self.assertEqual(german_data["chapters"][0]["headline"], "Erstes Licht")


class PruneTests(unittest.TestCase):
    """A regenerated story whose chapters were renamed keeps no old pictures.

    The files are named by chapter id, so the pictures of the chapters a new
    dataset replaced stayed in `public/chapter_art/` with nothing referring to
    them, and were committed with the regenerated story.
    """

    def _prune(self, referenced: List[str], files: List[str], datasets: bool = True):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            art = root / "chapter_art"
            person_dir = art / "ada_lovelace"
            person_dir.mkdir(parents=True)
            for name in files:
                (person_dir / name).write_bytes(b"webp")
            other_person = art / "alan_turing" / "old_full.webp"
            other_person.parent.mkdir()
            other_person.write_bytes(b"webp")

            base = "/chapter_art/ada_lovelace"
            chapters = [
                {
                    "id": chapter_id,
                    "illustration": {
                        "image": f"{base}/{chapter_id}_medium.webp",
                        "medium": f"{base}/{chapter_id}_medium.webp",
                        "full": f"{base}/{chapter_id}_full.webp",
                    },
                }
                for chapter_id in referenced
            ]
            english = root / "life_events.json"
            german = root / "de" / "life_events.json"
            german.parent.mkdir()
            for path in (english, german):
                path.write_text(json.dumps({"chapters": chapters}), encoding="utf-8")

            with (
                patch.object(chapter_art, "CHAPTER_ART_DIR", art),
                patch.object(
                    chapter_art,
                    "event_files",
                    return_value=[english, german] if datasets else [],
                ),
            ):
                removed = chapter_art.prune_orphaned_illustrations("ada_lovelace")

            self.assertTrue(other_person.exists(), "another person's file was removed")
            remaining = sorted(path.name for path in person_dir.iterdir())
        return removed, remaining

    def test_the_files_of_a_chapter_the_story_no_longer_has_are_removed(self) -> None:
        removed, remaining = self._prune(
            ["apple_rise"],
            [
                "apple_rise_full.webp",
                "apple_rise_medium.webp",
                "apple_takes_shape_full.webp",
                "apple_takes_shape_medium.webp",
            ],
        )
        self.assertEqual(
            removed, ["apple_takes_shape_full.webp", "apple_takes_shape_medium.webp"]
        )
        self.assertEqual(remaining, ["apple_rise_full.webp", "apple_rise_medium.webp"])

    def test_a_person_without_a_dataset_keeps_every_file(self) -> None:
        removed, remaining = self._prune([], ["first_full.webp"], datasets=False)
        self.assertEqual(removed, [])
        self.assertEqual(remaining, ["first_full.webp"])

    def test_a_run_that_writes_no_images_removes_none(self) -> None:
        with (
            patch.object(
                chapter_art,
                "_illustrate_chapters",
                side_effect=lambda *a, **k: {"success": True, "message": "done"},
            ),
            patch.object(
                chapter_art, "prune_orphaned_illustrations", return_value=[]
            ) as prune,
        ):
            chapter_art.generate_chapter_illustrations("ada_lovelace", dry_run=True)
            chapter_art.generate_chapter_illustrations("ada_lovelace", concepts_only=True)
            prune.assert_not_called()

            chapter_art.generate_chapter_illustrations("ada_lovelace")
            prune.assert_called_once_with("ada_lovelace")


if __name__ == "__main__":
    unittest.main()
