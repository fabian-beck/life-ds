"""A missing translation fails the parity check; a stale one only warns.

`--check` reports over every person and meta story. Gating it on staleness
made an unrelated change wait for a re-translation: regenerating one person
leaves that person's German copy describing English text that has moved, which
is readable prose and the expected state until `translate_person.py` catches
up. A missing document is the different case — a German reader gets nothing —
and that still fails.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import translate_all_persons  # noqa: E402

PERSONS = [{"id": "ada_lovelace"}, {"id": "frank_lloyd_wright"}]


def _counts(statuses):
    """Run the parity report over PERSONS with the given per-person statuses."""
    with (
        patch.object(
            translate_all_persons, "check_person_translation", side_effect=statuses
        ),
        patch.object(translate_all_persons, "list_meta_story_ids", return_value=[]),
    ):
        return translate_all_persons.run_check(PERSONS, "de", include_meta=False)


CURRENT = {"life_events": "current", "ego_network": "current", "registry": "current"}
STALE = {**CURRENT, "life_events": "stale", "ego_network": "stale"}
MISSING = {**CURRENT, "life_events": "missing"}


class ParityCheckTests(unittest.TestCase):
    def test_a_fully_current_corpus_counts_no_findings(self) -> None:
        counts = _counts([CURRENT, CURRENT])
        self.assertEqual(counts["stale"], 0)
        self.assertEqual(counts["missing"], 0)

    def test_staleness_is_counted_and_reported(self) -> None:
        counts = _counts([CURRENT, STALE])
        self.assertEqual(counts["stale"], 2)
        self.assertEqual(counts["missing"], 0)

    def test_a_missing_document_is_counted_apart_from_staleness(self) -> None:
        counts = _counts([MISSING, STALE])
        self.assertEqual(counts["missing"], 1)
        self.assertEqual(counts["stale"], 2)


class ExitCodeTests(unittest.TestCase):
    """The rule the CI step depends on: only `missing` fails the run."""

    def _exit_code(self, statuses):
        with (
            patch.object(
                sys,
                "argv",
                ["translate_all_persons.py", "--target-lang", "de", "--check"],
            ),
            patch.object(
                translate_all_persons, "load_person_list", return_value=PERSONS
            ),
            patch.object(
                translate_all_persons, "check_person_translation", side_effect=statuses
            ),
            patch.object(translate_all_persons, "list_meta_story_ids", return_value=[]),
        ):
            with self.assertRaises(SystemExit) as exit_call:
                translate_all_persons.main()
        return exit_call.exception.code

    def test_stale_alone_passes(self) -> None:
        self.assertEqual(self._exit_code([CURRENT, STALE]), 0)

    def test_missing_fails(self) -> None:
        self.assertEqual(self._exit_code([MISSING, CURRENT]), 1)

    def test_a_current_corpus_passes(self) -> None:
        self.assertEqual(self._exit_code([CURRENT, CURRENT]), 0)


if __name__ == "__main__":
    unittest.main()
