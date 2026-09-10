"""Decide which of the retrieved pictures a life's slides actually carry.

Four calls, in order: one writes the searches for the life as a whole, one runs
every planned query and deduplicates the pool, one matches what came back to
events and picks the reference portrait, and one looks at that portrait file
and says whether it depicts the subject. The searches themselves live in
`sources.py` and the ranking in `scoring.py`; what is decided here is which
picture goes where, and whether a picture goes anywhere at all.

An event with no picture is a correct answer. The instruction that asked for
40-60% of slides to be filled is what put a gravestone under fifteen deaths,
and the prompts here say so at length because the matcher judges by filenames
and captions and will otherwise reach for a memorial.

The matcher is also told when each photograph was taken, because a filename
cannot say so. Turing's 1952 conviction carried the facade of the Manchester
County Court Offices: the research had searched for a court in Manchester, Commons
answered with the court building that stands there today, and the matcher,
shown "Facade of Manchester County Court Offices" against "a court in
Manchester convicted Turing", read it as the building where it happened. The
file's own metadata dated the photograph to 2016. That year is now a line of
the listing, and a building found by its kind and its city is named among the
stand-ins no slide may carry.
"""

import os
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from pydantic import BaseModel, Field

from config import (
    BULK_MODEL,
    BULK_REASONING_EFFORT,
    DEFAULT_MODEL,
    LOW_REASONING_EFFORT,
)
from events.images import sources
from events.images.scoring import parse_year_from_date_string
from events.schemas import EventSkeleton
from utils.concurrency import map_concurrently
from utils.model_calls import get_client, parse_structured

# Image search string generation: writing Commons queries, which the search
# itself judges by returning something or nothing.
IMAGE_SEARCH_MODEL = BULK_MODEL
IMAGE_SEARCH_REASONING = LOW_REASONING_EFFORT

# Image-to-event matching. Low rather than none because the same call picks the
# reference portrait — the one output of this step that a reader sees on every
# slide, and the input the portrait step spends an image call on.
IMAGE_MATCH_MODEL = BULK_MODEL
IMAGE_MATCH_REASONING = BULK_REASONING_EFFORT

# Portrait verification. The matcher judges by filenames and captions alone,
# and its portrait pick is the one output of the image step nothing downstream checks —
# a wrong yes quietly becomes the face of the story, which is the config's own
# test for the default model. One call that actually looks at the chosen file.
PORTRAIT_VERIFY_MODEL = DEFAULT_MODEL
PORTRAIT_VERIFY_REASONING = LOW_REASONING_EFFORT


class ImageSearchStrings(BaseModel):
    """AI-generated search strings for finding images across all events."""

    search_strings: List[str] = Field(
        description="List of 20 search strings optimized for Wikimedia Commons"
    )


class ImageEventAssignment(BaseModel):
    """Assignment of a single image to an event."""

    image_id: int = Field(
        description="1-based index of the image from the candidate list"
    )
    event_index: int = Field(
        description="0-based index of the event to assign this image to"
    )
    caption: str = Field(
        description="Clean, concise caption for the image (5-15 words). Describe what the image shows."
    )
    reason: str = Field(
        description="Brief explanation of why this image fits this event"
    )


class PortraitSelection(BaseModel):
    """Selection of a portrait image for the person."""

    image_id: Optional[int] = Field(
        None,
        description="1-based index of the best portrait image, or null if no good portrait found",
    )
    reason: str = Field(description="Brief explanation of portrait selection")


class PortraitVerification(BaseModel):
    """One look at the selected portrait: does it show the subject at all?"""

    depicts_subject: bool = Field(
        description=(
            "True only if the image plausibly depicts the named person "
            "themselves — not someone else the caption mentions"
        )
    )
    reason: str = Field(description="One sentence naming what the image shows")


