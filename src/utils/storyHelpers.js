/**
 * Story-specific utility functions for date formatting, event processing, and map helpers.
 */

import { findPersonMentions } from "./personNames.js";
import { assetUrl } from "./assetUrl.js";
import {
  mdiCircleSmall,
  mdiBabyFaceOutline,
  mdiSkullOutline,
  mdiSchoolOutline,
  mdiRing,
  mdiCrownOutline,
  mdiStarCircleOutline,
  mdiSwordCross,
  mdiBookOpenVariant,
  mdiBriefcaseOutline,
  mdiNavigationVariant,
} from "@mdi/js";

/**
 * Icon rules for matching events to icons based on content.
 */
export const EVENT_ICON_RULES = [
  {
    icon: mdiBabyFaceOutline,
    matches: (event, text) =>
      event?.age === 0 || text.includes("birth") || text.includes("born"),
  },
  {
    icon: mdiSkullOutline,
    matches: (_event, text) =>
      text.includes("death") ||
      text.includes("died") ||
      text.includes("passed away"),
  },
  {
    icon: mdiSchoolOutline,
    matches: (_event, text) =>
      text.includes("graduat") ||
      text.includes("degree") ||
      text.includes("diploma"),
  },
  {
    icon: mdiRing,
    matches: (_event, text) =>
      text.includes("marriage") ||
      text.includes("married") ||
      text.includes("wedding"),
  },
  {
    icon: mdiCrownOutline,
    matches: (_event, text) =>
      text.includes("crowned") ||
      text.includes("coronation") ||
      text.includes("enthroned"),
  },
  {
    icon: mdiStarCircleOutline,
    matches: (_event, text) =>
      text.includes("award") ||
      text.includes("prize") ||
      text.includes("honor") ||
      text.includes("medal"),
  },
  {
    icon: mdiSwordCross,
    matches: (_event, text) =>
      text.includes("battle") ||
      text.includes("war") ||
      text.includes("campaign"),
  },
  {
    icon: mdiBookOpenVariant,
    matches: (_event, text) =>
      text.includes("publish") ||
      text.includes("publication") ||
      text.includes("book") ||
      text.includes("paper"),
  },
  {
    icon: mdiBriefcaseOutline,
    matches: (_event, text) =>
      text.includes("appointed") ||
      text.includes("elected") ||
      text.includes("named") ||
      text.includes("assumes"),
  },
  {
    icon: mdiNavigationVariant,
    matches: (_event, text) =>
      text.includes("voyage") ||
      text.includes("expedition") ||
      text.includes("travels") ||
      text.includes("journey"),
  },
];

/**
 * A calendar date as it appears in the data: an optional leading minus, a year
 * of one to six digits, and optional month and day parts.
 */
const HISTORICAL_DATE_PATTERN = /^(-?)(\d{1,6})(?:-(\d{2})(?:-(\d{2}))?)?$/;

/**
 * Expand a stored date into an instant the ECMAScript date parser accepts.
 *
 * Two shapes in the data are rejected by `Date.parse` as written. Pre-1000
 * years are not always zero-padded ("973-05-06" alongside "0975-01-01"), and
 * years before the common era need the expanded six-digit form
 * ("-000500-01-01"), not the four digits a B.C. year would naturally be
 * written with. Everything that turns a stored date into a `Date` goes through
 * here so both are handled once.
 *
 * Years before the common era follow ISO 8601's astronomical numbering, where
 * year 0 is 1 B.C. and "-000500" is 501 B.C.
 *
 * @param {string} value - Date string like "1955-04-18", "973-05-06" or "-0500"
 * @returns {string|null} Full ISO instant, or null when unparseable
 */
export function toIsoInstant(value) {
  if (typeof value !== "string") return null;
  const match = HISTORICAL_DATE_PATTERN.exec(value.trim());
  if (!match) return null;
  const [, sign, year, month, day] = match;
  // "-000000" is not a legal expanded year: 1 B.C. is written "0000".
  const isNegative = sign === "-" && Number(year) !== 0;
  const isoYear = isNegative
    ? `-${year.padStart(6, "0")}`
    : year.length > 4
      ? `+${year.padStart(6, "0")}`
      : year.padStart(4, "0");
  return `${isoYear}-${month ?? "01"}-${day ?? "01"}T00:00:00Z`;
}

/**
 * Parse a stored date into a `Date` at UTC midnight.
 * @param {string} value - Date string
 * @returns {Date|null} Parsed date, or null when unparseable
 */
export function parseHistoricalDate(value) {
  const iso = toIsoInstant(value);
  if (!iso) return null;
  const timestamp = Date.parse(iso);
  return Number.isNaN(timestamp) ? null : new Date(timestamp);
}

/**
 * Extract the year from a stored date.
 *
 * Read in UTC, because the dates are stored as UTC midnight — a local-time
 * read would land on December 31 of the previous year west of Greenwich.
 *
 * @param {string} value - Date string
 * @returns {number} Astronomical year (negative before the common era), or NaN
 */
export function extractYear(value) {
  const date = parseHistoricalDate(value);
  return date ? date.getUTCFullYear() : NaN;
}

/**
 * Convert an event to a sortable timestamp.
 * @param {Object} event - Event object with date and date_precision
 * @returns {number} Timestamp in milliseconds, or Infinity if no date
 */
export function toTimestamp(event) {
  if (!event?.date) return Number.POSITIVE_INFINITY;
  const date = parseHistoricalDate(event.date);
  return date ? date.getTime() : Number.NaN;
}

/**
 * Format a single date value according to precision.
 * @param {string} value - Date string
 * @param {string} precision - "day", "month", or "year"
 * @param {Object} formatters - Intl.DateTimeFormat instances for each precision
 * @returns {string|null} Formatted date or null
 */
export function formatSingleDate(value, precision, formatters) {
  if (!value) return null;
  const date = parseHistoricalDate(value);
  if (!date) return null;
  const normalizedPrecision = precision ?? "day";
  // Before the common era the year alone is ambiguous, so those dates are
  // formatted with an explicit era ("501 BC", "501 v. Chr.").
  const set =
    date.getUTCFullYear() <= 0 && formatters.beforeCommonEra
      ? formatters.beforeCommonEra
      : formatters;
  const formatter = set[normalizedPrecision] ?? set.day;
  return formatter.format(date);
}

/**
 * Format an event's date range for display.
 * @param {Object} event - Event with date, date_precision, date_end, date_end_precision, date_label
 * @param {Object} formatters - Intl.DateTimeFormat instances
 * @returns {string} Formatted date string
 */
export function formatDate(event, formatters) {
  if (!event) return "Date unavailable";
  const labelOverride =
    typeof event.date_label === "string" && event.date_label.trim()
      ? event.date_label.trim()
      : null;
  if (labelOverride) {
    return labelOverride;
  }
  const startLabel = formatSingleDate(
    event.date,
    event.date_precision,
    formatters
  );
  const endLabel = formatSingleDate(
    event.date_end,
    event.date_end_precision ?? event.date_precision,
    formatters
  );
  let label = startLabel;
  if (
    startLabel &&
    endLabel &&
    event.date_end &&
    event.date_end !== event.date
  ) {
    label = `${startLabel} – ${endLabel}`;
  }
  if (!label) return "Date unavailable";
  return label;
}

