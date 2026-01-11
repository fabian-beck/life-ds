<script>
  import { onMount, onDestroy } from "svelte";
  import { currentLanguage, _ } from "../stores/language";
  import maplibregl from "maplibre-gl";
  import { Protocol } from "pmtiles";
  import { layers, namedFlavor } from "@protomaps/basemaps";
  import { normalizeAllLocations, normalizePrimaryLocation } from "../utils/storyHelpers";
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

  // Popup state (Svelte-based, not MapLibre GL)
  let popupData = null;
  let popupPosition = { x: 0, y: 0 };

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

          if (layer.type === "symbol") return false;
          if (lower.includes("label")) return false;
          if (lower.includes("text")) return false;
          if (lower.includes("name")) return false;
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
    console.log('[LandingMap] loadAllEventLocations called with', entries.length, 'entries');
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
            } else {
              console.warn(`[LandingMap] No loader found for ${entry.id}, path: ${path}`);
            }
          }
        })
      );

      await new Promise((resolve) => setTimeout(resolve, 0));
    }

    console.log('[LandingMap] Loaded', features.length, 'location features');

    // Apply collision detection and circular arrangement
    const { markers, connections } = arrangeOverlappingMarkers(features, MAX_CLUSTER_ZOOM, 200);
    connectionLinesData = connections;

    console.log('[LandingMap] Arranged markers:', markers.length, 'Connection lines:', connections.features.length);

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

  async function setupMapLayers(geojsonData) {
    console.log('[LandingMap] setupMapLayers called with', geojsonData.features?.length || 0, 'features');

    mapInstance.addSource("events", {
      type: "geojson",
      data: geojsonData,
      cluster: true,
      clusterMaxZoom: 8,
      clusterRadius: 50,
      clusterProperties: {
        // Collect unique person IDs in cluster
        personIds: ["concat", ["get", "personId"]],
        // Get first person's color (will be used if single person)
        sampleColor: ["coalesce", ["get", "primaryColor"], "#94a3b8"]
      }
    });

    console.log('[LandingMap] Source added');

    // Add source for connection lines (links arranged markers to original position)
    mapInstance.addSource("marker-connections", {
      type: "geojson",
      data: connectionLinesData
    });

    // Add layer for connection lines (drawn BEFORE markers so markers appear on top)
    // Only show when individual markers are visible (zoom > clusterMaxZoom)
    mapInstance.addLayer({
      id: "marker-connection-lines",
      type: "line",
      source: "marker-connections",
      minzoom: 8, // Same as clusterMaxZoom - only show when clusters have resolved
      paint: {
        "line-color": ["get", "color"],
        "line-width": 1,
        "line-opacity": 0.3,
        "line-dasharray": [2, 2]
      }
    });

    // Cluster circles - use person color if single person, gray if multiple
    mapInstance.addLayer({
      id: "clusters",
      type: "circle",
      source: "events",
      filter: ["has", "point_count"],
      paint: {
        "circle-color": [
          "case",
          // Check if personIds array contains only one unique person
          // This is a simplified check - MapLibre doesn't have array uniqueness
          // So we use sampleColor for single-person clusters, gray for multi-person
          ["==", ["length", ["get", "personIds"]], ["get", "point_count"]],
          ["get", "sampleColor"], // Single person - use their color
          "#64748b" // Multiple people - use gray
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

      // Calculate screen position for popup
      const coords = feature.geometry.coordinates;
      const point = mapInstance.project(coords);
      const rect = mapContainer.getBoundingClientRect();

      popupPosition = {
        x: rect.left + point.x,
        y: rect.top + point.y,
      };

      popupData = {
        personName: props.personName,
        eventTitle: props.eventTitle,
        eventDate: props.eventDate || null,
        locationName: props.locationName || null,
        primaryColor: props.primaryColor,
        personId: props.personId,
        eventIndex: parseInt(props.eventIndex, 10),
        coordinates: coords,
      };
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
      if (popupData) {
        const point = mapInstance.project(popupData.coordinates);
        const rect = mapContainer.getBoundingClientRect();
        popupPosition = {
          x: rect.left + point.x,
          y: rect.top + point.y,
        };
      }
    });
  }

  async function initializeMap() {
    console.log('[LandingMap] initializeMap called');
    if (mapInstance || !mapContainer) {
      console.log('[LandingMap] Skipping init - mapInstance exists or no container');
      return;
    }

    isLoading = true;
    const geojsonData = await loadAllEventLocations(filteredEntries);
    isLoading = false;

    console.log('[LandingMap] GeoJSON data:', geojsonData);

    await resolvePmtilesUrl();
    const style = createBaseStyle();

    if (!style) {
      console.error('[LandingMap] No basemap style created');
      return;
    }

    if (!pmtilesProtocol) {
      pmtilesProtocol = new Protocol();
      maplibregl.addProtocol("pmtiles", pmtilesProtocol.tile);
    }

    const initialBounds = calculateInitialBounds(geojsonData);
    console.log('[LandingMap] Initial bounds:', initialBounds);

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
    });

    mapInstance.addControl(new maplibregl.NavigationControl(), "top-right");

    mapInstance.on("load", () => {
      console.log('[LandingMap] Map loaded, setting up layers');
      mapReady = true;
      setupMapLayers(geojsonData);
    });
  }

  async function updateMapData(entries) {
    console.log('[LandingMap] updateMapData called, mapReady:', mapReady, 'entries:', entries.length);
    if (!mapReady || !mapInstance) return;

    isLoading = true;
    const geojsonData = await loadAllEventLocations(entries);
    isLoading = false;

    const source = mapInstance.getSource("events");
    if (source) {
      console.log('[LandingMap] Updating source with', geojsonData.features?.length || 0, 'features');
      source.setData(geojsonData);

      // Update connection lines
      const connectionSource = mapInstance.getSource("marker-connections");
      if (connectionSource) {
        connectionSource.setData(connectionLinesData);
        console.log('[LandingMap] Updated connection lines:', connectionLinesData.features.length);
      }

      const bounds = calculateInitialBounds(geojsonData);
      if (bounds) {
        console.log('[LandingMap] Fitting bounds:', bounds);
        mapInstance.fitBounds(bounds, {
          padding: 80,
          maxZoom: 8,
          duration: 800,
        });
      } else {
        console.warn('[LandingMap] No bounds calculated');
      }
    } else {
      console.error('[LandingMap] No events source found');
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

  onMount(() => {
    initializeMap();
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
</div>

{#if popupData}
  <!-- svelte-ignore a11y-click-events-have-key-events -->
  <!-- svelte-ignore a11y-no-static-element-interactions -->
  <div class="popup-backdrop" on:click={closePopup}></div>
  <!-- svelte-ignore a11y-click-events-have-key-events -->
  <!-- svelte-ignore a11y-no-static-element-interactions -->
  <div
    class="landing-map-popup"
    style="--accent-color: {popupData.primaryColor}; left: {popupPosition.x}px; top: {popupPosition.y}px;"
    on:click|stopPropagation
    role="dialog"
    aria-label="Event details"
  >
    <button class="popup-close" on:click={closePopup} aria-label="Close popup">
      ×
    </button>
    <div class="popup-header">
      <h3 class="popup-person-name">{popupData.personName}</h3>
    </div>
    <div class="popup-body">
      <p class="popup-event-title">{popupData.eventTitle}</p>
      {#if popupData.eventDate}
        <p class="popup-date">{popupData.eventDate}</p>
      {/if}
      {#if popupData.locationName}
        <p class="popup-location">
          <svg width="12" height="12" viewBox="0 0 24 24">
            <path
              fill="currentColor"
              d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"
            />
          </svg>
          {popupData.locationName}
        </p>
      {/if}
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
    min-width: 200px;
    max-width: 280px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5);
    backdrop-filter: blur(8px);
    transform: translate(-50%, -100%);
    margin-top: -15px;
    pointer-events: auto;
  }

  .popup-close {
    position: absolute;
    top: 0.5rem;
    right: 0.5rem;
    background: none;
    border: none;
    color: #cbd5e1;
    font-size: 1.5rem;
    line-height: 1;
    cursor: pointer;
    padding: 0;
    width: 24px;
    height: 24px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: color 0.2s ease;
  }

  .popup-close:hover {
    color: #38bdf8;
  }

  .popup-header {
    margin-bottom: 0.75rem;
    padding-bottom: 0.5rem;
    padding-right: 1.5rem;
    border-bottom: 1px solid rgba(226, 232, 240, 0.15);
  }

  .popup-person-name {
    margin: 0;
    font-size: 1.1rem;
    font-weight: 600;
    color: var(--accent-color, #38bdf8);
  }

  .popup-event-title {
    margin: 0 0 0.5rem;
    font-size: 0.95rem;
    color: #e2e8f0;
    font-weight: 500;
  }

  .popup-date,
  .popup-location {
    margin: 0.25rem 0;
    font-size: 0.85rem;
    color: #94a3b8;
    display: flex;
    align-items: center;
    gap: 0.35rem;
  }

  .popup-cta {
    width: 100%;
    margin-top: 0.75rem;
    padding: 0.6rem;
    background: var(--accent-color, #38bdf8);
    color: #0f172a;
    border: none;
    border-radius: 0.5rem;
    font-weight: 600;
    font-size: 0.9rem;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .popup-cta:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(56, 189, 248, 0.4);
  }
</style>
