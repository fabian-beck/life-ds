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
            yield path


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


class PaletteChangeRedrawsTheImagesTests(unittest.TestCase):
    """An image is kept across a re-run, but never across a new palette.

    Both image steps keep what is already on disk, which is what makes a
    re-run cheap. The style step runs before them and may rewrite the two
    colors they are drawn in, and an image kept across that change is drawn in
    a palette no story uses — the state `utils/person_style.py` refuses to
    create from the other direction. The images are therefore redrawn exactly
    when the style step moved the palette under them.
    """

    def _drawing_run(self, new_colors, old_colors):
        forced = {}

        def portrait(*args, **kwargs):
            forced["portrait"] = kwargs.get("force")
            return {"success": True, "local_path": "portrait.png"}

        def chapter_art(*args, **kwargs):
            forced["chapter art"] = kwargs.get("force")
            return {
                "id": "ada_lovelace",
                "success": True,
                "generated": [],
                "message": "stubbed",
            }

        argv = ["Ada Lovelace", "--no-register", "--skip-review", "--skip-translate"]
        with _styles(ada_lovelace=old_colors) as styles_path:

            def restyle(*args, **kwargs):
                styles_path.write_text(
                    json.dumps({"styles": {"ada_lovelace": new_colors}}),
                    encoding="utf-8",
                )
                return {"id": "ada_lovelace", **new_colors}

            code = _run(
                argv,
                generate_style=restyle,
                generate_portrait=portrait,
                generate_chapter_illustrations=chapter_art,
            )
        self.assertEqual(code, 0)
        return forced

    def test_a_rewritten_palette_redraws_both_images(self) -> None:
        forced = self._drawing_run(
            new_colors={"primary": "#F2B84B", "secondary": "#63D6D1"},
            old_colors={"primary": "#00E5FF", "secondary": "#FFB000"},
        )
        self.assertEqual(forced, {"portrait": True, "chapter art": True})

    def test_an_unchanged_palette_keeps_the_images(self) -> None:
        colors = {"primary": "#00E5FF", "secondary": "#FFB000"}
        forced = self._drawing_run(new_colors=colors, old_colors=dict(colors))
        self.assertEqual(forced, {"portrait": False, "chapter art": False})


class PersonIdWithoutTheDatasetStepTests(unittest.TestCase):
    """A run that skips the dataset step still knows whose story it is.

    `--style-only` and `--network-only` skip step 1, which was the only place
    a run learned the person id, so every later step lost it: the portrait and
    the chapter art raised "No person ID resolved", and the background reports
    and the translation skipped themselves. The id is resolved from the
    existing data instead, which is what a run over an existing person has.
    """

    ARGV = [
        "Ada Lovelace",
        "--no-register",
        "--network-only",
        "--skip-review",
        "--skip-backgrounds",
        "--skip-translate",
    ]

    def _run_without_the_dataset_step(self, resolved):
        seen = {}

        def portrait(*args, **kwargs):
            seen["portrait"] = kwargs.get("person_id")
            return {"success": True, "local_path": "portrait.png"}

        def chapter_art(person_id=None, *args, **kwargs):
            seen["chapter art"] = person_id
            return {
                "id": person_id,
                "success": True,
                "generated": [],
                "message": "stubbed",
            }

        with _styles(ada_lovelace={"primary": "#FF8800", "secondary": "#1155AA"}):
            code = _run(
                self.ARGV,
                generate_portrait=portrait,
                generate_chapter_illustrations=chapter_art,
                resolve_person_id=lambda subject: resolved,
            )
        return code, seen

    def test_the_id_is_resolved_from_the_existing_data(self) -> None:
        code, seen = self._run_without_the_dataset_step("ada_lovelace")
        self.assertEqual(seen, {"portrait": "ada_lovelace", "chapter art": "ada_lovelace"})
        self.assertEqual(code, 0)

    def test_a_person_the_data_does_not_know_still_skips_cleanly(self) -> None:
        code, seen = self._run_without_the_dataset_step(None)
        self.assertEqual(seen, {}, "an image was drawn for nobody")
        self.assertEqual(code, 0, "skipping for an unknown person is not a failure")


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
