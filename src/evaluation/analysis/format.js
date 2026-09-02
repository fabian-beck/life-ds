export {
  formatDuration,
  formatPercent,
} from "../../utils/evaluation/analysis.js";

const dateTime = new Intl.DateTimeFormat("en-GB", {
  year: "numeric",
  month: "short",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

const dateOnly = new Intl.DateTimeFormat("en-GB", {
  year: "numeric",
  month: "short",
  day: "2-digit",
});

/** @param {number|null|undefined} ms */
export function formatDateTime(ms) {
  if (!Number.isFinite(ms)) return "—";
  return dateTime.format(new Date(ms));
}

/** @param {number|null|undefined} ms */
export function formatDate(ms) {
  if (!Number.isFinite(ms)) return "—";
  return dateOnly.format(new Date(ms));
}

/** @param {number|null|undefined} value */
export function formatCount(value) {
  if (!Number.isFinite(value)) return "—";
  return new Intl.NumberFormat("en-US").format(value);
}

/**
 * A browser family from a user agent string: only what a study needs to say
 * which browsers took part.
 * @param {string|null|undefined} ua
 */
export function browserFamily(ua) {
  if (!ua) return "—";
  if (/Edg\//.test(ua)) return "Edge";
  if (/OPR\//.test(ua)) return "Opera";
  if (/SamsungBrowser/.test(ua)) return "Samsung Internet";
  if (/Firefox\//.test(ua)) return "Firefox";
  if (/Chrome\//.test(ua)) return "Chrome";
  if (/Safari\//.test(ua) && /Version\//.test(ua)) return "Safari";
  return "Other";
}

/** @param {string|null|undefined} ua */
export function platformFamily(ua) {
  if (!ua) return "—";
  if (/iPhone|iPad|iPod/.test(ua)) return "iOS";
  if (/Android/.test(ua)) return "Android";
  if (/Windows/.test(ua)) return "Windows";
  if (/Mac OS X/.test(ua)) return "macOS";
  if (/Linux/.test(ua)) return "Linux";
  return "Other";
}

/**
 * A readable name from a story id: "ada_lovelace" → "Ada Lovelace". The log
 * carries the display name of a story once it was opened; this is the
 * fallback for one that never loaded.
 * @param {string|null|undefined} id
 */
export function nameFromId(id) {
  if (!id) return "—";
  return id
    .split("_")
    .map((part) => (part ? part[0].toUpperCase() + part.slice(1) : part))
    .join(" ");
}
