import { derived } from "svelte/store";
import { querystring } from "svelte-spa-router";

/**
 * Derived store that parses query parameters from the current URL
 * Returns an object with boolean flags for timeline and network modals,
 * the slide index, and the event index (both null if not present)
 */
export const queryParams = derived(querystring, ($querystring) => {
  const params = new URLSearchParams($querystring || "");
  const slideStr = params.get("slide");
  const slideIndex = slideStr ? parseInt(slideStr, 10) : null;
  const eventStr = params.get("event");
  const eventIndex = eventStr ? parseInt(eventStr, 10) : null;

  return {
    timeline: params.get("timeline") === "1",
    network: params.get("network") === "1",
    slide: slideIndex,
    event: eventIndex,
  };
});

/**
 * Helper function to build a URL with query parameters
 * @param {string} basePath - The base path without query string
 * @param {Object} params - Object with timeline, network, and slide
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

  const searchStr = search.toString();
  return searchStr ? `${basePath}?${searchStr}` : basePath;
}
