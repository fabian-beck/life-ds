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
  const startLabel = formatSingleDate(event.date, event.date_precision, formatters);
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
  const primary = event.locations.find(loc => loc?.primary === true) || event.locations[0];

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
 * @returns {Array} Array of {lon, lat, name} objects
 */
export function normalizeAllLocations(event) {
  if (!event?.locations || !Array.isArray(event.locations)) {
    return [];
  }

  return event.locations
    .filter(loc => Array.isArray(loc?.centroid) && loc.centroid.length === 2)
    .map(loc => {
      const [lng, lat] = loc.centroid.map(Number);
      return Number.isFinite(lng) && Number.isFinite(lat)
        ? { lon: lng, lat: lat, name: loc.name_historic }
        : null;
    })
    .filter(coord => coord !== null);
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
    } catch (error) {
      // ignore rule errors to avoid breaking icon rendering
    }
  }
  return mdiCircleSmall;
}

/**
 * Get Wikimedia Commons thumbnail URL at specified width.
 * @param {string} imageUrl - Original image URL
 * @param {number} width - Desired width in pixels
 * @returns {string} Thumbnail URL or original URL
 */
export function getThumbnailUrl(imageUrl, width = 400) {
  if (!imageUrl || typeof imageUrl !== "string") return imageUrl;

  // Optimize Wikimedia Commons images
  if (imageUrl.includes("upload.wikimedia.org/wikipedia/commons/")) {
    const parts = imageUrl.split("/wikipedia/commons/");
    if (parts.length === 2) {
      const [base, path] = parts;
      const filename = path.split("/").pop();
      return `${base}/wikipedia/commons/thumb/${path}/${width}px-${filename}`;
    }
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
  } catch (error) {
    return { label: url, isWikipedia: false };
  }
}

/**
 * Get the subcategory from a relationship type string.
 * @param {string} relationshipType - Relationship type like "family/spouse"
 * @returns {string|null} Subcategory or null
 */
export function getSubcategory(relationshipType) {
  return relationshipType?.includes("/") ? relationshipType.split("/")[1] : null;
}

/**
 * Get people relevant to an event from the ego network.
 * @param {Object} event - Event object
 * @param {Object} egoNetwork - Ego network with connections array
 * @returns {Array} Relevant connections (max 5)
 */
export function getRelevantPeople(event, egoNetwork) {
  if (!egoNetwork?.connections || !Array.isArray(egoNetwork.connections)) {
    return [];
  }

  const eventText =
    `${event?.title ?? ""} ${event?.description ?? ""}`.toLowerCase();
  const eventYear = event?.date ? parseInt(event.date.substring(0, 4)) : null;

  return egoNetwork.connections
    .filter((connection) => {
      // Check if person's name appears in event text
      const personName = connection.person_name.toLowerCase();
      if (!eventText.includes(personName)) {
        return false;
      }

      // Check if event year falls within relationship timeframe
      if (eventYear) {
        const startYear = connection.start_year;
        const endYear = connection.end_year;
        if (startYear && eventYear < startYear) {
          return false;
        }
        if (endYear && eventYear > endYear) {
          return false;
        }
      }

      return true;
    })
    .slice(0, 5);
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
