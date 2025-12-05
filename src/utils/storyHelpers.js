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
 * Escape special regex characters in a string.
 * @param {string} str - String to escape
 * @returns {string} Escaped string
 */
function escapeRegex(str) {
  return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Check if a word is too common to use for last-name-only matching.
 * Prevents false positives like "Church", "Grace", "Newton".
 * @param {string} word - Word to check
 * @returns {boolean} True if common word
 */
function isCommonWord(word) {
  const commonWords = new Set([
    'church', 'grace', 'hope', 'faith', 'love', 'king', 'queen',
    'prince', 'lord', 'duke', 'white', 'black', 'green', 'brown',
    'young', 'old', 'good', 'new', 'long', 'short', 'stone', 'wood',
    'hill', 'field', 'well', 'strong', 'bright', 'rich', 'poor'
  ]);
  return commonWords.has(word.toLowerCase());
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
  if (!name || typeof name !== 'string') return null;

  let normalized = name.trim();

  // Remove parenthetical clarifications: "Ethel Sara Turing (née Stoney)" → "Ethel Sara Turing"
  normalized = normalized.replace(/\s*\([^)]*\)/g, '');

  // Remove bracketed clarifications: "D. G. [David Gawen] Champernowne" → "D. G. Champernowne"
  normalized = normalized.replace(/\s*\[[^\]]*\]/g, '');

  // Remove suffixes: "John von Neumann Jr." → "John von Neumann"
  normalized = normalized.replace(/\s+(Jr|Sr|II|III|IV)\.?$/i, '');

  // Split into tokens
  const tokens = normalized.split(/\s+/).filter(t => t.length > 0);
  if (tokens.length === 0) return null;

  // Handle "von", "de", "van" etc. as part of last name
  const particleIndex = tokens.findIndex(t =>
    ['von', 'van', 'de', 'del', 'della', 'di'].includes(t.toLowerCase())
  );

  let lastName, firstNames;
  if (particleIndex > -1 && particleIndex < tokens.length - 1) {
    // Include particle in last name
    lastName = tokens.slice(particleIndex).join(' ');
    firstNames = tokens.slice(0, particleIndex);
  } else {
    lastName = tokens[tokens.length - 1];
    firstNames = tokens.slice(0, -1);
  }

  const firstName = firstNames.length > 0 ? firstNames[0] : '';

  return {
    fullName: normalized,
    firstName: firstName,
    lastName: lastName,
    tokens: tokens.map(t => t.toLowerCase()),
    originalName: name,
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
    regex: new RegExp(`\\b${escapeRegex(normalized.fullName)}\\b`, 'gi'),
    type: 'full',
    priority: 1,
  });

  // Variant 2: Last name only (medium priority, requires caution)
  // Only if last name is distinctive (>4 chars, not a common word)
  if (normalized.lastName.length > 4 && !isCommonWord(normalized.lastName)) {
    variants.push({
      text: normalized.lastName,
      regex: new RegExp(`\\b${escapeRegex(normalized.lastName)}\\b`, 'gi'),
      type: 'last',
      priority: 2,
    });
  }

  // Variant 3: First + Last (in case middle names/initials differ)
  if (normalized.firstName && normalized.tokens.length > 2) {
    const firstLast = `${normalized.firstName} ${normalized.lastName}`;
    variants.push({
      text: firstLast,
      regex: new RegExp(`\\b${escapeRegex(firstLast)}\\b`, 'gi'),
      type: 'first_last',
      priority: 1,
    });
  }

  // Sort by priority (lower number = higher priority)
  return variants.sort((a, b) => a.priority - b.priority);
}

