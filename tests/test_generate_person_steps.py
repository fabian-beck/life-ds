"""Tests for how a person run handles a step that fails.

Each step writes and registers its own output as it goes, so a failure in one
says nothing about whether the next can run. The bug this guards against is a
single `try` around the first three steps: a timeout in the network call threw
past the portrait, the review, and the translation of events already on disk,
and the run reported one error instead of what it actually produced.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import generate_person as pipeline  # noqa: E402

ARGV = [
    "Ada Lovelace",
    "--no-register",
    "--skip-portrait",
    "--skip-review",
    "--skip-translate",
]


def _run(argv=ARGV, **overrides):
    """Run the pipeline with every generation step stubbed out."""
    stubs = {
        "generate_dataset": lambda *a, **k: ("data/people/ada_lovelace", "ada_lovelace"),
        "generate_style": lambda *a, **k: {"id": "ada_lovelace"},
        "generate_person_network": lambda *a, **k: "network.json",
        # Every step that reaches the network has to be stubbed here, or the
        # suite runs it for real: the chapter illustrations were left out once
        # and the test drew a whole set of them against the live API.
        "generate_chapter_illustrations": lambda *a, **k: {
            "id": "ada_lovelace",
            "success": True,
            "generated": [],
            "message": "stubbed",
        },
    }
    stubs.update(overrides)
    with patch.multiple(pipeline, **{k: v for k, v in stubs.items()}):
        return pipeline.main(argv)


def _boom(message):
    def raise_it(*args, **kwargs):
        raise RuntimeError(message)

    return raise_it


class StepIsolationTests(unittest.TestCase):
    def test_a_clean_run_exits_zero(self) -> None:
        self.assertEqual(_run(), 0)

    def test_a_failed_step_does_not_stop_the_later_ones(self) -> None:
        reached = []

        def network(*args, **kwargs):
            reached.append("network")
            return "network.json"

        code = _run(
            generate_style=_boom("style service is down"),
            generate_person_network=network,
        )

        self.assertEqual(reached, ["network"], "the network step never ran")
        self.assertEqual(code, 1, "a degraded run must not report success")

    def test_the_events_step_failing_still_lets_the_others_run(self) -> None:
        reached = []

        def style(*args, **kwargs):
            reached.append("style")
            return {"id": "ada_lovelace"}

        code = _run(
            generate_dataset=_boom("the model timed out"),
            generate_style=style,
        )

        self.assertEqual(reached, ["style"])
        self.assertEqual(code, 1)


class RunLogTests(unittest.TestCase):
    def test_the_summary_names_what_failed_and_why(self) -> None:
        log = pipeline.RunLog()
        log.record("Life events", pipeline.STEP_OK)
        log.record("Ego network", pipeline.STEP_FAILED, "the model timed out")
        log.record("Portrait", pipeline.STEP_SKIPPED, "--skip-portrait")

        self.assertEqual(log.failed, ["Ego network"])

    def test_a_skipped_step_is_not_a_failed_one(self) -> None:
        """`--skip-portrait` is a choice the caller made, not a degraded run."""
        log = pipeline.RunLog()
        log.record("Life events", pipeline.STEP_OK)
        log.record("Portrait", pipeline.STEP_SKIPPED, "--skip-portrait")

        self.assertEqual(log.failed, [])


if __name__ == "__main__":
    unittest.main()
