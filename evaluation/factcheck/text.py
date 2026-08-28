#!/usr/bin/env python3
"""Text handling shared by the stages: identity, matching, and retrieval.

Three jobs that all reduce to comparing strings the model produced against
strings the repository already holds.

**Identity.** A fact needs an id that two evaluators, and a merge run weeks
later, arrive at independently. It is derived from the fact's own content, so
nothing has to be coordinated between runs.

**Matching.** A quote is evidence only if it is really in the source. The model
is asked for verbatim text and mostly complies, but it normalizes as it copies:
curly quotes straighten, an en dash becomes a hyphen, a line break inside a
paragraph becomes a space. Comparing on a normalized form accepts those and
still rejects a sentence the source does not contain.

**Retrieval.** The cached materials for one person run to hundreds of thousands
of characters, which is more than one call should carry per fact. Paragraphs are
therefore ranked against the claim by inverse-document-frequency-weighted
overlap and the best ones are sent. The ranking is deterministic, so a rerun
with the same inputs sends the same paragraphs.
"""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

# Punctuation the model silently rewrites while copying, mapped to the plain
# form both sides are compared in.
_PUNCTUATION_FOLD = {
    "‘": "'",
    "’": "'",
    "‚": "'",
    "‛": "'",
    "′": "'",
    "“": '"',
    "”": '"',
    "„": '"',
    "″": '"',
    "‐": "-",
    "‑": "-",
    "‒": "-",
    "–": "-",
    "—": "-",
    "―": "-",
    "−": "-",
    " ": " ",
    " ": " ",
    " ": " ",
    "…": "...",
}

_WORD = re.compile(r"[^\W\d_]+|\d+", re.UNICODE)

# Words too common to say anything about which paragraph answers a claim.
_STOPWORDS = frozenset("""
    a an and are as at be been but by for from had has have he her his in into is
    it its of on or she that the their them there they this to was were which who
    with von der die das des und ein eine einer im am zu
    """.split())


def fold(value: str) -> str:
    """The comparison form: NFKC, folded punctuation, collapsed whitespace.

    Case is kept. A quote that differs from the source only in case is a
    paraphrase of a proper noun often enough to be worth flagging, and the
    stages that use this compare machine-copied text, not user input.
    """
    normalized = unicodedata.normalize("NFKC", value or "")
    normalized = "".join(_PUNCTUATION_FOLD.get(char, char) for char in normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def digest(*parts: str) -> str:
    """A short content hash, the identity scheme for facts and bundles."""
    joined = "␟".join(fold(part) for part in parts)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:12]


def fact_id(person_id: str, unit_id: str, claim: str) -> str:
    """The identifier a fact keeps across bundles and result files.

    Derived from the claim rather than from its position, so reordering the
    sample, or sampling it again, leaves every id where it was. Re-running the
    extraction does change ids, because a reworded claim is a different claim;
    the dataset fingerprint on each file is what tells a merge that two result
    sets came from different extractions.
    """
    return f"{person_id}:{digest(person_id, unit_id, claim)}"


def find_quote(quote: str, haystack: str) -> Optional[Tuple[int, int]]:
    """Locate a quote in a source text, or report that it is not there.

    Returns the span in the *original* text, so the caller can show the quote
    where it sits rather than in the folded form it was matched in. The offset
    map is built once per call because folding can change length: "..." for an
    ellipsis is three characters where the source had one.
    """
    needle = fold(quote)
    if not needle:
        return None

    folded_chars: List[str] = []
    origins: List[int] = []
    previous_space = True  # leading whitespace is dropped, as in fold()
    for index, char in enumerate(unicodedata.normalize("NFC", haystack or "")):
        replacement = _PUNCTUATION_FOLD.get(char, char)
        if replacement.isspace() or (len(replacement) == 1 and replacement == " "):
            if previous_space:
                continue
            folded_chars.append(" ")
            origins.append(index)
            previous_space = True
            continue
        if replacement.strip() == "" and replacement:
            continue
        previous_space = False
        for part in unicodedata.normalize("NFKC", replacement):
            folded_chars.append(part)
            origins.append(index)

    folded = "".join(folded_chars).strip()
    # strip() only ever removes the trailing space this builder can leave.
    position = folded.find(needle)
    if position == -1:
        return None
    start = origins[position]
    end_index = min(position + len(needle) - 1, len(origins) - 1)
    return start, origins[end_index] + 1


@dataclass
class Chunk:
    """One retrievable paragraph of one material."""

    material_id: str
    index: int
    text: str
    start: int


