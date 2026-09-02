/**
 * The evaluation log API, written once over an abstract key-value store.
 *
 * Two hosts run it: the Netlify Function in `netlify/functions/evaluation.mjs`
 * over Netlify Blobs, and the Vite dev-server plugin in `vite.config.js` over a
 * directory of JSON files. Both translate their transport into the plain
 * request shape `handle()` takes and its plain response back, so the rules —
 * what a batch may contain, where it is stored, who may read — live here and
 * are the same on a laptop and on the deployment.
 *
 * Storage layout. Every batch the client sends is one immutable object under
 * `logs/<participant>/<session>/<seq>`, where `seq` is the client's per-session
 * counter, zero-padded so that lexical order is send order. Nothing is ever
 * rewritten: two flushes that overlap in flight cannot lose each other, and a
 * report is the concatenation of a prefix listing.
 */

export const PARTICIPANT_PATTERN = /^[A-Za-z0-9_-]{1,32}$/;
export const SESSION_PATTERN = /^[A-Za-z0-9_-]{8,64}$/;
export const MAX_EVENTS_PER_BATCH = 500;
export const MAX_BODY_BYTES = 512 * 1024;
export const LOG_PREFIX = "logs/";

const SEQ_WIDTH = 6;

/**
 * @typedef {Object} EvaluationStore
 * @property {(key: string) => Promise<any>} getJSON - The parsed object, or null.
 * @property {(key: string, value: any) => Promise<void>} setJSON
 * @property {(prefix: string) => Promise<string[]>} list - Every key under the prefix.
 * @property {(prefix: string) => Promise<string[]>} listDirectories - The next path
 *   segment of every key under the prefix, as `prefix + segment + "/"`.
 */

/**
 * @typedef {Object} ApiRequest
 * @property {string} method
 * @property {string} action - The path segment after `/api/evaluation/`.
 * @property {URLSearchParams} searchParams
 * @property {(name: string) => string | null} header
 * @property {() => Promise<string>} text - The raw body.
 */

/**
 * @typedef {Object} ApiResponse
 * @property {number} status
 * @property {any} body - Serialized as JSON; `null` sends an empty body.
 */

export function batchKey(participant, session, seq) {
  return `${LOG_PREFIX}${participant}/${session}/${String(seq).padStart(SEQ_WIDTH, "0")}`;
}

function json(status, body) {
  return { status, body };
}

function error(status, message) {
  return json(status, { error: message });
}

/**
 * Validate one batch as the client sends it. Returns the reason it is refused,
 * or null when it may be stored.
 * @param {any} batch
 * @returns {string | null}
 */
export function batchProblem(batch) {
  if (!batch || typeof batch !== "object" || Array.isArray(batch)) {
    return "The body must be a JSON object.";
  }
  if (!PARTICIPANT_PATTERN.test(String(batch.participant ?? ""))) {
    return "participant must be 1-32 letters, digits, dashes, or underscores.";
  }
  if (!SESSION_PATTERN.test(String(batch.session ?? ""))) {
    return "session must be 8-64 letters, digits, dashes, or underscores.";
  }
  if (!Number.isInteger(batch.seq) || batch.seq < 0 || batch.seq > 999999) {
    return "seq must be a non-negative integer.";
  }
  if (!Array.isArray(batch.events) || batch.events.length === 0) {
    return "events must be a non-empty array.";
  }
  if (batch.events.length > MAX_EVENTS_PER_BATCH) {
    return `A batch carries at most ${MAX_EVENTS_PER_BATCH} events.`;
  }
  for (const event of batch.events) {
    if (!event || typeof event !== "object" || typeof event.type !== "string") {
      return "Every event is an object with a string type.";
    }
    if (!Number.isFinite(event.t)) {
      return "Every event carries a numeric timestamp t.";
    }
  }
  return null;
}

/**
 * Build the API over a store.
 *
 * @param {Object} options
 * @param {EvaluationStore} options.store
 * @param {boolean} options.enabled - False outside the evaluation deployment,
 *   where every route answers 404 so the normal site exposes nothing.
 * @param {string} [options.analysisKey] - When set, reads require the same
 *   value in the `x-evaluation-key` header.
 * @param {() => Date} [options.now]
 */
