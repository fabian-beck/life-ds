#!/usr/bin/env python3
"""
Generate meta-story datasets using a multi-phase approach:
1. Phase 1: Story planning and person selection (1 AI call). Its chapters are
   a *proposal* — thematic era names with guessed date ranges, decided before
   any event is known.
2. Phase 2: Event collection (programmatic, no AI) — every dated event of the
   selected people, unfiltered and unbucketed.
3. Phase 3: AI-powered event filtering for topic relevance (batched AI calls),
   then Phase 3b: the proposed chapters are fitted deterministically to the
   events that survived, so no event is lost to a date-range gap.
4. Phase 4: Historical context landmarks (1 AI call)
5. Phase 5: Social network derived from ego networks (programmatic, no AI)
   Phase 5b: AI review/enrichment of the derived network (1 AI call)
6. Phase 6: Network narration for the scroll-over cards (1 AI call)
7. Phase 7: Geographic map section — event rating, geographic clustering,
   and stop narration with a discard option (see meta_story_map.py and
   meta_story_map_narration.py)
8. Phase 8: Story composer — top-down narrative composition (4 AI calls,
   see compose_meta_story.py): curation, then the caption layer bound to the
   items, then the article that runs between the components, then a
   redundancy pass over both. Runs LAST so it sees the assembled story
   including the map, whose stops it may reorder/discard; its exclusion
   cascade prunes the earlier sections deterministically.

Meta-stories group multiple people around thematic topics with temporal chapters.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

from openai import OpenAI, APIStatusError
from pydantic import BaseModel, Field

from compose_meta_story import compose_meta_story_dataset
from config import DEFAULT_MODEL, DEFAULT_REASONING_EFFORT, enable_utf8_console
from meta_story_map_narration import generate_geo_map
from meta_story_network import build_social_network, derive_clusters
from meta_story_network_review import review_social_network

enable_utf8_console()

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


class SelectionHints(BaseModel):
    """Hints to guide AI person selection and story structure."""

    hint: str = Field(
        description="Short guidance string for person selection (e.g., 'include also Jugendstil architects', 'focus on Vienna Secession period')"
    )


class MissingPersonSuggestion(BaseModel):
    """Suggestion for a person not in the registry who would strengthen this collection."""

    name: str = Field(description="Full name of the suggested person")
    reason: str = Field(
        description="Brief explanation of why this person would strengthen the collection (1-2 sentences)"
    )
    role: str = Field(
        description="Primary role or contribution (e.g., 'mathematician', 'architect')"
    )


class MetaStoryPlan(BaseModel):
    """Phase 1 output: Complete collection plan with selected people."""

    title: str = Field(description="Collection title (2-5 words)")
    tagline: str = Field(description="Short hook (3-10 words)")
    description: str = Field(
        description="Rich narrative overview (2-3 paragraphs) explaining the collection's significance"
    )
    selected_people: List[PersonReference] = Field(
        description="All people who clearly fit this collection (no fixed number - select based on fit)",
        min_length=1,
    )
    subtopics: List[Subtopic] = Field(
        description="2-4 thematic subtopics organizing the selected people",
        min_length=2,
        max_length=4,
    )
    chapters: List[TemporalChapter] = Field(
        description="3-6 era-based chapters covering the time span",
        min_length=3,
        max_length=6,
    )
    conclusion: str = Field(
        description="Overall narrative conclusion (2-3 sentences) tying the collection together"
    )
    missing_people_suggestions: Optional[List[MissingPersonSuggestion]] = Field(
        default=None,
        description="3-5 suggestions for people NOT in the registry who would strengthen this collection",
    )


class PersonEvent(BaseModel):
    """Reference to a specific event from a person's life_events.json with meta-story context."""

    person_id: str = Field(description="Person ID")
    event_date: str = Field(description="Event date (from life_events.json)")
    event_date_precision: str = Field(description="Date precision")
    event_title: str = Field(description="Event title (from life_events.json)")
    event_index: int = Field(description="Index in person's events array")
    theme_connection: str = Field(
        description="Explanation of how this event contributes to the meta-story theme"
    )
    # All events stored are essential (weak events are filtered out during generation)


class EventForReview(BaseModel):
    """Event to be reviewed for topic relevance."""

    event_id: str = Field(
        description="Unique identifier for tracking (person_id:event_index)"
    )
    person_name: str = Field(description="Person's name")
    event_title: str = Field(description="Event title")
    event_date: str = Field(description="Event date")
    event_description: str = Field(description="Event description (first 200 chars)")


class EventRelevanceDecision(BaseModel):
    """AI decision on whether an event is essential to the collection topic."""

    event_id: str = Field(
        description="Event identifier (matches EventForReview.event_id)"
    )
    is_relevant: bool = Field(
        description="True if event is ESSENTIAL to the collection topic (core contribution). False if weak/tangential."
    )
    theme_connection: str = Field(
        description="Brief explanation (1-2 sentences) of HOW this event contributes to the meta-story theme. Be specific about which aspect of the topic it demonstrates. If not relevant, explain why it's too tangential."
    )


class BatchEventRelevanceDecisions(BaseModel):
    """Batch of relevance decisions for multiple events."""

    decisions: List[EventRelevanceDecision] = Field(
        description="Relevance decision for each event in the batch"
    )


class HistoricalContextEvent(BaseModel):
    """A well-known historical event that contextualizes the meta-story era."""

    id: str = Field(description="Unique identifier (snake_case)")
    title: str = Field(
        description="Short event name (1-5 words, e.g. 'World War II', 'Moon Landing')"
    )
    description: str = Field(description="One-sentence context note")
    date_start: str = Field(description="ISO-8601 date (year, month, or day precision)")
    date_start_precision: str = Field(description="'year', 'month', or 'day'")
    date_end: Optional[str] = Field(
        default=None,
        description="ISO-8601 end date for time ranges (None for single events)",
    )
    date_end_precision: Optional[str] = Field(default=None)
    wikipedia_url: Optional[str] = Field(
        default=None, description="Wikipedia article URL for this event (if known)"
    )
    priority: int = Field(
        default=2,
        description=(
            "Label importance 1-3 for decluttering overlapping timeline labels "
            "(3 = a defining landmark that most shaped these people / that any "
            "reader would recognise, 2 = notable, 1 = minor background detail). "
            "When labels compete for horizontal space, higher priority wins."
        ),
    )


class ChapterHistoricalEvents(BaseModel):
    """Historical context events for a single chapter."""

    chapter_id: str = Field(description="Chapter ID this batch belongs to")
    events: List[HistoricalContextEvent] = Field(
        description="0-2 historical context events for this chapter"
    )


class HistoricalContextResponse(BaseModel):
    """Phase 4 AI response: historical events for all chapters."""

    chapter_events: List[ChapterHistoricalEvents] = Field(
        description="Historical context events grouped by chapter"
    )


