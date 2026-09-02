/**
 * The evaluation log endpoint on the evaluation deployment.
 *
 *   POST /api/evaluation/log            store one batch of interaction events
 *   GET  /api/evaluation/participants   every participant with a log
 *   GET  /api/evaluation/logs?participant=<id>   that participant's batches
 *
 * Storage is Netlify Blobs: a site-wide store that needs no provisioning and
 * survives every redeploy. The function is bundled for the normal deployment
 * too — the functions directory is on every branch — so it answers 404 unless
 * the build declared itself the evaluation deployment (see netlify.toml).
 * Reads additionally require `EVALUATION_ANALYSIS_KEY` when that variable is
 * set in the site's environment.
 */

import { getStore } from "@netlify/blobs";
import {
  createEvaluationApi,
  fromFetchRequest,
  toFetchResponse,
} from "../lib/evaluationApi.mjs";

const STORE_NAME = "evaluation-logs";

function blobStore() {
  const store = getStore(STORE_NAME);
  return {
    getJSON: (key) => store.get(key, { type: "json" }),
    setJSON: async (key, value) => {
      await store.setJSON(key, value);
    },
    list: async (prefix) =>
      (await store.list({ prefix })).blobs.map((b) => b.key),
    listDirectories: async (prefix) =>
      (await store.list({ prefix, directories: true })).directories,
  };
}

function isEnabled() {
  return (
    process.env.EVALUATION_MODE === "1" ||
    process.env.VITE_EVALUATION_MODE === "1"
  );
}

export default async (request, context) => {
  const api = createEvaluationApi({
    store: blobStore(),
    enabled: isEnabled(),
    analysisKey: process.env.EVALUATION_ANALYSIS_KEY ?? "",
  });
  const action = context.params?.action ?? "";
  const response = await api.handle(fromFetchRequest(request, action));
  return toFetchResponse(response);
};

export const config = {
  path: "/api/evaluation/:action",
};
