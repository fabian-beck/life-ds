/**
 * Remembers the vertical scroll position of a meta story so that opening a
 * person's story from it and returning lands the reader back where they left
 * off. The meta story timeline derives its horizontal position from
 * `window.scrollY`, so persisting that single value restores both the page
 * position and the timeline column the reader was looking at.
 *
 * The value is kept in `sessionStorage`, keyed by meta story id, and consumed
 * (removed) on restore so a fresh visit from the landing page always starts at
 * the top. Access goes through the shared safe-storage wrapper, so a browser
 * that refuses storage costs the reader their scroll position and nothing more.
 */

import { sessionStore } from "../utils/safeStorage.js";

const KEY_PREFIX = "metaStoryScroll:";

function keyFor(metaStoryId) {
  return `${KEY_PREFIX}${metaStoryId}`;
}

/**
 * Save the current window scroll position for a meta story. Call right before
 * navigating away (e.g. into a person's story).
 * @param {string} metaStoryId
 */
export function saveMetaStoryScroll(metaStoryId) {
  if (!metaStoryId || typeof window === "undefined") return;
  sessionStore.set(keyFor(metaStoryId), String(window.scrollY));
}

/**
 * Read and clear the saved scroll position for a meta story.
 * @param {string} metaStoryId
 * @returns {number|null} saved scroll offset, or null if none stored
 */
export function consumeMetaStoryScroll(metaStoryId) {
  if (!metaStoryId || typeof window === "undefined") return null;
  const raw = sessionStore.get(keyFor(metaStoryId));
  if (raw === null) return null;
  sessionStore.remove(keyFor(metaStoryId));
  const value = Number(raw);
  return Number.isFinite(value) ? value : null;
}