/**
 * Age in completed years on a given date.
 *
 * Coarse dates read as their first day, the same reading the rest of the date
 * handling uses: a month-precision date counts from the first of the month, a
 * year-precision one from January 1.
 *
 * @param {string} birthDate - Birth date string
 * @param {string} value - Date to measure the age at
 * @returns {number|null} Completed years, or null when a date is unparseable or falls before birth
 */
export function computeAgeAtDate(birthDate, value) {
  const birth = parseHistoricalDate(birthDate);
  const date = parseHistoricalDate(value);
  if (!birth || !date) return null;
  const beforeBirthday =
    date.getUTCMonth() < birth.getUTCMonth() ||
    (date.getUTCMonth() === birth.getUTCMonth() &&
      date.getUTCDate() < birth.getUTCDate());
  const age =
    date.getUTCFullYear() - birth.getUTCFullYear() - (beforeBirthday ? 1 : 0);
  return age < 0 ? null : age;
}

/**
 * The ages an event spans.
 *
 * An event that runs over a date range should read as a range of ages too, so
 * the two halves of the header agree. Only the age at the start is stored, so
 * the age at the end is measured against the birth date, and reported only
 * when the event lasts long enough to reach a later birthday.
 *
 * @param {Object} event - Event with age, date, and optionally date_end
 * @param {string} birthDate - Subject's birth date
 * @returns {{start: number, end: number|null}|null} Ages spanned, or null without a stored age
 */
export function getEventAgeRange(event, birthDate) {
  const start = event?.age;
  if (typeof start !== "number") return null;
  if (!event.date_end || event.date_end === event.date) {
    return { start, end: null };
  }
  const end = computeAgeAtDate(birthDate, event.date_end);
  return { start, end: end !== null && end > start ? end : null };
}

/**
 * Get the date note from an event.
 * @param {Object} event - Event object
 * @returns {string|null} Date note or null
 */
export function getDateNote(event) {
  const note = event?.date_note;
  return typeof note === "string" && note.trim() ? note.trim() : null;
}

/**
 * Intl formatters that name the era, built once per language.
 */
const eraYearFormatters = new Map();

function eraYearFormatter(language) {
  let formatter = eraYearFormatters.get(language);
  if (!formatter) {
    formatter = new Intl.DateTimeFormat(language, {
      year: "numeric",
      era: "short",
      timeZone: "UTC",
    });
    eraYearFormatters.set(language, formatter);
  }
  return formatter;
}

/**
 * Render one end of a lifespan.
 * @param {Date|null} date - Parsed date
 * @param {string} language - Language code like "en" or "de"
 * @returns {string|null} Year label, or null when there is no date
 */
function formatLifespanYear(date, language) {
  if (!date) return null;
  const year = date.getUTCFullYear();
  // A bare "500" would read as the common era. Intl already knows the era
  // names in every locale, so the label needs no string of its own.
  return year > 0 ? `${year}` : eraYearFormatter(language).format(date);
}

/**
 * Compute birth-death years label for a person.
 * @param {Object} person - Person object with birth_date/death_date (life event
 *   documents) or birthDate/deathDate (persons registry)
 * @param {string} [language] - Language code, used to name the era for dates
 *   before the common era
 * @returns {string} Years label like "1879 - 1955", "973 - 1024" or "1879"
 */
export function computeYearsLabel(person, language = "en") {
  if (!person) return "";
  // Life event documents use snake_case, the persons registry camelCase — both
  // shapes reach this helper (story slides vs. person cards).
  const birth = parseHistoricalDate(person.birth_date ?? person.birthDate);
  const death = parseHistoricalDate(person.death_date ?? person.deathDate);
  const birthLabel = formatLifespanYear(birth, language);
  const deathLabel = formatLifespanYear(death, language);
  if (birthLabel && deathLabel) {
    return `${birthLabel} - ${deathLabel}`;
  }
  return birthLabel ?? "";
}

/**
 * Normalize the primary location coordinates from an event.
 * @param {Object} event - Event with locations array
 * @returns {Object|null} {lon, lat} or null
 */
export function normalizePrimaryLocation(event) {
  if (!event?.locations || !Array.isArray(event.locations)) {
    return null;
  }

  // Find primary location, or use first with coordinates
  const primary =
    event.locations.find((loc) => loc?.primary === true) || event.locations[0];

  if (!Array.isArray(primary?.centroid) || primary.centroid.length !== 2) {
    return null;
  }

  const [lng, lat] = primary.centroid.map(Number);
  return Number.isFinite(lng) && Number.isFinite(lat)
    ? { lon: lng, lat: lat }
    : null;
}

/**
 * Get all location coordinates from an event.
 * @param {Object} event - Event with locations array
 * @returns {Array} Array of {lon, lat, name, primary} objects
 */
export function normalizeAllLocations(event) {
  if (!event?.locations || !Array.isArray(event.locations)) {
    return [];
  }

  return event.locations
    .filter((loc) => Array.isArray(loc?.centroid) && loc.centroid.length === 2)
    .map((loc) => {
      const [lng, lat] = loc.centroid.map(Number);
      return Number.isFinite(lng) && Number.isFinite(lat)
        ? {
            lon: lng,
            lat: lat,
            name: loc.name_historic,
            primary: loc.primary === true,
          }
        : null;
    })
    .filter((coord) => coord !== null);
}

/**
 * Check if a value is a valid coordinate object.
 * @param {*} value - Value to check
 * @returns {boolean} True if valid coordinate
 */
export function isCoordinate(value) {
  return (
    !!value &&
    typeof value === "object" &&
    Number.isFinite(value.lon) &&
    Number.isFinite(value.lat)
  );
}

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

/**
 * Resolve the appropriate icon for an event based on its content.
 * @param {Object} event - Event object
 * @returns {string} MDI icon path
 */
export function resolveEventIcon(event) {
  const text = `${event?.title ?? ""} ${event?.description ?? ""}`
    .toLowerCase()
    .replace(/\s+/g, " ")
    .trim();
  for (const rule of EVENT_ICON_RULES) {
    try {
      if (rule.matches(event, text)) {
        return rule.icon;
      }
    } catch {
      // ignore rule errors to avoid breaking icon rendering
    }
  }
  return mdiCircleSmall;
}

/**
 * Standard thumbnail widths allowed by Wikimedia for direct (hotlinked) requests.
 * Non-standard widths are rejected with HTTP 400, so any requested width must be
 * snapped to one of these. See https://www.mediawiki.org/wiki/Common_thumbnail_sizes
 */
const WIKIMEDIA_STANDARD_THUMB_WIDTHS = [
  20, 40, 60, 120, 250, 330, 500, 960, 1280, 1920, 3840,
];

/**
 * Snap a desired width up to the smallest allowed Wikimedia standard width
 * (capped at the largest), so the request is accepted and quality is sufficient.
 * @param {number} width - Desired width in pixels
 * @returns {number} A standard Wikimedia thumbnail width
 */
function snapToWikimediaWidth(width) {
  const sizes = WIKIMEDIA_STANDARD_THUMB_WIDTHS;
  return sizes.find((size) => size >= width) ?? sizes[sizes.length - 1];
}

const FLICKR_SIZE_SUFFIXES = [
  [100, "t"],
  [240, "m"],
  [320, "n"],
  [400, "w"],
  [500, ""],
  [640, "z"],
  [800, "c"],
  [1024, "b"],
];

