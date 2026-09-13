/**
 * Role names as comparison keys, with the masculine and feminine forms of one
 * German role read as that one role.
 *
 * German role names carry grammatical gender, so the same profession reaches
 * the interface as two words: Ada Lovelace is a `Mathematikerin` and Charles
 * Babbage a `Mathematiker`. Compared as written they share no role at all,
 * which leaves the related people at the end of a German story matching along
 * gender lines, and the role filter on the landing page offering the same
 * profession twice.
 *
 * A feminine form is therefore folded onto its masculine counterpart, but only
 * when that counterpart occurs in the data: a vocabulary built from the roles
 * actually recorded keeps a word that merely ends in "in" from being read as a
 * feminine role name. The fold is confined to German; the other locales carry
 * one word per role.
 */

/**
 * The trimmed, lowercased form a role is compared by.
 * @param {string} role - Role name as written in the data
 * @returns {string} Normalized role, or "" for anything that is not a name
 */
export function normalizeRole(role) {
  return typeof role === "string" ? role.trim().toLowerCase() : "";
}

const UMLAUT_VOWELS = { ä: "a", ö: "o", ü: "u" };

/**
 * The stem with its umlauts reverted, which is how a feminine form reaches its
 * masculine one in "Ärztin" -> "Arzt".
 * @param {string} stem - Lowercased stem
 * @returns {string} Stem without umlauts
 */
function withoutUmlauts(stem) {
  return stem.replace(/[äöü]/g, (vowel) => UMLAUT_VOWELS[vowel]);
}

// What a masculine role name adds to the stem a feminine one keeps:
// "Mathematikerin" -> "Mathematiker", "Pathologin" -> "Pathologe",
// "Beamtin" -> "Beamter".
const MASCULINE_ENDINGS = ["", "e", "er"];

// A stem this short is not a role name whose feminine form was built by
// suffixing "in".
const MINIMUM_STEM_LENGTH = 3;

/**
 * The masculine forms a German feminine role name could derive from, most
 * likely first. Empty for a role that is not a feminine form.
 * @param {string} normalized - Normalized role name
 * @returns {Array<string>} Candidate masculine forms
 */
function masculineCandidates(normalized) {
  if (!normalized.endsWith("in")) return [];
  const stem = normalized.slice(0, -2);
  if (stem.length < MINIMUM_STEM_LENGTH) return [];
  const stems = [stem];
  const reverted = withoutUmlauts(stem);
  if (reverted !== stem) stems.push(reverted);
  return stems.flatMap((base) =>
    MASCULINE_ENDINGS.map((ending) => `${base}${ending}`)
  );
}

/**
 * @typedef {Object} RoleVocabulary
 * @property {(role: string) => string} key - The key a role is grouped and
 *   compared by: the masculine form when the data pairs the role with one, and
 *   the normalized role itself otherwise
 * @property {(role: string) => string} label - The role as a reader sees it:
 *   the inclusive form ("Mathematiker:in") for a paired role, and the role as
 *   written otherwise
 */

/**
 * Build the role vocabulary of a dataset: every role that occurs in it, with
 * the German gender pairs among them merged.
 * @param {Iterable<string>} [roles] - Every role name the data records, in any
 *   order and with repetitions
 * @param {string} [language] - Current language code; only "de" merges
 * @returns {RoleVocabulary} Keys and labels for the roles of this dataset
 */
export function roleVocabulary(roles = [], language = "en") {
  // Normalized role -> the role as the data writes it, for labels.
  const written = new Map();
  for (const role of roles) {
    const normalized = normalizeRole(role);
    if (normalized && !written.has(normalized)) {
      written.set(normalized, role.trim());
    }
  }

  // Feminine role -> the masculine form it is folded onto.
  const folded = new Map();
  if (language === "de") {
    for (const normalized of written.keys()) {
      const masculine = masculineCandidates(normalized).find((candidate) =>
        written.has(candidate)
      );
      if (masculine) folded.set(normalized, masculine);
    }
  }

  // Key -> the feminine form of that role, which the inclusive label is built
  // from: dropping its "in" leaves the stem both forms share.
  const feminineByKey = new Map();
  for (const [feminine, masculine] of folded) {
    if (!feminineByKey.has(masculine)) {
      feminineByKey.set(masculine, written.get(feminine));
    }
  }

  const key = (role) => {
    const normalized = normalizeRole(role);
    return folded.get(normalized) ?? normalized;
  };

  return {
    key,
    label: (role) => {
      const feminine = feminineByKey.get(key(role));
      if (feminine) return `${feminine.slice(0, -2)}:in`;
      return (
        written.get(normalizeRole(role)) ??
        (typeof role === "string" ? role.trim() : "")
      );
    },
  };
}
