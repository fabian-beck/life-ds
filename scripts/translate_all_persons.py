#!/usr/bin/env python3
"""Batch translate all persons in the registry to a target language."""

import argparse
import json
import os
import sys

from openai import OpenAI

from config import DEFAULT_MODEL
from translate_person import translate_person_data, REGISTER_PATH, LANGUAGE_NAMES


def main():
    parser = argparse.ArgumentParser(
        description="Translate all persons in the registry to a target language"
    )
    parser.add_argument(
        "--target-lang",
        required=True,
        help="Target language code (e.g., 'de', 'fr', 'es')",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-translate even if translation already exists",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"OpenAI model to use (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--persons",
        help="Comma-separated list of person IDs to translate (default: all)",
    )
    parser.add_argument(
        "--skip-registry",
        action="store_true",
        help="Skip updating the language-specific registry file",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")

    args = parser.parse_args()

    # Validate OpenAI API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY environment variable not set")
        sys.exit(1)

    # Load registry
    if not REGISTER_PATH.exists():
        print(f"Error: Registry not found: {REGISTER_PATH}")
        sys.exit(1)

    with open(REGISTER_PATH, "r", encoding="utf-8") as f:
        registry = json.load(f)

    all_persons = registry.get("people", [])
    if not all_persons:
        print("Error: No persons found in registry")
        sys.exit(1)

    # Filter persons if specified
    if args.persons:
        person_ids = [p.strip() for p in args.persons.split(",")]
        persons_to_translate = [p for p in all_persons if p["id"] in person_ids]
        if len(persons_to_translate) != len(person_ids):
            found_ids = {p["id"] for p in persons_to_translate}
            missing = set(person_ids) - found_ids
            print(f"Warning: Some person IDs not found: {missing}")
    else:
        persons_to_translate = all_persons

    if not persons_to_translate:
        print("Error: No persons to translate")
        sys.exit(1)

    # Initialize OpenAI client
    client = OpenAI(api_key=api_key)

    lang_name = LANGUAGE_NAMES.get(args.target_lang, args.target_lang)
    total = len(persons_to_translate)

    print(f"Translating {total} person(s) to {lang_name}...")
    print(f"Model: {args.model}")
    print(f"Force: {args.force}")
    print()

    # Track results
    successful = []
    failed = []
    skipped = []

    # Translate each person
    for i, person in enumerate(persons_to_translate, 1):
        person_id = person["id"]
        person_name = person.get("name", person_id)

        print(f"[{i}/{total}] {person_name} ({person_id})")

        try:
            results = translate_person_data(
                person_id=person_id,
                target_lang=args.target_lang,
                client=client,
                model=args.model,
                force=args.force,
                verbose=args.verbose,
            )

            # Check if anything was translated
            if any(results.values()):
                successful.append(person_id)
                success_items = [k for k, v in results.items() if v]
                print(f"  ✓ Translated: {', '.join(success_items)}")
            else:
                # Could be skipped or failed
                from pathlib import Path

                target_dir = (
                    Path(__file__).resolve().parents[1]
                    / "data"
                    / "people"
                    / person_id
                    / args.target_lang
                )
                if not args.force and target_dir.exists():
                    skipped.append(person_id)
                    print("  → Skipped (already exists)")
                else:
                    failed.append(person_id)
                    print("  ✗ Failed")

        except KeyboardInterrupt:
            print("\n\nTranslation interrupted by user")
            break
        except Exception as e:
            print(f"  ✗ Error: {e}")
            failed.append(person_id)

        print()

    # Print summary
    print("=" * 60)
    print("TRANSLATION SUMMARY")
    print("=" * 60)
    print(f"Total:      {total}")
    print(f"Successful: {len(successful)}")
    print(f"Skipped:    {len(skipped)}")
    print(f"Failed:     {len(failed)}")
    print()

    if successful:
        print(f"✓ Successfully translated {len(successful)} person(s):")
        for pid in successful:
            print(f"  - {pid}")
        print()

    if skipped:
        print(f"→ Skipped {len(skipped)} person(s) (already translated):")
        for pid in skipped:
            print(f"  - {pid}")
        print()

    if failed:
        print(f"✗ Failed to translate {len(failed)} person(s):")
        for pid in failed:
            print(f"  - {pid}")
        print()

    # Exit with appropriate code
    if failed:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
