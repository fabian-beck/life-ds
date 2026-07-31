#!/usr/bin/env python3
"""Generate complete person dataset by running all three generation scripts."""

import argparse
import sys
from typing import Any

# Import the individual generation functions
from generate_person_events import (
    generate_person_events as generate_dataset,
    DEFAULT_MODEL as DATASET_MODEL,
)
from generate_person_style import generate_style, DEFAULT_MODEL as STYLE_MODEL
from generate_person_network import (
    generate_person_network,
    DEFAULT_MODEL as NETWORK_MODEL,
)
from generate_person_portrait import (
    extract_image_from_page,
    generate_portrait,
    is_direct_image_url,
)
from review_person import review_person_data


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
        "--skip-db",
        action="store_true",
        help="Skip fetching Deutsche Biographie data as additional source.",
    )
    parser.add_argument(
        "--skip-translate",
        action="store_true",
        help="Skip automatic translation after generation.",
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

    try:
        # Determine person_id from dataset generation or by loading existing data
        person_id = person_id_override

        # Step 1: Generate life events dataset
        if run_dataset:
            print("\n" + "=" * 60)
            print("STEP 1/3: Generating life events dataset")
            print("=" * 60 + "\n")
            dataset_path, person_id = generate_dataset(
                subject_for_fetch,
                person_id=person_id_override,
                update_registry=update_registry,
                model=dataset_model,
                use_deutsche_biographie=not args.skip_db,
            )
            print(f"\n✓ Life events dataset written to {dataset_path}")
        else:
            print("\n⊘ Skipping life events dataset generation")

        # Step 2: Generate interface style
        if run_style:
            print("\n" + "=" * 60)
            print("STEP 2/3: Generating interface style")
            print("=" * 60 + "\n")
            style_result = generate_style(
                subject_for_fetch,
                person_id=person_id,
                model=style_model,
            )
            print(f"\n✓ Interface style generated for '{style_result.get('id')}'")
        else:
            print("\n⊘ Skipping interface style generation")

        # Step 3: Generate ego network
        if run_network:
            print("\n" + "=" * 60)
            print("STEP 3/3: Generating ego network")
            print("=" * 60 + "\n")
            network_path = generate_person_network(
                subject_for_fetch,
                person_id=person_id,
                update_registry=update_registry,
                model=network_model,
            )
            print(f"\n✓ Ego network written to {network_path}")
        else:
            print("\n⊘ Skipping ego network generation")

        # Step 4: Generate portrait (if not skipped)
        # Unlike the steps above, portrait failures are non-fatal, so its
        # outcome is tracked explicitly for the final summary.
        portrait_ok = False
        if not args.skip_portrait:
            print("\n" + "=" * 60)
            print("STEP 4/6: Generating stylized portrait")
            print("=" * 60 + "\n")
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
                    portrait_ok = True
                    if portrait_result.get("cached"):
                        print(f"\n⊘ {portrait_result['message']}")
                    else:
                        print(
                            f"\n✓ Portrait generated: {portrait_result.get('local_path')}"
                        )
                else:
                    print(
                        f"\n⚠ Portrait generation failed: {portrait_result['message']}"
                    )
                    print("  Continuing with other generation steps...")
            except Exception as e:
                print(f"\n⚠ Portrait generation failed: {e}")
                print("  Continuing with other generation steps...")
        else:
            print("\n⊘ Skipping portrait generation (--skip-portrait flag)")

        # Step 5: Review (if not skipped)
        if not args.skip_review:
            print("\n" + "=" * 60)
            print("STEP 5/6: REVIEWING GENERATED DATA")
            print("=" * 60)
            print("Running quality review and polish...")
            print("(Only high-confidence changes will be applied)")

            try:
                review_success = review_person_data(
                    person_id or args.subject,
                    skip_low_confidence=True,  # Auto-mode: only high-confidence
                    verbose=False,
                )
                if review_success:
                    print("\n✓ Review complete")
                else:
                    print("\n⚠ Review encountered issues (data still usable)")
            except Exception as e:
                print(f"\n⚠ Review failed: {e}")
                print("  Generated data is still usable, but not reviewed.")
        else:
            print("\n⊘ Skipping review step (--skip-review flag)")

        # Step 6: Translate (if not skipped). Runs last so translations are
        # derived from the final (reviewed) English data. Failures are
        # non-fatal: the English reference is complete and
        # `translate_all_persons.py --check` will report the gap.
        translate_langs = [
            code.strip() for code in args.translate_langs.split(",") if code.strip()
        ]
        if args.skip_translate or not translate_langs:
            print("\n⊘ Skipping translation step (--skip-translate flag)")
        elif not person_id:
            print("\n⊘ Skipping translation step (no person_id resolved)")
        else:
            print("\n" + "=" * 60)
            print("STEP 6/6: Translating generated data")
            print("=" * 60 + "\n")
            try:
                import os

                from openai import OpenAI
                from translate_person import translate_person_data

                translate_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
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
                            f"⚠ Translation to '{lang}' incomplete "
                            f"(translated: {', '.join(translated) or 'nothing'})"
                        )
            except Exception as e:
                print(f"\n⚠ Translation failed: {e}")
                print(
                    "  English data is complete; run scripts/translate_person.py "
                    "manually to retry."
                )

        # Final summary
        print("\n" + "=" * 60)
        print("GENERATION COMPLETE")
        print("=" * 60)
        steps_run = sum([run_dataset, run_style, run_network])
        total_steps = 3
        if not args.skip_portrait:
            total_steps += 1
            steps_run += portrait_ok
        print(
            f"✓ Successfully generated {steps_run} of {total_steps} components for '{args.subject}'"
        )
        if not update_registry:
            print("⊘ Register update skipped by request")
        if args.skip_review:
            print("⊘ Review skipped by request")
        if args.skip_portrait:
            print("⊘ Portrait generation skipped by request")

    except Exception as error:
        print(f"\n✗ Error: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
