/**
 * The analysis page's side of the evaluation API.
 *
 * Reads go through the same deployment's function; when the site sets
 * `EVALUATION_ANALYSIS_KEY`, every read carries it in a header. The key is
 * remembered for the tab, never for the browser.
 */

import { assetUrl } from "../../utils/assetUrl.js";
import { sessionStore } from "../../utils/safeStorage.js";

const KEY_STORAGE = "evaluationAnalysisKey";

export class AnalysisKeyRequired extends Error {
  constructor() {
    super("An analysis key is required.");
    this.name = "AnalysisKeyRequired";
  }
}

export function storedKey() {
  return sessionStore.get(KEY_STORAGE) ?? "";
}

export function rememberKey(key) {
  if (key) sessionStore.set(KEY_STORAGE, key);
  else sessionStore.remove(KEY_STORAGE);
}

async function read(path) {
  const headers = {};
  const key = storedKey();
  if (key) headers["x-evaluation-key"] = key;
  const response = await fetch(assetUrl(path), { headers });
  if (response.status === 401) throw new AnalysisKeyRequired();
  if (!response.ok) {
    let detail = "";
    try {
      detail = (await response.json()).error ?? "";
    } catch {
      // A body that is not JSON says nothing more than the status.
    }
    throw new Error(`${response.status}${detail ? `: ${detail}` : ""}`);
  }
  return response.json();
}

/** @returns {Promise<Array<{id: string, sessions: number, batches: number}>>} */
export async function fetchParticipants() {
  const data = await read("/api/evaluation/participants");
  return data.participants ?? [];
}

/** @returns {Promise<Array<Object>>} the participant's batches */
export async function fetchLogs(participant) {
  const data = await read(
    `/api/evaluation/logs?participant=${encodeURIComponent(participant)}`
  );
  return data.batches ?? [];
}
