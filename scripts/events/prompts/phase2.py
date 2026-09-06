"""What Phase 2 is told about one event, and which articles it is shown.

The budget is the design. The subject's own article goes in at 30000
characters as the primary source; the articles relevant to this event go in at
6000 each, and only the eight that survive the relevance filter. What the call
is asked for is what the skeleton left open—historic and modern place names,
the people involved, sources, an icon, the terms the description leans on—plus
the Commons searches that would illustrate the event, written while its
material is still in front of the call.

When the event carries a classification, the class-specific block is appended
by `build_phase2_prompt_classified`, and it says what not to research: a field
the classification already holds is a field the prose must not repeat.
"""

import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from events.event_classes import EVENT_CLASS_CONFIG
from events.schemas import EventSkeleton
from icon_categories import format_icon_categories_for_prompt
from utils.prose_style import PROSE_STYLE_INSTRUCTIONS, description_contract_prompt


def filter_related_articles_for_event(
    event_skeleton: EventSkeleton,
    all_related_articles: List[Dict[str, Any]],
    max_articles: int = 5,
) -> List[Dict[str, Any]]:
    """
    Score and filter related articles for a specific event.

    Scoring:
    - Title keyword match: weight 3
    - Summary keyword match: weight 1
    - Title mentioned in event description: +100 boost

    Returns top N articles by score.
    """
    event_text = f"{event_skeleton.title} {event_skeleton.description}".lower()
    event_words = set(re.findall(r"\b\w{4,}\b", event_text))  # Words 4+ chars

    scored_articles = []
    for article in all_related_articles:
        title = article.get("title", "").lower()
        summary = article.get("summary", "").lower()

        title_words = set(re.findall(r"\b\w{4,}\b", title))
        summary_words = set(re.findall(r"\b\w{4,}\b", summary))

        title_overlap = len(event_words & title_words)
        summary_overlap = len(event_words & summary_words)

        score = (title_overlap * 3) + summary_overlap

        # Boost if article title mentioned in event description
        if title in event_skeleton.description.lower():
            score += 100

        scored_articles.append((score, article))

    # Sort by score descending, take top N
    scored_articles.sort(reverse=True, key=lambda x: x[0])
    return [article for score, article in scored_articles[:max_articles]]


# How much of each related article Phase 2 is shown, and how many it sees. The
# budget was 1000 characters of five articles — a lead paragraph each, enough to
# place a term and not enough to say what changed because of an event. The
# background writer (generate_event_backgrounds.py) reads the same material
# through the same numbers, and its report is written from it and from nothing
# else, so this is the number that decides whether a report can carry a detail
# at all. A lead paragraph is also the part of an article a model already
# knows; the specifics that make a report worth reading are further down.
RELATED_ARTICLE_CHARS = 6000
RELATED_ARTICLE_COUNT = 8

# How much of the subject's own article Phase 2 and the background writer are
# shown. The article is the primary source of the whole dataset and was, until
# this constant existed, not in either prompt at all — every location name,
# involved person, and source rested on model recall, with the related
# articles as the only text in front of it (#77). The cap keeps a long article
# from dwarfing the eight related excerpts; the events of a life cluster in
# its article's middle sections, so a front-truncated slice this size still
# carries most of them.
SUBJECT_ARTICLE_CHARS = 30000


