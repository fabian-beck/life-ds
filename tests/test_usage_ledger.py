"""What a run reports it spent, per step.

The ledger is the only place the pipeline says which step consumed what, and
it is filled from provider responses whose usage payload is optional and
inconsistently named. The risks are therefore that a call is attributed to the
wrong step, that a missing payload raises instead of counting as zero, and
that a step which spent tokens without producing anything disappears from the
report. Each is checked here against stub responses; no network is involved.
"""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from utils import usage  # noqa: E402


def response(input_tokens=0, output_tokens=0, cached=0, reasoning=0):
    """A stand-in for a Responses API result, shaped like the real one."""
    return SimpleNamespace(
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            input_tokens_details=SimpleNamespace(cached_tokens=cached),
            output_tokens_details=SimpleNamespace(reasoning_tokens=reasoning),
        )
    )


class UsageLedgerTests(unittest.TestCase):
    def setUp(self):
        usage.reset()

    def test_calls_are_attributed_to_the_open_step(self):
        usage.begin_step("Life events")
        usage.record_response("model-a", response(100, 20))
        usage.begin_step("Ego network")
        usage.record_response("model-a", response(30, 5))

        rows = {row.step: row for row in usage.by_step()}
        self.assertEqual(rows["Life events"].input_tokens, 100)
        self.assertEqual(rows["Ego network"].output_tokens, 5)

    def test_a_call_outside_any_step_is_still_counted(self):
        usage.record_response("model-a", response(7, 3))
        rows = usage.by_step()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].step, usage.UNATTRIBUTED)
        self.assertEqual(rows[0].total_tokens, 10)

    def test_the_context_manager_restores_the_step_it_interrupted(self):
        usage.begin_step("Review")
        with usage.step("Background reports"):
            usage.record_response("model-a", response(1, 1))
        usage.record_response("model-a", response(2, 2))

        rows = {row.step: row.calls for row in usage.by_step()}
        self.assertEqual(rows, {"Background reports": 1, "Review": 1})

    def test_a_response_without_usage_counts_the_call_and_no_tokens(self):
        usage.begin_step("Portrait")
        usage.record_response("image-model", SimpleNamespace(data=[1]), images=1)

        row = usage.by_step()[0]
        self.assertEqual(row.calls, 1)
        self.assertEqual(row.total_tokens, 0)
        self.assertEqual(row.images, 1)

    def test_older_field_names_are_read(self):
        usage.record_response(
            "model-a",
            {"usage": {"prompt_tokens": 11, "completion_tokens": 4}},
        )
        row = usage.by_step()[0]
        self.assertEqual((row.input_tokens, row.output_tokens), (11, 4))

    def test_totals_add_the_steps_up(self):
        usage.begin_step("Life events")
        usage.record_response("model-a", response(100, 20, cached=40, reasoning=8))
        usage.begin_step("Translation")
        usage.record_response("model-b", response(50, 10, cached=5, reasoning=2))

        total = usage.totals()
        self.assertEqual(total.calls, 2)
        self.assertEqual(total.input_tokens, 150)
        self.assertEqual(total.output_tokens, 30)
        self.assertEqual(total.cached_input_tokens, 45)
        self.assertEqual(total.reasoning_tokens, 10)
        self.assertEqual(total.models, ["model-a", "model-b"])

    def test_the_report_names_every_step_that_spent_anything(self):
        usage.begin_step("Life events")
        usage.record_response("model-a", response(100, 20))
        usage.begin_step("Review")
        usage.record_response("model-a", response(0, 0))  # refused, but paid for

        report = usage.format_report()
        self.assertIn("Life events", report)
        self.assertIn("Review", report)
        self.assertIn("Total", report)

    def test_the_ledger_serializes_per_step_and_per_call(self):
        usage.begin_step("Life events")
        usage.record_response("model-a", response(100, 20), label="curation")

        data = usage.as_dict()
        self.assertEqual(data["steps"][0]["step"], "Life events")
        self.assertEqual(data["total"]["total_tokens"], 120)
        self.assertEqual(data["calls"][0]["label"], "curation")


if __name__ == "__main__":
    unittest.main()
