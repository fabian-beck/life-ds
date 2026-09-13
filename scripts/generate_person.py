#!/usr/bin/env python3
"""Generate a person's story by running the steps of the person pipeline."""

import argparse
import json
import sys
from typing import Any, Dict, List, Optional, Tuple

# Import the individual generation functions
from config import DEFAULT_MODEL as DATASET_MODEL
from events.pipeline import generate_person_events as generate_dataset
from generate_person_style import generate_style, BULK_MODEL as STYLE_MODEL
from generate_person_network import (
    generate_person_network,
    DEFAULT_MODEL as NETWORK_MODEL,
)
from generate_person_portrait import (
    DEFAULT_PORTRAIT_MODEL,
    extract_image_from_page,
    generate_portrait,
    is_direct_image_url,
)
from generate_chapter_illustrations import (
    DEFAULT_IMAGE_MODEL as CHAPTER_ART_MODEL,
    generate_chapter_illustrations,
)
from generate_event_backgrounds import generate_event_backgrounds
from review_person import resolve_person_id, review_person_data
from utils import usage
from utils.text import slugify
from utils.person_style import MissingStyleError, has_style, story_colors

STEP_OK = "ok"
STEP_FAILED = "failed"
STEP_SKIPPED = "skipped"

_MARK = {STEP_OK: "✓", STEP_FAILED: "✗", STEP_SKIPPED: "⊘"}


class RunLog:
    """What each step of a run did.

    A person's data is written step by step and registered as it goes, so one
    step failing says nothing about whether the next can run — a network call
    that times out should not cost the portrait, the review, and the
    translation of events already on disk. Each step reports here instead of
    raising through the others, and the run ends by saying what it got and
    exiting non-zero if anything is missing, so a rerun can fill in the gaps.
    """

    def __init__(self) -> None:
        self.steps: List[Tuple[str, str, str]] = []

    def record(self, name: str, status: str, detail: str = "") -> None:
        self.steps.append((name, status, detail))

    @property
    def failed(self) -> List[str]:
        return [name for name, status, _ in self.steps if status == STEP_FAILED]

    def report(self, subject: str) -> None:
        print("\n" + "=" * 60)
        print("GENERATION COMPLETE" if not self.failed else "GENERATION DEGRADED")
        print("=" * 60)
        for name, status, detail in self.steps:
            suffix = f" — {detail}" if detail else ""
            print(f"{_MARK[status]} {name}{suffix}")
        produced = sum(1 for _, status, _ in self.steps if status == STEP_OK)
        attempted = sum(1 for _, status, _ in self.steps if status != STEP_SKIPPED)
        print(f"\nGenerated {produced} of {attempted} components for '{subject}'")
        if self.failed:
            print(
                "Rerun to fill in what is missing; the steps that succeeded are "
                "already written and will not be redone from scratch."
            )


# The steps of a run in the order they run: the name that `--skip-<name>` and
# `--only` use, the label the run log prints, and what the step writes. Each
# step reads what the earlier ones left on disk, so a step skipped here keeps
# its existing data for the steps after it.
STEPS: Tuple[Tuple[str, str, str], ...] = (
    ("events", "Life events", "the life events, with their images and places"),
    ("style", "Interface style", "the interface style"),
    ("network", "Ego network", "the ego network"),
    ("portrait", "Portrait", "the stylized portrait"),
    ("chapter-art", "Chapter illustrations", "the illustrations of the chapters"),
    ("review", "Review", "the review of the life events and the ego network"),
    ("backgrounds", "Background reports", "the depth-layer background reports"),
    ("translate", "Translation", "the translation into --translate-langs"),
)
STEP_NAMES = [name for name, _, _ in STEPS]
STEP_LABELS = {name: label for name, label, _ in STEPS}


def _step_list(value: str) -> List[str]:
    """Parse a comma-separated list of step names."""
    names = [name.strip() for name in value.split(",") if name.strip()]
    unknown = [name for name in names if name not in STEP_NAMES]
    if unknown or not names:
        raise argparse.ArgumentTypeError(
            f"unknown step {', '.join(unknown) or repr(value)}; "
            f"steps are {', '.join(STEP_NAMES)}"
        )
    return names


