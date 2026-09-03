/**
 * Reader-facing names for the relationship tokens in an ego network.
 *
 * `relationship_type` is a machine token — `family/father`, `professional/mentor`
 * — and the localized datasets correctly leave it untranslated: the German
 * ego_network.json carries the same `family/father` as the English one. It is
 * the interface's job to name it, and it used to do that by replacing
 * underscores, which meant a German reader got FATHER on the chip and
 * `Academic (6)` on the heading no matter what language they had chosen.
 *
 * Both segments of the token are looked up here instead. The vocabulary is
 * closed — `scripts/utils/relationship_vocabulary.py` names the categories
 * and roles, the generator is held to them, and both locales carry an entry
 * for each (tests/test_relationship_vocabulary.py). A token from outside the
 * vocabulary therefore signals a gap, and it falls back to a visibly generic
 * label ("Connection", "Verbindung") rather than an English title-casing of
 * the raw token that would fake precision in every language. In dev the gap
 * is also logged, so it surfaces instead of shipping.
 */

// One warning per unknown token, so a network with twelve chips of the same
// unmapped role does not flood the console.
const warnedTokens = new Set();

function warnUnknownToken(kind, token) {
  // import.meta.env exists under Vite; the Node test runner has neither it
  // nor a reason to warn.
  if (!import.meta.env?.DEV) return;
  const key = `${kind}:${token}`;
  if (warnedTokens.has(key)) return;
  warnedTokens.add(key);
  console.warn(
    `relationshipLabels: no locale entry for ${kind} "${token}" — ` +
      "extend the vocabulary and both locale files"
  );
}

/**
 * Fold a token to its locale key segment: lower case, one separator.
 * This also collapses the spellings the datasets disagree on —
 * `mother-in-law`, `mother_in_law` and `mother in law` are one key.
 * @param {string} token
 * @returns {string}
 */
function tokenKey(token) {
  return String(token || "")
    .trim()
    .toLowerCase()
    .replace(/[\s\-/]+/g, "_");
}

// Naive English pluralization for a single word — enough for the relationship
// subcategories that reach it as a fallback (colleague → colleagues, rival →
// rivals, adversary → adversaries).
function pluralizeWord(word) {
  if (/[^aeiou]y$/i.test(word)) {
    return `${word.slice(0, -1)}ies`;
  }
  if (/(s|x|z|ch|sh)$/i.test(word)) {
    return `${word}es`;
  }
  return `${word}s`;
}

/**
 * The raw token, spaced and capitalized. The relationship labels no longer
 * fall back to this — it fakes English precision in every language — but the
 * metadata values below still do, and tests exercise it directly.
 * @param {string} token
 * @param {number} count - 1 for the singular form
 * @returns {string}
 */
export function humanizeRelationshipToken(token, count = 1) {
  if (!token) return "";
  const words = String(token)
    .split(/[\s_-]+/)
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1));
  if (count !== 1 && words.length > 0) {
    words[words.length - 1] = pluralizeWord(words[words.length - 1]);
  }
  return words.join(" ");
}

// The translation store answers with the key itself when there is no entry,
// which is how a missing mapping is detected.
function lookup(t, key) {
  if (typeof t !== "function") return null;
  const value = t(key);
  return value && value !== key ? value : null;
}

/**
 * Name a relationship role — the segment after the slash, or a bare token.
 * @param {Function} t - the translate function from the language store
 * @param {string} subcategory - e.g. "father", "field_peer"
 * @param {number} count - 1 for the singular form
 * @returns {string}
 */
export function relationshipRoleLabel(t, subcategory, count = 1) {
  if (!subcategory) return "";
  // A caller with only the full token in hand ("family/father") means the role
  // it names; the category is the caller's other lookup.
  const role = String(subcategory).includes("/")
    ? String(subcategory).split("/").pop()
    : subcategory;
  if (!role) return "";
  const key = tokenKey(role);
  const suffix = count === 1 ? "one" : "other";
  const named = lookup(t, `network.role.${key}_${suffix}`);
  if (named) return named;
  warnUnknownToken("role", role);
  return (
    lookup(t, `network.role.unknown_${suffix}`) ??
    humanizeRelationshipToken(role, count)
  );
}

/**
 * Name a relationship category — the segment before the slash. A token with no
 * slash is a category and a role at once ("colleague"), so it falls through to
 * the role vocabulary before giving up.
 * @param {Function} t - the translate function from the language store
 * @param {string} category - e.g. "family", "professional", "colleague"
 * @param {number} count - how many people the heading covers
 * @returns {string}
 */
export function relationshipCategoryLabel(t, category, count = 2) {
  if (!category) return "";
  const key = tokenKey(category);
  const named =
    lookup(t, `network.category.${key}`) ??
    lookup(t, `network.role.${key}_${count === 1 ? "one" : "other"}`);
  if (named) return named;
  warnUnknownToken("category", category);
  return (
    lookup(t, "network.category.other") ??
    humanizeRelationshipToken(category, count)
  );
}

/**
 * Name a whole `relationship_type` as one string: "Professional · Mentor".
 * @param {Function} t - the translate function from the language store
 * @param {string} relationshipType
 * @returns {string}
 */
export function relationshipTypeLabel(t, relationshipType) {
  if (!relationshipType) return "";
  const [category, subcategory] = String(relationshipType).split("/");
  const parts = [relationshipCategoryLabel(t, category, 1)];
  if (subcategory) parts.push(relationshipRoleLabel(t, subcategory, 1));
  return parts.filter(Boolean).join(" · ");
}

/**
 * Name a relationship-metadata value — tie strength or interaction
 * frequency. Like `relationship_type`, these are machine tokens the
 * localized datasets deliberately keep in English (`strong`, `daily`), so
 * the interface resolves them through the locale. The vocabulary is closed
 * and small, but an unmapped token still falls back to its humanized form
 * rather than breaking.
 * @param {Function} t - the translate function from the language store
 * @param {"strength"|"frequency"} family
 * @param {string} token - e.g. "strong", "occasional"
 * @returns {string}
 */
export function relationshipMetaValueLabel(t, family, token) {
  if (!token) return "";
  return (
    lookup(t, `person.${family}_value.${tokenKey(token)}`) ??
    humanizeRelationshipToken(token, 1)
  );
}
