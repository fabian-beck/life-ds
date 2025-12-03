import { derived } from 'svelte/store';
import { querystring } from 'svelte-spa-router';

/**
 * Derived store that parses query parameters from the current URL
 * Returns an object with boolean flags for timeline and network modals,
 * and the slide index (null if not present or slide 0)
 */
export const queryParams = derived(querystring, ($querystring) => {
  const params = new URLSearchParams($querystring || '');
  const slideStr = params.get('slide');
  const slideIndex = slideStr ? parseInt(slideStr, 10) : null;

  return {
    timeline: params.get('timeline') === '1',
    network: params.get('network') === '1',
    slide: slideIndex,
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

  if (params.slide !== null && params.slide !== undefined && params.slide !== 0) {
    search.set('slide', params.slide.toString());
  }

  if (params.timeline) {
    search.set('timeline', '1');
  }

  if (params.network) {
    search.set('network', '1');
  }

  const searchStr = search.toString();
  return searchStr ? `${basePath}?${searchStr}` : basePath;
}
