/**
 * Shared utility functions used across multiple components.
 */

/**
 * Clamp a value between min and max bounds.
 * @param {number} value - The value to clamp
 * @param {number} min - The minimum bound
 * @param {number} max - The maximum bound
 * @returns {number} The clamped value
 */
export function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

/**
 * Normalize a display name by converting underscores to spaces and collapsing whitespace.
 * @param {string} value - The name to normalize
 * @returns {string} The normalized display name
 */
export function displayName(value = "") {
  if (typeof value !== "string") return "";
  return value.replace(/_/g, " ").replace(/\s+/g, " ").trim();
}

/**
 * Join `[name, value]` pairs into an inline `style` string.
 *
 * Four builders write one of these — the person story, the meta story, the
 * landing card and the person card — and each used to spell out its own
 * `if (value) segments.push(...)` ladder. What they share is only this: a
 * variable whose value is missing is omitted rather than emitted empty, so
 * the stylesheet's own fallback (`var(--x, …)`) is what takes over.
 *
 * They do *not* share their variable names. The same `style.background`
 * becomes `--story-bg`, `--ms-page-bg` or `--card-bg`, and the meta story
 * deliberately leaves its fonts unprefixed because `meta-frames.css` reads
 * `--heading-font`. So each builder still names its own variables, in its own
 * order, and only the mechanics live here.
 *
 * @param {Array<[string, unknown]>} entries - `[cssVariableName, value]` pairs
 * @returns {string} e.g. `--story-bg: #000; --story-primary: #fff`
 */
export function styleVars(entries) {
  return entries
    .filter(
      ([, value]) => value !== null && value !== undefined && value !== ""
    )
    .map(([name, value]) => `${name}: ${value}`)
    .join("; ");
}

/**
 * The app's one font stack: a chosen face in front of the shared fallbacks.
 *
 * Written out identically in four places before, which is three chances for
 * the fallback chain to drift away from the one the stylesheets assume.
 * @param {string} [font] - Family name, or nothing
 * @param {string} [fallback] - What to return when there is no font
 * @returns {string|null} A CSS font-family value
 */
export function fontStack(font, fallback = null) {
  return font ? `"${font}", Inter, sans-serif` : fallback;
}

/**
 * A CSS `url("…")` wrapper, or nothing when there is no source.
 * @param {string} [value] - URL or data URL
 * @returns {string|null} A CSS url() value
 */
export function cssUrl(value) {
  return value ? `url("${value}")` : null;
}

/**
 * Generate CSS variable string from a style configuration object.
 * @param {Object} style - The style configuration object
 * @returns {string} CSS variable declarations as a semicolon-separated string
 */
export function storyStyleVars(style) {
  if (!style || typeof style !== "object") return "";
  return styleVars([
    ["--story-bg", style.background],
    ["--story-bg-rgb", style.backgroundRgb],
    ["--story-primary", style.primary],
    ["--story-secondary", style.secondary],
    ["--story-pattern-image", cssUrl(style.backgroundPatternDataUrl)],
    ["--story-pattern-size", style.backgroundPatternDataUrl ? "500px" : null],
    ["--story-separator-glyph", cssUrl(style.separatorGlyphDataUrl)],
    ["--story-heading-font", fontStack(style.headingFont)],
    ["--story-body-font", fontStack(style.bodyFont)],
  ]);
}
