/**
 * Read the application's hash routes the way the evaluation analysis needs
 * them: which view a route shows, and what the query says about it.
 *
 * The logger records a route as the raw path and query string it saw, so the
 * log stays a faithful trace; interpreting it is this module's job and happens
 * once, at analysis time, in one place. The shapes are the ones App.svelte
 * matches: `/`, `/{lang}`, `/{lang}/story/{id}`, `/{lang}/meta/{id}`, each with
 * an optional query.
 */

/**
 * @typedef {Object} ParsedRoute
 * @property {string|null} lang - The language prefix, or null when absent
 * @property {"landing"|"story"|"meta"|"other"} kind
 * @property {string|null} id - The person or meta story id, for story and meta
 * @property {number|null} slide - The `slide` query value
 * @property {number|null} event - The `event` query value
 * @property {boolean} timeline - Whether the timeline is expanded
 * @property {boolean} network - Whether the network modal is open
 * @property {string|null} fromMeta - The meta story a person story was entered from
 * @property {string|null} fromLanding - The landing filters carried along
 * @property {string|null} search - The landing search query
 * @property {string[]} roles - The landing role filters
 * @property {string|null} collection - The landing collection filter
 */

const ROUTE_PATTERN =
  /^\/(?:([a-z]{2})(?=\/|$))?\/?(?:(story|meta|exhibition)\/([^/?#]+))?/;

function parseIndex(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = parseInt(value, 10);
  return Number.isNaN(parsed) ? null : parsed;
}

/**
 * @param {string} path - The route path without its query, e.g. "/en/story/x"
 * @param {string} [query] - The raw query string, with or without "?"
 * @returns {ParsedRoute}
 */
export function parseRoute(path, query = "") {
  const match = String(path ?? "").match(ROUTE_PATTERN);
  const params = new URLSearchParams(String(query ?? "").replace(/^\?/, ""));
  const lang = match?.[1] ?? null;
  const section = match?.[2] ?? null;
  const rawId = match?.[3] ?? null;
  /** @type {ParsedRoute["kind"]} */
  let kind = "other";
  let id = null;
  if (section === "story" || section === "exhibition") {
    kind = "story";
    id = decodeURIComponent(rawId);
  } else if (section === "meta") {
    kind = "meta";
    id = decodeURIComponent(rawId);
  } else if (match && /^\/(?:[a-z]{2})?\/?$/.test(String(path ?? ""))) {
    kind = "landing";
  }
  const roles = params.get("roles");
  return {
    lang,
    kind,
    id,
    slide: parseIndex(params.get("slide")),
    event: parseIndex(params.get("event")),
    timeline: params.get("timeline") === "1",
    network: params.get("network") === "1",
    fromMeta: params.get("from_meta") || null,
    fromLanding: params.get("from_landing") || null,
    search: params.get("q") || null,
    roles: roles ? roles.split(",").filter(Boolean) : [],
    collection: params.get("collection") || null,
  };
}

/**
 * A stable label for the view a route shows: "landing", "story:ada_lovelace",
 * "meta:computing_pioneers", or "other".
 * @param {ParsedRoute} route
 * @returns {string}
 */
export function viewKey(route) {
  return route.id ? `${route.kind}:${route.id}` : route.kind;
}