def chunk_text(
    material_id: str, text: str, *, min_chars: int = 200, max_chars: int = 1400
) -> List[Chunk]:
    """Split a material into paragraph chunks with their offsets.

    Wikipedia extracts are paragraph-separated, so paragraphs are the natural
    unit: they are self-contained enough to quote from and small enough that a
    handful of them fit in one call. Short paragraphs — section headings, single
    sentences — are merged forward until they carry enough context to judge, and
    a paragraph longer than the cap is split on sentence ends.
    """
    chunks: List[Chunk] = []
    if not text:
        return chunks

    pending: List[str] = []
    pending_start = 0
    cursor = 0
    for paragraph in re.split(r"\n\s*\n", text):
        start = text.find(paragraph, cursor)
        if start == -1:  # pragma: no cover - split() results are always found
            start = cursor
        cursor = start + len(paragraph)
        stripped = paragraph.strip()
        if not stripped:
            continue
        if not pending:
            pending_start = start
        pending.append(stripped)
        joined = "\n\n".join(pending)
        if len(joined) < min_chars:
            continue
        for piece, offset in _split_long(joined, max_chars):
            chunks.append(
                Chunk(material_id, len(chunks), piece, pending_start + offset)
            )
        pending = []

    if pending:
        joined = "\n\n".join(pending)
        for piece, offset in _split_long(joined, max_chars):
            chunks.append(
                Chunk(material_id, len(chunks), piece, pending_start + offset)
            )
    return chunks


def _split_long(text: str, max_chars: int) -> List[Tuple[str, int]]:
    """Break an over-long paragraph on sentence boundaries."""
    if len(text) <= max_chars:
        return [(text, 0)]
    pieces: List[Tuple[str, int]] = []
    start = 0
    while start < len(text):
        if len(text) - start <= max_chars:
            pieces.append((text[start:], start))
            break
        window = text[start : start + max_chars]
        cut = max(window.rfind(". "), window.rfind("! "), window.rfind("? "))
        if cut <= 0:
            cut = window.rfind(" ")
        if cut <= 0:
            cut = max_chars
        else:
            cut += 1
        pieces.append((text[start : start + cut].strip(), start))
        start += cut
    return pieces


def tokens(value: str) -> List[str]:
    """Content words of a string, lowercased, without stopwords."""
    return [
        token
        for token in (match.group(0).lower() for match in _WORD.finditer(value or ""))
        if token not in _STOPWORDS and len(token) > 1
    ]


def inverse_document_frequency(documents: Sequence[Sequence[str]]) -> Dict[str, float]:
    """How much each token narrows the corpus down.

    A term in every paragraph ("Turing" in the Turing article) says nothing
    about which paragraph to send; a term in three of them says a great deal.
    """
    total = max(len(documents), 1)
    seen: Counter[str] = Counter()
    for document in documents:
        seen.update(set(document))
    return {token: math.log(1 + total / (1 + count)) for token, count in seen.items()}


def rank_chunks(
    query: str,
    chunks: Sequence[Chunk],
    idf: Dict[str, float],
) -> List[Tuple[float, Chunk]]:
    """Chunks scored against a claim, best first, ties broken deterministically.

    The score is the summed inverse document frequency of the query terms the
    chunk contains, divided by the square root of the chunk's length so that a
    long paragraph does not win on breadth alone.
    """
    query_terms = set(tokens(query))
    scored: List[Tuple[float, Chunk]] = []
    for chunk in chunks:
        present = query_terms.intersection(tokens(chunk.text))
        if not present:
            continue
        weight = sum(idf.get(term, 1.0) for term in present)
        scored.append((weight / math.sqrt(max(len(chunk.text), 1)), chunk))
    scored.sort(key=lambda pair: (-pair[0], pair[1].material_id, pair[1].index))
    return scored


def context_window(text: str, start: int, end: int, radius: int = 320) -> str:
    """The quote with enough of its surroundings to judge it in place."""
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    prefix = "…" if left > 0 else ""
    suffix = "…" if right < len(text) else ""
    return f"{prefix}{text[left:right].strip()}{suffix}"


def collapse(value: str, limit: int) -> str:
    """A one-line preview of a longer string, for logs and tables."""
    single = re.sub(r"\s+", " ", value or "").strip()
    if len(single) <= limit:
        return single
    return single[: limit - 1].rstrip() + "…"


# A separator no quote can contain, so concatenating candidate strings cannot
# make a match span two of them.
_SEPARATOR = " \u241f "


def _scalars(value: object) -> Iterable[str]:
    """Every scalar inside a nested JSON structure, as text.

    Numbers included: an age of 17 and a coordinate are things a claim can be
    extracted from as readily as a sentence is.
    """
    if isinstance(value, str):
        yield value
    elif isinstance(value, bool):
        yield "true" if value else "false"
    elif isinstance(value, (int, float)):
        yield str(value)
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _scalars(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _scalars(item)


def provenance_haystack(payload: object, serialized: str) -> str:
    """What a claim's quoted source text is checked against.

    Both forms of the same data, because the model copies from either. It sees
    the unit as JSON, so a quote can span a structure — a coordinate pair, a
    whole annotation — and match only the serialized form; but a sentence
    containing a double quote appears escaped there and matches only the raw
    field value. Failing to find a quote in either is what the check is for: a
    provenance that was invented rather than copied.
    """
    parts = [serialized, *_scalars(payload)]
    return _SEPARATOR.join(fold(part) for part in parts)
