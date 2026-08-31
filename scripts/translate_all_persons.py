#!/usr/bin/env python3
"""Batch translate all persons (and meta stories) to a target language.

English is the reference version. By default this script (re)translates only
documents that are missing or stale — i.e. whose stored source fingerprint no
longer matches the current English text. Use --force to re-translate
everything, and --check to print a parity report without calling any API.

--check fails on a missing translation and warns on a stale one. A missing
document leaves a reader in that language with nothing, while a stale one is
readable prose describing English text that has since moved, and it is the
expected state between regenerating a person and re-translating them. Gating
on it stops every unrelated change until the re-translation runs.
"""

import argparse
import json
import os
import sys

from config import enable_utf8_console
from translate_person import (
    LANGUAGE_NAMES,
    REGISTER_PATH,
    TRANSLATION_MODEL,
    check_person_translation,
    translate_person_data,
)
from translate_meta_story import (
    check_meta_story_translation,
    list_meta_story_ids,
    translate_meta_story_data,
)

enable_utf8_console()

STATUS_ICONS = {
    "current": "✓",
    "stale": "↻",
    "missing": "✗",
    "no-source": "-",
}


def load_person_list():
    if not REGISTER_PATH.exists():
        print(f"Error: Registry not found: {REGISTER_PATH}")
        sys.exit(1)
    with open(REGISTER_PATH, "r", encoding="utf-8") as f:
        registry = json.load(f)
    people = registry.get("people", [])
    if not people:
        print("Error: No persons found in registry")
        sys.exit(1)
    return people


def run_check(persons, target_lang, include_meta=True):
    """Print a parity report (no API calls). Returns the status counts."""
    lang_name = LANGUAGE_NAMES.get(target_lang, target_lang)
    print(f"Translation status for {lang_name} ({target_lang})")
    print("(✓ current, ↻ stale, ✗ missing)\n")

    counts = {"current": 0, "stale": 0, "missing": 0, "no-source": 0}
    print(f"{'PERSON':<40} {'EVENTS':<8} {'NETWORK':<8} {'REGISTRY':<8}")
    for person in persons:
        person_id = person["id"]
        status = check_person_translation(person_id, target_lang)
        for value in status.values():
            counts[value] = counts.get(value, 0) + 1
        print(
            f"{person_id:<40} "
            f"{STATUS_ICONS.get(status['life_events'], '?'):<8} "
            f"{STATUS_ICONS.get(status['ego_network'], '?'):<8} "
            f"{STATUS_ICONS.get(status['registry'], '?'):<8}"
        )

    if include_meta:
        print(f"\n{'META STORY':<40} {'DETAIL':<8} {'REGISTRY':<8}")
        for story_id in list_meta_story_ids():
            status = check_meta_story_translation(story_id, target_lang)
            for value in status.values():
                counts[value] = counts.get(value, 0) + 1
            print(
                f"{story_id:<40} "
                f"{STATUS_ICONS.get(status['detail'], '?'):<8} "
                f"{STATUS_ICONS.get(status['registry'], '?'):<8}"
            )

    total = sum(counts.values())
    print(
        f"\nSummary: {counts['current']}/{total} current, "
        f"{counts['stale']} stale, {counts['missing']} missing"
    )
    if counts["stale"]:
        print(
            f"Warning: {counts['stale']} document(s) describe English text "
            "that has since changed. Re-translate with translate_person.py."
        )
    return counts


def main():
    parser = argparse.ArgumentParser(
        description="Translate all persons (and meta stories) to a target language"
    )
    parser.add_argument(
        "--target-lang",
        required=True,
        help="Target language code (e.g., 'de', 'fr', 'es')",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only report translation status (no API calls, no changes)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-translate everything, even translations that are current",
    )
    parser.add_argument(
        "--model",
        default=TRANSLATION_MODEL,
        help=f"OpenAI model to translate with (default: {TRANSLATION_MODEL})",
    )
    parser.add_argument(
        "--persons",
        help="Comma-separated list of person IDs to translate (default: all)",
    )
    parser.add_argument(
        "--skip-meta",
        action="store_true",
        help="Skip translating meta stories",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")

    args = parser.parse_args()

    all_persons = load_person_list()

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

    include_meta = not args.skip_meta and not args.persons

    # Check-only mode requires no API key and changes nothing
    if args.check:
        counts = run_check(persons_to_translate, args.target_lang, include_meta)
        sys.exit(1 if counts["missing"] else 0)

    # Validate OpenAI API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY environment variable not set")
        sys.exit(1)

    from openai import OpenAI

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
            before = check_person_translation(person_id, args.target_lang)
            if not args.force and all(v == "current" for v in before.values()):
                skipped.append(person_id)
                print("  → Skipped (translation current)")
                print()
                continue

            results = translate_person_data(
                person_id=person_id,
                target_lang=args.target_lang,
                client=client,
                model=args.model,
                force=args.force,
                verbose=args.verbose,
            )

            after = check_person_translation(person_id, args.target_lang)
            if any(results.values()) and all(
                v in ("current", "no-source") for v in after.values()
            ):
                successful.append(person_id)
                success_items = [k for k, v in results.items() if v]
                print(f"  ✓ Translated: {', '.join(success_items)}")
            else:
                failed.append(person_id)
                print("  ✗ Failed (translation incomplete)")

        except KeyboardInterrupt:
            print("\n\nTranslation interrupted by user")
            break
        except Exception as e:
            print(f"  ✗ Error: {e}")
            failed.append(person_id)

        print()

    # Translate meta stories
    meta_successful = []
    meta_failed = []
    if include_meta:
        story_ids = list_meta_story_ids()
        print(f"Translating {len(story_ids)} meta story(ies) to {lang_name}...")
        for story_id in story_ids:
            print(f"  {story_id}")
            try:
                before = check_meta_story_translation(story_id, args.target_lang)
                if not args.force and all(v == "current" for v in before.values()):
                    print("  → Skipped (translation current)")
                    continue
                if translate_meta_story_data(
                    story_id,
                    args.target_lang,
                    client,
                    model=args.model,
                    force=args.force,
                    verbose=args.verbose,
                ):
                    meta_successful.append(story_id)
                    print("  ✓ Translated")
                else:
                    meta_failed.append(story_id)
                    print("  ✗ Failed")
            except Exception as e:
                print(f"  ✗ Error: {e}")
                meta_failed.append(story_id)
        print()

    # Print summary
    print("=" * 60)
    print("TRANSLATION SUMMARY")
    print("=" * 60)
    print(f"Persons:      {total}")
    print(f"  Successful: {len(successful)}")
    print(f"  Skipped:    {len(skipped)} (already current)")
    print(f"  Failed:     {len(failed)}")
    if include_meta:
        print(
            f"Meta stories translated: {len(meta_successful)}, failed: {len(meta_failed)}"
        )
    print()

    if failed:
        print(f"✗ Failed to translate {len(failed)} person(s):")
        for pid in failed:
            print(f"  - {pid}")
        print()
    if meta_failed:
        print(f"✗ Failed to translate {len(meta_failed)} meta story(ies):")
        for sid in meta_failed:
            print(f"  - {sid}")
        print()

    # Exit with appropriate code
    if failed or meta_failed:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
