<script>
  import { tick, onMount, onDestroy } from "svelte";
  import "maplibre-gl/dist/maplibre-gl.css";
  import * as maplibregl from "maplibre-gl";
  import { _ } from "../stores/language";
  import { parseHexColor, rgbaFromHex } from "../utils/story/color.js";
  import { isCoordinate } from "../utils/story/geo.js";
  import {
    resolveBasemapUrl,
    createBasemapStyle,
    acquirePmtilesProtocol,
    releasePmtilesProtocol,
  } from "../utils/basemap.js";

  export let activeCoordinates = null;
  export let allActiveCoordinates = [];
  export let markerTrail = [];
  export let hasMapData = false;
  export let activeIndex = 0;
  export let isChapterSlide = false;
  // 0 while the reader is on the event, 1 once they have gone down into its
  // depth layer. The map belongs to the event: it fades out on the way down
  // rather than glowing behind a page of running text.
  export let depthProgress = 0;
  export let styleConfig = null;
  export let migrationPath = null; // {from: {lon, lat}, to: {lon, lat}} or null

  let basemapError = null;
  let mapContainer;
  let mapInstance = null;
  let mapReady = false;
  let mapInitializationPromise = null;
  let isDestroyed = false;
  let currentMarkers = [];
  let trailMarkers = [];
  let lastViewportKey = "";
  let protocolAcquired = false;

  $: primaryMarkerColor =
    styleConfig?.secondary && parseHexColor(styleConfig.secondary)
      ? styleConfig.secondary
      : "#38BDF8";
  $: fadedMarkerColor =
    rgbaFromHex(primaryMarkerColor, 0.7) ?? "rgba(56, 189, 248, 0.7)";

  function createMarkerElement(
    color,
    { opacity = 1, size = 14, label = null, lat = null, primary = false } = {}
  ) {
    const container = document.createElement("div");
    container.className = "story-map-marker-container";

    const element = document.createElement("span");
    element.className = "story-map-marker";
    element.style.backgroundColor = color;
    element.style.opacity = `${Math.min(Math.max(opacity, 0), 1)}`;
    const clampedSize = Math.max(size, 6);
    element.style.width = `${clampedSize}px`;
    element.style.height = `${clampedSize}px`;

    container.appendChild(element);

    if (label) {
      const labelElement = document.createElement("span");
      labelElement.className = "story-map-label";
      labelElement.textContent = label;
      labelElement.dataset.lat = lat?.toString() ?? "";
      labelElement.dataset.primary = primary ? "true" : "false";
      container.appendChild(labelElement);
    }

    return container;
  }

  function calculateLabelPosition(lat) {
    // Get current map bounds
    if (!mapInstance) return "top";

    const bounds = mapInstance.getBounds();
    const center = (bounds.getNorth() + bounds.getSouth()) / 2;

    // If marker is in the top half of the viewport, place label below
    // If marker is in the bottom half, place label above
    return lat > center ? "bottom" : "top";
  }

  function getLabelBounds(label, position) {
    // Get the marker container's position
    const container = label.closest(".story-map-marker-container");
    if (!container) return null;

    const containerRect = container.getBoundingClientRect();
    const labelWidth = label.offsetWidth || 80; // estimate if not rendered
    const labelHeight = label.offsetHeight || 16;

    // Calculate label position based on whether it's top or bottom
    const centerX = containerRect.left + containerRect.width / 2;
    const left = centerX - labelWidth / 2;
    const right = left + labelWidth;

    let top, bottom;
    if (position === "top") {
      bottom = containerRect.top - 1; // margin
      top = bottom - labelHeight;
    } else {
      top = containerRect.bottom + 1; // margin
      bottom = top + labelHeight;
    }

    return { left, right, top, bottom, centerX, centerY: (top + bottom) / 2 };
  }

  function rectsOverlap(a, b, padding = 2) {
    if (!a || !b) return false;
    return !(
      a.right + padding < b.left ||
      b.right + padding < a.left ||
      a.bottom + padding < b.top ||
      b.bottom + padding < a.top
    );
  }

  function getMarkerBounds(container) {
    const marker = container.querySelector(".story-map-marker");
    if (!marker) return null;
    const rect = marker.getBoundingClientRect();
    return {
      left: rect.left,
      right: rect.right,
      top: rect.top,
      bottom: rect.bottom,
    };
  }

  function getAllMarkerBounds() {
    const containers = document.querySelectorAll(".story-map-marker-container");
    const bounds = [];
    containers.forEach((container) => {
      const markerBounds = getMarkerBounds(container);
      if (markerBounds) {
        bounds.push(markerBounds);
      }
    });
    return bounds;
  }

  function isNearMapEdge(bounds, mapRect, edgeMargin = 20) {
    if (!bounds || !mapRect) return { nearTop: false, nearBottom: false };
    return {
      nearTop: bounds.top < mapRect.top + edgeMargin,
      nearBottom: bounds.bottom > mapRect.bottom - edgeMargin,
    };
  }

  function getOptimalPosition(
    label,
    lat,
    mapRect,
    allMarkerBounds,
    ownMarkerBounds
  ) {
    // Try both positions and pick the one that:
    // 1. Doesn't clip the edge
    // 2. Doesn't overlap with other markers (excluding own marker)
    const preferredPosition = calculateLabelPosition(lat);
    const altPosition = preferredPosition === "top" ? "bottom" : "top";

    // Get bounds for both positions
    label.classList.remove("story-map-label-top", "story-map-label-bottom");
    label.classList.add(`story-map-label-${preferredPosition}`);
    void label.offsetHeight;
    const preferredBounds = getLabelBounds(label, preferredPosition);
    const preferredEdge = isNearMapEdge(preferredBounds, mapRect);

    label.classList.remove("story-map-label-top", "story-map-label-bottom");
    label.classList.add(`story-map-label-${altPosition}`);
    void label.offsetHeight;
    const altBounds = getLabelBounds(label, altPosition);
    const altEdge = isNearMapEdge(altBounds, mapRect);

    // Check marker overlaps for both positions (exclude own marker)
    const otherMarkers = allMarkerBounds.filter(
      (m) =>
        !ownMarkerBounds ||
        Math.abs(m.left - ownMarkerBounds.left) > 1 ||
        Math.abs(m.top - ownMarkerBounds.top) > 1
    );

    const preferredOverlapsMarker = otherMarkers.some((m) =>
      rectsOverlap(preferredBounds, m, 4)
    );
    const altOverlapsMarker = otherMarkers.some((m) =>
      rectsOverlap(altBounds, m, 4)
    );

    // Score each position (lower is better)
    let preferredScore = 0;
    let altScore = 0;

    if (preferredPosition === "top" && preferredEdge.nearTop)
      preferredScore += 10;
    if (preferredPosition === "bottom" && preferredEdge.nearBottom)
      preferredScore += 10;
    if (preferredOverlapsMarker) preferredScore += 5;

    if (altPosition === "top" && altEdge.nearTop) altScore += 10;
    if (altPosition === "bottom" && altEdge.nearBottom) altScore += 10;
    if (altOverlapsMarker) altScore += 5;

    return altScore < preferredScore ? altPosition : preferredPosition;
  }

  function overlapsAnyMarker(labelBounds, allMarkerBounds, ownMarkerBounds) {
    const otherMarkers = allMarkerBounds.filter(
      (m) =>
        !ownMarkerBounds ||
        Math.abs(m.left - ownMarkerBounds.left) > 1 ||
        Math.abs(m.top - ownMarkerBounds.top) > 1
    );
    return otherMarkers.some((m) => rectsOverlap(labelBounds, m, 4));
  }

  function updateLabelPositions() {
    const labels = Array.from(document.querySelectorAll(".story-map-label"));
    if (labels.length === 0) return;

    // Get map container bounds for edge detection
    const mapRect = mapContainer?.getBoundingClientRect();

    // Get all marker bounds for overlap detection
    const allMarkerBounds = getAllMarkerBounds();

    // First pass: assign initial positions based on viewport and edge avoidance
    const labelData = labels.map((label, index) => {
      const lat = parseFloat(label.dataset.lat);
      const isPrimary = label.dataset.primary === "true";
      const container = label.closest(".story-map-marker-container");
      const ownMarkerBounds = container ? getMarkerBounds(container) : null;
      return {
        label,
        lat,
        index,
        isPrimary,
        ownMarkerBounds,
        position: "top", // will be set properly
        alternatePosition: "bottom",
        hidden: false,
      };
    });

    // Sort: primary first, then by latitude (higher lat = further north)
    labelData.sort((a, b) => {
      if (a.isPrimary && !b.isPrimary) return -1;
      if (!a.isPrimary && b.isPrimary) return 1;
      return (b.lat || 0) - (a.lat || 0);
    });

    // Temporarily show labels for measurement
    labelData.forEach(({ label }) => {
      label.classList.remove(
        "story-map-label-top",
        "story-map-label-bottom",
        "story-map-label-visible",
        "story-map-label-hidden"
      );
      label.classList.add("story-map-label-top"); // default for measurement
      label.style.visibility = "hidden";
      label.style.opacity = "1";
    });

    // Force layout recalc
    void labels[0]?.offsetHeight;

    // Second pass: assign optimal positions considering edges and markers (primary first)
    labelData.forEach((data) => {
      if (!isNaN(data.lat)) {
        data.position = getOptimalPosition(
          data.label,
          data.lat,
          mapRect,
          allMarkerBounds,
          data.ownMarkerBounds
        );
        data.alternatePosition = data.position === "top" ? "bottom" : "top";
      }
      data.label.classList.remove(
        "story-map-label-top",
        "story-map-label-bottom"
      );
      data.label.classList.add(`story-map-label-${data.position}`);
    });

    // Force layout recalc again
    void labels[0]?.offsetHeight;

    // Third pass: detect and resolve overlaps (primary is already first, so it gets priority)
    for (let i = 0; i < labelData.length; i++) {
      if (labelData[i].hidden) continue;

      const currentBounds = getLabelBounds(
        labelData[i].label,
        labelData[i].position
      );

      for (let j = i + 1; j < labelData.length; j++) {
        if (labelData[j].hidden) continue;

        const otherBounds = getLabelBounds(
          labelData[j].label,
          labelData[j].position
        );

        if (rectsOverlap(currentBounds, otherBounds)) {
          // Try flipping the later (non-primary) label to its alternate position
          const altPosition = labelData[j].alternatePosition;
          labelData[j].label.classList.remove(
            "story-map-label-top",
            "story-map-label-bottom"
          );
          labelData[j].label.classList.add(`story-map-label-${altPosition}`);
          labelData[j].position = altPosition;

          // Check if it still overlaps after flip
          void labelData[j].label.offsetHeight;
          const newBounds = getLabelBounds(labelData[j].label, altPosition);

          // Also check if new position clips the edge or overlaps markers
          const edgeCheck = isNearMapEdge(newBounds, mapRect);
          const clipsEdge =
            (altPosition === "top" && edgeCheck.nearTop) ||
            (altPosition === "bottom" && edgeCheck.nearBottom);
          const overlapsMarker = overlapsAnyMarker(
            newBounds,
            allMarkerBounds,
            labelData[j].ownMarkerBounds
          );

          // Check against all previous labels
          let stillOverlaps = false;
          for (let k = 0; k <= i; k++) {
            if (labelData[k].hidden) continue;
            const prevBounds = getLabelBounds(
              labelData[k].label,
              labelData[k].position
            );
            if (rectsOverlap(newBounds, prevBounds)) {
              stillOverlaps = true;
              break;
            }
          }

          if (stillOverlaps || clipsEdge || overlapsMarker) {
            // Hide the overlapping label as last resort
            labelData[j].hidden = true;
            labelData[j].label.classList.add("story-map-label-hidden");
          }
        }
      }
    }

    // Final pass: show labels with proper styling
    labelData.forEach(({ label, hidden }) => {
      label.style.visibility = "";
      label.style.opacity = "";
      if (!hidden) {
        label.classList.add("story-map-label-visible");
      }
    });
  }

  let labelUpdateFrame = null;

  // Labels are made visible by updateLabelPositions(), which normally runs on
  // the map's `moveend`. When a slide change recreates the markers but the
  // viewport does not move (e.g. consecutive events at the same location), no
  // `moveend` fires, so the freshly created labels would stay at opacity 0.
  // Schedule a direct update in that case, on the next frame so MapLibre has
  // positioned the new markers before we measure them.
  function scheduleLabelUpdate() {
    if (labelUpdateFrame !== null) {
      cancelAnimationFrame(labelUpdateFrame);
    }
    labelUpdateFrame = requestAnimationFrame(() => {
      labelUpdateFrame = null;
      updateLabelPositions();
    });
  }

  function clearMarkers() {
    for (const marker of currentMarkers) {
      marker.remove();
    }
    currentMarkers = [];
    for (const marker of trailMarkers) {
      marker.remove();
    }
    trailMarkers = [];
  }

  let migrationPathMarkers = [];
  let migrationAnimationFrameId = null;
  let migrationArrowTimeout = null;

  function clearMigrationPath() {
    if (!mapInstance) return;

    // Remove layers first, then sources
    if (mapInstance.getLayer("migration-path")) {
      mapInstance.removeLayer("migration-path");
    }
    if (mapInstance.getSource("migration-route")) {
      mapInstance.removeSource("migration-route");
    }

    // Cancel the pending arrow placement and the running animation loop
    if (migrationArrowTimeout) {
      clearTimeout(migrationArrowTimeout);
      migrationArrowTimeout = null;
    }
    if (migrationAnimationFrameId !== null) {
      cancelAnimationFrame(migrationAnimationFrameId);
      migrationAnimationFrameId = null;
    }

    // Remove all arrow markers
    for (const item of migrationPathMarkers) {
      const marker = item.marker || item;
      marker.remove();
    }
    migrationPathMarkers = [];
  }

  function createArrowElement(color) {
    const container = document.createElement("div");
    container.className = "migration-arrow-container";
    container.style.opacity = "0"; // Start invisible for fade-in

    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("width", "24");
    svg.setAttribute("height", "24");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.style.display = "block";

    // Larger, clearer arrow pointing upward (north), will be rotated by MapLibre
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", "M12 3 L20 15 L12 12 L4 15 Z");
    path.setAttribute("fill", color);
    path.setAttribute("opacity", "0.85");
    path.setAttribute("stroke", "rgba(2, 6, 23, 0.9)");
    path.setAttribute("stroke-width", "1.5");

    svg.appendChild(path);
    container.appendChild(svg);

    return container;
  }

  /**
   * Generate a curved arc between two points for migration path.
   * Uses a consistent curving direction that works well regardless of migration direction.
   * @param {Object} from - {lon, lat}
   * @param {Object} to - {lon, lat}
   * @param {number} numPoints - Number of points along the arc
   * @returns {Array} Array of [lon, lat] coordinates
   */
  function createCurvedPath(from, to, numPoints = 100) {
    const coordinates = [];

    // Calculate midpoint
    const midLon = (from.lon + to.lon) / 2;
    const midLat = (from.lat + to.lat) / 2;

    // Calculate distance in degrees
    const deltaLon = to.lon - from.lon;
    const deltaLat = to.lat - from.lat;
    const distance = Math.sqrt(deltaLon * deltaLon + deltaLat * deltaLat);

    // Arc height: use a moderate, distance-scaled offset
    // Cap at reasonable values to avoid extreme curves
    const baseHeight = Math.min(distance * 0.2, 8);
    const minHeight = Math.min(distance * 0.1, 3);
    const arcHeight = Math.max(baseHeight, minHeight);

    // Calculate perpendicular direction
    // Cross product approach: rotate direction vector 90° counterclockwise
    let perpLon = -deltaLat;
    let perpLat = deltaLon;
    const perpLength = Math.sqrt(perpLon * perpLon + perpLat * perpLat);

    if (perpLength === 0) {
      // Points are identical, return straight line
      return [
        [from.lon, from.lat],
        [to.lon, to.lat],
      ];
    }

    // Normalize perpendicular vector
    perpLon /= perpLength;
    perpLat /= perpLength;

    // Determine curve direction based on geography
    // For east-west migrations, curve based on hemisphere
    // For north-south migrations, curve based on longitude direction
    let curveDirection = 1; // default: curve "upward"

    if (Math.abs(deltaLon) > Math.abs(deltaLat)) {
      // Primarily east-west migration
      // Curve northward in northern hemisphere, southward in southern hemisphere
      curveDirection = midLat >= 0 ? 1 : -1;
    } else {
      // Primarily north-south migration
      // Curve eastward when going from west to east, westward when going from east to west
      curveDirection = deltaLon >= 0 ? 1 : -1;
    }

    // Apply curve direction
    const controlLon = midLon + perpLon * arcHeight * curveDirection;
    const controlLat = midLat + perpLat * arcHeight * curveDirection;

    // Generate points along quadratic Bézier curve
    for (let i = 0; i <= numPoints; i++) {
      const t = i / numPoints;
      const oneMinusT = 1 - t;

      // Quadratic Bézier: B(t) = (1-t)²P₀ + 2(1-t)tP₁ + t²P₂
      const lon =
        oneMinusT * oneMinusT * from.lon +
        2 * oneMinusT * t * controlLon +
        t * t * to.lon;
      const lat =
        oneMinusT * oneMinusT * from.lat +
        2 * oneMinusT * t * controlLat +
        t * t * to.lat;

      coordinates.push([lon, lat]);
    }

    return coordinates;
  }

  function addMigrationArrows(from, to, curvedCoordinates) {
    // Calculate arrow count based on pixel distance at current viewport
    const fromPoint = mapInstance.project([from.lon, from.lat]);
    const toPoint = mapInstance.project([to.lon, to.lat]);
    const pixelDistance = Math.sqrt(
      Math.pow(toPoint.x - fromPoint.x, 2) +
        Math.pow(toPoint.y - fromPoint.y, 2)
    );

    // Dynamically calculate number of arrows based on pixel distance
    // Aim for one arrow roughly every 100-120 pixels, minimum 1, maximum 5
    const numArrows = Math.max(1, Math.min(5, Math.round(pixelDistance / 110)));

    // Remove existing arrow markers ({ marker, coords } entries)
    for (const item of migrationPathMarkers) {
      (item.marker || item).remove();
    }
    migrationPathMarkers = [];

    // Animation duration in seconds - much slower, longer paths take longer
    const animationDuration = Math.max(8, Math.min(20, pixelDistance / 30));

    // Create arrows that will animate along the path
    for (let i = 0; i < numArrows; i++) {
      // Stagger the start of each arrow's animation
      const delay = (i / numArrows) * animationDuration;

      // Start arrow at the beginning of the path
      const startIndex = 0;
      const current = curvedCoordinates[startIndex];
      const next = curvedCoordinates[Math.min(3, curvedCoordinates.length - 1)];

      // Calculate initial angle
      const deltaX = next[0] - current[0];
      const deltaY = next[1] - current[1];
      const initialAngle = Math.atan2(deltaX, deltaY) * (180 / Math.PI);

      const arrowElement = createArrowElement(primaryMarkerColor);

      // Add animation to the arrow container
      arrowElement.style.animation = `migrate-arrow ${animationDuration}s linear ${delay}s infinite`;

      const marker = new maplibregl.Marker({
        element: arrowElement,
        anchor: "center",
        rotationAlignment: "map",
        pitchAlignment: "map",
      })
        .setLngLat([current[0], current[1]])
        .setRotation(initialAngle)
        .addTo(mapInstance);

      migrationPathMarkers.push({ marker, coords: curvedCoordinates });
    }

    // Animate arrows along the path
    const startTime = Date.now();

    function animateArrows() {
      const elapsed = (Date.now() - startTime) / 1000; // seconds

      migrationPathMarkers.forEach(({ marker, coords }, i) => {
        const delay = (i / numArrows) * animationDuration;
        const progress =
          ((elapsed - delay) % animationDuration) / animationDuration;

        if (progress >= 0) {
          // Calculate position along the curve with smooth interpolation
          const exactIndex = progress * (coords.length - 1);
          const index = Math.floor(exactIndex);
          const nextIndex = Math.min(index + 1, coords.length - 1);
          const fraction = exactIndex - index; // 0-1 between current and next point

          const current = coords[index];
          const next = coords[nextIndex];

          // Smoothly interpolate position between points
          const lon = current[0] + (next[0] - current[0]) * fraction;
          const lat = current[1] + (next[1] - current[1]) * fraction;

          // Update position
          marker.setLngLat([lon, lat]);

          // Calculate rotation using a few points ahead for smoother direction
          const lookAheadIndex = Math.min(index + 5, coords.length - 1);
          const lookAhead = coords[lookAheadIndex];
          const deltaX = lookAhead[0] - current[0];
          const deltaY = lookAhead[1] - current[1];
          const angle = Math.atan2(deltaX, deltaY) * (180 / Math.PI);
          marker.setRotation(angle);

          // Update opacity (fade in at start, fade out at end)
          const element = marker.getElement();
          if (element) {
            let opacity;
            if (progress < 0.1) {
              opacity = progress / 0.1;
            } else if (progress > 0.9) {
              opacity = (1 - progress) / 0.1;
            } else {
              opacity = 1;
            }
            element.style.opacity = opacity * 0.85;
          }
        }
      });

      // Reassign every frame so clearMigrationPath cancels the live frame,
      // not the long-expired first one.
      migrationAnimationFrameId = requestAnimationFrame(animateArrows);
    }

    animateArrows();
  }

  function updateMigrationPath(path) {
    if (!mapInstance || !mapReady) return;

    clearMigrationPath();

    if (!path || !path.from || !path.to) return;

    const { from, to } = path;

    // Validate coordinates
    if (
      !Number.isFinite(from.lon) ||
      !Number.isFinite(from.lat) ||
      !Number.isFinite(to.lon) ||
      !Number.isFinite(to.lat)
    ) {
      return;
    }

    // Create curved path coordinates
    const curvedCoordinates = createCurvedPath(from, to);

    // Create GeoJSON for the migration path
    const lineGeoJSON = {
      type: "Feature",
      geometry: {
        type: "LineString",
        coordinates: curvedCoordinates,
      },
      properties: {},
    };

    // Add source
    mapInstance.addSource("migration-route", {
      type: "geojson",
      data: lineGeoJSON,
    });

    // Add line layer with more subtle styling
    mapInstance.addLayer({
      id: "migration-path",
      type: "line",
      source: "migration-route",
      layout: {
        "line-join": "round",
        "line-cap": "round",
      },
      paint: {
        "line-color": primaryMarkerColor,
        "line-width": 2.5,
        "line-opacity": 0.25,
        "line-dasharray": [3, 2],
      },
    });

    // Defer arrow placement until after map animation completes (900ms + buffer)
    // This ensures arrows are counted based on final viewport, not initial state.
    // The handle is cleared by clearMigrationPath so a slide change within the
    // delay cannot resurrect arrows for a path that is no longer shown.
    migrationArrowTimeout = setTimeout(() => {
      migrationArrowTimeout = null;
      if (mapInstance && mapReady) {
        addMigrationArrows(from, to, curvedCoordinates);
      }
    }, 1000);
  }

  function teardownMapInstance() {
    if (labelUpdateFrame !== null) {
      cancelAnimationFrame(labelUpdateFrame);
      labelUpdateFrame = null;
    }
    clearMarkers();
    clearMigrationPath();
    if (mapInstance) {
      mapInstance.remove();
      mapInstance = null;
    }
    mapReady = false;
    lastViewportKey = "";
  }

  function updateMapState(activeCoord, historyCoords) {
    if (!mapInstance || !mapReady) return;

    const active = isCoordinate(activeCoord) ? activeCoord : null;
    const allActive =
      Array.isArray(allActiveCoordinates) && allActiveCoordinates.length > 0
        ? allActiveCoordinates.filter(isCoordinate)
        : active
          ? [active]
          : [];

    const history = Array.isArray(historyCoords)
      ? historyCoords.filter(isCoordinate)
      : [];

    clearMarkers();

    if (history.length > 0) {
      for (const coords of history) {
        const markerElement = createMarkerElement(fadedMarkerColor, {
          opacity: 0.8,
          size: 11,
        });
        const marker = new maplibregl.Marker({
          element: markerElement,
          anchor: "center",
        })
          .setLngLat([coords.lon, coords.lat])
          .addTo(mapInstance);
        trailMarkers.push(marker);
      }
    }

    if (allActive.length > 0) {
      const primaryIndex = allActive.findIndex((loc) => loc.primary === true);
      const primaryLoc =
        primaryIndex >= 0 ? allActive[primaryIndex] : allActive[0];

      const secondaryLocs = allActive.filter((_loc, idx) =>
        primaryIndex >= 0 ? idx !== primaryIndex : idx > 0
      );

      // Draw secondary markers first so primary appears on top
      for (const coords of secondaryLocs) {
        const markerElement = createMarkerElement(primaryMarkerColor, {
          opacity: 1.0,
          size: 15,
          label: coords.name || null,
          lat: coords.lat,
        });
        const marker = new maplibregl.Marker({
          element: markerElement,
          anchor: "center",
        })
          .setLngLat([coords.lon, coords.lat])
          .addTo(mapInstance);
        currentMarkers.push(marker);
      }

      // Draw primary marker last so it's in front
      const primaryElement = createMarkerElement(primaryMarkerColor, {
        opacity: 1.0,
        size: 17,
        label: primaryLoc.name || null,
        lat: primaryLoc.lat,
        primary: true,
      });
      primaryElement
        .querySelector(".story-map-marker")
        ?.classList.add("current");
      const primaryMarker = new maplibregl.Marker({
        element: primaryElement,
        anchor: "center",
      })
        .setLngLat([primaryLoc.lon, primaryLoc.lat])
        .addTo(mapInstance);
      currentMarkers.push(primaryMarker);
    }

    const positions =
      allActive.length > 0 ? [...allActive, ...history] : history;

    // Additional validation to prevent NaN coordinates from reaching maplibre
    const validPositions = positions.filter(
      (coord) => Number.isFinite(coord?.lon) && Number.isFinite(coord?.lat)
    );

    if (validPositions.length === 0) {
      if (lastViewportKey !== "baseline") {
        mapInstance.easeTo({ center: [0, 0], zoom: 1.0, duration: 700 });
        lastViewportKey = "baseline";
      }
      return;
    }

    const viewportKey = validPositions
      .map((coord) => `${coord.lon.toFixed(4)},${coord.lat.toFixed(4)}`)
      .join("|");

    if (viewportKey === lastViewportKey) {
      // Viewport unchanged: no map move will fire `moveend`, so reveal the
      // freshly recreated labels ourselves.
      scheduleLabelUpdate();
      return;
    }
    lastViewportKey = viewportKey;

    if (validPositions.length === 1) {
      mapInstance.easeTo({
        center: [validPositions[0].lon, validPositions[0].lat],
        zoom: 5.0,
        duration: 900,
      });
      return;
    }

    const bounds = validPositions
      .slice(1)
      .reduce(
        (accumulator, coord) => accumulator.extend([coord.lon, coord.lat]),
        new maplibregl.LngLatBounds(
          [validPositions[0].lon, validPositions[0].lat],
          [validPositions[0].lon, validPositions[0].lat]
        )
      );

    // Safety check: ensure bounds are valid before calling fitBounds
    try {
      const ne = bounds.getNorthEast();
      const sw = bounds.getSouthWest();
      if (
        !Number.isFinite(ne.lng) ||
        !Number.isFinite(ne.lat) ||
        !Number.isFinite(sw.lng) ||
        !Number.isFinite(sw.lat)
      ) {
        console.warn("Invalid bounds detected, skipping fitBounds");
        return;
      }

      // Calculate safe padding based on container size to prevent NaN errors
      const containerWidth = mapContainer?.clientWidth || 0;
      const containerHeight = mapContainer?.clientHeight || 0;

      // Ensure minimum usable area after padding (at least 50px)
      const maxHorizontalPadding = Math.max(0, (containerWidth - 50) / 2);
      const maxVerticalPadding = Math.max(0, (containerHeight - 50) / 2);

      const safePadding = {
        top: Math.min(120, maxVerticalPadding),
        bottom: Math.min(120, maxVerticalPadding),
        left: Math.min(80, maxHorizontalPadding),
        right: Math.min(80, maxHorizontalPadding),
      };

      // Skip fitBounds if container is too small
      if (containerWidth < 100 || containerHeight < 100) {
        mapInstance.easeTo({
          center: [validPositions[0].lon, validPositions[0].lat],
          zoom: 3.0,
          duration: 900,
        });
        return;
      }

      mapInstance.fitBounds(bounds, {
        padding: safePadding,
        duration: 900,
        maxZoom: 5.5,
      });
    } catch (err) {
      console.warn("fitBounds error:", err);
    }
  }

  function initializeMap() {
    if (mapInstance || !hasMapData || isDestroyed) {
      return mapInitializationPromise;
    }
    if (mapInitializationPromise) {
      return mapInitializationPromise;
    }

    mapInitializationPromise = (async () => {
      await tick();
      if (mapInstance || !hasMapData || !mapContainer || isDestroyed) return;

      const initialContainer = mapContainer;
      const url = await resolveBasemapUrl();
      if (!url) {
        basemapError = $_("story.basemap_error");
        return;
      }
      basemapError = null;
      if (
        mapInstance ||
        !hasMapData ||
        !mapContainer ||
        mapContainer !== initialContainer ||
        isDestroyed
      ) {
        return;
      }

      // The story map draws its own markers and labels, so the basemap stays
      // letterless; the label language is irrelevant with every label gone.
      const style = createBasemapStyle({ url, lang: "en", labelMode: "none" });

      if (!protocolAcquired) {
        acquirePmtilesProtocol();
        protocolAcquired = true;
      }

      const nextMap = new maplibregl.Map({
        container: initialContainer,
        style,
        center: [0, 0],
        zoom: 1.0,
        attributionControl: false,
        interactive: false,
      });
      mapInstance = nextMap;
      nextMap.dragPan.disable();
      nextMap.scrollZoom.disable();
      nextMap.boxZoom.disable();
      nextMap.dragRotate.disable();
      nextMap.touchZoomRotate.disableRotation();
      nextMap.doubleClickZoom.disable();
      nextMap.keyboard.disable();
      nextMap.on("load", () => {
        if (isDestroyed || mapInstance !== nextMap) return;
        mapReady = true;
        updateMapState(activeCoordinates, markerTrail);
      });
      nextMap.on("moveend", () => {
        if (isDestroyed || mapInstance !== nextMap) return;
        updateLabelPositions();
      });
    })().finally(() => {
      mapInitializationPromise = null;
    });

    return mapInitializationPromise;
  }

  // Reset viewport key when dataset changes
  export function resetViewport() {
    lastViewportKey = "";
  }

  onMount(() => {
    initializeMap();
  });

  onDestroy(() => {
    isDestroyed = true;
    teardownMapInstance();
    if (protocolAcquired) {
      releasePmtilesProtocol();
      protocolAcquired = false;
    }
  });

  $: if (hasMapData) {
    initializeMap();
  }

  $: if (mapReady && hasMapData && !isChapterSlide) {
    updateMapState(activeCoordinates, markerTrail);
    updateMigrationPath(migrationPath);
  }

  $: if (!hasMapData && mapInstance) {
    teardownMapInstance();
  }
