/**
 * Loading the data files that come in more than one language.
 *
 * Every localized document in `data/` follows one rule: look for the reader's
 * language, and fall back to English when that translation does not exist yet,
 * so a half-translated corpus still renders a whole app. App.svelte wrote that
 * rule three times — once for life events, once for ego networks, once for
 * meta stories — and the registries wrote a second one twice: the English list
 * is the reference, and localized entries are laid over it per id, so a person
 * without a translation still appears and the list is the same length in every
 * language.
 *
 * The generation counters that guard against a slow load resolving after a
 * faster one are deliberately *not* here: they guard component state, and only
 * the component knows what it is showing by the time an answer arrives.
 */

/**
 * Build a loader over an `import.meta.glob` map that falls back to English.
 *
 * @param {Object} options - How this kind of document is addressed
 * @param {Object<string, Function>} options.modules - The glob map
 * @param {(id: string, language: string) => string} options.pathFor - The path
 *   a document has in a given language
 * @param {string} options.label - What to call it in a log line
 * @param {boolean} [options.warnWhenMissing] - Whether a document that exists
 *   in no language at all is worth a warning. True for meta stories, whose ids
 *   come from a registry that promised they exist; false for a person's files,
 *   where an absent network is an ordinary state.
 * @returns {(id: string, language?: string) => Promise<Object|null>} Loader
 */
export function makeLocalizedLoader({
  modules,
  pathFor,
  label,
  warnWhenMissing = false,
}) {
  return async function load(id, language = "en") {
    let loader = modules[pathFor(id, language)];

    if (!loader && language !== "en") {
      console.warn(
        `${label} translation not found for ${id} in ${language}, falling back to English`
      );
      loader = modules[pathFor(id, "en")];
    }

    if (!loader) {
      if (warnWhenMissing) console.warn(`${label} not found: ${id}`);
      return null;
    }

    try {
      return await loader();
    } catch (error) {
      console.error(`Failed to load ${label} for ${id}:`, error);
      return null;
    }
  };
}

/**
 * Lay localized entries over an English list, matched by `id`.
 *
 * The English list decides which entries exist and in what order; a localized
 * entry only replaces one. That is what keeps a person who has no translation
 * from disappearing when the reader switches language.
 *
 * @param {Array<Object>} base - The English entries
 * @param {Array<Object>} localized - Entries in the reader's language
 * @returns {Array<Object>} The English list, with translations swapped in
 */
export function mergeLocalized(base, localized) {
  const entries = Array.isArray(base) ? base : [];
  if (!Array.isArray(localized) || localized.length === 0) return entries;
  const byId = new Map(localized.map((entry) => [entry.id, entry]));
  return entries.map((entry) => byId.get(entry.id) ?? entry);
}
