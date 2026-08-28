#!/usr/bin/env python3
"""The two prompts this evaluation puts on the wire.

They are kept apart from the stages that send them so that a change to what is
asked is visible as a change to this file, and so the report of an evaluation
run can quote the instructions it was produced under.
"""

from __future__ import annotations

from typing import Any, Dict, List

from .models import CLAIM_TYPE_LABELS

EXTRACTION_SYSTEM = (
    "You are a meticulous fact-extraction analyst. You decompose biographical "
    "text and data into the individual assertions it makes, and you never add, "
    "infer, or improve on what it says."
)

EVIDENCE_SYSTEM = (
    "You are a research assistant checking a biographical claim against source "
    "material. You quote sources exactly and you never quote from memory: if a "
    "passage is not in the supplied excerpts, it does not exist."
)


def extraction_prompt(
    person_name: str,
    unit_label: str,
    unit_scope: str,
    unit_json: str,
) -> str:
    """Ask for every assertion one unit of a person's dataset makes."""
    types = "\n".join(
        f"- {name}: {description}" for name, description in CLAIM_TYPE_LABELS.items()
    )
    return f"""SUBJECT: {person_name}
SECTION: {unit_label} (scope: {unit_scope})

Below is one part of a generated biographical dataset about {person_name}, as
it is stored. Extract every distinct assertion it makes.

An assertion is one proposition that could be checked on its own. Split
sentences that carry several: "In 1936 he published On Computable Numbers,
which introduced the universal machine" makes a claim about a date, a claim
about a publication, and a claim about that publication's content.

Rules:
- Cover the whole input. Structured fields assert things too: a date field
  claims when, a location claims where, an involved person claims who was
  present, an annotation claims what a term means, an image caption claims
  what a picture shows, a relationship claims how two people were connected.
- Write each claim so it stands alone. Resolve every pronoun, name
  {person_name} where the claim is about him or her, and carry the date or
  place in when the claim depends on it.
- Do not merge two assertions into one, and do not split one assertion into
  restatements of itself.
- Assert only what the input asserts. Never add background knowledge, never
  correct what looks wrong, and never soften what looks overstated.
- Copy source_text exactly from the input, character for character. It is the
  span the claim comes from, not a summary of it.
- Set checkable to false for interpretation, judgment, and framing — "his mind
  bridged mathematics and necessity" — and to true for anything a source could
  confirm or refute. Extract both kinds.

Claim types:
{types}

INPUT ({unit_scope}):
{unit_json}
"""


def evidence_prompt(
    person_name: str,
    claim: str,
    claim_type: str,
    story_context: str,
    excerpts: List[Dict[str, Any]],
) -> str:
    """Ask what the cached source materials say about one claim."""
    blocks = []
    for excerpt in excerpts:
        header = (
            f"[{excerpt['id']}] {excerpt['title']}"
            f" ({excerpt['source']}, {excerpt['language']})"
        )
        blocks.append(f"{header}\n{'-' * len(header)}\n{excerpt['text']}")
    joined = "\n\n".join(blocks)

    return f"""SUBJECT: {person_name}

CLAIM TO CHECK ({claim_type}):
{claim}

WHERE THE CLAIM COMES FROM:
{story_context}

Below are excerpts from the source materials this story was generated from.
Find every passage in them that supports the claim, and every passage that
contradicts it.

Rules:
- Quote only from the excerpts below. If the passage you want is not there,
  there is no such passage: report status "absent" rather than recalling one.
- Copy each quote character for character from the excerpt, including its
  spelling and punctuation. No ellipsis, no joining of separated sentences, no
  correction. A quote that cannot be found in the excerpt verbatim is discarded
  before an evaluator ever sees it.
- Keep each quote between five and sixty words: enough to stand on its own,
  little enough to read.
- Give the material_id of the excerpt each quote comes from.
- A claim can be supported in parts. Quote each part, and say in "covers" which
  part of the claim the passage bears on.
- Report status "supported" only when the excerpts establish the whole claim,
  "partial" when they establish part of it, "contradicted" when they state
  something incompatible with it, and "absent" when nothing in them bears on it.
- Dates, places, and numbers must match to count as support. A passage about
  the same event in a different year contradicts rather than supports.

EXCERPTS:
{joined}
"""
