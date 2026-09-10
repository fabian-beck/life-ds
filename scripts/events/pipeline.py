"""Generate one person's life events, step by step.

The order is the argument. The proposal reads the whole article set and proposes
the events, groups them into chapters, and writes the conclusion, because how
much of a life an event turns on, and where one phase of it ends, is a
comparison only that call can make. The research takes each event on its own
material, side by side. The chapters are then dated from their events, the
image step illustrates them, the geocoder places them, and `enforce_metadata`
brings the whole payload into the shape the corpus is read with before it is
written.

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
    Sequence,
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
from events.prompts.propose import build_proposal_prompt
from events.prompts.research import (
    RELATED_ARTICLE_COUNT,
    build_research_prompt_base,
    build_research_prompt_classified,
    filter_related_articles_for_event,
)
from events.schemas import (
    BirthClassification,
    ChapterPlan,
    DeathClassification,
    EventDetails,
    EventSkeleton,
    LifeChapter,
    LifeEvent,
    LifePlan,
)
from events.images.scoring import filter_images_by_quality
from icon_categories import normalize_icon
from utils.concurrency import map_concurrently, worker_count
from utils.geocode import geocode_location
from utils.registry import Registry
from utils.prose_style import PROSE_STYLE_INSTRUCTIONS, description_contract_prompt
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
# Configure model and reasoning effort for each step of the generation
# pipeline. This ensures consistent configuration between AI calls and logging.
#
# The proposal decides what the life is — its events, its chapters, its conclusion —
# and reads the whole article set, so it takes the default model and a
# reasoning budget. The steps below it work from material that call already
# settled, and every field they return is checked afterwards — icons against
# the catalog, involved people against known entities, places against the
# geocoder, image filenames against the fetched candidates — so they take the
# small model.

PROPOSAL_REASONING_EFFORT = (
    DEFAULT_REASONING_EFFORT  # Event skeletons and chapters (medium)
)

# Event detail research. Every field it returns is checked afterwards — icons
# against the catalog, people against known entities, places against the
# geocoder — which is what qualifies it for the small model. The background
# passage, the one output checked by nobody, is written in a step of its own
# (generate_event_backgrounds.py) on the default model.
RESEARCH_MODEL = BULK_MODEL
RESEARCH_REASONING_EFFORT = BULK_REASONING_EFFORT

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
# PROPOSAL: EVENT SKELETONS AND CHAPTERS
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

    Works on event skeletons, merged events, and the plain dicts a stored
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

    Works on event skeletons, merged events, and the plain dicts a stored
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


def propose_events(prompt: str, model: str) -> LifePlan:
    """
    Call OpenAI for the proposal using structured outputs.

    Returns:
        LifePlan with person metadata and event skeletons
    """
    client = get_client()

    system = (
        "You are a biographer laying out a life as a story told in slides, one event "
        "to a slide. You choose the events a life turns on, narrate each in its own "
        "moment, and group them into the chapters the story is told in; the diligence "
        "about evidence lives in the sources and the metadata, not in the prose. "
        "Use ISO-8601 dates, include date_precision as 'day', 'month', or 'year'. "
        "The precision is a claim of its own: use 'day' only when the sources state "
        "the day, 'month' only when they state the month, and fall back to 'year' "
        "otherwise. An honest 1814-07 is better than a wrong 1814-07-02. "
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
        "- Keep event titles crisp and concise (2-6 words), at the slide's granularity: a city, never a street\n"
        "- Use active, specific language that captures the essence of the event\n"
        "- Avoid generic titles like 'Major Achievement' or 'Important Work'\n"
        "- Examples: 'Birth in London', 'Graduated from Oxford', 'Published First Novel', 'Appointed Prime Minister'\n"
        "- Write the description as defined below; the research call adds the exact locations, images, and sources\n"
        "- DO NOT add annotations - the research call adds them\n"
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
        "\n\n" + description_contract_prompt() + "\n"
        "\nLength: 2-4 sentences per description, each carrying a fact about the event. "
        "Two is the floor: a description of one sentence has left out who was there, "
        "what led to the event, or what it was for, and the sources hold that for "
        "every event worth a slide. "
        "How every sentence is written is set out below, and it applies to the "
        "descriptions, the conclusion, and the summary alike.\n\n"
        + PROSE_STYLE_INSTRUCTIONS
        + "\n"
        "\n\nCHAPTERS:\n"
        "Group the events into 3-6 chapters that tell this person's story, and name the chapter on every event.\n"
        "- Each chapter represents a distinct phase with a UNIFIED THEME or focus (e.g., education, war service, exile, creative peak, final years)\n"
        "- ABSOLUTE PROHIBITION: NO chapter headline may contain 'Other', 'Miscellaneous', 'Additional', or 'Various' - these are generic categorizations, not meaningful life phases\n"
        "- Every chapter must be equally important with a specific, concrete theme - there are no 'other' or secondary chapters\n"
        "- List the chapters in chronological order. Chapters are contiguous runs of the timeline: "
        "every event of a chapter comes after every event of the chapter before it, and a chapter never resumes once the next has begun\n"
        "- Every event belongs to exactly one chapter, named in its chapter field by the chapter's id\n"
        f"- Every chapter holds at least {MIN_CHAPTER_EVENTS} events. A chapter slide opens on a phase of the life, and a phase "
        "with one event in it is that event told twice: fold such an event into the chapter before or after it\n"
        "- Events within a chapter should feel related - avoid mixing disparate life phases (e.g., don't combine education + early career + major achievement)\n"
        "- Aim for 3-6 chapters total - too few lacks nuance, too many fragments the story\n"
        "- If a life phase spans many years with different themes, consider splitting into multiple chapters\n"
        "- Chapters should flow into each other, creating narrative momentum\n"
        "- Do not date the chapters: a chapter begins with its first event and ends with its last\n"
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
        "- location: A summary of the main geographic area for this chapter - NOT a list of cities, but a regional summary. "
        "For example: 'England' (not 'London, Cambridge, Manchester'), 'United States' (not 'Princeton, New York, Boston'), "
        "'Central Europe' (not 'Vienna, Prague, Budapest'). Use the broadest appropriate region.\n"
        "\n\nCONCLUSION FIELD (2-4 sentences):\n"
        "- The one place that looks back over the whole life: what of this person's work "
        "is still in use, still read, still built on, and by whom\n"
        "- One sentence per strand of the work that persists, so that every event weighted "
        "0.9 or above has what came of it named; a single fact is a caption, and a "
        "life the story spent 12-16 slides on leaves more than one thing behind\n"
        "- Name the person in the first sentence; the field is read on a slide of its own\n"
        "- Event descriptions = factual, chronological, in-the-moment\n"
        "- Conclusion = what came of the life, stated as facts, after all events are told\n"
        "- State it as facts. No 'legacy', no 'journey', no dash, no 'not X but Y', "
        "and no sentence that weighs the life instead of saying what came of it\n"
        "  * BAD (one fact for a whole life): 'COBOL remains in use today in business and "
        "government computing.'\n"
        "  * BAD (a verdict): 'Grace Hopper transformed programming from an arcane machine "
        "task into a language people could command.'\n"
        "  * GOOD: 'Compilers descend from Hopper's A-0 and FLOW-MATIC. COBOL, whose design "
        "she steered, still runs banking and government systems. The Navy destroyer "
        "USS Hopper and the Grace Hopper Celebration of Women in Computing carry her "
        "name.'\n"
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
            [
                config["proposal_guidance"] + "\n"
                for config in EVENT_CLASS_CONFIG.values()
            ]
        )
        + "For other events (education, appointments, awards): OMIT classification.\n"
        f"Only classify when event CLEARLY matches one of the {len(EVENT_CLASS_CONFIG)} types above.\n"
        "\n\nEach event skeleton must provide: date (start of the event), date_precision, optional date_end/date_end_precision "
        "when the event spans a range, optional date_note for uncertainty, age (null if not applicable), "
        "title, description, weight, and the chapter it belongs to. "
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
        "\nTAGLINE GUIDELINES:\n"
        "- A catchy, memorable phrase (3-7 words) that captures the person's essence or most notable contribution\n"
        "- Name the specific thing this person did, made, or found: the work, the idea, the machine, the discovery\n"
        "- Do NOT use a generic status noun plus 'of': 'Pioneer of ...', 'Architect of ...', 'Father/Mother of ...', "
        "'Visionary of ...', 'Master of ...', 'Champion of ...', 'Giant of ...'. Such a phrase fits anyone in the field "
        "and does not tell people apart\n"
        "- Avoid words that rank the person in history instead of stating what they did: 'greatest', 'legendary', 'genius'. "
        "'First' is fine only when it is literally true\n"
        "- GOOD examples: 'The First Programmer', 'Gravity as Curved Spacetime', 'Steam-Powered Calculating Engines', "
        "'Compilers That Read English', 'Quantum Jumps Inside the Atom'\n"
        "- BAD examples: 'Father of Computer Science', 'Architect of Relativity', 'Pioneer of Structured Programming', 'Visionary of the Analytical Engine'"
    )

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": instructions},
        {"role": "user", "content": prompt},
    ]
    for attempt in range(1, PROPOSAL_ATTEMPTS + 1):
        parsed = parse_structured_or_raise(
            client,
            model=model,
            reasoning_effort=PROPOSAL_REASONING_EFFORT,
            input=messages,
            text_format=LifePlan,
            label="Event proposal",
        )
        try:
            return accept_life_plan(parsed)
        except RuntimeError as error:
            if attempt == PROPOSAL_ATTEMPTS:
                raise
            print(f"  Proposal: rejected plan {attempt}: {error}")
            messages = messages + [proposal_rejection_message(error)]
    raise AssertionError("unreachable")


PROPOSAL_ATTEMPTS = 2
"""How many plans the model may propose before a refused one fails the run.

