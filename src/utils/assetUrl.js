/**
 * Resolve a site-absolute asset path against the deployment base path.
 *
 * Generated data stores portrait paths as site-absolute strings such as
 * `/portraits/ada_lovelace_medium.webp`, and `public/` assets are referenced
 * the same way. Served from a domain root — the way the published site is —
 * those paths are correct as-is, but the dev server and the interface tests
 * serve the app from a subdirectory (`import.meta.env.BASE_URL ===
 * "/life-ds/"`), where they would resolve against the domain root and 404.
 *
 * Prefixing here — at the point where a path becomes a URL — keeps the
 * deployment layout out of the data files and out of the Python generators
 * that write them.
 *
 * Values that are not site-absolute local paths pass through untouched:
 * absolute URLs (Wikimedia, Flickr), protocol-relative URLs, data URIs, and
 * paths that already carry the base prefix.
 *
 * @param {string} path - Asset path or URL
 * @returns {string} URL usable from the deployed base path
 */
export function assetUrl(path) {
  const base = import.meta.env.BASE_URL;
  if (typeof path !== "string") return path;
  if (!path.startsWith("/") || path.startsWith("//")) return path;
  if (base === "/" || path.startsWith(base)) return path;
  return base.replace(/\/$/, "") + path;
}
