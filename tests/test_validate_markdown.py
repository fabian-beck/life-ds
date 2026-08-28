"""Tests for the stray-Markdown checker.

The shapes it exists for shipped: ``*Childe Harold's Pilgrimage*`` in a
background report, ``**Maria Zuse**`` in a network summary, and a translator
adding ``*Philosophical Magazine*`` where the English was plain. The risky
part is the other direction — the ``## `` headings a background report is
allowed, ``[[term|display]]`` annotation markers, and underscore-riddled
Commons file names must all pass.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from validate_markdown import markdown_findings  # noqa: E402


class MarkdownFindingTests(unittest.TestCase):
    def test_emphasis_around_a_work_title_is_found(self) -> None:
        findings = markdown_findings(
            "celebrated poets after *Childe Harold's Pilgrimage*, but", "background"
        )
        self.assertEqual(len(findings), 1)
        self.assertIn("asterisk", findings[0])

    def test_bold_names_are_found(self) -> None:
        findings = markdown_findings(
            "his earliest breakthroughs: **Maria Zuse** provided support", "summary"
        )
        self.assertEqual(len(findings), 1)
        self.assertIn("asterisk", findings[0])

    def test_a_backtick_is_found(self) -> None:
        findings = markdown_findings("the `Z3` was rebuilt", "description")
        self.assertEqual(len(findings), 1)
        self.assertIn("backtick", findings[0])

    def test_a_markdown_link_is_found(self) -> None:
        findings = markdown_findings(
            "see [the paper](https://example.org/paper)", "description"
        )
        self.assertIn("Markdown link", " ".join(findings))

    def test_double_underscore_emphasis_is_found(self) -> None:
        findings = markdown_findings("her __Notes__ appeared in 1843", "description")
        self.assertEqual(len(findings), 1)
        self.assertIn("double-underscore", findings[0])

    def test_a_heading_in_a_background_report_passes(self) -> None:
        self.assertEqual(
            markdown_findings(
                "The first paragraph.\n\n## The bombe on the floor\n\nMore prose.",
                "background",
            ),
            [],
        )

    def test_a_heading_anywhere_else_is_found(self) -> None:
        findings = markdown_findings("## Early years\n\nBorn in London.", "description")
        self.assertEqual(len(findings), 1)
        self.assertIn("heading outside a background report", findings[0])

    def test_annotation_markers_pass(self) -> None:
        self.assertEqual(
            markdown_findings(
                "wrote about the [[Analytical Engine|engine]] at length",
                "description",
            ),
            [],
        )

    def test_commons_file_names_pass(self) -> None:
        self.assertEqual(
            markdown_findings(
                "https://upload.wikimedia.org/wikipedia/commons/7/70/"
                "Wolfsschanze_-_panoramio.jpg/960px-Wolfsschanze_-_panoramio.jpg",
                "url",
            ),
            [],
        )

    def test_plain_prose_passes(self) -> None:
        self.assertEqual(
            markdown_findings(
                "After Childe Harold's Pilgrimage, Byron was famous.", "background"
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
