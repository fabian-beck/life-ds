"""
Helper functions for person data review system.

Utilities for applying changes, creating backups, generating logs,
and preserving JSON structure.
"""

import json
import os
import shutil
from datetime import datetime
from typing import Dict, Any, Tuple

from .review_models import EventsChanges, NetworkChanges, StyleChanges


def create_backup(file_path: str) -> str:
    """
    Create timestamped backup of a file.

    Args:
        file_path: Path to file to backup

    Returns:
        Path to backup file
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Cannot backup non-existent file: {file_path}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{file_path}.backup_{timestamp}"

    shutil.copy2(file_path, backup_path)
    return backup_path


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
                    connection["relationship_type"] = conn_change.new_relationship_type
                    applied += 1

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


def apply_style_changes(
    style_data: Dict[str, Any], changes: StyleChanges, min_confidence: int = 4
) -> Tuple[Dict[str, Any], int, int]:
    """
    Apply changes to style data, preserving JSON structure.

    Args:
        style_data: Original style data
        changes: Proposed changes
        min_confidence: Minimum confidence to apply

    Returns:
        Tuple of (updated_data, applied_count, skipped_count)
    """
    if changes.confidence < min_confidence:
        return style_data, 0, 1

    updated_data = json.loads(json.dumps(style_data))  # Deep copy
    applied = 0

    if changes.new_primary:
        updated_data["primary"] = changes.new_primary
        applied += 1

    if changes.new_secondary:
        updated_data["secondary"] = changes.new_secondary
        applied += 1

    if changes.new_background:
        updated_data["background"] = changes.new_background
        applied += 1

    if changes.new_pattern_svg:
        updated_data["background_pattern_svg"] = changes.new_pattern_svg
        applied += 1

    if changes.new_fonts:
        for key, value in changes.new_fonts.items():
            if key in updated_data:
                updated_data[key] = value
                applied += 1

    return updated_data, applied, 0