class ChapterWithEvents(TemporalChapter):
    """Chapter with mapped events from multiple people."""

    person_events: List[PersonEvent] = Field(
        description="Events from multiple people during this era"
    )
    historical_context: Optional[List[HistoricalContextEvent]] = Field(
        default=None,
        description="General historical events providing context for this era",
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


class GenerationMetadata(BaseModel):
    """Metadata about how the meta-story was generated."""

    hints: Optional[SelectionHints] = Field(
        default=None,
        description="Hints used to guide person selection and story structure",
    )
    model: str = Field(description="OpenAI model used for generation")
    generated_at: str = Field(description="ISO-8601 timestamp")


class MetaStoryDataset(BaseModel):
    """Top-level dataset structure for meta-story JSON."""

    dataset: str = Field(default="meta_story")
    created_on: str = Field(description="ISO-8601 timestamp")
    meta_story: MetaStory
    generation_metadata: Optional[GenerationMetadata] = Field(
        default=None, description="Metadata about generation process"
    )
    subtopics: List[Subtopic]
    chapters: List[ChapterWithEvents]
    conclusion: str


class NetworkCircleNarration(BaseModel):
    """Narrative text for one cluster ("circle") of the social network."""

    key: str = Field(description="The circle's key, copied verbatim from the input")
    title: str = Field(
        description="A short, evocative headline for the circle (2-5 words) — "
        "a book-chapter-style phrase capturing what bound this group, NOT a list "
        "of the people's names"
    )
    text: str = Field(
        description="2-4 sentence story text weaving the circle's ties together"
    )


class NetworkNarrationResult(BaseModel):
    """AI-written narration for the social network scroll-over cards."""

    intro: str = Field(
        description="A 2-3 sentence introductory paragraph for the network, "
        "written like a book's opening: thematic and evocative, in the third "
        "person and never addressed to the reader. It sets the scene for the "
        "whole network WITHOUT naming individual people or previewing the "
        "specific circles (those are revealed later). No lists, no reading guide."
    )
    circles: List[NetworkCircleNarration]


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
        return cast(Dict[str, Any], json.load(f))


def load_person_life_events(person_id: str) -> Optional[Dict[str, Any]]:
    """Load a person's life_events.json."""
    events_path = PEOPLE_DIR / person_id / "life_events.json"
    if not events_path.exists():
        return None
    with open(events_path, "r", encoding="utf-8") as f:
        return cast(Optional[Dict[str, Any]], json.load(f))


def validate_person_exists(person_id: str, registry: Dict[str, Any]) -> bool:
    """Check if person_id exists in registry."""
    people = registry.get("people", [])
    return any(p.get("id") == person_id for p in people)


def load_existing_hints(story_id: str) -> Optional[SelectionHints]:
    """Load hints from an existing meta-story JSON file."""
    meta_story_path = META_STORIES_DIR / f"{story_id}.json"
    if not meta_story_path.exists():
        return None

    try:
        with open(meta_story_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        metadata = data.get("generation_metadata", {})
        hints_data = metadata.get("hints")

        if hints_data:
            return SelectionHints(**hints_data)
        return None
    except Exception:
        return None


def load_hints_from_file(hints_path: str) -> Optional[SelectionHints]:
    """Load hints from a text or JSON file."""
    try:
        with open(hints_path, "r", encoding="utf-8") as f:
            content = f.read().strip()

        # Try parsing as JSON first
        try:
            hints_data = json.loads(content)
            if isinstance(hints_data, dict) and "hint" in hints_data:
                return SelectionHints(**hints_data)
            else:
                print("Error: JSON file must contain a 'hint' field")
                return None
        except json.JSONDecodeError:
            # Treat as plain text hint
            return SelectionHints(hint=content)
    except Exception as e:
        print(f"Error loading hints file: {e}")
        return None


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


# NOTE: a regex prefilter (``is_topic_relevant_event``) used to drop "personal
# life" events here, before Phase 3 ever saw them. It was removed deliberately:
#
# - It matched against the full DESCRIPTION, not just the title, so a
#   professional event was killed by an incidental mention. Measured across the
#   14 people of computing_pioneers it dropped 56 of 225 events, 9 of them with
#   a perfectly clean title — "Receives Grand Cross of the Order of Merit"
#   (killed by /\bengag/ matching "engaged"), "Earns MS and PhD at Berkeley"
#   (a marriage mentioned in its description), "Moves company to Paderborn"
#   (/\brelocat/).
# - Its judgement was topic-blind. "Birth in Bamberg" is noise for a computing
#   story and evidence for a place-based one like citizens_of_bamberg; a fixed
#   pattern list cannot tell those apart.
# - It was English-only, silent, and left no record of what it removed.
#
# Phase 3 is a strictly better version of the same filter: it sees the topic,
# decides per event, and states a reason. Life-cycle events now reach it and
# are rejected there — with context, and visibly.


# ============================================================================
# PHASE 1: STORY PLANNING
# ============================================================================


def phase1_story_planning(
    topic_title: str,
    registry: Dict[str, Any],
    client: OpenAI,
    model: str,
    manual_person_ids: Optional[List[str]] = None,
    hints: Optional[SelectionHints] = None,
    verbose: bool = False,
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
        print("\n=== PHASE 1: Story Planning ===")
        print(f"Topic: {topic_title}")

    # Build registry summary for AI
    people_summary = []
    for person in registry.get("people", []):
        summary_text = person.get("summary", "")
        # Truncate summaries for token efficiency, preserving sentence boundaries
        if len(summary_text) > 200:
            truncated = summary_text[:197]
            # Try to break at sentence boundary to preserve context
            last_period = truncated.rfind(".")
            if last_period > 100:  # Keep at least half
                summary_text = truncated[: last_period + 1]
            else:
                summary_text = truncated + "..."

        # Load location & event title data from life events to help with place-based/thematic topics
        person_id = person.get("id")
        locations = []
        key_events = []
        life_events = load_person_life_events(person_id)
        if life_events:
            # Extract unique location names from events
            location_set = set()
            for event in life_events.get("events", []):
                for loc_data in event.get("location_coordinates", []):
                    loc_name = loc_data.get("name")
                    if loc_name:
                        # Extract city/region (before first comma)
                        city = loc_name.split(",")[0].strip()
                        location_set.add(city)
            locations = sorted(list(location_set))[:10]  # Limit to top 10

            # Extract event titles (helps with thematic matching)
            key_events = [
                e.get("title", "") for e in life_events.get("events", [])[:15]
            ]  # First 15 events

        people_summary.append(
            {
                "id": person.get("id"),
                "name": person.get("name"),
                "primaryRoles": person.get("primaryRoles", []),
                "birthDate": person.get("birthDate"),
                "deathDate": person.get("deathDate"),
                "summary": summary_text,
                "locations": locations,  # NEW: Add locations for place-based selection
                "key_events": key_events,  # NEW: Add event titles for thematic matching
            }
        )

    # Build hints section if provided
    hints_section = ""
    if hints:
        hints_section = f"""

=== MANDATORY SELECTION OVERRIDE ===
The following hint OVERRIDES default selection criteria. If specific people are named,
you MUST include them even if they seem only loosely connected to the topic.
Hint: {hints.hint}
===================================
"""

    if manual_person_ids:
        # Manual mode: AI only creates structure, uses provided people
        relevant_people = [p for p in people_summary if p["id"] in manual_person_ids]

        prompt = f"""Create a thematic collection structure for the topic "{topic_title}".
{hints_section}
You MUST use these specific people (already selected):
{json.dumps(manual_person_ids, indent=2)}

Your task:
1. Create a compelling title, tagline, and description for this collection
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
- CRITICAL: Write description like a journalist or educator introducing the topic
  * DO NOT use meta-references like "This collection...", "These figures...", "This meta-story..."
  * Instead, write directly about the topic itself as an engaging introduction
  * Example GOOD: "Computing pioneers turned calculation from a human craft into..."
  * Example BAD: "This collection traces how computing pioneers turned..."
  * Think of it as the opening paragraphs of a feature article or documentary introduction

SUBTOPICS (2-4):
- Reflect meaningful thematic groupings (e.g., "Theoretical Foundations", "Wartime Applications")
- NOT just job title duplicates (avoid "Mathematicians", "Scientists", "Writers")
- Should tell a story within the story (e.g., "Breaking the Unbreakable", "From Theory to Practice")
- 2-4 people per subtopic is ideal
- CRITICAL CONSTRAINT: Each person must be assigned to EXACTLY ONE subtopic
  * NO OVERLAPS: A person cannot appear in multiple subtopics
  * NO OMISSIONS: Every selected person must appear in exactly one subtopic
  * If a person fits multiple themes, choose their PRIMARY contribution
- All selected people must be distributed across subtopics with no duplicates

CHAPTERS (3-6):
- Era-based with clear date ranges (year precision only)
- Title format: "Era Name (YYYY-YYYY)" (e.g., "Early Foundations (1900-1920)")
- Chapters should be chronological and non-overlapping
- CRITICAL: Chapter date ranges should focus on periods of ACTIVE CONTRIBUTION to the topic
  * DO NOT start chapters with birth years unless early life directly relates to the topic
  * Base date ranges on when people actually made their contributions (publications, discoveries, work, influence)
  * Example: If someone born in 1900 only contributed to computing in 1935-1950, the chapter should span 1935-1950, NOT 1900-1950
  * Use the key_events field to identify when actual topic-relevant work occurred
  * Chapters should capture the era when meaningful events happened, not entire lifespans

CONCLUSION:
- Synthesize the overall narrative (2-3 sentences)
- Capture the collective impact/legacy
- Should feel like the closing paragraph of a compelling essay

MISSING PEOPLE SUGGESTIONS:
- After creating the collection, suggest 3-5 notable people NOT in the registry who would strengthen this narrative
- For each suggestion: provide name, reason (why they'd fit), and role
- Focus on people who would fill gaps or add important perspectives
- These are recommendations for future dataset expansion

Use ALL provided person IDs (no more, no less).
Provide a relevance_note for each person explaining their fit.
"""
    else:
        # Automatic mode: AI selects people + creates structure
        prompt = f"""Create a thematic collection for the topic "{topic_title}" by selecting ALL people from the registry who clearly fit this topic.
{hints_section}
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
- Select people whose primaryRoles, summary, locations, OR key_events CLEARLY and DIRECTLY fit the topic
- When evaluating fit, consider ALL available data:
  * primaryRoles: profession/occupation
  * summary: career overview
  * locations: cities/regions where they lived/worked (especially important for place-based topics)
  * key_events: sample event titles from their life (reveals specific contributions)
- When a person has multiple roles, evaluate ALL roles for thematic fit
  * Example: "artist, architect, environmentalist" fits architecture topics if summary confirms architectural work
  * Role order does NOT indicate importance - evaluate based on substantive contribution
- For PLACE-BASED topics (e.g., "Citizens of Bamberg", "Berlin Intellectuals"):
  * Check the "locations" field - if the target city appears, this is STRONG evidence
  * Also check key_events for mentions of the place or activities there
  * Include anyone with significant residence, work, or contribution in that place
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
- CRITICAL: Write description like a journalist or educator introducing the topic
  * DO NOT use meta-references like "This collection...", "These figures...", "This meta-story..."
  * Instead, write directly about the topic itself as an engaging introduction
  * Example GOOD: "Computing pioneers turned calculation from a human craft into..."
  * Example BAD: "This collection traces how computing pioneers turned..."
  * Think of it as the opening paragraphs of a feature article or documentary introduction

SUBTOPICS (2-4):
- Reflect meaningful thematic groupings (e.g., "Theoretical Foundations", "Wartime Applications")
- NOT just job title duplicates (avoid "Mathematicians", "Scientists", "Writers")
- Should tell a story within the story (e.g., "Breaking the Unbreakable", "From Theory to Practice")
- 2-4 people per subtopic is ideal
- CRITICAL CONSTRAINT: Each person must be assigned to EXACTLY ONE subtopic
  * NO OVERLAPS: A person cannot appear in multiple subtopics
  * NO OMISSIONS: Every selected person must appear in exactly one subtopic
  * If a person fits multiple themes, choose their PRIMARY contribution
- All selected people must be distributed across subtopics with no duplicates

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
- CRITICAL: Chapters MUST be strictly chronological and NON-OVERLAPPING
  * Each chapter's date_end must be <= the next chapter's date_start (adjacent chapters MAY share a boundary year)
  * Chapters must be in chronological order from earliest to latest
  * Example CORRECT: Chapter 1 (1900-1920), Chapter 2 (1920-1945), Chapter 3 (1946-1970) ← sharing 1920 is OK
  * Example CORRECT: Chapter 1 (1900-1920), Chapter 2 (1921-1945), Chapter 3 (1946-1970)
  * Example WRONG: Chapter 1 (1900-1930), Chapter 2 (1920-1950) ← TRUE OVERLAP NOT ALLOWED
  * If an event could fit multiple chapters, assign it to the chapter where it has PRIMARY thematic importance
- Aim for roughly equal time spans when possible
- CRITICAL: Chapter date ranges should focus on periods of ACTIVE CONTRIBUTION to the topic
  * DO NOT start chapters with birth years unless early life directly relates to the topic
  * Base date ranges on when people actually made their contributions (publications, discoveries, work, influence)
  * Example: If someone born in 1900 only contributed to computing in 1935-1950, the chapter should span 1935-1950, NOT 1900-1950
  * Use the key_events field to identify when actual topic-relevant work occurred
  * Chapters should capture the era when meaningful events happened, not entire lifespans

CONCLUSION:
- Synthesize the overall narrative (2-3 sentences)
- Capture the collective impact/legacy
- Should feel like the closing paragraph of a compelling essay

MISSING PEOPLE SUGGESTIONS:
- After creating the collection, suggest 3-5 notable people NOT in the registry who would strengthen this narrative
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
                    "content": "You are an expert historian and narrative designer. Create compelling thematic collections that organize biographical data thematically and chronologically. CRITICAL: Each person must appear in EXACTLY ONE subtopic - no duplicates allowed across subtopics.",
                },
                {"role": "user", "content": prompt},
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

            # Validate subtopic assignments
            selected_person_ids = {p.person_id for p in plan.selected_people}
            subtopic_person_ids = set()
            person_assignment_count: Dict[str, int] = {}

            for subtopic in plan.subtopics:
                for person_id in subtopic.person_ids:
                    if person_id not in selected_person_ids:
                        print(
                            f"Error: Subtopic '{subtopic.id}' references non-selected person: {person_id}"
                        )
                        return None

                    # Track how many times each person is assigned
                    person_assignment_count[person_id] = (
                        person_assignment_count.get(person_id, 0) + 1
                    )
                    subtopic_person_ids.add(person_id)

            # Check for people assigned to multiple subtopics
            multi_assigned = [
                pid for pid, count in person_assignment_count.items() if count > 1
            ]
            if multi_assigned:
                print(
                    f"Error: These people are assigned to multiple subtopics: {multi_assigned}"
                )
                print("Each person must be assigned to exactly ONE subtopic.")
                return None

            # Check for people not assigned to any subtopic
            unassigned = selected_person_ids - subtopic_person_ids
            if unassigned:
                print(
                    f"Error: These people are not assigned to any subtopic: {list(unassigned)}"
                )
                print("All selected people must be assigned to exactly ONE subtopic.")
                return None

            # Validate chapters are strictly non-overlapping and chronological
            sorted_chapters = sorted(
                plan.chapters, key=lambda c: int(c.date_start.split("-")[0])
            )
            for i in range(len(sorted_chapters) - 1):
                current_chapter = sorted_chapters[i]
                next_chapter = sorted_chapters[i + 1]
                current_end = int(current_chapter.date_end.split("-")[0])
                next_start = int(next_chapter.date_start.split("-")[0])

                if current_end > next_start:
                    print("Error: Chapters overlap!")
                    print(f"  '{current_chapter.title}' ends in {current_end}")
                    print(f"  '{next_chapter.title}' starts in {next_start}")
                    print(
                        "Chapters must be non-overlapping (date_end <= next date_start)"
                    )
                    return None

            if verbose:
                print(f"Selected {len(plan.selected_people)} people")
                print(f"Created {len(plan.subtopics)} subtopics")
                print(f"Designed {len(plan.chapters)} chapters")
                print("Validated: All people assigned to exactly one subtopic")
                print("Validated: All chapters are non-overlapping")

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
            error_body = e.response.json() if hasattr(e.response, "json") else {}
            message = error_body.get("error", {}).get("message", str(e))
        except Exception:
            message = str(e)
        print(f"Error: OpenAI API error: {e.status_code} {message}")
        return None
    except Exception as e:
        print(f"Error: Phase 1 failed: {e}")
        return None


# ============================================================================
# PHASE 2: EVENT COLLECTION
# ============================================================================


def phase2_event_collection(
    plan: MetaStoryPlan, registry: Dict[str, Any], verbose: bool = False
) -> List[Dict[str, Any]]:
    """
    Phase 2: Collect EVERY dated event of the selected people, unfiltered.

    Deliberately not bucketed by the Phase 1 chapter ranges. Those ranges are
    guessed before anyone knows which events exist — from truncated summaries
    and the first 15 event titles — so gating on them silently deleted any
    essential event that fell in a gap between chapters or outside the outer
    bounds. Relevance is Phase 3's decision and the chapter fit is made
    afterwards, against the events that actually survived
    (``fit_chapters_to_events``).

    Args:
        plan: Output from Phase 1
        registry: Persons registry (for name lookup)
        verbose: Enable logging

    Returns:
        Flat list of raw event records, sorted chronologically, so Phase 3's
        batches stay era-coherent.
    """
    if verbose:
        print("\n=== PHASE 2: Event Collection ===")

    person_names = {}
    for person in registry.get("people", []):
        person_names[person.get("id", "")] = person.get("name", person.get("id", ""))

    collected: List[Dict[str, Any]] = []
    undated = 0

    for person_ref in plan.selected_people:
        person_id = person_ref.person_id
        life_events = load_person_life_events(person_id)
        if not life_events:
            if verbose:
                print(f"Warning: No life events found for {person_id}")
            continue

        events = life_events.get("events", [])
        person_undated = 0
        for idx, event in enumerate(events):
            event_year = parse_event_date(event)
            if event_year is None:
                # Without a year an event cannot be placed on the timeline.
                person_undated += 1
                continue
            collected.append(
                {
                    "person_id": person_id,
                    "person_name": person_names.get(person_id, person_id),
                    "event_index": idx,
                    "event_year": event_year,
                    "event": event,
                }
            )
        undated += person_undated
        if verbose:
            print(
                f"  {person_id}: {len(events) - person_undated} dated event(s)"
                + (f", {person_undated} undated (skipped)" if person_undated else "")
            )

    collected.sort(key=lambda e: e["event_year"])

    if verbose:
        print(f"\nTotal: {len(collected)} events collected (no pre-filtering)")
        if undated:
            print(f"  {undated} event(s) skipped for having no parsable date")

    return collected


# ============================================================================
# PHASE 3: AI-POWERED EVENT FILTERING
# ============================================================================


def _ascii(text: str) -> str:
    """Console-safe rendering for the verbose event log."""
    return text.encode("ascii", "replace").decode("ascii")


def phase3_ai_event_filtering(
    plan: MetaStoryPlan,
    collected_events: List[Dict[str, Any]],
    client: OpenAI,
    model: str,
    verbose: bool = False,
    batch_size: int = 20,
) -> List[Dict[str, Any]]:
    """
    Phase 3: Use AI to filter events for topic relevance.

    Reviews the story's whole event pool, not per-chapter buckets: relevance
    is a property of the event and the topic, not of which era box an event
    happened to land in. Chapters are fitted afterwards, to whatever survives.

    Args:
        plan: Output from Phase 1
        collected_events: Output from Phase 2 (all dated events, chronological)
        client: OpenAI client
        model: Model to use
        verbose: Enable logging
        batch_size: Number of events to process per AI call

    Returns:
        The curated event records (the Phase 2 dicts, each with the AI's
        ``theme_connection`` attached), in chronological order.
    """
    if verbose:
        print("\n=== PHASE 3: AI Event Filtering ===")

    # Prepare topic context for AI
    topic_context = f"""Collection Topic: {plan.title}
Tagline: {plan.tagline}
Description: {plan.description}

Thematic Subtopics:
{chr(10).join(f"- {st.title}: {st.description}" for st in plan.subtopics)}

Your task: Identify events that DIRECTLY contribute to this meta-story's narrative.
Focus on events that demonstrate the theme through concrete achievements, innovations, or impacts.
The pool below is every dated event of these people's lives, unfiltered — it includes
births, deaths, marriages, illnesses and relocations. Reject those unless the topic
gives them CLEAR thematic relevance (a birthplace matters to a story about a city;
a death matters to a story about persecution). Judge each against THIS topic."""

    curated: List[Dict[str, Any]] = []
    total_excluded = 0

    if verbose:
        print(f"  Reviewing {len(collected_events)} events...")

    for i in range(0, len(collected_events), batch_size):
        batch = collected_events[i : i + batch_size]
        batch_decisions = _filter_event_batch(
            batch, topic_context, client, model, verbose
        )

        for event_data in batch:
            event_id = f"{event_data['person_id']}:{event_data['event_index']}"
            decision = batch_decisions.get(event_id)
            title = _ascii(event_data["event"].get("title", ""))
            person_name = _ascii(event_data["person_name"])

            if decision and decision["is_relevant"]:
                curated.append(
                    {**event_data, "theme_connection": decision["theme_connection"]}
                )
                if verbose:
                    print(f"    [+] ESSENTIAL: {person_name}: {title}")
                    print(f"        Connection: {_ascii(decision['theme_connection'])}")
            else:
                total_excluded += 1
                if verbose:
                    print(f"    [-] WEAK: {person_name}: {title}")
                    if decision:
                        reason = decision.get("theme_connection", "Not relevant")
                        print(f"        Reason: {_ascii(reason)}")

    # Validate: every selected person should contribute at least one event
    person_event_counts: Dict[str, int] = {}
    for event_data in curated:
        pid = event_data["person_id"]
        person_event_counts[pid] = person_event_counts.get(pid, 0) + 1

    missing_persons = [
        p.person_id
        for p in plan.selected_people
        if p.person_id not in person_event_counts
    ]
    if missing_persons:
        print(
            "\nWARNING: The following persons have NO essential events in the meta-story:"
        )
        for person_id in missing_persons:
            print(f"  - {person_id}")
        print(
            "Every dated event of theirs was reviewed, so this is a curation "
            "judgement, not a date-range gap: either the AI filtering was too "
            "strict or the person does not belong in this story."
        )

    total_reviewed = len(collected_events)
    if verbose:
        print("\n=== Filtering Summary ===")
        print(f"Total reviewed: {total_reviewed}")
        if total_reviewed > 0:
            included_pct = 100 * len(curated) / total_reviewed
            excluded_pct = 100 * total_excluded / total_reviewed
            print(f"Included: {len(curated)} ({included_pct:.1f}%)")
            print(f"Excluded: {total_excluded} ({excluded_pct:.1f}%)")
        else:
            print(f"Included: {len(curated)}")
            print(f"Excluded: {total_excluded}")
        print("\nPerson coverage:")
        for person in plan.selected_people:
            count = person_event_counts.get(person.person_id, 0)
            status = "[OK]" if count > 0 else "[NONE]"
            print(f"  {status} {person.person_id}: {count} event(s)")

    return curated


def _filter_event_batch(
    events: List[Dict[str, Any]],
    topic_context: str,
    client: OpenAI,
    model: str,
    verbose: bool,
) -> Dict[str, Dict[str, Any]]:
    """
    Make a single AI call to filter a batch of events.

    Returns:
        Dict mapping event_id to decision dict {"is_relevant": bool, "reason": str}
    """
    # Prepare events for review
    events_for_review = []
    for event_data in events:
        event = event_data["event"]
        event_id = f"{event_data['person_id']}:{event_data['event_index']}"

        # Truncate description for token efficiency
        description = event.get("description", "")
        if len(description) > 300:
            description = description[:297] + "..."

        events_for_review.append(
            EventForReview(
                event_id=event_id,
                person_name=event_data["person_name"],
                event_title=event.get("title", ""),
                event_date=event.get("date", ""),
                event_description=description,
            )
        )

    # Group events by person to track coverage
    events_by_person: Dict[str, List[Any]] = {}
    for event_review in events_for_review:
        person_name = event_review.person_name
        if person_name not in events_by_person:
            events_by_person[person_name] = []
        events_by_person[person_name].append(event_review)

    prompt = f"""{topic_context}

Review the following events and determine which ones are TRULY ESSENTIAL to this meta-story.

CRITICAL REQUIREMENTS:
1. Be HIGHLY SELECTIVE - most events should be marked as weak/not relevant
2. Only mark events as essential if they represent MAJOR contributions to the topic
3. It is ACCEPTABLE for a person to have ZERO essential events in this batch if none meet the criteria
   (Each person needs at least one essential event across the ENTIRE meta-story, not per batch/chapter)

ESSENTIAL EVENT CRITERIA (is_relevant=true) - ALL must apply:
   ✓ DIRECT IMPACT: The event directly advanced the field/topic (not just participation)
   ✓ LANDMARK STATUS: Widely recognized as a significant milestone or breakthrough
   ✓ CONCRETE OUTPUT: Produced a lasting artifact (publication, invention, system, theory)
   ✓ IRREPLACEABLE: Removing this event would leave a major gap in the meta-story

   Examples of TRULY essential events:
   - "Published seminal paper that founded new subfield"
   - "Invented breakthrough technology that enabled X"
   - "Led team that created first working system for Y"
   - "Proved fundamental theorem that changed the field"

WEAK/TANGENTIAL EVENTS (is_relevant=false) - Mark as NOT relevant if ANY apply:
   ✗ Background/setup work (even if related to topic)
   ✗ Routine professional activities (teaching, consulting, management)
   ✗ Generic career milestones (appointments, promotions, awards for general work)
   ✗ Biographical context (education, training, meetings, relocations, career decisions)
   ✗ Preparatory or enabling work (unless it IS the breakthrough itself)
   ✗ Collaborations where this person was NOT the primary contributor
   ✗ Applications of existing ideas (unless groundbreaking application)
   ✗ Company/institution founding (unless the company/product IS the breakthrough)

   Examples of events to REJECT:
   - "Appointed to X position" → Career milestone, not contribution
   - "Studied under Y" → Background, not achievement
   - "Contributed to project Z" → Vague participation, not leadership
   - "Received award for career" → Recognition of past work, not the work itself
   - "Founded company/lab" → Setup activity, not the innovation itself
   - "Applied X theory to Y" → Application, not breakthrough (unless revolutionary)
   - "Break from teaching track" → Career decision, not contribution
   - "Joined X organization" → Career move, not achievement

STRICTNESS REQUIREMENT:
- DEFAULT TO REJECTING events unless they clearly meet ALL essential criteria
- If uncertain whether an event is essential → mark as is_relevant=false
- Only mark 1-3 events per person as essential (their absolute best contributions)
- Judge each event on its own merit against the criteria above. Do NOT aim for
  a share of the batch: the pool is every event of these people's lives, so most
  of it is biographical background that should be rejected. A batch in which
  nothing qualifies is a valid outcome.
- DO NOT include weak events just to ensure coverage - quality over quantity

For each event, provide:
1. **is_relevant**: true ONLY if event meets ALL essential criteria above, false otherwise
2. **theme_connection**:
   - If essential: Explain the CONCRETE contribution and why it's a landmark
   - If not essential: Briefly state why it doesn't meet the essential criteria

Events to review:
{json.dumps([e.model_dump() for e in events_for_review], indent=2)}
"""

    try:
        response = client.beta.chat.completions.parse(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert curator deciding which biographical events are ESSENTIAL to thematic collections. Be selective but ensure EVERY person has at least ONE essential event that demonstrates their contribution to the topic.",
                },
                {"role": "user", "content": prompt},
            ],
            response_format=BatchEventRelevanceDecisions,
        )

        result = response.choices[0].message
        if result.parsed:
            decisions = {}
            for decision in result.parsed.decisions:
                decisions[decision.event_id] = {
                    "is_relevant": decision.is_relevant,
                    "theme_connection": decision.theme_connection,
                }
            return decisions
        else:
            if verbose:
                print(
                    "  Warning: No parsed result from AI, including all events by default"
                )
            # Default: include all if AI fails
            return {
                f"{e['person_id']}:{e['event_index']}": {
                    "is_relevant": True,
                    "theme_connection": "AI filtering failed, included by default",
                }
                for e in events
            }

    except Exception as e:
        if verbose:
            print(f"  Warning: AI filtering error: {e}")
        # Default: include all if error
        return {
            f"{e['person_id']}:{e['event_index']}": {
                "is_relevant": True,
                "theme_connection": "AI filtering error, included by default",
            }
            for e in events
        }


# ============================================================================
# PHASE 4: HISTORICAL CONTEXT ENRICHMENT
# ============================================================================


# ============================================================================
# PHASE 3b: FIT CHAPTERS TO THE CURATED EVENTS (deterministic, no AI)
# ============================================================================


def _distance_to_chapter(year: int, start: int, end: int) -> int:
    """Years between ``year`` and a chapter's span (0 when inside it)."""
    if year < start:
        return start - year
    if year > end:
        return year - end
    return 0


def fit_chapters_to_events(
    plan: MetaStoryPlan,
    curated_events: List[Dict[str, Any]],
    verbose: bool = False,
) -> List[ChapterWithEvents]:
    """Place the curated events into chapters and fit the spans to them.

    Phase 1 proposes chapters — thematic era names with guessed date ranges —
    before knowing which events exist. Rather than using those ranges as a
    gate (which silently deleted any event falling in a gap between chapters
    or beyond the outer bounds), they are treated as a *proposal*: every
    curated event is assigned to the chapter that contains it, or failing
    that to the nearest one, and each chapter's span is then snapped to the
    events it actually holds.

    Nearest-chapter assignment over the ordered, non-overlapping proposal is
    a partition of the date line into contiguous regions, so snapping the
    spans afterwards cannot reorder the chapters or make them overlap.
    Chapters left without events are dropped: an empty era is a gap in the
    timeline, not a chapter.
    """
    if verbose:
        print("\n=== PHASE 3b: Chapter Fitting ===")

    proposal = sorted(plan.chapters, key=lambda c: int(c.date_start.split("-")[0]))
    spans = [
        (int(c.date_start.split("-")[0]), int(c.date_end.split("-")[0]))
        for c in proposal
    ]

    if not curated_events or not proposal:
        if verbose:
            print("  No curated events to place; keeping the proposed chapters")
        return [
            ChapterWithEvents(
                id=c.id,
                title=c.title,
                date_start=c.date_start,
                date_start_precision=c.date_start_precision,
                date_end=c.date_end,
                date_end_precision=c.date_end_precision,
                person_events=[],
            )
            for c in proposal
        ]

    buckets: Dict[str, List[Dict[str, Any]]] = {c.id: [] for c in proposal}
    out_of_range = 0

    for event_data in curated_events:
        year = event_data["event_year"]
        best_index = min(
            range(len(proposal)),
            key=lambda i: (_distance_to_chapter(year, *spans[i]), i),
        )
        if _distance_to_chapter(year, *spans[best_index]) > 0:
            out_of_range += 1
            if verbose:
                print(
                    f"  {year} {_ascii(event_data['person_name'])}: "
                    f"{_ascii(event_data['event'].get('title', ''))} -> "
                    f"nearest chapter '{proposal[best_index].id}' (outside its "
                    "proposed span)"
                )
        buckets[proposal[best_index].id].append(event_data)

    chapters: List[ChapterWithEvents] = []
    for chapter, (proposed_start, proposed_end) in zip(proposal, spans):
        events = sorted(buckets[chapter.id], key=lambda e: e["event_year"])
        if not events:
            if verbose:
                print(f"  Dropped empty chapter '{chapter.id}' ({chapter.title})")
            continue

        start = min(e["event_year"] for e in events)
        end = max(e["event_year"] for e in events)
        chapters.append(
            ChapterWithEvents(
                id=chapter.id,
                title=chapter.title,
                date_start=str(start),
                date_start_precision="year",
                date_end=str(end),
                date_end_precision="year",
                person_events=[
                    PersonEvent(
                        person_id=e["person_id"],
                        event_date=e["event"].get("date", ""),
                        event_date_precision=e["event"].get("date_precision", "year"),
                        event_title=e["event"].get("title", ""),
                        event_index=e["event_index"],
                        theme_connection=e["theme_connection"],
                    )
                    for e in events
                ],
            )
        )
        if verbose:
            fitted = ""
            if (start, end) != (proposed_start, proposed_end):
                fitted = f" (proposed {proposed_start}-{proposed_end})"
            print(
                f"  Chapter '{chapter.title}': {len(events)} event(s), "
                f"{start}-{end}{fitted}"
            )

    if out_of_range:
        print(
            f"Note: {out_of_range} curated event(s) fell outside every proposed "
            "chapter span and were attached to the nearest chapter, which was "
            "widened to fit them."
        )
    if len(chapters) < 2:
        print(
            f"WARNING: only {len(chapters)} chapter(s) hold events. The story's "
            "timeline will be very flat — consider revisiting the person "
            "selection or the topic."
        )

    return chapters


def phase4_historical_context(
    plan: MetaStoryPlan,
    chapters: List[ChapterWithEvents],
    registry: Dict[str, Any],
    client: OpenAI,
    model: str,
    max_events_per_chapter: int = 2,
    verbose: bool = False,
) -> List[ChapterWithEvents]:
    """
    Phase 4: Add well-known historical context events to chapters.

    Selects historical events that directly affected the specific people
    in this story, not generic world history landmarks.

    Args:
        plan: Output from Phase 1
        chapters: Output from Phase 3 (chapters with filtered person events)
        registry: Persons registry (for name/role lookup)
        client: OpenAI client
        model: Model to use
        max_events_per_chapter: Maximum historical events per chapter
        verbose: Enable logging

    Returns:
        Same chapters list with historical_context populated
    """
    if verbose:
        print("\n=== PHASE 4: Historical Context ===")

    # Build people summary so AI knows who it's selecting context for
    people_summary_parts = []
    for person_ref in plan.selected_people:
        person_id = person_ref.person_id
        # Find person in registry for name/roles
        person_info = None
        for person in registry.get("people", []):
            if person.get("id") == person_id:
                person_info = person
                break
        if person_info:
            name = person_info.get("name", person_id)
            roles = ", ".join(person_info.get("primaryRoles", []))
            birth = person_info.get("birthDate", "?")
            death = person_info.get("deathDate", "")
            lifespan = f"{birth} – {death}" if death else f"b. {birth}"
            people_summary_parts.append(
                f"  - {name} ({roles}, {lifespan}): {person_ref.relevance_note}"
            )

    people_context = "\n".join(people_summary_parts)

    # Build chapters context with person names on events
    chapters_context_parts = []
    # Build person_id -> name lookup
    person_name_lookup = {}
    for person in registry.get("people", []):
        person_name_lookup[person.get("id", "")] = person.get(
            "name", person.get("id", "")
        )

    for chapter in chapters:
        event_lines = []
        for e in chapter.person_events:
            pname = person_name_lookup.get(e.person_id, e.person_id)
            event_lines.append(f"    - {pname}: {e.event_title}")
        event_list = "\n".join(event_lines) if event_lines else "    (none)"

        chapters_context_parts.append(
            f'  Chapter: "{chapter.title}" (ID: {chapter.id})\n'
            f"  Date range: {chapter.date_start} to {chapter.date_end}\n"
            f"  Person events:\n{event_list}"
        )

    chapters_context = "\n\n".join(chapters_context_parts)

    prompt = f"""META-STORY:
  Title: {plan.title}
  Tagline: {plan.tagline}

PEOPLE IN THIS STORY:
{people_context}

CHAPTERS:

{chapters_context}

TASK: For each chapter, suggest 0-{max_events_per_chapter} well-known historical events that
DIRECTLY AFFECTED the specific people in this story. Every event must have a clear, concrete
connection to at least one person's life, work, or circumstances.

SELECTION PRINCIPLE — RELEVANCE OVER FAME:
- Do NOT pick generic "big history" events just because they happened during the time period
- ONLY pick events that demonstrably shaped the lives or work of the people listed above
- Ask yourself: "Did this event change what these specific people did, where they lived, or how they worked?"
- If the answer is no, do NOT include it — even if it's a famous world event

GOOD EXAMPLES (tailored to the people):
- "World War II" for computing pioneers who worked on codebreaking or ballistics
- "Fall of the Wall" for people who lived in or were affected by divided Germany
- "Great Depression" for architects whose commissions dried up in the 1930s

BAD EXAMPLES:
- "Russian Revolution" when none of the people lived in or were affected by Russia
- "Moon Landing" when the story is about 19th-century painters
- "Spanish Flu" when none of the people were notably affected by it
- "Industrial Revolution" — a gradual epoch, not a discrete event
- "Age of Enlightenment" — too fuzzy, no clear start/end moment

RULES:
- Titles must be SHORT (1-3 words): "World War II", "Cold War", "Fall of the Wall"
- Description: ONE sentence explaining how this event affected the people in this story specifically
  * GOOD: "The war forced Turing into codebreaking work at Bletchley Park"
  * BAD: "A global conflict that reshaped the 20th century"
- These are background landmarks, NOT field-specific milestones or discoveries
- AVOID FUZZY EPOCHS: Do not pick gradual processes or long eras that lack a discrete moment
  * NO: "Industrial Revolution", "Age of Enlightenment", "Renaissance", "Digital Age"
  * YES: "World War I", "Fall of the Wall", "Great Fire of London" — events with clear boundaries
  * If a span exceeds ~15 years, it's probably an epoch, not an event
- Do NOT repeat events already covered by the person events listed above
- AVOID TEMPORAL OVERLAPS: events across all chapters must not overlap in time
- Use date_end for eras/wars; leave null for single moments
- Only include events you are certain about. Do not invent.
- For wikipedia_url: provide the full URL if confident the article exists, else null
- For priority: rate 1-3 how strongly each event defines this story (3 = a defining
  landmark that most shaped these people or that any reader would recognise, 2 = notable,
  1 = minor background detail). Reserve 3 for the few events that truly anchor the era —
  overlapping labels are decluttered by priority, so the highest-priority ones win space.
- Many chapters may need ZERO events — only include one if it truly shaped these people's lives
"""

    try:
        response = client.beta.chat.completions.parse(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "You select well-known historical events that DIRECTLY AFFECTED "
                    "the specific people in a biographical story. Only pick events with a clear, "
                    "concrete connection to the people's lives — never generic world history filler.",
                },
                {"role": "user", "content": prompt},
            ],
            response_format=HistoricalContextResponse,
        )

        result = response.choices[0].message
        if result.parsed:
            context_response = result.parsed

            # Build lookup from chapter_id to historical events
            context_by_chapter = {}
            for ch_events in context_response.chapter_events:
                context_by_chapter[ch_events.chapter_id] = ch_events.events

            # Apply historical context to chapters
            total_events = 0
            for chapter in chapters:
                events = context_by_chapter.get(chapter.id, [])
                chapter.historical_context = events
                total_events += len(events)

                if verbose:
                    print(f"  Chapter '{chapter.title}': {len(events)} events")
                    for evt in events:
                        title = evt.title.encode("ascii", "replace").decode("ascii")
                        date_range = evt.date_start
                        if evt.date_end:
                            date_range += f" to {evt.date_end}"
                        print(f"    {title} ({date_range})")

            if verbose:
                print(f"\n  Total historical context events: {total_events}")

            return chapters

        elif result.refusal:
            print(f"Error: Model refused Phase 4: {result.refusal}")
            return chapters
        else:
            print(
                "Warning: Phase 4 returned no parsed result, skipping historical context"
            )
            return chapters

    except APIStatusError as e:
        message = ""
        try:
            error_body = e.response.json() if hasattr(e.response, "json") else {}
            message = error_body.get("error", {}).get("message", str(e))
        except Exception:
            message = str(e)
        print(f"Error: Phase 4 API error: {e.status_code} {message}")
        return chapters
    except Exception as e:
        print(f"Warning: Phase 4 failed: {e}")
        return chapters


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
    story_id: str,
    registry: Dict[str, Any],
    hints: Optional[SelectionHints] = None,
    model: str = DEFAULT_MODEL,
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
        lastUpdated=now,
    )

    # Build generation metadata
    generation_metadata = GenerationMetadata(hints=hints, model=model, generated_at=now)

    dataset = MetaStoryDataset(
        dataset="meta_story",
        created_on=now,
        meta_story=meta_story,
        generation_metadata=generation_metadata,
        subtopics=plan.subtopics,
        chapters=chapters,
        conclusion=plan.conclusion,
    )

    result = dataset.model_dump(exclude_none=False)

    # Phase 5: Social network — derived deterministically from the selected
    # people's ego networks (main people + bridging secondary people).
    result["social_network"] = build_social_network(person_ids, registry)

    return result