def skip_reasons(args: argparse.Namespace) -> Dict[str, Optional[str]]:
    """The flag that skips each step, or None for a step the run performs."""
    reasons: Dict[str, Optional[str]] = {}
    for name in STEP_NAMES:
        if getattr(args, "skip_" + name.replace("-", "_")):
            reasons[name] = f"--skip-{name}"
        elif args.only is not None and name not in args.only:
            reasons[name] = f"--only {','.join(args.only)}"
        else:
            reasons[name] = None
    return reasons


def parse_args(argv: Any) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Generate a person's story by running every step of the person "
            "pipeline, or the steps --only and the --skip flags leave."
        )
    )
    parser.add_argument(
        "subject", help="Person to research, e.g. 'Ada Lovelace' or 'henry_II'."
    )
    parser.add_argument(
        "--url",
        help="Wikipedia URL to use for disambiguation (e.g., 'https://en.wikipedia.org/wiki/Henry_II,_Holy_Roman_Emperor').",
    )
    parser.add_argument(
        "--no-register", action="store_true", help="Skip updating the persons register."
    )
    parser.add_argument(
        "--model",
        help=(
            "OpenAI model to use for all generation steps (overrides defaults). "
            "Must support structured outputs."
        ),
    )
    parser.add_argument(
        "--only",
        type=_step_list,
        metavar="STEP[,STEP...]",
        help=f"Run only the steps named ({', '.join(STEP_NAMES)}).",
    )
    for name, _, what in STEPS:
        parser.add_argument(f"--skip-{name}", action="store_true", help=f"Skip {what}.")
    parser.add_argument(
        "--portrait-model",
        default=DEFAULT_PORTRAIT_MODEL,
        help=f"OpenAI model for portrait generation (default: {DEFAULT_PORTRAIT_MODEL}).",
    )
    parser.add_argument(
        "--portrait-url",
        help=(
            "Licensed portrait image or landing-page URL. Page URLs are resolved "
            "to an image before style transfer."
        ),
    )
    parser.add_argument(
        "--portrait-source-page",
        help="Landing page used for portrait attribution (recommended with a direct image URL).",
    )
    parser.add_argument(
        "--portrait-license",
        help="License of the source portrait, e.g. 'CC BY-SA 4.0'.",
    )
    parser.add_argument(
        "--portrait-source-creator",
        help="Creator or credited source of the reference portrait.",
    )
    parser.add_argument(
        "--chapter-art-model",
        default=CHAPTER_ART_MODEL,
        help=f"OpenAI model for the chapter illustrations (default: {CHAPTER_ART_MODEL}).",
    )
    parser.add_argument(
        "--usage-json",
        help=(
            "Write the per-step token ledger to this path as JSON, in "
            "addition to printing it."
        ),
    )
    parser.add_argument(
        "--translate-langs",
        default="de",
        help="Comma-separated language codes to translate to after generation (default: de).",
    )
    return parser.parse_args(argv)


