#!/usr/bin/env python3
"""
Generate meta-story datasets using a two-phase approach:
1. Phase 1: Story planning and person selection (1 AI call)
2. Phase 2: Event mapping (programmatic, no AI)

Meta-stories group multiple people around thematic topics with temporal chapters.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from openai import OpenAI, APIStatusError
from pydantic import BaseModel, Field

from config import DEFAULT_MODEL, DEFAULT_REASONING_EFFORT

# Constants
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
REGISTER_PATH = DATA_DIR / "persons.json"
PEOPLE_DIR = DATA_DIR / "people"
META_STORIES_DIR = DATA_DIR / "meta_stories"
META_STORIES_REGISTER = DATA_DIR / "meta_stories.json"


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class PersonReference(BaseModel):
    """Reference to a person in the registry with relevance note."""
    person_id: str = Field(description="Person ID from persons.json")
    relevance_note: str = Field(
        description="Brief note explaining why this person fits the topic (1 sentence)"
    )


class Subtopic(BaseModel):
    """A thematic subtopic organizing selected people."""
    id: str = Field(description="Unique identifier (snake_case)")
    title: str = Field(description="Subtopic name (2-5 words)")
    description: str = Field(
        description="Brief narrative explaining this subtopic (1-2 sentences)"
    )
    person_ids: List[str] = Field(
        description="Person IDs belonging to this subtopic (2-4 people per subtopic)"
    )


class TemporalChapter(BaseModel):
    """An era-based chapter showing concurrent activities."""
    id: str = Field(description="Unique identifier (snake_case)")
    title: str = Field(
        description="Era name with date range (e.g., 'Early Foundations (1900-1920)')"
    )
    date_start: str = Field(description="ISO-8601 date (year precision)")
    date_start_precision: str = Field(
        default="year", description="Always 'year' for chapters"
    )
    date_end: str = Field(description="ISO-8601 date (year precision)")
    date_end_precision: str = Field(
        default="year", description="Always 'year' for chapters"
    )
    bridge_statement: str = Field(
        description="Narrative hook setting the era's context (1-2 sentences, max 30 words)"
    )


class MissingPersonSuggestion(BaseModel):
    """Suggestion for a person not in the registry who would fit this topic."""
    name: str = Field(description="Full name of the suggested person")
    reason: str = Field(
        description="Brief explanation of why this person would fit the topic (1-2 sentences)"
    )
    role: str = Field(description="Primary role or contribution (e.g., 'mathematician', 'architect')")


class MetaStoryPlan(BaseModel):
    """Phase 1 output: Complete meta-story plan with selected people."""
    title: str = Field(description="Meta-story title (2-5 words)")
    tagline: str = Field(description="Short hook (3-10 words)")
    description: str = Field(
        description="Rich narrative overview (2-3 paragraphs) explaining the story's significance"
    )
    selected_people: List[PersonReference] = Field(
        description="All people who clearly fit this meta-story (no fixed number - select based on fit)",
        min_length=1
    )
    subtopics: List[Subtopic] = Field(
        description="2-4 thematic subtopics organizing the selected people",
        min_length=2,
        max_length=4
    )
    chapters: List[TemporalChapter] = Field(
        description="3-6 era-based chapters covering the time span",
        min_length=3,
        max_length=6
    )
    conclusion: str = Field(
        description="Overall narrative conclusion (2-3 sentences) tying the meta-story together"
    )
    missing_people_suggestions: Optional[List[MissingPersonSuggestion]] = Field(
        default=None,
        description="3-5 suggestions for people NOT in the registry who would strengthen this meta-story"
    )


class PersonEvent(BaseModel):
    """Reference to a specific event from a person's life_events.json."""
    person_id: str = Field(description="Person ID")
    event_date: str = Field(description="Event date (from life_events.json)")
    event_date_precision: str = Field(description="Date precision")
    event_title: str = Field(description="Event title (from life_events.json)")
    event_index: int = Field(description="Index in person's events array")


