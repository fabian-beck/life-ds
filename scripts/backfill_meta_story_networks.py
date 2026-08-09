#!/usr/bin/env python3
"""Backfill the ``social_network`` block into existing meta-story JSON files.

The network is derived deterministically from ego networks (no AI, no API key),
so this can rebuild the block for every meta-story — including translated
copies under ``data/meta_stories/{lang}/`` — in place.

Node labels are person names and ``relationship_type`` is localized by the UI,
so the same derived network is written to every language file. Only optional
``relationship_description`` tooltips fall back to English.

Usage:
    python scripts/backfill_meta_story_networks.py            # all stories
    python scripts/backfill_meta_story_networks.py computing_pioneers
    python scripts/backfill_meta_story_networks.py --dry-run
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from config import enable_utf8_console
from utils.json_io import read_json, write_json
from meta_story_network import DATA_DIR, build_social_network, derive_clusters

enable_utf8_console()

META_STORIES_DIR = DATA_DIR / "meta_stories"
REGISTER_PATH = DATA_DIR / "persons.json"


def _story_files(story_id: str) -> List[Path]:
    """The English file plus every translated copy for a story."""
    files = []
    english = META_STORIES_DIR / f"{story_id}.json"
    if english.exists():
        files.append(english)
    for lang_dir in sorted(META_STORIES_DIR.iterdir()):
        if lang_dir.is_dir():
            translated = lang_dir / f"{story_id}.json"
            if translated.exists():
                files.append(translated)
    return files


def _story_ids() -> List[str]:
    return sorted(p.stem for p in META_STORIES_DIR.glob("*.json") if p.is_file())


def backfill(story_ids: List[str], registry: Dict[str, Any], dry_run: bool) -> None:
    for story_id in story_ids:
        english_path = META_STORIES_DIR / f"{story_id}.json"
        if not english_path.exists():
            print(f"  ⚠ Skipping unknown story: {story_id}")
            continue

        english = read_json(english_path)
        person_ids = english.get("meta_story", {}).get("person_ids", [])
        network = build_social_network(person_ids, registry)

        n_main = sum(1 for n in network["nodes"] if n["type"] == "main")
        n_sec = sum(1 for n in network["nodes"] if n["type"] == "secondary")
        print(
            f"{story_id}: {n_main} main + {n_sec} secondary nodes, "
            f"{len(network['links'])} links"
        )

        # Circle keys of the re-derived network, for narration carry-over.
        valid_keys = {c["key"] for c in derive_clusters(network)}
        main_ids = {n["id"] for n in network["nodes"] if n["type"] == "main"}

        def circle_survives(circle: Dict[str, Any]) -> bool:
            # Composer-organized circles carry explicit member_ids; they stay
            # valid as long as every member is still a main node. Derived
            # circles are matched against the re-derived cluster keys.
            members = circle.get("member_ids")
            if members:
                return all(pid in main_ids for pid in members)
            return circle.get("key") in valid_keys

        for path in _story_files(story_id):
            data = read_json(path)
            # Carry over each file's own narration (English or translated),
            # dropping circles whose cluster no longer exists. Regenerate
            # narration with the meta story pipeline when circles changed.
            old_narration = (data.get("social_network") or {}).get("narration")
            data["social_network"] = json.loads(json.dumps(network))
            if isinstance(old_narration, dict):
                kept = [
                    circle
                    for circle in (old_narration.get("circles") or [])
                    if circle_survives(circle)
                ]
                dropped = len(old_narration.get("circles") or []) - len(kept)
                data["social_network"]["narration"] = {
                    **old_narration,
                    "circles": kept,
                }
                if dropped:
                    print(
                        f"    ⚠ {path.relative_to(DATA_DIR)}: dropped {dropped} "
                        "narration circle(s) whose cluster changed — regenerate "
                        "narration"
                    )
            if dry_run:
                print(f"    [dry-run] would update {path.relative_to(DATA_DIR)}")
            else:
                write_json(path, data)
                print(f"    ✓ {path.relative_to(DATA_DIR)}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill social_network into meta-story JSON files"
    )
    parser.add_argument(
        "story_ids",
        nargs="*",
        help="Specific story IDs (default: all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without writing",
    )
    args = parser.parse_args()

    registry = read_json(REGISTER_PATH)
    story_ids = args.story_ids or _story_ids()
    backfill(story_ids, registry, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
