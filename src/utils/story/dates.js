/**
 * Historical dates: parsing the corpus's date strings (unpadded pre-1000
 * years, BCE dates in astronomical numbering), formatting them for display,
 * and deriving ages and lifespan labels.
 */
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