export function createEvaluationApi({
  store,
  enabled,
  analysisKey = "",
  now = () => new Date(),
}) {
  async function receiveBatch(request) {
    const text = await request.text();
    if (text.length > MAX_BODY_BYTES) {
      return error(413, "The batch is too large.");
    }
    let batch;
    try {
      batch = JSON.parse(text);
    } catch {
      return error(400, "The body is not JSON.");
    }
    const problem = batchProblem(batch);
    if (problem) return error(400, problem);

    const key = batchKey(batch.participant, batch.session, batch.seq);
    await store.setJSON(key, {
      participant: batch.participant,
      session: batch.session,
      seq: batch.seq,
      sentAt: typeof batch.sentAt === "string" ? batch.sentAt : null,
      receivedAt: now().toISOString(),
      events: batch.events,
    });
    return json(200, { ok: true, key });
  }

  function readAllowed(request) {
    if (!analysisKey) return true;
    return request.header("x-evaluation-key") === analysisKey;
  }

  async function listParticipants() {
    const directories = await store.listDirectories(LOG_PREFIX);
    const participants = [];
    for (const directory of directories) {
      const id = directory.slice(LOG_PREFIX.length).replace(/\/$/, "");
      if (!PARTICIPANT_PATTERN.test(id)) continue;
      // One listing per participant, in turn: the store answers a bounded
      // number of requests at once, and this is a handful of small ones.
      // eslint-disable-next-line no-await-in-loop
      const keys = await store.list(`${LOG_PREFIX}${id}/`);
      const sessions = new Set(
        keys.map((key) => key.split("/")[2]).filter(Boolean)
      );
      participants.push({ id, sessions: sessions.size, batches: keys.length });
    }
    participants.sort((a, b) => a.id.localeCompare(b.id));
    return json(200, { participants });
  }

  async function readLogs(request) {
    const participant = request.searchParams.get("participant") ?? "";
    if (!PARTICIPANT_PATTERN.test(participant)) {
      return error(400, "participant is required.");
    }
    const keys = (await store.list(`${LOG_PREFIX}${participant}/`)).sort();
    const batches = [];
    // A few at a time: a long session is hundreds of small objects, and the
    // store answers a bounded number of them concurrently.
    const CONCURRENCY = 16;
    for (let start = 0; start < keys.length; start += CONCURRENCY) {
      const slice = keys.slice(start, start + CONCURRENCY);
      // eslint-disable-next-line no-await-in-loop -- bounded concurrency
      const loaded = await Promise.all(slice.map((key) => store.getJSON(key)));
      for (const batch of loaded) {
        if (batch && Array.isArray(batch.events)) batches.push(batch);
      }
    }
    batches.sort((a, b) => a.session.localeCompare(b.session) || a.seq - b.seq);
    return json(200, { participant, batches });
  }

  /**
   * @param {ApiRequest} request
   * @returns {Promise<ApiResponse>}
   */
  function handle(request) {
    if (!enabled) return Promise.resolve(error(404, "Not found."));
    const { method, action } = request;
    if (action === "log") {
      if (method !== "POST") return error(405, "POST only.");
      return receiveBatch(request);
    }
    if (action === "participants" || action === "logs") {
      if (method !== "GET") return error(405, "GET only.");
      if (!readAllowed(request))
        return error(401, "An analysis key is required.");
      return action === "participants" ? listParticipants() : readLogs(request);
    }
    return error(404, "Not found.");
  }

  return { handle };
}

/**
 * Translate a Fetch API Request into the shape `handle()` reads.
 * @param {Request} request
 * @param {string} action
 * @returns {ApiRequest}
 */
export function fromFetchRequest(request, action) {
  const url = new URL(request.url);
  return {
    method: request.method,
    action,
    searchParams: url.searchParams,
    header: (name) => request.headers.get(name),
    text: () => request.text(),
  };
}

/**
 * Translate `handle()`'s answer into a Fetch API Response.
 * @param {ApiResponse} response
 * @returns {Response}
 */
export function toFetchResponse(response) {
  return new Response(
    response.body === null ? null : JSON.stringify(response.body),
    {
      status: response.status,
      headers: {
        "content-type": "application/json; charset=utf-8",
        "cache-control": "no-store",
      },
    }
  );
}