The chapter and order rules in the prompt are also checked in code, and a plan
that breaks one used to end the whole generation before the research had run. One
more call that names the rejection is cheaper than a failed run.
"""


def proposal_rejection_message(error: Exception) -> Dict[str, Any]:
    """The turn that asks for a corrected plan, naming why the last was refused."""
    return {
        "role": "user",
        "content": (
            "The previous plan was rejected for this reason: "
            + str(error)
            + "\nReturn a corrected plan that satisfies every rule above. Keep the "
            "events and chapters that were not at fault as they were."
        ),
    }


def accept_life_plan(parsed: LifePlan) -> LifePlan:
    """Classify the boundaries of a plan and refuse one whose structure is wrong.

    Raises RuntimeError when the events are out of order or the chapters do
    not partition them into contiguous runs of at least MIN_CHAPTER_EVENTS.
    """
    # Ensure events are sorted chronologically (defensive programming)
    parsed.event_skeletons.sort(key=lambda e: e.date)

    # The birth opens a story and the death closes it, so both are detected
    # rather than hoped for
    birth_index = ensure_birth_classification(
        parsed.event_skeletons, parsed.person.birth_date
    )
    if birth_index is None:
        print("  Proposal: no birth event found in the plan")
    death_index = ensure_death_classification(
        parsed.event_skeletons, parsed.person.death_date
    )
    if death_index is None:
        print("  Proposal: no death event found in the plan")

    # Log classifications from the proposal (using centralized config)
    classified_count = sum(
        1 for skeleton in parsed.event_skeletons if skeleton.event_class
    )
    if classified_count > 0:
        print(
            f"  Proposal: classified {classified_count}/{len(parsed.event_skeletons)} events"
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

    # The chapters are a partition of that order, and their headlines carry
    # the story, so both are checked before the research is paid for
    validate_chapter_partition(parsed.chapters, parsed.event_skeletons)
    _validate_chapter_headlines(parsed.chapters)
    print(f"  ✓ Chapter partition validated ({len(parsed.chapters)} chapters)")

    return parsed


# ============================================================================
# RESEARCH: THE DETAILS OF EACH EVENT
# ============================================================================


def research_event_details(
    event_skeleton: EventSkeleton,
    person_name: str,
    all_related_articles: List[Dict[str, Any]],
    model: str = RESEARCH_MODEL,
    retry_count: int = 2,
    deutsche_biographie_text: Optional[str] = None,
    subject_article: Optional[Dict[str, Any]] = None,
) -> EventDetails:
    """
    Research details for a single event with retry logic.
    Uses event-class-specific prompts for targeted research.

    Returns:
        EventDetails with locations, involved_people, sources, icon (no images; the image step adds them)
    """
    # Filter articles
    filtered_articles = filter_related_articles_for_event(
        event_skeleton, all_related_articles, max_articles=RELATED_ARTICLE_COUNT
    )

    # Route to event-class-specific prompt builder (using centralized config)
    if event_skeleton.event_class:
        # All classified events use the generic builder with config
        prompt = build_research_prompt_classified(
            event_skeleton,
            person_name,
            filtered_articles,
            deutsche_biographie_text=deutsche_biographie_text,
            subject_article=subject_article,
        )
    else:
        # Standard event (no classification)
        prompt = build_research_prompt_base(
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
        reasoning_effort=RESEARCH_REASONING_EFFORT,
        input=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        text_format=EventDetails,
        label=f"Research of '{event_skeleton.title}'",
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
    model: str = RESEARCH_MODEL,
    deutsche_biographie_text: Optional[str] = None,
    subject_article: Optional[Dict[str, Any]] = None,
) -> List[EventDetails]:
    """Research details for all events (no images; the image step adds them).

    The events are researched side by side: no event's research reads
    another's, and each call carries the same article set, so the step's
    wall clock is that of its slowest call rather than the sum of all of
    them. The details come back in the skeletons' order regardless.
    """
    # Log classification routing info
    classified_count = sum(1 for skeleton in event_skeletons if skeleton.event_class)
    print(
        f"  Research: using class-specific prompts for {classified_count}/{len(event_skeletons)} classified events"
    )
    workers = min(worker_count(), max(1, len(event_skeletons)))
    if workers > 1:
        print(f"  Research: {len(event_skeletons)} events, {workers} at a time")

    def research(indexed: Tuple[int, EventSkeleton]) -> EventDetails:
        idx, skeleton = indexed
        safe_title = skeleton.title.encode("ascii", "replace").decode("ascii")

        # Show which prompt type is being used
        prompt_type = "STANDARD"
        if skeleton.event_class:
            prompt_type = skeleton.event_class.type.upper()

        print(
            f"  [{idx}/{len(event_skeletons)}] Researching: {safe_title} [{prompt_type}]"
        )

        return research_event_details(
            skeleton,
            person_name,
            all_related_articles,
            model,
            deutsche_biographie_text=deutsche_biographie_text,
            subject_article=subject_article,
        )

    return map_concurrently(enumerate(event_skeletons, 1), research, workers=workers)


# ============================================================================
# EVENT MERGING
# ============================================================================


def merge_event_skeleton_and_details(
    skeleton: EventSkeleton, details: EventDetails
) -> LifeEvent:
    """Merge event skeleton with researched details (no images; the image step adds them)."""

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

    # Annotations come ONLY from the research (the proposal doesn't generate them)
    annotations = details.annotations

    # Merge description (prefer the research if provided with markers, else the proposal)
    description = details.description if details.description else skeleton.description

    # Create merged event (no images yet; the image step assigns them)
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
        images=None,  # assigned by the image step
        # The model invents icon names that render nothing, so resolve whatever
        # it returned to an icon that exists before it reaches disk.
        event_type_icon=normalize_icon(details.event_type_icon),
        chapter=skeleton.chapter,  # From the proposal, which laid out the chapters
        annotations=annotations,
        weight=skeleton.weight,  # From the proposal, which sees the whole life
        event_class=skeleton.event_class,  # From the proposal, not the research
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
# CHAPTERS: THE PARTITION THE PROPOSAL DREW, DATED FROM THE RESEARCHED EVENTS
# ============================================================================


MIN_CHAPTER_EVENTS = 2
"""The fewest events a chapter may hold.

