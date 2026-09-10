#!/usr/bin/env python3
"""Derive a social network for a meta-story from its people's ego networks.

The network is built deterministically (no AI) from the already-generated
``ego_network.json`` files:

* **Main nodes** are the meta-story's own people. A **main link** connects two
  main people when one appears in the other's ego network.
* **Secondary nodes** are people who are *not* in the meta-story but who appear
  in the ego networks of two or more main people — i.e. they introduce an
  important connection *between* the main people. They are rendered clearly
  smaller than the main nodes and are capped so the graph stays readable.

Because the network is derived from technical relationship data (names,
relationship types, strengths) it is copied verbatim into translated meta-story
files: node labels are person names (kept in the original language per the
translation rules) and ``relationship_type`` is localized by the UI. Only the
optional ``relationship_description`` falls back to English in other languages.

The one exception is ``social_network.narration`` — the network's clusters
("circles"), each stored with its main members and an AI-written story text
(see ``derive_clusters`` below and Phase 6 of ``generate_meta_story.py``) —
whose prose is part of the translation payload.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, cast

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
PEOPLE_DIR = DATA_DIR / "people"

# Cap on how many secondary (bridging) nodes to keep, so dense collections do
# not drown the main people in a cloud of minor connections.
MAX_SECONDARY_NODES = 14

_ROMAN_RE = re.compile(r"^m{0,4}(cm|cd|d?c{0,3})(xc|xl|l?x{0,3})(ix|iv|v?i{0,3})$")


def _strip_accents(value: str) -> str:
    return "".join(
        ch
        for ch in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(ch)
    )


def _clean_display_name(name: str) -> str:
    """Human-facing label: underscores → spaces, drop parenthetical/bracketed
    clarifications and comma-separated titles (e.g. "Otto III, Holy Roman
    Emperor" → "Otto III"), so node labels stay short and uncluttered."""
    cleaned = name.replace("_", " ")
    cleaned = re.sub(r"\s*\([^)]*\)", "", cleaned)
    cleaned = re.sub(r"\s*\[[^\]]*\]", "", cleaned)
    cleaned = cleaned.split(",")[0]
    return re.sub(r"\s+", " ", cleaned).strip()


def normalize_name(name: str) -> Optional[Dict[str, Any]]:
    """Normalize a person name for matching (mirrors the JS normalizePersonName).

    Returns a dict with ``full`` (lowercased, accent-free), ``tokens``,
    ``first`` and ``last`` tokens, or ``None`` for empty input.
    """
    if not name or not isinstance(name, str):
        return None

    normalized = name.strip()
    # Normalize hyphen variants to a plain hyphen.
    normalized = re.sub(r"[‐‑‒–—−]", "-", normalized)
    # Drop parenthetical / bracketed clarifications and comma-separated titles.
    normalized = re.sub(r"\s*\([^)]*\)", "", normalized)
    normalized = re.sub(r"\s*\[[^\]]*\]", "", normalized)
    normalized = re.sub(r",.*$", "", normalized)
    normalized = re.sub(r"\s+(jr|sr)\.?$", "", normalized, flags=re.IGNORECASE)

    normalized = _strip_accents(normalized).lower()
    normalized = normalized.replace("_", " ")
    normalized = re.sub(r"[^a-z0-9\s'\-]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()

    tokens = [t for t in normalized.split(" ") if t]
    if not tokens:
        return None

    return {
        "full": normalized,
        "tokens": tokens,
        "first": tokens[0],
        "last": tokens[-1],
    }


def _first_compatible(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    # Allow initials / prefixes: "alan" vs "a", "alan" vs "alan mathison".
    return a.startswith(b) or b.startswith(a)


def names_match(a: Optional[Dict[str, Any]], b: Optional[Dict[str, Any]]) -> bool:
    """Whether two normalized names refer to the same person."""
    if not a or not b:
        return False
    if a["full"] == b["full"]:
        return True
    if a["last"] != b["last"]:
        return False
    # Guard against regnal names ("Henry II" / "Otto III") matching on the
    # numeral alone — those require a full-string match, handled above.
    if _ROMAN_RE.match(a["last"]) or len(a["last"]) < 2:
        return False
    return _first_compatible(a["first"], b["first"])


def _secondary_key(norm: Dict[str, Any]) -> str:
    return "sec:" + re.sub(r"[^a-z0-9]+", "_", norm["full"]).strip("_")


def _load_ego_network(person_id: str) -> Optional[Dict[str, Any]]:
    path = PEOPLE_DIR / person_id / "ego_network.json"
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return cast(Optional[Dict[str, Any]], json.load(f))
    except Exception:
        return None


def _registry_index(registry: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {p.get("id"): p for p in registry.get("people", []) if p.get("id")}


def _portrait_for(person: Dict[str, Any]) -> Optional[str]:
    portrait = person.get("portrait") or {}
    return portrait.get("thumbnail") or portrait.get("image")


def _birth_year(person: Dict[str, Any]) -> Optional[int]:
    """Extract the birth year from a registry person's ``birthDate``.

    The year is anchored to the whole leading component so a B.C. date such as
    ``-000500-01-01`` yields -500 rather than the first four characters of it.
    """
    date = person.get("birthDate") or ""
    match = re.match(r"\s*(-?\d{1,6})(?:-|$)", str(date))
    return int(match.group(1)) if match else None


def _link_richness(link: Dict[str, Any]) -> Tuple[int, int]:
    """Sort key for choosing the better of two reciprocal links."""
    strength_rank = {"strong": 3, "moderate": 2, "weak": 1}.get(
        link.get("strength", ""), 0
    )
    desc_len = len(link.get("relationship_description") or "")
    return (strength_rank, desc_len)


def build_social_network(
    person_ids: List[str],
    registry: Dict[str, Any],
) -> Dict[str, Any]:
    """Build the ``social_network`` block for a meta-story.

    Args:
        person_ids: The meta-story's person IDs (main nodes).
        registry: The loaded ``persons.json`` registry.

    Returns:
        ``{"nodes": [...], "links": [...]}`` — always JSON-serializable, and
        empty lists when no relationships are found.
    """
    index = _registry_index(registry)
    main_ids = [pid for pid in person_ids if pid in index]

    # Precompute normalized names for the main people.
    main_norms: Dict[str, Dict[str, Any]] = {}
    for pid in main_ids:
        norm = normalize_name(index[pid].get("name", pid))
        if norm:
            main_norms[pid] = norm

    def match_main(conn_norm: Dict[str, Any], exclude: str) -> Optional[str]:
        for pid, norm in main_norms.items():
            if pid == exclude:
                continue
            if names_match(conn_norm, norm):
                return pid
        return None

    # Main ↔ main links, keyed by the unordered pair. Each value maps a
    # main person's id to that person's ego-network view of the other.
    main_links: Dict[Tuple[str, str], Dict[str, Dict[str, Any]]] = {}
    # Secondary candidates: key -> aggregated info.
    secondary: Dict[str, Dict[str, Any]] = {}

    for pid in main_ids:
        ego = _load_ego_network(pid)
        if not ego:
            continue
        for conn in ego.get("connections", []):
            conn_name = conn.get("person_name")
            conn_norm = normalize_name(conn_name or "")
            if not conn_norm:
                continue

            link_info = {
                "relationship_type": conn.get("relationship_type", ""),
                "relationship_description": conn.get("relationship_description", ""),
                "strength": conn.get("strength", ""),
            }

            other_main = match_main(conn_norm, exclude=pid)
            if other_main:
                pair = (min(pid, other_main), max(pid, other_main))
                # Store each direction separately so the UI can describe the tie
                # from either person's own perspective.
                endpoints = main_links.setdefault(pair, {})
                prev = endpoints.get(pid)
                if prev is None or _link_richness(link_info) > _link_richness(prev):
                    endpoints[pid] = link_info
                continue

            # Not a main person → potential bridging (secondary) node.
            key = _secondary_key(conn_norm)
            entry = secondary.setdefault(
                key,
                {
                    "name": _clean_display_name(conn_name),
                    "refs": {},  # main_id -> link_info
                },
            )
            # Keep the richest link per (secondary, main) pair.
            prev = entry["refs"].get(pid)
            if prev is None or _link_richness(link_info) > _link_richness(prev):
                entry["refs"][pid] = link_info

    # Keep only bridging secondaries (referenced by >= 2 main people) and cap.
    bridging = [
        (key, entry) for key, entry in secondary.items() if len(entry["refs"]) >= 2
    ]
    bridging.sort(
        key=lambda kv: (
            len(kv[1]["refs"]),
            sum(_link_richness(li)[0] for li in kv[1]["refs"].values()),
        ),
        reverse=True,
    )
    bridging = bridging[:MAX_SECONDARY_NODES]

    # Assemble nodes.
    nodes: List[Dict[str, Any]] = []
    for pid in main_ids:
        person = index[pid]
        nodes.append(
            {
                "id": pid,
                "name": _clean_display_name(person.get("name", pid)),
                "type": "main",
                "portrait": _portrait_for(person),
                "roles": (person.get("primaryRoles") or [])[:2],
                "birth_year": _birth_year(person),
            }
        )

    links: List[Dict[str, Any]] = []
    for pair in sorted(main_links.keys()):
        endpoints = main_links[pair]
        # Top-level fields (used for stroke width / native tooltip) come from the
        # richest available direction; `endpoints` carries both perspectives.
        primary = max(endpoints.values(), key=_link_richness)
        links.append(
            {
                "source": pair[0],
                "target": pair[1],
                "kind": "main",
                "relationship_type": primary["relationship_type"],
                "relationship_description": primary["relationship_description"],
                "strength": primary["strength"],
                "endpoints": endpoints,
            }
        )

    for key, entry in bridging:
        nodes.append(
            {
                "id": key,
                "name": entry["name"],
                "type": "secondary",
                "portrait": None,
                "roles": [],
                "birth_year": None,
            }
        )
        for main_id, link_info in entry["refs"].items():
            links.append(
                {
                    "source": main_id,
                    "target": key,
                    "kind": "secondary",
                    "relationship_type": link_info["relationship_type"],
                    "relationship_description": link_info["relationship_description"],
                    "strength": link_info["strength"],
                    # Only the main person's perspective exists for a bridge.
                    "endpoints": {main_id: link_info},
                }
            )

    return {"nodes": nodes, "links": links}


# ---------------------------------------------------------------------------
# Cluster ("circle") derivation
# ---------------------------------------------------------------------------

# Tie strength weights and the boost for direct main↔main links. Without the
# boost, two main people who share many acquaintances become such heavy hubs
# that modularity prefers splitting them apart (e.g. a married couple, each
# with their own half of a shared court), even though their direct bond is the
# story's strongest tie.
_STRENGTH_WEIGHT = {"strong": 3, "moderate": 2, "weak": 1}
_MAIN_LINK_BOOST = 3


def _cluster_link_weight(link: Dict[str, Any]) -> int:
    weight = _STRENGTH_WEIGHT.get(link.get("strength", ""), 2)
    return weight * _MAIN_LINK_BOOST if link.get("kind") == "main" else weight


def _pair_key(a: str, b: str) -> str:
    return f"{a}|{b}" if a < b else f"{b}|{a}"


def _detect_communities(links: List[Dict[str, Any]]) -> List[set]:
    """Greedy modularity merging (CNM), deterministic.

    Every node starts as its own community and the pair of connected
    communities with the highest modularity gain is merged until no merge
    improves modularity. Iterating keys in sorted order keeps the result
    independent of input ordering. The graphs are tiny (< 25 nodes), so the
    O(n³) greedy approach is fast enough and, unlike label propagation, fully
    deterministic. Unconnected nodes never form a community.
    """
    community_of: Dict[str, str] = {}
    members: Dict[str, set] = {}
    degree: Dict[str, float] = {}
    between: Dict[str, float] = {}
    m = 0.0

    for link in links:
        w = _cluster_link_weight(link)
        m += w
        for node_id in (link["source"], link["target"]):
            if node_id not in community_of:
                community_of[node_id] = node_id
                members[node_id] = {node_id}
                degree[node_id] = 0.0
            degree[node_id] += w
        key = _pair_key(link["source"], link["target"])
        between[key] = between.get(key, 0.0) + w
    if m == 0:
        return []

    while True:
        best_key = None
        best_gain = 1e-9
        for key in sorted(between.keys()):
            a, b = key.split("|")
            gain = between[key] / m - (degree[a] * degree[b]) / (2 * m * m)
            if gain > best_gain:
                best_gain = gain
                best_key = key
        if best_key is None:
            break

        a, b = best_key.split("|")
        for node_id in members[b]:
            members[a].add(node_id)
            community_of[node_id] = a
        degree[a] += degree[b]
        del members[b], degree[b], between[best_key]
        for key in list(between.keys()):
            x, y = key.split("|")
            if x != b and y != b:
                continue
            other = y if x == b else x
            pair_weight = between.pop(key)
            if other == a:
                continue
            merged = _pair_key(a, other)
            between[merged] = between.get(merged, 0.0) + pair_weight

    return [ids for ids in members.values() if len(ids) >= 2]


def derive_clusters(network: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Derive the ordered clusters ("circles") the UI narrates while scrolling.

    This is the only place the circles are detected. Phase 6 stores each
    cluster's main members as ``member_ids`` in the narration, and the client
    (``computeClusters`` in ``src/utils/networkClusters.js``) resolves those
    stored members against the graph rather than repeating the detection. The
    cluster ``key`` is the main ids in birth-year order joined with ``+``;
    narration texts are matched by that key. Clusters are ordered roughly by
    the mean birth year of their main members.
    """
    nodes = network.get("nodes") or []
    all_links = network.get("links") or []
    node_by_id = {n["id"]: n for n in nodes}
    links = [
        link
        for link in all_links
        if link.get("source") in node_by_id
        and link.get("target") in node_by_id
        and link["source"] != link["target"]
    ]
    if not links:
        return []

    strength_rank = {"strong": 3, "moderate": 2, "weak": 1}
    clusters: List[Dict[str, Any]] = []
    for ids in _detect_communities(links):
        mains = [node_by_id[i] for i in ids if node_by_id[i].get("type") == "main"]
        secondaries = [
            node_by_id[i] for i in ids if node_by_id[i].get("type") != "main"
        ]
        if not mains:
            continue
        mains.sort(
            key=lambda n: (
                n.get("birth_year") if n.get("birth_year") is not None else 10**9,
                n.get("name", ""),
            )
        )
        secondaries.sort(key=lambda n: n.get("name", ""))
        internal = sorted(
            (link for link in links if link["source"] in ids and link["target"] in ids),
            key=lambda link: (
                0 if link.get("kind") == "main" else 1,
                -strength_rank.get(link.get("strength", ""), 0),
                _pair_key(link["source"], link["target"]),
            ),
        )
        years = [n["birth_year"] for n in mains if isinstance(n.get("birth_year"), int)]
        clusters.append(
            {
                "key": "+".join(n["id"] for n in mains),
                "mains": mains,
                "secondaries": secondaries,
                "links": internal,
                "year_start": min(years) if years else None,
                "year_end": max(years) if years else None,
                "mean_year": sum(years) / len(years) if years else float("inf"),
            }
        )

    clusters.sort(
        key=lambda c: (
            c["mean_year"],
            c["year_start"] if c["year_start"] is not None else 10**9,
            c["key"],
        )
    )
    return clusters


def main() -> int:
    """CLI: print the derived network for a set of person IDs (for debugging)."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Derive a meta-story social network from ego networks"
    )
    parser.add_argument("person_ids", help="Comma-separated person IDs (main nodes)")
    args = parser.parse_args()

    registry_path = DATA_DIR / "persons.json"
    with open(registry_path, "r", encoding="utf-8") as f:
        registry = json.load(f)

    ids = [pid.strip() for pid in args.person_ids.split(",") if pid.strip()]
    network = build_social_network(ids, registry)
    print(json.dumps(network, indent=2, ensure_ascii=False))
    print(
        f"\n{len(network['nodes'])} nodes "
        f"({sum(1 for n in network['nodes'] if n['type'] == 'main')} main, "
        f"{sum(1 for n in network['nodes'] if n['type'] == 'secondary')} secondary), "
        f"{len(network['links'])} links",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