def phase6_network_narration(
    dataset: Dict[str, Any],
    client: OpenAI,
    model: str,
    verbose: bool = False,
) -> None:
    """Phase 6: Write short story texts for the network's clusters ("circles").

    The UI narrates the social network with scroll-over cards, one per cluster
    (derived deterministically by ``derive_clusters``, mirroring the client).
    This phase asks the model for a short narrative per circle plus an intro,
    stored as ``social_network.narration``. Failures are non-fatal — without
    narration the UI falls back to listing the ties.
    """
    network = dataset.get("social_network") or {}
    clusters = derive_clusters(network)
    if not clusters:
        return

    meta = dataset.get("meta_story", {})
    cluster_briefs = []
    for cluster in clusters:
        members = ", ".join(
            f"{n['name']} ({n.get('birth_year') or '?'}; "
            f"{', '.join(n.get('roles') or []) or 'role unknown'})"
            for n in cluster["mains"]
        )
        bridges = ", ".join(n["name"] for n in cluster["secondaries"]) or "none"
        ties = "\n".join(
            f"  - {link['source']} <-> {link['target']} "
            f"[{link.get('relationship_type', '')}, {link.get('strength', '')}]: "
            f"{link.get('relationship_description', '')}"
            for link in cluster["links"]
        )
        cluster_briefs.append(
            f"Circle key: {cluster['key']}\n"
            f"Main people: {members}\n"
            f"Bridging acquaintances: {bridges}\n"
            f"Ties:\n{ties}"
        )
    briefs = "\n\n".join(cluster_briefs)

    prompt = f"""Write the narration for the social-network section of the meta story
"{meta.get("title", "")}" ({meta.get("tagline", "")}).

The network is shown as a graph; while the reader scrolls, each "circle"
(cluster of closely connected people) is highlighted with a card containing a
short story text. Write those texts.

CIRCLES:

{briefs}

REQUIREMENTS:
- intro: a 2-3 sentence opening paragraph, written the way an author opens a
  chapter — evocative, setting up the human theme that runs through this
  network (what kind of bonds it is made of, what world it spans, what it
  builds toward). Do NOT name individual people, do NOT preview or list the
  specific circles/clusters (naming them here would spoil what follows), and
  do NOT explain how to read the graph.
- One entry per circle, in the given order, with `key` copied EXACTLY.
- Each circle title: a short, evocative headline (2-5 words) in the spirit of a
  book chapter — capture the theme or bond that unites the circle. Do NOT list
  the people's names; the names appear in the text below it.
- Each circle text: 2-4 sentences of flowing prose that weave the ties into a
  miniature story — how these people found each other, what bound them, who
  bridged whom. Ground every claim in the tie descriptions above; do not invent
  facts. No bullet points, no lists of relationships.
- Refer to people by natural name forms (e.g. "Babbage" on second mention).
- Tone: vivid but factual, matching a biographical story collection.
- NEVER address the reader. This is a data story, not a tutorial or a guided
  tour: no "you"/"your"/"we"/"us", no imperatives aimed at the audience
  ("Follow...", "Trace...", "Explore..."), no references to scrolling,
  clicking, or the graph as an interface. Write in the third person, about
  the people themselves."""

    try:
        response = client.beta.chat.completions.parse(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a skilled narrative writer turning "
                    "relationship data into short, factual story texts.",
                },
                {"role": "user", "content": prompt},
            ],
            response_format=NetworkNarrationResult,
        )
        result = response.choices[0].message
        if not result.parsed:
            print("Warning: Phase 6 returned no parsed result, skipping narration")
            return
        by_key = {c.key: c for c in result.parsed.circles}
        missing = [c["key"] for c in clusters if c["key"] not in by_key]
        if missing:
            print(f"Warning: Phase 6 narration missing circles {missing}, skipping")
            return
        network["narration"] = {
            "intro": result.parsed.intro,
            "circles": [
                {
                    "key": c["key"],
                    "title": by_key[c["key"]].title,
                    "text": by_key[c["key"]].text,
                }
                for c in clusters
            ],
        }
        if verbose:
            print(f"  Narrated {len(clusters)} circle(s)")
    except Exception as e:
        print(f"Warning: Phase 6 network narration failed: {e}")


