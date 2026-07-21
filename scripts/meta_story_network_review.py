#!/usr/bin/env python3
"""AI review of a meta-story's derived social network.

The social network in ``meta_story_network.build_social_network`` is derived
*deterministically* from each person's ``ego_network.json``. Those ego networks
are generated per person and never saw the other meta-story people as a group,
so the union can miss direct ties between two main people, over-state vague ones
("influenced by"), or carry stale relationship wording.

This module adds an **AI review pass** that runs *after* derivation and *before*
clustering/narration. Given the derived network plus the relevant Wikipedia
material for the main people, the model may:

* **add** links between existing nodes that the ego networks missed,
* **modify** an existing link's type / description / strength, and
* **delete** rather indirect ties (e.g. a vague "influence" with no real
  contact).

How aggressively it prunes vs. enriches is scaled by the **density** of the
main-people subgraph: a sparse network invites generous, well-supported
additions; a dense one invites strict pruning of weak/indirect ties. The pass
is deterministic in how it *applies* the model's decisions (node ids are
validated, unordered pairs are matched regardless of orientation, degenerate
bridging nodes are cleaned up), so a bad model response can only edit links
between nodes that already exist — it can never introduce new people.

No graph data here is part of the translation payload, so a reviewed network is
copied verbatim into translated files, exactly like the derived one.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field

try:  # Package-style import (scripts/ on sys.path)
    from utils.wikipedia_cache import load_from_cache
except Exception:  # pragma: no cover - fallback for unusual import setups
    load_from_cache = None  # type: ignore

# How much Wikipedia text to feed per person. We keep the article lead plus the
# sentences that actually mention another main person, so the context stays
# focused on inter-person relationships (and the prompt stays affordable).
LEAD_CHARS = 700
MAX_RELATION_SENTENCES = 24
MAX_ARTICLE_CHARS = 4500

# Density thresholds for the strictness of the review (fraction of possible
# main<->main edges that actually exist).
SPARSE_BELOW = 0.22
DENSE_ABOVE = 0.5

_STRENGTHS = ("weak", "moderate", "strong")


# ---------------------------------------------------------------------------
# Structured-output schema
# ---------------------------------------------------------------------------


class ReviewLink(BaseModel):
    """An added or modified tie between two existing nodes."""

    source: str = Field(description="Node id of one endpoint (must already exist)")
    target: str = Field(
        description="Node id of the other endpoint (must already exist)"
    )
    relationship_type: str = Field(
        description="Category/subcategory, e.g. 'professional/colleague', "
        "'intellectual/influence', 'family/spouse'"
    )
    relationship_description: str = Field(
        description="One concrete sentence describing the tie and its basis"
    )
    strength: Literal["weak", "moderate", "strong"]
    rationale: str = Field(
        description="Why this tie is direct enough to add/keep (for the log; not stored)"
    )


class ReviewDeletion(BaseModel):
    """A tie to remove because it is indirect / vague / unsupported."""

    source: str
    target: str
    rationale: str = Field(description="Why this tie is too indirect to keep")


class NetworkReview(BaseModel):
    """The model's proposed edits to the derived network."""

    additions: List[ReviewLink] = Field(
        default_factory=list,
        description="New ties between existing nodes the ego networks missed",
    )
    modifications: List[ReviewLink] = Field(
        default_factory=list,
        description="Existing ties whose type/description/strength should change",
    )
    deletions: List[ReviewDeletion] = Field(
        default_factory=list,
        description="Existing ties to delete as too indirect/vague",
    )


# ---------------------------------------------------------------------------
# Context building
# ---------------------------------------------------------------------------


def _last_name_tokens(name: str) -> List[str]:
    """Distinctive (len>3) name tokens used to find mentions in article text."""
    cleaned = re.sub(r"[^A-Za-z\s'-]", " ", name or "")
    return [t for t in cleaned.split() if len(t) > 3]


def _split_sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[.!?])\s+", text or "")
    return [p.strip() for p in parts if p.strip()]


