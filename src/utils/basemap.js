/**
 * Shared Protomaps basemap bootstrap for the map components.
 *
 * StoryMap, MetaStoryMap, and LandingMap each carried their own copy of the
 * same four steps — candidate URLs, HEAD-probe resolution, dark style
 * construction, pmtiles protocol registration — and the copies had already
 * started to drift (one skipped the teardown guard, one never memoized the
 * style). The only real difference between the maps is how many labels they
 * want, so that is the one parameter.
 */

import maplibregl from "maplibre-gl";
import { Protocol } from "pmtiles";
import { layers, namedFlavor } from "@protomaps/basemaps";
import { assetUrl } from "./assetUrl.js";

/**
 * A `public/` asset path as an absolute URL against the page it is loaded on.
 * @param {string} path - Site-absolute path, placeholders and all
 * @returns {string} Absolute URL
 */
function absoluteAssetUrl(path) {
  return new URL(assetUrl(path), window.location.href).href;
}

// Local basemap (zoom 0-5) extracted from Protomaps v4 demo bucket.
const DEFAULT_PM_TILES_URL = assetUrl("/basemap.pmtiles");

// The letterforms and icons the style draws with, vendored next to the tiles
// by scripts/vendor_basemap_assets.mjs. Pointing these at protomaps.github.io,
// as the upstream style does, sent every visitor's IP to a US CDN on every map
// view and left the map missing its icons whenever that host was unreachable.
// MapLibre fills in {fontstack} and {range}, and appends .json/.png and @2x to
// the sprite path.
//
// The sprite URL has to be absolute — MapLibre rejects a site-absolute one
// outright ("Invalid sprite URL … must be absolute") and the map then loads
// with no icons at all. The glyphs URL must stay site-absolute for the
// opposite reason: resolving it through URL() percent-encodes the braces, and
// MapLibre then reports the {fontstack} and {range} tokens as missing.
const GLYPHS_URL = assetUrl("/basemap-assets/fonts/{fontstack}/{range}.pbf");
const SPRITE_URL = absoluteAssetUrl("/basemap-assets/sprites/v4/dark");
const PRIMARY_PM_TILES_URL =
  import.meta.env.VITE_PROTOMAPS_PM_TILES_URL ?? DEFAULT_PM_TILES_URL;
const FALLBACK_PM_TILES_URL =
  import.meta.env.VITE_PROTOMAPS_PM_TILES_FALLBACK_URL ?? DEFAULT_PM_TILES_URL;

// A reachable URL holds for the whole session, so later maps skip the probe.
// A failure is not memoized: the next map gets to try again.
let resolvedUrl = null;

/**
 * The pmtiles URL to use, probing the primary and fallback in parallel.
 * @returns {Promise<string|null>} A reachable URL, or null when neither
 *   candidate answers — the caller shows its own localized error.
 */
export async function resolveBasemapUrl() {
  if (resolvedUrl) return resolvedUrl;
  const candidates = [
    ...new Set([PRIMARY_PM_TILES_URL, FALLBACK_PM_TILES_URL].filter(Boolean)),
  ];
  const results = await Promise.allSettled(
    candidates.map(async (url) => {
      const res = await fetch(url, { method: "HEAD" });
      if (res.ok) return url;
      throw new Error(`Failed to fetch ${url}`);
    })
  );
  const ok = results.find((r) => r.status === "fulfilled");
  if (ok) {
    resolvedUrl = ok.value;
    return resolvedUrl;
  }
  return null;
}

// How much lettering each map wants on the basemap:
// - "none": geography only — the story map draws its own markers and labels
// - "places": place and water names, but no boundary/border lines or labels
// - "full": everything the flavor defines
const LABEL_FILTERS = {
  none: (layer, lowerId) => {
    if (layer.type === "symbol") return false;
    if (
      lowerId.includes("label") ||
      lowerId.includes("text") ||
      lowerId.includes("name")
    ) {
      return false;
    }
    return !(lowerId.includes("boundary") || lowerId.includes("border"));
  },
  places: (layer, lowerId) =>
    !(lowerId.includes("boundary") || lowerId.includes("border")),
  full: () => true,
};

// Built styles keyed by url|lang|labelMode; MapLibre mutates the style object
// it is given, so callers always receive a fresh deep clone of the cache.
const styleCache = new Map();

/**
 * The dark Protomaps style for a resolved pmtiles URL.
 * @param {Object} options
 * @param {string} options.url - A URL from resolveBasemapUrl()
 * @param {string} [options.lang] - Label language ("en", "de", …)
 * @param {"none"|"places"|"full"} [options.labelMode] - How much lettering
 * @returns {Object} A style object the caller owns
 */
export function createBasemapStyle({ url, lang = "en", labelMode = "full" }) {
  const key = `${url}|${lang}|${labelMode}`;
  if (!styleCache.has(key)) {
    const filter = LABEL_FILTERS[labelMode] ?? LABEL_FILTERS.full;
    styleCache.set(
      key,
      JSON.stringify({
        version: 8,
        glyphs: GLYPHS_URL,
        sprite: SPRITE_URL,
        sources: {
          protomaps: {
            type: "vector",
            url: `pmtiles://${url}`,
            attribution:
              '<a href="https://protomaps.com">Protomaps</a> · <a href="https://www.openstreetmap.org">OpenStreetMap</a>',
          },
        },
        layers: layers("protomaps", namedFlavor("dark"), {
          lang,
          labelsOnly: false,
        }).filter((layer) => {
          const id = layer?.id ?? "";
          if (typeof id !== "string") return true;
          return filter(layer, id.toLowerCase());
        }),
      })
    );
  }
  return JSON.parse(styleCache.get(key));
}

/**
 * The label layers' text expressions for a language, for swapping a live
 * map's labels in place without rebuilding the style (which would tear down
 * the data layers and their event handlers).
 * @param {string} lang - Label language ("en", "de", …)
 * @returns {Array<{id: string, textField: unknown}>}
 */
export function basemapLabelExpressions(lang) {
  return layers("protomaps", namedFlavor("dark"), {
    lang,
    labelsOnly: true,
  })
    .filter((layer) => layer?.type === "symbol" && layer.layout?.["text-field"])
    .map((layer) => ({ id: layer.id, textField: layer.layout["text-field"] }));
}

// The pmtiles protocol is one global MapLibre registry entry, but each map
// component used to register and remove it independently — safe only as long
// as no two maps are ever mounted at once. Reference counting removes that
// assumption.
let protocol = null;
let protocolUsers = 0;

/** Ensure the pmtiles protocol is registered; call once per map instance. */
export function acquirePmtilesProtocol() {
  if (!protocol) {
    protocol = new Protocol();
    maplibregl.addProtocol("pmtiles", protocol.tile);
  }
  protocolUsers += 1;
}

/** Release one map instance's use; unregisters when the last map is gone. */
export function releasePmtilesProtocol() {
  protocolUsers = Math.max(0, protocolUsers - 1);
  if (protocolUsers === 0 && protocol) {
    try {
      if (typeof maplibregl.removeProtocol === "function") {
        maplibregl.removeProtocol("pmtiles");
      }
    } catch {
      // Protocol was already removed; nothing to do.
    }
    protocol = null;
  }
}
