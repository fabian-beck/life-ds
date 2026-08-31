"""What the chapter call is told: turn researched events into a story arc.

The events are already decided by the time this runs, so what the call adds is
grouping and headlines—three to five chapters that read as an arc rather than
as a date range.
"""

from typing import List, Optional

from events.schemas import LifeEvent


def build_chapter_generation_prompt(
    merged_events: List[LifeEvent],
    person_name: str,
    birth_date: Optional[str] = None,
    death_date: Optional[str] = None,
) -> str:
    """
    Build prompt for chapter generation based on established events.

    The prompt includes all event details so the AI can create meaningful chapters
    with involved_people and location aggregated from the events.
    """
    prompt = f"PERSON: {person_name}\n"
    if birth_date:
        prompt += f"Born: {birth_date}\n"
    if death_date:
        prompt += f"Died: {death_date}\n"
    prompt += f"\n{'='*60}\n"
    prompt += "ESTABLISHED LIFE EVENTS (chronologically ordered):\n"
    prompt += f"{'='*60}\n\n"

    for idx, event in enumerate(merged_events, 1):
        prompt += f"EVENT {idx}:\n"
        prompt += f"  Date: {event.date}"
        if event.date_end:
            prompt += f" to {event.date_end}"
        prompt += f" (precision: {event.date_precision})\n"
        if event.age is not None:
            prompt += f"  Age: {event.age}\n"
        prompt += f"  Title: {event.title}\n"
        prompt += f"  Description: {event.description}\n"

        if event.locations:
            locations_str = ", ".join(
                [
                    loc.get("name_modern") or loc.get("name_historic", "Unknown")
                    for loc in event.locations
                ]
            )
            prompt += f"  Locations: {locations_str}\n"

        if event.involved_people:
            prompt += f"  Involved people: {', '.join(event.involved_people)}\n"

        prompt += "\n"

    prompt += f"{'='*60}\n"
    prompt += f"Total: {len(merged_events)} events\n"

    return prompt