A chapter slide announces a phase of the life and the event slides then tell
it. A chapter with one event announces that event and tells it once more on
the next slide, with the same year and the same place on both — the Turing
dataset opened "Across the Atlantic" on his Princeton doctorate alone. Such an
event belongs to the chapter before or after it.
"""


def validate_chapter_partition(
    chapters: Sequence[ChapterPlan], skeletons: Sequence[EventSkeleton]
) -> None:
    """Check that the plan's chapters partition its events into contiguous runs.

    The interface inserts a chapter slide wherever the chapter id changes
    between two consecutive events, so a chapter that resumes after another
    has begun renders twice. Every event has to name a chapter that exists,
    every chapter has to hold at least MIN_CHAPTER_EVENTS events, and the
    order in which the chapters first appear along the timeline has to be the
    order the plan lists them in. A plan that fails any of this is refused
    before the research is paid for.
    """
    if not chapters:
        raise RuntimeError("The proposal returned no chapters")
    ids = [chapter.id for chapter in chapters]
    duplicates = sorted({cid for cid in ids if ids.count(cid) > 1})
    if duplicates:
        raise RuntimeError(f"Chapter ids are not unique: {', '.join(duplicates)}")
    known = set(ids)

    order_of_appearance: List[str] = []
    members: Dict[str, int] = {cid: 0 for cid in ids}
    for skeleton in skeletons:
        if not skeleton.chapter:
            raise RuntimeError(f"Event '{skeleton.title}' names no chapter")
        if skeleton.chapter not in known:
            raise RuntimeError(
                f"Event '{skeleton.title}' names unknown chapter '{skeleton.chapter}'"
            )
        members[skeleton.chapter] += 1
        if skeleton.chapter in order_of_appearance:
            if order_of_appearance[-1] != skeleton.chapter:
                raise RuntimeError(
                    f"Chapter '{skeleton.chapter}' resumes at '{skeleton.title}' "
                    f"after chapter '{order_of_appearance[-1]}' has begun"
                )
        else:
            order_of_appearance.append(skeleton.chapter)

    empty = [cid for cid in ids if cid not in order_of_appearance]
    if empty:
        raise RuntimeError(f"Chapters hold no event: {', '.join(empty)}")
    if order_of_appearance != ids:
        raise RuntimeError(
            "Chapters are listed out of order: the plan says "
            f"{', '.join(ids)} but the events run {', '.join(order_of_appearance)}"
        )
    thin = [
        f"{cid} ({members[cid]})" for cid in ids if members[cid] < MIN_CHAPTER_EVENTS
    ]
    if thin:
        raise RuntimeError(
            f"Chapters hold fewer than {MIN_CHAPTER_EVENTS} events: {', '.join(thin)}"
        )


def _validate_chapter_headlines(chapters: Sequence[ChapterPlan]) -> None:
    """
    Validate that chapter headlines don't contain generic "Other" categorizations.

    Raises RuntimeError if any chapter headline contains prohibited terms.
    """
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


def build_chapters(
    plan_chapters: Sequence[ChapterPlan], events: List[LifeEvent]
) -> List[LifeChapter]:
    """Date each chapter from its events and gather the people they name.

    A chapter begins with the earliest of its events and ends with the latest,
    each boundary carried at the precision of the event it comes from: a
    boundary can never be more precise than the event it has to cover, which is
    what used to let a chapter dated to the day begin after a member event
    dated to the year. The ages are read off the same two events, and the
    people are the union of what the research found on the members, with the name
    variations folded together.
    """
    events_by_chapter: Dict[str, List[LifeEvent]] = {}
    for event in events:
        if event.chapter:
            events_by_chapter.setdefault(event.chapter, []).append(event)

    chapters: List[LifeChapter] = []
    for plan in plan_chapters:
        members = events_by_chapter.get(plan.id)
        if not members:
            raise RuntimeError(f"Chapter '{plan.id}' holds no event")
        first = min(
            members,
            key=lambda e: normalize_date_for_comparison(e.date, to_end=False),
        )
        last = max(
            members,
            key=lambda e: normalize_date_for_comparison(
                e.date_end or e.date, to_end=True
            ),
        )
        end_date = last.date_end or last.date
        end_precision = (
            last.date_end_precision if last.date_end else last.date_precision
        ) or "year"
        people = [name for member in members for name in (member.involved_people or [])]
        deduplicated = deduplicate_person_names(people)
        chapters.append(
            LifeChapter(
                id=plan.id,
                headline=plan.headline,
                date_start=first.date,
                date_start_precision=first.date_precision or "year",
                date_end=end_date,
                date_end_precision=end_precision,
                age_start=first.age,
                age_end=last.age,
                involved_people=deduplicated or None,
                location=plan.location,
            )
        )
    return chapters


def research_images_for_all_events(
    merged_events: List[LifeEvent],
    event_skeletons: List[EventSkeleton],
    event_details_list: List[EventDetails],
    person_name: str,
) -> Tuple[List[LifeEvent], Optional[Dict[str, Any]]]:
    """
    The image step: batch image discovery and AI-driven assignment.

    New approach:
    1. AI generates 20 optimized search strings for all events
    2. Execute all Commons searches and collect unique images
    3. AI selects portrait AND matches images to events
    4. Return events with assigned images and portrait

    Returns:
        Tuple of (enriched_events, portrait_dict or None)
    """
    print("  [Images] Planning the searches...")
    search_strings = assign.generate_image_search_strings(event_skeletons, person_name)
    print(f"    Generated {len(search_strings)} search strings")

    event_queries = assign.plan_event_image_searches(
        [details.image_search_queries or [] for details in event_details_list]
    )
    print(f"    Plus searches for {len(event_queries)} event(s) from the research")

    print("  [Images] Searching Commons and Openverse...")
    candidate_images = assign.execute_batch_image_search(
        search_strings, images_per_query=10, event_queries=event_queries
    )

    if not candidate_images:
        print("    No images found, skipping assignment")
        return merged_events, None

    print(f"    Found {len(candidate_images)} candidate images")

    # Quality pre-filtering (permissive - AI makes final decisions)
    print("  [Images] Scoring and ranking the candidates...")
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
        f"  [Images] Matching {len(filtered_images)} images to {len(event_skeletons)} events..."
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
    Generate person life events dataset using proposal-and-research approach.

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

    # Load cache (no Commons images; the image step fetches them)
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

    # PROPOSAL: the event skeletons and chapters
    print(
        f"[Step 4/11] Proposing the events (model: {model}, reasoning: {PROPOSAL_REASONING_EFFORT})..."
    )
    proposal_prompt = build_proposal_prompt(
        page_data,
        summary_data,
        subject,
        related_articles,
        deutsche_biographie_text=db_prompt_text,
    )
    life_plan = propose_events(proposal_prompt, model)
    print(
        f"[Step 4/11] Generated {len(life_plan.event_skeletons)} event skeletons "
        f"in {len(life_plan.chapters)} chapters"
    )

    # RESEARCH: the details of each event (no images yet)
    print(
        f"[Step 5/11] Researching the events (model: {RESEARCH_MODEL}, reasoning: {RESEARCH_REASONING_EFFORT})..."
    )
    event_details_list = research_all_event_details(
        event_skeletons=life_plan.event_skeletons,
        person_name=life_plan.person.name,
        all_related_articles=related_articles or [],
        deutsche_biographie_text=db_prompt_text,
        subject_article=page_data,
    )
    print(f"[Step 5/11] Researched details for {len(event_details_list)} events")

    # MERGE: Combine skeletons + details
    print("[Step 6/11] Merging event skeletons with details...")
    merged_events = merge_all_events(life_plan.event_skeletons, event_details_list)

    # CHAPTERS: date the partition the proposal drew from the researched events
    print("[Step 7/11] Dating chapters from their events...")
    chapters = build_chapters(life_plan.chapters, merged_events)
    conclusion = life_plan.conclusion
    print(f"[Step 7/11] Dated {len(chapters)} chapters")

    # IMAGES: search, rank, match, verify
    print(
        f"[Step 8/11] Finding images for the events (model: {assign.IMAGE_SEARCH_MODEL}, reasoning: {assign.IMAGE_SEARCH_REASONING}/{assign.IMAGE_MATCH_REASONING})..."
    )
    enriched_events, portrait = research_images_for_all_events(
        merged_events=merged_events,
        event_skeletons=life_plan.event_skeletons,
        event_details_list=event_details_list,
        person_name=life_plan.person.name,
    )
    images_assigned = sum(1 for e in enriched_events if e.images)
    print(
        f"[Step 8/11] Assigned images to {images_assigned} / {len(enriched_events)} events"
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
    print("[Step 9/11] Normalizing dataset metadata...")
    payload = enforce_metadata(payload, page_data, summary_data)
    print(f"[Step 9/11] Dataset includes {len(payload['events'])} events")

    # Geocode with enhanced logic
    print("[Step 10/11] Resolving event location coordinates...")
    payload, geocoded_events = enrich_event_coordinates_v2(payload)
    print(f"[Step 10/11] Coordinates resolved for {geocoded_events} events")

    # Write to file
    print(f"[Step 11/11] Writing dataset for '{identifier}'...")
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
        from sync_meta_story_events import describe_dropped, sync_meta_story_events

        sync_report = sync_meta_story_events(
            identifier, old_person_data=old_payload, new_person_data=payload
        )
        if sync_report["stories"]:
            print(
                f"Incrementally updated {sync_report['stories']} meta story/stories "
                f"({sync_report['updated']} references changed, "
                f"{sync_report['removed']} removed)"
            )
        for line in describe_dropped(sync_report):
            print(line)
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

    A generated portrait wins over the AI-selected one and keeps the
    attribution it was stored with. The stylized artwork is a derivative of one
    specific original, so `originalImage`, `source`, and the other original*
    keys go on naming that original; a candidate this run happens to pick
    describes an image the artwork was never derived from. `originalImage` is
    also the reference `generate_person_portrait.py` reads back, so a swapped
    one would redirect the next `--force` run as well. The attribution is
    written by the portrait step, which knows the original it stylized.
    """
    if existing_generated:
        print(f"{indent}Keeping the generated portrait and its attribution")
        return existing_generated
    if ai_portrait:
        portrait_data = {
            "image": ai_portrait["url"],
            "source": ai_portrait["source"],
        }
        for key in ("caption", "creator", "license", "licenseUrl"):
            if ai_portrait.get(key):
                portrait_data[key] = ai_portrait[key]
        return portrait_data
    return None


def image_assignment_block(img: Dict[str, Any]) -> Dict[str, Any]:
    """One stored image entry, keeping only the attribution fields that exist."""
    block = {"url": img["url"], "caption": img["caption"], "source": img["source"]}
    for key in ("creator", "license", "licenseUrl"):
        if img.get(key):
            block[key] = img[key]
    return block
