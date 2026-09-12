#!/usr/bin/env python3
"""Convert existing PNG portraits to multi-size WebP format for optimized loading."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

from PIL import Image

from config import enable_utf8_console
from utils.registry import Registry

enable_utf8_console()


# Constants
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
REGISTER_PATH = DATA_DIR / "persons.json"
PUBLIC_DIR = Path(__file__).resolve().parents[1] / "public"
PORTRAITS_DIR = PUBLIC_DIR / "portraits"


def create_webp_sizes(source_image_path: Path, person_id: str) -> Dict[str, str]:
    """
    Create multiple WebP sizes from source image for optimized loading.

    Args:
        source_image_path: Path to source PNG image
        person_id: Person identifier

    Returns:
        Dict with size keys (thumbnail, medium, full) mapped to local paths
    """
    sizes = {
        "thumbnail": 200,  # For landing page grid
        "medium": 400,  # For story overview slide
        "full": 1024,  # For image viewer
    }

    result_paths = {}

    try:
        # Open source image
        img = Image.open(source_image_path)

        for size_key, target_size in sizes.items():
            # Calculate new dimensions maintaining aspect ratio
            aspect_ratio = img.width / img.height
            if aspect_ratio > 1:
                # Landscape
                new_width = target_size
                new_height = int(target_size / aspect_ratio)
            else:
                # Portrait or square
                new_height = target_size
                new_width = int(target_size * aspect_ratio)

            # Resize image with high-quality Lanczos resampling
            resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

            # Save as WebP
            output_filename = f"{person_id}_{size_key}.webp"
            output_path = PORTRAITS_DIR / output_filename

            # WebP quality: 85 for full, 80 for smaller sizes (excellent quality, good compression)
            quality = 85 if size_key == "full" else 80
            resized.save(
                output_path, "WEBP", quality=quality, method=6
            )  # method=6 = slowest but best compression

            # Store relative path for use in data files
            result_paths[size_key] = f"/portraits/{output_filename}"

            file_size_kb = output_path.stat().st_size / 1024
            print(
                f"    ✓ Created {size_key} ({new_width}x{new_height}): {output_filename} ({file_size_kb:.1f}KB)"
            )

    except Exception as e:
        print(f"    ✗ Error creating WebP sizes: {e}", file=sys.stderr)
        return {}

    return result_paths


def update_person_portrait_paths(
    person: Dict[str, Any], portrait_paths: Dict[str, str]
) -> None:
    """
    Update a person's portrait data with multi-size WebP paths.

    Args:
        person: Person dict from registry
        portrait_paths: Dict with 'thumbnail', 'medium', 'full' paths
    """
    if "portrait" not in person:
        person["portrait"] = {}

    # Preserve existing data
    original_image = person["portrait"].get("originalImage") or person["portrait"].get(
        "image"
    )
    source = person["portrait"].get("source", "https://commons.wikimedia.org/")
    caption = person["portrait"].get(
        "caption", "Stylized portrait based on historical photograph"
    )
    creator = person["portrait"].get("creator", "AI generated artwork")
    original_caption = person["portrait"].get("originalCaption")

    # Update with multi-size paths
    person["portrait"].update(
        {
            "image": portrait_paths.get(
                "thumbnail", portrait_paths.get("full")
            ),  # Default to thumbnail
            "thumbnail": portrait_paths.get("thumbnail"),
            "medium": portrait_paths.get("medium"),
            "full": portrait_paths.get("full"),
            "source": source,
            "caption": caption,
            "creator": creator,
            "originalImage": original_image,
        }
    )

    if original_caption:
        person["portrait"]["originalCaption"] = original_caption


def update_life_events_portrait(person_id: str, portrait_data: Dict[str, Any]) -> None:
    """
    Update life_events.json with portrait data for main language and translations.

    Args:
        person_id: Person identifier
        portrait_data: Portrait data dict to sync
    """
    people_dir = DATA_DIR / "people" / person_id

    if not people_dir.exists():
        print(f"    Warning: Person directory not found: {people_dir}", file=sys.stderr)
        return

    # Update main life_events.json
    life_events_file = people_dir / "life_events.json"
    if life_events_file.exists():
        try:
            life_events = json.loads(life_events_file.read_text(encoding="utf-8"))

            if not life_events.get("person"):
                life_events["person"] = {}

            life_events["person"]["portrait"] = portrait_data

            life_events_file.write_text(
                json.dumps(life_events, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            print("    ✓ Updated life_events.json")
        except Exception as e:
            print(
                f"    Warning: Failed to update life_events.json: {e}", file=sys.stderr
            )

    # Update translated life_events.json files
    updated_translations = []
    for lang_dir in people_dir.iterdir():
        if not lang_dir.is_dir() or lang_dir.name.startswith("_"):
            continue

        translated_life_events = lang_dir / "life_events.json"
        if translated_life_events.exists():
            try:
                life_events = json.loads(
                    translated_life_events.read_text(encoding="utf-8")
                )

                if not life_events.get("person"):
                    life_events["person"] = {}

                life_events["person"]["portrait"] = portrait_data

                translated_life_events.write_text(
                    json.dumps(life_events, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
                updated_translations.append(lang_dir.name)
            except Exception as e:
                print(
                    f"    Warning: Failed to update {lang_dir.name}/life_events.json: {e}",
                    file=sys.stderr,
                )

    if updated_translations:
        print(f"    ✓ Updated translations: {', '.join(updated_translations)}")


def convert_portrait(person_id: str, force: bool = False) -> bool:
    """
    Convert a single person's PNG portrait to multi-size WebP.

    Args:
        person_id: Person identifier
        force: Regenerate even if WebP files exist

    Returns:
        True if successful, False otherwise
    """
    print(f"  Converting portrait for: {person_id}")

    # Check if source PNG exists
    source_png = PORTRAITS_DIR / f"{person_id}.png"
    if not source_png.exists():
        print(f"    ⊘ No PNG portrait found: {source_png}")
        return False

    # Check if WebP files already exist
    thumbnail_webp = PORTRAITS_DIR / f"{person_id}_thumbnail.webp"
    if thumbnail_webp.exists() and not force:
        print("    ⊘ WebP portraits already exist (use --force to regenerate)")
        return True

    # Create WebP sizes
    portrait_paths = create_webp_sizes(source_png, person_id)

    if not portrait_paths:
        print("    ✗ Failed to create WebP sizes")
        return False

    # Update registry
    registry = Registry(REGISTER_PATH)
    person = registry.find(person_id)

    if not person:
        print("    Warning: Person not found in registry", file=sys.stderr)
        return False

    update_person_portrait_paths(person, portrait_paths)
    registry.save()
    print("    ✓ Registry updated")

    # Update life_events.json
    update_life_events_portrait(person_id, person["portrait"])

    return True


def convert_all_portraits(force: bool = False) -> None:
    """
    Convert all PNG portraits in the portraits directory to multi-size WebP.

    Args:
        force: Regenerate even if WebP files exist
    """
    if not PORTRAITS_DIR.exists():
        print(f"✗ Portraits directory not found: {PORTRAITS_DIR}", file=sys.stderr)
        return

    # Find all PNG portraits
    png_portraits = list(PORTRAITS_DIR.glob("*.png"))

    # Filter out the master style portrait
    png_portraits = [p for p in png_portraits if p.name != "master_style_portrait.png"]

    if not png_portraits:
        print("No PNG portraits found to convert")
        return

    print(f"Found {len(png_portraits)} PNG portrait(s) to convert")
    print()

    success_count = 0
    skip_count = 0
    fail_count = 0

    for png_path in png_portraits:
        # Extract person_id from filename (e.g., "alan_turing.png" -> "alan_turing")
        person_id = png_path.stem

        result = convert_portrait(person_id, force=force)

        if result:
            # Check if it was actually converted or skipped
            thumbnail_webp = PORTRAITS_DIR / f"{person_id}_thumbnail.webp"
            if thumbnail_webp.exists():
                success_count += 1
            else:
                skip_count += 1
        else:
            fail_count += 1

        print()

    # Summary
    print("=" * 60)
    print("Conversion complete!")
    print(f"  ✓ Successfully converted: {success_count}")
    print(f"  ⊘ Skipped (already exist): {skip_count}")
    print(f"  ✗ Failed: {fail_count}")
    print("=" * 60)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Convert existing PNG portraits to multi-size WebP format."
    )
    parser.add_argument(
        "person_ids",
        nargs="*",
        help="Person IDs to convert (if not specified, converts all)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate even if WebP files already exist",
    )
    return parser.parse_args()


def main() -> int:
    """Main entry point."""
    args = parse_args()

    print("Converting PNG portraits to multi-size WebP format")
    print("=" * 60)
    print()

    try:
        if args.person_ids:
            # Convert specific persons
            success_count = 0
            for person_id in args.person_ids:
                if convert_portrait(person_id, force=args.force):
                    success_count += 1
                print()

            print(
                f"✓ Successfully converted {success_count}/{len(args.person_ids)} portrait(s)"
            )
        else:
            # Convert all portraits
            convert_all_portraits(force=args.force)

        return 0

    except Exception as error:
        print(f"\n✗ Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
