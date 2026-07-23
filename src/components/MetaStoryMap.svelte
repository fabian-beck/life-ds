<script>
  import { onMount, onDestroy } from "svelte";
  import "maplibre-gl/dist/maplibre-gl.css";
  import maplibregl from "maplibre-gl";
  import { Protocol } from "pmtiles";
  import { layers, namedFlavor } from "@protomaps/basemaps";
  import { _ } from "../stores/language.js";
  import { displayName } from "../utils/helpers.js";
  import { generateNameVariants } from "../utils/storyHelpers.js";
  import { saveMetaStoryScroll } from "../stores/metaStoryScroll.js";
  import personStylesData from "../../data/person_styles.json";

  // The `geo_map` block from a meta story: { clusters: [...], narration? }
  export let geoMap = null;
  export let currentLanguage = "en";
  // Meta story id, so an event link can carry the `from_meta` context that
  // returns the reader here (with scroll restored) on closing the story.
  export let metaStoryId = null;

  const personStyles = personStylesData.styles;

  // How many events a stop card spells out before summarizing the rest.
  const MAX_CARD_EVENTS = 4;

  // Local basemap (zoom 0-5) extracted from Protomaps v4 demo bucket.
  const DEFAULT_PM_TILES_URL = "/basemap.pmtiles";
  const PRIMARY_PM_TILES_URL =
    import.meta.env.VITE_PROTOMAPS_PM_TILES_URL ?? DEFAULT_PM_TILES_URL;
  const FALLBACK_PM_TILES_URL =
    import.meta.env.VITE_PROTOMAPS_PM_TILES_FALLBACK_URL ??
    DEFAULT_PM_TILES_URL;

  function primaryColor(personId) {
    return personStyles[personId]?.primary || "#38bdf8";
  }

  // Hash-router link to the exact event slide in the person's own story. The
  // `event` query param addresses the life_events.json index (event index ≠
  // slide index when chapters exist), and `from_meta` lets the story's close
  // button return to this meta story.
  function eventHref(event) {
    const idx = event.event_index != null ? event.event_index : 0;
    return (
      `#/${currentLanguage}/story/${event.person_id}?event=${idx}` +
      (metaStoryId ? `&from_meta=${metaStoryId}` : "")
    );
  }

  // Remember where the reader left the meta story before jumping into a story,
  // so returning restores this scroll position (matches the network/timeline).
  function openStory() {
    if (metaStoryId) saveMetaStoryScroll(metaStoryId);
  }

  $: clusters = geoMap?.clusters ?? [];
  $: hasMap = clusters.length > 0;

  // Narration stops matched to clusters by key; cards without a text fall
  // back to listing the cluster's events.
  $: stopTexts = new Map(
    (geoMap?.narration?.stops || []).map((s) => [s.key, s.text])
  );
  $: stopTitles = new Map(
    (geoMap?.narration?.stops || [])
      .filter((s) => s.title)
      .map((s) => [s.key, s.title])
  );

  // Unique people per cluster (for name emphasis in the narration text).
  function clusterPeople(cluster) {
    const seen = new Map();
    for (const event of cluster.events || []) {
      if (!seen.has(event.person_id)) {
        seen.set(event.person_id, {
          id: event.person_id,
          name: event.person_name,
        });
      }
    }
    return [...seen.values()];
  }

  // Highlight each member's name where it appears in the narration text —
  // the same .person-mention treatment used in the network cards.
  function highlightNarration(text, cluster) {
    if (!text) return [{ type: "text", content: "" }];
    const people = clusterPeople(cluster);

    const matches = [];
    for (const person of people) {
      let best = null;
      for (const variant of generateNameVariants(person.name)) {
        variant.regex.lastIndex = 0;
        let m;
        while ((m = variant.regex.exec(text)) !== null) {
          const cand = {
            start: m.index,
            end: variant.regex.lastIndex,
            len: m[0].length,
            priority: variant.priority,
            person,
          };
          if (
            !best ||
            cand.priority < best.priority ||
            (cand.priority === best.priority && cand.len > best.len)
          ) {
            best = cand;
          }
        }
      }
      if (best) matches.push(best);
    }

    matches.sort((a, b) => a.start - b.start || b.len - a.len);
    const segments = [];
    let cursor = 0;
    for (const match of matches) {
      if (match.start < cursor) continue;
      if (match.start > cursor) {
        segments.push({
          type: "text",
          content: text.slice(cursor, match.start),
        });
      }
      segments.push({
        type: "person",
        content: text.slice(match.start, match.end),
        personId: match.person.id,
      });
      cursor = match.end;
    }
    if (cursor < text.length) {
      segments.push({ type: "text", content: text.slice(cursor) });
    }
    return segments;
  }

  function stopYearRange(cluster) {
    if (cluster.year_start == null) return "";
    return cluster.year_start === cluster.year_end
      ? `${cluster.year_start}`
      : `${cluster.year_start}–${cluster.year_end}`;
  }

  // --- Scroll narration steps ----------------------------------------------
  // Same observer pattern as MetaStoryNetwork: the observer only says WHEN to
  // look; the active step is recomputed from card geometry so jump-scrolls
  // can't leave a stale state behind.
  const BAND_BOTTOM = 0.75;
  const stepEls = [];
  let stepObserver = null;
  let activeStep = null;

  function recomputeActiveStep() {
    const bandBottom = window.innerHeight * BAND_BOTTOM;
    let current = null;
    for (let i = 0; i < stepEls.length; i++) {
      const el = stepEls[i];
      if (el && el.getBoundingClientRect().top < bandBottom) current = i;
    }
    activeStep = current;
  }

  function observeStep(node, index) {
    if (!stepObserver && typeof IntersectionObserver !== "undefined") {
      stepObserver = new IntersectionObserver(recomputeActiveStep, {
        rootMargin: "-55% 0px -25% 0px",
      });
    }
    stepEls[index] = node;
    stepObserver?.observe(node);
    return {
      destroy() {
        stepObserver?.unobserve(node);
        if (stepEls[index] === node) stepEls[index] = null;
      },
    };
  }

  // --- Map -----------------------------------------------------------------
  let mapContainer;
  let mapInstance = null;
  let mapReady = false;
  let basemapError = null;
  let pmtilesProtocol = null;
  let markers = [];
  let lastCameraStep = undefined; // last step the camera moved for

  async function resolvePmtilesUrl() {
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
    const ok = results.find((r) => r.status === "fulfilled");
    if (ok) return ok.value;
    basemapError = $_("story.basemap_error");
    return null;
  }

  // Dark Protomaps style WITH place labels (the map is the story here, so
  // labels help orientation), in the current UI language; boundaries kept.
  function createBaseStyle(pmtilesUrl) {
    return {
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
        lang: currentLanguage,
        labelsOnly: false,
        landOnly: false,
      }),
    };
  }

  function markerElement(event, clusterIndex) {
    // MapLibre writes its per-frame positioning transform onto the marker
    // element itself, so the visual dot must live in a child: the wrapper is
    // left free for MapLibre's translate (with no CSS transition to lag it
    // behind the camera during flyTo/fitBounds), while the inner dot carries
    // the look and the highlight/scale transitions.
    const el = document.createElement("span");
    el.className = "meta-map-marker";
    el.dataset.cluster = `${clusterIndex}`;
    el.title = `${event.event_date} · ${displayName(event.person_name)}: ${event.event_title}`;
    const dot = document.createElement("span");
    dot.className = "meta-map-marker-dot";
    dot.style.backgroundColor = primaryColor(event.person_id);
    el.appendChild(dot);
    return el;
  }

  function addMarkers() {
    for (const marker of markers) marker.marker.remove();
    markers = [];
    clusters.forEach((cluster, clusterIndex) => {
      for (const event of cluster.events || []) {
        const el = markerElement(event, clusterIndex);
        const marker = new maplibregl.Marker({ element: el })
          .setLngLat(event.coordinates)
          .addTo(mapInstance);
        markers.push({ marker, el, clusterIndex });
      }
    });
    updateMarkerStates();
  }

  function updateMarkerStates() {
    for (const { el, clusterIndex } of markers) {
      el.classList.toggle(
        "current",
        activeStep != null && clusterIndex === activeStep
      );
      el.classList.toggle(
        "dimmed",
        activeStep != null && clusterIndex !== activeStep
      );
    }
  }

  function overviewBounds() {
    const bounds = new maplibregl.LngLatBounds();
    for (const cluster of clusters) {
      bounds.extend([cluster.bbox[0], cluster.bbox[1]]);
      bounds.extend([cluster.bbox[2], cluster.bbox[3]]);
    }
    return bounds;
  }

  const prefersReducedMotion =
    typeof window !== "undefined" &&
    window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

  function moveCamera(step) {
    if (!mapInstance || !mapReady) return;
    const duration = prefersReducedMotion ? 0 : 2200;
    if (step == null) {
      // Overview: every stop in the frame.
      mapInstance.fitBounds(overviewBounds(), {
        padding: 70,
        maxZoom: 6,
        duration: prefersReducedMotion ? 0 : 1400,
        essential: true,
      });
      return;
    }
    const cluster = clusters[step];
    if (!cluster) return;
    const [minLon, minLat, maxLon, maxLat] = cluster.bbox;
    const spread = Math.max(maxLon - minLon, maxLat - minLat);
    if (spread < 0.02) {
      // Single place: settle at city level.
      mapInstance.flyTo({
        center: cluster.centroid,
        zoom: 8.5,
        duration,
        essential: true,
      });
    } else {
      mapInstance.fitBounds(
        [
          [minLon, minLat],
          [maxLon, maxLat],
        ],
        { padding: 90, maxZoom: 9, duration, essential: true }
      );
    }
  }

  // Drive camera + marker emphasis from the active card.
  $: if (mapReady && activeStep !== lastCameraStep) {
    lastCameraStep = activeStep;
    moveCamera(activeStep);
    updateMarkerStates();
  }

  async function initMap() {
    const pmtilesUrl = await resolvePmtilesUrl();
    if (!pmtilesUrl || !mapContainer) return;

    if (!pmtilesProtocol) {
      pmtilesProtocol = new Protocol();
      maplibregl.addProtocol("pmtiles", pmtilesProtocol.tile);
    }

    mapInstance = new maplibregl.Map({
      container: mapContainer,
      style: createBaseStyle(pmtilesUrl),
      center: clusters[0]?.centroid ?? [0, 20],
      zoom: 2,
      // The reader never pans or zooms — the story drives the camera.
      interactive: false,
      attributionControl: false,
    });
    mapInstance.dragPan.disable();
    mapInstance.scrollZoom.disable();
    mapInstance.boxZoom.disable();
    mapInstance.dragRotate.disable();
    mapInstance.touchZoomRotate.disable();
    mapInstance.doubleClickZoom.disable();
    mapInstance.keyboard.disable();

    mapInstance.on("load", () => {
      mapReady = true;
      addMarkers();
      moveCamera(activeStep ?? null);
    });
    mapInstance.on("error", (e) => {
      // Tile errors after init are non-fatal; only report a dead style.
      if (!mapReady && !basemapError) {
        basemapError = $_("story.basemap_error");
      }
      console.warn("MetaStoryMap error:", e?.error ?? e);
    });
  }

  onMount(() => {
    if (hasMap) initMap();
  });

  onDestroy(() => {
    for (const marker of markers) marker.marker.remove();
    markers = [];
    if (mapInstance) {
      mapInstance.remove();
      mapInstance = null;
    }
    if (pmtilesProtocol && typeof maplibregl.removeProtocol === "function") {
      try {
        maplibregl.removeProtocol("pmtiles");
      } catch {
        /* already removed */
      }
    }
    pmtilesProtocol = null;
    stepObserver?.disconnect();
  });
