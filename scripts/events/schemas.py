"""The shapes a life takes on its way from a model call to disk.

Two families live here. The dataset models—`Person`, `LifeChapter`,
`EventSkeleton`, `LifePlan`, `EventDetails`, `LifeEvent`—are what the phases
hand each other and what the written file is a dump of, so a field this module
does not name is a field the corpus cannot carry. The classification models are
the structured blocks a few kinds of event carry instead of prose; the rubric
that tells the phases how to detect and research them is a table of plain data
in `events/event_classes.py`.
"""

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field

# ============================================================================
# PYDANTIC MODELS
# ============================================================================


class ImageMetadata(BaseModel):
    """Metadata for an image associated with an event."""

    url: str = Field(description="The full URL of the image")
    caption: str = Field(
        description="A concise, factual description of what the image shows"
    )
    source: str = Field(
        description="The source URL, typically a Wikimedia Commons page"
    )
    # The image search reads all three off the file page, and ImageViewer
    # renders all three. They are declared here because a field this model does
    # not name is dropped by the model dump on the way to disk — which is how
    # the corpus came to ship CC BY-SA images with the attribution their
    # licenses require stripped out.
    creator: Optional[str] = Field(
        None, description="Who made the image, as the file page credits them"
    )
    license: Optional[str] = Field(
        None, description="License name, e.g. 'CC BY-SA 3.0' or 'Public domain'"
    )
    licenseUrl: Optional[str] = Field(  # noqa: N815 - the field the UI reads
        None, description="Link to the license text, when the file page gives one"
    )


class Annotation(BaseModel):
    """Explanation for an annotated term in event description."""

    explanation: str = Field(description="Clear, concise explanation (1-2 sentences)")
    wikipedia_url: Optional[str] = Field(
        None, description="Optional Wikipedia URL for further reading"
    )


# ============================================================================
# EVENT CLASSIFICATION MODELS (Phase 2 - Optional)
# ============================================================================


class BirthClassification(BaseModel):
    """Classification for the birth event that opens a life story."""

    type: Literal["birth"] = Field(default="birth", description="Always 'birth'")
    father: Optional[str] = Field(
        None, description="Full name of the father, if documented"
    )
    mother: Optional[str] = Field(
        None,
        description="Full name of the mother, including her maiden name when documented",
    )
    birth_name: Optional[str] = Field(
        None,
        description="Full name given at birth, only when it differs from the name the person is known by",
    )
    characterization: Optional[str] = Field(
        None,
        description="Brief characterization of the household born into (e.g., 'academic family', 'farming household') - 1-4 words",
    )


class DeathClassification(BaseModel):
    """Classification for the death event that closes a life story."""

    type: Literal["death"] = Field(default="death", description="Always 'death'")
    cause: Optional[str] = Field(
        None,
        description="Brief cause of death (e.g., 'heart failure', 'cyanide poisoning') - 1-6 words. "
        "Omit when the sources do not give one; never guess a cause",
    )
    characterization: Optional[str] = Field(
        None,
        description="Brief characterization of the circumstances (e.g., 'after long illness', 'sudden', "
        "'ruled a suicide', 'in exile') - 1-4 words",
    )
    place_of_rest: Optional[str] = Field(
        None,
        description="Burial or resting place, when documented (e.g., 'Assistens Cemetery, Copenhagen')",
    )


class MarriagePartnershipClassification(BaseModel):
    """Classification for marriage/partnership events."""

    type: Literal["marriage_partnership"] = Field(
        default="marriage_partnership", description="Always 'marriage_partnership'"
    )
    subtype: Literal["marriage", "partnership"] = Field(
        description="Marriage (legal/ceremonial) or partnership (domestic/romantic)"
    )
    partner: str = Field(description="Full name of spouse/partner")
    duration: Optional[str] = Field(
        None, description="Duration if applicable (e.g., 'until death', '17 years')"
    )
    children: Optional[int] = Field(
        None, description="Number of children from this union, if mentioned"
    )
    characterization: Optional[str] = Field(
        None,
        description=(
            "Brief characterization of the bond between the partners (e.g., 'devoted partnership', "
            "'political alliance', 'strained') - 1-4 words. Describe the relationship itself, not "
            "only the work the partners did together; a purely professional label such as 'close "
            "collaboration' does not characterize a marriage"
        ),
    )