class ImageAssignmentResult(BaseModel):
    """Result of AI image-to-event matching."""

    portrait: Optional[PortraitSelection] = Field(
        None,
        description="Selection of the best portrait image for the person's profile",
    )
    assignments: List[ImageEventAssignment] = Field(
        default_factory=list,
        description="List of image-to-event assignments. Each image can only be assigned once.",
    )


def generate_image_search_strings(
    event_skeletons: List[EventSkeleton],
    person_name: str,
    model: str = IMAGE_SEARCH_MODEL,
) -> List[str]:
    """
    Use AI to generate 20 optimized search strings for finding images
    across all events at once.
    """
    # Build prompt with all events
    prompt = f"PERSON: {person_name}\n\n"
    prompt += "LIFE EVENTS:\n"
    prompt += "=" * 60 + "\n\n"

    for idx, skeleton in enumerate(event_skeletons):
        prompt += f"Event {idx}: {skeleton.title} ({skeleton.date})\n"
        prompt += f"  Description: {skeleton.description[:200]}...\n\n"

    prompt += "=" * 60 + "\n"
    prompt += "TASK: Generate exactly 20 search strings for Wikimedia Commons\n"
    prompt += "=" * 60 + "\n\n"

    prompt += "CRITICAL: Wikimedia Commons uses SIMPLE keyword matching, not semantic search.\n"
    prompt += "Your search strings must be SHORT and SIMPLE (2-4 words max).\n\n"

    prompt += "SEARCH STRING RULES:\n"
    prompt += "  • Use 2-4 words MAXIMUM per search string\n"
    prompt += "  • Exactly 5 searches are for the PERSON: the name alone, or the name with one generic word. These are what the profile portrait is chosen from\n"
    prompt += "  • The other 15 name THINGS the events name: the building, the machine, the document, the published work, the ship, the award, the institution. A proper name needs no person attached to it\n"
    # The old rule was "ALWAYS combine the person's name with generic terms
    # (city names, professions, etc.)", and Commons answers that form with what
    # a later century built: "Franz Kafka Prague" returns a birthplace plaque, a
    # bronze head, a kinetic sculpture, and a statue before it returns anything
    # Kafka saw. Fifteen of the corpus's death slides carry a gravestone, and
    # this line is where they were found.
    prompt += "  • NEVER search for a commemoration: no 'X memorial', 'X grave', 'X birthplace', 'X plaque', 'X statue', 'X monument', 'X museum', 'X stamp'. Those return what a later century built to remember the person, and this story is about what the person did\n"
    prompt += "  • A generic term must be anchored to something — the person's name or a proper name. NO standalone city names, countries, or professions\n"
    prompt += "  • NO adjectives, NO years, NO descriptive phrases\n"
    prompt += "  • NO long phrases like 'exterior view of' or 'night view'\n\n"

    prompt += "GOOD EXAMPLES (2-4 words):\n"
    prompt += "  • 'Zaha Hadid'\n"
    prompt += "  • 'Vitra Fire Station'\n"
    prompt += "  • 'MAXXI Rome'\n"
    prompt += "  • 'Heydar Aliyev Center'\n"
    prompt += "  • 'Pritzker Prize'\n"
    prompt += "  • 'Zaha Hadid architecture'\n"
    prompt += "  • 'London Aquatics Centre'\n"
    prompt += "  • 'Béla Bartók portrait' (one of the five for the person)\n"
    prompt += "  • 'Bartók phonograph recording' (a thing he worked with)\n\n"

    prompt += "BAD EXAMPLES (too generic, too long, or commemorative):\n"
    prompt += "  • 'Budapest' ❌ (too generic - name what happened there instead)\n"
    prompt += "  • 'composer' ❌ (too generic - use 'Bartók composer' instead)\n"
    prompt += "  • 'Hungary' ❌ (too generic - name the thing instead)\n"
    prompt += "  • 'Bartók memorial Budapest' ❌ (a monument, not the life)\n"
    prompt += "  • 'Kafka birthplace' ❌ (returns the plaque on the wall)\n"
    prompt += "  • 'Turing grave' ❌ (a stone, not a death)\n"
    prompt += "  • 'Vitra Fire Station Weil am Rhein exterior 1993 Zaha Hadid' ❌ (too long)\n"
    prompt += "  • 'Deconstructivist Architecture exhibition 1988 MoMA New York' ❌ (too long)\n"
    prompt += "  • 'ancient Sumerian city ruins Iraq Ur archaeological site' ❌ (too long)\n\n"

    prompt += "CRITICAL RULE: Never search for standalone generic terms (cities, countries, professions),\n"
    prompt += (
        "and never search for what was built afterwards to remember this person.\n"
    )

    if not os.getenv("OPENAI_API_KEY"):
        # Fallback: generate basic search strings
        return [f"{person_name}", f"{person_name} portrait"]

    client = get_client()

    parsed = parse_structured(
        client,
        model=model,
        reasoning_effort=IMAGE_SEARCH_REASONING,
        input=[
            {
                "role": "system",
                "content": "You are an expert at crafting search queries for Wikimedia Commons to find historically relevant images for biographical timelines.",
            },
            {"role": "user", "content": prompt},
        ],
        text_format=ImageSearchStrings,
        label="Image search strings",
    )
    if parsed is not None:
        return parsed.search_strings[:20]

    # Fallback
    return [person_name]