</script>

{#if hasMap}
  <div class="mmap">
    <!-- The map pins below the sticky header while the cards scroll over it -->
    <div class="mmap-sticky">
      <div class="map-frame">
        {#if basemapError}
          <div class="map-error" role="note">{basemapError}</div>
        {:else if !mapReady}
          <div class="map-loading">{$_("meta_story.map_loading")}</div>
        {/if}
        <div
          class="map-canvas"
          class:hidden={!mapReady}
          bind:this={mapContainer}
          role="img"
          aria-label={$_("meta_story.map_aria")}
        ></div>
      </div>
    </div>

    <!-- Narration: cards scroll up over the pinned map, each zooming to and
         explaining one geographic stop of the story. -->
    <ol class="mmap-steps">
      {#each clusters as cluster, i (cluster.key)}
        <li class="step" use:observeStep={i}>
          <div class="step-card" class:current={activeStep === i}>
            <p class="step-kicker">
              <span class="step-place">
                {cluster.label}{#if stopYearRange(cluster)}&nbsp;({stopYearRange(
                    cluster
                  )}){/if}
              </span>
            </p>
            <h3 class="step-title">
              {stopTitles.get(cluster.key) ?? cluster.label}
            </h3>
            {#if stopTexts.has(cluster.key)}
              <p class="step-body">
                {#each highlightNarration(stopTexts.get(cluster.key), cluster) as seg}{#if seg.type === "text"}{seg.content}{:else}<strong
                      class="person-mention"
                      style={`--mention-color: ${primaryColor(seg.personId)}`}
                      >{seg.content}</strong
                    >{/if}{/each}
              </p>
            {/if}
            <ul class="event-list">
              {#each cluster.events.slice(0, MAX_CARD_EVENTS) as event (`${event.person_id}-${event.event_index}`)}
                <li
                  class="event"
                  style={`--person-color: ${primaryColor(event.person_id)}`}
                >
                  <a
                    class="event-link"
                    href={eventHref(event)}
                    on:click={openStory}
                    title={$_("meta_story.map_open_event", {
                      name: displayName(event.person_name),
                    })}
                  >
                    <span class="event-date">{event.event_date}</span>
                    <span class="event-title">{event.event_title}</span>
                    <span class="event-person"
                      >{displayName(event.person_name)}</span
                    >
                  </a>
                </li>
              {/each}
            </ul>
            {#if cluster.events.length > MAX_CARD_EVENTS}
              <p class="event-more">
                {$_("meta_story.map_more_events", {
                  count: cluster.events.length - MAX_CARD_EVENTS,
                })}
              </p>
            {/if}
          </div>
        </li>
      {/each}
    </ol>
  </div>
{/if}

<style>
  .mmap {
    position: relative;
  }

  /* The map pins FULL SCREEN while the narration cards (which follow in
     flow) scroll up and over it. Full-bleed out of the 800px story column
     (same trick as the timeline's scroll proxy); the translucent app header
     simply overlays the map's top edge. */
  .mmap-sticky {
    position: sticky;
    top: 0;
    z-index: 1;
    width: 100vw;
    margin-left: calc(-50vw + 50%);
  }

  .map-frame {
    position: relative;
    width: 100%;
    height: 100vh;
    overflow: hidden;
    background: rgba(15, 23, 42, 0.6);
    /* Vertical page scrolling passes through the (non-interactive) map. */
    touch-action: pan-y;
  }

  .map-canvas {
    position: absolute;
    inset: 0;
    opacity: 1;
    transition: opacity 0.3s ease;
  }

  .map-canvas.hidden {
    opacity: 0;
  }

  /* The map is camera-driven; make sure the canvas never captures input. */
  .map-canvas :global(.maplibregl-canvas) {
    pointer-events: none;
  }

  .map-loading,
  .map-error {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #94a3b8;
    font-size: 0.9rem;
    letter-spacing: 0.01em;
  }

  .map-loading {
    animation: mmap-pulse 1.4s ease-in-out infinite;
  }

  @keyframes mmap-pulse {
    0%,
    100% {
      opacity: 0.55;
    }
    50% {
      opacity: 1;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .map-loading {
      animation: none;
    }
    .map-canvas {
      transition: none;
    }
    :global(.meta-map-marker-dot) {
      transition: none;
    }
  }

  /* Event markers (DOM elements appended by MapLibre, hence :global).
     MapLibre owns the wrapper's transform (its per-frame positioning during
     camera moves), so the wrapper carries NO transition — otherwise every
     positional update would ease over 0.3s and the markers would lag behind
     the map during flyTo/fitBounds. The inner dot holds the visual styling
     and the highlight/scale transitions instead. */
  :global(.meta-map-marker) {
    display: block;
    width: 13px;
    height: 13px;
  }

  :global(.meta-map-marker-dot) {
    display: block;
    width: 100%;
    height: 100%;
    border-radius: 50%;
    border: 2px solid rgba(2, 6, 23, 0.85);
    box-shadow: 0 0 8px rgba(56, 189, 248, 0.35);
    opacity: 0.85;
    transition:
      transform 0.3s ease,
      opacity 0.3s ease;
  }

  :global(.meta-map-marker.current .meta-map-marker-dot) {
    transform: scale(1.35);
    opacity: 1;
    z-index: 2;
  }

  :global(.meta-map-marker.dimmed .meta-map-marker-dot) {
    opacity: 0.35;
    box-shadow: none;
  }

  /* --- Narration cards (mirroring the network section) -------------------- */
  .mmap-steps {
    position: relative;
    z-index: 2;
    list-style: none;
    margin: 0;
    padding: 12vh 0 16vh;
    pointer-events: none;
  }

  .step {
    display: flex;
    justify-content: center;
    margin: 0 0 55vh;
  }

  .step:last-child {
    margin-bottom: 0;
  }

  /* Frosted glass over the map: a translucent scrim so the blurred basemap
     reads through as a soft backdrop, mirroring the network cards. */
  .step-card {
    pointer-events: auto;
    width: min(30rem, 100%);
    background: rgba(15, 23, 42, 0.45);
    backdrop-filter: blur(20px) saturate(1.3);
    -webkit-backdrop-filter: blur(20px) saturate(1.3);
    border: 1px solid rgba(148, 163, 184, 0.22);
    border-radius: 16px;
    padding: 1.1rem 1.3rem 1.2rem;
    box-shadow: 0 14px 34px rgba(2, 6, 23, 0.45);
    transition: border-color 0.25s ease;
  }

  .step-card.current {
    border-color: rgba(56, 189, 248, 0.55);
  }

  .step-kicker {
    margin: 0 0 0.3rem;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #7dd3fc;
  }

  .step-place {
    color: #94a3b8;
    text-transform: none;
    letter-spacing: 0.02em;
  }

  .step-title {
    margin: 0;
    font-family: var(--heading-font, "Space Grotesk", sans-serif);
    font-size: 1.1rem;
    font-weight: 700;
    color: #e2e8f0;
    line-height: 1.35;
  }

  .step-body {
    margin: 0.5rem 0 0;
    font-size: 0.9rem;
    line-height: 1.6;
    color: #cbd5e1;
  }

  .person-mention {
    font-weight: 700;
    color: #f1f5f9;
    text-shadow: 0 0 6px var(--mention-color, rgba(56, 189, 248, 0.35));
  }

  .event-list {
    list-style: none;
    margin: 0.8rem 0 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 0.45rem;
  }

  .event {
    border-left: 2px solid var(--person-color, rgba(56, 189, 248, 0.6));
    font-size: 0.82rem;
    line-height: 1.4;
  }

  /* Each event is a link to its slide in the person's own story. The link is
     the full clickable row (padding lives here, not on the li) so the whole
     entry is a comfortable target. */
  .event-link {
    display: flex;
    align-items: baseline;
    flex-wrap: wrap;
    gap: 0.4rem;
    padding: 0.15rem 0.4rem 0.15rem 0.6rem;
    border-radius: 0 6px 6px 0;
    text-decoration: none;
    color: inherit;
    transition:
      background-color 0.2s ease,
      transform 0.2s ease;
  }

  .event-link:hover,
  .event-link:focus-visible {
    background: rgba(148, 163, 184, 0.12);
    transform: translateX(2px);
    outline: none;
  }

  .event-link:focus-visible {
    box-shadow: 0 0 0 2px var(--person-color, rgba(56, 189, 248, 0.6));
  }

  .event-link:hover .event-title,
  .event-link:focus-visible .event-title {
    text-decoration: underline;
    text-decoration-color: var(--person-color, rgba(56, 189, 248, 0.6));
    text-underline-offset: 2px;
  }

  .event-date {
    color: #7dd3fc;
    font-variant-numeric: tabular-nums;
    flex: 0 0 auto;
  }

  .event-title {
    color: #f1f5f9;
    font-weight: 600;
  }

  .event-person {
    color: #94a3b8;
  }

  .event-more {
    margin: 0.5rem 0 0;
    font-size: 0.78rem;
    color: #94a3b8;
  }

  @media (max-width: 640px) {
    .step-card {
      width: min(28rem, 100%);
      padding: 0.95rem 1.05rem 1.05rem;
    }
  }
</style>
