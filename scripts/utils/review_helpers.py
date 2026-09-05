"""
Helper functions for person data review system.

Utilities for applying changes, generating logs, and preserving JSON
structure.
"""

import json
import re
from typing import Any, Dict, Tuple

from events.normalize import drop_repeated_annotations

from .relationship_vocabulary import normalize_relationship_type
from .review_models import EventsChanges, NetworkChanges


def apply_event_changes(
    events_data: Dict[str, Any], changes: EventsChanges, min_confidence: int = 4
) -> Tuple[Dict[str, Any], int, int]:
    """
    Apply changes to life events data, preserving JSON structure.

    Args:
        events_data: Original events data
        changes: Proposed changes
        min_confidence: Minimum confidence to apply (1-5)

    Returns:
        Tuple of (updated_data, applied_count, skipped_count)
    """
    updated_data = json.loads(json.dumps(events_data))  # Deep copy
    applied = 0
    skipped = 0

    # Apply event changes
    for event_change in changes.events:
        if event_change.confidence < min_confidence:
            skipped += 1
            continue

        event_idx = event_change.event_index
        if event_idx < 0 or event_idx >= len(updated_data.get("events", [])):
            continue

        event = updated_data["events"][event_idx]

        if event_change.new_title:
            event["title"] = event_change.new_title
            applied += 1

        if event_change.new_description:
            event["description"] = event_change.new_description
            applied += 1

        if event_change.new_date_end:
            # The span's end is the one date the reviewer may correct — the
            # Planck review saw a family-losses event whose prose reached
            # 1919 while its metadata ended in 1917 and could not fix it.
            # The anchor date stays untouchable, the precision is read off
            # the value instead of trusted, and an end before the anchor is
            # refused.
            end = event_change.new_date_end.strip()
            precision = {1: "year", 2: "month", 3: "day"}.get(len(end.split("-")))
            anchor = str(event.get("date") or "")
            padded_end = {4: end + "-12-31", 7: end + "-31"}.get(len(end), end)
            if (
                precision
                and re.fullmatch(r"\d{4}(-\d{2}){0,2}", end)
                and anchor
                and padded_end >= anchor[:10]
            ):
                event["date_end"] = end
                event["date_end_precision"] = precision
                applied += 1
            else:
                print(
                    f'  Skipping date_end "{end}" for event {event_idx}: '
                    "not a date after the event's own"
                )
                skipped += 1

        if event_change.new_impact is not None:
            # Only publication and invention classifications carry an impact
            # field; a stored block without one is stored without the key, so
            # dropping a content-only impact removes the key rather than
            # leaving a null behind.
            event_class = event.get("event_class")
            if isinstance(event_class, dict) and event_class.get("type") in (
                "publication",
                "invention",
            ):
                new_impact = event_change.new_impact.strip()
                if new_impact:
                    event_class["impact"] = new_impact
                else:
                    event_class.pop("impact", None)
                applied += 1
            else:
                print(
                    f"  Skipping impact for event {event_idx}: "
                    "no publication/invention classification"
                )
                skipped += 1

        if event_change.new_annotations:
            # Convert Pydantic models to dicts
            event["annotations"] = {
                term: (
                    {"explanation": ann.explanation, "wikipedia_url": ann.wikipedia_url}
                    if hasattr(ann, "explanation")
                    else ann
                )
                for term, ann in event_change.new_annotations.items()
            }
            applied += 1

        if event_change.new_involved_people is not None:
            event["involved_people"] = event_change.new_involved_people
            applied += 1

        if event_change.new_locations is not None:
            # Convert Pydantic models to dicts. The geocoding pass below fills
            # in the centroids the reviewer is not allowed to invent.
            event["locations"] = [
                loc.model_dump() if hasattr(loc, "model_dump") else loc
                for loc in event_change.new_locations
            ]
            applied += 1

        if event_change.new_event_type_icon:
            event["event_type_icon"] = event_change.new_event_type_icon
            applied += 1

    # Apply chapter changes
    for chapter_change in changes.chapters:
        if chapter_change.confidence < min_confidence:
            skipped += 1
            continue

        # Find chapter by ID
        for chapter in updated_data.get("chapters", []):
            if chapter.get("id") == chapter_change.chapter_id:
                if chapter_change.new_headline:
                    chapter["headline"] = chapter_change.new_headline
                    applied += 1
                break

    # Apply conclusion changes
    if changes.conclusion and (changes.conclusion_confidence or 5) >= min_confidence:
        updated_data["conclusion"] = changes.conclusion
        applied += 1
    elif changes.conclusion:
        skipped += 1

    # The reviewer is asked to annotate a term only where the story first
    # meets it, and this holds it to that the way generation does.
    drop_repeated_annotations(updated_data.get("events", []))

    return updated_data, applied, skipped


def apply_network_changes(
    network_data: Dict[str, Any], changes: NetworkChanges, min_confidence: int = 4
) -> Tuple[Dict[str, Any], int, int]:
    """
    Apply changes to ego network data, preserving JSON structure.

    Args:
        network_data: Original network data
        changes: Proposed changes
        min_confidence: Minimum confidence to apply

    Returns:
        Tuple of (updated_data, applied_count, skipped_count)
    """
    updated_data = json.loads(json.dumps(network_data))  # Deep copy
    applied = 0
    skipped = 0

    # Apply ego metadata changes
    if changes.ego:
        for key, value in changes.ego.model_dump(exclude_none=True).items():
            if key in updated_data.get("ego", {}):
                updated_data["ego"][key] = value
                applied += 1

    # Apply connection changes
    for conn_change in changes.connections:
        if conn_change.confidence < min_confidence:
            skipped += 1
            continue

        # Find connection by person_name
        for connection in updated_data.get("connections", []):
            if connection.get("person_name") == conn_change.person_name:
                if conn_change.new_relationship_description:
                    connection["relationship_description"] = (
                        conn_change.new_relationship_description
                    )
                    applied += 1

                if conn_change.new_relationship_type:
                    # The vocabulary is closed: a proposed type is folded onto
                    # it, and one that stays outside is skipped rather than
                    # let a review reopen the corpus to invented types.
                    new_type, known = normalize_relationship_type(
                        conn_change.new_relationship_type
                    )
                    if known:
                        connection["relationship_type"] = new_type
                        applied += 1
                    else:
                        print(
                            "  Skipping relationship type outside the vocabulary: "
                            f"{conn_change.new_relationship_type!r} "
                            f"({conn_change.person_name})"
                        )
                        skipped += 1

                if conn_change.new_metadata:
                    for key, value in conn_change.new_metadata.model_dump(
                        exclude_none=True
                    ).items():
                        if key in connection:
                            connection[key] = value
                            applied += 1
                break

    # Apply category summary changes
    for summary_change in changes.category_summaries:
        if summary_change.confidence < min_confidence:
            skipped += 1
            continue

        # Find category summary by relationship_type
        for summary in updated_data.get("category_summaries", []):
            if summary.get("relationship_type") == summary_change.relationship_type:
                summary["summary"] = summary_change.new_summary
                applied += 1
                break

    return updated_data, applied, skipped
