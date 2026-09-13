/**
 * Relating events to the people around them: name normalization and
 * similarity, the relevant connections of an event, and family roles.
 */
import { displayName } from "../helpers.js";
import { findPersonMentions } from "../personNames.js";
import { roleVocabulary } from "../roles.js";

/**
 * Get the subcategory from a relationship type string.
 * @param {string} relationshipType - Relationship type like "family/spouse"
 * @returns {string|null} Subcategory or null
 */
export function getSubcategory(relationshipType) {
  return relationshipType?.includes("/")
    ? relationshipType.split("/")[1]
    : null;
}
/**
 * Escape special regex characters in a string.
 * Also normalizes hyphens to match various Unicode hyphen characters.
 * @param {string} str - String to escape
 * @returns {string} Escaped string with hyphen normalization
 */
export function escapeRegex(str) {
  // First escape special regex characters
  let escaped = str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  // Replace all types of hyphens with a character class that matches any hyphen variant
  // This handles: regular hyphen (-), non-breaking hyphen (‑), en-dash (–), em-dash (—), minus sign (−)
  escaped = escaped.replace(
    /[-\u2010\u2011\u2012\u2013\u2014\u2212]/g,
    "[-\\u2010\\u2011\\u2012\\u2013\\u2014\\u2212]"
  );
  return escaped;
}
/**
 * Minimum similarity score for a name match to be accepted.
 */
const MATCH_THRESHOLD = 0.6;
/**
 * Normalize a person name for matching.
 * Handles parentheticals, initials, and special characters.
 * @param {string} name - Full person name
 * @returns {Object|null} Normalized name components
 */
export function normalizePersonName(name) {
  if (!name || typeof name !== "string") return null;

  let normalized = name.trim();

  // Normalize all hyphen variants to standard ASCII hyphen
  // This handles: non-breaking hyphen (‑), en-dash (–), em-dash (—), hyphen (‐), minus sign (−)
  normalized = normalized.replace(
    /[\u2010\u2011\u2012\u2013\u2014\u2212]/g,
    "-"
  );

  // Extract maiden name if present: "Ingrid Otto (née Smolla)" → maidenName = "Smolla"
  // Also handles: "née", "born", "geborene", "geb."
  let maidenName = null;
  const maidenMatch = normalized.match(
    /\(\s*(?:née|nee|born|geborene|geb\.?)\s+([^)]+)\)/i
  );
  if (maidenMatch) {
    maidenName = maidenMatch[1].trim();
  }

  // Remove parenthetical clarifications: "Ethel Sara Turing (née Stoney)" → "Ethel Sara Turing"
  normalized = normalized.replace(/\s*\([^)]*\)/g, "");

  // Remove bracketed clarifications: "D. G. [David Gawen] Champernowne" → "D. G. Champernowne"
  normalized = normalized.replace(/\s*\[[^\]]*\]/g, "");

  // Remove comma-separated titles: "Henry II, Holy Roman Emperor" → "Henry II"
  // This handles titles that come after a comma
  normalized = normalized.replace(
    /,\s*(Holy Roman Emperor|Holy Roman Empress|King|Queen|Emperor|Empress|Duke|Duchess|Count|Countess|Prince|Princess|Bishop|Archbishop|Pope|Saint|Dr\.|Prof\.).*$/i,
    ""
  );

  // Split off a Jr./Sr. suffix but NOT Roman numerals (II, III, IV, V, etc.),
  // which are part of regnal names. The suffix is kept aside rather than
  // dropped: it is what tells a father from the son who carries his name.
  let suffix = null;
  normalized = normalized.replace(/\s+(Jr|Sr)\.?$/i, (_, found) => {
    suffix = found.toLowerCase();
    return "";
  });

  // Remove titles with geographic qualifiers: "Count of Luxembourg", "Duke of Bavaria", "Bishop of Metz"
  // Pattern: (Title) of (Place) - these are descriptive, not part of the actual name
  normalized = normalized.replace(
    /,?\s*(Count|Duke|Duchess|Bishop|Archbishop|King|Queen|Prince|Princess|Emperor|Empress|Lord|Lady|Earl|Baron|Baroness|Margrave|Landgrave|Elector)\s+of\s+[\w\s-]+$/i,
    ""
  );

  // Also handle "of Place" at the end for names like "Cunigunde of Luxembourg" → keep as is but don't use place as last name
  // We'll handle this by detecting the "of Place" pattern
  const ofPlaceMatch = normalized.match(/^(.+?)\s+of\s+([\w\s-]+)$/i);
  let isGeographicName = false;
  if (ofPlaceMatch) {
    // This is a name like "Cunigunde of Luxembourg" or "Henry of Bavaria"
    // The part after "of" is a place, not a surname
    isGeographicName = true;
  }

  // Split into tokens
  const tokens = normalized.split(/\s+/).filter((t) => t.length > 0);
  if (tokens.length === 0) return null;

  // Handle "von", "de", "van" etc. as part of last name (but NOT "of" which is geographic)
  const particleIndex = tokens.findIndex((t) =>
    ["von", "van", "de", "del", "della", "di"].includes(t.toLowerCase())
  );

  let lastName, firstNames;

  if (isGeographicName) {
    // For names like "Cunigunde of Luxembourg", use the first part as the name
    // Don't use the geographic part as the last name
    const nameBeforeOf = ofPlaceMatch[1];
    const nameTokens = nameBeforeOf.split(/\s+/).filter((t) => t.length > 0);
    if (nameTokens.length === 0) return null;
    lastName = nameTokens[nameTokens.length - 1];
    firstNames = nameTokens.slice(0, -1);
  } else if (particleIndex > -1 && particleIndex < tokens.length - 1) {
    // Include particle in last name
    lastName = tokens.slice(particleIndex).join(" ");
    firstNames = tokens.slice(0, particleIndex);
  } else {
    lastName = tokens[tokens.length - 1];
    firstNames = tokens.slice(0, -1);
  }

  const firstName = firstNames.length > 0 ? firstNames[0] : "";

  return {
    fullName: normalized,
    firstName: firstName,
    lastName: lastName,
    maidenName: maidenName,
    suffix: suffix,
    tokens: tokens.map((t) => t.toLowerCase()),
    originalName: name,
    isGeographicName: isGeographicName,
  };
}
/**
 * Calculate a similarity score between two normalized names.
 * Returns a score from 0 (no match) to 1 (exact match).
 * @param {Object} name1 - First normalized name
 * @param {Object} name2 - Second normalized name
 * @returns {number} Similarity score 0-1
 */