class MigrationClassification(BaseModel):
    """Classification for migration events (emigration, immigration, relocation, exile, etc.)."""

    type: Literal["migration"] = Field(
        default="migration", description="Always 'migration'"
    )
    from_location: str = Field(description="Origin location (city/region/country)")
    to_location: str = Field(description="Destination location (city/region/country)")
    characterization: Optional[str] = Field(
        None,
        description="Nature of move (e.g., 'political exile', 'career opportunity') - 1-4 words",
    )


class InventionClassification(BaseModel):
    """Classification for invention/innovation events."""

    type: Literal["invention"] = Field(
        default="invention", description="Always 'invention'"
    )
    title: str = Field(description="Name/title of invention")
    description: str = Field(description="Brief technical description (1-2 sentences)")
    impact: Optional[str] = Field(
        None, description="Historical/practical impact (1-2 sentences)"
    )


class PublicationClassification(BaseModel):
    """Classification for publication events (books, papers, articles, etc.)."""

    type: Literal["publication"] = Field(
        default="publication", description="Always 'publication'"
    )
    title: str = Field(description="Title of the work")
    publication_type: Literal[
        "book", "paper", "article", "manuscript", "thesis", "essay"
    ] = Field(description="Type of publication")
    publisher: Optional[str] = Field(
        None,
        description="Publisher or journal name (e.g., 'Nature', 'Cambridge University Press')",
    )
    significance: Optional[str] = Field(
        None,
        description="Brief significance note (e.g., 'seminal work', 'controversial', 'bestseller') - 1-4 words",
    )
    impact: Optional[str] = Field(
        None,
        description=(
            "What happened because of the work — documented reception, "
            "influence, consequences (1-2 sentences). Never a summary of "
            "what the work depicts or contains. Omit when no impact is "
            "documented."
        ),
    )


# Union of all classification types
# Note: Using standard Union instead of discriminated union for OpenAI compatibility
EventClassification = Union[
    BirthClassification,
    DeathClassification,
    MarriagePartnershipClassification,
    MigrationClassification,
    InventionClassification,
    PublicationClassification,
]

# The same set keyed by the ``type`` a stored block carries, so anything that
# reads an event off disk can rebuild the block the pipeline works with.
CLASSIFICATION_MODELS = {
    "birth": BirthClassification,
    "death": DeathClassification,
    "marriage_partnership": MarriagePartnershipClassification,
    "migration": MigrationClassification,
    "invention": InventionClassification,
    "publication": PublicationClassification,
}


class Portrait(BaseModel):
    """Portrait information for the person."""

    image: Optional[str] = Field(None, description="URL of the portrait image")
    source: Optional[str] = Field(None, description="Source URL for the portrait")


class Person(BaseModel):
    """Metadata about the person."""

    name: str = Field(description="Full name of the person")
    birth_date: Optional[str] = Field(None, description="Birth date in ISO-8601 format")
    death_date: Optional[str] = Field(None, description="Death date in ISO-8601 format")
    primary_roles: List[str] = Field(
        description="2-3 primary roles/professions. Use short, generic, lowercase single words or two-word phrases. "
        "Examples: 'mathematician', 'physicist', 'writer', 'composer', 'computer scientist', 'monarch', 'inventor'. "
        "Avoid specific titles, company names, or idiosyncratic descriptions."
    )
    tagline: str = Field(
        description="Catchy, memorable phrase capturing the person's essence (3-7 words). "
        "Name the specific work, idea, or discovery; do not use a generic status noun such as "
        "'Pioneer of ...', 'Architect of ...', 'Father/Mother of ...', or 'Visionary of ...'."
    )
    summary: str = Field(description="Brief biographical summary")
    wikipedia: Optional[str] = Field(None, description="Wikipedia URL")
    portrait: Optional[Portrait] = Field(None, description="Portrait information")