/**
 * Build a Flickr image URL at the nearest supported public size.
 * Size suffixes larger than 1024px use per-size secrets, so they are not
 * safe to derive from a URL stored in the dataset.
 * @param {string} imageUrl - Flickr static image URL
 * @param {number} width - Desired longest edge in pixels
 * @returns {string} Optimized URL or the original when it cannot be derived
 */
function getFlickrThumbnailUrl(imageUrl, width) {
  const match = imageUrl.match(
    /^(https:\/\/live\.staticflickr\.com\/\d+\/\d+_[^_/.]+)(?:_([a-z0-9]+))?(\.(?:jpe?g|png|gif)(?:\?.*)?)$/i
  );
  if (!match) return imageUrl;

  const existingSuffix = match[2]?.toLowerCase();
  const publicSuffixes = ["s", "q", "t", "m", "n", "w", "z", "c", "b"];
  if (existingSuffix && !publicSuffixes.includes(existingSuffix)) {
    return imageUrl;
  }

  const suffix =
    FLICKR_SIZE_SUFFIXES.find(([size]) => size >= width)?.[1] ?? "b";
  return `${match[1]}${suffix ? `_${suffix}` : ""}${match[3]}`;
}

/**
 * Get optimized image URL based on desired width.
 * For portrait objects with multi-size WebP support, selects appropriate size.
 * For Wikimedia Commons and Flickr URLs, uses their thumbnail services.
 * For direct URLs, returns as-is.
 * @param {Object|string} imageOrPortrait - Portrait object or direct URL string
 * @param {number} width - Desired width in pixels
 * @returns {string} Optimized URL or original
 */
export function getThumbnailUrl(imageOrPortrait, width = 400) {
  // Handle portrait objects with multi-size WebP support
  if (imageOrPortrait && typeof imageOrPortrait === "object") {
    const portrait = imageOrPortrait;

    // Select appropriate size based on target width
    if (portrait.thumbnail || portrait.medium || portrait.full) {
      if (width <= 200 && portrait.thumbnail) {
        return assetUrl(portrait.thumbnail);
      } else if (width <= 400 && portrait.medium) {
        return assetUrl(portrait.medium);
      } else if (portrait.full) {
        return assetUrl(portrait.full);
      }
      // Fallback to any available size
      return assetUrl(portrait.thumbnail || portrait.medium || portrait.full);
    }

    // Legacy: portrait object has image property
    if (portrait.image) {
      imageOrPortrait = portrait.image;
    }
  }

  // From here on, imageOrPortrait should be a string URL
  const imageUrl = imageOrPortrait;
  if (!imageUrl || typeof imageUrl !== "string") return imageUrl;

  // Optimize Wikimedia Commons images
  if (imageUrl.includes("upload.wikimedia.org/wikipedia/commons/")) {
    // Wikimedia rejects non-standard thumbnail widths on direct requests (HTTP 400),
    // so snap to an allowed standard size.
    const stdWidth = snapToWikimediaWidth(width);

    // Check if URL is already a thumbnail
    if (imageUrl.includes("/thumb/")) {
      // URL is already a thumbnail - just adjust the size
      // Example: .../thumb/a/b/File.svg/800px-File.svg.png -> .../thumb/a/b/File.svg/500px-File.svg.png
      return imageUrl.replace(/\/\d+px-([^/]+)$/, `/${stdWidth}px-$1`);
    }

    // Convert full URL to thumbnail URL
    const parts = imageUrl.split("/wikipedia/commons/");
    if (parts.length === 2) {
      const [base, path] = parts;
      const filename = path.split("/").pop();
      // For SVG files, append .png to get the rasterized version
      const thumbFilename = filename.toLowerCase().endsWith(".svg")
        ? `${filename}.png`
        : filename;
      return `${base}/wikipedia/commons/thumb/${path}/${stdWidth}px-${thumbFilename}`;
    }
  }

  if (imageUrl.includes("live.staticflickr.com/")) {
    return getFlickrThumbnailUrl(imageUrl, width);
  }

  return assetUrl(imageUrl);
}

/**
 * Filter and validate image data for display.
 * @param {Array} images - Array of image objects or URLs
 * @returns {Array} Valid image objects
 */
export function getValidImages(images) {
  if (!Array.isArray(images) || images.length === 0) return [];

  return images.filter((imageData) => {
    const url = typeof imageData === "string" ? imageData : imageData?.url;
    if (!url || typeof url !== "string") return false;

    // Filter out TIFF images (not supported by browsers)
    if (/\.tiff?(\?|$)/i.test(url)) return false;

    try {
      new URL(url);
      return true;
    } catch {
      return false;
    }
  });
}

/**
 * Extract a readable label from a source URL.
 * @param {string} url - Source URL
 * @returns {Object} {label, isWikipedia}
 */
