"""Generate one person's life events, phase by phase.

The order is the argument. Phase 1 reads the whole article set and proposes
the events, because how much of a life an event turns on is a comparison only
that call can make. Phase 2 researches them one at a time, given the material
each one needs. The chapter pass groups what came back, the image phase
illustrates it, the geocoder places it, and `enforce_metadata` brings the whole
payload into the shape the corpus is read with before it is written.

`generate_person_events` is the driver that runs all of it; the module it was
split out of keeps the command line.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Tuple,
    cast,
)


from config import (
    BULK_MODEL,
    BULK_REASONING_EFFORT,
    DEFAULT_MODEL,
    DEFAULT_REASONING_EFFORT,
    LOW_REASONING_EFFORT,
    enable_utf8_console,
)
from events.event_classes import EVENT_CLASS_CONFIG
from events.images import assign
from events.normalize import enforce_metadata, normalize_date_for_comparison
from events.prompts.chapters import build_chapter_generation_prompt
from events.prompts.phase1 import build_phase1_prompt
from events.prompts.phase2 import (
    RELATED_ARTICLE_COUNT,
    build_phase2_prompt_base,
    build_phase2_prompt_classified,
    filter_related_articles_for_event,
)
from events.schemas import (
    BirthClassification,
    ChapterGenerationOutput,
    DeathClassification,
    EventDetails,
    EventSkeleton,
    LifeChapter,
    LifeEvent,
    LifePlan,
)
from events.images.scoring import filter_images_by_quality
from icon_categories import normalize_icon
from utils.geocode import geocode_location
from utils.registry import Registry
from utils.model_calls import (
    get_client,
    parse_structured,
    parse_structured_or_raise,
)
from utils.json_io import write_json
from utils.text import slugify
from utils.wikipedia_cache import (
    WIKIPEDIA_SUMMARY_API,
    _fetch_wikipedia_page_from_api,
    _fetch_wikipedia_summary_from_api,
    ensure_cache,
    fetch_wikipedia_extract,
    get_cache_dir,
    get_cached_wikipedia_page,
    get_cached_wikipedia_summary,
)

enable_utf8_console()

# ============================================================================
# AI MODEL AND REASONING EFFORT CONFIGURATION
# ============================================================================
# Configure model and reasoning effort for each phase of the generation
# pipeline. This ensures consistent configuration between AI calls and logging.
#
# Phase 1 and the chapter pass decide what the life is and read the whole
# article set, so they take the default model and a reasoning budget. The three
# phases below them work from material those calls already settled, and every
# field they return is checked afterwards — icons against the catalog, involved
# people against known entities, places against the geocoder, image filenames
# against the fetched candidates — so they take the small model.

PHASE1_REASONING_EFFORT = DEFAULT_REASONING_EFFORT  # Event skeleton generation (medium)

# Event detail research. Every field it returns is checked afterwards — icons
# against the catalog, people against known entities, places against the
# geocoder — which is what qualifies it for the small model. The background
# passage, the one output checked by nobody, is written in a step of its own
# (generate_event_backgrounds.py) on the default model.
PHASE2_MODEL = BULK_MODEL
PHASE2_REASONING_EFFORT = BULK_REASONING_EFFORT


CHAPTER_REASONING_EFFORT = DEFAULT_REASONING_EFFORT  # Chapter generation (medium)
RELATED_ARTICLES_REASONING = LOW_REASONING_EFFORT  # Related article discovery (none)

# Import from cache_wikipedia_materials for related articles functionality
try:
    from cache_wikipedia_materials import fetch_related_articles
except ImportError:
    fetch_related_articles = None  # type: ignore[assignment]

# Import Deutsche Biographie utilities
try:
    from utils.deutsche_biographie import (
        ensure_deutsche_biographie_cache,
        get_cached_deutsche_biographie,
        format_for_prompt as format_db_for_prompt,
    )
except ImportError:
    ensure_deutsche_biographie_cache = None  # type: ignore[assignment]
    get_cached_deutsche_biographie = None  # type: ignore[assignment]
    format_db_for_prompt = None  # type: ignore[assignment]

# Constants
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
REGISTER_PATH = DATA_DIR / "persons.json"
PEOPLE_DIR = DATA_DIR / "people"
_wikipedia_lang: Optional[str] = None


# ============================================================================
# WIKIPEDIA DATA FETCHING (copied from generate_person_dataset.py)
# ============================================================================


def _fetch_wikipedia_page(title: str, lang: Optional[str] = None) -> Dict[str, Any]:
    language = lang or _wikipedia_lang or "en"
    api_url = f"https://{language}.wikipedia.org/w/api.php"
    return _fetch_wikipedia_page_from_api(title, api_url)


def fetch_wikipedia_summary(title: str) -> Dict[str, Any]:
    """Fetch Wikipedia summary from REST API."""
    return _fetch_wikipedia_summary_from_api(title, WIKIPEDIA_SUMMARY_API)


# ============================================================================
# PHASE 1: EVENT SKELETON GENERATION
# ============================================================================


_BIRTH_WORDS = re.compile(r"\b(born|birth|birthplace)\b", re.IGNORECASE)
_DEATH_WORDS = re.compile(
    r"\b(died|dies|death|dying|killed|executed|assassinated|passed away)\b",
    re.IGNORECASE,
)


def _event_field(event: Any, name: str) -> Any:
    """Read a field from an event that may be a model or a plain dict."""
    if isinstance(event, dict):
        return event.get(name)
    return getattr(event, name, None)


def _event_class_type(event: Any) -> Optional[str]:
    """The classification type of an event, whether model or plain dict."""
    event_class = _event_field(event, "event_class")
    if event_class is None:
        return None
    if isinstance(event_class, dict):
        value = event_class.get("type")
    else:
        value = getattr(event_class, "type", None)
    return value if isinstance(value, str) else None


def find_birth_event_index(
    events: List[Any], birth_date: Optional[str] = None
) -> Optional[int]:
    """
    Index of the event that tells the subject's own birth, or None.

    The date decides first: the event must be dated at age 0 (or on the
    person's birth date) *and* open the story or read as a birth. That is what
    keeps a child's or sibling's birth out — those events carry the subject's
    own age, never zero — and it is why the date is asked before the model's
    own classification, which is only consulted when no event is dated there.

    Works on Phase 1 skeletons, merged events, and the plain dicts a stored
    ``life_events.json`` holds.
    """
    birth_day = (birth_date or "").strip()[:10]

    for index, event in enumerate(events):
        age = _event_field(event, "age")
        date = str(_event_field(event, "date") or "")
        dated_at_birth = (age == 0) or (bool(birth_day) and date[:10] == birth_day)
        if not dated_at_birth:
            continue
        text = f"{_event_field(event, 'title') or ''} {_event_field(event, 'description') or ''}"
        if index == 0 or _BIRTH_WORDS.search(text):
            return index

    for index, event in enumerate(events):
        if _event_class_type(event) == "birth":
            return index

    return None


def find_death_event_index(
    events: List[Any], death_date: Optional[str] = None
) -> Optional[int]:
    """
    Index of the event that tells the subject's own death, or None.

    The date decides first, as it does for the birth, but a death is not always
    dated on the day it happened: a duel or a tram accident opens the event days
    earlier. So an event dated on the death date qualifies, and so does the last
    event of the story when it falls in the death year and says someone died.
    Requiring the story's end is what keeps a spouse's or a child's death out.

    The search runs backwards, because a death closes a story the way a birth
    opens one: a plot with three events on the day Stauffenberg died ends with
    the execution, not with the bomb he planted that morning.

    With no death date on record — a life the sources leave open — only a
    closing event whose *title* names a death qualifies. The model's own
    classification is consulted last.

    Works on Phase 1 skeletons, merged events, and the plain dicts a stored
    ``life_events.json`` holds.
    """
    death_day = (death_date or "").strip()[:10]
    last = len(events) - 1

    for index in range(last, -1, -1):
        event = events[index]
        date = str(_event_field(event, "date") or "")
        title = str(_event_field(event, "title") or "")
        text = f"{title} {_event_field(event, 'description') or ''}"
        if death_day:
            dated_at_death = date[:10] == death_day or (
                date[:4] == death_day[:4] and index == last
            )
            if dated_at_death and (index == last or _DEATH_WORDS.search(text)):
                return index
        elif index == last and _DEATH_WORDS.search(title):
            return index

    for index, event in enumerate(events):
        if _event_class_type(event) == "death":
            return index

    return None


def _apply_single_classification(
    events: List[Any],
    index: Optional[int],
    class_type: str,
    build: Callable[[], Any],
) -> None:
    """
    Make exactly the event at ``index`` carry ``class_type``, in place.

    The classification is what the story slide styles, so one the model forgot
    silently costs the reader what the slide would have shown, and one the model
    put on a child's birth or a spouse's death styles the wrong slide. Both are
    repaired here rather than left to the prompt.
    """
    for position, event in enumerate(events):
        classified = _event_class_type(event) == class_type
        if position == index and not classified:
            event.event_class = build()
        elif classified and position != index:
            event.event_class = None


def ensure_birth_classification(
    event_skeletons: List[EventSkeleton], birth_date: Optional[str] = None
) -> Optional[int]:
    """
    Guarantee that at most one event — the subject's own birth — is classified
    as a birth, editing the skeletons in place and returning its index.
    """
    index = find_birth_event_index(event_skeletons, birth_date)
    _apply_single_classification(event_skeletons, index, "birth", BirthClassification)
    return index


def ensure_death_classification(
    event_skeletons: List[EventSkeleton], death_date: Optional[str] = None
) -> Optional[int]:
    """
    Guarantee that at most one event — the subject's own death — is classified
    as a death, editing the skeletons in place and returning its index.
    """
    index = find_death_event_index(event_skeletons, death_date)
    _apply_single_classification(event_skeletons, index, "death", DeathClassification)
    return index


def _validate_chronological_order(event_skeletons: List[EventSkeleton]) -> None:
    """
    Validate that events are in strict chronological order.

    Raises RuntimeError if events are not chronologically ordered.
    """
    # Validate chronological ordering
    for i in range(len(event_skeletons) - 1):
        current_event = event_skeletons[i]
        next_event = event_skeletons[i + 1]

        # Compare dates
        current_date = current_event.date
        next_date = next_event.date

        if current_date > next_date:
            raise RuntimeError(
                f"Events are not in chronological order: "
                f"'{current_event.title}' ({current_date}) comes after "
                f"'{next_event.title}' ({next_date})"
            )

    print(f"  ✓ Chronological order validated ({len(event_skeletons)} events)")


def call_openai_phase1(prompt: str, model: str) -> LifePlan:
    """
    Call OpenAI for Phase 1 using structured outputs.

    Returns:
        LifePlan with person metadata and event skeletons
    """
    client = get_client()

    system = (
        "You are a meticulous historian creating biographical timeline outlines. "
        "Focus on identifying the most significant events in a person's life. "
        "Write event descriptions that are chronologically accurate, factually focused, "
        "and balance professional achievements with personal human context. "
        "Use ISO-8601 dates, include date_precision as 'day', 'month', or 'year'. "
        "The precision is a claim of its own: use 'day' only when the sources state "
        "the day, 'month' only when they state the month, and fall back to 'year' "
        "otherwise. An honest 1814-07 is better than a wrong 1814-07-02. "
        "The year in an event's description must be the year the event is dated to; "
        "when the sources put the event in a different year than you first assumed, "
        "move the date, do not leave the disagreement in the prose. "
        "All output must be in American English only, regardless of source language. "
        "Every text field is plain text rendered verbatim by the interface: never "
        "write Markdown in it — no *emphasis* or **bold**, no `code`, no [links](url), "
        "no headings. A title of a work stands plain in the sentence, without "
        "asterisks or underscores around it."
    )

    instructions = (
        "You will receive a main Wikipedia article about a specific person (the TARGET SUBJECT), plus several related articles for context. "
        "Your task is to create a biographical timeline for the TARGET SUBJECT ONLY - not any of the people mentioned in related articles. "
        "\n\nCRITICAL REQUIREMENT: Produce EXACTLY 12-16 significant life events for the TARGET SUBJECT. NO MORE, NO LESS. "
        "Quality over quantity - select only the most historically significant moments from the TARGET SUBJECT's life. "
        "\n\nCover the TARGET SUBJECT's early life, education, major accomplishments, and later years. "
        "Do not include events that occur after the TARGET SUBJECT's death or that focus on their legacy. "
        "\n\nREMINDER: You must output between 12 and 16 events total. If you find yourself creating more than 16 events, "
        "consolidate related events or remove less significant ones. "
        "\n\nABSOLUTE PROHIBITION: DO NOT create any section, category, or grouping labeled 'Other Events' or similar. "
        "ALL events must be equally important and presented in strict chronological order without any 'miscellaneous' category. "
        "Every event is a main biographical event - there are no 'other' or secondary events. "
        "\n\nIMPORTANT - Event Skeleton Guidelines:\n"
        "- Keep event titles crisp and concise (2-6 words)\n"
        "- Use active, specific language that captures the essence of the event\n"
        "- Avoid generic titles like 'Major Achievement' or 'Important Work'\n"
        "- Examples: 'Birth in London', 'Graduated from Oxford', 'Published First Novel', 'Appointed Prime Minister'\n"
        "- Write rich descriptions (2-4 sentences) that mention context, people involved, and places\n"
        "- DO NOT specify exact locations, images, or detailed sources (Phase 2 will research these)\n"
        "- DO mention places, people, and context in the description naturally\n"
        "- DO NOT add annotations - Phase 2 will handle all annotations\n"
        "\n\nWEIGHT - how much of the life the event turns on:\n"
        "- Give every event a weight from 0.0 to 1.0\n"
        "- Judge it against the OTHER EVENTS OF THIS LIFE, not against history at large: "
        "the most consequential thing this person did is near 1.0 even if the world barely noticed, "
        "and a minor episode is near 0.1 even if it happened somewhere famous\n"
        "- 0.9-1.0: the events the life is remembered for; without them the story is not this person's\n"
        "- 0.6-0.8: turning points — the work, the appointment, the loss that changed the direction\n"
        "- 0.3-0.5: substantial but not pivotal; a post taken, a degree earned, a move made\n"
        "- 0.1-0.2: context and texture — real events that a short telling would leave out\n"
        "- SPREAD THEM OUT. Do not give everything 0.7. A life has a few peaks and many "
        "foothills, and a flat set of weights is the same as no weights at all\n"
        "- Weigh what the event MEANT, not how well documented it is: a quiet decision that "
        "redirected the work outranks a well-attended ceremony that changed nothing\n"
        "\n\nCRITICAL TEMPORAL RULE - Stay in the Moment:\n"
        "- Descriptions must be chronologically confined - describe ONLY what was happening at that time\n"
        "- NEVER reference future events, outcomes, or career retrospectives\n"
        "- FORBIDDEN phrases: 'later he would...', 'this would lead to...', 'in keeping with his future...', 'by the end of his life...'\n"
        "- Write from the perspective of the event itself, not from biographical hindsight\n"
        "- GOOD: 'Schönlein studied medicine in Landshut, learning from Andreas Röschlaub and Friedrich Tiedemann.'\n"
        "- BAD: 'Schönlein studied medicine in Landshut, training that would later shape his bedside teaching method.'\n"
        "\n\nTone and Style Guidelines:\n"
        "- Write as NARRATIVE BIOGRAPHY, not as meta-commentary about biography\n"
        "- Events should flow together to tell a life story, but each event stays focused on itself\n"
        "- FORBIDDEN meta-references: 'the biography records...', 'sources mention...', 'this helps explain why he later...'\n"
        "- FORBIDDEN analytical framing: 'the period mattered less for...', 'these years are significant because...'\n"
        "- Present events as lived experiences, not as literary analysis\n"
        "- Show the story unfolding, don't explain the story's structure\n"
        "- GOOD: 'He completed his dissertation on brain development under Döllinger, exploring comparative embryology in mammals.'\n"
        "- BAD: 'The period mattered less for any single exam than for the intellectual tensions it exposed him to.'\n"
        "- GOOD: 'He studied medicine in Landshut and Würzburg, learning anatomy from Döllinger and clinical methods from Walther.'\n"
        "- BAD: 'Among the teachers named in his biography are Andreas Röschlaub, Friedrich Tiedemann, and...'\n"
        "\n\nPersonal and Human Context:\n"
        "- Balance professional achievements with personal life, relationships, and human experiences\n"
        "- Include family, friendships, emotional impacts, life circumstances where relevant\n"
        "- Don't make EVERY event about career milestones and professional accomplishments\n"
        "- Consider: What was their personal life like? Who were they close to? What challenges did they face?\n"
        "- Professional events can still mention human context (e.g., who supported them, personal motivations)\n"
        "\n\nConciseness Requirements:\n"
        "- Target 2-4 sentences, but make each sentence DIRECT and ECONOMICAL\n"
        "- Avoid verbose constructions, unnecessary clauses, and abstract philosophical framing\n"
        "- Prefer active voice and concrete details over interpretive summaries\n"
        "- Cut any sentence that doesn't add factual information about the event\n"
        "- GOOD: 'He studied in Landshut and Würzburg, learning from anatomists and clinicians.'\n"
        "- BAD: 'This mix of theoretical ambition and concrete anatomical instruction helps explain why he later insisted...'\n"
        "\n\nDEATH EVENT SPECIAL RULE:\n"
        "- Death descriptions must be FACTUAL ONLY: date, location, age, immediate circumstances, cause if known\n"
        "- DO NOT include legacy analysis, historical impact, or career summaries in the death event\n"
        "- Save ALL interpretive retrospectives for the separate 'conclusion' field\n"
        "- The conclusion field exists specifically for legacy - keep death factual\n"
        "- GOOD: 'Schönlein died in Bamberg on 23 January 1864 after years of declining health.'\n"
        "- BAD: 'His death closed a career that helped reshape German clinical training... The most durable part of his legacy was...'\n"
        "\n\nCONCLUSION FIELD (1-2 sentences):\n"
        "- This is WHERE legacy, impact, and retrospective analysis belong\n"
        "- Event descriptions = factual, chronological, in-the-moment\n"
        "- Conclusion = interpretive, retrospective, legacy-focused\n"
        "- The conclusion summarizes the person's life significance AFTER all events are told\n"
        "\n\nEVENT CLASSIFICATION (optional):\n"
        f"For each event skeleton, determine if it matches one of these {len(EVENT_CLASS_CONFIG)} specific biographical event types:\n"
        + "".join(
            [
                f"  {i+1}. {config['name']} - {config['description']}\n"
                for i, config in enumerate(EVENT_CLASS_CONFIG.values())
            ]
        )
        + "\n"
        "Detection guidelines:\n"
        + "".join(
            [config["phase1_guidance"] + "\n" for config in EVENT_CLASS_CONFIG.values()]
        )
        + "For other events (education, appointments, awards): OMIT classification.\n"
        f"Only classify when event CLEARLY matches one of the {len(EVENT_CLASS_CONFIG)} types above.\n"
        "\n\nEach event skeleton must provide: date (start of the event), date_precision, optional date_end/date_end_precision "
        "when the event spans a range, optional date_note for uncertainty, age (null if not applicable), "
        "title, and description. "
        "\nInclude person metadata with name, birth_date, death_date when known, primary_roles, tagline, summary, "
        "wikipedia URL, and portrait info if available.\n"
        "\nPRIMARY_ROLES GUIDELINES (CRITICAL):\n"
        "- Provide exactly 2-3 roles, never more\n"
        "- Use SHORT, GENERIC, LOWERCASE role names (1-2 words max)\n"
        "- Roles must be comparable across different people (standard profession/role names)\n"
        "- GOOD examples: 'mathematician', 'physicist', 'writer', 'composer', 'architect', 'monarch', 'inventor', 'computer scientist', 'philosopher', 'entrepreneur'\n"
        "- BAD examples: 'Founder of Apple Inc' (too specific), 'King of Germany' (use 'monarch'), 'theoretical biologist' (too niche, use 'biologist'), 'Computer pioneer' (use 'computer scientist')\n"
        "- For royalty/rulers: use 'monarch', 'emperor', or 'ruler' - not specific titles\n"
        "- Avoid adjectives and qualifiers: 'scientist' not 'renowned scientist'\n"
        "\nThe tagline should be a catchy, memorable phrase (3-7 words) that captures the person's essence or most notable contribution. "
        "Examples: 'Father of Computer Science', 'The First Programmer', 'Architect of Relativity', 'Pioneer of Structured Programming'."
    )

    parsed = parse_structured_or_raise(
        client,
        model=model,
        reasoning_effort=PHASE1_REASONING_EFFORT,
        input=[
            {"role": "system", "content": system},
            {"role": "user", "content": instructions},
            {"role": "user", "content": prompt},
        ],
        text_format=LifePlan,
        label="Phase 1",
    )

    # Ensure events are sorted chronologically (defensive programming)
    parsed.event_skeletons.sort(key=lambda e: e.date)

    # The birth opens a story and the death closes it, so both are detected
    # rather than hoped for
    birth_index = ensure_birth_classification(
        parsed.event_skeletons, parsed.person.birth_date
    )
    if birth_index is None:
        print("  Phase 1: No birth event found in the plan")
    death_index = ensure_death_classification(
        parsed.event_skeletons, parsed.person.death_date
    )
    if death_index is None:
        print("  Phase 1: No death event found in the plan")

    # Log classifications from Phase 1 (using centralized config)
    classified_count = sum(
        1 for skeleton in parsed.event_skeletons if skeleton.event_class
    )
    if classified_count > 0:
        print(
            f"  Phase 1: Classified {classified_count}/{len(parsed.event_skeletons)} events"
        )
        for skeleton in parsed.event_skeletons:
            if skeleton.event_class:
                class_type = skeleton.event_class.type
                if class_type in EVENT_CLASS_CONFIG:
                    log_format = EVENT_CLASS_CONFIG[class_type]["log_format"]
                    print(f"    - {skeleton.title}: {log_format(skeleton.event_class)}")
                else:
                    # Fallback for unknown types
                    print(f"    - {skeleton.title}: {class_type.upper()}")

    # Validate chronological ordering
    _validate_chronological_order(parsed.event_skeletons)

    return parsed


# ============================================================================
# PHASE 2: EVENT DETAIL RESEARCH
# ============================================================================


def research_event_details(
    event_skeleton: EventSkeleton,
    person_name: str,
    all_related_articles: List[Dict[str, Any]],
    model: str = PHASE2_MODEL,
    retry_count: int = 2,
    deutsche_biographie_text: Optional[str] = None,
    subject_article: Optional[Dict[str, Any]] = None,
) -> EventDetails:
    """
    Research details for a single event with retry logic.
    Uses event-class-specific prompts for targeted research.

    Returns:
        EventDetails with locations, involved_people, sources, icon (NO images - Phase 3)
    """
    # Filter articles
    filtered_articles = filter_related_articles_for_event(
        event_skeleton, all_related_articles, max_articles=RELATED_ARTICLE_COUNT
    )

    # Route to event-class-specific prompt builder (using centralized config)
    if event_skeleton.event_class:
        # All classified events use the generic builder with config
        prompt = build_phase2_prompt_classified(
            event_skeleton,
            person_name,
            filtered_articles,
            deutsche_biographie_text=deutsche_biographie_text,
            subject_article=subject_article,
        )
    else:
        # Standard event (no classification)
        prompt = build_phase2_prompt_base(
            event_skeleton,
            person_name,
            filtered_articles,
            deutsche_biographie_text=deutsche_biographie_text,
            subject_article=subject_article,
        )

    system = (
        "You are a research assistant specializing in biographical event details. "
        "Provide specific, factual information for the given event. "
        "Ensure descriptions are chronologically confined, concise, and balanced. "
        "All output must be in American English only. Be precise with locations and people. "
        "Every text field is plain text rendered verbatim by the interface: apart from "
        "the [[term|display]] annotation markers, never write Markdown — no *emphasis* "
        "or **bold**, no `code`, no [links](url). A title of a work stands plain in "
        "the sentence, without asterisks or underscores around it."
    )

    details = parse_structured(
        get_client(),
        model=model,
        reasoning_effort=PHASE2_REASONING_EFFORT,
        input=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        text_format=EventDetails,
        label=f"Phase 2 research of '{event_skeleton.title}'",
        attempts=retry_count + 1,
    )
    if details is not None:
        return details

    # The event keeps its place in the story with nothing researched about it:
    # no place, nobody involved, no sources, and the neutral icon. Said plainly
    # here because the record itself cannot say it — the story renders a
    # degraded event exactly like a thin one.
    safe_title = event_skeleton.title.encode("ascii", "replace").decode("ascii")
    print(f"    [!] Event not researched, keeping it unresolved: {safe_title}")
    return EventDetails(
        locations=None, involved_people=None, sources=[], event_type_icon="mdi-calendar"
    )


def research_all_event_details(
    event_skeletons: List[EventSkeleton],
    person_name: str,
    all_related_articles: List[Dict[str, Any]],
    model: str = PHASE2_MODEL,
    deutsche_biographie_text: Optional[str] = None,
    subject_article: Optional[Dict[str, Any]] = None,
) -> List[EventDetails]:
    """Research details for all events sequentially (NO images - Phase 3)."""
    # Log classification routing info
    classified_count = sum(1 for skeleton in event_skeletons if skeleton.event_class)
    print(
        f"  Phase 2: Using class-specific prompts for {classified_count}/{len(event_skeletons)} classified events"
    )

    details = []
    for idx, skeleton in enumerate(event_skeletons, 1):
        safe_title = skeleton.title.encode("ascii", "replace").decode("ascii")

        # Show which prompt type is being used
        prompt_type = "STANDARD"
        if skeleton.event_class:
            prompt_type = skeleton.event_class.type.upper()

        print(
            f"  [{idx}/{len(event_skeletons)}] Researching: {safe_title} [{prompt_type}]"
        )

        detail = research_event_details(
            skeleton,
            person_name,
            all_related_articles,
            model,
            deutsche_biographie_text=deutsche_biographie_text,
            subject_article=subject_article,
        )
        details.append(detail)

    return details


# ============================================================================
# EVENT MERGING
# ============================================================================


def merge_event_skeleton_and_details(
    skeleton: EventSkeleton, details: EventDetails
) -> LifeEvent:
    """Merge Phase 1 skeleton with Phase 2 details (NO images - Phase 3)."""

    # Build locations array from EventDetails.locations
    locations = []
    if details.locations and len(details.locations) > 0:
        for loc in details.locations:
            locations.append(
                {
                    "name_historic": loc.name_historic,
                    "name_modern": loc.name_modern,
                    "centroid": loc.centroid,
                    "primary": loc.primary,
                }
            )

    # Annotations come ONLY from Phase 2 (Phase 1 doesn't generate them)
    annotations = details.annotations

    # Merge description (prefer Phase 2 if provided with markers, else Phase 1)
    description = details.description if details.description else skeleton.description

    # Create merged event (NO images yet - assigned in Phase 3, NO chapter yet - assigned in Chapter phase)
    return LifeEvent(
        date=skeleton.date,
        date_precision=skeleton.date_precision,
        date_end=skeleton.date_end,
        date_end_precision=skeleton.date_end_precision,
        date_note=skeleton.date_note,
        age=skeleton.age,
        title=skeleton.title,
        description=description,
        locations=locations,
        involved_people=details.involved_people,
        sources=details.sources if details.sources else [],
        images=None,  # Images assigned in Phase 3
        # The model invents icon names that render nothing, so resolve whatever
        # it returned to an icon that exists before it reaches disk.
        event_type_icon=normalize_icon(details.event_type_icon),
        chapter=None,  # Chapter assigned in Chapter generation phase
        annotations=annotations,
        weight=skeleton.weight,  # From Phase 1, which sees the whole life
        event_class=skeleton.event_class,  # From Phase 1, not Phase 2
    )


def merge_all_events(
    skeletons: List[EventSkeleton], details_list: List[EventDetails]
) -> List[LifeEvent]:
    """Merge all skeletons with their details."""
    if len(skeletons) != len(details_list):
        raise ValueError("Skeleton and details lists must have same length")

    return [
        merge_event_skeleton_and_details(skeleton, details)
        for skeleton, details in zip(skeletons, details_list)
    ]


# ============================================================================
# CHAPTER GENERATION PHASE
# ============================================================================


def call_openai_chapter_generation(
    prompt: str, model: str, retry_count: int = 2
) -> ChapterGenerationOutput:
    """
    Call OpenAI to generate chapters based on established events.

    Returns:
        ChapterGenerationOutput with list of chapters including involved_people and location
    """
    client = get_client()

    system = (
        "You are a skilled biographer crafting a compelling narrative from life events. "
        "Your task is to organize events into engaging chapters that read like a well-told story. "
        "Write with energy and insight, making each chapter feel like part of a coherent journey. "
        "All output must be in American English only. Every text field is plain text "
        "rendered verbatim by the interface: never write Markdown in it."
    )

    instructions = (
        "Based on the established life events provided, create 3-6 compelling life chapters that tell this person's story.\n\n"
        "CHAPTER REQUIREMENTS:\n"
        "- Each chapter represents a distinct phase with a UNIFIED THEME or focus (e.g., education, war service, exile, creative peak, final years)\n"
        "- ABSOLUTE PROHIBITION: NO chapter headline may contain 'Other', 'Miscellaneous', 'Additional', or 'Various' - these are generic categorizations, not meaningful life phases\n"
        "- Every chapter must be equally important with a specific, concrete theme - there are no 'other' or secondary chapters\n"
        "- Chapters must be chronologically ordered and non-overlapping\n"
        "- Events within a chapter should feel related - avoid mixing disparate life phases (e.g., don't combine education + early career + major achievement)\n"
        "- Aim for 3-6 chapters total - too few lacks nuance, too many fragments the story\n"
        "- The first chapter should start with or before the first event\n"
        "- The last chapter should end with or after the last event\n"
        "- Every event must belong to exactly one chapter based on its date\n"
        "- Chapters should flow into each other, creating narrative momentum\n"
        "- If a life phase spans many years with different themes, consider splitting into multiple chapters\n\n"
        "CHAPTER STRUCTURE:\n"
        "- id: Unique identifier (lowercase, snake_case)\n"
        "- headline: CATCHY, story-like chapter title (2-5 words, VARY THE LENGTH). Each headline should express ONE unified concept or theme - NOT a list. "
        "Think like a book chapter - vivid, evocative, intriguing. AVOID 'and', commas, or other punctuation that creates lists. "
        "Be specific and focused on a single idea.\n"
        "  GOOD examples: 'Breaking the Code' (3), 'Exile in Paris' (3), 'The Vienna Circle' (3), 'Rise to Power' (3), "
        "'Final Reckoning' (2), 'A Mind Divided' (3), 'Into the Unknown' (3), 'Wartime Service' (2), "
        "'Building the Future' (3), 'Years of Struggle' (3), 'The Last Battle' (3), 'New Beginnings' (2).\n"
        "  BAD examples: 'Adoption, Valley Spark' (comma creates list), 'Return, Reinvention, Last Act' (multiple concepts), "
        "'Dropout, Zen Fire' (comma splits concepts), 'Early Life and Education' ('and' creates list).\n"
        "- date_start, date_start_precision: When this chapter begins\n"
        "- date_end, date_end_precision: When this chapter ends\n"
        "- age_start, age_end: Subject's age at chapter start/end (null if not applicable)\n"
        "- involved_people: Aggregate the key people mentioned across all events in this chapter "
        "(exclude the main subject, include only significant individuals). "
        "IMPORTANT: Use each person's most canonical name form ONLY ONCE - avoid duplicates or name variations "
        "(e.g., use 'Anna Lloyd Jones' not both 'Anna Lloyd Jones' and 'Anna Lloyd Jones Wright')\n"
        "- location: A summary of the main geographic area for this chapter - NOT a list of cities, but a regional summary. "
        "For example: 'England' (not 'London, Cambridge, Manchester'), 'United States' (not 'Princeton, New York, Boston'), "
        "'Central Europe' (not 'Vienna, Prague, Budapest'). Use the broadest appropriate region.\n\n"
        "CONCLUSION:\n"
        "- After all chapters, provide a crisp, powerful conclusion statement (1-2 sentences)\n"
        "- Capture the person's legacy, lasting impact, or the essence of their life journey\n"
        "- Make it memorable and meaningful - this is the final word on their story\n\n"
        "STORYTELLING GUIDELINES:\n"
        "- Headlines should intrigue and invite the reader in - ONE clear concept, NO lists or comma-separated phrases\n"
        "- VARY headline length (mix 2-word, 3-word, 4-word, and 5-word titles) to create rhythm and avoid monotony\n"
        "- Each chapter should have thematic coherence - events should share a common thread or life phase\n"
        "- Connect chapters so they flow as a continuous story, with each building on the previous\n"
        "- Use vivid, concrete language over abstract generalities\n"
        "- The conclusion should resonate and leave a lasting impression\n\n"
        "Craft chapters that feel like distinct, meaningful phases of this person's journey - not arbitrary date ranges."
    )

    chapters = parse_structured(
        client,
        model=model,
        reasoning_effort=CHAPTER_REASONING_EFFORT,
        input=[
            {"role": "system", "content": system},
            {"role": "user", "content": instructions},
            {"role": "user", "content": prompt},
        ],
        text_format=ChapterGenerationOutput,
        label="chapter generation",
        attempts=retry_count + 1,
    )
    if chapters is None:
        # Unlike a thin event, a story without chapters has no shape at all,
        # so this is the one Phase that fails the run rather than degrading.
        raise RuntimeError("Chapter generation failed")
    return chapters


def deduplicate_person_names(names: List[str]) -> List[str]:
    """
    Deduplicate person names by removing variations of the same person.

    Uses fuzzy matching to identify names that are likely the same person
    (e.g., "Anna Lloyd Jones" and "Anna Lloyd Jones Wright").
    Keeps the shorter, more canonical form.
    """
    if not names:
        return []

    # Normalize names for comparison
    def normalize(name: str) -> str:
        # Remove common suffixes, lowercase, strip whitespace
        normalized = name.lower().strip()
        # Remove parentheticals like "(Lady Byron)"
        normalized = re.sub(r"\s*\([^)]*\)\s*", " ", normalized)
        # Normalize whitespace
        normalized = " ".join(normalized.split())
        return normalized

    # Group similar names
    seen: Dict[str, str] = {}
    result: List[str] = []

    for name in names:
        norm = normalize(name)

        # Check if this is a variation of an existing name
        found_match = False
        for existing_norm, existing_name in seen.items():
            # If one is a substring of the other, they're likely the same person
            if norm in existing_norm or existing_norm in norm:
                # Keep the shorter (more canonical) name
                if len(norm) < len(existing_norm):
                    # Replace with shorter name
                    seen[norm] = name
                    result[result.index(existing_name)] = name
                found_match = True
                break

        if not found_match:
            seen[norm] = name
            result.append(name)

    return result


def assign_events_to_chapters(
    events: List[LifeEvent], chapters: List[LifeChapter]
) -> List[LifeEvent]:
    """
    Assign each event to the appropriate chapter based on date.

    Events are assigned to the chapter whose date range contains the event date.
    Uses normalized date comparison to handle different date precisions correctly
    (e.g., "1945-07" vs "1945-07-01").
    """
    # Sort chapters by normalized start date
    sorted_chapters = sorted(
        chapters,
        key=lambda c: normalize_date_for_comparison(c.date_start, to_end=False),
    )

    updated_events = []
    for event in events:
        # Normalize event date to start of period for comparison
        event_date_normalized = normalize_date_for_comparison(event.date, to_end=False)
        assigned_chapter = None

        # Find the chapter that contains this event's date
        for chapter in sorted_chapters:
            chapter_start = normalize_date_for_comparison(
                chapter.date_start, to_end=False
            )
            chapter_end = normalize_date_for_comparison(chapter.date_end, to_end=True)

            if chapter_start <= event_date_normalized <= chapter_end:
                assigned_chapter = chapter.id
                break

        # If no chapter found, assign to last chapter
        if not assigned_chapter and sorted_chapters:
            assigned_chapter = sorted_chapters[-1].id

        # Copy rather than reconstruct: a field-by-field constructor here must
        # name every field or silently drop the ones it forgets, and it has —
        # image attribution once, then background, weight, and
        # background_images. Every field LifeEvent grows must survive this step.
        updated_events.append(event.model_copy(update={"chapter": assigned_chapter}))

    return updated_events


def clamp_chapter_bounds(
    chapters: List[LifeChapter], events: List[LifeEvent]
) -> List[LifeChapter]:
    """Widen each chapter's boundary dates to cover its own events.

    The model dates a chapter as precisely as its anchor event — Planck's
    last chapter opened on the day his son was executed — while a member
    event may carry only a year. Read at its own precision, that event then
    begins before the chapter that contains it, and the assignment fallback
    above hides the contradiction instead of failing. A chapter boundary may
    never be more precise than the boundary event it has to cover, so where
    a member event spills over, the boundary becomes that event's own date
    at that event's own precision.
    """
    events_by_chapter: Dict[str, List[LifeEvent]] = {}
    for event in events:
        if event.chapter:
            events_by_chapter.setdefault(event.chapter, []).append(event)

    clamped = []
    for chapter in chapters:
        members = events_by_chapter.get(chapter.id) or []
        update: Dict[str, Any] = {}
        if members:
            first = min(
                members,
                key=lambda e: normalize_date_for_comparison(e.date, to_end=False),
            )
            if normalize_date_for_comparison(
                first.date, to_end=False
            ) < normalize_date_for_comparison(chapter.date_start, to_end=False):
                update["date_start"] = first.date
                update["date_start_precision"] = first.date_precision
            last = max(
                members,
                key=lambda e: normalize_date_for_comparison(
                    e.date_end or e.date, to_end=True
                ),
            )
            last_date = last.date_end or last.date
            last_precision = (
                last.date_end_precision if last.date_end else last.date_precision
            ) or "year"
            if normalize_date_for_comparison(
                last_date, to_end=True
            ) > normalize_date_for_comparison(chapter.date_end, to_end=True):
                update["date_end"] = last_date
                update["date_end_precision"] = last_precision
        if update:
            named = ", ".join(f"{k}={v}" for k, v in sorted(update.items()))
            print(f"  Chapter '{chapter.id}' widened to cover its events: {named}")
        clamped.append(chapter.model_copy(update=update) if update else chapter)
    return clamped


def _validate_chapter_headlines(chapters: List[LifeChapter]) -> None:
    """
    Validate that chapter headlines don't contain generic "Other" categorizations.

    Raises RuntimeError if any chapter headline contains prohibited terms.
    """
    import re

    # Patterns to detect generic "other" categorizations in chapter headlines
    # Note: We check for "other" as a chapter-starting word to catch patterns like
    # "Other Events", "Other Achievements", etc., while allowing "Mother of All Demos"
    prohibited_patterns = [
        r"^\s*other\s+",  # "other" at the start of the headline
        r"\bother\s+events?\b",  # "other event" or "other events"
        r"\bother\s+achievements?\b",  # "other achievement" or "other achievements"
        r"\bmiscellaneous\b",
        r"\badditional\s+events?\b",
        r"\bvarious\s+events?\b",
    ]

    for chapter in chapters:
        headline_lower = chapter.headline.lower()
        for pattern in prohibited_patterns:
            if re.search(pattern, headline_lower):
                raise RuntimeError(
                    f"Chapter headline contains prohibited categorization term: '{chapter.headline}'. "
                    f"All chapters must represent meaningful life phases, not generic 'other' or 'miscellaneous' groupings."
                )

    print(f"  ✓ Chapter headlines validated ({len(chapters)} chapters)")


def generate_chapters_for_events(
    merged_events: List[LifeEvent],
    person_name: str,
    birth_date: Optional[str],
    death_date: Optional[str],
    model: str,
) -> Tuple[List[LifeChapter], List[LifeEvent], str]:
    """
    Generate chapters for the established events and assign events to chapters.

    Returns:
        Tuple of (chapters, events_with_chapter_assignments, conclusion)
    """
    # Build prompt with all event information
    prompt = build_chapter_generation_prompt(
        merged_events, person_name, birth_date, death_date
    )

    # Call AI to generate chapters
    chapter_output = call_openai_chapter_generation(prompt, model)

    # Validate chapter headlines don't contain generic categorization terms
    _validate_chapter_headlines(chapter_output.chapters)

    # Deduplicate involved_people in chapters (remove name variations)
    deduplicated_chapters = []
    for chapter in chapter_output.chapters:
        if chapter.involved_people:
            deduplicated_people = deduplicate_person_names(chapter.involved_people)
            chapter = LifeChapter(
                id=chapter.id,
                headline=chapter.headline,
                date_start=chapter.date_start,
                date_start_precision=chapter.date_start_precision,
                date_end=chapter.date_end,
                date_end_precision=chapter.date_end_precision,
                age_start=chapter.age_start,
                age_end=chapter.age_end,
                involved_people=deduplicated_people,
                location=chapter.location,
            )
        deduplicated_chapters.append(chapter)

    # Assign events to chapters, then widen chapter bounds to cover them —
    # the assignment's last-chapter fallback would otherwise hide an event
    # whose coarse date begins before its chapter's precise start.
    events_with_chapters = assign_events_to_chapters(
        merged_events, deduplicated_chapters
    )
    clamped_chapters = clamp_chapter_bounds(deduplicated_chapters, events_with_chapters)

    return clamped_chapters, events_with_chapters, chapter_output.conclusion


def research_images_for_all_events(
    merged_events: List[LifeEvent],
    event_skeletons: List[EventSkeleton],
    event_details_list: List[EventDetails],
    person_name: str,
) -> Tuple[List[LifeEvent], Optional[Dict[str, Any]]]:
    """
    Phase 3: Batch image discovery and AI-driven assignment.

    New approach:
    1. AI generates 20 optimized search strings for all events
    2. Execute all Commons searches and collect unique images
    3. AI selects portrait AND matches images to events
    4. Return events with assigned images and portrait

    Returns:
        Tuple of (enriched_events, portrait_dict or None)
    """
    print("  [Phase 3a] Generating image search strings...")
    search_strings = assign.generate_image_search_strings(event_skeletons, person_name)
    print(f"    Generated {len(search_strings)} search strings")

    event_queries = assign.plan_event_image_searches(
        [details.image_search_queries or [] for details in event_details_list]
    )
    print(f"    Plus searches for {len(event_queries)} event(s) from Phase 2")

    print("  [Phase 3b] Searching image sources (Commons + Openverse)...")
    candidate_images = assign.execute_batch_image_search(
        search_strings, images_per_query=10, event_queries=event_queries
    )

    if not candidate_images:
        print("    No images found, skipping assignment")
        return merged_events, None

    print(f"    Found {len(candidate_images)} candidate images")

    # Quality pre-filtering (permissive - AI makes final decisions)
    print("  [Phase 3b+] Applying quality pre-filtering...")
    filtered_images = filter_images_by_quality(
        candidate_images,
        person_name=person_name,
        min_score=10.0,  # Permissive threshold (out of 45 possible)
    )

    if not filtered_images:
        print("    No images passed quality filters, skipping assignment")
        return merged_events, None

    filtered_count = len(candidate_images) - len(filtered_images)
    print(
        f"    Filtered out {filtered_count} low-quality images ({len(filtered_images)} remaining)"
    )

    # Show quality score distribution
    if filtered_images:
        scores = [img.get("quality_score", 0) for img in filtered_images]
        avg_score = sum(scores) / len(scores)
        max_score = max(scores)
        min_score = min(scores)
        print(
            f"    Quality scores: avg={avg_score:.1f}, range={min_score:.1f}-{max_score:.1f}"
        )

    print(
        f"  [Phase 3c] AI matching {len(filtered_images)} images to {len(event_skeletons)} events..."
    )
    assignments, portrait = assign.match_images_to_events(
        filtered_images, event_skeletons, person_name
    )
    print(f"    Assigned images to {len(assignments)} events")
    if portrait:
        verdict = assign.verify_portrait_depicts_person(portrait, person_name)
        if verdict is False:
            print("    ✗ Portrait rejected on sight; leaving the pick empty")
            portrait = None
        elif verdict is None:
            print("    ! Portrait unverified (the check did not run); keeping it")
        else:
            print("    ✓ Portrait selected and verified")

    # Apply assignments to events
    enriched_events = []
    for idx, event in enumerate(merged_events):
        event_dict = event.model_dump()

        if idx in assignments:
            event_dict["images"] = [image_assignment_block(assignments[idx])]
            safe_title = event.title.encode("ascii", "replace").decode("ascii")
            print(f"    ✓ Event {idx}: {safe_title}")
        else:
            event_dict.pop("images", None)

        enriched_events.append(LifeEvent(**event_dict))

    return enriched_events, portrait


# ============================================================================
# ENHANCED GEOCODING
# ============================================================================


def enrich_event_coordinates_v2(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Enhanced geocoding for unified location structure."""
    events = payload.get("events") or []
    enriched = []
    geocoded_count = 0
    unresolved: List[str] = []

    for event in events:
        if not isinstance(event, dict):
            enriched.append(event)
            continue

        updated = {**event}
        locations = updated.get("locations", [])

        if not locations:
            enriched.append(updated)
            continue

        # Geocode each location missing coordinates
        geocoded_locations = []
        for loc in locations:
            if not isinstance(loc, dict):
                continue

            # If already has centroid, preserve it
            if loc.get("centroid"):
                geocoded_locations.append(loc)
                geocoded_count += 1
                continue

            # Try geocoding (prefer modern name, fallback to historic)
            name_to_geocode = loc.get("name_modern") or loc.get("name_historic")

            if not name_to_geocode:
                geocoded_locations.append(loc)
                continue

            geocoded = geocode_location(name_to_geocode)

            if geocoded:
                geocoded_locations.append(
                    {**loc, "centroid": [geocoded["lon"], geocoded["lat"]]}
                )
                geocoded_count += 1
            else:
                unresolved.append(name_to_geocode)
                geocoded_locations.append(loc)

        updated["locations"] = geocoded_locations
        enriched.append(updated)

    if unresolved:
        distinct = sorted(set(unresolved))
        print(
            f"  ⚠ {len(unresolved)} location(s) left without coordinates: "
            + ", ".join(distinct)
        )

    payload["events"] = enriched
    return payload, geocoded_count


# ============================================================================
# FILE I/O
# ============================================================================


def write_dataset(payload: Dict[str, Any], person_id: str) -> Path:
    """Write dataset to file."""
    person_dir = PEOPLE_DIR / person_id
    person_dir.mkdir(parents=True, exist_ok=True)
    output_path = person_dir / "life_events.json"
    write_json(output_path, payload)
    return output_path


def pad_year(date: Optional[str]) -> Optional[str]:
    """Zero-pad a pre-1000 year so the date sorts and parses like every other.

    A bare ``973-05-06`` is not an ISO 8601 date: JavaScript's date parser
    rejects it, and a four-character slice of it reads ``973-``. The registry
    therefore stores ``0973-05-06``.
    """
    if not isinstance(date, str):
        return date
    match = re.match(r"^(-?)(\d{1,4})(\b.*)$", date.strip())
    if not match:
        return date
    sign, year, rest = match.groups()
    return f"{sign}{year.zfill(4)}{rest}"


def update_register(person_id: str, payload: Dict[str, Any], file_path: Path) -> None:
    """Update persons register."""
    person = payload.get("person", {})

    portrait = person.get("portrait")
    birth_date = pad_year(person.get("birth_date"))
    death_date = pad_year(person.get("death_date"))

    primary_roles = person.get("primary_roles", [])
    if isinstance(primary_roles, list):
        primary_roles = primary_roles[:3]

    current_timestamp = datetime.now().astimezone().isoformat()

    entry = {
        "id": person_id,
        "name": person.get("name", person_id.replace("_", " ").title()),
        "summary": person.get("summary"),
    }

    # Only include tagline if it's actually set (to preserve existing tagline when updating)
    tagline = person.get("tagline")
    if tagline is not None:
        entry["tagline"] = tagline

    # Explicitly set portrait (or None to remove it)
    entry["portrait"] = portrait
    if birth_date:
        entry["birthDate"] = birth_date
    if death_date:
        entry["deathDate"] = death_date
    if primary_roles:
        entry["primaryRoles"] = primary_roles

    entry["created"] = current_timestamp
    entry["lastUpdated"] = current_timestamp

    registry = Registry(REGISTER_PATH)
    # `created` records when the person first appeared, so the existing entry
    # always wins on it; everything else this function knows about is newer.
    stored = registry.upsert(entry, preserve=("created",))
    # An explicit None means "no portrait", which is stored as the key's
    # absence rather than a null.
    if stored.get("portrait") is None:
        stored.pop("portrait", None)
    registry.sort_by_name()
    registry.save()


# ============================================================================
# MAIN ORCHESTRATION
# ============================================================================


def generate_person_events(
    subject: str,
    *,
    person_id: Optional[str] = None,
    update_registry: bool = True,
    model: str = DEFAULT_MODEL,
    use_cache: bool = True,
    use_deutsche_biographie: bool = True,
) -> Tuple[Path, str]:
    """
    Generate person life events dataset using two-phase approach.

    Args:
        subject: Person name or Wikipedia URL to research
        person_id: Optional person ID to use instead of auto-generating from article title
        update_registry: Whether to update persons.json registry
        model: OpenAI model to use
        use_cache: Whether to use cached Wikipedia materials
        use_deutsche_biographie: Whether to fetch/use Deutsche Biographie data

    Returns:
        Tuple of (file_path, person_id)
    """

    print(f"[Step 1/10] Fetching Wikipedia article for '{subject}'...")
    page_data = fetch_wikipedia_extract(subject, _fetch_wikipedia_page)
    article_title = page_data.get("title", subject)
    print(f"[Step 1/10] Found article '{article_title}'")

    # Use provided person_id or generate from article title
    identifier = person_id or slugify(article_title)

    # Load cache (NO Commons images - fetched later in Phase 3)
    print(f"[Step 2/10] Loading cached materials for '{identifier}'...")
    related_articles = None
    summary_data = {}

    if use_cache:
        try:
            ensure_cache(identifier, article_title, person_name=article_title)
            cached_page = get_cached_wikipedia_page(
                identifier, article_title, use_cache=True
            )
            cached_summary = get_cached_wikipedia_summary(
                identifier, article_title, use_cache=True
            )

            # Load related articles if available
            cache_dir = get_cache_dir(identifier)
            related_path = cache_dir / "related_articles.json"
            if related_path.exists():
                try:
                    related_articles = json.loads(
                        related_path.read_text(encoding="utf-8")
                    )
                    print(
                        f"[Step 2/10] Using cached materials ({len(related_articles)} related articles)"
                    )
                except json.JSONDecodeError:
                    print("[Step 2/10] Using cached materials (no related articles)")
            else:
                print("[Step 2/10] Using cached materials (no related articles)")

            page_data = cached_page
            summary_data = cached_summary
        except Exception as e:
            print(f"[Step 2/10] Cache unavailable ({e}), fetching directly...")
            summary_data = fetch_wikipedia_summary(article_title)
    else:
        print("[Step 2/10] Retrieving summary details...")
        summary_data = fetch_wikipedia_summary(article_title)

    # Fetch related articles if not already loaded from cache
    if related_articles is None and fetch_related_articles is not None:
        print(
            f"[Step 3/10] Fetching related articles (model: {model}, reasoning: {RELATED_ARTICLES_REASONING})..."
        )
        try:
            related_articles = fetch_related_articles(
                article_title,
                max_related=15,
                model=model,
                use_cache=use_cache,
                person_id=identifier,
            )
            print(f"[Step 3/10] Found {len(related_articles)} related articles")

            if related_articles and use_cache:
                cache_dir = get_cache_dir(identifier)
                related_path = cache_dir / "related_articles.json"
                cache_dir.mkdir(parents=True, exist_ok=True)
                write_json(related_path, related_articles)
                print(f"[Step 3/10] Cached {len(related_articles)} related articles")
        except Exception as e:
            print(f"[Step 3/10] Warning: Failed to fetch related articles ({e})")
            related_articles = []
    else:
        print(
            f"[Step 3/10] Using {len(related_articles) if related_articles else 0} related articles from cache"
        )

    # Load Deutsche Biographie data (best-effort)
    db_prompt_text = None
    if use_deutsche_biographie and ensure_deutsche_biographie_cache is not None:
        try:
            # Extract birth/death years from Wikipedia for disambiguation
            _db_birth_year = None
            _db_death_year = None
            _wiki_extract = page_data.get("extract", "")
            _year_match = re.search(
                r"\((\d{4})\s*[-–]\s*(\d{4})\)", _wiki_extract[:500]
            )
            if _year_match:
                _db_birth_year = int(_year_match.group(1))
                _db_death_year = int(_year_match.group(2))

            db_data = ensure_deutsche_biographie_cache(
                person_id=identifier,
                person_name=article_title,
                birth_year=_db_birth_year,
                death_year=_db_death_year,
            )
            if db_data and format_db_for_prompt is not None:
                db_prompt_text = format_db_for_prompt(db_data)
                if db_prompt_text:
                    print("[Step 3b/10] Deutsche Biographie data included in prompts")
        except Exception as e:
            print(f"[Step 3b/10] Warning: Deutsche Biographie fetch failed ({e})")
    elif not use_deutsche_biographie:
        print("[Step 3b/10] Deutsche Biographie skipped by request")

    # PHASE 1: Generate event skeletons
    print(
        f"[Step 4/12] PHASE 1: Generating event skeletons (model: {model}, reasoning: {PHASE1_REASONING_EFFORT})..."
    )
    phase1_prompt = build_phase1_prompt(
        page_data,
        summary_data,
        subject,
        related_articles,
        deutsche_biographie_text=db_prompt_text,
    )
    life_plan = call_openai_phase1(phase1_prompt, model)
    print(f"[Step 4/12] Generated {len(life_plan.event_skeletons)} event skeletons")

    # PHASE 2: Research event details (NO images - Phase 3)
    print(
        f"[Step 5/12] PHASE 2: Researching event details (model: {PHASE2_MODEL}, reasoning: {PHASE2_REASONING_EFFORT})..."
    )
    event_details_list = research_all_event_details(
        event_skeletons=life_plan.event_skeletons,
        person_name=life_plan.person.name,
        all_related_articles=related_articles or [],
        deutsche_biographie_text=db_prompt_text,
        subject_article=page_data,
    )
    print(f"[Step 5/12] Researched details for {len(event_details_list)} events")

    # MERGE: Combine skeletons + details
    print("[Step 6/12] Merging event skeletons with details...")
    merged_events = merge_all_events(life_plan.event_skeletons, event_details_list)

    # CHAPTER GENERATION: Create chapters based on established events
    print(
        f"[Step 7/12] Generating life chapters (model: {model}, reasoning: {CHAPTER_REASONING_EFFORT})..."
    )
    chapters, events_with_chapters, conclusion = generate_chapters_for_events(
        merged_events=merged_events,
        person_name=life_plan.person.name,
        birth_date=life_plan.person.birth_date,
        death_date=life_plan.person.death_date,
        model=model,
    )
    print(f"[Step 7/12] Generated {len(chapters)} chapters with conclusion")

    # PHASE 3: Event-specific image discovery
    print(
        f"[Step 8/12] PHASE 3: Discovering and assigning event-specific images (model: {assign.PHASE3_IMAGE_SEARCH_MODEL}, reasoning: {assign.PHASE3_IMAGE_SEARCH_REASONING}/{assign.PHASE3_IMAGE_MATCH_REASONING})..."
    )
    enriched_events, portrait = research_images_for_all_events(
        merged_events=events_with_chapters,
        event_skeletons=life_plan.event_skeletons,
        event_details_list=event_details_list,
        person_name=life_plan.person.name,
    )
    images_assigned = sum(1 for e in enriched_events if e.images)
    print(
        f"[Step 8/12] Assigned images to {images_assigned} / {len(enriched_events)} events"
    )

    # Build final payload
    person_data = life_plan.person.model_dump()

    # Apply the AI-selected portrait, but never displace a generated one.
    portrait_block = resolve_portrait(
        portrait, find_existing_generated_portrait(identifier)
    )
    if portrait_block:
        person_data["portrait"] = portrait_block
    else:
        person_data.pop("portrait", None)

    payload: Dict[str, Any] = {
        "dataset": life_plan.dataset,
        "created_on": life_plan.created_on,
        "person": person_data,
        "chapters": [ch.model_dump() for ch in chapters] if chapters else None,
        "conclusion": conclusion if conclusion else None,
        "events": [ev.model_dump(exclude_none=True) for ev in enriched_events],
    }

    # Normalize metadata
    print("[Step 9/12] Normalizing dataset metadata...")
    payload = enforce_metadata(payload, page_data, summary_data)
    print(f"[Step 9/12] Dataset includes {len(payload['events'])} events")

    # Geocode with enhanced logic
    print("[Step 10/12] Resolving event location coordinates...")
    payload, geocoded_events = enrich_event_coordinates_v2(payload)
    print(f"[Step 10/12] Coordinates resolved for {geocoded_events} events")

    # Resolve a link for every published work the story names
    print("[Step 11/12] Resolving publication source links...")
    try:
        from enrich_publication_links import enrich_events as enrich_publication_links

        person_block = payload.get("person") or {}
        linked = enrich_publication_links(
            payload["events"],
            person_name=str(person_block.get("name") or identifier).replace("_", " "),
            person_article=person_block.get("wikipedia"),
            person_id=identifier,
        )
        print(f"[Step 11/12] Linked {linked} publication(s) to a source")
    except Exception as error:
        # A missing link costs the reader a click, not the run its dataset.
        print(f"Warning: could not resolve publication links ({error})")

    # Write to file
    print(f"[Step 12/12] Writing dataset for '{identifier}'...")
    existing_path = PEOPLE_DIR / identifier / "life_events.json"
    old_payload = None
    if existing_path.exists():
        try:
            old_payload = json.loads(existing_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    file_path = write_dataset(payload, identifier)

    # Preserve curated meta-story selections when event indexes or text change.
    try:
        from sync_meta_story_events import sync_meta_story_events

        sync_report = sync_meta_story_events(
            identifier, old_person_data=old_payload, new_person_data=payload
        )
        if sync_report["stories"]:
            print(
                f"Incrementally updated {sync_report['stories']} meta story/stories "
                f"({sync_report['updated']} references changed, "
                f"{sync_report['removed']} removed)"
            )
    except Exception as error:
        print(f"Warning: Could not sync meta-story events ({error})")

    if update_registry:
        print("Updating persons register...")
        update_register(identifier, payload, file_path)
        print("Register update complete")
    else:
        print("Register update skipped")

    return file_path, identifier


def find_existing_generated_portrait(
    person_id: str, *, indent: str = "  "
) -> Optional[Dict[str, Any]]:
    """A previously generated portrait for this person, or None.

    The registry is checked first; when it does not carry one, the portrait
    files on disk still count — a regeneration must not lose a portrait that
    only the files remember.
    """
    try:
        if REGISTER_PATH.exists():
            registry = json.loads(REGISTER_PATH.read_text(encoding="utf-8"))
            for person in registry.get("people", []):
                if person.get("id") != person_id:
                    continue
                existing = person.get("portrait", {})
                if (
                    existing
                    and isinstance(existing.get("image"), str)
                    and existing["image"].startswith("/portraits/")
                ):
                    print(
                        f"{indent}Found existing generated portrait in registry: "
                        f"{existing['image']}"
                    )
                    return cast(Dict[str, Any], existing)
                break

        portraits_dir = Path(__file__).resolve().parents[1] / "public" / "portraits"
        thumbnail_path = portraits_dir / f"{person_id}_thumbnail.webp"
        if thumbnail_path.exists():
            print(
                f"{indent}Found existing generated portrait files on disk: "
                f"{thumbnail_path.name}"
            )
            return {
                "image": f"/portraits/{person_id}_thumbnail.webp",
                "thumbnail": f"/portraits/{person_id}_thumbnail.webp",
                "medium": f"/portraits/{person_id}_medium.webp",
                "full": f"/portraits/{person_id}_full.webp",
                "caption": "Stylized portrait based on historical photograph",
                "creator": "AI generated artwork",
            }
    except Exception as e:
        print(f"{indent}Warning: Could not check for existing portrait: {e}")
    return None


def resolve_portrait(
    ai_portrait: Optional[Dict[str, Any]],
    existing_generated: Optional[Dict[str, Any]],
    *,
    indent: str = "  ",
) -> Optional[Dict[str, Any]]:
    """The portrait block to store, or None when there is nothing to show.

    A generated portrait always wins over the AI-selected one; the latter then
    replaces the original it was derived from — and `source` follows it, so
    the reader's source link points at the page the current original lives on
    rather than at wherever a previous one came from. The original's own
    attribution travels under original* keys, because a CC-BY reference keeps
    its license terms even behind a stylized derivative.
    """
    if ai_portrait:
        if existing_generated:
            portrait_data = existing_generated.copy()
            portrait_data["originalImage"] = ai_portrait["url"]
            portrait_data["source"] = ai_portrait["source"]
            for src_key, dst_key in (
                ("creator", "originalCreator"),
                ("license", "originalLicense"),
                ("licenseUrl", "originalLicenseUrl"),
            ):
                if ai_portrait.get(src_key):
                    portrait_data[dst_key] = ai_portrait[src_key]
                else:
                    portrait_data.pop(dst_key, None)
            print(
                f"{indent}Preserving generated portrait, updating originalImage to: "
                f"{ai_portrait['url']}"
            )
            return portrait_data
        portrait_data = {
            "image": ai_portrait["url"],
            "source": ai_portrait["source"],
        }
        for key in ("caption", "creator", "license", "licenseUrl"):
            if ai_portrait.get(key):
                portrait_data[key] = ai_portrait[key]
        return portrait_data
    if existing_generated:
        print(f"{indent}No AI portrait found, keeping existing generated portrait")
        return existing_generated
    return None


def image_assignment_block(img: Dict[str, Any]) -> Dict[str, Any]:
    """One stored image entry, keeping only the attribution fields that exist."""
    block = {"url": img["url"], "caption": img["caption"], "source": img["source"]}
    for key in ("creator", "license", "licenseUrl"):
        if img.get(key):
            block[key] = img[key]
    return block