function calculateNameSimilarity(name1, name2) {
  if (!name1 || !name2) return 0;

  // Exact full name match = perfect score. A suffix on one side only is not
  // exact: "Christian Bohr" is the father, "Christian Bohr Jr." the son, and
  // the pair still scores high enough below to match when there is no other.
  if (
    name1.fullName.toLowerCase() === name2.fullName.toLowerCase() &&
    (name1.suffix ?? null) === (name2.suffix ?? null)
  ) {
    return 1.0;
  }

  let score = 0;

  // Check for Roman numeral pattern
  const romanNumeralPattern = /^(I{1,3}|IV|V|VI{0,3}|IX|X|XI{0,3}|XIV|XV)$/i;

  // Check first name match
  const firstName1 = name1.firstName?.toLowerCase() || "";
  const firstName2 = name2.firstName?.toLowerCase() || "";
  const firstNamesMatch = firstName1 && firstName2 && firstName1 === firstName2;

  // Check last name match - but ignore if last name is a Roman numeral
  const lastName1 = name1.lastName?.toLowerCase() || "";
  const lastName2 = name2.lastName?.toLowerCase() || "";
  const lastName1IsNumeral = romanNumeralPattern.test(lastName1);
  const lastName2IsNumeral = romanNumeralPattern.test(lastName2);

  // Only count last name match if neither is a Roman numeral
  const lastNamesMatch =
    lastName1 &&
    lastName2 &&
    !lastName1IsNumeral &&
    !lastName2IsNumeral &&
    lastName1 === lastName2;

  // Check if last names are contained in each other (handles partial matches)
  // Also skip if either is a Roman numeral
  const lastNameContained =
    lastName1 &&
    lastName2 &&
    !lastName1IsNumeral &&
    !lastName2IsNumeral &&
    (lastName1.includes(lastName2) || lastName2.includes(lastName1));

  // Check for Roman numeral in either name (important for rulers)
  const hasRomanNumeral1 = name1.tokens?.some((t) =>
    romanNumeralPattern.test(t)
  );
  const hasRomanNumeral2 = name2.tokens?.some((t) =>
    romanNumeralPattern.test(t)
  );

  // If both have Roman numerals, they MUST match AND first names must also match
  if (hasRomanNumeral1 && hasRomanNumeral2) {
    const numeral1 = name1.tokens
      .find((t) => romanNumeralPattern.test(t))
      ?.toUpperCase();
    const numeral2 = name2.tokens
      .find((t) => romanNumeralPattern.test(t))
      ?.toUpperCase();
    if (numeral1 !== numeral2) {
      return 0; // Different rulers (e.g., Henry II vs Henry V), no match
    }
    // Same numeral but different first names = different person (e.g., Henry II vs Dietrich II)
    if (!firstNamesMatch) {
      return 0;
    }
    // Same numeral AND same first name = likely same person
    score += 0.5;
  }

  // First name match is important
  if (firstNamesMatch) {
    score += 0.4;
  }

  // Last name match (only for real surnames, not Roman numerals)
  if (lastNamesMatch) {
    score += 0.4;
  } else if (
    lastNameContained &&
    lastName1.length > 3 &&
    lastName2.length > 3
  ) {
    // Partial last name match (for married names, etc.)
    score += 0.2;
  }

  // Check if one full name contains the other (handles titles being stripped)
  const full1 = name1.fullName.toLowerCase();
  const full2 = name2.fullName.toLowerCase();
  if (full1.includes(full2) || full2.includes(full1)) {
    score += 0.2;
  }

  // Check maiden name matching (for married women)
  // E.g., "Ingrid Smolla" should match "Ingrid Otto (née Smolla)"
  const maiden1 = name1.maidenName?.toLowerCase();
  const maiden2 = name2.maidenName?.toLowerCase();

  if (firstNamesMatch) {
    // If first names match, check if one's last name matches the other's maiden name
    if (maiden1 && lastName2 === maiden1) {
      score += 0.4; // "Ingrid Smolla" matches "Ingrid Otto (née Smolla)"
    } else if (maiden2 && lastName1 === maiden2) {
      score += 0.4; // Same, other direction
    }
  }

  // Cap at 0.95 for non-exact matches
  return Math.min(score, 0.95);
}
/**
 * Get people relevant to an event from the ego network.
 * Uses a scoring-based approach for matching involved_people to network connections.
 * @param {Object} event - Event object
 * @param {Object} egoNetwork - Ego network with connections array
 * @returns {Array} Relevant connections (max 5)
 */