class ChapterWithEvents(TemporalChapter):
    """Chapter with mapped events from multiple people."""
    person_events: List[PersonEvent] = Field(
        description="Events from multiple people during this era"
    )


class MetaStory(BaseModel):
    """Complete meta-story with all metadata."""
    id: str = Field(description="Unique identifier (snake_case)")
    title: str
    tagline: str
    description: str
    person_ids: List[str] = Field(description="All person IDs in this story")
    date_range_start: str = Field(description="Earliest event date")
    date_range_end: str = Field(description="Latest event date")
    lastUpdated: str = Field(description="ISO-8601 timestamp")


class MetaStoryDataset(BaseModel):
    """Top-level dataset structure for meta-story JSON."""
    dataset: str = Field(default="meta_story")
    created_on: str = Field(description="ISO-8601 timestamp")
    meta_story: MetaStory
    subtopics: List[Subtopic]
    chapters: List[ChapterWithEvents]
    conclusion: str


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def slugify(title: str) -> str:
    """Convert meta-story title to slug (story_id)."""
    # Remove parenthetical content and special chars
    title = title.split("(")[0].strip()
    slug = re.sub(r"[^a-z0-9]+", "_", title.lower())
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug.strip("_")


def load_persons_registry() -> Dict[str, Any]:
    """Load the persons.json registry."""
    with open(REGISTER_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_person_life_events(person_id: str) -> Optional[Dict[str, Any]]:
    """Load a person's life_events.json."""
    events_path = PEOPLE_DIR / person_id / "life_events.json"
    if not events_path.exists():
        return None
    with open(events_path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_person_exists(person_id: str, registry: Dict[str, Any]) -> bool:
    """Check if person_id exists in registry."""
    people = registry.get("people", [])
    return any(p.get("id") == person_id for p in people)


def parse_event_date(event: Dict[str, Any]) -> Optional[int]:
    """Extract year from event date for sorting."""
    date_str = event.get("date", "")
    if not date_str:
        return None
    try:
        # Extract year from YYYY, YYYY-MM, or YYYY-MM-DD
        return int(date_str.split("-")[0])
    except (ValueError, IndexError):
        return None


# ============================================================================
# PHASE 1: STORY PLANNING
# ============================================================================

def phase1_story_planning(
    topic_title: str,
    registry: Dict[str, Any],
    client: OpenAI,
    model: str,
    manual_person_ids: Optional[List[str]] = None,
    verbose: bool = False
) -> Optional[MetaStoryPlan]:
    """
    Phase 1: AI-driven story planning and person selection.

    Args:
        topic_title: The thematic topic (e.g., "Computing Pioneers")
        registry: Full persons.json registry
        client: OpenAI client
        model: Model to use
        manual_person_ids: If provided, skip AI person selection
        verbose: Enable logging

    Returns:
        MetaStoryPlan object or None on failure
    """
    if verbose:
        print(f"\n=== PHASE 1: Story Planning ===")
        print(f"Topic: {topic_title}")

    # Build registry summary for AI
    people_summary = []
    for person in registry.get("people", []):
        summary_text = person.get("summary", "")
        # Truncate summaries for token efficiency, preserving sentence boundaries
        if len(summary_text) > 200:
            truncated = summary_text[:197]
            # Try to break at sentence boundary to preserve context
            last_period = truncated.rfind('.')
            if last_period > 100:  # Keep at least half
                summary_text = truncated[:last_period + 1]
            else:
                summary_text = truncated + "..."

        people_summary.append({
            "id": person.get("id"),
            "name": person.get("name"),
            "primaryRoles": person.get("primaryRoles", []),
            "birthDate": person.get("birthDate"),
            "deathDate": person.get("deathDate"),
            "summary": summary_text
        })

    if manual_person_ids:
        # Manual mode: AI only creates structure, uses provided people
        relevant_people = [p for p in people_summary if p["id"] in manual_person_ids]

        prompt = f"""Create a meta-story structure for the topic "{topic_title}".

You MUST use these specific people (already selected):
{json.dumps(manual_person_ids, indent=2)}

Your task:
1. Create a compelling title, tagline, and description for this meta-story
2. Organize the people into 2-4 thematic subtopics (based on their roles/contributions)
3. Design 3-6 temporal chapters covering their combined lifespans
4. Write a conclusion statement tying the story together

Person details:
{json.dumps(relevant_people, indent=2)}

IMPORTANT RULES:

TITLE & NARRATIVE:
- Title should be compelling and thematic (2-5 words)
- Tagline should be a short hook (3-10 words)
- Description should be rich narrative (2-3 paragraphs) explaining significance
- Write for a general educated audience, not just academics

SUBTOPICS (2-4):
- Reflect meaningful thematic groupings (e.g., "Theoretical Foundations", "Wartime Applications")
- NOT just job title duplicates (avoid "Mathematicians", "Scientists", "Writers")
- Should tell a story within the story (e.g., "Breaking the Unbreakable", "From Theory to Practice")
- 2-4 people per subtopic is ideal
- OK to have overlapping membership (person can appear in multiple subtopics)

CHAPTERS (3-6):
- Era-based with clear date ranges (year precision only)
- Title format: "Era Name (YYYY-YYYY)" (e.g., "Early Foundations (1900-1920)")
- Chapters should be chronological and non-overlapping
- Bridge statement: narrative hook, not summary (1-2 sentences, max 30 words)
- Each bridge should create anticipation for what happened during that era

CONCLUSION:
- Synthesize the overall narrative (2-3 sentences)
- Capture the collective impact/legacy
- Should feel like the closing paragraph of a compelling essay

MISSING PEOPLE SUGGESTIONS:
- After creating the meta-story, suggest 3-5 notable people NOT in the registry who would strengthen this narrative
- For each suggestion: provide name, reason (why they'd fit), and role
- Focus on people who would fill gaps or add important perspectives
- These are recommendations for future dataset expansion

Use ALL provided person IDs (no more, no less).
Provide a relevance_note for each person explaining their fit.
"""
    else:
        # Automatic mode: AI selects people + creates structure
        prompt = f"""Create a meta-story for the topic "{topic_title}" by selecting ALL people from the registry who clearly fit this topic.

Available people:
{json.dumps(people_summary, indent=2)}

Your task:
1. SELECT ALL people who clearly and directly fit this topic
   - Do NOT limit yourself to a fixed number - select everyone who truly belongs
   - Focus on thematic coherence (shared profession, movement, domain, or era)
   - Aim for diversity in time period and contribution type when multiple candidates exist
   - Provide brief relevance note for each selected person
2. Create compelling title, tagline, and description
3. Organize selected people into 2-4 thematic subtopics
4. Design 3-6 temporal chapters covering their combined lifespans
5. Write conclusion statement

SELECTION CRITERIA - BE THOUGHTFUL:
- Select people whose primaryRoles OR summary CLEARLY and DIRECTLY fit the topic
- When a person has multiple roles, evaluate ALL roles for thematic fit
  * Example: "artist, architect, environmentalist" fits architecture topics if summary confirms architectural work
  * Role order does NOT indicate importance - evaluate based on substantive contribution
- Each person must have strong thematic relevance, not just superficial keyword overlap
- A tangential connection is NOT enough - the person must have made substantial contributions
- Do NOT artificially limit selections to hit a target number - include ALL who clearly fit
- PREFER diversity in approach over perfect thematic overlap
  * Include people with DIFFERENT perspectives on the same theme (e.g., structural vs. aesthetic approaches to organic architecture)
  * Mix of well-known pioneers and lesser-known innovators
  * Variety in time periods for richer cross-connections
- Each person should bring something unique and substantial to the narrative
- REJECT people who are only marginally related or require stretching the topic definition
- When in doubt: if someone is widely recognized for work central to the topic, INCLUDE them

TITLE & NARRATIVE:
- Title should be compelling and thematic (2-5 words)
- Tagline should be a short hook (3-10 words)
- Description should be rich narrative (2-3 paragraphs) explaining significance
- Write for a general educated audience, not just academics

SUBTOPICS (2-4):
- Reflect meaningful thematic groupings (e.g., "Theoretical Foundations", "Wartime Applications")
- NOT just job title duplicates (avoid "Mathematicians", "Scientists", "Writers")
- Should tell a story within the story (e.g., "Breaking the Unbreakable", "From Theory to Practice")
- 2-4 people per subtopic is ideal
- OK to have overlapping membership (person can appear in multiple subtopics)

GOOD SUBTOPIC EXAMPLES:
- "Theoretical Foundations" (mathematicians who defined computation)
- "Wartime Computing" (codebreakers and engineers)
- "Software Pioneers" (compiler and language inventors)
- "Critical Voices" (technologists questioning AI ethics)

BAD SUBTOPIC EXAMPLES:
- "Mathematicians" (too generic)
- "American Scientists" (geographic grouping, not thematic)
- "Famous People" (meaningless)

CHAPTERS (3-6):
- Era-based with clear date ranges (year precision only)
- Title format: "Era Name (YYYY-YYYY)" (e.g., "Early Foundations (1900-1920)")
- Chapters should be chronological and non-overlapping
- Bridge statement: narrative hook, not summary (1-2 sentences, max 30 words)
- Each bridge should create anticipation for what happened during that era
- Aim for roughly equal time spans when possible

CONCLUSION:
- Synthesize the overall narrative (2-3 sentences)
- Capture the collective impact/legacy
- Should feel like the closing paragraph of a compelling essay

MISSING PEOPLE SUGGESTIONS:
- After creating the meta-story, suggest 3-5 notable people NOT in the registry who would strengthen this narrative
- For each suggestion: provide name, reason (why they'd fit), and role
- Focus on people who would fill gaps or add important perspectives
- These are recommendations for future dataset expansion
"""

    try:
        response = client.beta.chat.completions.parse(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert historian and narrative designer. Create compelling meta-stories that organize biographical data thematically and chronologically."
                },
                {"role": "user", "content": prompt}
            ],
            response_format=MetaStoryPlan,
        )

        result = response.choices[0].message
        if result.parsed:
            plan = result.parsed

            # Validate selected people exist in registry
            invalid_ids = []
            for person_ref in plan.selected_people:
                if not validate_person_exists(person_ref.person_id, registry):
                    invalid_ids.append(person_ref.person_id)

            if invalid_ids:
                print(f"Error: AI selected non-existent person IDs: {invalid_ids}")
                return None

            if verbose:
                print(f"Selected {len(plan.selected_people)} people")
                print(f"Created {len(plan.subtopics)} subtopics")
                print(f"Designed {len(plan.chapters)} chapters")

            return plan
        elif result.refusal:
            print(f"Error: Model refused: {result.refusal}")
            return None
        else:
            print("Error: No parsed result")
            return None

    except APIStatusError as e:
        message = ""
        try:
            error_body = e.response.json() if hasattr(e.response, 'json') else {}
            message = error_body.get("error", {}).get("message", str(e))
        except Exception:
            message = str(e)
        print(f"Error: OpenAI API error: {e.status_code} {message}")
        return None
    except Exception as e:
        print(f"Error: Phase 1 failed: {e}")
        return None


