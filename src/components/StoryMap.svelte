<script>
  import { tick, onMount, onDestroy } from "svelte";
  import "maplibre-gl/dist/maplibre-gl.css";
  import maplibregl from "maplibre-gl";
  import { Protocol } from "pmtiles";
  import { layers, namedFlavor } from "@protomaps/basemaps";
  import { _ } from "../stores/language";
  import { isCoordinate, parseHexColor, rgbaFromHex } from "../utils/storyHelpers.js";

  export let activeCoordinates = null;
  export let allActiveCoordinates = [];
  export let markerTrail = [];
  export let hasMapData = false;
  export let activeIndex = 0;
  export let styleConfig = null;

  // Local basemap (zoom 0-5) extracted from Protomaps v4 demo bucket.
  const DEFAULT_PM_TILES_URL = "/basemap.pmtiles";
  const PRIMARY_PM_TILES_URL =
    import.meta.env.VITE_PROTOMAPS_PM_TILES_URL ?? DEFAULT_PM_TILES_URL;
  const FALLBACK_PM_TILES_URL =
    import.meta.env.VITE_PROTOMAPS_PM_TILES_FALLBACK_URL ??
    DEFAULT_PM_TILES_URL;

  let pmtilesUrl = PRIMARY_PM_TILES_URL;
  let basemapError = null;
  let basemapResolved = false;
  let mapContainer;
  let mapInstance = null;
  let mapReady = false;
  let currentMarkers = [];
  let trailMarkers = [];
  let lastViewportKey = "";
  let pmtilesProtocol = null;
  let basemapStyleCache = null;

  $: primaryMarkerColor =
    styleConfig?.secondary && parseHexColor(styleConfig.secondary)
      ? styleConfig.secondary
      : "#38BDF8";
  $: fadedMarkerColor =
    rgbaFromHex(primaryMarkerColor, 0.7) ?? "rgba(56, 189, 248, 0.7)";

  async function resolvePmtilesUrl() {
    if (basemapResolved) return pmtilesUrl;
    const candidates = [...new Set([PRIMARY_PM_TILES_URL, FALLBACK_PM_TILES_URL].filter(Boolean))];
    for (const url of candidates) {
      try {
        const res = await fetch(url, { method: "HEAD" });
        if (res.ok) {
          pmtilesUrl = url;
          basemapError = null;
          basemapResolved = true;
          basemapStyleCache = null;
          return pmtilesUrl;
        }
      } catch (_err) {
        // ignore and continue
      }
    }
    basemapError = $_("story.basemap_error");
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
          if (lower.includes("label")) return false;
          if (lower.includes("boundary") || lower.includes("border"))
            return false;
          return true;
        }),
      };
    }
    return JSON.parse(JSON.stringify(basemapStyleCache));
  }

  function createMarkerElement(color, { opacity = 1, size = 14 } = {}) {
    const element = document.createElement("span");
    element.className = "story-map-marker";
    element.style.backgroundColor = color;
    element.style.opacity = `${Math.min(Math.max(opacity, 0), 1)}`;
    const clampedSize = Math.max(size, 6);
    element.style.width = `${clampedSize}px`;
    element.style.height = `${clampedSize}px`;
    return element;
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

  function teardownMapInstance() {
    clearMarkers();
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
    const allActive = Array.isArray(allActiveCoordinates) && allActiveCoordinates.length > 0
      ? allActiveCoordinates.filter(isCoordinate)
      : (active ? [active] : []);

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
          anchor: "bottom",
        })
          .setLngLat([coords.lon, coords.lat])
          .addTo(mapInstance);
        trailMarkers.push(marker);
      }
    }

    if (allActive.length > 0) {
      const primaryIndex = allActive.findIndex(loc => loc.primary === true);
      const primaryLoc = primaryIndex >= 0 ? allActive[primaryIndex] : allActive[0];

      const primaryElement = createMarkerElement(primaryMarkerColor, {
        opacity: 1.0,
        size: 17,
      });
      primaryElement.classList.add("current");
      const primaryMarker = new maplibregl.Marker({
        element: primaryElement,
        anchor: "bottom",
      })
        .setLngLat([primaryLoc.lon, primaryLoc.lat])
        .addTo(mapInstance);
      currentMarkers.push(primaryMarker);

      const secondaryLocs = allActive.filter((_loc, idx) =>
        primaryIndex >= 0 ? idx !== primaryIndex : idx > 0
      );

      for (const coords of secondaryLocs) {
        const markerElement = createMarkerElement(primaryMarkerColor, {
          opacity: 1.0,
          size: 15,
        });
        const marker = new maplibregl.Marker({
          element: markerElement,
          anchor: "bottom",
        })
          .setLngLat([coords.lon, coords.lat])
          .addTo(mapInstance);
        currentMarkers.push(marker);
      }
    }

    const positions = allActive.length > 0
      ? [...allActive, ...history]
      : history;

    if (positions.length === 0) {
      if (lastViewportKey !== "baseline") {
        mapInstance.easeTo({ center: [0, 0], zoom: 1.0, duration: 700 });
        lastViewportKey = "baseline";
      }
      return;
    }

    const viewportKey = positions
      .map((coord) => `${coord.lon.toFixed(4)},${coord.lat.toFixed(4)}`)
      .join("|");

    if (viewportKey === lastViewportKey) {
      return;
    }
    lastViewportKey = viewportKey;

    if (positions.length === 1) {
      mapInstance.easeTo({
        center: [positions[0].lon, positions[0].lat],
        zoom: 5.5,
        duration: 900,
      });
      return;
    }

    const bounds = positions
      .slice(1)
      .reduce(
        (accumulator, coord) => accumulator.extend([coord.lon, coord.lat]),
        new maplibregl.LngLatBounds(
          [positions[0].lon, positions[0].lat],
          [positions[0].lon, positions[0].lat]
        )
      );

    mapInstance.fitBounds(bounds, {
      padding: { top: 100, bottom: 100, left: 60, right: 60 },
      duration: 900,
      maxZoom: 6.5,
    });
  }

  async function initialiseMap() {
    if (mapInstance || !hasMapData) return;
    await tick();
    if (mapInstance || !mapContainer) return;
    await resolvePmtilesUrl();
    const style = createBaseStyle();
    if (!style) {
      return;
    }
    if (!pmtilesProtocol) {
      pmtilesProtocol = new Protocol();
      maplibregl.addProtocol("pmtiles", pmtilesProtocol.tile);
    }
    mapInstance = new maplibregl.Map({
      container: mapContainer,
      style,
      center: [0, 0],
      zoom: 1.0,
      attributionControl: false,
      interactive: false,
    });
    mapInstance.dragPan.disable();
    mapInstance.scrollZoom.disable();
    mapInstance.boxZoom.disable();
    mapInstance.dragRotate.disable();
    mapInstance.touchZoomRotate.disableRotation();
    mapInstance.doubleClickZoom.disable();
    mapInstance.keyboard.disable();
    mapInstance.on("load", () => {
      mapReady = true;
      updateMapState(activeCoordinates, markerTrail);
    });
  }

  // Reset viewport key when dataset changes
  export function resetViewport() {
    lastViewportKey = "";
  }

  onMount(() => {
    initialiseMap();
  });

  onDestroy(() => {
    teardownMapInstance();
    if (pmtilesProtocol && typeof maplibregl.removeProtocol === "function") {
      try {
        maplibregl.removeProtocol("pmtiles");
      } catch (error) {
        // ignore removal issues
      }
    }
    pmtilesProtocol = null;
  });

  $: if (hasMapData) {
    initialiseMap();
  }

  $: if (mapReady && hasMapData) {
    updateMapState(activeCoordinates, markerTrail);
  }

  $: if (!hasMapData && mapInstance) {
    teardownMapInstance();
  }
</script>

<div
  class="map-overlay"
  class:hidden={activeIndex === 0}
  aria-hidden="true"
>
  <div class="map-gradient" />
  <div class="map-frame">
    <div class="map-container" bind:this={mapContainer} />
    {#if basemapError}
      <div class="map-error" role="note">{basemapError}</div>
    {/if}
  </div>
</div>

<style>
  .map-overlay {
    position: absolute;
    inset: auto 0 0;
    height: clamp(240px, 45vh, 340px);
    pointer-events: none;
    z-index: 1;
    opacity: 1;
    transition: opacity 0.3s ease;
  }

  .map-overlay.hidden {
    opacity: 0;
    pointer-events: none;
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
    min-height: clamp(180px, 28vh, 260px);
    border-radius: 0;
    overflow: hidden;
    border: none;
    box-shadow: none;
    pointer-events: none;
    position: relative;
    background: transparent;
    z-index: 0;
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
</style>