# Two searches per event, not the three or four the research wrote. They are ordered,
# the first names what the report is most about, and every one of them costs a
# request now and a line of the matcher's prompt afterwards.
EVENT_IMAGE_QUERIES_PER_EVENT = 2


def plan_event_image_searches(
    queries_by_event: Sequence[Sequence[str]],
    limit: int = EVENT_IMAGE_QUERIES_PER_EVENT,
) -> Dict[int, List[str]]:
    """The per-event Commons searches, as a map from event index to queries.

    The research already names what would illustrate each event while it still has
    the researched material in front of it — the machine, the building, the
    document — and those searches went to the background report and nowhere
    else. The twenty searches written for the whole life cannot do that job:
    they are written from titles and truncated descriptions, and the only thing
    they reliably know about an event is the person and the city it happened
    in, which is the search that returns a plaque.
    """
    planned: Dict[int, List[str]] = {}
    for index, queries in enumerate(queries_by_event):
        kept: List[str] = []
        for query in queries or []:
            text = " ".join(str(query or "").split())
            if text and text not in kept:
                kept.append(text)
            if len(kept) >= limit:
                break
        if kept:
            planned[index] = kept
    return planned


def execute_batch_image_search(
    search_strings: List[str],
    images_per_query: int = 10,
    event_queries: Optional[Dict[int, List[str]]] = None,
) -> List[Dict[str, Any]]:
    """
    Execute all search queries against Wikimedia Commons and Openverse.

    ``event_queries`` maps an event index to the searches written for that
    event; their hits are tagged with ``for_event`` so the matcher knows which
    event a candidate was found for. They come first, because deduplication
    keeps the first sighting of a URL and the tag is worth more than the order.

    The queries of one group are sent side by side and their answers merged
    in the group's own order, so the result is the one the serial loop
    produced, minus the wait: forty searches of half a second each were
    twenty seconds spent on nothing that depended on anything.

    Returns deduplicated list of image candidates with metadata.
    """
    all_images: List[Dict[str, Any]] = []
    seen_urls: Set[str] = set()

    def safe(query: str) -> str:
        return query.encode("ascii", "replace").decode("ascii")

    def commons(query: str) -> List[Dict[str, Any]]:
        try:
            return sources.search_wikimedia_commons(query, limit=images_per_query)
        except Exception as e:
            print(f"        Warning: Search failed for '{safe(query)}': {e}")
            return []

    def openverse(query: str) -> List[Dict[str, Any]]:
        try:
            return sources.search_openverse(query, limit=images_per_query)
        except Exception as e:
            print(f"        Warning: Search failed for '{safe(query)}': {e}")
            return []

    def keep(
        results: List[Dict[str, Any]],
        provider: Optional[str] = None,
        for_event: Optional[int] = None,
    ) -> None:
        # Merged on the calling thread, in query order: the first sighting of a
        # URL wins, and which sighting is first is decided here, not by the
        # order the searches happened to answer in.
        for img in results:
            if img["url"] in seen_urls:
                continue
            seen_urls.add(img["url"])
            if provider:
                img["provider"] = provider
            if for_event is not None:
                img["for_event"] = for_event
            all_images.append(img)

    # Commons only for these: they name things, and the thing-shaped query is
    # what Commons indexes well. Openverse contributes breadth to the person
    # searches below, where breadth is what is missing.
    if event_queries:
        planned = [
            (event_index, query)
            for event_index in sorted(event_queries)
            for query in event_queries[event_index]
        ]
        print(f"    [Per event] {len(planned)} search(es) from the researched events:")
        for event_index, query in planned:
            print(f"      Event {event_index}: '{safe(query)}'")
        found = map_concurrently([query for _, query in planned], commons)
        for (event_index, _), results in zip(planned, found):
            keep(results, provider="wikimedia", for_event=event_index)
        print(f"      Found {len(all_images)} unique images for named things")

    # Search Wikimedia Commons for the searches written for the whole life
    print("    [Source 1/2] Wikimedia Commons:")
    for query in search_strings:
        print(f"      Searching: '{safe(query)}'")
    for results in map_concurrently(search_strings, commons):
        keep(results, provider="wikimedia")

    commons_count = len(all_images)
    print(f"      Found {commons_count} unique images from Commons and events")

    # Search Openverse (aggregates Flickr, museums, etc.)
    print("    [Source 2/2] Openverse (Flickr, museums, etc.):")
    for query in search_strings:
        print(f"      Searching: '{safe(query)}'")
    for results in map_concurrently(search_strings, openverse):
        keep(results)

    openverse_count = len(all_images) - commons_count
    print(f"      Found {openverse_count} unique images from Openverse")

    print(f"    Total unique images found: {len(all_images)}")
    return all_images


