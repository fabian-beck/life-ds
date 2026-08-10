#!/usr/bin/env python3
"""Generate stylized portraits for all persons using the OpenAI image API."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List

from generate_person_portrait import (
    DEFAULT_MASTER_STYLE_PATH,
    PORTRAITS_DIR,
    generate_portrait,
    person_registry,
)

# Note: UTF-8 encoding is already set by generate_person_portrait module


def get_persons_needing_portraits(
    registry: Dict[str, Any], force: bool = False
) -> List[str]:
    """
    Get list of person IDs that need portrait generation.

    Args:
        registry: The persons registry
        force: If True, include all persons even if they have portraits

    Returns:
        List of person IDs
    """
    persons_needing_portraits = []

    for person in registry.get("people", []):
        person_id = person.get("id")
        if not person_id:
            continue

        # Check if portrait is already generated
        portrait = person.get("portrait", {})
        portrait_image = portrait.get("image", "")

        # Generated portraits are stored in /portraits/
        has_generated_portrait = portrait_image.startswith("/portraits/")

        # Check if the portrait file actually exists
        portrait_path = PORTRAITS_DIR / f"{person_id}.png"
        portrait_exists = portrait_path.exists()

        if force or not has_generated_portrait or not portrait_exists:
            # Check if person has a reference portrait (Wikimedia URL)
            reference_url = None
            if portrait_image and portrait_image.startswith("http"):
                # Already has Wikimedia URL
                reference_url = portrait_image
            elif portrait_image.startswith("/portraits/"):
                # Has generated portrait, check for original
                reference_url = portrait.get("originalImage")

            if reference_url:
                persons_needing_portraits.append(person_id)
            else:
                print(
                    f"⊘ Skipping {person_id}: No reference portrait URL available",
                    file=sys.stderr,
                )

    return persons_needing_portraits


def main(argv: Any = None) -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate stylized portraits for all persons using the OpenAI image API."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate all portraits even if they exist",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Test without API calls or file writes"
    )
    parser.add_argument(
        "--master-style",
        type=Path,
        default=DEFAULT_MASTER_STYLE_PATH,
        help=f"Path to master style portrait (default: {DEFAULT_MASTER_STYLE_PATH})",
    )
    parser.add_argument(
        "--model",
        default="gpt-image-2",
        help="OpenAI model to use (default: gpt-image-2). Models with image editing support: dall-e-2, gpt-image-1, gpt-image-1.5, gpt-image-2",
    )
    parser.add_argument(
        "--persons",
        help="Comma-separated list of specific person IDs to generate (e.g., 'alan_turing,ada_lovelace')",
    )

    args = parser.parse_args(argv)

    # Load registry
    try:
        registry = person_registry().document
    except Exception as e:
        print(f"✗ Error loading persons registry: {e}", file=sys.stderr)
        return 1

    # Get persons to process
    if args.persons:
        # Generate specific persons
        person_ids = [p.strip() for p in args.persons.split(",")]
        print(f"Generating portraits for specified persons: {', '.join(person_ids)}")
    else:
        # Get persons needing portraits
        person_ids = get_persons_needing_portraits(registry, force=args.force)

        if not person_ids:
            print("✓ All persons already have portraits!")
            print("  Use --force to regenerate all portraits")
            return 0

        print(f"Found {len(person_ids)} person(s) needing portraits:")
        for person_id in person_ids:
            print(f"  - {person_id}")

    print()
    print(f"Master style: {args.master_style}")
    print(f"Model: {args.model}")
    if args.dry_run:
        print("Mode: DRY RUN (no API calls or file writes)")
    if args.force:
        print("Force: Regenerate even if exists")
    print()

    # Generate portraits
    results = []
    total = len(person_ids)

    for idx, person_id in enumerate(person_ids, 1):
        print(f"{'='*80}")
        print(f"Processing {idx}/{total}: {person_id}")
        print(f"{'='*80}")
        print()

        # Find person in registry
        person = None
        for p in registry.get("people", []):
            if p.get("id") == person_id:
                person = p
                break

        if not person:
            print(
                f"✗ Error: Person '{person_id}' not found in registry", file=sys.stderr
            )
            results.append(
                {
                    "id": person_id,
                    "success": False,
                    "message": "Person not found in registry",
                }
            )
            continue

        # Get reference portrait URL
        portrait = person.get("portrait", {})
        reference_url = portrait.get("image")

        # If portrait is a local path (already generated), use the original Wikimedia URL
        if reference_url and reference_url.startswith("/portraits/"):
            reference_url = portrait.get("originalImage")
            if reference_url:
                print(
                    "Using original Wikimedia portrait (stored in originalImage field)"
                )

        if not reference_url or not reference_url.startswith("http"):
            error_msg = f"No valid reference portrait URL for '{person_id}'"
            print(f"✗ Error: {error_msg}", file=sys.stderr)
            results.append({"id": person_id, "success": False, "message": error_msg})
            continue

        print(f"Reference portrait: {reference_url}")
        print()

        # Generate portrait
        result = generate_portrait(
            person_id=person_id,
            reference_image_url=reference_url,
            master_style_path=args.master_style,
            model=args.model,
            dry_run=args.dry_run,
            force=args.force,
        )

        results.append(result)
        print()

    # Print summary
    print(f"{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    print()

    successful = [r for r in results if r.get("success")]
    cached = [r for r in results if r.get("cached")]
    failed = [r for r in results if not r.get("success")]

    print(f"Total: {len(results)}")
    print(f"Successful: {len(successful)}")
    print(f"Cached (already existed): {len(cached)}")
    print(f"Failed: {len(failed)}")
    print()

    if failed:
        print("Failed portraits:")
        for result in failed:
            print(f"  ✗ {result['id']}: {result.get('message', 'Unknown error')}")
        print()

    if successful and not cached:
        print("Successfully generated:")
        for result in successful:
            if not result.get("cached"):
                print(f"  ✓ {result['id']}")
        print()

    if cached:
        print("Already existed (use --force to regenerate):")
        for result in cached:
            print(f"  ⊘ {result['id']}")
        print()

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