</script>

<div
  class="map-overlay"
  class:hidden={activeIndex === 0}
  class:blended-out={isChapterSlide}
  class:depth-fading={depthProgress > 0}
  style="--map-depth-opacity: {Math.max(0, 1 - depthProgress)}"
  aria-hidden="true"
>
  <div class="map-gradient"></div>
  <div class="map-frame">
    <div class="map-container" bind:this={mapContainer}></div>
    {#if basemapError}
      <div class="map-error" role="note">{basemapError}</div>
    {/if}
  </div>
</div>

<style>
  .map-overlay {
    position: absolute;
    inset: auto 0 0;
    height: 45vh;
    pointer-events: none;
    z-index: 1;
    /* Driven from the reader's descent into the slide, so it tracks the
       gesture instead of animating after it. The transition below still
       carries the slide-to-slide fades, which are steps rather than a drag. */
    opacity: var(--map-depth-opacity, 1);
    transition: opacity 0.6s ease;
  }

  /* While the descent is driving the opacity the fade has to keep up with the
     finger; the slower curve above is for fades the reader did not drag. */
  .map-overlay.depth-fading {
    transition: opacity 0.12s linear;
  }

  .map-overlay.hidden {
    opacity: 0;
    pointer-events: none;
  }

  .map-overlay.blended-out {
    opacity: 0;
  }

  .map-gradient {
    position: absolute;
    top: -70px;
    left: 0;
    right: 0;
    height: 200px;
    background: linear-gradient(
      178deg,
      rgba(var(--story-bg-rgb, 15, 23, 42)) 60%,
      rgba(var(--story-bg-rgb, 15, 23, 42), 0.2) 70%,
      rgba(var(--story-bg-rgb, 15, 23, 42), 0) 80%,
      transparent 100%
    );
    z-index: 2;
    pointer-events: none;
  }

  .map-frame {
    padding: 0;
    width: 100%;
    height: 100%;
    box-sizing: border-box;
    position: relative;
    z-index: 1;
  }

  .map-frame::before {
    content: "";
    position: absolute;
    inset: 0;
    background: linear-gradient(
      180deg,
      rgba(var(--story-bg-rgb, 15, 23, 42), 0.55) 0%,
      rgba(var(--story-bg-rgb, 15, 23, 42), 0.25) 45%,
      transparent 80%
    );
    pointer-events: none;
    z-index: 1;
  }

  .map-container {
    width: 100%;
    height: 100%;
    border-radius: 0;
    overflow: hidden;
    border: none;
    box-shadow: none;
    pointer-events: none;
    position: relative;
    background: transparent;
    z-index: 0;
  }

  /* Apply filter only to the MapLibre canvas, not markers */
  :global(.map-container .maplibregl-canvas) {
    filter: contrast(1.45) brightness(1.4) saturate(1.2);
  }

  .map-error {
    position: absolute;
    bottom: 1rem;
    left: 50%;
    transform: translateX(-50%);
    background: rgba(15, 23, 42, 0.9);
    color: #f87171;
    padding: 0.5rem 1rem;
    border-radius: 0.5rem;
    font-size: 0.85rem;
    z-index: 10;
  }

  :global(.story-map-marker-container) {
    display: flex;
    flex-direction: column;
    align-items: center;
    pointer-events: none;
  }

  :global(.story-map-marker) {
    display: block;
    border-radius: 50%;
    border: 2px solid rgba(2, 6, 23, 0.65);
    box-shadow: 0 8px 18px rgba(2, 6, 23, 0.5);
  }

  :global(.story-map-marker.current) {
    border-width: 2.5px;
    border-color: rgba(255, 255, 255, 0.9);
    animation: markerPulse 2s ease-in-out infinite;
  }

  :global(.story-map-label) {
    position: absolute;
    padding: 1px 4px;
    background: rgba(2, 6, 23, 0.35);
    color: rgba(255, 255, 255, 0.75);
    font-size: 11px;
    font-weight: 500;
    white-space: nowrap;
    border-radius: 2px;
    box-shadow: none;
    pointer-events: none;
    text-shadow: 0 1px 3px rgba(0, 0, 0, 0.8);
    letter-spacing: 0.02em;
    max-width: 120px;
    overflow: hidden;
    text-overflow: ellipsis;
    opacity: 0;
    transition: opacity 0.3s ease-out;
  }

  :global(.story-map-label.story-map-label-visible) {
    opacity: 1;
  }

  :global(.story-map-label.story-map-label-hidden) {
    opacity: 0 !important;
    pointer-events: none;
  }

  :global(.story-map-label-top) {
    bottom: 100%;
    margin-bottom: 1px;
  }

  :global(.story-map-label-bottom) {
    top: 100%;
    margin-top: 1px;
  }

  @keyframes markerPulse {
    0%,
    100% {
      box-shadow:
        0 0 8px rgba(255, 255, 255, 0.4),
        0 8px 18px rgba(2, 6, 23, 0.5);
    }
    50% {
      box-shadow:
        0 0 16px rgba(255, 255, 255, 0.6),
        0 8px 18px rgba(2, 6, 23, 0.5);
    }
  }

  :global(.migration-arrow-container) {
    pointer-events: none;
    filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.5));
  }

  @keyframes migrate-flow {
    0% {
      offset-distance: 0%;
      opacity: 0;
    }
    10% {
      opacity: 0.85;
    }
    90% {
      opacity: 0.85;
    }
    100% {
      offset-distance: 100%;
      opacity: 0;
    }
  }
</style>
