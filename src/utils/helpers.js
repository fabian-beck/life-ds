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
 * Generate CSS variable string from a style configuration object.
 * @param {Object} style - The style configuration object
 * @returns {string} CSS variable declarations as a semicolon-separated string
 */
export function storyStyleVars(style) {
  if (!style || typeof style !== "object") return "";
  const segments = [];
  if (style.background) segments.push(`--story-bg: ${style.background}`);
  if (style.backgroundRgb)
    segments.push(`--story-bg-rgb: ${style.backgroundRgb}`);
  if (style.primary) segments.push(`--story-primary: ${style.primary}`);
  if (style.secondary) segments.push(`--story-secondary: ${style.secondary}`);
  if (style.backgroundPatternDataUrl) {
    segments.push(
      `--story-pattern-image: url("${style.backgroundPatternDataUrl}")`
    );
    segments.push(`--story-pattern-size: 500px`);
  }
  if (style.separatorGlyphDataUrl) {
    segments.push(
      `--story-separator-glyph: url("${style.separatorGlyphDataUrl}")`
    );
  }
  if (style.headingFont) {
    segments.push(
      `--story-heading-font: "${style.headingFont}", Inter, sans-serif`
    );
  }
  if (style.bodyFont) {
    segments.push(
      `--story-body-font: "${style.bodyFont}", Inter, sans-serif`
    );
  }
  return segments.join("; ");
}

/**
 * Join items with a separator glyph (from style config) or fallback to a default separator.
 * @param {Array<string>} items - The items to join
 * @param {Object} styleConfig - Style configuration with optional separatorGlyphDataUrl
 * @param {string} fallback - Fallback separator (default: " · ")
 * @returns {string} HTML string with items joined by separator
 */
export function joinWithSeparator(items, styleConfig, fallback = " · ") {
  if (!items || items.length === 0) return "";
  if (items.length === 1) return items[0];

  // Use separator_glyph_svg if available
  if (styleConfig?.separatorGlyphDataUrl) {
    return items.join(
      `<span class="separator-glyph" style="display: inline-block; margin: 0 0.5rem; width: 1em; height: 1em; vertical-align: middle; background: url('${styleConfig.separatorGlyphDataUrl}') center/contain no-repeat;"></span>`
    );
  }

  // Fallback separator
  return items.join(fallback);
}
