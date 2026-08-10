/**
 * Color primitives shared by the story views and maps.
 */
/**
 * Parse a hex color string to RGB components.
 * @param {string} value - Hex color like "#38BDF8"
 * @returns {Object|null} {r, g, b} or null
 */
export function parseHexColor(value) {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  if (!/^#[0-9a-fA-F]{6}$/.test(trimmed)) return null;
  const r = parseInt(trimmed.slice(1, 3), 16);
  const g = parseInt(trimmed.slice(3, 5), 16);
  const b = parseInt(trimmed.slice(5, 7), 16);
  if ([r, g, b].some((component) => Number.isNaN(component))) {
    return null;
  }
  return { r, g, b };
}
/**
 * Convert hex color to rgba string.
 * @param {string} hex - Hex color string
 * @param {number} alpha - Alpha value 0-1
 * @returns {string|null} RGBA string or null
 */
export function rgbaFromHex(hex, alpha) {
  const parsed = parseHexColor(hex);
  if (!parsed) return null;
  const nextAlpha = Math.min(Math.max(alpha, 0), 1);
  return `rgba(${parsed.r}, ${parsed.g}, ${parsed.b}, ${nextAlpha})`;
}