export function sourceLabel(url) {
  try {
    const urlObj = new URL(url);
    const { hostname, pathname } = urlObj;

    // Handle Wikipedia URLs specially to extract article title
    if (hostname.includes("wikipedia.org")) {
      const match = pathname.match(/\/wiki\/(.+)/);
      if (match) {
        const title = decodeURIComponent(match[1])
          .replace(/_/g, " ")
          .replace(/#.*$/, "");
        return { label: title, isWikipedia: true };
      }
    }

    return { label: hostname.replace(/^www\./, ""), isWikipedia: false };
  } catch {
    return { label: url, isWikipedia: false };
  }
}

/**
 * Where a published work can be followed up, for a publication event.
 *
 * A resolved link comes from the data (`scripts/enrich_publication_links.py`
 * writes it after confirming both the title and the authorship against
 * Wikidata or Wikipedia). When there is none — the work has no record anywhere,
 * or the title the model wrote is a description rather than a name — the search
 * is built here instead: in the reader's language, so a German reader lands in
 * the German encyclopedia, and without ever going stale in the data.
 *
 * @param {Object|null} eventClass - The event's `event_class` block
 * @param {string|null} authorName - The story's subject, i.e. the work's author
 * @param {string} language - Current UI language code
 * @returns {{url: string, site: string, kind: string, isSearch: boolean}|null}
 */
export function getPublicationSource(eventClass, authorName, language = "en") {
  if (!eventClass || eventClass.type !== "publication") return null;

  const link = eventClass.source_link;
  if (link?.url) {
    return {
      url: link.url,
      site: link.site || sourceLabel(link.url).label,
      kind: link.kind || "link",
      isSearch: false,
    };
  }

  const title = (eventClass.title || "").trim();
  if (!title) return null;
  const host = /^[a-z]{2}$/.test(language || "")
    ? `${language}.wikipedia.org`
    : "en.wikipedia.org";
  const query = [title, authorName].filter(Boolean).join(" ");
  return {
    url: `https://${host}/w/index.php?search=${encodeURIComponent(query)}`,
    site: "Wikipedia",
    kind: "search",
    isSearch: true,
  };
}

/**
 * Get the subcategory from a relationship type string.
 * @param {string} relationshipType - Relationship type like "family/spouse"
 * @returns {string|null} Subcategory or null
 */
export function getSubcategory(relationshipType) {
  return relationshipType?.includes("/")
    ? relationshipType.split("/")[1]
    : null;
}

/**
 * Escape special regex characters in a string.
 * Also normalizes hyphens to match various Unicode hyphen characters.
 * @param {string} str - String to escape
 * @returns {string} Escaped string with hyphen normalization
 */
export function escapeRegex(str) {
  // First escape special regex characters
  let escaped = str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  // Replace all types of hyphens with a character class that matches any hyphen variant
  // This handles: regular hyphen (-), non-breaking hyphen (‑), en-dash (–), em-dash (—), minus sign (−)
  escaped = escaped.replace(
    /[-\u2010\u2011\u2012\u2013\u2014\u2212]/g,
    "[-\\u2010\\u2011\\u2012\\u2013\\u2014\\u2212]"
  );
  return escaped;
}

/**
 * Minimum similarity score for a name match to be accepted.
 */
const MATCH_THRESHOLD = 0.6;

/**
 * Check if event year falls within relationship timeframe.
 * @param {number|null} eventYear - Event year
 * @param {number} startYear - Relationship start year
 * @param {number} endYear - Relationship end year
 * @returns {boolean} True if within range
 */
function isWithinYearRange(eventYear, startYear, endYear) {
  if (!eventYear) return true; // No year to check
  if (startYear && eventYear < startYear) return false;
  if (endYear && eventYear > endYear) return false;
  return true;
}

/**
 * Normalize a person name for matching.
 * Handles parentheticals, initials, and special characters.
 * @param {string} name - Full person name
 * @returns {Object|null} Normalized name components
 */
export function normalizePersonName(name) {
  if (!name || typeof name !== "string") return null;

  let normalized = name.trim();

  // Normalize all hyphen variants to standard ASCII hyphen
  // This handles: non-breaking hyphen (‑), en-dash (–), em-dash (—), hyphen (‐), minus sign (−)
  normalized = normalized.replace(
    /[\u2010\u2011\u2012\u2013\u2014\u2212]/g,
    "-"
  );

  // Extract maiden name if present: "Ingrid Otto (née Smolla)" → maidenName = "Smolla"
  // Also handles: "née", "born", "geborene", "geb."
  let maidenName = null;
  const maidenMatch = normalized.match(
    /\(\s*(?:née|nee|born|geborene|geb\.?)\s+([^)]+)\)/i
  );
  if (maidenMatch) {
    maidenName = maidenMatch[1].trim();
  }

  // Remove parenthetical clarifications: "Ethel Sara Turing (née Stoney)" → "Ethel Sara Turing"
  normalized = normalized.replace(/\s*\([^)]*\)/g, "");

  // Remove bracketed clarifications: "D. G. [David Gawen] Champernowne" → "D. G. Champernowne"
  normalized = normalized.replace(/\s*\[[^\]]*\]/g, "");

  // Remove comma-separated titles: "Henry II, Holy Roman Emperor" → "Henry II"
  // This handles titles that come after a comma
  normalized = normalized.replace(
    /,\s*(Holy Roman Emperor|Holy Roman Empress|King|Queen|Emperor|Empress|Duke|Duchess|Count|Countess|Prince|Princess|Bishop|Archbishop|Pope|Saint|Dr\.|Prof\.).*$/i,
    ""
  );

  // Remove suffixes like Jr., Sr. but NOT Roman numerals (II, III, IV, V, etc.) as they're part of regnal names
  normalized = normalized.replace(/\s+(Jr|Sr)\.?$/i, "");

  // Remove titles with geographic qualifiers: "Count of Luxembourg", "Duke of Bavaria", "Bishop of Metz"
  // Pattern: (Title) of (Place) - these are descriptive, not part of the actual name
  normalized = normalized.replace(
    /,?\s*(Count|Duke|Duchess|Bishop|Archbishop|King|Queen|Prince|Princess|Emperor|Empress|Lord|Lady|Earl|Baron|Baroness|Margrave|Landgrave|Elector)\s+of\s+[\w\s-]+$/i,
    ""
  );

  // Also handle "of Place" at the end for names like "Cunigunde of Luxembourg" → keep as is but don't use place as last name
  // We'll handle this by detecting the "of Place" pattern
  const ofPlaceMatch = normalized.match(/^(.+?)\s+of\s+([\w\s-]+)$/i);
  let isGeographicName = false;
  if (ofPlaceMatch) {
    // This is a name like "Cunigunde of Luxembourg" or "Henry of Bavaria"
    // The part after "of" is a place, not a surname
    isGeographicName = true;
  }

  // Split into tokens
  const tokens = normalized.split(/\s+/).filter((t) => t.length > 0);
  if (tokens.length === 0) return null;

  // Handle "von", "de", "van" etc. as part of last name (but NOT "of" which is geographic)
  const particleIndex = tokens.findIndex((t) =>
    ["von", "van", "de", "del", "della", "di"].includes(t.toLowerCase())
  );

  let lastName, firstNames;

  if (isGeographicName) {
    // For names like "Cunigunde of Luxembourg", use the first part as the name
    // Don't use the geographic part as the last name
    const nameBeforeOf = ofPlaceMatch[1];
    const nameTokens = nameBeforeOf.split(/\s+/).filter((t) => t.length > 0);
    if (nameTokens.length === 0) return null;
    lastName = nameTokens[nameTokens.length - 1];
    firstNames = nameTokens.slice(0, -1);
  } else if (particleIndex > -1 && particleIndex < tokens.length - 1) {
    // Include particle in last name
    lastName = tokens.slice(particleIndex).join(" ");
    firstNames = tokens.slice(0, particleIndex);
  } else {
    lastName = tokens[tokens.length - 1];
    firstNames = tokens.slice(0, -1);
  }

  const firstName = firstNames.length > 0 ? firstNames[0] : "";

  return {
    fullName: normalized,
    firstName: firstName,
    lastName: lastName,
    maidenName: maidenName,
    tokens: tokens.map((t) => t.toLowerCase()),
    originalName: name,
    isGeographicName: isGeographicName,
  };
}

/**
 * Calculate a similarity score between two normalized names.
 * Returns a score from 0 (no match) to 1 (exact match).
 * @param {Object} name1 - First normalized name
 * @param {Object} name2 - Second normalized name
 * @returns {number} Similarity score 0-1
 */
