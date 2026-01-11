<script>
  import { onMount, onDestroy } from "svelte";
  import { currentLanguage, _ } from "../stores/language";
  import maplibregl from "maplibre-gl";
  import { Protocol } from "pmtiles";
  import { layers, namedFlavor } from "@protomaps/basemaps";
  import { normalizeAllLocations, normalizePrimaryLocation, formatSingleDate } from "../utils/storyHelpers";
  import { displayName } from "../utils/helpers";
  import { arrangeOverlappingMarkers } from "../utils/mapHelpers";

  export let filteredEntries = [];
  export let getStyle = () => ({});
  export let onNavigate = () => {};

  const DEFAULT_PM_TILES_URL = "/basemap.pmtiles";
  const PRIMARY_PM_TILES_URL =
    import.meta.env.VITE_PROTOMAPS_PM_TILES_URL ?? DEFAULT_PM_TILES_URL;
  const FALLBACK_PM_TILES_URL =
    import.meta.env.VITE_PROTOMAPS_PM_TILES_FALLBACK_URL ?? DEFAULT_PM_TILES_URL;
  const MAX_CLUSTER_ZOOM = 12;

  let mapContainer;
  let mapInstance = null;
  let mapReady = false;
  let isLoading = false;
  let eventDataCache = new Map();
  let pmtilesProtocol = null;
  let pmtilesUrl = PRIMARY_PM_TILES_URL;
  let basemapResolved = false;
  let basemapError = null;
  let basemapStyleCache = null;
  let updateTimeout;
  let connectionLinesData = { type: "FeatureCollection", features: [] };
  let dummyMarkersData = { type: "FeatureCollection", features: [] };

  // Popup state (Svelte-based, not MapLibre GL)
  let popupData = null;
  let popupPosition = { x: 0, y: 0 };
  let popupElement = null;
  let popupPlacement = { anchor: { x: 0.5, y: 1.0 } }; // Default: centered above trigger

  // Top persons display state
  let topPersons = []; // Array of {personId, personName, portraitUrl, primaryColor, count}
  let showTopPersons = false; // Visibility toggle based on event count

  // Map personId to full person data (including portrait info)
  $: personLookup = new Map(
    filteredEntries.map(entry => [entry.id, entry])
  );

  // Date formatters for different precision levels (reactive to language changes)
  $: dateFormatters = {
    year: new Intl.DateTimeFormat($currentLanguage, { year: "numeric" }),
    month: new Intl.DateTimeFormat($currentLanguage, { year: "numeric", month: "long" }),
    day: new Intl.DateTimeFormat($currentLanguage, { year: "numeric", month: "long", day: "numeric" }),
  };

  // Lazy load event data modules
  const datasetModules = import.meta.glob(
    [
      "../../data/people/*/life_events.json",
      "../../data/people/*/de/life_events.json",
      "../../data/people/*/fr/life_events.json",
    ],
    { import: "default" }
  );

  async function resolvePmtilesUrl() {
    if (basemapResolved) return pmtilesUrl;
    const candidates = [
      ...new Set([PRIMARY_PM_TILES_URL, FALLBACK_PM_TILES_URL].filter(Boolean)),
    ];

    const results = await Promise.allSettled(
      candidates.map(async (url) => {
        const res = await fetch(url, { method: "HEAD" });
        if (res.ok) return url;
        throw new Error(`Failed to fetch ${url}`);
      })
    );

    const successfulResult = results.find((r) => r.status === "fulfilled");
    if (successfulResult) {
      pmtilesUrl = successfulResult.value;
      basemapError = null;
      basemapResolved = true;
      basemapStyleCache = null;
      return pmtilesUrl;
    }
    basemapError = $_("landing.map_error");
    basemapResolved = true;
    return null;
  }

  function createBaseStyle() {
    if (basemapError) return null;
    if (
      !basemapStyleCache ||
      !basemapStyleCache.sources?.protomaps?.url?.includes(pmtilesUrl)
    ) {
      basemapStyleCache = {
        version: 8,
        glyphs:
          "https://protomaps.github.io/basemaps-assets/fonts/{fontstack}/{range}.pbf",
        sprite: "https://protomaps.github.io/basemaps-assets/sprites/v4/dark",
        sources: {
          protomaps: {
            type: "vector",
            url: `pmtiles://${pmtilesUrl}`,
            attribution:
              '<a href="https://protomaps.com">Protomaps</a> · <a href="https://www.openstreetmap.org">OpenStreetMap</a>',
          },
        },
        layers: layers("protomaps", namedFlavor("dark"), {
          lang: "en",
          labelsOnly: false,
          landOnly: false,
        }).filter((layer) => {
          const id = layer?.id ?? "";
          if (typeof id !== "string") return true;
          const lower = id.toLowerCase();

          // Keep labels for major features (places, water)
          // Remove boundary/border labels for cleaner look
          if (lower.includes("boundary")) return false;
          if (lower.includes("border")) return false;

          return true;
        }),
      };
    }
    return JSON.parse(JSON.stringify(basemapStyleCache));
  }

  function extractFeatures(personEntry, events) {
    const features = [];
    const personStyle = getStyle(personEntry.id);

    events.forEach((event, eventIndex) => {
      const primaryLocation = normalizePrimaryLocation(event);
      if (primaryLocation) {
        // Find the primary location object to get the name
        const locations = normalizeAllLocations(event);
        const primaryLocationObj = locations.find(loc => loc.primary) || locations[0];

        features.push({
          type: "Feature",
          geometry: { type: "Point", coordinates: [primaryLocation.lon, primaryLocation.lat] },
          properties: {
            personId: personEntry.id,
            personName: displayName(personEntry.name),
            eventIndex,
            eventTitle: event.title,
            eventDate: event.date || "",
            datePrecision: event.date_precision || "day",
            locationName: primaryLocationObj?.name || "Unknown",
            primaryColor: personStyle?.primary || "#38BDF8",
            secondaryColor: personStyle?.secondary || "#9A7BFF",
          },
        });
      }
    });

    return features;
  }

  async function loadAllEventLocations(entries) {
    const features = [];
    const BATCH_SIZE = 10;

    for (let i = 0; i < entries.length; i += BATCH_SIZE) {
      const batch = entries.slice(i, i + BATCH_SIZE);

      await Promise.all(
        batch.map(async (entry) => {
          if (eventDataCache.has(entry.id)) {
            const events = eventDataCache.get(entry.id);
            features.push(...extractFeatures(entry, events));
          } else {
            const lang = $currentLanguage;
            const path =
              lang === "en"
                ? `../../data/people/${entry.id}/life_events.json`
                : `../../data/people/${entry.id}/${lang}/life_events.json`;

            let loader = datasetModules[path];
            if (!loader && lang !== "en") {
              loader = datasetModules[`../../data/people/${entry.id}/life_events.json`];
            }

            if (loader) {
              try {
                const data = await loader();
                const events = data?.events || [];
                eventDataCache.set(entry.id, events);
                features.push(...extractFeatures(entry, events));
              } catch (err) {
                console.warn(`Failed to load events for ${entry.id}:`, err);
              }
            }
          }
        })
      );

      await new Promise((resolve) => setTimeout(resolve, 0));
    }

    // Apply collision detection and circular arrangement
    const { markers, connections, dummies } = arrangeOverlappingMarkers(features, MAX_CLUSTER_ZOOM, 200);
    connectionLinesData = connections;
    dummyMarkersData = dummies;

    return { type: "FeatureCollection", features: markers };
  }

  function calculateInitialBounds(geojsonData) {
    if (!geojsonData.features || geojsonData.features.length === 0) {
      return null;
    }

    const bounds = new maplibregl.LngLatBounds();

    for (const feature of geojsonData.features) {
      const coords = feature.geometry.coordinates;
      bounds.extend([coords[0], coords[1]]);
    }

    return bounds;
  }

  // Helper function to parse hex color to RGB
  function hexToRgb(hex) {
    const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
    return result ? {
      r: parseInt(result[1], 16),
      g: parseInt(result[2], 16),
      b: parseInt(result[3], 16)
    } : null;
  }

  // Helper function to convert RGB to hex
  function rgbToHex(r, g, b) {
    return "#" + [r, g, b].map(x => {
      const hex = Math.round(x).toString(16);
      return hex.length === 1 ? "0" + hex : hex;
    }).join('');
  }

  // Handle person card click to navigate to their story
  function handlePersonCardClick(personId) {
    // Find first event for this person in current viewport
    const visibleFeatures = mapInstance.queryRenderedFeatures({
      layers: ['unclustered-point']
    }).filter(f => f.properties.personId === personId);

    if (visibleFeatures.length > 0) {
      const firstEvent = visibleFeatures[0].properties;
      onNavigate({
        personId: firstEvent.personId,
        eventIndex: parseInt(firstEvent.eventIndex, 10)
      });
    }
  }

  // Update top persons display based on visible events
  function updateTopPersons() {
    if (!mapReady || !mapInstance) return;

    const source = mapInstance.getSource('events');
    if (!source || !source._data) return;

    // Get current map bounds
    const bounds = mapInstance.getBounds();

    // Query source features within bounds (includes ALL features, not just rendered)
    const allFeatures = source._data.features || [];
    const featuresInBounds = allFeatures.filter(feature => {
      const [lng, lat] = feature.geometry.coordinates;
      return bounds.contains([lng, lat]);
    });

    const totalVisible = featuresInBounds.length;

    // Show portraits only when < 50 total events visible in viewport
    showTopPersons = totalVisible > 0 && totalVisible < 50;

    // Count events per person from all features in bounds
    const personCounts = new Map();

    featuresInBounds.forEach(feature => {
      const personId = feature.properties.personId;
      personCounts.set(personId, (personCounts.get(personId) || 0) + 1);
    });

    if (showTopPersons) {
      // Sort persons by event count (descending) and take top 3
      const sorted = Array.from(personCounts.entries())
        .sort((a, b) => b[1] - a[1])
        .slice(0, 3);

      topPersons = sorted.map(([personId, count]) => {
        const person = personLookup.get(personId);
        const style = getStyle(personId);

        return {
          personId,
          personName: person?.name?.replace(/_/g, ' ') || personId,
          portraitUrl: person?.portrait?.thumbnail || person?.portrait?.image || null,
          primaryColor: style?.primary || '#38BDF8',
          count
        };
      });
    } else {
      topPersons = [];
    }
  }

  // Interpolate between person color and gray based on dominance percentage
  function interpolateColor(personColor, percentage) {
    const grayColor = "#64748b"; // Neutral gray for mixed clusters
    const personRgb = hexToRgb(personColor);
    const grayRgb = hexToRgb(grayColor);

    if (!personRgb || !grayRgb) return grayColor;

    // Map percentage from 0.5-1.0 range to 0-1 interpolation factor
    // At 50%: factor = 0 (full gray)
    // At 100%: factor = 1 (full person color)
    const factor = (percentage - 0.5) / 0.5;

    // Linear interpolation between gray and person color
    const r = grayRgb.r + (personRgb.r - grayRgb.r) * factor;
    const g = grayRgb.g + (personRgb.g - grayRgb.g) * factor;
    const b = grayRgb.b + (personRgb.b - grayRgb.b) * factor;

    return rgbToHex(r, g, b);
  }

  // Calculate dominant person color for a cluster (>50% threshold)
  function getClusterDominantColor(clusterId, callback) {
    const source = mapInstance.getSource("events");
    if (!source) return callback("#64748b"); // Default gray

    source.getClusterLeaves(clusterId, Infinity, 0, (err, features) => {
      if (err || !features || features.length === 0) {
        return callback("#64748b");
      }

      // Count person occurrences
      const personCounts = {};
      const personColors = {};

      features.forEach(feature => {
        const personId = feature.properties.personId;
        const color = feature.properties.primaryColor;

        personCounts[personId] = (personCounts[personId] || 0) + 1;
        personColors[personId] = color;
      });

      // Find person with most events
      let maxCount = 0;
      let dominantPerson = null;

      for (const [personId, count] of Object.entries(personCounts)) {
        if (count > maxCount) {
          maxCount = count;
          dominantPerson = personId;
        }
      }

      // Check if dominant person has >50%
      const totalCount = features.length;
      const percentage = maxCount / totalCount;

      if (dominantPerson && percentage > 0.5) {
        const interpolatedColor = interpolateColor(personColors[dominantPerson], percentage);
        callback(interpolatedColor);
      } else {
        callback("#64748b"); // Gray for mixed clusters
      }
    });
  }

  async function setupMapLayers(geojsonData) {
    mapInstance.addSource("events", {
      type: "geojson",
      data: geojsonData,
      cluster: true,
      clusterMaxZoom: 8,
      clusterRadius: 50,
      clusterProperties: {
        // Collect all person IDs in cluster (concatenated string)
        personIds: ["concat", ["get", "personId"]],
        // Get first person's color as fallback
        sampleColor: ["coalesce", ["get", "primaryColor"], "#94a3b8"]
      }
    });

    // Add source for connection lines (links arranged markers to original position)
    mapInstance.addSource("marker-connections", {
      type: "geojson",
      data: connectionLinesData
    });

    // Add source for dummy markers (original positions)
    mapInstance.addSource("dummy-markers", {
      type: "geojson",
      data: dummyMarkersData
    });

    // Add layer for dummy markers (small, non-interactive circles at original positions)
    // Only show when clusters have fully resolved (one zoom level past clusterMaxZoom)
    mapInstance.addLayer({
      id: "dummy-marker-points",
      type: "circle",
      source: "dummy-markers",
      minzoom: 9, // One level past clusterMaxZoom to ensure clusters are fully resolved
      paint: {
        "circle-color": ["get", "color"],
        "circle-radius": 4,
        "circle-opacity": 1.0,
        "circle-stroke-width": 1,
        "circle-stroke-color": "rgba(255, 255, 255, 0.8)",
        "circle-stroke-opacity": 1.0
      }
    });

    // Add layer for connection lines (drawn AFTER dummy markers but BEFORE regular markers)
    // Only show when clusters have fully resolved (one zoom level past clusterMaxZoom)
    mapInstance.addLayer({
      id: "marker-connection-lines",
      type: "line",
      source: "marker-connections",
      minzoom: 9, // One level past clusterMaxZoom to ensure clusters are fully resolved
      paint: {
        "line-color": ["get", "color"],
        "line-width": 1,
        "line-opacity": 0.3,
        "line-dasharray": [2, 2]
      }
    });

    // Cluster circles - colored by dominant person (>50% threshold)
    mapInstance.addLayer({
      id: "clusters",
      type: "circle",
      source: "events",
      filter: ["has", "point_count"],
      paint: {
        "circle-color": [
          "case",
          // Use feature-state color if available, otherwise fallback to gray
          ["!=", ["feature-state", "dominantColor"], null],
          ["feature-state", "dominantColor"],
          "#64748b" // Default gray while calculating
        ],
        "circle-radius": [
          "step",
          ["get", "point_count"],
          20,
          10,
          30,
          50,
          40,
          100,
          50,
        ],
        "circle-stroke-width": 2,
        "circle-stroke-color": "rgba(255, 255, 255, 0.6)",
        "circle-opacity": 0.75,
      },
    });

    // Cluster count labels
    mapInstance.addLayer({
      id: "cluster-count",
      type: "symbol",
      source: "events",
      filter: ["has", "point_count"],
      layout: {
        "text-field": ["get", "point_count_abbreviated"],
        "text-font": ["Noto Sans Regular"],
        "text-size": 14,
      },
      paint: {
        "text-color": "#ffffff",
        "text-halo-color": "rgba(0, 0, 0, 0.5)",
        "text-halo-width": 1,
      },
    });

    // Unclustered points
    mapInstance.addLayer({
      id: "unclustered-point",
      type: "circle",
      source: "events",
      filter: ["!", ["has", "point_count"]],
      paint: {
        "circle-color": ["get", "primaryColor"],
        "circle-radius": 8,
        "circle-stroke-width": 2,
        "circle-stroke-color": "rgba(255, 255, 255, 0.8)",
        "circle-opacity": 0.85,
        "circle-stroke-opacity": 0.9,
      },
    });

    // Cursor changes
    mapInstance.on("mouseenter", "clusters", () => {
      mapInstance.getCanvas().style.cursor = "pointer";
    });
    mapInstance.on("mouseleave", "clusters", () => {
      mapInstance.getCanvas().style.cursor = "";
    });
    mapInstance.on("mouseenter", "unclustered-point", () => {
      mapInstance.getCanvas().style.cursor = "pointer";
    });
    mapInstance.on("mouseleave", "unclustered-point", () => {
      mapInstance.getCanvas().style.cursor = "";
    });

    // Click handlers
    mapInstance.on("click", "clusters", (e) => {
      const features = mapInstance.queryRenderedFeatures(e.point, {
        layers: ["clusters"],
      });

      if (!features.length) return;

      const clusterId = features[0].properties.cluster_id;
      const currentZoom = mapInstance.getZoom();

      mapInstance.getSource("events").getClusterExpansionZoom(clusterId, (err, zoom) => {
        if (err) return;

        // Cap the maximum zoom level to prevent zooming in too far
        // This is important because some markers may be at the same location
        // and won't resolve even at high zoom levels
        const targetZoom = Math.min(zoom, MAX_CLUSTER_ZOOM);

        // If we're already at or very close to the max zoom, don't try to expand
        // This prevents zooming when points are too close together to resolve
        if (currentZoom >= MAX_CLUSTER_ZOOM - 0.5) {
          return;
        }

        mapInstance.easeTo({
          center: features[0].geometry.coordinates,
          zoom: targetZoom,
          duration: 500,
        });
      });
    });

    mapInstance.on("click", "unclustered-point", (e) => {
      const features = mapInstance.queryRenderedFeatures(e.point, {
        layers: ["unclustered-point"],
      });

      if (!features.length) return;

      const feature = features[0];
      const props = feature.properties;

      // Store coordinates for later positioning
      const coords = feature.geometry.coordinates;

      // Get person data for portrait
      const person = filteredEntries.find(entry => entry.id === props.personId);
      const portraitUrl = person?.portrait?.thumbnail || person?.portrait?.image || null;

      // Format date nicely based on precision
      const formattedDate = props.eventDate
        ? formatSingleDate(props.eventDate, props.datePrecision, dateFormatters)
        : null;

      popupData = {
        personName: props.personName,
        eventTitle: props.eventTitle,
        eventDate: formattedDate,
        locationName: props.locationName || null,
        primaryColor: props.primaryColor,
        personId: props.personId,
        eventIndex: parseInt(props.eventIndex, 10),
        coordinates: coords,
        portraitUrl: portraitUrl,
      };

      // Position popup after it's rendered
      requestAnimationFrame(() => {
        if (popupElement && mapInstance && mapContainer) {
          calculatePopupPosition(coords);
        }
      });
    });

    // Close popup on map click (but not on popup itself)
    mapInstance.on("click", (e) => {
      const features = mapInstance.queryRenderedFeatures(e.point, {
        layers: ["unclustered-point"],
      });

      if (!features.length) {
        popupData = null;
      }
    });

    // Update popup position on map move
    mapInstance.on("move", () => {
      if (popupData && popupElement && mapInstance && mapContainer) {
        calculatePopupPosition(popupData.coordinates);
      }
    });

    // Update cluster colors based on dominant person (>50% threshold)
    function updateClusterColors() {
      const clusters = mapInstance.querySourceFeatures("events", {
        filter: ["has", "point_count"],
        sourceLayer: null
      });

      clusters.forEach(cluster => {
        const clusterId = cluster.properties.cluster_id;

        getClusterDominantColor(clusterId, (color) => {
          mapInstance.setFeatureState(
            { source: "events", id: clusterId },
            { dominantColor: color }
          );
        });
      });
    }

    // Initial color update
    updateClusterColors();

    // Initial top persons update
    updateTopPersons();

    // Update colors when map moves or zooms (clusters may change)
    mapInstance.on("moveend", updateClusterColors);
    mapInstance.on("zoomend", updateClusterColors);

    // Update top persons when map moves or zooms
    // Use moveend only (fires after both pan and zoom)
    mapInstance.on('moveend', updateTopPersons);

    // Close popup when user starts interacting with map (scroll/zoom/pan)
    mapInstance.on('movestart', () => {
      if (popupData) {
        closePopup();
      }
    });
    mapInstance.on('zoomstart', () => {
      if (popupData) {
        closePopup();
      }
    });
  }

  // Smart popup positioning to prevent clipping (similar to MetaStoryTimeline approach)
  function calculatePopupPosition(coordinates) {
    if (!popupElement || !mapInstance || !mapContainer) return;

    // Get marker position on screen
    const point = mapInstance.project(coordinates);
    const mapRect = mapContainer.getBoundingClientRect();

    // Marker position in viewport coordinates
    const markerX = mapRect.left + point.x;
    const markerY = mapRect.top + point.y;

    // Measure tooltip dimensions
    const tooltipRect = popupElement.getBoundingClientRect();
    const tooltipWidth = tooltipRect.width;
    const tooltipHeight = tooltipRect.height;

    // Viewport constraints (with padding)
    const padding = 16;
    const viewportLeft = padding;
    const viewportTop = padding;
    const viewportRight = window.innerWidth - padding;
    const viewportBottom = window.innerHeight - padding;

    // Space available around marker
    const spaceAbove = markerY - viewportTop;
    const spaceBelow = viewportBottom - markerY;

    // Determine optimal placement
    let anchorX = 0.5; // Default: centered horizontally
    let anchorY = 1.0; // Default: positioned above marker (bottom of tooltip at marker)
    let finalX = markerX;
    let finalY = markerY;

    // Vertical placement: prefer top, fall back to bottom
    if (spaceAbove >= tooltipHeight + 15) {
      // Position above marker
      anchorY = 1.0;
      finalY = markerY - 15; // 15px clearance from marker
    } else if (spaceBelow >= tooltipHeight + 15) {
      // Position below marker
      anchorY = 0.0;
      finalY = markerY + 15; // 15px clearance from marker
    } else {
      // Not enough space either way - prefer top but clamp
      anchorY = 1.0;
      finalY = Math.max(viewportTop + tooltipHeight, markerY - 15);
    }

    // Horizontal centering with boundary checks
    const halfWidth = tooltipWidth / 2;

    // Calculate what the final position would be if centered
    let tentativeX = markerX;
    let tentativeAnchorX = 0.5;

    // Check if centering would cause left overflow
    if (markerX - halfWidth < viewportLeft) {
      // Too close to left edge - align left edge of popup to viewport padding
      tentativeAnchorX = 0.0;
      tentativeX = viewportLeft;
    }
    // Check if centering would cause right overflow
    else if (markerX + halfWidth > viewportRight) {
      // Too close to right edge - align right edge of popup to viewport padding
      tentativeAnchorX = 1.0;
      tentativeX = viewportRight;
    }
    // Enough space to center
    else {
      tentativeAnchorX = 0.5;
      tentativeX = markerX;
    }

    anchorX = tentativeAnchorX;
    finalX = tentativeX;

    // Update placement state
    popupPlacement = { anchor: { x: anchorX, y: anchorY } };
    popupPosition = { x: finalX, y: finalY };
  }

  async function initializeMap() {
    if (mapInstance || !mapContainer) {
      return;
    }

    isLoading = true;
    const geojsonData = await loadAllEventLocations(filteredEntries);
    isLoading = false;

    await resolvePmtilesUrl();
    const style = createBaseStyle();

    if (!style) {
      return;
    }

    if (!pmtilesProtocol) {
      pmtilesProtocol = new Protocol();
      maplibregl.addProtocol("pmtiles", pmtilesProtocol.tile);
    }

    const initialBounds = calculateInitialBounds(geojsonData);

    mapInstance = new maplibregl.Map({
      container: mapContainer,
      style: style,
      bounds: initialBounds || undefined,
      fitBoundsOptions: {
        padding: { top: 80, bottom: 80, left: 80, right: 80 },
        maxZoom: 8,
      },
      interactive: true,
      attributionControl: false,
      pitchWithRotate: false,
      dragRotate: false,
      touchPitch: false,
      touchZoomRotate: true,
      bearingSnap: 0,
    });

    // Disable rotation completely, even with touch gestures (allows zoom only)
    mapInstance.touchZoomRotate.disableRotation();

    // Add navigation control without compass (rotation disabled)
    mapInstance.addControl(
      new maplibregl.NavigationControl({ showCompass: false }),
      "top-right"
    );

    // Add custom zoom reset button
    class ZoomResetControl {
      onAdd(map) {
        this._map = map;
        this._container = document.createElement("div");
        this._container.className = "maplibregl-ctrl maplibregl-ctrl-group";
        this._container.innerHTML = `
          <button type="button" class="maplibregl-ctrl-zoom-reset" title="Reset zoom">
            <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor">
              <path d="M10 3C6.13 3 3 6.13 3 10s3.13 7 7 7 7-3.13 7-7-3.13-7-7-7zm0 12c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5z"/>
              <circle cx="10" cy="10" r="2"/>
            </svg>
          </button>
        `;
        this._container.querySelector("button").addEventListener("click", () => {
          const bounds = calculateInitialBounds({ type: "FeatureCollection", features: mapInstance.getSource("events")?._data?.features || [] });
          if (bounds) {
            map.fitBounds(bounds, {
              padding: 80,
              maxZoom: 8,
              duration: 800,
            });
          }
        });
        return this._container;
      }

      onRemove() {
        this._container.parentNode.removeChild(this._container);
        this._map = undefined;
      }
    }

    mapInstance.addControl(new ZoomResetControl(), "top-right");

    mapInstance.on("load", () => {
      mapReady = true;
      setupMapLayers(geojsonData);
    });
  }

  async function updateMapData(entries) {
    if (!mapReady || !mapInstance) return;

    isLoading = true;
    const geojsonData = await loadAllEventLocations(entries);
    isLoading = false;

    const source = mapInstance.getSource("events");
    if (source) {
      source.setData(geojsonData);

      // Update connection lines
      const connectionSource = mapInstance.getSource("marker-connections");
      if (connectionSource) {
        connectionSource.setData(connectionLinesData);
      }

      // Update dummy markers
      const dummySource = mapInstance.getSource("dummy-markers");
      if (dummySource) {
        dummySource.setData(dummyMarkersData);
      }

      const bounds = calculateInitialBounds(geojsonData);
      if (bounds) {
        mapInstance.fitBounds(bounds, {
          padding: 80,
          maxZoom: 8,
          duration: 800,
        });
      }
    }
  }

  // Popup handlers
  function handlePopupNavigate() {
    if (popupData) {
      onNavigate({
        personId: popupData.personId,
        eventIndex: popupData.eventIndex,
      });
      popupData = null;
    }
  }

  function closePopup() {
    popupData = null;
  }

  // Debounced reactive update
  $: {
    if (updateTimeout) clearTimeout(updateTimeout);
    updateTimeout = setTimeout(() => {
      if (mapReady) updateMapData(filteredEntries);
    }, 300);
  }

  // Handle wheel events on the entire page to close popup
  function handleWheel() {
    if (popupData) {
      closePopup();
    }
  }

  onMount(() => {
    initializeMap();

    // Add wheel event listener to window for mouse wheel scrolling
    window.addEventListener('wheel', handleWheel, { passive: true });
  });

  onDestroy(() => {
    if (mapInstance) {
      mapInstance.remove();
      mapInstance = null;
    }
    if (pmtilesProtocol) {
      maplibregl.removeProtocol("pmtiles");
      pmtilesProtocol = null;
    }
    eventDataCache.clear();

    // Clean up wheel event listener
    window.removeEventListener('wheel', handleWheel);
  });