def _person_context(
    person_id: str,
    name: str,
    other_tokens: List[str],
) -> Optional[str]:
    """Build a focused Wikipedia excerpt for one main person.

    Returns the article lead plus every sentence mentioning another main person,
    capped. Returns ``None`` when no cache is available for the person.
    """
    if load_from_cache is None:
        return None
    try:
        page, summary, _ = load_from_cache(person_id)
    except Exception:
        return None

    lead = ""
    if isinstance(summary, dict):
        lead = (summary.get("extract") or "").strip()
    full = ""
    if isinstance(page, dict):
        full = (page.get("extract") or "").strip()
    if not lead and full:
        lead = full[:LEAD_CHARS].strip()
    if not lead and not full:
        return None

    pattern = None
    if other_tokens:
        pattern = re.compile(
            r"\b(" + "|".join(re.escape(t) for t in other_tokens) + r")\b",
            re.IGNORECASE,
        )

    relation_sentences: List[str] = []
    if pattern and full:
        seen = set()
        for sentence in _split_sentences(full):
            if pattern.search(sentence):
                key = sentence.lower()
                if key in seen:
                    continue
                seen.add(key)
                relation_sentences.append(sentence)
                if len(relation_sentences) >= MAX_RELATION_SENTENCES:
                    break

    chunk = lead[:LEAD_CHARS]
    if relation_sentences:
        chunk += "\n  Mentions of others: " + " ".join(relation_sentences)
    return chunk[:MAX_ARTICLE_CHARS]


def _main_density(
    nodes: List[Dict[str, Any]], links: List[Dict[str, Any]]
) -> Tuple[float, int, int]:
    """Density of the main<->main subgraph: (fraction, edges, possible)."""
    main_ids = {n["id"] for n in nodes if n.get("type") == "main"}
    possible = len(main_ids) * (len(main_ids) - 1) // 2
    edges = sum(
        1
        for link in links
        if link.get("source") in main_ids and link.get("target") in main_ids
    )
    density = edges / possible if possible else 0.0
    return density, edges, possible


def _strictness_guidance(density: float) -> str:
    if density < SPARSE_BELOW:
        return (
            "This network is SPARSE, so be GENEROUS and PREFER ADDING over "
            "deleting: add every well-supported tie you can justify from the "
            "material (shared work, documented correspondence, mentor/student, "
            "family, direct collaboration, AND well-documented intellectual "
            "influence even when the two never met in person, e.g. one person "
            "building directly on another's published work). Downgrade a weak "
            "tie's strength rather than removing it. Delete ONLY ties that are "
            "factually wrong or entirely unsupported — do NOT delete a genuine, "
            "documented influence just because the contact was indirect."
        )
    if density > DENSE_ABOVE:
        return (
            "This network is DENSE, so be STRICT: aggressively delete indirect, "
            "vague, or purely thematic ties (e.g. 'was influenced by' with no "
            "documented contact, or generic same-field association). Add a new "
            "tie only when the direct, concrete connection is unmistakable."
        )
    return (
        "This network has MODERATE density: add clearly direct ties that are "
        "missing, and delete only ties that are genuinely vague or indirect "
        "(e.g. an unsubstantiated 'influence' with no documented basis). Keep a "
        "well-documented influence but mark it as weak. Keep the graph honest, "
        "not crowded."
    )


def _humanize(node: Dict[str, Any]) -> str:
    roles = ", ".join(node.get("roles") or []) or "role unknown"
    year = node.get("birth_year") or "?"
    return f"{node['name']} ({year}; {roles})"