export function getRelevantPeople(event, egoNetwork) {
  if (!egoNetwork?.connections || !Array.isArray(egoNetwork.connections)) {
    return [];
  }

  const connections = egoNetwork.connections;

  // PHASE 1: Use involved_people field if present
  if (
    event.involved_people &&
    Array.isArray(event.involved_people) &&
    event.involved_people.length > 0
  ) {
    // Each name resolves to one connection at most — its best match, never
    // every connection that resembles it. "Benjamin Babbage" scores 1.0
    // against the father and 0.8 against the son who carries his name; the
    // father is the chip, the son is not.
    const matched = [];
    for (const name of event.involved_people) {
      const connection = findPersonInNetwork(name, egoNetwork);
      if (connection && !matched.includes(connection)) {
        matched.push(connection);
      }
    }
    return matched.slice(0, 5);
  }

  // PHASE 2: Fall back to who is actually named in the event text. This is the
  // same matcher that highlights the names, so the people offered as chips and
  // the names emphasized in the description cannot disagree.
  const eventText = `${event?.title ?? ""} ${event?.description ?? ""}`;
  const mentioned = new Set(
    findPersonMentions(eventText, connections).map((match) => match.person)
  );

  const strengthOrder = { strong: 0, moderate: 1, weak: 2 };
  return connections
    .filter((connection) => mentioned.has(connection))
    .sort(
      (a, b) =>
        (strengthOrder[a.strength] ?? 3) - (strengthOrder[b.strength] ?? 3)
    )
    .slice(0, 5);
}
/**
 * Find a person in the ego network by name using fuzzy matching.
 * Uses multiple fallback strategies for robust matching.
 * @param {string} personName - Name to search for
 * @param {Object} egoNetwork - Ego network with connections array
 * @returns {Object|null} Matching connection object or null
 */
export function findPersonInNetwork(personName, egoNetwork) {
  if (!egoNetwork?.connections || !personName) return null;

  const connections = egoNetwork.connections;
  const searchNormalized = normalizePersonName(personName);
  if (!searchNormalized) return null;

  // Find best match by similarity score
  let bestMatch = null;
  let bestScore = 0;

  for (const conn of connections) {
    const connNormalized = normalizePersonName(conn.person_name);
    if (!connNormalized) continue;

    const score = calculateNameSimilarity(searchNormalized, connNormalized);
    if (score >= MATCH_THRESHOLD && score > bestScore) {
      bestScore = score;
      bestMatch = conn;
    }
  }

  return bestMatch;
}
/**
 * Get chapter people from involved_people list, matched against ego network.
 * Only returns people found in the network with fuzzy matching.
 * Filters to only show people with "strong" connections.
 * @param {Object} chapter - Chapter object with involved_people array
 * @param {Object} egoNetwork - Ego network with connections
 * @returns {Array} Array of matched connection objects with metadata
 */
