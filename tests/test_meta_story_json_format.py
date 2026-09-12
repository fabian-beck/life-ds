"""The meta-story data ships in the canonical writer's format.

Every meta-story script writes through ``utils/json_io.py``, and Prettier used
to check the files afterwards. The two disagree — Prettier sets a short array
on one line and the writer never does — so a composition, a translation, or an
event sync left the tree failing ``format:check`` until someone ran Prettier by
hand, and a session that did not notice pushed data the next run reformatted
back. The generated data is prettier-ignored now, like the person data beside
it, and this holds the files to the one format that remains.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from utils.json_io import read_json, write_json  # noqa: E402

DATA_DIR = REPO_ROOT / "data"


def meta_story_files() -> list[Path]:
    """Every committed meta-story data file, registries included."""
    files = sorted(DATA_DIR.glob("meta_stories*.json"))
    files.append(DATA_DIR / "meta_story_styles.json")
    files.extend(sorted((DATA_DIR / "meta_stories").rglob("*.json")))
    return [path for path in files if path.exists()]


class MetaStoryJsonFormatTests(unittest.TestCase):
    def test_every_file_is_written_the_way_the_scripts_write_it(self) -> None:
        for path in meta_story_files():
            with self.subTest(path=str(path.relative_to(REPO_ROOT))):
                written = self.canonical_text(read_json(path))
                self.assertEqual(written, path.read_bytes().decode("utf-8"))

    def canonical_text(self, data: object) -> str:
        """What ``write_json`` puts on disk for this content."""
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "canonical.json"
            write_json(path, data)
            return path.read_bytes().decode("utf-8")

    def test_the_files_are_ignored_by_prettier(self) -> None:
        """Whatever Prettier still checks, the writer would have to match."""
        ignored = (REPO_ROOT / ".prettierignore").read_text(encoding="utf-8")
        for pattern in (
            "data/meta_stories.json",
            "data/meta_stories_*.json",
            "data/meta_story_styles.json",
            "data/meta_stories/**/*.json",
        ):
            self.assertIn(pattern, ignored)


if __name__ == "__main__":
    unittest.main()