# The picture that stands in for the thing instead of showing it. Both calls
# that choose pictures are held to this — the one that puts a picture on a slide
# and the one that puts pictures under a report — because they used to disagree
# about it and only one of them was right. The report critic has rejected "a
# modern memorial, plaque, or reenactment standing in for the thing itself"
# since it was written; the slide matcher listed "Memorial/plaque -> later
# events or death" among its GOOD MATCHES. The slide is the picture the reader
# actually meets, and the corpus records what that permission bought: a grave on
# fifteen of the death slides, a birthplace plaque on Kafka's birth, a
# commemorative sparrow on Einstein's.
STAND_IN_REJECTION_INSTRUCTIONS = (
    "- a memorial, plaque, gravestone, tomb, statue, bust, commemorative "
    "stamp, coin, or street sign standing in for what it commemorates. A "
    "plaque on a house is a picture of a plaque, not of the birth it marks, "
    "and a grave is not a picture of a death. The one exception is an event "
    "that is ABOUT the object itself — the monument unveiled, the medal "
    "awarded, the burial described. The test is whether the event names the "
    "thing, not whether the thing names the person\n"
    "- a present-day photograph of an institution's buildings, campus, or "
    "signage standing in for the institution. A university logo on a wall is "
    "a picture of a wall\n"
    "- a photograph of whatever building of some kind now stands in a city "
    "the text names: the county court offices found for 'a court in "
    "Manchester', the hospital found for 'a hospital in Vienna', the station "
    "found for 'arrived in Berlin'. A building illustrates an event only when "
    "the text names THAT building and it stood at the time. A match between "
    "the kind of place and the city is not a match, and a photograph taken "
    "decades after the event shows what stands there now, whatever its name\n"
    "- a picture that merely shares a name or a word with the text. A firm "
    "called Morcom is not Christopher Morcom, and a map of the town of "
    "Banbury is not the Banbury sheets. A place that lent its name to a thing "
    "is not that thing\n"
    "- a generic stock photograph of an everyday object — an apple, a cup, a "
    "letter, a laboratory bench — standing in for the particular one the text "
    "describes. Anybody's apple is not a picture of that apple\n"
)