def build_phase2_prompt_base(
    event_skeleton: EventSkeleton,
    person_name: str,
    filtered_related_articles: List[Dict[str, Any]],
    deutsche_biographie_text: Optional[str] = None,
    subject_article: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Build base Phase 2 prompt (common sections for all event types).

    Used for standard events (no classification) and as foundation for class-specific prompts.
    Focus on specific details for THIS event only (NO images - Phase 3).
    """
    # The material first, the event last. Every event of a life is researched
    # against the same article, the same second source and the same task
    # description, so those blocks are identical across the sixteen or so
    # calls a person costs, but a provider discounts a repeated prefix only
    # while nothing varying precedes it, and the four lines naming the event
    # used to precede all of it. Stated at the end the event also reads as the
    # question the material has been laid out to answer.
    event_section = "\n" + "=" * 60 + "\n"
    event_section += "RESEARCH DETAILS FOR THIS SPECIFIC EVENT:\n"
    event_section += "=" * 60 + "\n\n"
    event_section += f"Title: {event_skeleton.title}\n"
    event_section += f"Date: {event_skeleton.date}\n"
    event_section += f"Description: {event_skeleton.description}\n"
    event_section += f"Subject: {person_name}\n"

    # Add event class info if present
    if event_skeleton.event_class:
        class_type = event_skeleton.event_class.type
        event_section += f"Event Class: {class_type}\n"

    prompt = _subject_article_prompt_section(subject_article)

    # Add Deutsche Biographie context if available
    if deutsche_biographie_text:
        prompt += "\n" + deutsche_biographie_text + "\n"

    prompt += "\n" + "=" * 60 + "\n"
    prompt += "TASK: Provide the following details for THIS specific event:\n"
    prompt += "=" * 60 + "\n\n"

    prompt += "0. DESCRIPTION (with annotation markers):\n"
    prompt += "   - Return the event description with [[term|display]] markers inserted for any annotations\n"
    prompt += "   - If you create annotations (section 5 below), you MUST insert the markers into this description\n"
    prompt += "   - If no annotations, return the original description text unchanged\n"
    prompt += "   - Example: If annotating 'Leopoldstadt', change 'Leopoldstadt district' to '[[Leopoldstadt|Leopoldstadt district]]'\n"
    prompt += "   \n"
    # Build dynamic list of classification types
    class_types_str = "/".join(
        [config["display_name"].lower() for config in EVENT_CLASS_CONFIG.values()]
    )
    prompt += "   - Where the Phase 1 description falls short of the definition below, rewrite it.\n"
    prompt += "     You hold more of the article than Phase 1 saw. Add the fact the definition asks\n"
    prompt += "     for and the skeleton lacks, such as the name of the partner or the collaborator,\n"
    prompt += "     what they did, the place, or what led to the event, and cut what the definition\n"
    prompt += "     excludes. The result is 2-4 sentences; a skeleton of one sentence is extended,\n"
    prompt += "     never returned as it is. The article in front of you is the evidence for what\n"
    prompt += "     the sentence asserts, not a register to write in.\n\n"
    prompt += description_contract_prompt() + "\n"
    prompt += PROSE_STYLE_INSTRUCTIONS + "\n"
    prompt += "   The rules above hold for the description, every annotation explanation, and every text field of the classification.\n\n"

    prompt += "1. LOCATIONS (can be multiple):\n"
    prompt += "   - Identify ALL significant locations for THIS specific event\n"
    prompt += "   - IMPORTANT: Keep location names SHORT and at CITY LEVEL at maximum\n"
    prompt += "   - Do NOT include street addresses, building names, or exact venues\n"
    prompt += "   - For EACH location, provide:\n"
    prompt += "     * name_historic: City/region name at time (e.g., 'Königsberg', 'Ceylon', 'Cambridge')\n"
    prompt += "     * name_modern: Modern city/region for geocoding (e.g., 'Kaliningrad, Russia', 'Cambridge, UK')\n"
    prompt += "     * primary: true for main location, false for secondary\n"
    prompt += "   - Examples of GOOD location names:\n"
    prompt += "     * 'London' not 'Bletchley Park, Milton Keynes'\n"
    prompt += "     * 'Paris' not 'Sorbonne University, Paris'\n"
    prompt += "     * 'Berlin' not '10 Downing Street, Berlin'\n"
    prompt += "   - Multi-location examples:\n"
    prompt += "     * Voyages: departure port city + arrival port city\n"
    prompt += "     * Conferences: host city only (not venue name)\n"
    prompt += "     * Battles/campaigns: battle location cities/regions\n"
    prompt += "   - If truly unknown or non-geographic, return empty array\n"
    prompt += (
        "   - For single-location events, provide one location with primary=true\n\n"
    )

    prompt += "2. INVOLVED_PEOPLE:\n"
    prompt += "   - List people DIRECTLY involved in THIS specific event\n"
    prompt += f"   - EXCLUDE the main subject ({person_name})\n"
    prompt += (
        "   - Examples: collaborators, opponents, witnesses, family members present\n"
    )
    prompt += "   - Leave null if no other people directly involved\n\n"

    prompt += "3. SOURCES:\n"
    prompt += "   - 1-3 Wikipedia URLs that DOCUMENT THIS EVENT\n"
    prompt += f"   - The subject's own article is always valid: https://en.wikipedia.org/wiki/{quote(person_name.replace(' ', '_'))}\n"
    prompt += "     It is the right answer whenever no related article covers this event specifically,\n"
    prompt += "     which is the ordinary case — most events of a life are documented in the life's article\n"
    prompt += "   - A related article below is a source ONLY if it actually recounts this event. Being\n"
    prompt += "     supplied is not a qualification, and neither is being about the same field, the same\n"
    prompt += "     period, or a person who appears in it. An article about a later paper is not a source\n"
    prompt += "     for an earlier death; an article about a colleague is not a source for a posting\n"
    prompt += "   - One precise source beats three loose ones. Never pad the list\n\n"

    prompt += "4. EVENT_TYPE_ICON:\n"
    prompt += "   - Select the most appropriate MDI icon from the categories below\n"
    prompt += "   - Based on the semantic type of this event\n\n"

    prompt += "5. ANNOTATIONS (0-3 per event):\n"
    prompt += "   - An annotation is a tap-to-open gloss under the slide. It is the reader's only way to learn\n"
    prompt += "     what a term in the description is, since the slide shows nothing else about it\n"
    prompt += "   - THE TEST: read each noun phrase of the description as an educated general reader who is\n"
    prompt += "     not a specialist in the subject's field. Would that reader know what the term is and why\n"
    prompt += "     it matters here? If not, annotate it. A term every mathematician, architect, or historian\n"
    prompt += "     of the period knows still needs a gloss when the general reader does not\n"
    prompt += "   - Annotate on that test:\n"
    prompt += "     * Technical and scientific concepts, including the standard ones of a field\n"
    prompt += "       ('central limit theorem', 'general relativity', 'reaction-diffusion system', 'Entscheidungsproblem')\n"
    prompt += "     * Historical inventions and machines ('Difference Engine', 'Jacquard loom')\n"
    prompt += "     * Institutions whose role is not clear from their name ('Bletchley Park', 'Royal Society')\n"
    prompt += "     * Movements, events, and laws that carry context ('Anschluss', 'documenta', 'Nuremberg Laws')\n"
    prompt += "     * Regional and cultural terms unknown outside their area ('Matura', 'soirée')\n"
    prompt += (
        "     * Works named by title where the sentence does not say what they are\n"
    )
    prompt += "   - Do not annotate:\n"
    prompt += "     * Person names, never, in any form (full names, first names, titles such as '8th Baron King',\n"
    prompt += "       nicknames). People belong in INVOLVED_PEOPLE (section 2)\n"
    prompt += f"     * The subject of this event's classification ({class_types_str}): the classification\n"
    prompt += "       carries the details, so glossing 'Z3' on an invention event or the partner on a marriage\n"
    prompt += "       event is redundant\n"
    prompt += "     * Well-known cities, countries, continents, regions, and geographic features (Paris, Japan,\n"
    prompt += "       Normandy, the Rhine), and common places (university, school, museum, studio)\n"
    prompt += "     * Well-known periods and events (WWII, Renaissance, Cold War) and basic cultural terms\n"
    prompt += "       (exhibition, retrospective, prize)\n"
    prompt += "     * A term the description itself explains: 'royal estate of Kaufungen' needs no gloss of\n"
    prompt += "       Kaufungen, 'Nazi youth organization' none of Hitler Youth, and a sentence that introduces\n"
    prompt += "       the term with an appositive ('Banburismus, a statistical method for reducing bombe work')\n"
    prompt += "       has already defined it. Annotate such a term only when the explanation can go past the\n"
    prompt += "       sentence, and then it says what the sentence does not (how the method worked, what the\n"
    prompt += "       name refers to) and repeats none of it\n"
    prompt += "   - Mark each term once, at its first occurrence, as [[term|display_text]]. The term is the\n"
    prompt += "     minimal noun phrase (1-4 words), never a clause: [[general relativity|general theory of\n"
    prompt += "     relativity]], not the sentence that contains it\n"
    prompt += "   - The explanation is 1-2 sentences: what the term is, and what it meant for this event where\n"
    prompt += "     the description does not already say so. Read it against the description before you\n"
    prompt += "     return it: an explanation that says the sentence again in other words is worse than none,\n"
    prompt += "     since the reader taps it and learns nothing. Optional: wikipedia_url for further reading\n"
    prompt += "   - Zero is right for an event whose description names no such term, and that is common: a\n"
    prompt += "     birth, a move, or a marriage told in plain words carries nothing to gloss. Do not invent an\n"
    prompt += "     annotation for a plain sentence, and do not withhold one from a term that fails the test;\n"
    prompt += "     the reader gets no other explanation\n\n"

    prompt += "6. IMAGE_SEARCH_QUERIES (3-4 short Commons searches):\n"
    prompt += "   - What would ILLUSTRATE this event: the machine, the building, the document,\n"
    prompt += "     the instrument, the place, the diagram\n"
    prompt += "   - Name the thing, not the person. The story already carries the subject's own\n"
    prompt += "     pictures, and a second portrait of them illustrates nothing\n"
    prompt += "   - 2-5 words each, the words a photograph of it would be filed under\n"
    prompt += "     * GOOD: 'Bombe machine Bletchley Park', 'Enigma machine naval four-rotor'\n"
    prompt += "     * BAD: 'Alan Turing portrait', 'cryptanalysis', 'World War II'\n"
    prompt += "   - Each query names a DIFFERENT thing the event's material mentions. Four searches\n"
    prompt += (
        "     for four angles on one machine return the same photograph four times\n"
    )
    prompt += "   - Return an empty list rather than guessing at something that might exist\n\n"

    # Add icon categories
    prompt += "\n" + "=" * 60 + "\n"
    prompt += "AVAILABLE ICONS:\n"
    prompt += "=" * 60 + "\n"
    prompt += format_icon_categories_for_prompt()
    prompt += "\n"

    prompt += event_section

    return prompt + _related_articles_prompt_section(filtered_related_articles)


def _subject_article_prompt_section(subject_article: Optional[Dict[str, Any]]) -> str:
    """The subject's own article as the primary source, ahead of everything else.

    It leads the prompt rather than trailing it: the same article is sent with
    every event of a life, and a repeated prefix is only discounted while
    nothing that varies per call precedes it.
    """
    extract = (subject_article or {}).get("extract", "")
    if not extract:
        return ""

    section = "\n" + "=" * 60 + "\n"
    section += "SUBJECT'S OWN WIKIPEDIA ARTICLE (primary source):\n"
    section += "=" * 60 + "\n"
    section += (
        "This is the article the whole story is drawn from. Ground every field "
        "you return in it before reaching for recall or for the related articles: "
        "historic and modern location names, involved people, sources, and any "
        "prose you write. Where it and your memory disagree, the article wins.\n\n"
    )
    title = subject_article.get("title", "") if subject_article else ""
    if title:
        section += f"TITLE: {title}\n"
    url = subject_article.get("fullurl", "") if subject_article else ""
    if url:
        section += f"URL: {url}\n"
    section += "-" * 60 + "\n"
    truncated = extract[:SUBJECT_ARTICLE_CHARS]
    section += f"{truncated}"
    if len(extract) > SUBJECT_ARTICLE_CHARS:
        section += "..."
    return section + "\n"


def _related_articles_prompt_section(
    filtered_related_articles: List[Dict[str, Any]],
) -> str:
    """Helper to add related articles section to Phase 2 prompts."""
    if not filtered_related_articles:
        return ""

    prompt = "\n" + "=" * 60 + "\n"
    prompt += f"RELATED ARTICLES (filtered for this event, top {len(filtered_related_articles)}):\n"
    prompt += "=" * 60 + "\n\n"

    for idx, article in enumerate(filtered_related_articles, 1):
        prompt += f"\nARTICLE {idx}: {article.get('title', 'Unknown')}\n"
        prompt += f"URL: {article.get('url', '')}\n"
        prompt += "-" * 60 + "\n"

        full_text = article.get("fullText", "")
        if full_text:
            truncated = full_text[:RELATED_ARTICLE_CHARS]
            prompt += f"{truncated}...\n\n"
        else:
            summary = article.get("summary", "")
            if summary:
                prompt += f"{summary}\n\n"

    return prompt


def build_phase2_prompt_classified(
    event_skeleton: EventSkeleton,
    person_name: str,
    filtered_related_articles: List[Dict[str, Any]],
    deutsche_biographie_text: Optional[str] = None,
    subject_article: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Generic Phase 2 prompt builder for classified events.
    Uses EVENT_CLASS_CONFIG to generate event-class-specific guidance.
    """
    # Get base prompt (sections 0-5) — DB text included via base
    base = build_phase2_prompt_base(
        event_skeleton,
        person_name,
        [],
        deutsche_biographie_text=deutsche_biographie_text,
        subject_article=subject_article,
    )

    # event_class is None for standard events. The only caller checks before
    # routing here, so this is belt-and-braces — but an unclassified event has
    # the same answer as an unrecognised class, so let it take that same path.
    class_type = event_skeleton.event_class.type if event_skeleton.event_class else None
    if class_type not in EVENT_CLASS_CONFIG:
        # Fallback to base prompt if config not found
        return base + _related_articles_prompt_section(filtered_related_articles)

    config = EVENT_CLASS_CONFIG[class_type]

    # Build class-specific guidance section
    prompt = base + f"\n\n{config['display_name']} EVENT SPECIFIC GUIDANCE:\n"
    prompt += "=" * 60 + "\n"
    prompt += f"This event has been classified as {config['name']} in Phase 1.\n"

    # List what the classification already contains
    fields_list = ", ".join(config["fields"].keys())
    prompt += f"The classification already contains: {fields_list}.\n\n"

    prompt += "Your Phase 2 research should focus on:\n"
    for focus_item in config["phase2_focus"]:
        prompt += f"{focus_item}\n"
    prompt += "\n"

    return prompt + _related_articles_prompt_section(filtered_related_articles)