# ============================================================================
# PHASE 2: EVENT MAPPING
# ============================================================================

def phase2_event_mapping(
    plan: MetaStoryPlan,
    verbose: bool = False
) -> List[ChapterWithEvents]:
    """
    Phase 2: Map events to temporal chapters (programmatic, no AI).

    Args:
        plan: Output from Phase 1
        verbose: Enable logging

    Returns:
        List of chapters with person_events arrays
    """
    if verbose:
        print(f"\n=== PHASE 2: Event Mapping ===")

    # Load all person life events
    person_events = {}
    for person_ref in plan.selected_people:
        person_id = person_ref.person_id
        life_events = load_person_life_events(person_id)
        if life_events:
            person_events[person_id] = life_events.get("events", [])
        else:
            if verbose:
                print(f"Warning: No life events found for {person_id}")
            person_events[person_id] = []

    # Map events to chapters
    chapters_with_events = []
    for chapter in plan.chapters:
        chapter_start = int(chapter.date_start.split("-")[0])
        chapter_end = int(chapter.date_end.split("-")[0])

        mapped_events = []

        for person_id, events in person_events.items():
            for idx, event in enumerate(events):
                event_year = parse_event_date(event)
                if event_year is None:
                    continue

                # Check if event falls within chapter range
                if chapter_start <= event_year <= chapter_end:
                    mapped_events.append(PersonEvent(
                        person_id=person_id,
                        event_date=event.get("date", ""),
                        event_date_precision=event.get("date_precision", "year"),
                        event_title=event.get("title", ""),
                        event_index=idx
                    ))

        # Sort events by date within chapter
        mapped_events.sort(key=lambda e: parse_event_date({"date": e.event_date}) or 0)

        chapters_with_events.append(ChapterWithEvents(
            id=chapter.id,
            title=chapter.title,
            date_start=chapter.date_start,
            date_start_precision=chapter.date_start_precision,
            date_end=chapter.date_end,
            date_end_precision=chapter.date_end_precision,
            bridge_statement=chapter.bridge_statement,
            person_events=mapped_events
        ))

        if verbose:
            print(f"  Chapter '{chapter.title}': {len(mapped_events)} events")

    return chapters_with_events


