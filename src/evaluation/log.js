/**
 * The one call a component makes to record something a reader did.
 *
 * `logEvent` is a no-op until the evaluation runtime installs a sink, and the
 * runtime is only ever loaded on the evaluation deployment (see App.svelte),
 * so a component may call it freely: on the ordinary site the call costs a
 * null check, and the module it imports is this file and nothing else.
 */

/** Whether this build is the user-evaluation deployment. */
export const evaluationMode = import.meta.env.VITE_EVALUATION_MODE === "1";

/** @type {((type: string, data?: Record<string, any>) => void) | null} */
let sink = null;

/**
 * Record an interaction.
 * @param {string} type - A dotted event name, e.g. "story.navigate"
 * @param {Record<string, any>} [data] - Small, JSON-serializable details
 */
export function logEvent(type, data = {}) {
  if (sink) sink(type, data);
}

/**
 * Installed by the evaluation runtime; `null` uninstalls.
 * @param {((type: string, data?: Record<string, any>) => void) | null} next
 */
export function setEventSink(next) {
  sink = next;
}
