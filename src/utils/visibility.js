/**
 * Entries marked hidden: people and collections the registries keep but the
 * deployed site does not show.
 *
 * A registry entry — in `persons.json` or `meta_stories.json` — carries
 * `"hidden": true` when it should stay out of the published site, and nothing
 * at all otherwise. The English registry is the reference: localized
 * registries are derived from it and copy the flag, but the flag is read from
 * the English entries so a stale derivation cannot show what English hides.
 *
 * The development server shows hidden entries by default, marked as such, and
 * offers a switch to preview what the deployment shows; a production build
 * never includes them. That policy lives in `src/stores/visibility.js`; the
 * functions here only apply a decision they are handed.
 */

/**
 * Whether a registry entry is marked hidden.
 *
 * Only the boolean `true` counts: a registry written by hand could carry the
 * string "true" or a number, and a person who is hidden by a typo is a person
 * nobody can find.
 *
 * @param {Object|null|undefined} entry - A registry entry
 * @returns {boolean} True when the entry carries `hidden: true`
 */
export function isHidden(entry) {
  return entry?.hidden === true;
}

/**
 * The entries a reader may see.
 *
 * @template {{ hidden?: boolean }} T
 * @param {Array<T>} entries - Registry entries
 * @param {boolean} includeHidden - Whether hidden entries stay in the list
 * @returns {Array<T>} The entries, without the hidden ones unless asked for
 */
export function filterVisible(entries, includeHidden = false) {
  const list = Array.isArray(entries) ? entries : [];
  return includeHidden ? list : list.filter((entry) => !isHidden(entry));
}

/**
 * Carry the hidden flags of a reference list over to another list of the
 * same entries, matched by `id`.
 *
 * The localized registries are laid over the English one entry by entry, so
 * a German entry replaces the English one whole — including whatever the
 * English entry said about being hidden. This restores the English answer.
 *
 * @template {{ id: string, hidden?: boolean }} T
 * @param {Array<T>} entries - The entries to annotate
 * @param {Array<{ id: string, hidden?: boolean }>} reference - The English
 *   entries whose flags decide
 * @returns {Array<T>} The entries, each hidden exactly when its reference is
 */
export function withHiddenFrom(entries, reference) {
  const list = Array.isArray(entries) ? entries : [];
  const hiddenIds = new Set(
    (Array.isArray(reference) ? reference : [])
      .filter((entry) => isHidden(entry))
      .map((entry) => entry.id)
  );
  return list.map((entry) => {
    const hidden = hiddenIds.has(entry?.id);
    if (hidden === isHidden(entry)) return entry;
    if (hidden) return { ...entry, hidden: true };
    const { hidden: _dropped, ...visible } = entry;
    return /** @type {T} */ (visible);
  });
}
