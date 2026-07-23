#!/usr/bin/env python3
"""Translate meta stories (thematic story collections) to a target language.

Like person translations, meta story translations are derived from the English
reference: only text fields are translated and merged onto a copy of the
English document (see translate_person.py for the architecture).

Layout:
- data/meta_stories/{id}.json           English detail (reference)
- data/meta_stories/{lang}/{id}.json    Translated detail
- data/meta_stories.json                English registry (reference)
- data/meta_stories_{lang}.json         Translated registry
"""

import argparse
import copy
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

from openai import OpenAI

from config import DEFAULT_MODEL
from translate_person import (
    DATA_DIR,
    LANGUAGE_NAMES,
    compute_fingerprint,
    extract_meta_story_translatables,
    load_json_file,
    save_json_file,
    translate_meta_story,
    translation_status,
)

META_STORIES_DIR = DATA_DIR / "meta_stories"
META_STORIES_REGISTER = DATA_DIR / "meta_stories.json"


def list_meta_story_ids() -> List[str]:
    """All meta story IDs from the English registry."""
    registry = load_json_file(META_STORIES_REGISTER) or {}
    return [
        entry["id"]
        for entry in registry.get("meta_stories", [])
        if isinstance(entry, dict) and entry.get("id")
    ]


def registry_entry_for(story_id: str) -> Optional[Dict[str, Any]]:
    registry = load_json_file(META_STORIES_REGISTER) or {}
    return next(
        (e for e in registry.get("meta_stories", []) if e.get("id") == story_id),
        None,
    )


def update_language_meta_registry(
    story_id: str,
    translated_detail: Dict[str, Any],
    target_lang: str,
    verbose: bool = False,
) -> bool:
    """Derive the language registry entry from the English registry entry plus
    the already-translated detail document, keeping English registry order."""
    source_entry = registry_entry_for(story_id)
    if source_entry is None:
        print(f"  ⚠ Meta story not found in registry: {story_id}")
        return False

    entry = copy.deepcopy(source_entry)
    meta = translated_detail.get("meta_story", {}) or {}
    if meta.get("title"):
        entry["title"] = meta["title"]
    if meta.get("tagline"):
        entry["tagline"] = meta["tagline"]
    entry["lastUpdated"] = datetime.now().astimezone().isoformat()
    entry["translation"] = {
        "source_lang": "en",
        "target_lang": target_lang,
        "source_fingerprint": compute_fingerprint(
            _extract_registry_translatables(source_entry)
        ),
        "translated_on": entry["lastUpdated"],
        "translator": translated_detail.get("translation", {}).get(
            "translator", "derived"
        ),
    }

    registry_path = DATA_DIR / f"meta_stories_{target_lang}.json"
    registry = load_json_file(registry_path) or {"meta_stories": []}
    stories = registry.setdefault("meta_stories", [])
    for i, existing in enumerate(stories):
        if existing.get("id") == story_id:
            stories[i] = entry
            break
    else:
        stories.append(entry)

    # Keep the language registry ordered like the English registry
    order = {sid: i for i, sid in enumerate(list_meta_story_ids())}
    stories.sort(key=lambda e: order.get(e.get("id"), len(order)))

    if verbose:
        print(f"  ✓ Updated {registry_path.name}")
    return save_json_file(registry, registry_path)


def _extract_registry_translatables(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {"title": entry.get("title", ""), "tagline": entry.get("tagline", "")}


def check_meta_story_translation(story_id: str, target_lang: str) -> Dict[str, str]:
    """Report the translation status of a meta story without calling any API."""
    detail_status = translation_status(
        load_json_file(META_STORIES_DIR / f"{story_id}.json"),
        load_json_file(META_STORIES_DIR / target_lang / f"{story_id}.json"),
        extract_meta_story_translatables,
    )
    registry = load_json_file(DATA_DIR / f"meta_stories_{target_lang}.json") or {}
    target_entry = next(
        (e for e in registry.get("meta_stories", []) if e.get("id") == story_id),
        None,
    )
    registry_status = translation_status(
        registry_entry_for(story_id), target_entry, _extract_registry_translatables
    )
    return {"detail": detail_status, "registry": registry_status}


def translate_meta_story_data(
    story_id: str,
    target_lang: str,
    client: OpenAI,
    model: str = DEFAULT_MODEL,
    force: bool = False,
    verbose: bool = False,
) -> bool:
    """Translate one meta story (detail file + registry entry).

    Without ``force``, skips meta stories whose translation is current.
    """
    source = load_json_file(META_STORIES_DIR / f"{story_id}.json")
    if source is None:
        print(f"Error: Meta story not found: {story_id}")
        return False

    status = check_meta_story_translation(story_id, target_lang)
    if not force and all(value == "current" for value in status.values()):
        if verbose:
            print(f"  Translation up to date for {story_id} (use --force to redo)")
        return True

    translated = translate_meta_story(source, target_lang, client, model, verbose)
    if translated is None:
        return False

    target_path = META_STORIES_DIR / target_lang / f"{story_id}.json"
    if not save_json_file(translated, target_path):
        return False
    if verbose:
        print(f"  ✓ Meta story translated: {target_path}")

    return update_language_meta_registry(story_id, translated, target_lang, verbose)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Translate meta stories to a target language using OpenAI API"
    )
    parser.add_argument(
        "story_id",
        nargs="?",
        help="Meta story ID (e.g., 'computing_pioneers'); omit with --all",
    )
    parser.add_argument(
        "--all", action="store_true", help="Translate all meta stories"
    )
    parser.add_argument(
        "--target-lang",
        required=True,
        help="Target language code (e.g., 'de', 'fr', 'es')",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-translate even if the translation is current",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"OpenAI model to use (default: {DEFAULT_MODEL})",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    args = parser.parse_args()

    if not args.all and not args.story_id:
        parser.error("provide a story_id or --all")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY environment variable not set")
        return 1
    client = OpenAI(api_key=api_key)

    story_ids = list_meta_story_ids() if args.all else [args.story_id]
    lang_name = LANGUAGE_NAMES.get(args.target_lang, args.target_lang)

    failures = 0
    for story_id in story_ids:
        print(f"Translating meta story '{story_id}' to {lang_name}...")
        if not translate_meta_story_data(
            story_id,
            args.target_lang,
            client,
            model=args.model,
            force=args.force,
            verbose=args.verbose,
        ):
            failures += 1
            print(f"  ✗ Failed: {story_id}")

    if failures:
        print(f"\n✗ {failures} meta story translation(s) failed")
        return 1
    print("\n✓ Meta story translations complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