def image_year_taken(img: Dict[str, Any]) -> Optional[int]:
    """The year a candidate photograph was made, or None when the source did
    not say. Commons reports it as `DateTimeOriginal`; Openverse reports no
    date at all."""
    return parse_year_from_date_string(str(img.get("dateTimeOriginal") or ""))


def build_image_match_prompt(
    candidate_images: List[Dict[str, Any]],
    event_skeletons: List[EventSkeleton],
    person_name: str,
) -> str:
    """What the matcher is shown: the events, the candidates, and the rules.

    Built here rather than at the call site so that the rules the corpus
    depends on can be read without paying for a model call.
    """
    prompt = f"PERSON: {person_name}\n\n"

    prompt += "LIFE EVENTS:\n"
    prompt += "=" * 60 + "\n"
    for idx, skeleton in enumerate(event_skeletons):
        prompt += f"[Event {idx}] {skeleton.title} ({skeleton.date})\n"
        prompt += f"    {skeleton.description[:150]}...\n\n"

    prompt += "\n" + "=" * 60 + "\n"
    prompt += "AVAILABLE IMAGES:\n"
    prompt += "=" * 60 + "\n\n"

    for idx, img in enumerate(candidate_images, 1):
        prompt += f"[Image {idx}]\n"
        prompt += f"  Filename: {img['filename']}\n"
        prompt += f"  Caption: {img['caption'][:200]}\n"
        # When the photograph was made, from the file's own metadata. The
        # filename of a present-day photograph names the thing as if it were
        # timeless, and the one fact that gave the Manchester court facade
        # away — taken in 2016, for a conviction in 1952 — was in a field the
        # matcher was never shown. Left out when the source reports no date,
        # which is most of Openverse; a guessed year would be a hint pointing
        # at nothing.
        taken = image_year_taken(img)
        if taken is not None:
            prompt += f"  Taken: {taken}\n"
        # Where the picture came from, when it came from one event's own
        # searches rather than from the twenty written for the whole life. The
        # per-event searches name things — the machine, the building, the
        # document — so a candidate carrying this line is already a candidate
        # for something in particular.
        if img.get("for_event") is not None:
            prompt += f"  Searched for: Event {img['for_event']}\n"
        prompt += "\n"

    prompt += "=" * 60 + "\n"
    prompt += "TASK: Select portrait AND assign images to events\n"
    prompt += "=" * 60 + "\n\n"

    prompt += "TWO TASKS:\n"
    prompt += "1. Select the BEST PORTRAIT image for this person's profile\n"
    prompt += "2. Match other images to specific life events\n\n"

    prompt += "PORTRAIT SELECTION:\n"
    prompt += "  • Choose ONE image that depicts this person visually\n"
    prompt += "  • ACCEPTABLE: photographs, paintings OF the person, drawings OF the person, sculptures/statues OF the person\n"
    prompt += "  • Prefer: clear depictions of the face, well-known portraits, professional photos\n"
    prompt += "  • For PRE-PHOTOGRAPHY historical figures: period paintings, sculptures, tomb effigies, coins, seals, medieval manuscripts are acceptable\n"
    prompt += "  • ACCEPTABLE: Statues and sculptures that clearly depict the person's likeness (bust, full statue)\n"
    prompt += "  • NEVER SELECT: buildings, plaques, street signs, memorial plaques without a face/likeness\n"
    prompt += "  • NEVER SELECT: artworks CREATED BY the person (we want depictions OF them, not BY them)\n"
    prompt += "  • NEVER SELECT: costume illustrations from books like 'Costumes of All Nations', 'Trachten der Völker', or similar costume/fashion reference books - these are GENERIC costume drawings, NOT actual portraits\n"
    prompt += "  • NEVER SELECT: modern imaginative recreations where no historical likeness exists (speculative illustrations)\n"
    prompt += "  • If no actual depiction of the person exists, set portrait to null\n"
    prompt += "  • The portrait image will NOT be used for any event\n\n"

    prompt += "EVENT IMAGE MATCHING:\n"

    prompt += "ASSIGNMENT RULES:\n"
    prompt += "  • Each image can be assigned to AT MOST one event\n"
    prompt += "  • Each event can have AT MOST one image\n"
    prompt += "  • Only assign if the image DIRECTLY relates to that specific event\n"
    prompt += "  • A candidate marked 'Searched for: Event N' was retrieved by a query written for that event. Treat it as a lead, not an instruction — it still has to pass every rule below\n"
    prompt += "  • A candidate's 'Taken: YEAR' line is when the photograph was made, from the file's own metadata. A photograph taken decades after the event shows what stands there now. It can still show the thing itself — a preserved machine, a document, a building the event names that stood then — but it is never a picture of a place the event names only by its kind and its city\n"
    # No quota. The old one read "Aim for 40-60% of events to have images", and
    # a quota asked of a call that cannot see its candidates is a quota met with
    # whatever shares a word with the event: the corpus landed on 47% and paid
    # for it in gravestones. The picture the reader meets is the largest thing
    # on the slide, and a wrong one costs more than an empty space does.
    prompt += "  • An event with NO image is a normal, correct outcome. There is no target number and no quota — assigning nothing to two thirds of the events is a good answer if the candidates deserve nothing better\n"
    prompt += "  • Ask of each assignment: could this picture be printed beside this event with a straight face? If you have to explain the connection, the answer is no\n\n"

    prompt += "GOOD MATCHES:\n"
    prompt += "  • Document/publication image → event about publishing that work\n"
    prompt += "  • Photograph of a building the event NAMES, where the event happened inside it and it stood at the time\n"
    prompt += "  • Machine/device → event about inventing or working with it\n"
    prompt += "  • Historical photo from specific year → event from that year\n"
    prompt += "  • A picture of a person or object the event NAMES, where that person is not the subject\n\n"

    prompt += "NEVER ASSIGN:\n"
    prompt += STAND_IN_REJECTION_INSTRUCTIONS
    prompt += "- a portrait of the subject. The story already carries one, and a face beside every event says nothing about any of them\n"
    prompt += "- a picture of a different subject from the same era or field, however evocative\n"
    prompt += "- a loosely related image, such as a city photo for an event that merely happened in that city\n\n"

    prompt += "CAPTION GUIDELINES:\n"
    prompt += "  • IMPORTANT: You CANNOT see the images - only filenames and metadata\n"
    prompt += (
        "  • Base captions ONLY on what the filename/metadata explicitly tells you\n"
    )
    prompt += "  • Do NOT assume or describe visual details you cannot verify\n"
    prompt += "  • Keep captions factual and minimal (5-12 words)\n"
    prompt += "  • Use the original source caption/title if it's descriptive enough\n"
    prompt += "  • For buildings/places: just name the place, don't describe what you can't see\n"
    prompt += "  • Good: 'Bletchley Park, wartime codebreaking headquarters'\n"
    prompt += "  • Good: 'The Olympiastadion Munich roof structure'\n"
    prompt += "  • Bad: 'Aerial view showing the curved tensile membrane' (you can't see this)\n"

    return prompt