def build_review_prompt(
    network: Dict[str, Any],
    guidance: str,
    density: float,
    edges: int,
    possible: int,
) -> str:
    nodes = network.get("nodes") or []
    links = network.get("links") or []
    node_by_id = {n["id"]: n for n in nodes}
    main_nodes = [n for n in nodes if n.get("type") == "main"]
    secondary_nodes = [n for n in nodes if n.get("type") != "main"]

    people_lines = "\n".join(f"  - id: {n['id']} | {_humanize(n)}" for n in main_nodes)
    bridge_lines = (
        "\n".join(f"  - id: {n['id']} | {n['name']}" for n in secondary_nodes)
        or "  (none)"
    )

    tie_lines = []
    for link in links:
        s = node_by_id.get(link.get("source"), {}).get("name", link.get("source"))
        t = node_by_id.get(link.get("target"), {}).get("name", link.get("target"))
        tie_lines.append(
            f"  - {link.get('source')} <-> {link.get('target')} "
            f"({s} <-> {t}) [{link.get('kind')}; "
            f"{link.get('relationship_type', '')}; {link.get('strength', '')}]: "
            f"{link.get('relationship_description', '')}"
        )
    ties = "\n".join(tie_lines) or "  (no ties yet)"

    contexts = []
    for n in main_nodes:
        others = []
        for other in main_nodes:
            if other["id"] != n["id"]:
                others.extend(_last_name_tokens(other["name"]))
        ctx = _person_context(n["id"], n["name"], others)
        if ctx:
            contexts.append(f"### {n['name']} (id: {n['id']})\n{ctx}")
    context_block = "\n\n".join(contexts) or "(no Wikipedia material available)"

    return f"""You are reviewing the social network of a biographical story collection.

The graph's MAIN people (nodes you may connect):
{people_lines}

BRIDGING acquaintances already in the graph (secondary nodes; you may connect to
or prune ties involving them, but do NOT invent new people):
{bridge_lines}

CURRENT TIES (source <-> target ids):
{ties}

Main-subgraph density: {edges}/{possible} possible edges = {density:.2f}.
{guidance}

RELEVANT WIKIPEDIA MATERIAL (article leads + sentences mentioning other main
people):

{context_block}

TASK — propose edits to the tie set, grounded ONLY in the material and
well-established facts:
- additions: direct ties missing from the graph. Use EXISTING node ids only
  (source and target must both appear above). Never introduce a new person.
- modifications: existing ties whose relationship_type, description, or strength
  should change to be more accurate. Repeat the SAME source/target ids.
- deletions: existing ties that are too indirect/vague to belong in a social
  network (a documented mentorship stays; a one-line "was influenced by" with no
  contact goes).
- relationship_type must follow the "category/subcategory" convention, e.g.
  professional/colleague, professional/mentor, intellectual/influence,
  intellectual/correspondent, family/spouse, friendship/close-friend.
- strength is one of: weak, moderate, strong.
- Do not restate ties that should stay unchanged. Only list real edits.
- Ties are undirected; order of source/target does not matter."""


# ---------------------------------------------------------------------------
# Applying edits
# ---------------------------------------------------------------------------


def _pair(a: str, b: str) -> frozenset:
    return frozenset((a, b))


def _kind_for(source_node: Dict[str, Any], target_node: Dict[str, Any]) -> str:
    return (
        "main"
        if source_node.get("type") == "main" and target_node.get("type") == "main"
        else "secondary"
    )


def _endpoints_for(
    source: str,
    target: str,
    source_node: Dict[str, Any],
    target_node: Dict[str, Any],
    info: Dict[str, Any],
) -> Dict[str, Any]:
    """Build an ``endpoints`` map consistent with build_social_network: both
    perspectives for a main<->main tie, only the main side(s) for a bridge."""
    endpoints: Dict[str, Any] = {}
    if source_node.get("type") == "main":
        endpoints[source] = dict(info)
    if target_node.get("type") == "main":
        endpoints[target] = dict(info)
    if not endpoints:  # secondary<->secondary (rare): keep one entry
        endpoints[source] = dict(info)
    return endpoints


