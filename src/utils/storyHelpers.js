/**
 * Story-specific utility functions for date formatting, event processing, and map helpers.
 */

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
 * Convert an event to a sortable timestamp.
 * @param {Object} event - Event object with date and date_precision
 * @returns {number} Timestamp in milliseconds, or Infinity if no date
 */
export function toTimestamp(event) {
  if (!event?.date) return Number.POSITIVE_INFINITY;
  const precision = event.date_precision ?? "day";
  const iso =
    precision === "year"
      ? `${event.date}-01-01T00:00:00Z`
      : precision === "month"
        ? `${event.date}-01T00:00:00Z`
        : `${event.date}T00:00:00Z`;
  return Date.parse(iso);
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
  const normalizedPrecision = precision ?? "day";
  const formatter = formatters[normalizedPrecision] ?? formatters.day;
  const iso =
    normalizedPrecision === "year"
      ? `${value}-01-01T00:00:00Z`
      : normalizedPrecision === "month"
        ? `${value}-01T00:00:00Z`
        : `${value}T00:00:00Z`;
  const timestamp = Date.parse(iso);
  if (Number.isNaN(timestamp)) return null;
  return formatter.format(new Date(timestamp));
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
 * Get the date note from an event.
 * @param {Object} event - Event object
 * @returns {string|null} Date note or null
 */
export function getDateNote(event) {
  const note = event?.date_note;
  return typeof note === "string" && note.trim() ? note.trim() : null;
}

/**
 * Compute birth-death years label for a person.
 * @param {Object} person - Person object with birth_date and death_date
 * @returns {string} Years label like "1879 - 1955" or "1879"
 */
export function computeYearsLabel(person) {
  if (!person) return "";
  const { birth_date: birth, death_date: death } = person;
  const birthYear = birth ? new Date(birth).getFullYear() : NaN;
  const deathYear = death ? new Date(death).getFullYear() : NaN;
  if (!Number.isNaN(birthYear) && !Number.isNaN(deathYear)) {
    return `${birthYear} - ${deathYear}`;
  }
  return Number.isNaN(birthYear) ? "" : `${birthYear}`;
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
        return portrait.thumbnail;
      } else if (width <= 400 && portrait.medium) {
        return portrait.medium;
      } else if (portrait.full) {
        return portrait.full;
      }
      // Fallback to any available size
      return portrait.thumbnail || portrait.medium || portrait.full;
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

  return imageUrl;
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
function escapeRegex(str) {
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
 * Words too common to use for last-name-only matching.
 * Prevents false positives like "Church", "Grace", "Newton".
 */
const COMMON_WORDS = new Set([
  "church",
  "grace",
  "hope",
  "faith",
  "love",
  "king",
  "queen",
  "prince",
  "lord",
  "duke",
  "white",
  "black",
  "green",
  "brown",
  "young",
  "old",
  "good",
  "new",
  "long",
  "short",
  "stone",
  "wood",
  "hill",
  "field",
  "well",
  "strong",
  "bright",
  "rich",
  "poor",
]);

/**
 * Check if a word is too common to use for last-name-only matching.
 * @param {string} word - Word to check
 * @returns {boolean} True if common word
 */
function isCommonWord(word) {
  return COMMON_WORDS.has(word.toLowerCase());
}

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
 * Generate all plausible variants of a person name for matching.
 * @param {string} name - Full person name
 * @returns {Array} Variant objects with priority scores
 */
export function generateNameVariants(name) {
  const normalized = normalizePersonName(name);
  if (!normalized) return [];

  const variants = [];

  // Variant 1: Full name (highest priority)
  variants.push({
    text: normalized.fullName,
    regex: new RegExp(`\\b${escapeRegex(normalized.fullName)}\\b`, "gi"),
    type: "full",
    priority: 1,
  });

  // Variant 2: Last name only (medium priority, requires caution)
  // Only if last name is distinctive (>4 chars, not a common word)
  // Skip for geographic names where the "last name" is really the only name (e.g., "Cunigunde" from "Cunigunde of Luxembourg")
  // For geographic names, the lastName IS the firstName, so skip last-name-only variant
  if (
    normalized.lastName.length > 4 &&
    !isCommonWord(normalized.lastName) &&
    !normalized.isGeographicName &&
    normalized.firstName
  ) {
    // Must have a distinct first name
    variants.push({
      text: normalized.lastName,
      regex: new RegExp(`\\b${escapeRegex(normalized.lastName)}\\b`, "gi"),
      type: "last",
      priority: 2,
    });
  }

  // Variant 3: First + Last (in case middle names/initials differ)
  if (
    normalized.firstName &&
    normalized.tokens.length > 2 &&
    !normalized.isGeographicName
  ) {
    const firstLast = `${normalized.firstName} ${normalized.lastName}`;
    variants.push({
      text: firstLast,
      regex: new RegExp(`\\b${escapeRegex(firstLast)}\\b`, "gi"),
      type: "first_last",
      priority: 1,
    });
  }

  // Variant 4: First name only (lowest priority, for rulers/single-name persons)
  // Only if first name is distinctive enough (>4 chars, not too common)
  // This helps match "Henry" in text when the person is "Henry II"
  if (
    normalized.firstName &&
    normalized.firstName.length > 4 &&
    !isCommonWord(normalized.firstName)
  ) {
    variants.push({
      text: normalized.firstName,
      regex: new RegExp(`\\b${escapeRegex(normalized.firstName)}\\b`, "gi"),
      type: "first",
      priority: 3,
    });
  }

  // Variant 5: First name + maiden name (for married women)
  // E.g., "Ingrid Otto (née Smolla)" → also match "Ingrid Smolla"
  if (normalized.maidenName && normalized.firstName) {
    const firstMaiden = `${normalized.firstName} ${normalized.maidenName}`;
    variants.push({
      text: firstMaiden,
      regex: new RegExp(`\\b${escapeRegex(firstMaiden)}\\b`, "gi"),
      type: "maiden",
      priority: 1,
    });
  }

  // Sort by priority (lower number = higher priority)
  return variants.sort((a, b) => a.priority - b.priority);
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

  const eventYear = event?.date ? parseInt(event.date.substring(0, 4)) : null;
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

  // PHASE 2: Fallback to smart text matching
  const eventText =
    `${event?.title ?? ""} ${event?.description ?? ""}`.toLowerCase();

  // Check if multiple people share the same last name (ambiguity detection)
  const lastNameCounts = new Map();
  for (const conn of connections) {
    const normalized = normalizePersonName(conn.person_name);
    if (normalized) {
      const count = lastNameCounts.get(normalized.lastName) || 0;
      lastNameCounts.set(normalized.lastName, count + 1);
    }
  }

  const matchedConnections = connections
    .map((connection) => {
      const normalized = normalizePersonName(connection.person_name);
      const variants = generateNameVariants(connection.person_name);

      // If multiple people share this last name, skip last-name-only variants to avoid ambiguity
      const hasAmbiguousLastName =
        normalized && lastNameCounts.get(normalized.lastName) > 1;

      // Try to find best match
      for (const variant of variants) {
        // Skip last-name-only matches if ambiguous
        if (hasAmbiguousLastName && variant.type === "last") {
          continue;
        }

        if (variant.regex.test(eventText)) {
          return {
            connection,
            matchType: variant.type,
            priority: variant.priority,
          };
        }
      }
      return null;
    })
    .filter((match) => {
      if (!match) return false;

      // Year range check
      const conn = match.connection;
      return isWithinYearRange(eventYear, conn.start_year, conn.end_year);
    })
    .sort((a, b) => {
      // Sort by match quality (full name > last name)
      if (a.priority !== b.priority) return a.priority - b.priority;

      // Then by relationship strength
      const strengthOrder = { strong: 0, moderate: 1, weak: 2 };
      return (
        (strengthOrder[a.connection.strength] || 3) -
        (strengthOrder[b.connection.strength] || 3)
      );
    })
    .slice(0, 5)
    .map((match) => match.connection);

  return matchedConnections;
}

/**
 * Parse event description into segments with annotations AND person names.
 * Annotations take priority over person name matches.
 * @param {string} description - Event description text
 * @param {Object} annotations - Annotation dictionary
 * @param {Array} relevantPeople - Array of connection objects
 * @returns {Array} Segments: {type: 'text'|'annotation'|'person', ...}
 */
export function parseDescriptionSegments(
  description,
  annotations = {},
  relevantPeople = []
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

  // Step 2: Find person name matches
  // We only want ONE match per person - the best one (longest/highest priority)
  const personMatches = [];

  // Check if multiple people share the same last name (ambiguity detection)
  const lastNameCounts = new Map();
  for (const person of relevantPeople) {
    const normalized = normalizePersonName(person.person_name);
    if (normalized) {
      const count = lastNameCounts.get(normalized.lastName) || 0;
      lastNameCounts.set(normalized.lastName, count + 1);
    }
  }

  for (const person of relevantPeople) {
    const normalized = normalizePersonName(person.person_name);
    const variants = generateNameVariants(person.person_name);

    // If multiple people share this last name, skip last-name-only variants to avoid ambiguity
    const hasAmbiguousLastName =
      normalized && lastNameCounts.get(normalized.lastName) > 1;

    // Find the best match for this person (we only want one)
    let bestMatch = null;

    for (const variant of variants) {
      // Skip last-name-only matches if ambiguous
      if (hasAmbiguousLastName && variant.type === "last") {
        continue;
      }

      let match;
      variant.regex.lastIndex = 0; // Reset regex

      while ((match = variant.regex.exec(description)) !== null) {
        const start = match.index;
        const end = variant.regex.lastIndex;

        // Check if this overlaps with an annotation
        const overlapsAnnotation = annotationRanges.some(
          (ann) =>
            (start >= ann.start && start < ann.end) ||
            (end > ann.start && end <= ann.end)
        );

        if (!overlapsAnnotation) {
          const candidate = {
            start,
            end,
            type: "person",
            person,
            matchedText: match[0],
            priority: variant.priority,
          };

          // Keep this match if it's better than the current best
          // Better = lower priority number (full name beats last name)
          // If same priority, prefer longer match
          if (
            !bestMatch ||
            candidate.priority < bestMatch.priority ||
            (candidate.priority === bestMatch.priority &&
              candidate.matchedText.length > bestMatch.matchedText.length)
          ) {
            bestMatch = candidate;
          }
        }
      }
    }

    // Add only the best match for this person
    if (bestMatch) {
      personMatches.push(bestMatch);
    }
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
 * @param {string} language - Language code like "en" or "de"
 * @returns {Object} Formatters for day, month, year
 */
export function createDateFormatters(language) {
  return {
    day: new Intl.DateTimeFormat(language, { dateStyle: "long" }),
    month: new Intl.DateTimeFormat(language, {
      year: "numeric",
      month: "long",
    }),
    year: new Intl.DateTimeFormat(language, { year: "numeric" }),
  };
}
