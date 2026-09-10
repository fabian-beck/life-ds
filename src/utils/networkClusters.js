/**
 * Resolve the highlightable clusters ("circles") of a meta story social
 * network from the circles stored in its narration.
 *
 * The pipeline decides the circles and stores each one's main members as
 * `member_ids` (`social_network.narration.circles`): Phase 6 detects them by
 * greedy modularity over the reviewed graph, and the composer may later
 * merge, split, reorder, or discard them. The client never repeats that
 * detection; it only resolves the stored members against the graph, attaches
 * the bridging people, and collects each circle's internal ties. A narration
 * without `member_ids` yields no circles, and the section shows no cards.
 */

function pairKey(a, b) {
  return a < b ? `${a}|${b}` : `${b}|${a}`;
}

const STRENGTH_RANK = { strong: 3, moderate: 2, weak: 1 };

/**
 * Sort a cluster's internal ties: main↔main bonds first (they carry the
 * story), then bridging ties, each strongest-first.
 */
function sortInternalLinks(links, ids) {
  return links
    .filter((l) => ids.has(l.source) && ids.has(l.target))
    .sort(
      (a, b) =>
        (a.kind === "main" ? 0 : 1) - (b.kind === "main" ? 0 : 1) ||
        (STRENGTH_RANK[b.strength] || 0) - (STRENGTH_RANK[a.strength] || 0) ||
        pairKey(a.source, a.target).localeCompare(pairKey(b.source, b.target))
    );
}

/**
 * Compute the ordered clusters for a meta story social network.
 *
 * Circles come from the narration's `member_ids`, in their stored order. Main
 * members are sorted by birth year and name, which is the order the pipeline
 * stores and the order its circle `key` encodes. Secondary (bridging) nodes
 * join the circle holding most of their main neighbors, earlier circle
 * winning ties; unassigned ones stay outside every circle.
 *
 * @param {{nodes: Array, links: Array, narration?: Object}} network - the
 *   `social_network` block
 * @returns {Array<{key: string, mains: Array, secondaries: Array,
 *   nodeIds: Set<string>, links: Array}>} ordered clusters
 */
export function computeClusters(network) {
  if (!network?.nodes?.length || !network?.links?.length) return [];
  const nodeById = new Map(network.nodes.map((n) => [n.id, n]));
  const links = network.links.filter(
    (l) =>
      nodeById.has(l.source) && nodeById.has(l.target) && l.source !== l.target
  );
  if (!links.length) return [];

  const circles = (network.narration?.circles || []).filter(
    (c) => Array.isArray(c.member_ids) && c.member_ids.length
  );

  const clusters = [];
  for (const circle of circles) {
    const mains = circle.member_ids
      .map((id) => nodeById.get(id))
      .filter((n) => n && n.type === "main");
    if (mains.length < 2) continue; // defensively skip degenerate circles
    mains.sort(
      (a, b) =>
        (a.birth_year ?? Infinity) - (b.birth_year ?? Infinity) ||
        a.name.localeCompare(b.name)
    );
    clusters.push({
      key: circle.key || mains.map((n) => n.id).join("+"),
      mains,
      secondaries: [],
      nodeIds: new Set(mains.map((n) => n.id)),
      links: [],
    });
  }
  if (!clusters.length) return [];

  for (const node of network.nodes) {
    if (node.type !== "secondary") continue;
    let best = null;
    let bestCount = 0;
    for (const cluster of clusters) {
      let count = 0;
      for (const l of links) {
        const other =
          l.source === node.id
            ? l.target
            : l.target === node.id
              ? l.source
              : null;
        if (other && cluster.nodeIds.has(other)) count++;
      }
      if (count > bestCount) {
        bestCount = count;
        best = cluster;
      }
    }
    if (best) {
      best.secondaries.push(node);
      best.nodeIds.add(node.id);
    }
  }
  for (const cluster of clusters) {
    cluster.secondaries.sort((a, b) => a.name.localeCompare(b.name));
    cluster.links = sortInternalLinks(links, cluster.nodeIds);
  }
  return clusters;
}