function calculateNameSimilarity(name1, name2) {
  if (!name1 || !name2) return 0;

  // Exact full name match = perfect score
  if (name1.fullName.toLowerCase() === name2.fullName.toLowerCase()) {
    return 1.0;
  }

  let score = 0;

  // Check for Roman numeral pattern
  const romanNumeralPattern = /^(I{1,3}|IV|V|VI{0,3}|IX|X|XI{0,3}|XIV|XV)$/i;

  // Check first name match
  const firstName1 = name1.firstName?.toLowerCase() || "";
  const firstName2 = name2.firstName?.toLowerCase() || "";
  const firstNamesMatch = firstName1 && firstName2 && firstName1 === firstName2;

  // Check last name match - but ignore if last name is a Roman numeral
  const lastName1 = name1.lastName?.toLowerCase() || "";
  const lastName2 = name2.lastName?.toLowerCase() || "";
  const lastName1IsNumeral = romanNumeralPattern.test(lastName1);
  const lastName2IsNumeral = romanNumeralPattern.test(lastName2);

  // Only count last name match if neither is a Roman numeral
  const lastNamesMatch =
    lastName1 &&
    lastName2 &&
    !lastName1IsNumeral &&
    !lastName2IsNumeral &&
    lastName1 === lastName2;

  // Check if last names are contained in each other (handles partial matches)
  // Also skip if either is a Roman numeral
  const lastNameContained =
    lastName1 &&
    lastName2 &&
    !lastName1IsNumeral &&
    !lastName2IsNumeral &&
    (lastName1.includes(lastName2) || lastName2.includes(lastName1));

  // Check for Roman numeral in either name (important for rulers)
  const hasRomanNumeral1 = name1.tokens?.some((t) =>
    romanNumeralPattern.test(t)
  );
  const hasRomanNumeral2 = name2.tokens?.some((t) =>
    romanNumeralPattern.test(t)
  );

  // If both have Roman numerals, they MUST match AND first names must also match
  if (hasRomanNumeral1 && hasRomanNumeral2) {
    const numeral1 = name1.tokens
      .find((t) => romanNumeralPattern.test(t))
      ?.toUpperCase();
    const numeral2 = name2.tokens
      .find((t) => romanNumeralPattern.test(t))
      ?.toUpperCase();
    if (numeral1 !== numeral2) {
      return 0; // Different rulers (e.g., Henry II vs Henry V), no match
    }
    // Same numeral but different first names = different person (e.g., Henry II vs Dietrich II)
    if (!firstNamesMatch) {
      return 0;
    }
    // Same numeral AND same first name = likely same person
    score += 0.5;
  }

  // First name match is important
  if (firstNamesMatch) {
    score += 0.4;
  }

  // Last name match (only for real surnames, not Roman numerals)
  if (lastNamesMatch) {
    score += 0.4;
  } else if (
    lastNameContained &&
    lastName1.length > 3 &&
    lastName2.length > 3
  ) {
    // Partial last name match (for married names, etc.)
    score += 0.2;
  }

  // Check if one full name contains the other (handles titles being stripped)
  const full1 = name1.fullName.toLowerCase();
  const full2 = name2.fullName.toLowerCase();
  if (full1.includes(full2) || full2.includes(full1)) {
    score += 0.2;
  }

  // Check maiden name matching (for married women)
  // E.g., "Ingrid Smolla" should match "Ingrid Otto (née Smolla)"
  const maiden1 = name1.maidenName?.toLowerCase();
  const maiden2 = name2.maidenName?.toLowerCase();

  if (firstNamesMatch) {
    // If first names match, check if one's last name matches the other's maiden name
    if (maiden1 && lastName2 === maiden1) {
      score += 0.4; // "Ingrid Smolla" matches "Ingrid Otto (née Smolla)"
    } else if (maiden2 && lastName1 === maiden2) {
      score += 0.4; // Same, other direction
    }
  }

  // Cap at 0.95 for non-exact matches
  return Math.min(score, 0.95);
}

/**
 * Get people relevant to an event from the ego network.
 * Uses a scoring-based approach for matching involved_people to network connections.
 * @param {Object} event - Event object
 * @param {Object} egoNetwork - Ego network with connections array
 * @returns {Array} Relevant connections (max 5)
 */
export function getRelevantPeople(event, egoNetwork) {
  if (!egoNetwork?.connections || !Array.isArray(egoNetwork.connections)) {
    return [];
  }

  const parsedYear = extractYear(event?.date);
  const eventYear = Number.isNaN(parsedYear) ? null : parsedYear;
  const connections = egoNetwork.connections;

  // PHASE 1: Use involved_people field if present
  if (
    event.involved_people &&
    Array.isArray(event.involved_people) &&
    event.involved_people.length > 0
  ) {
    // Normalize all involved people names
    const involvedNormalized = event.involved_people
      .map((name) => normalizePersonName(name))
      .filter(Boolean);

    const matched = connections.filter((conn) => {
      const connNormalized = normalizePersonName(conn.person_name);
      if (!connNormalized) return false;

      // Find the best similarity score against any involved person
      const bestScore = Math.max(
        ...involvedNormalized.map((involved) =>
          calculateNameSimilarity(involved, connNormalized)
        )
      );

      if (bestScore < MATCH_THRESHOLD) return false;

      // Still apply year-range filtering
      return isWithinYearRange(eventYear, conn.start_year, conn.end_year);
    });

    return matched.slice(0, 5);
  }

  // PHASE 2: Fall back to who is actually named in the event text. This is the
  // same matcher that highlights the names, so the people offered as chips and
  // the names emphasized in the description cannot disagree.
  const eventText = `${event?.title ?? ""} ${event?.description ?? ""}`;
  const mentioned = new Set(
    findPersonMentions(eventText, connections).map((match) => match.person)
  );

  const strengthOrder = { strong: 0, moderate: 1, weak: 2 };
  return connections
    .filter(
      (connection) =>
        mentioned.has(connection) &&
        isWithinYearRange(eventYear, connection.start_year, connection.end_year)
    )
    .sort(
      (a, b) =>
        (strengthOrder[a.strength] ?? 3) - (strengthOrder[b.strength] ?? 3)
    )
    .slice(0, 5);
}

/** Characters that make a neighbor part of the same word. */
const WORD_CHARACTER = /[\p{L}\p{N}]/u;

/**
 * Escape a literal string for use inside a regular expression.
 * @param {string} value - Literal text
 * @returns {string} Pattern source matching that text
 */
function escapeForRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Locate an annotated term in prose that carries no `[[…]]` markup for it.
 *
 * The generator is asked to define an annotation *and* mark its term in the
 * description, and it regularly does only the first — across the current data
 * roughly one annotation in nine is defined but never marked, so its
 * explanation is written, translated, and then never shown. The terms this
 * strands are mostly institutions ("Glasgow School of Art", "Risø",
 * "Cercle Artístic de Sant Lluc"), which is what the reader notices: the very
 * names that need a gloss are the ones without one.
 *
 * Finding the term in the text is the same move the app already makes for
 * people, whose names are matched in the prose rather than marked up in it.
 * The markup therefore stops being the only way to place an annotation and
 * becomes what it is actually needed for: annotating a phrase whose wording
 * differs from the term (`[[Modernisme|the modernista style]]`).
 *
 * @param {string} description - Prose to scan
 * @param {string} termKey - Annotation key, as prose or as a slug
 * @param {Array<{start: number, end: number}>} occupied - Ranges already taken
 * @returns {{start: number, end: number}|null} First free whole-word match
 */
function findAnnotationTerm(description, termKey, occupied) {
  // Keys come both as prose ("Glasgow School of Art") and as slugs
  // ("Greek_War_of_Independence"); both stand for the same words.
  const spelled = termKey.replace(/_/g, " ");
  // A key names a place in full where the sentence names it plainly
  // ("Portland, Oregon" for "moved from Portland"), so the qualifier behind
  // the comma is dropped — but only after the full key has failed to match.
  const unqualified = spelled.replace(/,[^,]*$/, "");
  const candidates = [termKey, spelled, unqualified];

  for (const candidate of candidates) {
    const term = candidate.trim();
    if (!term) continue;

    // Case-insensitive: a term is keyed as the concept ("photoelectric_effect")
    // as often as it is spelled the way the sentence spells it.
    const pattern = new RegExp(escapeForRegExp(term), "giu");
    let match;
    while ((match = pattern.exec(description)) !== null) {
      const start = match.index;
      const end = pattern.lastIndex;
      const before = description[start - 1];
      const after = description[end];
      if (before && WORD_CHARACTER.test(before)) continue;
      if (after && WORD_CHARACTER.test(after)) continue;
      if (occupied.some((range) => start < range.end && range.start < end)) {
        continue;
      }
      return { start, end };
    }
  }

  return null;
}

