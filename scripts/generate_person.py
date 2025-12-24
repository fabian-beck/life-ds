#!/usr/bin/env python3
"""Generate complete person dataset by running all three generation scripts."""

import argparse
import sys
from typing import Any

# Import the individual generation functions
from generate_person_events import generate_person_events as generate_dataset, DEFAULT_MODEL as DATASET_MODEL
from generate_person_style import generate_style, DEFAULT_MODEL as STYLE_MODEL
from generate_person_network import (
    generate_person_network,
    DEFAULT_MODEL as NETWORK_MODEL,
)
from generate_person_portrait import generate_portrait
from review_person import review_person_data


def parse_args(argv: Any) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate complete person dataset (life events, interface style, and ego network)."
    )
    parser.add_argument("subject", help="Person to research, e.g. 'Ada Lovelace' or 'henry_II'.")
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
            "Must support structured outputs: gpt-4o-mini, gpt-4o-2024-08-06, or later."
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
        default="gpt-image-1",
        help="OpenAI model for portrait generation (default: gpt-image-1).",
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
        if not args.skip_portrait:
            print("\n" + "=" * 60)
            print("STEP 4/5: Generating stylized portrait")
            print("=" * 60 + "\n")
            try:
                from pathlib import Path
                portrait_result = generate_portrait(
                    person_id=person_id,
                    reference_image_url=None,  # Will use reference from registry
                    source_page_url=None,
                    master_style_path=Path(__file__).resolve().parents[1] / "public" / "master_style_portrait.png",
                    model=args.portrait_model,
                    dry_run=False,
                    force=False,
                )
                if portrait_result["success"]:
                    if portrait_result.get("cached"):
                        print(f"\n⊘ {portrait_result['message']}")
                    else:
                        print(f"\n✓ Portrait generated: {portrait_result.get('local_path')}")
                else:
                    print(f"\n⚠ Portrait generation failed: {portrait_result['message']}")
                    print("  Continuing with other generation steps...")
            except Exception as e:
                print(f"\n⚠ Portrait generation failed: {e}")
                print("  Continuing with other generation steps...")
        else:
            print("\n⊘ Skipping portrait generation (--skip-portrait flag)")

        # Step 5: Review (if not skipped)
        if not args.skip_review:
            print("\n" + "=" * 60)
            print("STEP 5/5: REVIEWING GENERATED DATA")
            print("=" * 60)
            print("Running quality review and polish...")
            print("(Only high-confidence changes will be applied)")

            try:
                review_success = review_person_data(
                    person_id or args.subject,
                    skip_low_confidence=True,  # Auto-mode: only high-confidence
                    verbose=False
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

        # Final summary
        print("\n" + "=" * 60)
        print("GENERATION COMPLETE")
        print("=" * 60)
        steps_run = sum([run_dataset, run_style, run_network])
        total_steps = 3
        if not args.skip_portrait:
            total_steps += 1
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
