"""
Pydantic models for person data review system.

These models define the structure for AI-generated review outputs
with confidence scoring and detailed rationales.
"""

from typing import List, Optional, Dict, Any
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
    bridge_statement_issue: Optional[str] = None
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
    """Location coordinate object"""
    label: str
    name: str
    primary: bool
    centroid: List[float]
    source: str


class EventChanges(BaseModel):
    """Proposed changes for a single event"""
    event_index: int
    new_title: Optional[str] = None
    new_description: Optional[str] = None
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
    new_bridge_statement: Optional[str] = None
    confidence: int = Field(ge=1, le=5)
    rationale: str


class EventsChanges(BaseModel):
    """All proposed changes for life events"""
    person_metadata: Optional[Dict[str, Any]] = None
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


class ConnectionChanges(BaseModel):
    """Proposed changes for a network connection"""
    person_name: str
    new_relationship_description: Optional[str] = None
    new_relationship_type: Optional[str] = None
    new_metadata: Optional[Dict[str, Any]] = None
    confidence: int = Field(ge=1, le=5)
    rationale: str


class CategorySummaryChanges(BaseModel):
    """Proposed changes for a category summary"""
    relationship_type: str
    new_summary: str
    confidence: int = Field(ge=1, le=5)
    rationale: str


class NetworkChanges(BaseModel):
    """All proposed changes for ego network"""
    ego: Optional[Dict[str, Any]] = None
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
