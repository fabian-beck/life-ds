/**
 * Role names as comparison keys, with the gendered German forms of one role
 * reduced to the same key.
 *
 * German role names carry grammatical gender, so one profession reaches the
 * interface as two words: Ada Lovelace is a `Mathematikerin` and Charles
 * Babbage a `Mathematiker`. Compared as written they share no role at all,
 * which leaves the related people at the end of a German story matching along
 * gender lines, and the role filter on the landing page offering the same
 * profession twice.
 *
 * A key is therefore the stem the two forms are left with once the endings
 * they disagree on come off. That stem is not a word: `Mathematiker` and
 * `Mathematikerin` both key as `mathematik`, `Kaiser` and `Kaiserin` as
 * `kais`. A key only has to be the same for both forms and different for
 * different roles, so the rule strips an ending wherever it sits rather than
 * deciding first whether it carries gender — cutting `Bauer` back to `bau`
 * costs nothing as long as `Bäuerin` arrives there too.
 *
 * The rule reads no data, so a role no registry has carried yet keys like one
 * that has. What it cannot do is relate two different words for one
 * profession: `Unternehmerin` and `Geschäftsmann` stay apart, and so do the
 * multi-word roles whose adjective inflects with the noun ("politische
 * Beraterin" against "politischer Berater"). A translation that names the same
 * profession with another noun is a data question rather than a matching one.
 */

/**
 * The trimmed, lowercased form a role is compared by, with inner whitespace
 * collapsed so one spelling of a multi-word role is one key.
 * @param {string} role - Role name as written in the data
 * @returns {string} Normalized role, or "" for anything that is not a name
 */
function normalizeRole(role) {
  return typeof role === "string"
    ? role.trim().toLowerCase().split(/\s+/).join(" ")
    : "";
}

// The endings the two German forms of a role disagree on, in the order they
// come off: a feminine name suffixes "in" to the stem ("Mathematikerin"),
// rarely with "ess" before it ("Prinzessin"); the weak and adjectival nouns
// carry "e" or "er" ("Pathologe", "Beamter"); and a compound in "-mann" pairs
// with one in "-frau".
const GENDERED_ENDINGS = [/in$/, /ess$/, /er?$/, /(?:mann|frau)$/];

// A stem shorter than this is no longer distinctive, so the ending stays.
const MINIMUM_STEM_LENGTH = 3;

const UMLAUT_VOWELS = { ä: "a", ö: "o", ü: "u" };

/**
 * The key a role is compared by: its stem in German, where the gendered forms
 * of one role reach the same stem, and the normalized role itself elsewhere.
 * @param {string} role - Role name as written in the data
 * @param {string} [language] - Current language code; only "de" has gendered
 *   role names to reduce
 * @returns {string} Comparison key, or "" for anything that is not a name
 */
export function roleKey(role, language = "en") {
  const normalized = normalizeRole(role);
  if (language !== "de" || !normalized) return normalized;

  const stem = GENDERED_ENDINGS.reduce((current, ending) => {
    const stripped = current.replace(ending, "");
    return stripped.length >= MINIMUM_STEM_LENGTH ? stripped : current;
  }, normalized);
  // The umlaut a feminine name takes is the last difference left, as in
  // "Ärztin" against "Arzt".
  return stem.replace(/[äöü]/g, (vowel) => UMLAUT_VOWELS[vowel]);
}

/**
 * The label the roles of one key share, for a filter that offers each key
 * once. Where the data carries both the feminine form of a role and another
 * form of it, the two are named inclusively ("Mathematiker:in"); a role that
 * occurs in one form only is named as the data writes it.
 * @param {Array<string>} forms - The role names of one key, as written
 * @returns {string} Reader-facing label
 */
export function roleLabel(forms) {
  const written = (forms || [])
    .map((form) => (typeof form === "string" ? form.trim() : ""))
    .filter(Boolean);
  const feminine = written.find((form) => /in$/i.test(form));
  const otherForm = written.find((form) => !/in$/i.test(form));
  if (feminine && otherForm) return `${feminine.slice(0, -2)}:in`;
  return written[0] ?? "";
}