def match_images_to_events(
    candidate_images: List[Dict[str, Any]],
    event_skeletons: List[EventSkeleton],
    person_name: str,
    model: str = IMAGE_MATCH_MODEL,
) -> Tuple[Dict[int, Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Use AI to match images to events based on caption and filename.
    Also selects the best portrait image for the person.

    Returns:
        Tuple of (event_assignments dict, portrait dict or None)
    """
    if not candidate_images:
        return {}, None

    prompt = build_image_match_prompt(candidate_images, event_skeletons, person_name)

    if not os.getenv("OPENAI_API_KEY"):
        return {}, None

    client = get_client()

    try:
        result = parse_structured(
            client,
            model=model,
            reasoning_effort=IMAGE_MATCH_REASONING,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You are a meticulous image curator for biographical timelines. "
                        "Match images to life events only when there is a clear, direct connection. "
                        "Quality over quantity - it's better to leave events without images than to make poor matches."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            text_format=ImageAssignmentResult,
            label="Image matching",
        )

        if result is None:
            return {}, None

        # Extract portrait selection
        portrait_image: Optional[Dict[str, Any]] = None
        portrait_img_idx: Optional[int] = None
        if result.portrait and result.portrait.image_id is not None:
            portrait_img_idx = result.portrait.image_id - 1  # Convert to 0-based
            if 0 <= portrait_img_idx < len(candidate_images):
                portrait_image = candidate_images[portrait_img_idx].copy()
                # Use original source caption for portrait (already in the image dict)
                # The 'caption' field from search results contains the title/description

        # Build mapping, validating indices
        assignments: Dict[int, Dict[str, Any]] = {}
        used_images: Set[int] = set()

        # Mark portrait as used so it won't be assigned to events
        if portrait_img_idx is not None:
            used_images.add(portrait_img_idx)

        for assignment in result.assignments:
            img_idx = assignment.image_id - 1  # Convert to 0-based
            event_idx = assignment.event_index

            # Validate indices
            if img_idx < 0 or img_idx >= len(candidate_images):
                continue
            if event_idx < 0 or event_idx >= len(event_skeletons):
                continue

            # Check if image already used (including portrait)
            if img_idx in used_images:
                continue

            # Check if event already has image
            if event_idx in assignments:
                continue

            used_images.add(img_idx)
            # Store the image with AI-generated caption
            img_with_caption = candidate_images[img_idx].copy()
            img_with_caption["caption"] = assignment.caption
            assignments[event_idx] = img_with_caption

        return assignments, portrait_image

    except Exception as e:
        print(f"    Warning: Image matching failed: {e}")
        return {}, None


def verify_portrait_depicts_person(
    portrait: Dict[str, Any], person_name: str
) -> Optional[bool]:
    """One look at the selected portrait before it becomes the face of a story.

    The matcher chooses from filenames and captions alone, and its portrait
    pick is the one output of the image step nothing downstream checks — with Openverse
    in the candidate pool, a photograph of the subject's spouse carries the
    subject's name in its caption. This shows the chosen file itself to the
    model. Returns None when the call fails, and the caller keeps the
    unverified pick: the check exists to catch a wrong portrait, not to lose
    a right one to a timeout.
    """
    prompt = (
        f"Is this image a portrait of {person_name} — a depiction of that "
        "person themselves?\n\n"
        "Answer no if it shows someone else (a spouse, relative, or colleague, "
        "even when the caption names the subject), a building, a work made BY "
        "the subject, a costume plate, a memorial or grave, or a group in "
        "which the subject cannot be identified.\n\n"
        "What the file came with:\n"
        f"- Caption: {portrait.get('caption') or 'none'}\n"
        f"- Filename: {portrait.get('filename') or 'none'}\n"
        f"- Source page: {portrait.get('source') or 'none'}\n\n"
        "Judge by what the image shows, not by what the caption claims."
    )
    parsed = parse_structured(
        get_client(),
        model=PORTRAIT_VERIFY_MODEL,
        reasoning_effort=PORTRAIT_VERIFY_REASONING,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": portrait["url"]},
                ],
            }
        ],
        text_format=PortraitVerification,
        label="portrait verification",
    )
    if parsed is None:
        return None
    if not parsed.depicts_subject:
        print(f"    Portrait verification says no: {parsed.reason}")
    return parsed.depicts_subject
