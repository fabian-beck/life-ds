/**
 * Reader-facing names for the machine tokens in an event classification.
 *
 * `event_class` carries two kinds of field. Its prose — a marriage's
 * characterization, an invention's description, a publication's significance —
 * is translated with the rest of the document and arrives ready to print. Its
 * tokens are not: `type`, `subtype`, and `publication_type` come from fixed
 * vocabularies the generator writes once, and the localized datasets keep them
 * as they are, exactly as they keep `relationship_type`. Naming them is the
 * interface's job, and printing them raw is how a German reader ended up with
 * "Marriage · 6 children" on a slide that was otherwise entirely German.
 *
 * The vocabularies are small and closed, so a missing entry means the generator
 * grew a new value. That falls back to the humanized token — the old behavior —
 * rather than showing a locale key.
 */

// The translation store answers with the key itself when there is no entry,
// which is how a missing mapping is detected.
function lookup(t, key) {
  if (typeof t !== "function") return null;
  const value = t(key);
  return value && value !== key ? value : null;
}

/**
 * The fallback name: the raw token, spaced and capitalized.
 * @param {string} token
 * @returns {string}
 */
export function humanizeEventClassToken(token) {
  if (!token) return "";
  return String(token)
    .split(/[\s_-]+/)
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

/**
 * Name what kind of event a classification marks.
 *
 * A marriage_partnership is named by its subtype, because "Marriage" and
 * "Partnership" are what the reader is told the union was.
 * @param {Function} t - the translate function from the language store
 * @param {{type?: string, subtype?: string}} [eventClass]
 * @returns {string}
 */
export function eventClassLabel(t, eventClass) {
  const type = eventClass?.type;
  if (!type) return "";
  if (type === "marriage_partnership") {
    const subtype =
      eventClass.subtype === "partnership" ? "partnership" : "marriage";
    return (
      lookup(t, `story.event_class.${subtype}`) ??
      humanizeEventClassToken(subtype)
    );
  }
  return (
    lookup(t, `story.event_class.${type}`) ?? humanizeEventClassToken(type)
  );
}

/**
 * Name a publication's kind for its badge.
 * @param {Function} t - the translate function from the language store
 * @param {string} publicationType - e.g. "book", "thesis"
 * @returns {string}
 */
export function publicationTypeLabel(t, publicationType) {
  if (!publicationType) {
    return lookup(t, "story.event_class.publication") ?? "Publication";
  }
  return (
    lookup(t, `story.publication_type.${publicationType}`) ??
    humanizeEventClassToken(publicationType)
  );
}
