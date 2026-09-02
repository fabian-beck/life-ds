import { writable } from "svelte/store";
import { localStore } from "../utils/safeStorage.js";

/**
 * Who is reading, on the evaluation deployment.
 *
 * A participant identifies themselves once, through the gate App.svelte shows
 * before anything else; the id is remembered in local storage so a reload or
 * a second visit on the same device continues under the same name. Changing
 * it is a deliberate act on the landing page, which starts a new session.
 */

const STORAGE_KEY = "evaluationParticipant";

/** The characters an id may carry — the server enforces the same rule. */
export const PARTICIPANT_PATTERN = /^[A-Za-z0-9_-]{1,32}$/;

/**
 * @param {string} value
 * @returns {string|null} the id as stored, or null when it is not valid
 */
export function normalizeParticipantId(value) {
  const trimmed = String(value ?? "").trim();
  return PARTICIPANT_PATTERN.test(trimmed) ? trimmed : null;
}

export const participant = writable(
  normalizeParticipantId(localStore.get(STORAGE_KEY))
);

participant.subscribe((id) => {
  if (id) localStore.set(STORAGE_KEY, id);
  else localStore.remove(STORAGE_KEY);
});

/**
 * @param {string} value
 * @returns {boolean} whether the id was accepted
 */
export function setParticipant(value) {
  const id = normalizeParticipantId(value);
  if (!id) return false;
  participant.set(id);
  return true;
}

export function clearParticipant() {
  participant.set(null);
}
