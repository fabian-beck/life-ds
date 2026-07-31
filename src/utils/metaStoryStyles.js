/**
 * Visual identity of a meta story: colors, fonts and the SVG marks that
 * punctuate its prose.
 *
 * The registry mirrors `person_styles.json` — one entry per story under a
 * top-level `styles` wrapper — and is resolved here rather than in App.svelte
 * because only the meta story view needs it. Stories without an entry get no
 * variables at all, so the view keeps the neutral editorial palette its CSS
 * declares as fallbacks.
 */

import metaStoryStylesData from "../../data/meta_story_styles.json";
import { parseHexColor } from "./storyHelpers.js";

const rawStyles =
  metaStoryStylesData && typeof metaStoryStylesData === "object"
    ? metaStoryStylesData.styles
    : null;

function normalizeHex(value) {
  return parseHexColor(value) ? value.trim().toUpperCase() : null;
}

function svgToDataUrl(svg) {
  if (typeof svg !== "string") return null;
  const trimmed = svg.trim();
  if (!trimmed.startsWith("<svg")) return null;
  return `data:image/svg+xml,${encodeURIComponent(trimmed).replace(/%0A/g, "")}`;
}

/**
 * Normalized style for one meta story, or null when the story has none.
 * @param {string} metaStoryId - The meta story's id, e.g. "computing_pioneers"
 * @returns {Object|null} { primary, secondary, background, backgroundRgb,
 *   patternDataUrl, separatorGlyphDataUrl, ornamentDataUrl, headingFont, bodyFont }
 */
export function metaStoryStyle(metaStoryId) {
  const raw =
    metaStoryId && rawStyles && typeof rawStyles === "object"
      ? rawStyles[metaStoryId]
      : null;
  if (!raw || typeof raw !== "object") return null;

  const primary = normalizeHex(raw.primary);
  const secondary = normalizeHex(raw.secondary);
  const background = normalizeHex(raw.background);
  const rgb = background ? parseHexColor(background) : null;

  const style = {
    primary,
    secondary,
    background,
    backgroundRgb: rgb ? `${rgb.r}, ${rgb.g}, ${rgb.b}` : null,
    patternDataUrl: svgToDataUrl(raw.background_pattern_svg),
    separatorGlyphDataUrl: svgToDataUrl(raw.separator_glyph_svg),
    ornamentDataUrl: svgToDataUrl(raw.ornament_svg),
    headingFont:
      typeof raw.heading_font === "string" && raw.heading_font.trim()
        ? raw.heading_font.trim()
        : null,
    bodyFont:
      typeof raw.body_font === "string" && raw.body_font.trim()
        ? raw.body_font.trim()
        : null,
  };
  return Object.values(style).some(Boolean) ? style : null;
}

/**
 * CSS custom property declarations for a normalized meta story style.
 *
 * `--heading-font` and `--body-font` are the same variables the timeline,
 * network and map already read, so setting them on the story container styles
 * the whole article, components included.
 * @param {Object|null} style - A style from {@link metaStoryStyle}
 * @returns {string} Semicolon-separated CSS variable declarations
 */
export function metaStoryStyleVars(style) {
  if (!style || typeof style !== "object") return "";
  const segments = [];
  if (style.primary) segments.push(`--ms-primary: ${style.primary}`);
  if (style.secondary) segments.push(`--ms-secondary: ${style.secondary}`);
  if (style.background) segments.push(`--ms-page-bg: ${style.background}`);
  if (style.backgroundRgb)
    segments.push(`--ms-page-bg-rgb: ${style.backgroundRgb}`);
  if (style.patternDataUrl)
    segments.push(`--ms-pattern-image: url("${style.patternDataUrl}")`);
  if (style.separatorGlyphDataUrl)
    segments.push(`--ms-glyph: url("${style.separatorGlyphDataUrl}")`);
  if (style.ornamentDataUrl)
    segments.push(`--ms-ornament: url("${style.ornamentDataUrl}")`);
  if (style.headingFont)
    segments.push(`--heading-font: "${style.headingFont}", Inter, sans-serif`);
  if (style.bodyFont)
    segments.push(`--body-font: "${style.bodyFont}", Inter, sans-serif`);
  return segments.join("; ");
}
