/**
 * Map utilities for collision detection and marker arrangement
 * Uses Web Mercator projection for pixel-space calculations
 */

const TILE_SIZE = 512; // MapLibre default tile size

/**
 * Converts geographic coordinates to Web Mercator pixels at a given zoom level
 * @param {number} lon - Longitude (-180 to 180)
 * @param {number} lat - Latitude (-90 to 90)
 * @param {number} zoom - Zoom level
 * @returns {Object} {x, y} pixel coordinates
 */
export function lonLatToPixels(lon, lat, zoom) {
  const scale = (TILE_SIZE * Math.pow(2, zoom)) / (2 * Math.PI);

  const x = scale * ((lon * Math.PI) / 180 + Math.PI);
  const y =
    scale *
    (Math.PI - Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360)));

  return { x, y };
}

/**
 * Converts Web Mercator pixels back to geographic coordinates
 * @param {number} x - Pixel X coordinate
 * @param {number} y - Pixel Y coordinate
 * @param {number} zoom - Zoom level
 * @returns {Object} {lon, lat} geographic coordinates
 */
export function pixelsToLonLat(x, y, zoom) {
  const scale = (TILE_SIZE * Math.pow(2, zoom)) / (2 * Math.PI);

  const lon = ((x / scale - Math.PI) * 180) / Math.PI;
  const lat =
    ((2 * Math.atan(Math.exp(Math.PI - y / scale)) - Math.PI / 2) * 180) /
    Math.PI;

  return { lon, lat };
}

/**
 * Detects if two geographic points would overlap on screen at a given zoom level
 * @param {Object} pointA - {lon, lat}
 * @param {Object} pointB - {lon, lat}
 * @param {number} zoom - Map zoom level
 * @param {number} thresholdPixels - Distance threshold in pixels (default: 15)
 * @returns {boolean} True if points would overlap
 */
export function wouldOverlap(pointA, pointB, zoom, thresholdPixels = 15) {
  const pixelA = lonLatToPixels(pointA.lon, pointA.lat, zoom);
  const pixelB = lonLatToPixels(pointB.lon, pointB.lat, zoom);

  const distance = Math.sqrt(
    Math.pow(pixelB.x - pixelA.x, 2) + Math.pow(pixelB.y - pixelA.y, 2)
  );

  return distance < thresholdPixels;
}

/**
 * Arranges overlapping markers in a circular pattern around their original location
 * @param {Array} features - GeoJSON features with Point geometries
 * @param {number} zoom - Target zoom level for collision detection (e.g., 12)
 * @param {number} separationPixels - Minimum separation in pixels (default: 15)
 * @returns {Object} { markers: Array, connections: GeoJSON, dummies: GeoJSON } - Adjusted markers, connection lines, and dummy markers
 */
export function arrangeOverlappingMarkers(
  features,
  zoom,
  separationPixels = 15
) {
  if (!features || features.length === 0) {
    return {
      markers: [],
      connections: { type: "FeatureCollection", features: [] },
      dummies: { type: "FeatureCollection", features: [] },
    };
  }

  const arranged = [];
  const connections = [];
  const dummies = [];
  const processed = new Set();

  for (let i = 0; i < features.length; i++) {
    if (processed.has(i)) continue;

    // Find all features that overlap with feature i
    const group = [i];
    const [lonA, latA] = features[i].geometry.coordinates;
    const pixelA = lonLatToPixels(lonA, latA, zoom);

    for (let j = i + 1; j < features.length; j++) {
      if (processed.has(j)) continue;

      const [lonB, latB] = features[j].geometry.coordinates;
      const pixelB = lonLatToPixels(lonB, latB, zoom);

      const distance = Math.sqrt(
        Math.pow(pixelB.x - pixelA.x, 2) + Math.pow(pixelB.y - pixelA.y, 2)
      );

      if (distance < separationPixels) {
        group.push(j);
        processed.add(j);
      }
    }

    if (group.length === 1) {
      // No overlap - keep original position
      arranged.push(features[i]);
    } else {
      // Multiple overlapping markers - arrange in circle
      const centerPixel = pixelA;
      const centerCoords = [lonA, latA];
      const radius = separationPixels;
      const angleStep = (2 * Math.PI) / group.length;

      // Create a single dummy marker at the original (center) position
      dummies.push({
        type: "Feature",
        geometry: {
          type: "Point",
          coordinates: centerCoords,
        },
        properties: {
          // Use a neutral gray color for dummies
          color: "#64748b",
        },
      });

      group.forEach((idx, position) => {
        // Deep copy to avoid mutating original
        const feature = JSON.parse(JSON.stringify(features[idx]));

        // Arrange all markers in circle (no center marker)
        const angle = angleStep * position;
        const offsetX = radius * Math.cos(angle);
        const offsetY = radius * Math.sin(angle);

        const newPixel = {
          x: centerPixel.x + offsetX,
          y: centerPixel.y + offsetY,
        };

        const newCoords = pixelsToLonLat(newPixel.x, newPixel.y, zoom);

        // Update marker coordinates
        feature.geometry.coordinates = [newCoords.lon, newCoords.lat];

        // Create connection line from center to adjusted position
        connections.push({
          type: "Feature",
          geometry: {
            type: "LineString",
            coordinates: [
              centerCoords,
              [newCoords.lon, newCoords.lat],
            ],
          },
          properties: {
            color: feature.properties.primaryColor || "#94a3b8",
          },
        });

        arranged.push(feature);
      });
    }

    processed.add(i);
  }

  return {
    markers: arranged,
    connections: { type: "FeatureCollection", features: connections },
    dummies: { type: "FeatureCollection", features: dummies },
  };
}
