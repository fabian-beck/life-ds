/**
 * Derive highlightable clusters ("circles") from a meta story social network.
 *
 * Communities are found with deterministic greedy modularity merging (CNM):
 * every node starts as its own community and the pair of connected communities
 * with the highest modularity gain is merged until no merge improves
 * modularity. Ties are weighted by relationship strength so strong bonds pull
 * people into the same circle. The graphs are tiny (< 25 nodes), so the O(n³)
 * greedy approach is more than fast enough and, unlike label propagation,
 * fully deterministic.
 *
 * Unconnected nodes never form a cluster — they simply don't take part in the
 * scroll narration.
 */

const STRENGTH_WEIGHT = { strong: 3, moderate: 2, weak: 1 };

// Direct ties between two of the story's own people count triple: without the
// boost, two main people who share many acquaintances become such heavy hubs
// that modularity prefers splitting them apart (e.g. a married couple, each
// with their own half of a shared court), even though their direct bond is the
// story's strongest tie.
const MAIN_LINK_BOOST = 3;

function linkWeight(link) {
  const w = STRENGTH_WEIGHT[link.strength] || 2;
  return link.kind === "main" ? w * MAIN_LINK_BOOST : w;
}

function pairKey(a, b) {
  return a < b ? `${a}|${b}` : `${b}|${a}`;
}

/**
 * Partition node ids into communities by greedy modularity maximization.
 * @param {Array} links - links with resolved source/target ids and weights
 * @returns {Array<Set<string>>} communities with at least two members
 */
function detectCommunities(links) {
  // Start with one community per linked node.
  const communityOf = new Map(); // node id -> community id
  const members = new Map(); // community id -> Set of node ids
  const degree = new Map(); // community id -> summed weighted degree
  const between = new Map(); // pairKey(commA, commB) -> summed weight
  let m = 0; // total edge weight

  for (const link of links) {
    const w = linkWeight(link);
    m += w;
    for (const id of [link.source, link.target]) {
      if (!communityOf.has(id)) {
        communityOf.set(id, id);
        members.set(id, new Set([id]));
        degree.set(id, 0);
      }
      degree.set(id, degree.get(id) + w);
    }
    const key = pairKey(link.source, link.target);
    between.set(key, (between.get(key) || 0) + w);
  }
  if (m === 0) return [];

  // Repeatedly merge the connected community pair with the best modularity
  // gain: ΔQ = e_ab/m − deg_a·deg_b/(2m²). Iterating keys in sorted order
  // keeps the result independent of input ordering.
  for (;;) {
    let bestKey = null;
    let bestGain = 1e-9;
    for (const key of [...between.keys()].sort()) {
      const [a, b] = key.split("|");
      const gain =
        between.get(key) / m - (degree.get(a) * degree.get(b)) / (2 * m * m);
      if (gain > bestGain) {
        bestGain = gain;
        bestKey = key;
      }
    }
    if (!bestKey) break;

    const [a, b] = bestKey.split("|");
    // Merge b into a.
    for (const id of members.get(b)) {
      members.get(a).add(id);
      communityOf.set(id, a);
    }
    degree.set(a, degree.get(a) + degree.get(b));
    members.delete(b);
    degree.delete(b);
    between.delete(bestKey);
    // Re-point b's remaining inter-community edges at a.
    for (const key of [...between.keys()]) {
      const [x, y] = key.split("|");
      if (x !== b && y !== b) continue;
      const other = x === b ? y : x;
      const w = between.get(key);
      between.delete(key);
      if (other === a) continue;
      const merged = pairKey(a, other);
      between.set(merged, (between.get(merged) || 0) + w);
    }
  }

  return [...members.values()].filter((set) => set.size >= 2);
}

/**
 * Compute the ordered clusters for a meta story social network.
 *
 * @param {{nodes: Array, links: Array}} network - the `social_network` block
 * @returns {Array<{key: string, mains: Array, secondaries: Array,
 *   nodeIds: Set<string>, links: Array, yearStart: number|null,
 *   yearEnd: number|null}>} clusters ordered roughly by time (mean birth year
 *   of their main members)
 */
export function computeClusters(network) {
  if (!network?.nodes?.length || !network?.links?.length) return [];
  const nodeById = new Map(network.nodes.map((n) => [n.id, n]));
  const links = network.links.filter(
    (l) =>
      nodeById.has(l.source) && nodeById.has(l.target) && l.source !== l.target
  );
  if (!links.length) return [];

  const strengthRank = { strong: 3, moderate: 2, weak: 1 };
  const clusters = [];
  for (const ids of detectCommunities(links)) {
    const mains = [];
    const secondaries = [];
    for (const id of ids) {
      const node = nodeById.get(id);
      (node.type === "main" ? mains : secondaries).push(node);
    }
    if (!mains.length) continue;
    mains.sort(
      (a, b) =>
        (a.birth_year ?? Infinity) - (b.birth_year ?? Infinity) ||
        a.name.localeCompare(b.name)
    );
    secondaries.sort((a, b) => a.name.localeCompare(b.name));

    // Internal ties: main↔main bonds first (they carry the story), then
    // bridging ties, each strongest-first.
    const internal = links
      .filter((l) => ids.has(l.source) && ids.has(l.target))
      .sort(
        (a, b) =>
          (a.kind === "main" ? 0 : 1) - (b.kind === "main" ? 0 : 1) ||
          (strengthRank[b.strength] || 0) - (strengthRank[a.strength] || 0) ||
          pairKey(a.source, a.target).localeCompare(pairKey(b.source, b.target))
      );

    const years = mains
      .map((n) => n.birth_year)
      .filter((y) => typeof y === "number");
    clusters.push({
      key: mains.map((n) => n.id).join("+"),
      mains,
      secondaries,
      nodeIds: ids,
      links: internal,
      yearStart: years.length ? Math.min(...years) : null,
      yearEnd: years.length ? Math.max(...years) : null,
      meanYear: years.length
        ? years.reduce((a, b) => a + b, 0) / years.length
        : Infinity,
    });
  }

  // Roughly temporal order: by mean birth year of the main members, earliest
  // members breaking ties so overlapping generations still read forward.
  clusters.sort(
    (a, b) =>
      a.meanYear - b.meanYear ||
      (a.yearStart ?? Infinity) - (b.yearStart ?? Infinity) ||
      a.key.localeCompare(b.key)
  );
  return clusters;
}