def save_meta_story(
    story_id: str, dataset: Dict[str, Any], verbose: bool = False
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
    story_id: str, meta_story_data: Dict[str, Any], verbose: bool = False
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
        "lastUpdated": ms["lastUpdated"],
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
        help="Topic title (e.g., 'Computing Pioneers', 'Renaissance Artists')",
    )
    parser.add_argument(
        "--person-ids",
        help="Comma-separated person IDs to manually specify (skip AI selection)",
    )
    parser.add_argument(
        "--force", action="store_true", help="Overwrite existing meta-story"
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"OpenAI model (default: {DEFAULT_MODEL})",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=20,
        help="Number of events to process per AI call in Phase 3 (default: 20)",
    )
    parser.add_argument(
        "--skip-ai-filtering",
        action="store_true",
        help="Skip AI event filtering (Phase 3) - include all collected events",
    )
    parser.add_argument(
        "--hints",
        help="Selection hint string (e.g., 'include Jugendstil architects'), or 'none' to disable hint reuse",
    )
    parser.add_argument(
        "--skip-historical-context",
        action="store_true",
        help="Skip Phase 4 (historical context enrichment)",
    )
    parser.add_argument(
        "--max-context-events",
        type=int,
        default=2,
        help="Maximum historical context events per chapter (default: 2)",
    )
    parser.add_argument(
        "--skip-network-review",
        action="store_true",
        help="Skip Phase 5b (AI review/enrichment of the derived social network)",
    )
    parser.add_argument(
        "--skip-compose",
        action="store_true",
        help="Skip Phase 8 (top-down story composition)",
    )
    parser.add_argument(
        "--no-exclusions",
        action="store_true",
        help="Phase 8: never drop people from the story (text composition only)",
    )
    parser.add_argument(
        "--skip-redundancy-pass",
        action="store_true",
        help="Phase 8: skip the pass that rewrites article slots repeating "
        "each other or the captions",
    )
    parser.add_argument(
        "--skip-map",
        action="store_true",
        help="Skip Phase 7 (geographic map section)",
    )
    parser.add_argument(
        "--skip-translate",
        action="store_true",
        help="Skip automatic translation after generation",
    )
    parser.add_argument(
        "--translate-langs",
        default="de",
        help="Comma-separated language codes to translate to after generation (default: de)",
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

    # Handle hints - automatic reuse by default
    hints = None
    if args.hints:
        if args.hints.lower() == "none":
            # Explicitly disable hint reuse
            if args.verbose:
                print("Hints: Disabled (--hints none)")
        else:
            # Use the hint string directly
            hints = SelectionHints(hint=args.hints)
            if args.verbose:
                print(f"Hints: {args.hints}")
    else:
        # Default: try to reuse existing hints
        existing_hints = load_existing_hints(story_id)
        if existing_hints:
            hints = existing_hints
            if args.verbose:
                print("Hints: Reusing from existing meta-story")
        else:
            if args.verbose:
                print("Hints: None (no existing hints found)")

    print(f"Generating meta-story: {args.topic_title}")
    print(f"Story ID: {story_id}")

    # Phase 1: Story planning
    plan = phase1_story_planning(
        topic_title=args.topic_title,
        registry=registry,
        client=client,
        model=args.model,
        manual_person_ids=manual_person_ids,
        hints=hints,
        verbose=args.verbose,
    )

    if not plan:
        print("ERROR: Phase 1 failed")
        sys.exit(1)

    # Phase 2: Event collection (everything dated, unfiltered)
    collected_events = phase2_event_collection(
        plan=plan, registry=registry, verbose=args.verbose
    )

    # Phase 3: AI event filtering
    if args.skip_ai_filtering:
        if args.verbose:
            print("\n=== PHASE 3: AI Event Filtering (SKIPPED) ===")
        curated_events = [
            {**e, "theme_connection": "Included without AI filtering"}
            for e in collected_events
        ]
    else:
        curated_events = phase3_ai_event_filtering(
            plan=plan,
            collected_events=collected_events,
            client=client,
            model=args.model,
            verbose=args.verbose,
            batch_size=args.batch_size,
        )

    # Phase 3b: fit the proposed chapters to the events that survived curation
    chapters = fit_chapters_to_events(plan, curated_events, verbose=args.verbose)

    # Phase 4: Historical context enrichment
    if args.skip_historical_context:
        if args.verbose:
            print("\n=== PHASE 4: Historical Context (SKIPPED) ===")
    else:
        chapters = phase4_historical_context(
            plan=plan,
            chapters=chapters,
            registry=registry,
            client=client,
            model=args.model,
            max_events_per_chapter=args.max_context_events,
            verbose=args.verbose,
        )

    # Build dataset (Phase 5: derive the social network deterministically)
    dataset = build_meta_story_dataset(
        plan, chapters, story_id, registry, hints=hints, model=args.model
    )

    # Phase 5b: AI review of the derived network — enrich with missing direct
    # ties, refine wording, and prune vague/indirect ones. Runs BEFORE
    # clustering/narration so the circles reflect the reviewed graph. Non-fatal:
    # on any failure the deterministic network is kept.
    if args.skip_network_review:
        if args.verbose:
            print("\n=== PHASE 5b: Network Review (SKIPPED) ===")
    else:
        if args.verbose:
            print("\n=== PHASE 5b: Network Review ===")
        dataset["social_network"] = review_social_network(
            dataset.get("social_network") or {},
            client=client,
            model=args.model,
            reasoning_effort=DEFAULT_REASONING_EFFORT,
            verbose=args.verbose,
        )

    # Phase 6: narrate the social network's circles (non-fatal on failure).
    # This is the baseline narration; Phase 8 rewrites it in the story's
    # unified voice, but keeping Phase 6 means the story still has narration
    # when composition is skipped or fails.
    if args.verbose:
        print("\n=== PHASE 6: Network Narration ===")
    phase6_network_narration(
        dataset, client=client, model=args.model, verbose=args.verbose
    )

    # Phase 7: geographic map section — rate the story's located events,
    # cluster them geographically, and narrate the top clusters as map stops
    # (with an option to discard accidental groupings). Runs BEFORE the
    # composer so the composer can reorder/curate the stops; its exclusion
    # cascade prunes the map deterministically. Non-fatal.
    if args.skip_map:
        if args.verbose:
            print("\n=== PHASE 7: Map Section (SKIPPED) ===")
    else:
        if args.verbose:
            print("\n=== PHASE 7: Map Section ===")
        try:
            geo_map = generate_geo_map(
                dataset,
                registry,
                client,
                model=args.model,
                reasoning_effort=DEFAULT_REASONING_EFFORT,
                verbose=args.verbose,
            )
            if geo_map is not None:
                dataset["geo_map"] = geo_map
        except Exception as e:
            print(f"Warning: map section generation failed: {e}")

    # Phase 8: story composer — reads the assembled story top-down (with
    # Wikipedia context) and rewrites it as two layers: the captions bound to
    # the timeline, graph and map, and the article running between them, which
    # carries the context those components cannot show. Also curates — its own
    # network circle organization, curated map stops, and optionally dropping
    # clearly disconnected people. Non-fatal: on failure the bottom-up texts
    # are kept.
    if args.skip_compose:
        if args.verbose:
            print("\n=== PHASE 8: Story Composition (SKIPPED) ===")
    else:
        if args.verbose:
            print("\n=== PHASE 8: Story Composition ===")
        composed = compose_meta_story_dataset(
            dataset,
            registry,
            client,
            model=args.model,
            allow_exclusions=not args.no_exclusions,
            deduplicate=not args.skip_redundancy_pass,
            verbose=args.verbose,
        )
        if composed is not None:
            dataset = composed
        else:
            print("Warning: story composition failed, keeping bottom-up texts")

    # Save files
    if not save_meta_story(story_id, dataset, verbose=args.verbose):
        sys.exit(1)

    if not update_meta_stories_registry(story_id, dataset, verbose=args.verbose):
        sys.exit(1)

    # Translate the meta story so language versions stay in sync with English.
    # Translation failures are non-fatal: the English reference is complete and
    # `translate_all_persons.py --check` will report the gap.
    if not args.skip_translate:
        from translate_meta_story import translate_meta_story_data

        for lang in [
            code.strip() for code in args.translate_langs.split(",") if code.strip()
        ]:
            print(f"\nTranslating meta-story to '{lang}'...")
            try:
                if translate_meta_story_data(
                    story_id,
                    lang,
                    client,
                    model=args.model,
                    force=True,
                    verbose=args.verbose,
                ):
                    print(f"  Translation to '{lang}' complete")
                else:
                    print(f"  WARNING: translation to '{lang}' failed")
            except Exception as e:
                print(f"  WARNING: translation to '{lang}' failed: {e}")

    print("\nSUCCESS: Meta-story created!")
    print(f"  ID: {story_id}")
    print(f"  People: {len(dataset['meta_story']['person_ids'])}")
    print(f"  Subtopics: {len(dataset['subtopics'])}")
    print(f"  Chapters: {len(dataset['chapters'])}")
    print(
        "  Total person events: "
        f"{sum(len(c.get('person_events') or []) for c in dataset['chapters'])}"
    )
    for excluded in (dataset.get("composition") or {}).get("excluded_people") or []:
        print(f"  Excluded by composer: {excluded['person_id']} — {excluded['reason']}")
    total_context = sum(
        len(c.get("historical_context") or [])
        for c in dataset["chapters"]
        if c.get("historical_context")
    )
    if total_context > 0:
        print(f"  Total historical context events: {total_context}")

    # Display missing people suggestions
    if plan.missing_people_suggestions and len(plan.missing_people_suggestions) > 0:
        print("\nRECOMMENDATIONS: Missing people who would strengthen this meta-story:")
        for i, suggestion in enumerate(plan.missing_people_suggestions, 1):
            print(f"\n  {i}. {suggestion.name} ({suggestion.role})")
            print(f"     {suggestion.reason}")
        print("\n  Consider adding these people to expand the dataset.")

    sys.exit(0)


if __name__ == "__main__":
    main()
