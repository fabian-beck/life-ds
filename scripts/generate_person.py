#!/usr/bin/env python3
"""Generate complete person dataset by running all three generation scripts."""

import argparse
import json
import sys
from typing import Any, List, Tuple

# Import the individual generation functions
from generate_person_events import (
    generate_person_events as generate_dataset,
    DEFAULT_MODEL as DATASET_MODEL,
)
from generate_person_style import generate_style, BULK_MODEL as STYLE_MODEL
from generate_person_network import (
    generate_person_network,
    DEFAULT_MODEL as NETWORK_MODEL,
)
from generate_person_portrait import (
    extract_image_from_page,
    generate_portrait,
    is_direct_image_url,
)
from generate_chapter_illustrations import generate_chapter_illustrations
from generate_event_backgrounds import generate_event_backgrounds
from review_person import review_person_data
from utils import usage

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


def parse_args(argv: Any) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate complete person dataset (life events, interface style, and ego network)."
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
        "--dataset-only",
        action="store_true",
        help="Generate only life events dataset (skip interface style and network).",
    )
    parser.add_argument(
        "--style-only",
        action="store_true",
        help="Generate only interface style (skip dataset and network).",
    )
    parser.add_argument(
        "--network-only",
        action="store_true",
        help="Generate only ego network (skip dataset and interface style).",
    )
    parser.add_argument(
        "--skip-review",
        action="store_true",
        help="Skip the automatic review step after generation.",
    )
    parser.add_argument(
        "--skip-portrait",
        action="store_true",
        help="Skip portrait generation (stylized artwork from reference image).",
    )
    parser.add_argument(
        "--portrait-model",
        default="gpt-image-2",
        help="OpenAI model for portrait generation (default: gpt-image-2).",
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
        "--skip-chapter-art",
        action="store_true",
        help="Skip the abstract illustrations for the chapter slides.",
    )
    parser.add_argument(
        "--chapter-art-model",
        default="gpt-image-2",
        help="OpenAI model for the chapter illustrations (default: gpt-image-2).",
    )
    parser.add_argument(
        "--skip-db",
        action="store_true",
        help="Skip fetching Deutsche Biographie data as additional source.",
    )
    parser.add_argument(
        "--skip-backgrounds",
        action="store_true",
        help="Skip writing the depth-layer background reports.",
    )
    parser.add_argument(
        "--skip-translate",
        action="store_true",
        help="Skip automatic translation after generation.",
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
        from generate_person_events import slugify

        person_id_override = slugify(args.subject)
    else:
        subject_for_fetch = args.subject
        person_id_override = None

    # Determine which models to use
    dataset_model = args.model or DATASET_MODEL
    style_model = args.model or STYLE_MODEL
    network_model = args.model or NETWORK_MODEL

    # Determine which steps to run
    run_dataset = not (args.style_only or args.network_only)
    run_style = not (args.dataset_only or args.network_only)
    run_network = not (args.dataset_only or args.style_only)

    run_log = RunLog()

    def banner(text: str) -> None:
        print("\n" + "=" * 60)
        print(text)
        print("=" * 60 + "\n")

    # Determine person_id from dataset generation or by loading existing data
    person_id = person_id_override

    # Step 1: Generate life events dataset
    usage.begin_step("Life events")
    if run_dataset:
        banner("STEP 1/8: Generating life events dataset")
        try:
            dataset_path, person_id = generate_dataset(
                subject_for_fetch,
                person_id=person_id_override,
                update_registry=update_registry,
                model=dataset_model,
                use_deutsche_biographie=not args.skip_db,
            )
            print(f"\n✓ Life events dataset written to {dataset_path}")
            run_log.record("Life events", STEP_OK)
        except Exception as error:
            print(f"\n✗ Life events dataset generation failed: {error}")
            run_log.record("Life events", STEP_FAILED, str(error))
    else:
        print("\n⊘ Skipping life events dataset generation")
        run_log.record("Life events", STEP_SKIPPED, "not requested")

    # Step 2: Generate interface style
    usage.begin_step("Interface style")
    if run_style:
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
        print("\n⊘ Skipping interface style generation")
        run_log.record("Interface style", STEP_SKIPPED, "not requested")

    # Step 3: Generate ego network
    usage.begin_step("Ego network")
    if run_network:
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
        print("\n⊘ Skipping ego network generation")
        run_log.record("Ego network", STEP_SKIPPED, "not requested")

    # Step 4: Generate portrait (if not skipped)
    usage.begin_step("Portrait")
    if not args.skip_portrait:
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

            if not person_id:
                raise ValueError(
                    "No person ID resolved — run the dataset step or pass "
                    "--url so the portrait can be filed under a person ID"
                )

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
                force=False,
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
    else:
        print("\n⊘ Skipping portrait generation (--skip-portrait flag)")
        run_log.record("Portrait", STEP_SKIPPED, "--skip-portrait")

    # Step 5: Chapter illustrations (if not skipped). After the style, whose
    # colors they are drawn in, and after the dataset, whose chapters they
    # illustrate — a person with neither simply has nothing to draw.
    usage.begin_step("Chapter illustrations")
    if not args.skip_chapter_art:
        banner("STEP 5/8: Generating chapter illustrations")
        try:
            if not person_id:
                raise ValueError(
                    "No person ID resolved — run the dataset step or pass "
                    "--url so the illustrations can be filed under a person ID"
                )
            art_result = generate_chapter_illustrations(
                person_id,
                model=args.chapter_art_model,
                concept_model=args.model or DATASET_MODEL,
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
    else:
        print("\n⊘ Skipping chapter illustrations (--skip-chapter-art flag)")
        run_log.record("Chapter illustrations", STEP_SKIPPED, "--skip-chapter-art")

    # Step 6: Review (if not skipped)
    usage.begin_step("Review")
    if not args.skip_review:
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
        print("\n⊘ Skipping review step (--skip-review flag)")
        run_log.record("Review", STEP_SKIPPED, "--skip-review")

    # Step 7: Depth-layer background reports. After review, so the reports
    # build on the reviewed English text and its annotations; before
    # translation, so the translator sees them. The step computes the story's
    # own deep-event selection and writes a report only where the story will
    # offer one.
    usage.begin_step("Background reports")
    if args.skip_backgrounds:
        print("\n⊘ Skipping background reports (--skip-backgrounds flag)")
        run_log.record("Background reports", STEP_SKIPPED, "--skip-backgrounds")
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
    if args.skip_translate or not translate_langs:
        print("\n⊘ Skipping translation step (--skip-translate flag)")
        run_log.record("Translation", STEP_SKIPPED, "--skip-translate")
    elif not person_id:
        print("\n⊘ Skipping translation step (no person_id resolved)")
        run_log.record("Translation", STEP_SKIPPED, "no person ID resolved")
    else:
        banner("STEP 8/8: Translating generated data")
        try:
            import os

            from openai import OpenAI
            from translate_person import translate_person_data

            translate_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            incomplete = []
            for lang in translate_langs:
                print(f"Translating '{person_id}' to '{lang}'...")
                results = translate_person_data(
                    person_id=person_id,
                    target_lang=lang,
                    client=translate_client,
                    model=args.model or DATASET_MODEL,
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