def apply_review(
    network: Dict[str, Any],
    review: NetworkReview,
    verbose: bool = False,
) -> Dict[str, Any]:
    """Apply the model's edits to a copy of the network, defensively.

    Invalid edits (unknown node ids, self-loops) are skipped. Returns the edited
    network; the original is left untouched.
    """
    nodes = [dict(n) for n in (network.get("nodes") or [])]
    links = [dict(link) for link in (network.get("links") or [])]
    node_by_id = {n["id"]: n for n in nodes}
    links_by_pair: Dict[frozenset, Dict[str, Any]] = {
        _pair(link["source"], link["target"]): link for link in links
    }

    added = modified = deleted = 0

    # 1) Deletions first.
    for d in review.deletions:
        key = _pair(d.source, d.target)
        link = links_by_pair.get(key)
        if link is None:
            continue
        links.remove(link)
        del links_by_pair[key]
        deleted += 1
        if verbose:
            print(f"    [-] delete {d.source} <-> {d.target}: {d.rationale}")

    # 2) Upserts (additions + modifications share one code path so a mislabeled
    #    edit still lands correctly).
    for edit in list(review.additions) + list(review.modifications):
        if edit.source == edit.target:
            continue
        s_node = node_by_id.get(edit.source)
        t_node = node_by_id.get(edit.target)
        if s_node is None or t_node is None:
            if verbose:
                print(
                    f"    [!] skip edit with unknown node: "
                    f"{edit.source} <-> {edit.target}"
                )
            continue
        if edit.strength not in _STRENGTHS:
            continue

        info = {
            "relationship_type": edit.relationship_type,
            "relationship_description": edit.relationship_description,
            "strength": edit.strength,
        }
        key = _pair(edit.source, edit.target)
        existing = links_by_pair.get(key)
        if existing is not None:
            existing.update(info)
            existing["endpoints"] = _endpoints_for(
                existing["source"],
                existing["target"],
                node_by_id[existing["source"]],
                node_by_id[existing["target"]],
                info,
            )
            existing["origin"] = "reviewed"
            modified += 1
            if verbose:
                print(f"    [~] modify {edit.source} <-> {edit.target}")
        else:
            link = {
                "source": edit.source,
                "target": edit.target,
                "kind": _kind_for(s_node, t_node),
                "relationship_type": edit.relationship_type,
                "relationship_description": edit.relationship_description,
                "strength": edit.strength,
                "endpoints": _endpoints_for(
                    edit.source, edit.target, s_node, t_node, info
                ),
                "origin": "review_added",
            }
            links.append(link)
            links_by_pair[key] = link
            added += 1
            if verbose:
                print(f"    [+] add {edit.source} <-> {edit.target}")

    # 3) Clean up degenerate bridging nodes: a secondary node only earns its
    #    place by connecting >= 2 main people. After edits, drop any secondary
    #    node that no longer does, along with its links.
    nodes, links = _prune_secondary(nodes, links)

    if verbose:
        print(
            f"  Review applied: +{added} added, ~{modified} modified, "
            f"-{deleted} deleted"
        )

    result = dict(network)
    result["nodes"] = nodes
    result["links"] = links
    return result


def _prune_secondary(
    nodes: List[Dict[str, Any]], links: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    node_type = {n["id"]: n.get("type") for n in nodes}
    while True:
        main_degree: Dict[str, int] = {}
        for link in links:
            for a, b in (
                (link["source"], link["target"]),
                (link["target"], link["source"]),
            ):
                if node_type.get(a) == "secondary" and node_type.get(b) == "main":
                    main_degree[a] = main_degree.get(a, 0) + 1
        drop = {
            nid
            for nid, typ in node_type.items()
            if typ == "secondary" and main_degree.get(nid, 0) < 2
        }
        if not drop:
            break
        nodes = [n for n in nodes if n["id"] not in drop]
        links = [
            link
            for link in links
            if link["source"] not in drop and link["target"] not in drop
        ]
        node_type = {n["id"]: n.get("type") for n in nodes}
    return nodes, links


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def review_social_network(
    network: Dict[str, Any],
    client: Any,
    model: str,
    reasoning_effort: str = "medium",
    verbose: bool = False,
) -> Dict[str, Any]:
    """Review and refine a derived social network with one AI call.

    Non-fatal: on any error (or an empty/degenerate network) the original
    network is returned unchanged.
    """
    nodes = network.get("nodes") or []
    links = network.get("links") or []
    main_count = sum(1 for n in nodes if n.get("type") == "main")
    if main_count < 2:
        return network

    density, edges, possible = _main_density(nodes, links)
    guidance = _strictness_guidance(density)
    prompt = build_review_prompt(network, guidance, density, edges, possible)

    if verbose:
        label = (
            "sparse"
            if density < SPARSE_BELOW
            else ("dense" if density > DENSE_ABOVE else "moderate")
        )
        print(f"  Main-subgraph density {edges}/{possible} = {density:.2f} ({label})")

    try:
        response = client.responses.parse(
            model=model,
            reasoning={"effort": reasoning_effort},
            input=[
                {
                    "role": "system",
                    "content": "You are a careful biographical network editor. "
                    "You add, refine, and prune social-network ties strictly from "
                    "the evidence provided, never inventing people or unsupported "
                    "connections.",
                },
                {"role": "user", "content": prompt},
            ],
            text_format=NetworkReview,
        )
        review = response.output_parsed
        if review is None:
            if verbose:
                print("  Network review returned no result, keeping derived network")
            return network
    except Exception as e:
        print(f"Warning: network review failed: {e}")
        return network

    return apply_review(network, review, verbose=verbose)
