/**
 * Event locations: the unified location structure, coordinate checks, and the
 * migration path a migration-classified event describes.
 */
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
