#!/usr/bin/env python3
"""Search one person's materials for what they say about one claim.

Separated from the command-line stage so that the retrieval and the quote
verification can be tested without a model, which is where the failures that
would quietly weaken an evaluation live: excerpts that never contained the
answer, and quotes that are not in any source.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .materials import Material
from .models import EvidenceOutput
from .prompts import EVIDENCE_SYSTEM, evidence_prompt
from .text import (
    Chunk,
    context_window,
    find_quote,
    inverse_document_frequency,
    rank_chunks,
    tokens,
)

DEFAULT_BUDGET = 45000
DEFAULT_MAX_EXCERPTS = 24

# Sections of a Wikipedia extract that are apparatus rather than statement: a
# list of further reading, a bibliography, a row of external links. They match
# a claim's proper nouns as well as any paragraph and support nothing, so they
# are left out of the searchable text rather than sent and ignored.
_APPARATUS = re.compile(
    r"^=+\s*(notes|references|citations|sources|further reading|bibliography|"
    r"external links|see also|einzelnachweise|literatur|weblinks|siehe auch)"
    r"\s*=+",
    re.IGNORECASE,
)


def is_apparatus(text: str) -> bool:
    """Whether a chunk is reference apparatus rather than prose."""
    return bool(_APPARATUS.match(text.strip()))


class MaterialIndex:
    """A person's materials, chunked once and searchable per claim."""

    def __init__(self, materials: Sequence[Material]) -> None:
        self.materials = {material.id: material for material in materials}
        self.chunks: List[Chunk] = []
        for material in materials:
            self.chunks.extend(
                chunk for chunk in material.chunks if not is_apparatus(chunk.text)
            )
        self.idf = inverse_document_frequency(
            [tokens(chunk.text) for chunk in self.chunks]
        )
        # The lead summary is always sent: it is short, and it anchors who the
        # claim is about when the ranked paragraphs are all about one episode.
        self.always = [
            chunk for chunk in self.chunks if chunk.material_id == "wp-summary"
        ][:1]

    def select(
        self,
        query: str,
        *,
        budget: int = DEFAULT_BUDGET,
        max_excerpts: int = DEFAULT_MAX_EXCERPTS,
    ) -> List[Chunk]:
        """The excerpts to send for one claim, best match first."""
        chosen: List[Chunk] = list(self.always)
        used = sum(len(chunk.text) for chunk in chosen)
        seen = {(chunk.material_id, chunk.index) for chunk in chosen}

        for _, chunk in rank_chunks(query, self.chunks, self.idf):
            if len(chosen) >= max_excerpts or used >= budget:
                break
            key = (chunk.material_id, chunk.index)
            if key in seen:
                continue
            seen.add(key)
            chosen.append(chunk)
            used += len(chunk.text)
        return chosen

    def excerpt_payload(self, chunks: Sequence[Chunk]) -> List[Dict[str, Any]]:
        """The excerpts as the prompt presents them."""
        payload = []
        for chunk in chunks:
            material = self.materials[chunk.material_id]
            payload.append(
                {
                    "id": f"{chunk.material_id}#{chunk.index}",
                    "title": material.title,
                    "source": material.source,
                    "language": material.language,
                    "text": chunk.text,
                }
            )
        return payload

    def locate(
        self, quote: str, preferred: str
    ) -> Tuple[Optional[str], Optional[Tuple[int, int]]]:
        """Find a quote in the materials, preferring the one it was filed under.

        A model that copies faithfully but mislabels the excerpt has still found
        real evidence, so every material is searched before the quote is called
        unverified. The material it was actually found in is what gets recorded.
        """
        candidates = [preferred] if preferred in self.materials else []
        candidates += [
            material_id for material_id in self.materials if material_id != preferred
        ]
        for material_id in candidates:
            span = find_quote(quote, self.materials[material_id].text)
            if span is not None:
                return material_id, span
        return None, None


def search_query(fact: Dict[str, Any]) -> str:
    """What the retrieval ranks paragraphs against.

    The claim itself, plus the span it was extracted from and the event's title:
    the claim is a rewritten sentence, and the original wording often carries the
    proper nouns that make a paragraph findable.
    """
    context = fact.get("context") or {}
    parts = [
        str(fact.get("claim") or ""),
        str(fact.get("source_text") or ""),
        str(context.get("event_title") or ""),
        str(fact.get("person_name") or ""),
    ]
    return " ".join(part for part in parts if part)


def story_context(fact: Dict[str, Any]) -> str:
    """How the claim is presented to the evidence call: where it comes from."""
    context = fact.get("context") or {}
    lines = [f"Section: {fact.get('unit_label') or fact.get('unit_id')}"]
    if context.get("event_date"):
        lines.append(f"Event date as the story gives it: {context['event_date']}")
    if fact.get("source_field"):
        lines.append(f"Field: {fact['source_field']}")
    if fact.get("source_text"):
        lines.append(f"Story text: \"{fact['source_text']}\"")
    return "\n".join(lines)


def verify_quotes(
    index: MaterialIndex,
    parsed: EvidenceOutput,
    excerpt_ids: Sequence[str],
) -> List[Dict[str, Any]]:
    """Check every quote against the sources and describe where it sits.

    A quote is kept whatever the verdict — a fabricated quote is a finding about
    the evidence stage, not something to hide — but it is marked, and the merge
    report counts the marks.
    """
    supplied = set(excerpt_ids)
    verified: List[Dict[str, Any]] = []
    for quote in parsed.quotes:
        raw_id = (quote.material_id or "").strip()
        preferred = raw_id.split("#", 1)[0]
        material_id, span = index.locate(quote.quote, preferred)
        record: Dict[str, Any] = {
            "quote": quote.quote,
            "stance": quote.stance,
            "covers": quote.covers,
            "claimed_material_id": raw_id,
            "material_id": material_id or preferred,
            "verified": material_id is not None,
            "from_supplied_excerpt": raw_id in supplied,
        }
        if material_id is not None and span is not None:
            material = index.materials[material_id]
            record["title"] = material.title
            record["url"] = material.url
            record["source"] = material.source
            record["language"] = material.language
            record["offset"] = span[0]
            record["context"] = context_window(material.text, span[0], span[1])
        verified.append(record)
    return verified


def build_input(
    person_name: str,
    fact: Dict[str, Any],
    excerpts: Sequence[Dict[str, Any]],
) -> List[Dict[str, str]]:
    """The message list for one evidence call."""
    return [
        {"role": "system", "content": EVIDENCE_SYSTEM},
        {
            "role": "user",
            "content": evidence_prompt(
                person_name,
                str(fact.get("claim") or ""),
                str(fact.get("claim_type") or "event"),
                story_context(fact),
                list(excerpts),
            ),
        },
    ]
