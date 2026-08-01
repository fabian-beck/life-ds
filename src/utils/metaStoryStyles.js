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
 * How a story's boxes are cut.
 *
 * A named vocabulary rather than raw CSS in the data: the frame has to work on
 * a full-bleed narration card, on a floating chapter header and on a caption
 * badge at once, so what the story chooses is a *character* and the sizes for
 * each role are decided here. It also keeps generated values out of a style
 * attribute — the entries below are the only shapes that can ever be applied.
 *
 * `radius` frames panels (cards, tooltips, figures), `radiusSmall` the chips
 * and badges inside them, and `ruleWidth` sets the hairlines that are rules
 * rather than frames — the subhead underline, the pulled quote's bar — which
 * have to grow to 3px before `double` can draw two lines at all.
 *
 * Circles and pills that mark a position rather than enclose content — event
 * dots, the year pill, the pager buttons — keep their own geometry: they are
 * not frames.
 */
export const FRAMES = {
  // Machine-cut: no radius at all, a hairline rule. Grids, circuitry, Bauhaus.
  square: {
    radius: "0",
    radiusSmall: "0",
    borderWidth: "1px",
    borderStyle: "solid",
    ruleWidth: "1px",
  },
  // The double rule of an engraved broadside, corners barely eased.
  engraved: {
    radius: "2px",
    radiusSmall: "1px",
    borderWidth: "3px",
    borderStyle: "double",
    ruleWidth: "3px",
  },
  // The neutral default: what every box looked like before frames existed.
  soft: {
    radius: "16px",
    radiusSmall: "0.35rem",
    borderWidth: "1px",
    borderStyle: "solid",
    ruleWidth: "1px",
  },
  // Round-headed: a panel that springs at the top and sits flat, like an arcade.
  arched: {
    radius: "1.75rem 1.75rem 0.3rem 0.3rem",
    radiusSmall: "0.6rem 0.6rem 0.1rem 0.1rem",
    borderWidth: "1px",
    borderStyle: "solid",
    ruleWidth: "1px",
  },
  // Grown rather than drawn: opposite corners disagree, so no edge is repeated.
  organic: {
    radius: "1.75rem 0.6rem 1.75rem 0.6rem",
    radiusSmall: "0.7rem 0.25rem 0.7rem 0.25rem",
    borderWidth: "1px",
    borderStyle: "solid",
    ruleWidth: "1px",
  },
};

/**
 * Normalized style for one meta story, or null when the story has none.
 * @param {string} metaStoryId - The meta story's id, e.g. "computing_pioneers"
 * @returns {Object|null} { primary, secondary, background, backgroundRgb,
 *   patternDataUrl, separatorGlyphDataUrl, ornamentDataUrl, frame, headingFont,
 *   bodyFont }
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
    frame:
      typeof raw.frame === "string" && raw.frame.trim() in FRAMES
        ? raw.frame.trim()
        : null,
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
  const frame = FRAMES[style.frame];
  if (frame) {
    segments.push(`--ms-frame-radius: ${frame.radius}`);
    segments.push(`--ms-frame-radius-sm: ${frame.radiusSmall}`);
    segments.push(`--ms-frame-border-width: ${frame.borderWidth}`);
    segments.push(`--ms-frame-border-style: ${frame.borderStyle}`);
    segments.push(`--ms-frame-rule-width: ${frame.ruleWidth}`);
  }
  if (style.headingFont)
    segments.push(`--heading-font: "${style.headingFont}", Inter, sans-serif`);
  if (style.bodyFont)
    segments.push(`--body-font: "${style.bodyFont}", Inter, sans-serif`);
  return segments.join("; ");
}