# ============================================================================
# FILE I/O
# ============================================================================

def calculate_date_range(chapters: List[ChapterWithEvents]) -> tuple:
    """Calculate overall date range from chapters."""
    if not chapters:
        return ("1900", "2000")

    start_years = [int(c.date_start.split("-")[0]) for c in chapters]
    end_years = [int(c.date_end.split("-")[0]) for c in chapters]

    return (str(min(start_years)), str(max(end_years)))


def build_meta_story_dataset(
    plan: MetaStoryPlan,
    chapters: List[ChapterWithEvents],
    story_id: str
) -> Dict[str, Any]:
    """Build final meta-story dataset JSON."""
    date_start, date_end = calculate_date_range(chapters)
    person_ids = [p.person_id for p in plan.selected_people]

    now = datetime.now().astimezone().isoformat()

    meta_story = MetaStory(
        id=story_id,
        title=plan.title,
        tagline=plan.tagline,
        description=plan.description,
        person_ids=person_ids,
        date_range_start=date_start,
        date_range_end=date_end,
        lastUpdated=now
    )

    dataset = MetaStoryDataset(
        dataset="meta_story",
        created_on=now,
        meta_story=meta_story,
        subtopics=plan.subtopics,
        chapters=chapters,
        conclusion=plan.conclusion
    )

    return dataset.model_dump(exclude_none=False)


