/**
 * Web storage that cannot take the application down with it.
 *
 * Reading `localStorage` is not a safe operation. A `typeof` guard only covers
 * the server-side case where the object is absent; in a browser where the
 * visitor has blocked site data the property exists and *accessing it throws*
 * (`SecurityError`), and writes throw once a quota is exhausted
 * (`QuotaExceededError`). Both stores below read at module scope, so an
 * unguarded access aborts the whole bootstrap and leaves a blank page on every
 * route.
 *
 * Losing a remembered language or contrast preference is a fine degradation.
 * Losing the application is not — so every access here answers with an absent
 * value instead of throwing.
 */

function safeStorage(open) {
  return {
    /**
     * @param {string} key
     * @returns {string|null} the stored value, or null if unreadable
     */
    get(key) {
      try {
        // Referencing the global is itself the step that can throw, so it
        // happens inside the guard rather than before it.
        return open().getItem(key);
      } catch {
        return null;
      }
    },

    /**
     * @param {string} key
     * @param {string} value
     * @returns {boolean} whether the value was stored
     */
    set(key, value) {
      try {
        open().setItem(key, value);
        return true;
      } catch {
        return false;
      }
    },

    /**
     * @param {string} key
     * @returns {boolean} whether the key was removed
     */
    remove(key) {
      try {
        open().removeItem(key);
        return true;
      } catch {
        return false;
      }
    },
  };
}

export const localStore = safeStorage(() => localStorage);
export const sessionStore = safeStorage(() => sessionStorage);
