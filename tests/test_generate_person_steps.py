"""Tests for how a person run handles a step that fails.

Each step writes and registers its own output as it goes, so a failure in one
says nothing about whether the next can run. The bug this guards against is a
single `try` around the first three steps: a timeout in the network call threw
past the portrait, the review, and the translation of events already on disk,
and the run reported one error instead of what it actually produced.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import generate_person as pipeline  # noqa: E402
from utils import person_style  # noqa: E402

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


@contextmanager
def _styles(**styles):
    """Run with `person_styles.json` holding exactly the styles given."""
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "person_styles.json"
        path.write_text(json.dumps({"styles": styles}), encoding="utf-8")
        with patch.object(person_style, "STYLES_PATH", path):
            yield


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


class StyleGatesTheImagesTests(unittest.TestCase):
    """The portrait and the chapter art are drawn in the story's own colors.

    Both steps read `person_styles.json` for the primary and secondary color
    their prompts name, so a run whose style step produced nothing has no
    palette to draw in. It skips them instead: an image drawn in a default
    palette is cached under the person's name, and the next run finds it there
    and leaves it alone.
    """

    def test_the_image_steps_are_skipped_when_the_person_has_no_style(self) -> None:
        drawn = []

        def portrait(*args, **kwargs):
            drawn.append("portrait")
            return {"success": True, "local_path": "portrait.png"}

        def chapter_art(*args, **kwargs):
            drawn.append("chapter art")
            return {"id": "nobody", "success": True, "generated": [], "message": ""}

        argv = ["Nobody Yet", "--no-register", "--skip-review", "--skip-translate"]
        with _styles():
            code = _run(
                argv,
                generate_dataset=lambda *a, **k: (
                    "data/people/nobody_yet",
                    "nobody_yet",
                ),
                generate_style=_boom("style service is down"),
                generate_portrait=portrait,
                generate_chapter_illustrations=chapter_art,
            )

        self.assertEqual(drawn, [], "an image was drawn without a style to draw in")
        self.assertEqual(code, 1, "the failed style step must still be reported")

    def test_a_person_who_has_a_style_still_gets_their_images(self) -> None:
        drawn = []

        def portrait(*args, **kwargs):
            drawn.append("portrait")
            return {"success": True, "local_path": "portrait.png"}

        def chapter_art(*args, **kwargs):
            drawn.append("chapter art")
            return {
                "id": "ada_lovelace",
                "success": True,
                "generated": [],
                "message": "stubbed",
            }

        argv = ["Ada Lovelace", "--no-register", "--skip-review", "--skip-translate"]
        with _styles(ada_lovelace={"primary": "#FF8800", "secondary": "#1155AA"}):
            code = _run(
                argv,
                generate_portrait=portrait,
                generate_chapter_illustrations=chapter_art,
            )

        self.assertEqual(drawn, ["portrait", "chapter art"])
        self.assertEqual(code, 0)


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
