#!/usr/bin/env python3
"""Schemas for the two model-driven stages, and for what they write to disk.

The pydantic models are the structured-output contract; the plain dictionaries
the stages persist are documented in ``evaluation/README.md`` and read by the
evaluator page and the merge script.
"""

from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, Field

ClaimType = Literal[
    "date",
    "place",
    "person",
    "role",
    "work",
    "event",
    "quantity",
    "attribution",
    "causal",
    "characterization",
]

CLAIM_TYPE_LABELS = {
    "date": "when something happened",
    "place": "where something happened",
    "person": "who was involved, and how they were related",
    "role": "a position, title, office, or occupation held",
    "work": "a book, paper, artwork, invention, or building",
    "event": "that something happened at all",
    "quantity": "a number, age, count, duration, or amount",
    "attribution": "a source, image credit, or authorship of material",
    "causal": "that one thing brought about another",
    "characterization": "an interpretation, judgment, or framing",
}


class ExtractedClaim(BaseModel):
    """One atomic assertion the story makes."""

    claim: str = Field(
        description=(
            "The assertion as a single standalone sentence, understandable with "
            "no other context: name the person, and name the date or place when "
            "the assertion depends on one."
        )
    )
    claim_type: ClaimType = Field(description="Which kind of assertion this is.")
    source_field: str = Field(
        description=(
            "The field of the supplied JSON the assertion comes from, such as "
            "'description', 'locations[0].name_historic', or 'summary'."
        )
    )
    source_text: str = Field(
        description=(
            "The exact text from the supplied JSON that carries the assertion, "
            "copied character for character."
        )
    )
    checkable: bool = Field(
        description=(
            "True when the assertion could be confirmed or refuted by a source. "
            "False for interpretation, judgment, and framing."
        )
    )


class ExtractionOutput(BaseModel):
    """Every claim one unit makes."""

    claims: List[ExtractedClaim]


EvidenceStance = Literal["supports", "contradicts", "related"]

EvidenceStatus = Literal["supported", "partial", "absent", "contradicted"]


class EvidenceQuote(BaseModel):
    """One passage of source material, copied exactly."""

    material_id: str = Field(description="The id of the excerpt the quote comes from.")
    quote: str = Field(
        description=(
            "The passage copied character for character from that excerpt, "
            "between five and sixty words, with no ellipsis and no edits."
        )
    )
    stance: EvidenceStance = Field(
        description=(
            "'supports' when the passage establishes the claim or part of it, "
            "'contradicts' when it states something incompatible, 'related' when "
            "it concerns the same matter without settling it."
        )
    )
    covers: str = Field(
        description="Which part of the claim this passage bears on, in a few words."
    )


class EvidenceOutput(BaseModel):
    """What the materials say about one claim."""

    status: EvidenceStatus = Field(
        description=(
            "'supported' when the excerpts establish the whole claim, 'partial' "
            "when they establish part of it, 'contradicted' when they state "
            "something incompatible, 'absent' when they do not bear on it."
        )
    )
    quotes: List[EvidenceQuote]
    notes: str = Field(
        description=(
            "One or two sentences on what the excerpts do and do not establish. "
            "Say plainly when nothing in them bears on the claim."
        )
    )


# The verdicts the evaluator page offers. Kept here because the merge script
# groups and orders by them and the page must not disagree with the report.
VERDICTS = (
    "supported",
    "partly_supported",
    "unsupported",
    "contradicted",
    "not_a_claim",
    "misextracted",
    "unclear",
)

VERDICT_LABELS = {
    "supported": "Supported",
    "partly_supported": "Partly supported",
    "unsupported": "Unsupported",
    "contradicted": "Contradicted",
    "not_a_claim": "Not a factual claim",
    "misextracted": "Misextracted",
    "unclear": "Cannot decide",
}

# Verdicts that say something went wrong in the story itself, as opposed to
# something the evaluation could not settle or the extractor got wrong.
PROBLEM_VERDICTS = ("partly_supported", "unsupported", "contradicted")

EVIDENCE_QUALITY = ("conclusive", "partial", "irrelevant", "none")

EVIDENCE_QUALITY_LABELS = {
    "conclusive": "Quotes settle it",
    "partial": "Quotes help, but do not settle it",
    "irrelevant": "Quotes do not bear on the claim",
    "none": "No quotes offered",
}

SEVERITY = ("none", "minor", "moderate", "serious")

SEVERITY_LABELS = {
    "none": "No consequence",
    "minor": "Minor: a detail a reader would not act on",
    "moderate": "Moderate: a reader would carry away something wrong",
    "serious": "Serious: misrepresents the person or the historical record",
}

CONFIDENCE = ("low", "medium", "high")
