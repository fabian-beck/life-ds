/**
 * Barrel for the story utility modules.
 *
 * This file was a 1,900-line grab-bag of eight unrelated clusters — dates,
 * locations, colors, imagery, icons, person matching, prose segmentation, and
 * event depth — with largely disjoint consumers. The clusters now live under
 * `src/utils/story/`; this barrel re-exports every public symbol so existing
 * imports keep working. New code should import from the specific module.
 */

export {
  toIsoInstant,
  parseHistoricalDate,
  extractYear,
  toTimestamp,
  formatSingleDate,
  formatDate,
  computeAgeAtDate,
  getEventAgeRange,
  getDateNote,
  computeYearsLabel,
  createDateFormatters,
} from "./story/dates.js";

export {
  normalizePrimaryLocation,
  normalizeAllLocations,
  isCoordinate,
  isMigrationEvent,
  getMigrationPath,
} from "./story/geo.js";

export { parseHexColor, rgbaFromHex } from "./story/color.js";

export { EVENT_ICON_RULES, resolveEventIcon } from "./story/eventIcons.js";

export {
  getThumbnailUrl,
  getValidImages,
  sourceLabel,
  getPublicationSource,
  getBackgroundImages,
} from "./story/images.js";

export {
  getSubcategory,
  escapeRegex,
  normalizePersonName,
  getRelevantPeople,
  findPersonInNetwork,
  getChapterPeople,
  isBirthEvent,
  normalizeFamilyRole,
  getBirthParents,
} from "./story/personMatching.js";

export { parseDescriptionSegments } from "./story/prose.js";

export {
  getEventWeight,
  getEventDepth,
  DEEP_EVENT_FLOOR,
  selectDeepEventIndexes,
  hasBackgroundReport,
} from "./story/eventDepth.js";
