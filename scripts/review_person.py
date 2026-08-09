#!/usr/bin/env python3
"""
Review and improve generated person data.

This script acts as a constructive critic to review life events, ego network,
and visual style data, proposing improvements for readability, accuracy, and
storytelling quality.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional, cast

from openai import OpenAI, APIStatusError
from pydantic import ValidationError

# Add parent directory to path for imports. Everything below resolves through
# it, so these imports have to follow the insert — hence the E402 waivers.
sys.path.insert(0, str(Path(__file__).parent))

from config import (  # noqa: E402
    DEFAULT_MODEL,
    DEFAULT_REASONING_EFFORT,
    LOW_REASONING_EFFORT,
)
from generate_person_events import enrich_event_coordinates_v2  # noqa: E402
from utils.review_models import (  # noqa: E402
    CombinedReviewOutput,
    StyleReviewOutput,
    EventsChanges,
    NetworkChanges,
)
from utils.review_prompts import (  # noqa: E402
    get_combined_review_prompt,
    get_style_review_prompt,
)
from utils.review_helpers import (  # noqa: E402
    apply_event_changes,
    apply_network_changes,
    apply_style_changes,
)
from utils.wikipedia_cache import (  # noqa: E402
    get_cached_wikipedia_page,
    get_cache_dir,
)


def get_cached_related_articles(person_id: str) -> Optional[List[Dict[str, str]]]:
    """Load cached related Wikipedia articles."""
    cache_dir = get_cache_dir(person_id)
    related_path = cache_dir / "related_articles.json"

    if not related_path.exists():
        return None

    with open(related_path, "r", encoding="utf-8") as f:
        return cast(Optional[List[Dict[str, str]]], json.load(f))


# Constants
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
PERSONS_REGISTER = DATA_DIR / "persons.json"
STYLES_REGISTER = DATA_DIR / "person_styles.json"
PEOPLE_DIR = DATA_DIR / "people"


def resolve_person_id(person_name_or_id: str) -> Optional[str]:
    """
    Resolve person name or ID to canonical person_id.

    Args:
        person_name_or_id: Person name or ID

    Returns:
        Canonical person_id or None if not found
    """
    person_name_or_id_normalized = (
        person_name_or_id.lower().replace(" ", "_").replace("-", "_")
    )

    # Check if it's already a valid person_id
    person_dir = PEOPLE_DIR / person_name_or_id_normalized
    if person_dir.exists():
        return person_name_or_id_normalized

    # Try to find in persons.json by name
    try:
        with open(PERSONS_REGISTER, "r", encoding="utf-8") as f:
            persons = json.load(f)

        for person in persons.get("people", []):
            if person.get("id") == person_name_or_id_normalized:
                return person_name_or_id_normalized
            if person.get("name", "").lower().replace(
                "_", " "
            ) == person_name_or_id.lower().replace("_", " "):
                return cast(Optional[str], person.get("id"))
    except Exception:
        pass

    return None


def load_person_data(person_id: str) -> Dict[str, Any]:
    """
    Load all person data files.

    Args:
        person_id: Person identifier

    Returns:
        Dictionary with events, network, style, cache data

    Raises:
        FileNotFoundError: If required files don't exist
    """
    person_dir = PEOPLE_DIR / person_id

    # Load life events
    events_path = person_dir / "life_events.json"
    if not events_path.exists():
        raise FileNotFoundError(f"Life events not found: {events_path}")

    with open(events_path, "r", encoding="utf-8") as f:
        events_data = json.load(f)

    # Load ego network
    network_path = person_dir / "ego_network.json"
    network_data = None
    if network_path.exists():
        with open(network_path, "r", encoding="utf-8") as f:
            network_data = json.load(f)

    # Load style
    style_data = None
    if STYLES_REGISTER.exists():
        with open(STYLES_REGISTER, "r", encoding="utf-8") as f:
            styles = json.load(f)
            style_data = styles.get(person_id)

    # Load cached Wikipedia content
    # Note: We pass empty title since we're always using cache (use_cache=True by default)
    wikipedia_page = get_cached_wikipedia_page(person_id, title="", use_cache=True)
    related_articles = get_cached_related_articles(person_id)

    return {
        "events": events_data,
        "network": network_data,
        "style": style_data,
        "wikipedia_page": wikipedia_page,
        "related_articles": related_articles or [],
        "person_id": person_id,
    }


def validate_data(person_data: Dict[str, Any]) -> List[str]:
    """
    Perform pre-review validation checks.

    Args:
        person_data: Loaded person data

    Returns:
        List of critical error messages (empty if all OK)
    """
    errors = []
    events_data = person_data.get("events", {})

    # Only check for truly critical issues that would prevent review
    if not events_data.get("events"):
        errors.append("No events found in life_events.json - cannot review")

    # Note: We don't check for person_metadata or orphaned annotations
    # as the review process can actually fix these issues

    return errors


def review_combined(
    events_data: Dict[str, Any],
    network_data: Optional[Dict[str, Any]],
    wikipedia_page: Dict[str, Any],
    related_articles: List[Dict[str, str]],
    model: str,
    reasoning_effort: str,
) -> CombinedReviewOutput:
    """
    Review both life events and ego network together with AI.

    Args:
        events_data: Life events data
        network_data: Ego network data (can be None)
        wikipedia_page: Cached Wikipedia page
        related_articles: Related Wikipedia articles
        model: AI model to use
        reasoning_effort: Reasoning effort level

    Returns:
        CombinedReviewOutput with proposed changes for both
    """
    print(
        f"  Reviewing life events and network (model: {model}, reasoning: {reasoning_effort})..."
    )

    client = OpenAI()

    # Get Wikipedia content
    wiki_text = wikipedia_page.get("extract", "")

    # Build combined prompt
    prompt = get_combined_review_prompt(
        events_data, network_data or {}, wiki_text, related_articles
    )

    try:
        # Call AI with structured output
        response = client.responses.parse(
            model=model,
            reasoning=cast(Any, {"effort": reasoning_effort}),
            input=[{"role": "user", "content": prompt}],
            text_format=CombinedReviewOutput,
        )

        if response.status != "completed" or not response.output_parsed:
            raise RuntimeError(
                "Failed to parse structured output from model (Combined review)"
            )

        review_output = response.output_parsed
        print(f"  * Review complete: {review_output.change_summary}")

        return review_output

    except APIStatusError as e:
        print(f"  X API error during combined review: {e}")
        raise
    except ValidationError as e:
        print(f"  X Validation error in combined review output: {e}")
        raise


def review_style(
    style_data: Dict[str, Any],
    events_data: Dict[str, Any],
    model: str,
    reasoning_effort: str,
) -> StyleReviewOutput:
    """
    Review visual style with AI.

    Args:
        style_data: Style data
        events_data: Life events data for context
        model: AI model to use
        reasoning_effort: Reasoning effort level

    Returns:
        StyleReviewOutput with proposed changes
    """
    print(
        f"  Reviewing visual style (model: {model}, reasoning: {reasoning_effort})..."
    )

    client = OpenAI()

    prompt = get_style_review_prompt(style_data, events_data)

    try:
        response = client.responses.parse(
            model=model,
            reasoning=cast(Any, {"effort": reasoning_effort}),
            input=[{"role": "user", "content": prompt}],
            text_format=StyleReviewOutput,
        )

        if response.status != "completed" or not response.output_parsed:
            raise RuntimeError(
                "Failed to parse structured output from model (Style review)"
            )

        review_output = response.output_parsed
        print(f"  * Style review complete: {review_output.change_summary}")

        return review_output

    except APIStatusError as e:
        print(f"  X API error during style review: {e}")
        raise
    except ValidationError as e:
        print(f"  X Validation error in style review output: {e}")
        raise


def review_person_data(
    person_name_or_id: str,
    aspect: str = "all",
    dry_run: bool = False,
    min_confidence: int = 4,
    model: str = DEFAULT_MODEL,
    reasoning_effort: Optional[str] = None,
    verbose: bool = False,
) -> bool:
    """
    Main review function for person data.

    Args:
        person_name_or_id: Person name or ID
        aspect: Which aspect to review (events/network/style/all)
        dry_run: Show changes without applying
        min_confidence: Lowest confidence (1-5) a change may have to be applied
        model: AI model to use
        reasoning_effort: Reasoning effort override
        verbose: Enable verbose logging

    Returns:
        True if successful, False otherwise
    """
    print(f"\n{'='*60}")
    print(f"REVIEWING PERSON DATA: {person_name_or_id}")
    print(f"{'='*60}\n")

    # Resolve person ID
    person_id = resolve_person_id(person_name_or_id)
    if not person_id:
        print(f"X Person not found: {person_name_or_id}")
        return False

    print(f"[Step 1/6] Resolved person ID: {person_id}")

    # Load data
    print("[Step 2/6] Loading person data...")
    try:
        person_data = load_person_data(person_id)
    except FileNotFoundError as e:
        print(f"X {e}")
        return False

    # Validate
    print("[Step 3/6] Validating data...")
    errors = validate_data(person_data)
    if errors:
        print("X Critical errors found:")
        for error in errors:
            print(f"  - {error}")
        print("\nPlease fix these errors before reviewing.")
        return False

    print("  * Validation passed")

    # Determine reasoning effort
    combined_reasoning = (
        reasoning_effort or DEFAULT_REASONING_EFFORT
    )  # Use configured default for combined review
    style_reasoning = (
        reasoning_effort or LOW_REASONING_EFFORT
    )  # Use low effort for style review

    # Review phases
    combined_review = None
    style_review = None

    # Phase 1: Combined Events + Network Review
    if aspect in ["all", "events", "network"]:
        print("\n[Step 4/5] PHASE 1: Reviewing life events and network together...")
        try:
            combined_review = review_combined(
                person_data["events"],
                person_data["network"],
                person_data["wikipedia_page"],
                person_data["related_articles"],
                model,
                combined_reasoning,
            )
        except Exception as e:
            print(f"X Combined review failed: {e}")
            if verbose:
                import traceback

                traceback.print_exc()
            return False

    # Phase 2: Style
    if aspect in ["all", "style"] and person_data["style"]:
        print("\n[Step 5/5] PHASE 2: Reviewing visual style...")
        try:
            style_review = review_style(
                person_data["style"], person_data["events"], model, style_reasoning
            )
        except Exception as e:
            print(f"X Style review failed: {e}")
            if verbose:
                import traceback

                traceback.print_exc()
            return False

    # Create default empty reviews if not run
    if not combined_review:
        combined_review = CombinedReviewOutput(
            overall_assessment="Not reviewed",
            events_changes=EventsChanges(),
            network_changes=NetworkChanges(),
            change_summary="No changes",
        )

    if not style_review and person_data["style"]:
        from utils.review_models import StyleChanges

        style_review = StyleReviewOutput(
            overall_assessment="Not reviewed",
            color_palette_feedback="",
            pattern_feedback="",
            font_feedback="",
            proposed_changes=StyleChanges(confidence=1, rationale=""),
            change_summary="No changes",
        )
    elif not style_review:
        from utils.review_models import StyleChanges

        style_review = StyleReviewOutput(
            overall_assessment="No style data",
            color_palette_feedback="",
            pattern_feedback="",
            font_feedback="",
            proposed_changes=StyleChanges(confidence=1, rationale=""),
            change_summary="No changes",
        )

    # Apply changes
    print(f"\n[Phase 3] Applying changes (min confidence: {min_confidence})...")

    events_applied = 0
    events_skipped = 0
    network_applied = 0
    network_skipped = 0
    style_applied = 0
    style_skipped = 0

    updated_events = person_data["events"]
    updated_network = person_data["network"]
    updated_style = person_data["style"]

    if aspect in ["all", "events", "network"]:
        # Apply events changes from combined review
        updated_events, events_applied, events_skipped = apply_event_changes(
            person_data["events"], combined_review.events_changes, min_confidence
        )
        print(f"  Events: {events_applied} applied, {events_skipped} skipped")

        # Reviewer-supplied locations arrive as names only, so resolve them
        # through the same geocoder the generation pipeline uses.
        if any(
            change.new_locations is not None
            for change in combined_review.events_changes.events
            if change.confidence >= min_confidence
        ):
            updated_events, geocoded = enrich_event_coordinates_v2(updated_events)
            print(f"  Locations: {geocoded} geocoded")

        # Apply network changes from combined review
        if person_data["network"]:
            updated_network, network_applied, network_skipped = apply_network_changes(
                person_data["network"], combined_review.network_changes, min_confidence
            )
            print(f"  Network: {network_applied} applied, {network_skipped} skipped")

    if aspect in ["all", "style"] and person_data["style"]:
        updated_style, style_applied, style_skipped = apply_style_changes(
            person_data["style"], style_review.proposed_changes, min_confidence
        )
        print(f"  Style: {style_applied} applied, {style_skipped} skipped")

    # Save or display
    if dry_run:
        print("\n" + "=" * 60)
        print("DRY RUN - Changes summary:")
        print("=" * 60)
        print(
            f"  Events: {events_applied} changes would be applied, {events_skipped} skipped"
        )
        print(
            f"  Network: {network_applied} changes would be applied, {network_skipped} skipped"
        )
        print(
            f"  Style: {style_applied} changes would be applied, {style_skipped} skipped"
        )
        # Name each proposed change: a dry run whose output is three counts
        # cannot be reviewed, and reviewing is the mode's whole point.
        for change in combined_review.events_changes.events:
            fields = ", ".join(
                f"{name.removeprefix('new_')}={value!r}"
                for name, value in change.model_dump(exclude_none=True).items()
                if name.startswith("new_")
            )
            if fields:
                print(
                    f"  event {change.event_index} "
                    f"[confidence {change.confidence}]: {fields}"
                )
        for chapter_change in combined_review.events_changes.chapters:
            if chapter_change.new_headline:
                print(
                    f"  chapter {chapter_change.chapter_id} "
                    f"[confidence {chapter_change.confidence}]: "
                    f"headline={chapter_change.new_headline!r}"
                )
        for connection in combined_review.network_changes.connections:
            fields = ", ".join(
                f"{name.removeprefix('new_')}={value!r}"
                for name, value in connection.model_dump(exclude_none=True).items()
                if name.startswith("new_")
            )
            if fields:
                print(
                    f"  network {connection.person_name!r} "
                    f"[confidence {connection.confidence}]: {fields}"
                )
        print("\n* Dry run complete. No files modified.")
        return True

    # Save files
    print("\n[Phase 4] Saving changes...")

    person_dir = PEOPLE_DIR / person_id

    if aspect in ["all", "events"]:
        events_path = person_dir / "life_events.json"
        with open(events_path, "w", encoding="utf-8") as f:
            json.dump(updated_events, f, indent=2, ensure_ascii=False)
        print(f"  * Updated {events_path.name}")
        try:
            from sync_meta_story_events import sync_meta_story_events

            sync_meta_story_events(
                person_id,
                old_person_data=person_data["events"],
                new_person_data=updated_events,
            )
        except Exception as error:
            print(f"  ! Could not sync meta-story events: {error}")

    if aspect in ["all", "network"] and updated_network:
        network_path = person_dir / "ego_network.json"
        with open(network_path, "w", encoding="utf-8") as f:
            json.dump(updated_network, f, indent=2, ensure_ascii=False)
        print(f"  * Updated {network_path.name}")

    if aspect in ["all", "style"] and updated_style:
        # Update style in styles register
        with open(STYLES_REGISTER, "r", encoding="utf-8") as f:
            styles = json.load(f)

        styles[person_id] = updated_style

        with open(STYLES_REGISTER, "w", encoding="utf-8") as f:
            json.dump(styles, f, indent=2, ensure_ascii=False)
        print(f"  * Updated {STYLES_REGISTER.name}")

    total_applied = events_applied + network_applied + style_applied
    total_skipped = events_skipped + network_skipped + style_skipped

    print(f"\n* Review complete for {person_id}!")
    print(f"  Total changes applied: {total_applied}")
    print(f"  Changes skipped: {total_skipped}")

    return True


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Review and improve generated person data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python review_person.py "Alan Turing"
  python review_person.py "alan_turing" --aspect events
  python review_person.py "ada_lovelace" --dry-run
  python review_person.py "grace_hopper" --min-confidence 3
        """,
    )

    parser.add_argument("person_name_or_id", help="Person name or ID to review")

    parser.add_argument(
        "--aspect",
        choices=["all", "events", "network", "style"],
        default="all",
        help="Which aspect to review (default: all)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show proposed changes without applying them",
    )

    parser.add_argument(
        "--min-confidence",
        type=int,
        choices=range(1, 6),
        default=4,
        help="Lowest confidence a change may have to be applied (default: 4)",
    )

    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"OpenAI model to use (default: {DEFAULT_MODEL})",
    )

    parser.add_argument(
        "--reasoning-effort",
        choices=["low", "medium", "high"],
        help="Override default reasoning effort levels",
    )

    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    success = review_person_data(
        args.person_name_or_id,
        aspect=args.aspect,
        dry_run=args.dry_run,
        min_confidence=args.min_confidence,
        model=args.model,
        reasoning_effort=args.reasoning_effort,
        verbose=args.verbose,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
