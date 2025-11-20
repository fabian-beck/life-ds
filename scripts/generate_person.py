#!/usr/bin/env python3
"""Generate complete person dataset by running all three generation scripts."""

import argparse
import sys
from pathlib import Path
from typing import Any

# Import the individual generation functions
from generate_person_dataset import generate_dataset, DEFAULT_MODEL as DATASET_MODEL
from generate_person_style import generate_style, DEFAULT_MODEL as STYLE_MODEL
from generate_person_network import generate_person_network, DEFAULT_MODEL as NETWORK_MODEL


def parse_args(argv: Any) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate complete person dataset (life events, interface style, and ego network)."
    )
    parser.add_argument(
        "subject",
        help="Person to research, e.g. 'Ada Lovelace'."
    )
    parser.add_argument(
        "--no-register",
        action="store_true",
        help="Skip updating the persons register."
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
        help="Generate only life events dataset (skip interface style and network)."
    )
    parser.add_argument(
        "--style-only",
        action="store_true",
        help="Generate only interface style (skip dataset and network)."
    )
    parser.add_argument(
        "--network-only",
        action="store_true",
        help="Generate only ego network (skip dataset and interface style)."
    )
    return parser.parse_args(argv)


def main(argv: Any = None) -> int:
    """Main entry point."""
    args = parse_args(argv)
    update_registry = not args.no_register

    # Determine which models to use
    dataset_model = args.model or DATASET_MODEL
    style_model = args.model or STYLE_MODEL
    network_model = args.model or NETWORK_MODEL

    # Determine which steps to run
    run_dataset = not (args.style_only or args.network_only)
    run_style = not (args.dataset_only or args.network_only)
    run_network = not (args.dataset_only or args.style_only)

    try:
        # Step 1: Generate life events dataset
        if run_dataset:
            print("\n" + "="*60)
            print("STEP 1/3: Generating life events dataset")
            print("="*60 + "\n")
            dataset_path = generate_dataset(
                args.subject,
                update_registry=update_registry,
                model=dataset_model,
            )
            print(f"\n✓ Life events dataset written to {dataset_path}")
        else:
            print("\n⊘ Skipping life events dataset generation")

        # Step 2: Generate interface style
        if run_style:
            print("\n" + "="*60)
            print("STEP 2/3: Generating interface style")
            print("="*60 + "\n")
            style_result = generate_style(
                args.subject,
                model=style_model,
            )
            print(f"\n✓ Interface style generated for '{style_result.get('id')}'")
        else:
            print("\n⊘ Skipping interface style generation")

        # Step 3: Generate ego network
        if run_network:
            print("\n" + "="*60)
            print("STEP 3/3: Generating ego network")
            print("="*60 + "\n")
            network_path = generate_person_network(
                args.subject,
                update_registry=update_registry,
                model=network_model,
            )
            print(f"\n✓ Ego network written to {network_path}")
        else:
            print("\n⊘ Skipping ego network generation")

        # Final summary
        print("\n" + "="*60)
        print("GENERATION COMPLETE")
        print("="*60)
        steps_run = sum([run_dataset, run_style, run_network])
        print(f"✓ Successfully generated {steps_run} of 3 datasets for '{args.subject}'")
        if not update_registry:
            print("⊘ Register update skipped by request")

    except Exception as error:
        print(f"\n✗ Error: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