/**
 * Parse event description into segments with annotations AND person names.
 * Annotations take priority over person name matches.
 * @param {string} description - Event description text
 * @param {Object} annotations - Annotation dictionary
 * @param {Array} relevantPeople - Array of connection objects
 * @param {string} [subjectName] - The story's own subject. Family shares
 *   surnames, so without them a bare "Hamilton" in Alexander Hamilton's story
 *   is handed to his father. Matching the subject too lets the shared surname
 *   come out ambiguous — and therefore plain — while "James Hamilton" still
 *   resolves to the father.
 * @returns {Array} Segments: {type: 'text'|'annotation'|'person', ...}
 */
export function parseDescriptionSegments(
  description,
  annotations = {},
  relevantPeople = [],
  subjectName = null
) {
  if (!description) return [];

  // Step 1: Parse annotations first (they take priority)
  const annotationPattern = /\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g;
  const annotationRanges = [];
  const seenTermKeys = new Set(); // Track which terms we've already annotated
  let match;

  while ((match = annotationPattern.exec(description)) !== null) {
    const termKey = match[1];
    const displayText = match[2] || match[1];
    const annotation = annotations[termKey];

    // Track this range regardless of whether annotation exists
    // If annotation exists AND we haven't seen this term before, mark it as an annotation
    // Otherwise, mark it as plain text (to strip the markup)
    if (annotation && !seenTermKeys.has(termKey)) {
      seenTermKeys.add(termKey); // Mark this term as used
      annotationRanges.push({
        start: match.index,
        end: annotationPattern.lastIndex,
        type: "annotation",
        termKey,
        displayText,
        annotation,
      });
    } else {
      // Annotation markup exists but no annotation definition, or duplicate
      // Add as a plain text replacement (strip the markup, keep display text)
      annotationRanges.push({
        start: match.index,
        end: annotationPattern.lastIndex,
        type: "unresolved-annotation",
        displayText,
      });
    }
  }

  // Step 2: Find person name matches, skipping anything the annotation
  // markup already claims (annotations win, and their `[[term|display]]`
  // syntax would otherwise be highlighted mid-marker).
  const subject = subjectName
    ? { person_name: subjectName, isSubject: true }
    : null;
  const personMatches = findPersonMentions(
    description,
    subject ? [...relevantPeople, subject] : relevantPeople,
    { exclude: annotationRanges }
  )
    // The subject is only in the list to compete for their own name; their
    // mentions stay plain text (this is their story — nothing to link to).
    .filter((match) => !match.person.isSubject)
    .map((match) => ({
      start: match.start,
      end: match.end,
      type: "person",
      person: match.person,
      matchedText: description.slice(match.start, match.end),
    }));

  // Step 2b: An annotation the description never marked up is still an
  // annotation — find its term in the prose (see findAnnotationTerm). Names are
  // settled first and an emphasized one is off limits: the generator is told
  // never to annotate a person, and where it did anyway ("Lord Byron" in Ada
  // Lovelace's birth) the person's card is the richer answer. The subject's own
  // name is not a match to protect — it renders as plain text — so a term that
  // merely contains it ("Zuse KG") is still free. Explicit markup keeps its
  // precedence, having been written into the sentence on purpose.
  for (const [termKey, annotation] of Object.entries(annotations ?? {})) {
    if (seenTermKeys.has(termKey) || !annotation) continue;
    const range = findAnnotationTerm(description, termKey, [
      ...annotationRanges,
      ...personMatches,
    ]);
    if (!range) continue;
    seenTermKeys.add(termKey);
    annotationRanges.push({
      start: range.start,
      end: range.end,
      type: "annotation",
      termKey,
      // The prose spells the term the way the sentence needed it; that is what
      // the reader tapped, so that is what the popup labels.
      displayText: description.slice(range.start, range.end),
      annotation,
    });
  }

  // Step 3: Merge all ranges and sort by position
  const allRanges = [...annotationRanges, ...personMatches].sort((a, b) => {
    if (a.start !== b.start) return a.start - b.start;
    // If same start, annotations win
    if (a.type === "annotation") return -1;
    if (b.type === "annotation") return 1;
    return 0;
  });

  // Step 4: Remove overlapping person matches
  const filteredRanges = [];
  let lastEnd = 0;

  for (const range of allRanges) {
    if (range.start >= lastEnd) {
      filteredRanges.push(range);
      lastEnd = range.end;
    }
    // Skip overlapping ranges
  }

  // Step 5: Build final segment array
  const segments = [];
  let currentPos = 0;

  for (const range of filteredRanges) {
    // Add text before this range
    if (range.start > currentPos) {
      segments.push({
        type: "text",
        content: description.slice(currentPos, range.start),
      });
    }

    // Add the range itself
    if (range.type === "annotation") {
      segments.push({
        type: "annotation",
        termKey: range.termKey,
        displayText: range.displayText,
        annotation: range.annotation,
      });
    } else if (range.type === "unresolved-annotation") {
      // Unresolved annotation: just add the display text as plain text
      segments.push({
        type: "text",
        content: range.displayText,
      });
    } else if (range.type === "person") {
      segments.push({
        type: "person",
        content: range.matchedText,
        person: range.person,
      });
    }

    currentPos = range.end;
  }

  // Add remaining text
  if (currentPos < description.length) {
    segments.push({
      type: "text",
      content: description.slice(currentPos),
    });
  }

  return segments;
}

/**
 * Find a person in the ego network by name using fuzzy matching.
 * Uses multiple fallback strategies for robust matching.
 * @param {string} personName - Name to search for
 * @param {Object} egoNetwork - Ego network with connections array
 * @returns {Object|null} Matching connection object or null
 */
export function findPersonInNetwork(personName, egoNetwork) {
  if (!egoNetwork?.connections || !personName) return null;

  const connections = egoNetwork.connections;
  const searchNormalized = normalizePersonName(personName);
  if (!searchNormalized) return null;

  // Find best match by similarity score
  let bestMatch = null;
  let bestScore = 0;

  for (const conn of connections) {
    const connNormalized = normalizePersonName(conn.person_name);
    if (!connNormalized) continue;

    const score = calculateNameSimilarity(searchNormalized, connNormalized);
    if (score >= MATCH_THRESHOLD && score > bestScore) {
      bestScore = score;
      bestMatch = conn;
    }
  }

  return bestMatch;
}

/**
 * Get chapter people from involved_people list, matched against ego network.
 * Only returns people found in the network with fuzzy matching.
 * Filters to only show people with "strong" connections.
 * @param {Object} chapter - Chapter object with involved_people array
 * @param {Object} egoNetwork - Ego network with connections
 * @returns {Array} Array of matched connection objects with metadata
 */