def main(argv: Any = None) -> int:
    """Main entry point."""
    args = parse_args(argv)
    update_registry = not args.no_register

    # When URL is provided, use it for fetching but preserve original subject as person_id
    if args.url:
        subject_for_fetch = args.url
        person_id_override = slugify(args.subject)
    else:
        subject_for_fetch = args.subject
        person_id_override = None

    # Determine which models to use
    dataset_model = args.model or DATASET_MODEL
    style_model = args.model or STYLE_MODEL
    network_model = args.model or NETWORK_MODEL

    skipped = skip_reasons(args)
    run_log = RunLog()

    def skip(step: str) -> None:
        reason = skipped[step] or ""
        print(f"\n⊘ Skipping {STEP_LABELS[step].lower()} ({reason})")
        run_log.record(STEP_LABELS[step], STEP_SKIPPED, reason)

    def banner(text: str) -> None:
        print("\n" + "=" * 60)
        print(text)
        print("=" * 60 + "\n")

    # Determine person_id from dataset generation or by loading existing data
    person_id = person_id_override

    # Step 1: Generate life events dataset
    usage.begin_step("Life events")
    if not skipped["events"]:
        banner("STEP 1/8: Generating life events dataset")
        try:
            dataset_path, person_id = generate_dataset(
                subject_for_fetch,
                person_id=person_id_override,
                update_registry=update_registry,
                model=dataset_model,
            )
            print(f"\n✓ Life events dataset written to {dataset_path}")
            run_log.record("Life events", STEP_OK)
        except Exception as error:
            print(f"\n✗ Life events dataset generation failed: {error}")
            run_log.record("Life events", STEP_FAILED, str(error))
    else:
        skip("events")

    # Every step after the dataset one is filed under a person id, and step 1
    # is where a run normally learns it. Under --skip-events that step does
    # not run at all, and a run whose dataset step failed has no
    # id either, so the id is resolved from the data already on disk: the
    # registry and data/people/ both answer to a name or an id. A person
    # neither knows is genuinely new, and the steps below skip themselves as
    # they already do.
    if person_id is None:
        person_id = resolve_person_id(args.subject)
        if person_id:
            print(f"\n→ Resolved existing person '{person_id}' from {args.subject!r}")

    # The colors the shipped images were drawn in, read before the style step
    # may rewrite them.
    def current_colors() -> Optional[Dict[str, str]]:
        if not person_id:
            return None
        try:
            return story_colors(person_id)
        except MissingStyleError:
            return None

    colors_before_style = current_colors()

    # Step 2: Generate interface style
    usage.begin_step("Interface style")
    if not skipped["style"]:
        banner("STEP 2/8: Generating interface style")
        try:
            style_result = generate_style(
                subject_for_fetch,
                person_id=person_id,
                model=style_model,
            )
            print(f"\n✓ Interface style generated for '{style_result.get('id')}'")
            run_log.record("Interface style", STEP_OK)
        except Exception as error:
            print(f"\n✗ Interface style generation failed: {error}")
            run_log.record("Interface style", STEP_FAILED, str(error))
    else:
        skip("style")

    # The two image steps are drawn in the story's primary and secondary color,
    # so they are downstream of the style rather than beside it. A person whose
    # style step failed — or was skipped for a person who never had one — has
    # no palette to draw in, and an image drawn in a default one would be cached
    # under the person's name and never redrawn. The check reads what is on
    # disk, so a style written by an earlier run still counts.
    style_missing = person_id is not None and not has_style(person_id)
    no_style_reason = (
        "no interface style — run scripts/generate_person_style.py, then rerun"
    )

    # Both images are filed under a person id. Without one there is no dataset
    # to draw from either, so this is a step that cannot run rather than one
    # that failed, and it is reported the way the missing style is.
    no_id_reason = (
        f"no person ID — the dataset step did not run and no existing person "
        f"matches {args.subject!r}; pass --url to file the run under an ID"
    )

    # A portrait and a chapter illustration are kept when they already exist,
    # which is what makes a re-run cheap. The style step runs before them and
    # may have just rewritten the two colors they are drawn in, and an image
    # kept across that change is drawn in a palette no story uses — the state
    # utils/person_style.py refuses to create from the other direction. So the
    # images are redrawn exactly when the palette moved under them.
    colors_after_style = current_colors()
    palette_changed = False
    if (
        colors_before_style is not None
        and colors_after_style is not None
        and colors_after_style != colors_before_style
    ):
        palette_changed = True
        print(
            f"\n↻ Palette changed ({colors_before_style['primary']}/"
            f"{colors_before_style['secondary']} → {colors_after_style['primary']}/"
            f"{colors_after_style['secondary']}); redrawing the portrait and the "
            "chapter illustrations in the new colors"
        )

    # Step 3: Generate ego network
    usage.begin_step("Ego network")
    if not skipped["network"]:
        banner("STEP 3/8: Generating ego network")
        try:
            network_path = generate_person_network(
                subject_for_fetch,
                person_id=person_id,
                update_registry=update_registry,
                model=network_model,
            )
            print(f"\n✓ Ego network written to {network_path}")
            run_log.record("Ego network", STEP_OK)
        except Exception as error:
            print(f"\n✗ Ego network generation failed: {error}")
            run_log.record("Ego network", STEP_FAILED, str(error))
    else:
        skip("network")

    # Step 4: Generate portrait (if not skipped)
    usage.begin_step("Portrait")
    if skipped["portrait"]:
        skip("portrait")
    elif style_missing:
        print(f"\n⊘ Skipping portrait generation ({no_style_reason})")
        run_log.record("Portrait", STEP_SKIPPED, no_style_reason)
    elif not person_id:
        print(f"\n⊘ Skipping portrait generation ({no_id_reason})")
        run_log.record("Portrait", STEP_SKIPPED, no_id_reason)
    else:
        banner("STEP 4/8: Generating stylized portrait")
        try:
            from pathlib import Path

            portrait_reference_url = args.portrait_url
            portrait_source_page = args.portrait_source_page
            if portrait_reference_url and not is_direct_image_url(
                portrait_reference_url
            ):
                page_url = portrait_reference_url
                portrait_reference_url, extracted_page = extract_image_from_page(
                    page_url
                )
                if not portrait_reference_url:
                    raise ValueError(
                        f"Could not resolve a portrait image from {page_url}"
                    )
                portrait_source_page = portrait_source_page or extracted_page

            portrait_result = generate_portrait(
                person_id=person_id,
                reference_image_url=portrait_reference_url,
                source_page_url=portrait_source_page,
                source_license=args.portrait_license,
                source_creator=args.portrait_source_creator,
                master_style_path=Path(__file__).resolve().parents[1]
                / "public"
                / "master_style_portrait.png",
                model=args.portrait_model,
                dry_run=False,
                force=palette_changed,
            )
            if portrait_result["success"]:
                if portrait_result.get("cached"):
                    print(f"\n⊘ {portrait_result['message']}")
                else:
                    print(
                        f"\n✓ Portrait generated: {portrait_result.get('local_path')}"
                    )
                run_log.record("Portrait", STEP_OK)
            else:
                print(f"\n✗ Portrait generation failed: {portrait_result['message']}")
                run_log.record("Portrait", STEP_FAILED, portrait_result["message"])
        except Exception as error:
            print(f"\n✗ Portrait generation failed: {error}")
            run_log.record("Portrait", STEP_FAILED, str(error))

    # Step 5: Chapter illustrations (if not skipped). After the style, whose
    # colors they are drawn in, and after the dataset, whose chapters they
    # illustrate — a person with neither simply has nothing to draw.
    usage.begin_step("Chapter illustrations")
    if skipped["chapter-art"]:
        skip("chapter-art")
    elif style_missing:
        print(f"\n⊘ Skipping chapter illustrations ({no_style_reason})")
        run_log.record("Chapter illustrations", STEP_SKIPPED, no_style_reason)
    elif not person_id:
        print(f"\n⊘ Skipping chapter illustrations ({no_id_reason})")
        run_log.record("Chapter illustrations", STEP_SKIPPED, no_id_reason)
    else:
        banner("STEP 5/8: Generating chapter illustrations")
        try:
            art_result = generate_chapter_illustrations(
                person_id,
                model=args.chapter_art_model,
                concept_model=args.model or DATASET_MODEL,
                force=palette_changed,
            )
            if art_result["success"]:
                print(f"\n✓ {art_result['message']}")
                run_log.record("Chapter illustrations", STEP_OK)
            else:
                print(f"\n✗ Chapter illustrations failed: {art_result['message']}")
                run_log.record(
                    "Chapter illustrations", STEP_FAILED, art_result["message"]
                )
        except Exception as error:
            print(f"\n✗ Chapter illustrations failed: {error}")
            run_log.record("Chapter illustrations", STEP_FAILED, str(error))

    # Step 6: Review (if not skipped)
    usage.begin_step("Review")
    if not skipped["review"]:
        print("\n" + "=" * 60)
        print("STEP 6/8: REVIEWING GENERATED DATA")
        print("=" * 60)
        print("Running quality review and polish...")
        print("(Only high-confidence changes will be applied)")

        try:
            review_success = review_person_data(
                person_id or args.subject,
                min_confidence=4,  # Auto-mode: only high-confidence
                verbose=False,
            )
            if review_success:
                print("\n✓ Review complete")
                run_log.record("Review", STEP_OK)
            else:
                print("\n✗ Review encountered issues (data still usable)")
                run_log.record("Review", STEP_FAILED, "review reported failure")
        except Exception as error:
            print(f"\n✗ Review failed: {error}")
            print("  Generated data is still usable, but not reviewed.")
            run_log.record("Review", STEP_FAILED, str(error))
    else:
        skip("review")

    # Step 7: Depth-layer background reports. After review, so the reports
    # build on the reviewed English text and its annotations; before
    # translation, so the translator sees them. The step computes the story's
    # own deep-event selection and writes a report only where the story will
    # offer one.
    usage.begin_step("Background reports")
    if skipped["backgrounds"]:
        skip("backgrounds")
    elif not person_id:
        print("\n⊘ Skipping background reports (no person_id resolved)")
        run_log.record("Background reports", STEP_SKIPPED, "no person ID resolved")
    else:
        banner("STEP 7/8: Writing depth-layer background reports")
        try:
            written = generate_event_backgrounds(person_id)
            print(f"\n✓ Wrote {written} background report(s)")
            run_log.record("Background reports", STEP_OK)
        except Exception as error:
            print(f"\n✗ Background reports failed: {error}")
            run_log.record("Background reports", STEP_FAILED, str(error))

    # Step 8: Translate (if not skipped). Runs last so translations are
    # derived from the final (reviewed) English data. The English reference is
    # complete either way, and `translate_all_persons.py --check` reports the
    # gap, but a failure still counts against the run.
    usage.begin_step("Translation")
    translate_langs = [
        code.strip() for code in args.translate_langs.split(",") if code.strip()
    ]
    if skipped["translate"]:
        skip("translate")
    elif not translate_langs:
        print("\n⊘ Skipping translation (no --translate-langs)")
        run_log.record("Translation", STEP_SKIPPED, "no --translate-langs")
    elif not person_id:
        print("\n⊘ Skipping translation step (no person_id resolved)")
        run_log.record("Translation", STEP_SKIPPED, "no person ID resolved")
    else:
        banner("STEP 8/8: Translating generated data")
        try:
            import os

            from openai import OpenAI
            from translate_person import TRANSLATION_MODEL, translate_person_data

            translate_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            incomplete = []
            for lang in translate_langs:
                print(f"Translating '{person_id}' to '{lang}'...")
                results = translate_person_data(
                    person_id=person_id,
                    target_lang=lang,
                    client=translate_client,
                    # The translator's own tier, not the dataset model. A
                    # payload whose structure the merge enforces is the small
                    # model's case exactly, and `translate_person.py` says so
                    # in TRANSLATION_MODEL; passing DATASET_MODEL here
                    # overrode that silently and ran the documents on the
                    # reasoning tier. The glossary is unaffected — it takes
                    # GLOSSARY_MODEL explicitly, whatever this argument says.
                    model=args.model or TRANSLATION_MODEL,
                    force=True,
                )
                if all(results.values()):
                    print(f"✓ Translation to '{lang}' complete")
                else:
                    translated = [key for key, ok in results.items() if ok]
                    print(
                        f"✗ Translation to '{lang}' incomplete "
                        f"(translated: {', '.join(translated) or 'nothing'})"
                    )
                    incomplete.append(lang)
            if incomplete:
                run_log.record(
                    "Translation",
                    STEP_FAILED,
                    f"incomplete for {', '.join(incomplete)}",
                )
            else:
                run_log.record("Translation", STEP_OK)
        except Exception as error:
            print(f"\n✗ Translation failed: {error}")
            print(
                "  English data is complete; run scripts/translate_person.py "
                "manually to retry."
            )
            run_log.record("Translation", STEP_FAILED, str(error))

    run_log.report(args.subject)
    usage.print_report()
    if args.usage_json:
        from pathlib import Path as UsagePath

        ledger_path = UsagePath(args.usage_json)
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        ledger_path.write_text(
            json.dumps(usage.as_dict(), indent=2) + "\n", encoding="utf-8"
        )
        print(f"Usage ledger written to {ledger_path}")
    if not update_registry:
        print("⊘ Register update skipped by request")

    return 1 if run_log.failed else 0


if __name__ == "__main__":
    sys.exit(main())
