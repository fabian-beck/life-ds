/**
 * Role boxes inside one relationship circle of the network view.
 *
 * A circle ("Academic", "Professional") lists its people as chips. When a
 * role repeats inside the circle — three students, two collaborators — the
 * chips sharing it are gathered into a labeled box and drop their own role
 * label, and whoever is left over lands in a trailing "Other" box. A box is
 * a subdivision, so it exists only where there is something to subdivide:
 * a circle that resolves to a single group, whether because no role repeats
 * or because every member shares one role, keeps its chips unboxed, each
 * carrying its role.
 */

const STRENGTH_ORDER = { strong: 0, moderate: 1, weak: 2 };

/**
 * The role half of a `category/role` token, or null for a bare category.
 * @param {string} relationshipType
 * @returns {string|null}
 */
export function getSubcategory(relationshipType) {
  if (!relationshipType || !relationshipType.includes("/")) {
    return null;
  }
  return relationshipType.split("/")[1];
}

/**
 * Sort connections strongest first, in place. A missing or unknown strength
 * sorts last.
 * @param {Array} connections
 * @returns {Array} the same array
 */
export function sortByStrength(connections) {
  return connections.sort(
    (a, b) =>
      (STRENGTH_ORDER[a.strength] ?? 3) - (STRENGTH_ORDER[b.strength] ?? 3)
  );
}

/**
 * Accumulated strength score of a group: lower means stronger overall.
 * @param {Array} connections
 * @returns {number}
 */
export function calculateAccumulatedStrength(connections) {
  return connections.reduce(
    (sum, conn) => sum + (STRENGTH_ORDER[conn.strength] ?? 3),
    0
  );
}

/**
 * Group a circle's connections into role boxes.
 *
 * Returns one entry per box, strongest box first and the leftovers last.
 * `subcategory` is the role a box is named after (null for an unlabeled
 * group), `label` its reader-facing name, and `isOther` marks the box of
 * leftovers that share no role. A result with a single entry is not boxed:
 * it carries no label, and the template renders its people plainly.
 *
 * @param {Array} connections - the circle's connections
 * @param {(subcategory: string, count: number) => string} labelRole - names a
 *   role for the reader, singular for a count of one
 * @returns {Array<{subcategory: string|null, label: string|null, isOther?: boolean, people: Array}>}
 */
export function groupBySubcategory(connections, labelRole) {
  const subcategoryCounts = new Map();
  for (const conn of connections) {
    const subcategory = getSubcategory(conn.relationship_type);
    if (subcategory) {
      subcategoryCounts.set(
        subcategory,
        (subcategoryCounts.get(subcategory) || 0) + 1
      );
    }
  }

  const repeatedSubcategories = new Set();
  subcategoryCounts.forEach((count, subcategory) => {
    if (count >= 2) {
      repeatedSubcategories.add(subcategory);
    }
  });

  const unboxed = () => [
    { subcategory: null, label: null, people: sortByStrength(connections) },
  ];

  if (repeatedSubcategories.size === 0) {
    return unboxed();
  }

  const groups = new Map();
  const ungrouped = [];
  for (const conn of connections) {
    const subcategory = getSubcategory(conn.relationship_type);
    if (subcategory && repeatedSubcategories.has(subcategory)) {
      if (!groups.has(subcategory)) {
        groups.set(subcategory, []);
      }
      groups.get(subcategory).push(conn);
    } else {
      ungrouped.push(conn);
    }
  }

  // One box holding the whole circle subdivides nothing.
  if (groups.size === 1 && ungrouped.length === 0) {
    return unboxed();
  }

  const groupsArray = [];
  groups.forEach((people, subcategory) => {
    groupsArray.push({
      subcategory,
      label: labelRole(subcategory, people.length),
      people: sortByStrength(people),
      accumulatedStrength: calculateAccumulatedStrength(people),
    });
  });

  // Strongest box first.
  groupsArray.sort((a, b) => a.accumulatedStrength - b.accumulatedStrength);

  if (ungrouped.length > 0) {
    // A lone leftover with a role of its own needs no generic "Other" box:
    // the box is named after that role and the chip drops its now-redundant
    // role label, as in every labeled box.
    const soleSubcategory =
      ungrouped.length === 1
        ? getSubcategory(ungrouped[0].relationship_type)
        : null;
    groupsArray.push({
      subcategory: soleSubcategory,
      label: soleSubcategory ? labelRole(soleSubcategory, 1) : null,
      isOther: !soleSubcategory,
      people: sortByStrength(ungrouped),
      accumulatedStrength: Infinity,
    });
  }

  return groupsArray;
}