export function getChapterPeople(chapter, egoNetwork) {
  if (!chapter?.involved_people || !Array.isArray(chapter.involved_people)) {
    return [];
  }

  // Only return people that can be matched to the ego network with strong connections
  const matchedPeople = chapter.involved_people
    .map((name, idx) => {
      const networkPerson = findPersonInNetwork(name, egoNetwork);
      if (networkPerson && networkPerson.strength === "strong") {
        return {
          ...networkPerson,
          _originalName: name,
          _index: idx,
        };
      }
      return null;
    })
    .filter(Boolean);

  // Deduplicate by person_name (in case multiple variations match same network person)
  const seen = new Map();
  return matchedPeople.filter((person) => {
    const key = person.person_name;
    if (seen.has(key)) {
      return false;
    }
    seen.set(key, true);
    return true;
  });
}

/**
 * Check if an event is a migration event.
 * @param {Object} event - Event object
 * @returns {boolean} True if event has migration class
 */
export function isMigrationEvent(event) {
  return event?.event_class?.type === "migration";
}

/**
 * Check if an event is the subject's own birth.
 * @param {Object} event - Event object
 * @returns {boolean} True if event has birth class
 */
export function isBirthEvent(event) {
  return event?.event_class?.type === "birth";
}

/**
 * Canonical family role of a relationship token: lowercased, hyphenated, with
 * step/half/adoptive/foster prefixes and "-by-marriage" suffixes stripped
 * ("family/step_father" -> "father"). Returns null without a subcategory.
 * @param {string} relationshipType - e.g. "family/mother"
 * @returns {string|null} Canonical role
 */
export function normalizeFamilyRole(relationshipType) {
  const subcategory = getSubcategory(relationshipType);
  if (!subcategory) return null;
  return subcategory
    .toLowerCase()
    .replace(/[\s_]+/g, "-")
    .replace(/-by-marriage$/, "")
    .replace(/^(step|half|adoptive|adopted|biological|foster)-?/, "");
}

const PARENT_ROLES = ["father", "mother"];

// Some datasets record a parent the sources never name ("Unnamed mother of
// …"). That is a placeholder rather than a name, and a chip carrying it says
// less than no chip at all.
const PLACEHOLDER_NAME = /^\s*(unnamed|unknown|unidentified)\b/i;

/**
 * The parents to show on a birth slide, father first.
 *
 * The classification names them — Phase 1 reads the article — and the ego
 * network supplies the metadata behind each chip whenever it knows that
 * person, so a parent here behaves exactly like a parent in the network view.
 * When the classification names nobody, the parents are read from the network
 * itself, which is the same place the network view reads them from.
 * @param {Object} event - Event object
 * @param {Object} egoNetwork - Ego network with connections array
 * @returns {Array} Connection-shaped objects for the parents
 */
export function getBirthParents(event, egoNetwork) {
  if (!isBirthEvent(event)) return [];

  const named = [];
  for (const role of PARENT_ROLES) {
    const name = event.event_class[role];
    if (!name || PLACEHOLDER_NAME.test(name)) continue;
    named.push(
      findPersonInNetwork(name, egoNetwork) ?? {
        person_name: name,
        relationship_type: `family/${role}`,
        relationship_description: "",
      }
    );
  }
  if (named.length > 0) return named;

  const connections = egoNetwork?.connections ?? [];
  return PARENT_ROLES.map((role) =>
    connections.find(
      (connection) =>
        (connection.relationship_type || "").split("/")[0] === "family" &&
        normalizeFamilyRole(connection.relationship_type) === role &&
        !PLACEHOLDER_NAME.test(connection.person_name || "")
    )
  ).filter(Boolean);
}

/**
 * Extract migration path coordinates from an event.
 * Returns from/to coordinates if event is a migration with multiple locations.
 * @param {Object} event - Event object
 * @returns {Object|null} {from: {lon, lat}, to: {lon, lat}} or null
 */
export function getMigrationPath(event) {
  if (!isMigrationEvent(event)) {
    return null;
  }

  const locations = normalizeAllLocations(event);
  if (locations.length < 2) {
    return null;
  }

  // For migration events, assume first location is "from" and last is "to"
  // (or use primary flag to determine destination)
  const toLocation =
    locations.find((loc) => loc.primary) || locations[locations.length - 1];
  const fromLocation = locations.find((loc) => !loc.primary) || locations[0];

  if (!fromLocation || !toLocation || fromLocation === toLocation) {
    return null;
  }

  return {
    from: { lon: fromLocation.lon, lat: fromLocation.lat },
    to: { lon: toLocation.lon, lat: toLocation.lat },
  };
}

/**
 * Create date formatters for a specific language.
 *
 * Dates are stored as UTC midnight, so the formatters read them in UTC too —
 * otherwise every date would slip to the previous day west of Greenwich.
 *
 * The `beforeCommonEra` set names the era explicitly, which `dateStyle` cannot
 * do; `formatSingleDate` reaches for it when the year is not in the common era.
 *
 * @param {string} language - Language code like "en" or "de"
 * @returns {Object} Formatters for day, month, year, plus a B.C. variant
 */
export function createDateFormatters(language) {
  return {
    day: new Intl.DateTimeFormat(language, {
      dateStyle: "long",
      timeZone: "UTC",
    }),
    month: new Intl.DateTimeFormat(language, {
      year: "numeric",
      month: "long",
      timeZone: "UTC",
    }),
    year: new Intl.DateTimeFormat(language, {
      year: "numeric",
      timeZone: "UTC",
    }),
    beforeCommonEra: {
      day: new Intl.DateTimeFormat(language, {
        year: "numeric",
        month: "long",
        day: "numeric",
        era: "short",
        timeZone: "UTC",
      }),
      month: new Intl.DateTimeFormat(language, {
        year: "numeric",
        month: "long",
        era: "short",
        timeZone: "UTC",
      }),
      year: new Intl.DateTimeFormat(language, {
        year: "numeric",
        era: "short",
        timeZone: "UTC",
      }),
    },
  };
}

/* ------------------------------------------------------------------ *
 * Event weight and the depth layer
 * ------------------------------------------------------------------ */

// Icons that name a kind of event a life is remembered for — a work, a
// discovery, an honor. The datasets classify only five kinds of event in
// `event_class`, and a landmark often falls outside all of them (Turing's two
// famous papers carry no classification at all), so the icon is the one
// vocabulary that separates "published the paper" from "took up a post". Kinds
// that recur in every academic life — schooling, degrees, appointments — are
// deliberately absent: they say what happened, not that it mattered.
const MILESTONE_ICONS = new Set([
  "mdi-book",
  "mdi-book-open-variant",
  "mdi-file-document",
  "mdi-file-document-edit",
  "mdi-newspaper",
  "mdi-lightbulb-on-outline",
  "mdi-microscope",
  "mdi-test-tube",
  "mdi-palette",
  "mdi-drawing",
  "mdi-cube",
  "mdi-music-note",
  "mdi-medal",
  "mdi-trophy",
  "mdi-crown",
  "mdi-shield-crown",
  "mdi-star",
  "mdi-seal",
  "mdi-gavel",
  "mdi-office-building",
  "mdi-castle",
]);

// The classifications, by how much of a life they turn on.
const CLASS_WEIGHTS = {
  birth: 0.3,
  death: 0.3,
  invention: 0.3,
  publication: 0.3,
  marriage_partnership: 0.25,
  migration: 0.15,
};