export function getChapterPeople(chapter, egoNetwork) {
  if (!chapter?.involved_people || !Array.isArray(chapter.involved_people)) {
    return [];
  }

  // Only return people that can be matched to the ego network with strong connections
  const matchedPeople = chapter.involved_people
    .map((name, idx) => {
      const networkPerson = findPersonInNetwork(name, egoNetwork);
      if (networkPerson && networkPerson.strength === "strong") {
        return {
          ...networkPerson,
          _originalName: name,
          _index: idx,
        };
      }
      return null;
    })
    .filter(Boolean);

  // Deduplicate by person_name (in case multiple variations match same network person)
  const seen = new Map();
  return matchedPeople.filter((person) => {
    const key = person.person_name;
    if (seen.has(key)) {
      return false;
    }
    seen.set(key, true);
    return true;
  });
}

const PARTNER_ROLES_BY_SUBTYPE = {
  marriage: new Set(["spouse"]),
  partnership: new Set(["partner", "romantic-partner"]),
};
const ALL_PARTNER_ROLES = new Set(["spouse", "partner", "romantic-partner"]);

/**
 * Resolve the partner named by a marriage or partnership event. The event's
 * name remains the primary evidence. When titles or name changes defeat that
 * match, one unambiguous partner-role connection can supply the same person;
 * multiple candidates are never guessed between.
 * @param {Object} event - Event with a marriage_partnership classification
 * @param {Object} egoNetwork - Ego network with connections array
 * @returns {Object|null} A connection-shaped partner, or null
 */
export function getMarriagePartner(event, egoNetwork) {
  if (event?.event_class?.type !== "marriage_partnership") return null;

  const partnerName = event.event_class.partner;
  if (!partnerName) return null;

  const nameMatch = findPersonInNetwork(partnerName, egoNetwork);
  if (nameMatch) return nameMatch;

  const acceptedRoles =
    PARTNER_ROLES_BY_SUBTYPE[event.event_class.subtype] ?? ALL_PARTNER_ROLES;
  const roleMatches = (egoNetwork?.connections ?? []).filter((connection) => {
    const role = getSubcategory(connection.relationship_type)
      ?.toLowerCase()
      .replace(/[\s_]+/g, "-");
    return acceptedRoles.has(role);
  });
  if (roleMatches.length === 1) return roleMatches[0];

  return {
    person_name: partnerName,
    relationship_type:
      event.event_class.subtype === "marriage"
        ? "family/spouse"
        : "social/partner",
    relationship_description: "",
  };
}

/**
 * Check if an event is the subject's own birth.
 * @param {Object} event - Event object
 * @returns {boolean} True if event has birth class
 */
export function isBirthEvent(event) {
  return event?.event_class?.type === "birth";
}
/**
 * Canonical family role of a relationship token: lowercased, hyphenated, with
 * step/half/adoptive/foster prefixes and "-by-marriage" suffixes stripped
 * ("family/step_father" -> "father"). Returns null without a subcategory.
 * @param {string} relationshipType - e.g. "family/mother"
 * @returns {string|null} Canonical role
 */
export function normalizeFamilyRole(relationshipType) {
  const subcategory = getSubcategory(relationshipType);
  if (!subcategory) return null;
  return subcategory
    .toLowerCase()
    .replace(/[\s_]+/g, "-")
    .replace(/-by-marriage$/, "")
    .replace(/^(step|half|adoptive|adopted|biological|foster)-?/, "");
}
const PARENT_ROLES = ["father", "mother"];
// Some datasets record a parent the sources never name ("Unnamed mother of
// …"). That is a placeholder rather than a name, and a chip carrying it says
// less than no chip at all.
const PLACEHOLDER_NAME = /^\s*(unnamed|unknown|unidentified)\b/i;

/**
 * Resolve a parent by role when their name and network label use unrelated
 * forms, such as a personal name and a title. A role is identity evidence only
 * when exactly one connection has it; otherwise choosing would conflate
 * distinct people.
 * @param {string} role - Canonical parent role
 * @param {Object} egoNetwork - Ego network with connections array
 * @returns {Object|null} The uniquely identified parent, or null
 */
