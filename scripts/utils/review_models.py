"""
Pydantic models for person data review system.

These models define the structure for AI-generated review outputs
with confidence scoring and detailed rationales.
"""

from typing import List, Optional, Dict
from pydantic import BaseModel, Field

# ============================================================
# EVENTS REVIEW MODELS
# ============================================================


class MetadataIssue(BaseModel):
    """Issue with person metadata (name, summary, dates, etc.)"""

    field: str
    issue: str
    suggested_fix: Optional[str] = None


class EventReview(BaseModel):
    """Review assessment for a single event"""

    event_index: int
    title_issue: Optional[str] = None
    description_issues: List[str] = Field(default_factory=list)
    annotation_issues: List[str] = Field(default_factory=list)
    metadata_issues: List[str] = Field(default_factory=list)
    source_verification: str
    icon_appropriateness: str
    suggested_improvements: List[str] = Field(default_factory=list)


class ChapterReview(BaseModel):
    """Review assessment for a chapter"""

    chapter_id: str
    headline_issue: Optional[str] = None
    coherence_assessment: str
    pacing_feedback: str


class ConclusionReview(BaseModel):
    """Review assessment for the conclusion statement"""

    issue: Optional[str] = None
    suggested_improvement: Optional[str] = None


class Annotation(BaseModel):
    """Annotation definition"""

    explanation: str
    wikipedia_url: Optional[str] = None


class LocationObject(BaseModel):
    """A place an event happened, in the schema the application reads.

    Coordinates are deliberately absent: the reviewer names the place and the
    geocoder resolves it, so a corrected location cannot arrive with
    model-authored coordinates attached.
    """

    name_historic: str
    name_modern: Optional[str] = None
    primary: bool


class EventChanges(BaseModel):
    """Proposed changes for a single event"""

    event_index: int
    new_title: Optional[str] = None
    new_description: Optional[str] = None
    new_date_end: Optional[str] = Field(
        None,
        description=(
            "Corrected end date for an event that spans a period (YYYY, "
            "YYYY-MM, or YYYY-MM-DD), only when the event's own description "
            "proves the span. The event's anchor date is not editable."
        ),
    )
    new_annotations: Optional[Dict[str, Annotation]] = None
    new_involved_people: Optional[List[str]] = None
    new_locations: Optional[List[LocationObject]] = None
    new_event_type_icon: Optional[str] = None
    confidence: int = Field(ge=1, le=5, description="Confidence rating 1-5")
    rationale: str


class ChapterChanges(BaseModel):
    """Proposed changes for a chapter"""

    chapter_id: str
    new_headline: Optional[str] = None
    confidence: int = Field(ge=1, le=5)
    rationale: str


class EventsChanges(BaseModel):
    """All proposed changes for life events"""

    events: List[EventChanges] = Field(default_factory=list)
    chapters: List[ChapterChanges] = Field(default_factory=list)
    conclusion: Optional[str] = None
    conclusion_confidence: Optional[int] = Field(None, ge=1, le=5)
    conclusion_rationale: Optional[str] = None


class CombinedReviewOutput(BaseModel):
    """Complete review output for both life events and network"""

    overall_assessment: str
    person_metadata_issues: List[MetadataIssue] = Field(default_factory=list)
    event_reviews: List[EventReview] = Field(default_factory=list)
    chapter_reviews: List[ChapterReview] = Field(default_factory=list)
    conclusion_review: Optional[ConclusionReview] = None
    connection_reviews: List["ConnectionReview"] = Field(default_factory=list)
    balance_assessment: str = ""
    events_changes: EventsChanges
    network_changes: "NetworkChanges"
    change_summary: str


# ============================================================
# NETWORK REVIEW MODELS
# ============================================================


class ConnectionReview(BaseModel):
    """Review assessment for a network connection"""

    person_name: str
    relationship_type_issue: Optional[str] = None
    description_issue: Optional[str] = None
    metadata_issues: List[str] = Field(default_factory=list)
    source_verification: str
    cross_reference_check: str


class CategorySummaryReview(BaseModel):
    """Review assessment for a category summary"""

    relationship_type: str
    issue: Optional[str] = None
    suggested_improvement: Optional[str] = None


class ConnectionMetadata(BaseModel):
    """Mutable metadata fields of a network connection.

    Fields are enumerated rather than left as an open mapping because OpenAI
    structured outputs require additionalProperties: false, which an
    arbitrary Dict[str, Any] cannot express.
    """

    start_year: Optional[int] = None
    end_year: Optional[int] = None
    strength: Optional[str] = None
    interaction_frequency: Optional[str] = None
    influence_direction: Optional[str] = None
    shared_activities: Optional[List[str]] = None
    notes: Optional[str] = None


class ConnectionChanges(BaseModel):
    """Proposed changes for a network connection"""

    person_name: str
    new_relationship_description: Optional[str] = None
    new_relationship_type: Optional[str] = None
    new_metadata: Optional[ConnectionMetadata] = None
    confidence: int = Field(ge=1, le=5)
    rationale: str


class CategorySummaryChanges(BaseModel):
    """Proposed changes for a category summary"""

    relationship_type: str
    new_summary: str
    confidence: int = Field(ge=1, le=5)
    rationale: str


class EgoChanges(BaseModel):
    """Proposed changes to the ego's own metadata"""

    name: Optional[str] = None
    birth_year: Optional[int] = None
    death_year: Optional[int] = None
    primary_roles: Optional[List[str]] = None
    summary: Optional[str] = None
    wikipedia: Optional[str] = None


class NetworkChanges(BaseModel):
    """All proposed changes for ego network"""

    ego: Optional[EgoChanges] = None
    connections: List[ConnectionChanges] = Field(default_factory=list)
    category_summaries: List[CategorySummaryChanges] = Field(default_factory=list)


class NetworkReviewOutput(BaseModel):
    """Complete review output for ego network"""

    overall_assessment: str
    ego_metadata_issues: List[str] = Field(default_factory=list)
    connection_reviews: List[ConnectionReview] = Field(default_factory=list)
    category_summary_reviews: List[CategorySummaryReview] = Field(default_factory=list)
    balance_assessment: str
    proposed_changes: NetworkChanges
    change_summary: str


# ============================================================
# STYLE REVIEW MODELS
# ============================================================


class StyleChanges(BaseModel):
    """Proposed changes for visual style"""

    new_primary: Optional[str] = None
    new_secondary: Optional[str] = None
    new_background: Optional[str] = None
    new_pattern_svg: Optional[str] = None
    new_fonts: Optional[Dict[str, str]] = None
    confidence: int = Field(ge=1, le=5)
    rationale: str


class StyleReviewOutput(BaseModel):
    """Complete review output for visual style"""

    overall_assessment: str
    color_palette_feedback: str
    pattern_feedback: str
    font_feedback: str
    proposed_changes: StyleChanges
    change_summary: str


# ============================================================
# REVIEW STATISTICS
# ============================================================


class ReviewStatistics(BaseModel):
    """Statistics about the review process"""

    total_changes_proposed: int
    high_confidence_changes_applied: int
    low_confidence_changes_skipped: int
    events_edited: int
    total_events: int
    chapters_edited: int
    total_chapters: int
    network_edited: int
    total_network: int
    avg_description_length_before: Optional[float] = None
    avg_description_length_after: Optional[float] = None