class LifeChapter(BaseModel):
    """A chapter grouping a sequence of life events."""

    id: str = Field(
        description="Unique identifier for the chapter (lowercase, snake_case)"
    )
    headline: str = Field(
        description="Catchy, story-like chapter headline (2-5 words). Make it engaging and evocative, like a book chapter title. Avoid using 'and' - prefer vivid, specific headlines."
    )
    date_start: str = Field(
        description="ISO-8601 date when this chapter begins (YYYY-MM-DD, YYYY-MM, or YYYY)"
    )
    date_start_precision: str = Field(
        description="Precision level for start date: 'day', 'month', or 'year'"
    )
    date_end: str = Field(
        description="ISO-8601 date when this chapter ends (YYYY-MM-DD, YYYY-MM, or YYYY)"
    )
    date_end_precision: str = Field(
        description="Precision level for end date: 'day', 'month', or 'year'"
    )
    age_start: Optional[int] = Field(
        None, description="Subject's age at chapter start, null if not applicable"
    )
    age_end: Optional[int] = Field(
        None, description="Subject's age at chapter end, null if not applicable"
    )
    involved_people: Optional[List[str]] = Field(
        None,
        description="Names of key people involved during this life chapter (aggregated from events, exclude the main subject)",
    )
    location: Optional[str] = Field(
        None,
        description="Summary of the main geographic area for this chapter (e.g., 'England', 'United States', 'Central Europe') - not a list of places",
    )


# Phase 1 Models


class ChapterPlan(BaseModel):
    """Phase 1: a chapter as the plan names it.

    The plan says which events belong to a chapter by naming the chapter on
    each event skeleton, so the dates and ages of a chapter are not asked of
    the model at all: they are read off its first and last event once the
    events are researched.
    """

    id: str = Field(
        description="Unique identifier for the chapter (lowercase, snake_case)"
    )
    headline: str = Field(
        description="Catchy, story-like chapter headline (2-5 words). Make it engaging and evocative, like a book chapter title. Avoid using 'and' - prefer vivid, specific headlines."
    )
    location: Optional[str] = Field(
        None,
        description="Summary of the main geographic area for this chapter (e.g., 'England', 'United States', 'Central Europe') - not a list of places",
    )


class EventSkeleton(BaseModel):
    """Phase 1: Minimal event structure for planning the narrative."""

    date: str = Field(description="ISO-8601 date string (YYYY-MM-DD, YYYY-MM, or YYYY)")
    date_precision: str = Field(
        description="Precision level: 'day', 'month', or 'year'"
    )
    date_end: Optional[str] = Field(
        None, description="Optional end date for events spanning a range"
    )
    date_end_precision: Optional[str] = Field(
        None, description="Precision for the end date"
    )
    date_note: Optional[str] = Field(
        None, description="Note about date uncertainty or alternative representations"
    )
    age: Optional[int] = Field(
        None,
        description="Subject's age at the time of the event, null if not applicable",
    )
    title: str = Field(description="Brief title of the event (2-6 words)")
    description: str = Field(
        description="Detailed description of the event (2-4 sentences)"
    )
    weight: Optional[float] = Field(
        None,
        description=(
            "How much of this life the event turns on, 0.0 to 1.0, judged "
            "against the other events of THIS life rather than against history "
            "at large."
        ),
    )
    event_class: Optional[EventClassification] = Field(
        None,
        description="Structured classification for specific event types (marriage_partnership, migration, invention). Omit for standard biographical events.",
    )
    # Required of the plan and checked after parsing; optional on the model so
    # the skeleton stays usable as a plain event record elsewhere.
    chapter: Optional[str] = Field(
        None,
        description="ID of the chapter this event belongs to. Chapters are contiguous in time: every event of a chapter comes after every event of the previous chapter.",
    )


