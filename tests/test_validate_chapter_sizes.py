"""Tests for the chapter-size checker.

The floor itself is one comparison; what the tests pin down is that the
checker reads the same number Phase 1 refuses on, that an empty chapter counts
as a finding rather than being skipped, and that the script reports by default
and gates only under ``--check``.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import validate_chapter_sizes as sizes  # noqa: E402
from events.pipeline import MIN_CHAPTER_EVENTS  # noqa: E402


def dataset(*chapter_ids: str, events: list[str]) -> dict:
    return {
        "chapters": [{"id": cid, "headline": cid} for cid in chapter_ids],
        "events": [{"date": "1900", "chapter": cid} for cid in events],
    }


class ChapterSizeTests(unittest.TestCase):
    def test_the_floor_is_the_one_phase_one_refuses_on(self) -> None:
        self.assertEqual(MIN_CHAPTER_EVENTS, 2)

    def test_chapters_at_the_floor_pass(self) -> None:
        data = dataset("a", "b", events=["a", "a", "b", "b", "b"])
        self.assertEqual(sizes.check_person("someone", data), [])

    def test_a_single_event_chapter_is_reported(self) -> None:
        data = dataset("a", "b", events=["a", "a", "b"])
        findings = [str(f) for f in sizes.check_person("someone", data)]
        self.assertEqual(
            findings,
            ["someone: chapter 'b' holds a single event, fewer than 2"],
        )

    def test_an_empty_chapter_is_reported(self) -> None:
        data = dataset("a", "b", events=["a", "a"])
        findings = [str(f) for f in sizes.check_person("someone", data)]
        self.assertEqual(findings, ["someone: chapter 'b' holds no event, fewer than 2"])

    def test_a_dataset_without_chapters_has_nothing_to_report(self) -> None:
        self.assertEqual(sizes.check_person("someone", {"events": [{}]}), [])

    def test_the_script_reports_by_default_and_gates_under_check(self) -> None:
        # phillis_wheatley ships with an empty chapter and alan_turing with a
        # single-event one (data/outdated.md); the corpus still carries the
        # finding, so the default run has to stay green.
        self.assertEqual(sizes.main(["alan_turing"]), 0)
        self.assertEqual(sizes.main(["alan_turing", "--check"]), 1)


if __name__ == "__main__":
    unittest.main()
