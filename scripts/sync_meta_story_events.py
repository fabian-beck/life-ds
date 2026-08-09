#!/usr/bin/env python3
"""Incrementally reconcile a person's events referenced by meta stories.

Meta stories deliberately keep only a small, curated subset of a person's life
events.  Regenerating a person can move those events to different array indexes,
so rebuilding the whole meta story is both expensive and destructive.  This
module updates only the stored event references and leaves chapters, historical
context, and thematic explanations untouched.
"""

import argparse
import json
import re
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils.json_io import write_json

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
META_STORIES_DIR = DATA_DIR / "meta_stories"


def _normalize(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def _event_snapshot(reference: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "date": reference.get("event_date", ""),
        "date_precision": reference.get("event_date_precision", "year"),
        "title": reference.get("event_title", ""),
    }


def _resolve_old_event(
    reference: Dict[str, Any], old_events: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Resolve a reference against the pre-update data, tolerating stale indexes."""
    index = reference.get("event_index")
    if isinstance(index, int) and 0 <= index < len(old_events):
        indexed = old_events[index]
        same_title = _normalize(indexed.get("title")) == _normalize(
            reference.get("event_title")
        )
        same_date = indexed.get("date") == reference.get("event_date")
        if same_title or same_date:
            return indexed

    title = _normalize(reference.get("event_title"))
    date = reference.get("event_date")
    matches = [
        event
        for event in old_events
        if _normalize(event.get("title")) == title and event.get("date") == date
    ]
    return matches[0] if len(matches) == 1 else _event_snapshot(reference)


def _find_new_event(
    old_event: Dict[str, Any], new_events: List[Dict[str, Any]]
) -> Optional[int]:
    """Find the same semantic event after regeneration, conservatively."""
    old_id = old_event.get("id")
    if old_id:
        matches = [i for i, event in enumerate(new_events) if event.get("id") == old_id]
        if len(matches) == 1:
            return matches[0]

    old_title = _normalize(old_event.get("title"))
    old_date = old_event.get("date")

    exact = [
        i
        for i, event in enumerate(new_events)
        if _normalize(event.get("title")) == old_title and event.get("date") == old_date
    ]
    if len(exact) == 1:
        return exact[0]

    same_title = [
        i
        for i, event in enumerate(new_events)
        if old_title and _normalize(event.get("title")) == old_title
    ]
    if len(same_title) == 1:
        return same_title[0]

    same_date = [
        i
        for i, event in enumerate(new_events)
        if old_date and event.get("date") == old_date
    ]
    if len(same_date) == 1:
        return same_date[0]

    # This covers modest title rewrites while avoiding guesses for deleted events.
    scored: List[Tuple[float, int]] = []
    if old_title:
        for i, event in enumerate(new_events):
            title = _normalize(event.get("title"))
            score = SequenceMatcher(None, old_title, title).ratio()
            if old_date and event.get("date") == old_date:
                score += 0.1
            scored.append((score, i))
    scored.sort(reverse=True)
    if scored and scored[0][0] >= 0.82:
        if len(scored) == 1 or scored[0][0] - scored[1][0] >= 0.08:
            return scored[0][1]
    return None


def _load(path: Path) -> Optional[Dict[str, Any]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _translation_fingerprint(detail: Dict[str, Any]) -> str:
    """Match the canonical fingerprint used by check_meta_story_translation()."""
    from translate_person import compute_fingerprint, extract_meta_story_translatables

    return compute_fingerprint(extract_meta_story_translatables(detail))


def _touch_registry(data_dir: Path, story_ids: set, language: str = "") -> None:
    path = data_dir / (
        f"meta_stories_{language}.json" if language else "meta_stories.json"
    )
    registry = _load(path)
    if registry is None:
        return
    changed = False
    now = datetime.now().astimezone().isoformat()
    for entry in registry.get("meta_stories", []) or []:
        if entry.get("id") in story_ids:
            entry["lastUpdated"] = now
            changed = True
    if changed:
        write_json(path, registry)


def _update_detail(
    detail: Dict[str, Any],
    person_id: str,
    mapping: Dict[int, Optional[int]],
    new_events: List[Dict[str, Any]],
    title_events: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[int, int]:
    updated = 0
    removed = 0
    title_events = title_events or new_events

    for chapter in detail.get("chapters", []) or []:
        references = chapter.get("person_events") or []
        kept = []
        for reference in references:
            if reference.get("person_id") != person_id:
                kept.append(reference)
                continue

            old_index = reference.get("event_index")
            new_index = mapping.get(old_index) if isinstance(old_index, int) else None
            if new_index is None or not 0 <= new_index < len(new_events):
                removed += 1
                continue

            event = new_events[new_index]
            title_event = (
                title_events[new_index] if new_index < len(title_events) else event
            )
            replacements = {
                "event_index": new_index,
                "event_date": event.get("date", ""),
                "event_date_precision": event.get("date_precision", "year"),
                "event_title": title_event.get("title", event.get("title", "")),
            }
            if any(reference.get(key) != value for key, value in replacements.items()):
                reference.update(replacements)
                updated += 1
            kept.append(reference)
        chapter["person_events"] = kept

    if updated or removed:
        meta = detail.get("meta_story")
        if isinstance(meta, dict):
            meta["lastUpdated"] = datetime.now().astimezone().isoformat()
    return updated, removed


def sync_meta_story_events(
    person_id: str,
    *,
    old_person_data: Optional[Dict[str, Any]] = None,
    new_person_data: Optional[Dict[str, Any]] = None,
    data_dir: Path = DATA_DIR,
    verbose: bool = False,
) -> Dict[str, int]:
    """Update only meta-story event references affected by one person update."""
    people_dir = data_dir / "people"
    meta_dir = data_dir / "meta_stories"
    if new_person_data is None:
        new_person_data = _load(people_dir / person_id / "life_events.json")
    if new_person_data is None:
        raise FileNotFoundError(f"No life events found for '{person_id}'")

    old_events = (old_person_data or {}).get("events") or []
    new_events = new_person_data.get("events") or []
    mapping: Dict[int, Optional[int]] = {}

    # Build the mapping from English references. A reference snapshot is enough
    # when the caller no longer has the pre-update person document.
    english_paths = sorted(meta_dir.glob("*.json"))
    for path in english_paths:
        detail = _load(path) or {}
        for chapter in detail.get("chapters", []) or []:
            for reference in chapter.get("person_events", []) or []:
                if reference.get("person_id") != person_id:
                    continue
                old_index = reference.get("event_index")
                if not isinstance(old_index, int) or old_index in mapping:
                    continue
                old_event = _resolve_old_event(reference, old_events)
                mapping[old_index] = _find_new_event(old_event, new_events)

    report = {"stories": 0, "files": 0, "updated": 0, "removed": 0}
    affected_story_ids = set()
    changed_story_ids = set()

    for path in english_paths:
        english_detail = _load(path)
        if english_detail is None:
            continue
        if any(
            event.get("person_id") == person_id
            for chapter in (english_detail.get("chapters") or [])
            for event in (chapter.get("person_events") or [])
        ):
            affected_story_ids.add(path.stem)
        updated, removed = _update_detail(
            english_detail, person_id, mapping, new_events, new_events
        )
        if updated or removed:
            write_json(path, english_detail)
            changed_story_ids.add(path.stem)
            report["files"] += 1
            report["updated"] += updated
            report["removed"] += removed
            if verbose:
                print(f"  Updated {path.relative_to(data_dir)}")

    _touch_registry(data_dir, changed_story_ids)

    # Apply identical index/date changes to every existing language version.
    for language_dir in sorted(path for path in meta_dir.iterdir() if path.is_dir()):
        translated_person = _load(
            people_dir / person_id / language_dir.name / "life_events.json"
        )
        translated_events = (translated_person or {}).get("events") or new_events
        localized_changes = set()
        for story_id in affected_story_ids:
            path = language_dir / f"{story_id}.json"
            localized_detail = _load(path)
            if localized_detail is None:
                continue
            updated, removed = _update_detail(
                localized_detail, person_id, mapping, new_events, translated_events
            )
            fingerprint_changed = False
            if translated_person and isinstance(
                localized_detail.get("translation"), dict
            ):
                source = _load(meta_dir / f"{story_id}.json")
                if source is not None:
                    fingerprint = _translation_fingerprint(source)
                    if (
                        localized_detail["translation"].get("source_fingerprint")
                        != fingerprint
                    ):
                        localized_detail["translation"][
                            "source_fingerprint"
                        ] = fingerprint
                        fingerprint_changed = True
            if updated or removed or fingerprint_changed:
                write_json(path, localized_detail)
                localized_changes.add(story_id)
                changed_story_ids.add(story_id)
                report["files"] += 1
                report["updated"] += updated
                report["removed"] += removed
                if verbose:
                    print(f"  Updated {path.relative_to(data_dir)}")
        _touch_registry(data_dir, localized_changes, language_dir.name)

    report["stories"] = len(changed_story_ids)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Incrementally sync a person's event references in meta stories."
    )
    parser.add_argument("person_id", help="Person ID, e.g. ada_lovelace")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    report = sync_meta_story_events(args.person_id, verbose=args.verbose)
    print(
        f"Synced {report['stories']} meta stories: "
        f"{report['updated']} references updated, {report['removed']} removed."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
