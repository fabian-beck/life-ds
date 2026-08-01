import { derived } from "svelte/store";
import { querystring } from "./router.js";

// The landing's own query parameters: its search box and its role chips. A
// story or collection opened from a filtered landing carries them along in
// `from_landing` so closing it can put the landing back the way it was found.
const LANDING_FILTER_KEYS = ["q", "roles"];

/**
 * Reduce a query string to the landing's filter parameters.
 * @param {string} querystringValue - A raw query string, with or without "?"
 * @returns {string|null} - "q=…&roles=…", or null when nothing is filtered
 */
export function landingFilterQuery(querystringValue) {
  const source = new URLSearchParams(
    (querystringValue || "").replace(/^\?/, "")
  );
  const filters = new URLSearchParams();
  for (const key of LANDING_FILTER_KEYS) {
    const value = source.get(key);
    if (value) filters.set(key, value);
  }
  return filters.toString() || null;
}

/**
 * Derived store that parses query parameters from the current URL
 * Returns an object with boolean flags for timeline and network modals,
 * the slide index, the event index, and the from_meta and from_landing
 * contexts (all null if not present)
 */
export const queryParams = derived(querystring, ($querystring) => {
  const params = new URLSearchParams($querystring || "");
  // Treat non-numeric values as absent so NaN never leaks into scroll math
  const parseIndex = (value) => {
    if (!value) return null;
    const parsed = parseInt(value, 10);
    return Number.isNaN(parsed) ? null : parsed;
  };
  const slideIndex = parseIndex(params.get("slide"));
  const eventIndex = parseIndex(params.get("event"));

  return {
    timeline: params.get("timeline") === "1",
    network: params.get("network") === "1",
    slide: slideIndex,
    event: eventIndex,
    from_meta: params.get("from_meta") || null,
    from_landing: params.get("from_landing") || null,
  };
});

/**
 * The query string that carries a reader's origin into a person story: the
 * collection they came through, and the landing filters behind it.
 * @param {string|null} metaStoryId - The collection being read, if any
 * @param {string|null} fromLanding - The landing filters, if any
 * @returns {string} - "from_meta=…&from_landing=…", or "" when there is no
 *   context to carry
 */
export function originQuery(metaStoryId, fromLanding) {
  const params = new URLSearchParams();
  if (metaStoryId) params.set("from_meta", metaStoryId);
  if (fromLanding) params.set("from_landing", fromLanding);
  return params.toString();
}

/**
 * The parameters that say where the reader came from rather than what the view
 * is showing. Every URL rebuilt while the reader is inside a story or a
 * collection has to carry them through unchanged, so they are spread from here
 * instead of being listed again at each call site.
 * @param {Object} params - The parsed query parameters
 * @returns {Object} - The from_meta and from_landing context
 */
export function navigationContext(params) {
  return {
    from_meta: params.from_meta,
    from_landing: params.from_landing,
  };
}

/**
 * Helper function to build a URL with query parameters
 * @param {string} basePath - The base path without query string
 * @param {Object} params - Object with timeline, network, slide, from_meta,
 *   and from_landing
 * @returns {string} - Complete URL with query string if params are present
 */
export function buildUrlWithParams(basePath, params) {
  const search = new URLSearchParams();

  if (
    params.slide !== null &&
    params.slide !== undefined &&
    params.slide !== 0
  ) {
    search.set("slide", params.slide.toString());
  }

  if (params.timeline) {
    search.set("timeline", "1");
  }

  if (params.network) {
    search.set("network", "1");
  }

  // Preserve from_meta parameter if present
  if (params.from_meta) {
    search.set("from_meta", params.from_meta);
  }

  // Preserve the landing filters the reader arrived with
  if (params.from_landing) {
    search.set("from_landing", params.from_landing);
  }

  const searchStr = search.toString();
  return searchStr ? `${basePath}?${searchStr}` : basePath;
}