def save_meta_story(
    story_id: str,
    dataset: Dict[str, Any],
    verbose: bool = False
) -> bool:
    """Save meta-story JSON file."""
    output_path = META_STORIES_DIR / f"{story_id}.json"

    try:
        META_STORIES_DIR.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(dataset, f, indent=2, ensure_ascii=False)

        if verbose:
            print(f"Saved meta-story: {output_path}")

        return True
    except Exception as e:
        print(f"Error: Failed to save meta-story: {e}")
        return False


def update_meta_stories_registry(
    story_id: str,
    meta_story_data: Dict[str, Any],
    verbose: bool = False
) -> bool:
    """Update or create meta_stories.json registry."""
    registry_path = META_STORIES_REGISTER

    # Load existing registry
    if registry_path.exists():
        with open(registry_path, "r", encoding="utf-8") as f:
            registry = json.load(f)
    else:
        registry = {"meta_stories": []}

    # Build registry entry
    ms = meta_story_data["meta_story"]
    entry = {
        "id": story_id,
        "title": ms["title"],
        "tagline": ms["tagline"],
        "person_count": len(ms["person_ids"]),
        "date_range_start": ms["date_range_start"],
        "date_range_end": ms["date_range_end"],
        "created": ms["lastUpdated"],
        "lastUpdated": ms["lastUpdated"]
    }

    # Update or append
    found = False
    for i, existing in enumerate(registry["meta_stories"]):
        if existing["id"] == story_id:
            # Preserve original created date
            entry["created"] = existing.get("created", entry["created"])
            registry["meta_stories"][i] = entry
            found = True
            break

    if not found:
        registry["meta_stories"].append(entry)

    # Save registry
    try:
        with open(registry_path, "w", encoding="utf-8") as f:
            json.dump(registry, f, indent=2, ensure_ascii=False)

        if verbose:
            action = "Updated" if found else "Added"
            print(f"{action} registry entry: {story_id}")

        return True
    except Exception as e:
        print(f"Error: Failed to update registry: {e}")
        return False


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Generate a meta-story dataset grouping multiple people around a thematic topic"
    )
    parser.add_argument(
        "topic_title",
        help="Topic title (e.g., 'Computing Pioneers', 'Renaissance Artists')"
    )
    parser.add_argument(
        "--person-ids",
        help="Comma-separated person IDs to manually specify (skip AI selection)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing meta-story"
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"OpenAI model (default: {DEFAULT_MODEL})"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output"
    )

    args = parser.parse_args()

    # Validate OpenAI API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY environment variable not set")
        sys.exit(1)

    client = OpenAI(api_key=api_key)

    # Load registry
    if not REGISTER_PATH.exists():
        print(f"Error: Registry not found: {REGISTER_PATH}")
        sys.exit(1)

    registry = load_persons_registry()

    # Parse manual person IDs if provided
    manual_person_ids = None
    if args.person_ids:
        manual_person_ids = [pid.strip() for pid in args.person_ids.split(",")]
        # Validate all exist
        for pid in manual_person_ids:
            if not validate_person_exists(pid, registry):
                print(f"Error: Person not found: {pid}")
                sys.exit(1)
        if args.verbose:
            print(f"Using manual person selection: {manual_person_ids}")

    # Generate story ID
    story_id = slugify(args.topic_title)
    output_path = META_STORIES_DIR / f"{story_id}.json"

    # Check if exists
    if output_path.exists() and not args.force:
        print(f"Error: Meta-story already exists: {story_id}")
        print("Use --force to overwrite")
        sys.exit(1)

    print(f"Generating meta-story: {args.topic_title}")
    print(f"Story ID: {story_id}")

    # Phase 1: Story planning
    plan = phase1_story_planning(
        topic_title=args.topic_title,
        registry=registry,
        client=client,
        model=args.model,
        manual_person_ids=manual_person_ids,
        verbose=args.verbose
    )

    if not plan:
        print("ERROR: Phase 1 failed")
        sys.exit(1)

    # Phase 2: Event mapping
    chapters = phase2_event_mapping(plan, verbose=args.verbose)

    # Build dataset
    dataset = build_meta_story_dataset(plan, chapters, story_id)

    # Save files
    if not save_meta_story(story_id, dataset, verbose=args.verbose):
        sys.exit(1)

    if not update_meta_stories_registry(story_id, dataset, verbose=args.verbose):
        sys.exit(1)

    print(f"\nSUCCESS: Meta-story created!")
    print(f"  ID: {story_id}")
    print(f"  People: {len(plan.selected_people)}")
    print(f"  Subtopics: {len(plan.subtopics)}")
    print(f"  Chapters: {len(chapters)}")
    print(f"  Total events: {sum(len(c.person_events) for c in chapters)}")

    # Display missing people suggestions
    if plan.missing_people_suggestions and len(plan.missing_people_suggestions) > 0:
        print(f"\nRECOMMENDATIONS: Missing people who would strengthen this meta-story:")
        for i, suggestion in enumerate(plan.missing_people_suggestions, 1):
            print(f"\n  {i}. {suggestion.name} ({suggestion.role})")
            print(f"     {suggestion.reason}")
        print(f"\n  Consider adding these people to expand the dataset.")

    sys.exit(0)


if __name__ == "__main__":
    main()
