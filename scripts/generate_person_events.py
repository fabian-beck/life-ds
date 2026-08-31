#!/usr/bin/env python3
"""Command line for generating one person's life events.

The pipeline itself lives in `events/pipeline.py`; this is the entry point
that reads the arguments and reports where the dataset was written.
"""

import argparse
import sys
from typing import Any

from config import DEFAULT_MODEL, enable_utf8_console
from events.pipeline import REGISTER_PATH, generate_person_events
from utils.text import slugify

enable_utf8_console()


def parse_args(argv: Any) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate life event datasets using two-phase AI approach."
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
        "--no-cache",
        action="store_true",
        help="Skip using cached Wikipedia materials and fetch directly from APIs.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=(
            f"OpenAI model to use (default from OPENAI_MODEL env or '{DEFAULT_MODEL}'). "
            "Must support structured outputs. "
            "See https://platform.openai.com/docs/guides/structured-outputs for supported models."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Any = None) -> int:
    args = parse_args(argv)
    try:
        # When URL is provided, use it for fetching but preserve original subject as person_id
        if args.url:
            subject_for_fetch = args.url
            person_id_override = slugify(args.subject)
        else:
            subject_for_fetch = args.subject
            person_id_override = None

        file_path, person_id = generate_person_events(
            subject_for_fetch,
            person_id=person_id_override,
            update_registry=not args.no_register,
            model=args.model,
            use_cache=not args.no_cache,
        )
        print(f"\nDataset written to {file_path}")
        if args.no_register:
            print("Register update skipped by request.")
        else:
            print(f"Register updated at {REGISTER_PATH}")
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
