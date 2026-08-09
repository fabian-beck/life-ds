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


if __name__ == "__main__":
    unittest.main()
