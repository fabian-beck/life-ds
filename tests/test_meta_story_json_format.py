"""The meta-story data is left to the writer that produces it.

Every meta-story script writes through ``utils/json_io.py``, and Prettier used
to check the files afterwards. The two disagree — Prettier sets a short array
on one line and the writer never does — so a composition, a translation, or an
event sync left the tree failing ``format:check`` until someone ran Prettier by
hand, and a session that did not notice pushed data the next run reformatted
back. The generated data is prettier-ignored now, like the person data beside
it, and this holds that arrangement in place.
"""

from __future__ import annotations

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


class MetaStoryJsonFormatTests(unittest.TestCase):
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