class LifePlan(BaseModel):
    """Phase 1 output: person metadata, chapters, event skeletons, conclusion."""

    dataset: str = Field(description="Name of the dataset")
    created_on: str = Field(description="Creation date in ISO-8601 format")
    person: Person = Field(description="Person metadata")
    chapters: List[ChapterPlan] = Field(
        description="3-6 chapters in chronological order, each named by at least two event skeletons"
    )
    event_skeletons: List[EventSkeleton] = Field(
        description="List of event skeletons (minimal event data)"
    )
    conclusion: str = Field(
        description="What came of this person's life, stated as facts in 2-4 sentences: what of their work is still in use, still read, still built on, and by whom, one sentence per strand of the work that persists."
    )


# Phase 2 Models


class LocationInfo(BaseModel):
    """Location information with historic and modern names."""

    name_historic: str = Field(
        description="Location name at time of event (e.g., 'Königsberg', 'Ceylon')"
    )
    name_modern: Optional[str] = Field(
        None,
        description="Modern geographic name for geocoding (e.g., 'Kaliningrad, Russia')",
    )
    centroid: Optional[List[float]] = Field(
        None, description="[longitude, latitude] coordinates, or null if not geocoded"
    )
    primary: bool = Field(
        default=True, description="True if this is the primary/main location"
    )


class EventDetails(BaseModel):
    """Phase 2: Research details for a specific event (NO images - handled in Phase 3)."""

    description: Optional[str] = Field(
        None,
        description="Event description with [[term|display]] markers for annotations. If no annotations, return the original description unchanged.",
    )
    locations: Optional[List[LocationInfo]] = Field(
        None,
        description="Array of location objects. Can be empty or contain multiple locations.",
    )
    involved_people: Optional[List[str]] = Field(
        None,
        description="Names of people directly involved in this event (exclude the main subject)",
    )
    sources: List[str] = Field(
        default_factory=list,
        description="Array of Wikipedia URLs or references supporting this event",
    )
    image_search_queries: List[str] = Field(
        default_factory=list,
        description=(
            "3-4 Wikimedia Commons search queries for pictures that illustrate "
            "THIS event — the machine, the building, the document, the place "
            "it names. Not portraits of the subject."
        ),
    )
    event_type_icon: Optional[str] = Field(
        None, description="MDI icon identifier (e.g., 'mdi-crown', 'mdi-book')"
    )
    annotations: Optional[Dict[str, Annotation]] = Field(
        None, description="Dictionary mapping term keys to their explanations"
    )


# Final Model


class LifeEvent(BaseModel):
    """Final merged event (skeleton + details)."""

    date: str = Field(description="ISO-8601 date string")
    date_precision: str = Field(description="Precision level")
    date_end: Optional[str] = None
    date_end_precision: Optional[str] = None
    date_note: Optional[str] = None
    age: Optional[int] = None
    title: str = Field(description="Brief title of the event")
    description: str = Field(description="Detailed description")
    locations: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Unified location array with name_historic/name_modern/centroid/primary",
    )
    involved_people: Optional[List[str]] = Field(
        None, description="People directly involved in this event"
    )
    sources: List[str] = Field(description="Array of Wikipedia URLs or references")
    images: Optional[List[ImageMetadata]] = None
    event_type_icon: Optional[str] = Field(None, description="MDI icon identifier")
    chapter: Optional[str] = Field(None, description="Chapter ID this event belongs to")
    annotations: Optional[Dict[str, Annotation]] = Field(
        None, description="Dictionary mapping term keys to their explanations"
    )
    background: Optional[str] = Field(
        None, description="Background report behind the event"
    )
    background_images: Optional[List[Dict[str, Any]]] = Field(
        None, description="Context pictures for the background report"
    )
    weight: Optional[float] = Field(
        None, description="How much of the life this event turns on, 0.0 to 1.0"
    )
    event_class: Optional[EventClassification] = Field(
        None, description="Structured classification for specific event types"
    )