/**
 * Get people relevant to an event from the ego network.
 * Two-phase approach:
 * 1. PRIMARY: Use involved_people field if present
 * 2. FALLBACK: Smart text matching with name variants
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
  if (event.involved_people && Array.isArray(event.involved_people) && event.involved_people.length > 0) {
    // Normalize all involved people names
    const involvedNormalized = event.involved_people
      .map(name => normalizePersonName(name))
      .filter(Boolean);

    const matched = connections.filter(conn => {
      const connNormalized = normalizePersonName(conn.person_name);
      if (!connNormalized) return false;

      // Try to match against involved_people
      const isMatch = involvedNormalized.some(involved => {
        // Exact full name match
        if (involved.fullName === connNormalized.fullName) return true;

        // Fuzzy match for family members: same first name is sufficient
        // This handles cases like "Elsa Stowasser" (event) vs "Elsa Hundertwasser" (network)
        // Common for mothers with different married names, or name variants
        if (involved.firstName && connNormalized.firstName) {
          const firstNamesMatch = involved.firstName.toLowerCase() === connNormalized.firstName.toLowerCase();
          const isFamily = conn.relationship_type?.startsWith('family/');

          if (firstNamesMatch && isFamily) {
            return true;
          }

          // For non-family, require last name match too
          if (firstNamesMatch) {
            const involvedLower = involved.fullName.toLowerCase();
            const connLower = connNormalized.fullName.toLowerCase();
            return involvedLower.includes(connNormalized.lastName.toLowerCase()) ||
                   connLower.includes(involved.lastName.toLowerCase());
          }
        }

        return false;
      });

      if (!isMatch) return false;

      // Still apply year-range filtering
      return isWithinYearRange(eventYear, conn.start_year, conn.end_year);
    });

    return matched.slice(0, 5);
  }

  // PHASE 2: Fallback to smart text matching
  const eventText = `${event?.title ?? ""} ${event?.description ?? ""}`.toLowerCase();

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
    .map(connection => {
      const normalized = normalizePersonName(connection.person_name);
      const variants = generateNameVariants(connection.person_name);

      // If multiple people share this last name, skip last-name-only variants to avoid ambiguity
      const hasAmbiguousLastName = normalized && lastNameCounts.get(normalized.lastName) > 1;

      // Try to find best match
      for (const variant of variants) {
        // Skip last-name-only matches if ambiguous
        if (hasAmbiguousLastName && variant.type === 'last') {
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
    .filter(match => {
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
      return (strengthOrder[a.connection.strength] || 3) - (strengthOrder[b.connection.strength] || 3);
    })
    .slice(0, 5)
    .map(match => match.connection);

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
export function parseDescriptionSegments(description, annotations = {}, relevantPeople = []) {
  if (!description) return [];

  // Step 1: Parse annotations first (they take priority)
  const annotationPattern = /\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g;
  const annotationRanges = [];
  let match;

  while ((match = annotationPattern.exec(description)) !== null) {
    const termKey = match[1];
    const displayText = match[2] || match[1];
    const annotation = annotations[termKey];

    if (annotation) {
      annotationRanges.push({
        start: match.index,
        end: annotationPattern.lastIndex,
        type: 'annotation',
        termKey,
        displayText,
        annotation,
      });
    }
  }

  // Step 2: Find person name matches
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
    const hasAmbiguousLastName = normalized && lastNameCounts.get(normalized.lastName) > 1;

    for (const variant of variants) {
      // Skip last-name-only matches if ambiguous
      if (hasAmbiguousLastName && variant.type === 'last') {
        continue;
      }

      let match;
      variant.regex.lastIndex = 0; // Reset regex

      while ((match = variant.regex.exec(description)) !== null) {
        const start = match.index;
        const end = variant.regex.lastIndex;

        // Check if this overlaps with an annotation
        const overlapsAnnotation = annotationRanges.some(
          ann => (start >= ann.start && start < ann.end) || (end > ann.start && end <= ann.end)
        );

        if (!overlapsAnnotation) {
          personMatches.push({
            start,
            end,
            type: 'person',
            person,
            matchedText: match[0],
            priority: variant.priority,
          });
        }
      }
    }
  }

  // Step 3: Merge all ranges and sort by position
  const allRanges = [...annotationRanges, ...personMatches].sort((a, b) => {
    if (a.start !== b.start) return a.start - b.start;
    // If same start, annotations win
    if (a.type === 'annotation') return -1;
    if (b.type === 'annotation') return 1;
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
        type: 'text',
        content: description.slice(currentPos, range.start),
      });
    }

    // Add the range itself
    if (range.type === 'annotation') {
      segments.push({
        type: 'annotation',
        termKey: range.termKey,
        displayText: range.displayText,
        annotation: range.annotation,
      });
    } else if (range.type === 'person') {
      segments.push({
        type: 'person',
        content: range.matchedText,
        person: range.person,
      });
    }

    currentPos = range.end;
  }

  // Add remaining text
  if (currentPos < description.length) {
    segments.push({
      type: 'text',
      content: description.slice(currentPos),
    });
  }

  return segments;
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