/**
 * How much of a life an event turns on, on a 0–1 scale.
 *
 * The datasets carry the number: Phase 1 proposes a life's events and weighs
 * them against each other in the same call, which is the only place in the
 * pipeline that sees them all at once. That is what makes the judgment
 * possible at all — weight here is comparative, not absolute.
 *
 * What follows is the fallback for a dataset generated before the field
 * existed, and it is a weaker thing: it reads the traces an important event
 * leaves behind — a classification, a milestone icon, a picture, annotations,
 * people, length — which is to say it reads the documentation rather than the
 * life. It ranks a well-attended ceremony above a quiet paper that founded a
 * field. Backfilling the weights is what fixes that; see
 * `scripts/backfill_event_weights.py`.
 * @param {Object} event - Event object
 * @returns {number} Weight between 0 and 1
 */
export function getEventWeight(event) {
  if (!event) return 0;

  if (Number.isFinite(event.weight)) {
    return Math.min(Math.max(event.weight, 0), 1);
  }

  let weight = 0;

  const classWeight = CLASS_WEIGHTS[event.event_class?.type];
  if (classWeight) {
    weight += classWeight;
  } else if (MILESTONE_ICONS.has(event.event_type_icon)) {
    // A classification already says the event is one of the recognized kinds;
    // the icon is what is left to go on when it does not.
    weight += 0.2;
  }

  const annotationCount = Object.keys(event.annotations ?? {}).length;
  weight += Math.min(annotationCount, 3) * 0.08;

  if (getValidImages(event.images).length > 0) weight += 0.12;

  const peopleCount = Array.isArray(event.involved_people)
    ? event.involved_people.length
    : 0;
  weight += Math.min(peopleCount, 3) * 0.05;

  const sourceCount = Array.isArray(event.sources) ? event.sources.length : 0;
  weight += Math.min(Math.max(sourceCount - 1, 0), 2) * 0.05;

  const length =
    typeof event.description === "string" ? event.description.length : 0;
  if (length >= 380) weight += 0.1;
  else if (length >= 300) weight += 0.05;

  // An event the sources place across a span, rather than on a day, tends to
  // be one they treat as an episode.
  if (event.date_end) weight += 0.05;

  return Math.min(weight, 1);
}

/**
 * The material a depth layer would have to show for one event: the place under
 * both its names, the terms its description leans on, the pictures with their
 * credits, the people who were there, and where all of it was read.
 *
 * Every part of this is already in the dataset. What the fold shows of it is a
 * tap away at most — an annotation behind its term, a credit behind the
 * lightbox — and the place and the sources are not on the slide at all.
 * @param {Object} event - Event object
 * @param {Object} egoNetwork - Ego network with connections array
 * @returns {Object} {background, places, terms, images, people, sources, itemCount, sectionCount}
 */
export function getEventDepth(event, egoNetwork) {
  const places = Array.isArray(event?.locations)
    ? event.locations
        .filter((location) => location?.name_historic || location?.name_modern)
        .map((location) => ({
          historic: location.name_historic ?? null,
          modern: location.name_modern ?? null,
          primary: location.primary === true,
        }))
    : [];

  const terms = Object.entries(event?.annotations ?? {})
    .filter(([, annotation]) => !!annotation?.explanation)
    .map(([term, annotation]) => ({
      term,
      explanation: annotation.explanation,
      wikipediaUrl: annotation.wikipedia_url ?? null,
    }));

  const images = getValidImages(event?.images)
    .map((imageData) =>
      typeof imageData === "string" ? { url: imageData } : imageData
    )
    .filter((image) => image.caption || image.creator || image.source);

  const people = getRelevantPeople(event, egoNetwork);

  const sources = Array.isArray(event?.sources)
    ? event.sources.filter((url) => typeof url === "string" && url.length > 0)
    : [];

  // The passage Phase 2 wrote for this event, where there is one. It is
  // deliberately left out of the counts below: those decide which events offer
  // a depth layer at all, the passages are generated for the events that do,
  // and letting one feed the other would make the selection drift as the
  // corpus fills in.
  const background =
    typeof event?.background === "string" ? event.background : null;
  const illustrations = getBackgroundImages(event);

  const sections = [places, terms, images, people, sources];
  return {
    background,
    illustrations,
    places,
    terms,
    images,
    people,
    sources,
    itemCount: sections.reduce((total, section) => total + section.length, 0),
    sectionCount: sections.filter((section) => section.length > 0).length,
  };
}

// A weight below this is not a highlight in any life, however its neighbors
// score. Without a floor a thin chapter would still nominate its best event.
export const DEEP_EVENT_FLOOR = 0.35;

// Below this there is not enough behind the fold to be worth the trip down.
const MIN_DEPTH_SECTIONS = 2;
const MIN_DEPTH_ITEMS = 3;

/**
 * Which events of one life open a depth layer.
 *
 * Weight alone would cluster the highlights wherever a life is best
 * documented, so the selection is made per chapter: each chapter offers its
 * heaviest event and no more, which spreads the deep slides across the story
 * the way a comic spreads its big panels across a chapter. An event that has
 * too little behind the fold is passed over for the next one down, and a
 * chapter whose best event never clears the floor simply offers none.
 * @param {Array} events - Event objects in story order
 * @param {Object} egoNetwork - Ego network with connections array
 * @returns {Set<number>} Indexes into `events`
 */
export function selectDeepEventIndexes(events, egoNetwork) {
  if (!Array.isArray(events) || events.length === 0) return new Set();

  const candidates = events
    .map((event, index) => ({
      index,
      chapter: event?.chapter ?? "",
      weight: getEventWeight(event),
      depth: getEventDepth(event, egoNetwork),
    }))
    .filter(
      (candidate) =>
        candidate.weight >= DEEP_EVENT_FLOOR &&
        candidate.depth.sectionCount >= MIN_DEPTH_SECTIONS &&
        candidate.depth.itemCount >= MIN_DEPTH_ITEMS
    );

  const best = new Map();
  for (const candidate of candidates) {
    const held = best.get(candidate.chapter);
    // Ties go to the earlier event: a chapter's first landmark is the one the
    // reader meets while the chapter is still being established.
    if (!held || candidate.weight > held.weight) {
      best.set(candidate.chapter, candidate);
    }
  }

  return new Set([...best.values()].map((candidate) => candidate.index));
}

/**
 * Whether an event actually has a layer to open.
 *
 * `selectDeepEventIndexes` picks the events a layer is *worth* writing for,
 * which is what the backfill script asks it for. The reader's question is a
 * different one: the layer is the generated report and nothing else, so an
 * event whose report has not been written yet must not advertise a second
 * screen and then show an empty one. A corpus fills in one life at a time, and
 * the invitation down appears exactly where there is something down there.
 * @param {Object} event - Event object
 * @returns {boolean}
 */
export function hasBackgroundReport(event) {
  return (
    typeof event?.background === "string" && event.background.trim() !== ""
  );
}

/**
 * The pictures the depth layer shows: the ones searched for the background
 * report, and nothing else.
 *
 * The report's illustrations are searched against the report — the machine,
 * the building, the document it describes — so they show the reader something
 * the slide above did not. The event's own picture is deliberately not a
 * fallback: it is a screen up, the reader has just scrolled past it, and
 * reprinting it under the report is what made the layer look like a second
 * copy of the slide. A report with no illustrations is set as plain prose.
 * @param {Object} event - Event object
 * @returns {Array} Image objects with url and, where known, caption and credit
 */
export function getBackgroundImages(event) {
  return Array.isArray(event?.background_images)
    ? event.background_images.filter((image) => image?.url)
    : [];
}