</script>

<div class="landing-map-container">
  {#if isLoading}
    <div class="loading-overlay">
      <p>{$_("landing.map_loading")}</p>
    </div>
  {/if}
  {#if basemapError}
    <div class="error-overlay">
      <p>{basemapError}</p>
    </div>
  {/if}
  <div bind:this={mapContainer} class="map"></div>

  {#if showTopPersons && topPersons.length > 0}
    <div class="top-persons-overlay">
      {#each topPersons as person (person.personId)}
        <!-- svelte-ignore a11y-click-events-have-key-events -->
        <!-- svelte-ignore a11y-no-static-element-interactions -->
        <div
          class="person-card"
          style="--person-color: {person.primaryColor}"
          on:click={() => handlePersonCardClick(person.personId)}
          role="button"
          tabindex="0"
          aria-label="View {person.personName}'s story"
        >
          {#if person.portraitUrl}
            <img
              src={person.portraitUrl}
              alt={person.personName}
              class="person-portrait"
            />
          {:else}
            <div class="person-portrait-placeholder" style="background: {person.primaryColor}">
              {person.personName.charAt(0)}
            </div>
          {/if}
          <div class="person-info">
            <div class="person-name">{person.personName}</div>
            <div class="person-count">{person.count} {person.count === 1 ? 'event' : 'events'}</div>
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>

{#if popupData}
  <!-- svelte-ignore a11y-click-events-have-key-events -->
  <!-- svelte-ignore a11y-no-static-element-interactions -->
  <div class="popup-backdrop" on:click={closePopup}></div>
  <!-- svelte-ignore a11y-click-events-have-key-events -->
  <!-- svelte-ignore a11y-no-static-element-interactions -->
  <div
    bind:this={popupElement}
    class="landing-map-popup"
    style="
      --accent-color: {popupData.primaryColor};
      --anchor-x: {popupPlacement.anchor.x};
      --anchor-y: {popupPlacement.anchor.y};
      left: {popupPosition.x}px;
      top: {popupPosition.y}px;
    "
    on:click|stopPropagation
    role="dialog"
    aria-label="Event details"
  >
    <div class="popup-content">
      {#if popupData.portraitUrl}
        <img
          src={popupData.portraitUrl}
          alt={popupData.personName}
          class="popup-portrait"
        />
      {:else}
        <div class="popup-portrait-placeholder" style="background: {popupData.primaryColor}">
          {popupData.personName.charAt(0)}
        </div>
      {/if}
      <div class="popup-text">
        <h3 class="popup-person-name">{popupData.personName}</h3>
        <p class="popup-event-title">{popupData.eventTitle}</p>
        {#if popupData.eventDate || popupData.locationName}
          <div class="popup-metadata">
            {#if popupData.eventDate}
              <span class="popup-date">{popupData.eventDate}</span>
            {/if}
            {#if popupData.locationName}
              <span class="popup-location">
                <svg width="12" height="12" viewBox="0 0 24 24">
                  <path
                    fill="currentColor"
                    d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"
                  />
                </svg>
                {popupData.locationName}
              </span>
            {/if}
          </div>
        {/if}
      </div>
    </div>
    <button class="popup-cta" on:click={handlePopupNavigate}>
      {$_("landing.map_view_story")}
    </button>
  </div>
{/if}

<style>
  .landing-map-container {
    position: relative;
    width: 100%;
    height: 100%;
  }

  .map {
    width: 100%;
    height: 100%;
  }

  .loading-overlay,
  .error-overlay {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(15, 23, 42, 0.9);
    color: #cbd5e1;
    z-index: 10;
    font-size: 1rem;
  }

  .error-overlay {
    color: #f87171;
  }

  .popup-backdrop {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 9998;
    background: transparent;
  }

  .landing-map-popup {
    position: fixed;
    z-index: 9999;
    background: rgba(15, 23, 42, 0.96);
    border: 1px solid var(--accent-color, #38bdf8);
    border-radius: 0.75rem;
    padding: 1rem;
    width: 340px;
    max-width: 85vw;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5);
    backdrop-filter: blur(8px);
    pointer-events: auto;

    /* Dynamic transform based on anchor point (similar to MetaStoryTimeline) */
    transform: translate(
      calc(-100% * var(--anchor-x, 0.5)),
      calc(-100% * var(--anchor-y, 1.0))
    );

    /* Smooth appearance animation */
    animation: fadeInPopup 0.2s ease;
  }

  @keyframes fadeInPopup {
    from {
      opacity: 0;
      transform: translate(
        calc(-100% * var(--anchor-x, 0.5)),
        calc(-100% * var(--anchor-y, 1.0) - 10px)
      );
    }
    to {
      opacity: 1;
      transform: translate(
        calc(-100% * var(--anchor-x, 0.5)),
        calc(-100% * var(--anchor-y, 1.0))
      );
    }
  }

  .popup-content {
    display: flex;
    align-items: flex-start;
    gap: 0.75rem;
    margin-bottom: 0.75rem;
  }

  .popup-portrait {
    width: 80px;
    height: auto;
    object-fit: contain;
    object-position: center;
    flex-shrink: 0;
    mix-blend-mode: lighten;
  }

  .popup-portrait-placeholder {
    width: 80px;
    height: 80px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 2rem;
    font-weight: 700;
    color: #0f172a;
    background: var(--accent-color, #38bdf8);
    flex-shrink: 0;
  }

  .popup-text {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }

  .popup-person-name {
    margin: 0;
    font-size: 1rem;
    font-weight: 600;
    color: var(--accent-color, #38bdf8);
    font-family: var(--heading-font, 'Space Grotesk', sans-serif);
    line-height: 1.2;
  }

  .popup-event-title {
    margin: 0;
    font-size: 0.875rem;
    color: #cbd5e1;
    font-weight: 500;
    font-family: var(--body-font, 'IBM Plex Sans', sans-serif);
    line-height: 1.3;
  }

  .popup-metadata {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 1rem;
    margin-top: 0.25rem;
  }

  .popup-date {
    font-size: 0.85rem;
    color: #94a3b8;
    font-family: var(--body-font, 'IBM Plex Sans', sans-serif);
    white-space: nowrap;
  }

  .popup-location {
    font-size: 0.85rem;
    color: #94a3b8;
    display: flex;
    align-items: center;
    gap: 0.35rem;
    font-family: var(--body-font, 'IBM Plex Sans', sans-serif);
    text-align: right;
    margin-left: auto;
  }

  .popup-cta {
    width: 100%;
    margin-top: 0;
    padding: 0.6rem;
    background: var(--accent-color, #38bdf8);
    color: #0f172a;
    border: none;
    border-radius: 0.5rem;
    font-weight: 600;
    font-size: 0.9rem;
    font-family: var(--body-font, 'IBM Plex Sans', sans-serif);
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .popup-cta:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(var(--accent-color-rgb, 56, 189, 248), 0.4);
  }

  .popup-cta:focus-visible {
    outline: 2px solid var(--accent-color, #38bdf8);
    outline-offset: 2px;
  }

  .popup-cta:active {
    transform: translateY(0);
  }

  .top-persons-overlay {
    position: absolute;
    bottom: 1rem;
    left: 1rem;
    z-index: 100;
    display: flex;
    flex-direction: row;
    gap: 1rem;
    pointer-events: none;
  }

  .person-card {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    background: none;
    border: none;
    border-radius: 0;
    padding: 0;
    backdrop-filter: none;
    box-shadow: none;
    animation: fadeIn 0.3s ease-out;
    pointer-events: auto;
    cursor: pointer;
    transition: transform 0.2s ease, opacity 0.2s ease;
  }

  .person-card:hover {
    transform: translateY(-2px);
    opacity: 0.85;
  }

  @keyframes fadeIn {
    from {
      opacity: 0;
    }
    to {
      opacity: 1;
    }
  }

  .person-portrait {
    width: 48px;
    height: 48px;
    border-radius: 50%;
    object-fit: cover;
    border: 2px solid var(--person-color, #38bdf8);
    flex-shrink: 0;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.6);
  }

  .person-portrait-placeholder {
    width: 48px;
    height: 48px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.25rem;
    font-weight: 700;
    color: #0f172a;
    flex-shrink: 0;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.6);
  }

  .person-info {
    display: flex;
    flex-direction: column;
    gap: 0.1rem;
    min-width: 0;
  }

  .person-name {
    font-size: 0.75rem;
    font-weight: 600;
    color: #e2e8f0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    text-shadow:
      0 0 4px rgba(0, 0, 0, 1),
      0 0 8px rgba(0, 0, 0, 0.8),
      0 1px 3px rgba(0, 0, 0, 0.9);
  }

  .person-count {
    font-size: 0.65rem;
    color: #cbd5e1;
    text-shadow:
      0 0 4px rgba(0, 0, 0, 1),
      0 0 8px rgba(0, 0, 0, 0.8),
      0 1px 3px rgba(0, 0, 0, 0.9);
  }

  /* Responsive adjustments for mobile */
  @media (max-width: 640px) {
    .landing-map-popup {
      max-width: calc(100vw - 2rem);
      min-width: 200px;
      padding: 0.875rem;
    }

    .popup-portrait {
      width: 60px;
    }

    .popup-portrait-placeholder {
      width: 60px;
      height: 60px;
      font-size: 1.5rem;
    }

    .popup-person-name {
      font-size: 0.9rem;
    }

    .popup-event-title {
      font-size: 0.8rem;
    }

    .popup-date,
    .popup-location {
      font-size: 0.75rem;
    }

    .popup-cta {
      padding: 0.55rem;
      font-size: 0.85rem;
    }

    .top-persons-overlay {
      bottom: 0.5rem;
      left: 0.5rem;
      max-width: calc(100% - 1rem);
      gap: 0.4rem;
    }

    .person-portrait,
    .person-portrait-placeholder {
      width: 28px;
      height: 28px;
    }

    .person-name {
      font-size: 0.7rem;
    }

    .person-count {
      font-size: 0.6rem;
    }
  }
</style>