function findUniqueParentByRole(role, egoNetwork) {
  const matches = (egoNetwork?.connections ?? []).filter(
    (connection) =>
      (connection.relationship_type || "").split("/")[0] === "family" &&
      normalizeFamilyRole(connection.relationship_type) === role
  );
  return matches.length === 1 ? matches[0] : null;
}

/**
 * The parents to show on a birth slide, father first.
 *
 * The classification names them — Phase 1 reads the article — and the ego
 * network supplies the metadata behind each chip whenever it knows that
 * person, so a parent here behaves exactly like a parent in the network view.
 * When the classification names nobody, the parents are read from the network
 * itself, which is the same place the network view reads them from.
 * @param {Object} event - Event object
 * @param {Object} egoNetwork - Ego network with connections array
 * @returns {Array} Connection-shaped objects for the parents
 */
export function getBirthParents(event, egoNetwork) {
  if (!isBirthEvent(event)) return [];

  const named = [];
  for (const role of PARENT_ROLES) {
    const name = event.event_class[role];
    if (!name || PLACEHOLDER_NAME.test(name)) continue;
    named.push(
      findPersonInNetwork(name, egoNetwork) ??
        findUniqueParentByRole(role, egoNetwork) ?? {
          person_name: name,
          relationship_type: `family/${role}`,
          relationship_description: "",
        }
    );
  }
  if (named.length > 0) return named;

  const connections = egoNetwork?.connections ?? [];
  return PARENT_ROLES.map((role) =>
    connections.find(
      (connection) =>
        (connection.relationship_type || "").split("/")[0] === "family" &&
        normalizeFamilyRole(connection.relationship_type) === role &&
        !PLACEHOLDER_NAME.test(connection.person_name || "")
    )
  ).filter(Boolean);
}

/**
 * The people a story points at once it is over: others in the registry who
 * share a primary role with its subject, best first.
 *
 * Being in the subject's ego network counts for exactly as much as one shared
 * role, so a colleague the story actually mentions outranks a stranger with
 * the same job — but a stranger with two shared roles outranks the colleague
 * again. Someone with no role in common is not offered at all, which is why
 * the list can come back empty.
 *
 * Roles are compared by the keys of the registry's role vocabulary, so a
 * German `Mathematikerin` and a `Mathematiker` share the role they name.
 *
 * @param {Object} [inputs] - What the scoring reads
 * @param {Object} [inputs.person] - The story's subject; without one the
 *   list is empty
 * @param {Object} [inputs.registry] - `persons.json`, as `{ people: [...] }`;
 *   without it the list is empty
 * @param {Object} [inputs.egoNetwork] - The subject's network, if loaded
 * @param {string} [inputs.language] - Current language code, which decides
 *   whether gendered role names are merged
 * @param {number} [inputs.limit] - How many to return
 * @returns {Array<{person: Object, overlapCount: number, score: number,
 *   sharedRoles: Array<string>}>} Candidates, highest score first; each shared
 *   role is named as the subject's own data writes it
 */
export function relatedPersonsByRole({
  person,
  registry,
  egoNetwork = null,
  language = "en",
  limit = 5,
} = {}) {
  const people = registry?.people;
  if (!person?.primary_roles || !Array.isArray(people)) return [];

  const subjectName = displayName(person?.name);
  const subject = people.find(
    (entry) => displayName(entry.name) === subjectName
  );
  if (!subject) return [];

  const vocabulary = roleVocabulary(
    [
      ...(person.primary_roles || []),
      ...people.flatMap((entry) => entry.primaryRoles || []),
    ],
    language
  );
  // The subject's own words for its roles, by the key they are compared under.
  const subjectRoles = new Map(
    (person.primary_roles || []).map((role) => [vocabulary.key(role), role])
  );
  if (subjectRoles.size === 0) return [];

  return people
    .filter((entry) => entry.id !== subject.id)
    .map((entry) => {
      const roles = new Set(
        (entry.primaryRoles || []).map((role) => vocabulary.key(role))
      );
      const sharedRoles = [...subjectRoles]
        .filter(([key]) => roles.has(key))
        .map(([, role]) => role);
      const inNetwork = egoNetwork?.connections?.some((connection) =>
        connection.person_name
          ?.toLowerCase()
          .includes(displayName(entry.name).toLowerCase())
      )
        ? 1
        : 0;
      const overlapCount = sharedRoles.length;
      return {
        person: entry,
        overlapCount,
        score: overlapCount * 3 + inNetwork * 3,
        sharedRoles,
      };
    })
    .filter((candidate) => candidate.overlapCount > 0)
    .sort((a, b) => b.score - a.score || b.overlapCount - a.overlapCount)
    .slice(0, limit);
}
