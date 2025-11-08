<script>
  import { createEventDispatcher, tick, onMount, onDestroy } from "svelte";
  import {
    mdiChevronLeft,
    mdiChevronRight,
    mdiClose,
    mdiMapMarkerOutline,
    mdiLinkVariant,
    mdiBabyFaceOutline,
    mdiSkullOutline,
    mdiSchoolOutline,
    mdiRing,
    mdiCrownOutline,
    mdiStarCircleOutline,
    mdiSwordCross,
    mdiBookOpenVariant,
    mdiBriefcaseOutline,
    mdiNavigationVariant,
    mdiCircleSmall,
    mdiHome,
  } from "@mdi/js";
  import "maplibre-gl/dist/maplibre-gl.css";
  import maplibregl from "maplibre-gl";
  import { Protocol } from "pmtiles";
  import { layers, namedFlavor } from "@protomaps/basemaps";

  export let dataset = null;
  export let activeIndex = 0;
  export let hasRegistryEntries = false;
  export let styleConfig = null;

  const dispatch = createEventDispatcher();

  const DEFAULT_COORDINATES = null;
  const DEFAULT_PM_TILES_URL =
    "https://build.protomaps.com/20251105.pmtiles?download=1";
  const PMTILES_BUILD_URL =
    import.meta.env.VITE_PROTOMAPS_PM_TILES_URL ?? DEFAULT_PM_TILES_URL;
  let mapContainer;
  let mapInstance = null;
  let mapReady = false;
  let currentMarker = null;
  let trailMarkers = [];
  let lastViewportKey = "";
  let lastDatasetName = null;
  let datasetName = null;

  let primaryMarkerColor = "#38BDF8";
  let fadedMarkerColor = "rgba(56, 189, 248, 0.35)";

  let pmtilesProtocol = null;
  let basemapStyleCache = null;

  const UNKNOWN_LOCATION_LABEL = "Location unknown";

  const EVENT_ICON_RULES = [
    {
      icon: mdiBabyFaceOutline,
      matches: (event, text) =>
        event?.age === 0 || text.includes("birth") || text.includes("born"),
    },
    {
      icon: mdiSkullOutline,
      matches: (_event, text) =>
        text.includes("death") ||
        text.includes("died") ||
        text.includes("passed away"),
    },
    {
      icon: mdiSchoolOutline,
      matches: (_event, text) =>
        text.includes("graduat") ||
        text.includes("degree") ||
        text.includes("diploma"),
    },
    {
      icon: mdiRing,
      matches: (_event, text) =>
        text.includes("marriage") ||
        text.includes("married") ||
        text.includes("wedding"),
    },
    {
      icon: mdiCrownOutline,
      matches: (_event, text) =>
        text.includes("crowned") ||
        text.includes("coronation") ||
        text.includes("enthroned"),
    },
    {
      icon: mdiStarCircleOutline,
      matches: (_event, text) =>
        text.includes("award") ||
        text.includes("prize") ||
        text.includes("honor") ||
        text.includes("medal"),
    },
    {
      icon: mdiSwordCross,
      matches: (_event, text) =>
        text.includes("battle") ||
        text.includes("war") ||
        text.includes("campaign"),
    },
    {
      icon: mdiBookOpenVariant,
      matches: (_event, text) =>
        text.includes("publish") ||
        text.includes("publication") ||
        text.includes("book") ||
        text.includes("paper"),
    },
    {
      icon: mdiBriefcaseOutline,
      matches: (_event, text) =>
        text.includes("appointed") ||
        text.includes("elected") ||
        text.includes("named") ||
        text.includes("assumes"),
    },
    {
      icon: mdiNavigationVariant,
      matches: (_event, text) =>
        text.includes("voyage") ||
        text.includes("expedition") ||
        text.includes("travels") ||
        text.includes("journey"),
    },
  ];

  const formatters = {
    day: new Intl.DateTimeFormat("en", { dateStyle: "long" }),
    month: new Intl.DateTimeFormat("en", { year: "numeric", month: "long" }),
    year: new Intl.DateTimeFormat("en", { year: "numeric" }),
  };

  function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
  }

  function displayName(value = "") {
    if (typeof value !== "string") return "";
    return value.replace(/_/g, " ").replace(/\s+/g, " ").trim();
  }

  function storyStyleVars(style) {
    if (!style || typeof style !== "object") return "";
    const segments = [];
    if (style.background) segments.push(`--story-bg: ${style.background}`);
    if (style.backgroundRgb)
      segments.push(`--story-bg-rgb: ${style.backgroundRgb}`);
    if (style.primary) segments.push(`--story-primary: ${style.primary}`);
    if (style.secondary) segments.push(`--story-secondary: ${style.secondary}`);
    if (style.backgroundPatternDataUrl) {
      segments.push(
        `--story-pattern-image: url(\"${style.backgroundPatternDataUrl}\")`
      );
    }
    if (typeof style.patternOpacity === "number") {
      const opacity = clamp(style.patternOpacity, 0, 1);
      segments.push(`--story-pattern-opacity: ${opacity}`);
    }
    return segments.join("; ");
  }

  $: person = dataset?.person ?? {};
  $: events = Array.isArray(dataset?.events) ? dataset.events : [];
  $: portrait = person?.portrait;
  $: personName = displayName(person?.name ?? "Select a person");
  $: personSummary = person?.summary ?? "";
  $: hasDataset = Boolean(dataset);
  $: hasPersonSummary = Boolean(personSummary);
  $: yearsLabel = computeYearsLabel(person);
  $: rolesLabel = Array.isArray(person?.primary_roles)
    ? person.primary_roles.join(" · ")
    : "";
  $: eventSlides = events
    .slice()
    .sort((a, b) => toTimestamp(a) - toTimestamp(b))
    .map((event, eventIndex) => ({ ...event, eventIndex }))
    .map((event) => ({
      ...event,
      coordinates: normalizePrimaryLocation(event),
    }));
  $: totalSlides = eventSlides.length;
  $: slides = totalSlides > 0 ? [{ type: "spacer" }, ...eventSlides] : [];
  $: totalPanels = slides.length;
  $: hasEvents = totalSlides > 0;
  $: hasMapData = eventSlides.some((event) => isCoordinate(event.coordinates));
  $: hasMultipleEvents = totalSlides > 1;
  $: if (totalPanels === 0 && activeIndex !== 0) {
    activeIndex = 0;
  } else if (totalPanels > 0 && activeIndex >= totalPanels) {
    activeIndex = totalPanels - 1;
  }

  $: activeEventIndex =
    totalSlides > 0 && activeIndex > 0
      ? Math.min(Math.max(activeIndex - 1, 0), totalSlides - 1)
      : -1;

  $: activeCoordinates =
    activeEventIndex >= 0
      ? (eventSlides[activeEventIndex]?.coordinates ?? DEFAULT_COORDINATES)
      : DEFAULT_COORDINATES;

  $: markerTrail =
    hasMapData && activeEventIndex > 0
      ? eventSlides
          .slice(0, activeEventIndex)
          .map((event) => event.coordinates)
          .filter(isCoordinate)
      : [];
  $: indicatorProgress =
    hasMultipleEvents && activeEventIndex >= 0
      ? activeEventIndex / (totalSlides - 1)
      : 0;
  $: indicatorIcons = eventSlides.map((event) => resolveEventIcon(event));

  $: primaryMarkerColor =
    styleConfig?.secondary && parseHexColor(styleConfig.secondary)
      ? styleConfig.secondary
      : "#38BDF8";
  $: fadedMarkerColor =
    rgbaFromHex(primaryMarkerColor, 0.35) ?? "rgba(56, 189, 248, 0.35)";

  $: datasetName = dataset?.person?.name ?? null;
  $: if (datasetName !== lastDatasetName) {
    lastDatasetName = datasetName;
    lastViewportKey = "";
  }

  let slidesContainer;

  async function scrollToIndex(index) {
    if (!slidesContainer) return;
    const clamped = Math.min(Math.max(index, 0), totalPanels - 1);
    // wait for DOM to settle
    await tick();
    const { clientWidth } = slidesContainer;
    if (!clientWidth) return;
    slidesContainer.scrollTo({
      left: clamped * clientWidth,
      behavior: "smooth",
    });
  }

  function prevSlide() {
    if (totalPanels === 0) return;
    activeIndex = Math.max(0, activeIndex - 1);
    scrollToIndex(activeIndex);
  }

  function nextSlide() {
    if (totalPanels === 0) return;
    activeIndex = Math.min(totalPanels - 1, activeIndex + 1);
    scrollToIndex(activeIndex);
  }

  function goToEvent(eventIndex) {
    if (!Number.isInteger(eventIndex)) return;
    const clamped = clamp(eventIndex, 0, Math.max(eventSlides.length - 1, 0));
    const targetIndex = clamped + 1;
    if (totalPanels === 0) return;
    activeIndex = targetIndex;
    scrollToIndex(targetIndex);
  }

  function handleClose() {
    dispatch("close");
  }

  function handleScroll(event) {
    if (totalPanels === 0) {
      activeIndex = 0;
      return;
    }
    const { scrollLeft, clientWidth } = event.target;
    if (!clientWidth) return;
    const index = Math.round(scrollLeft / clientWidth);
    activeIndex = Math.min(Math.max(index, 0), totalPanels - 1);
  }

  function handleWheel(event) {
    if (event.ctrlKey) return;
    if (!slidesContainer || totalPanels === 0) return;
    const dominantDelta =
      Math.abs(event.deltaX) > Math.abs(event.deltaY)
        ? event.deltaX
        : event.deltaY;
    if (!dominantDelta) return;
    event.preventDefault();
    slidesContainer.scrollBy({
      left: dominantDelta,
      behavior: "smooth",
    });
  }

  function computeYearsLabel(currentPerson) {
    if (!currentPerson) return "";
    const { birth_date: birth, death_date: death } = currentPerson;
    if (birth && death) {
      const birthYear = new Date(birth).getFullYear();
      const deathYear = new Date(death).getFullYear();
      if (!Number.isNaN(birthYear) && !Number.isNaN(deathYear)) {
        return `${birthYear} - ${deathYear}`;
      }
    }
    if (birth) {
      const birthYear = new Date(birth).getFullYear();
      if (!Number.isNaN(birthYear)) {
        return `${birthYear}`;
      }
    }
    return "";
  }

  function toTimestamp(event) {
    if (!event?.date) return Number.POSITIVE_INFINITY;
    const precision = event.date_precision ?? "day";
    const iso =
      precision === "year"
        ? `${event.date}-01-01T00:00:00Z`
        : precision === "month"
          ? `${event.date}-01T00:00:00Z`
          : `${event.date}T00:00:00Z`;
    return Date.parse(iso);
  }

  function formatSingleDate(value, precision) {
    if (!value) return null;
    const normalizedPrecision = precision ?? "day";
    const formatter = formatters[normalizedPrecision] ?? formatters.day;
    const iso =
      normalizedPrecision === "year"
        ? `${value}-01-01T00:00:00Z`
        : normalizedPrecision === "month"
          ? `${value}-01T00:00:00Z`
          : `${value}T00:00:00Z`;
    const timestamp = Date.parse(iso);
    if (Number.isNaN(timestamp)) return null;
    return formatter.format(new Date(timestamp));
  }

  function formatDate(event) {
    if (!event) return "Date unavailable";
    const labelOverride =
      typeof event.date_label === "string" && event.date_label.trim()
        ? event.date_label.trim()
        : null;
    const supplementalNote =
      typeof event.date_note === "string" && event.date_note.trim()
        ? event.date_note.trim()
        : null;
    if (labelOverride) {
      if (supplementalNote) {
        const noteParts = supplementalNote
          .split(";")
          .map((part) => part.trim())
          .filter(Boolean)
          .filter(
            (part) =>
              part.localeCompare(labelOverride, undefined, {
                sensitivity: "accent",
              }) !== 0
          );
        if (noteParts.length > 0) {
          return `${labelOverride} (${noteParts.join("; ")})`;
        }
      }
      return labelOverride;
    }
    const startLabel = formatSingleDate(event.date, event.date_precision);
    const endLabel = formatSingleDate(
      event.date_end,
      event.date_end_precision ?? event.date_precision
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
    if (!label) return supplementalNote ?? "Date unavailable";
    if (!supplementalNote) return label;
    const supplementalParts = supplementalNote
      .split(";")
      .map((part) => part.trim())
      .filter(Boolean);
    if (supplementalParts.length === 0) return label;
    return `${label} (${supplementalParts.join("; ")})`;
  }

  function formatAgeLabel(age) {
    if (age === null || age === undefined) return null;
    if (age === 0) return "At birth";
    return `Age ${age}`;
  }

  function formatLocations(locations = []) {
    if (!locations.length) return UNKNOWN_LOCATION_LABEL;
    return locations.join(" · ");
  }

  function sourceLabel(url) {
    try {
      const { hostname } = new URL(url);
      return hostname.replace(/^www\./, "");
    } catch (error) {
      return url;
    }
  }

  function normalizePrimaryLocation(event) {
    if (!event?.location_coordinates) return DEFAULT_COORDINATES;
    const primary = event.location_coordinates.find((item) => {
      if (!item) return false;
      if (item.primary === true) return true;
      return false;
    });
    if (!primary) return DEFAULT_COORDINATES;
    if (!Array.isArray(primary.centroid) || primary.centroid.length !== 2) {
      return DEFAULT_COORDINATES;
    }
    const [lng, lat] = primary.centroid;
    const lonValue = Number(lng);
    const latValue = Number(lat);
    if (!Number.isFinite(lonValue) || !Number.isFinite(latValue)) {
      return DEFAULT_COORDINATES;
    }
    return { lon: lonValue, lat: latValue };
  }

  function isCoordinate(value) {
    return (
      !!value &&
      typeof value === "object" &&
      Number.isFinite(value.lon) &&
      Number.isFinite(value.lat)
    );
  }

  function parseHexColor(value) {
    if (typeof value !== "string") return null;
    const trimmed = value.trim();
    if (!/^#[0-9a-fA-F]{6}$/.test(trimmed)) return null;
    const r = parseInt(trimmed.slice(1, 3), 16);
    const g = parseInt(trimmed.slice(3, 5), 16);
    const b = parseInt(trimmed.slice(5, 7), 16);
    if ([r, g, b].some((component) => Number.isNaN(component))) {
      return null;
    }
    return { r, g, b };
  }

  function rgbaFromHex(hex, alpha) {
    const parsed = parseHexColor(hex);
    if (!parsed) return null;
    const nextAlpha = Math.min(Math.max(alpha, 0), 1);
    return `rgba(${parsed.r}, ${parsed.g}, ${parsed.b}, ${nextAlpha})`;
  }

  function resolveEventIcon(event) {
    const text = `${event?.title ?? ""} ${event?.description ?? ""}`
      .toLowerCase()
      .replace(/\s+/g, " ")
      .trim();
    for (const rule of EVENT_ICON_RULES) {
      try {
        if (rule.matches(event, text)) {
          return rule.icon;
        }
      } catch (error) {
        // ignore rule errors to avoid breaking icon rendering
      }
    }
    return mdiCircleSmall;
  }

  function createBaseStyle() {
    if (!basemapStyleCache) {
      basemapStyleCache = {
        version: 8,
        glyphs:
          "https://protomaps.github.io/basemaps-assets/fonts/{fontstack}/{range}.pbf",
        sprite: "https://protomaps.github.io/basemaps-assets/sprites/v4/dark",
        sources: {
          protomaps: {
            type: "vector",
            url: `pmtiles://${PMTILES_BUILD_URL}`,
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
          if (lower.includes("boundary") || lower.includes("border")) {
            return false;
          }
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
    if (currentMarker) {
      currentMarker.remove();
      currentMarker = null;
    }
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
    const history = Array.isArray(historyCoords)
      ? historyCoords.filter(isCoordinate)
      : [];

    clearMarkers();

    if (history.length > 0) {
      for (const coords of history) {
        const markerElement = createMarkerElement(fadedMarkerColor, {
          opacity: 0.6,
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

    if (active) {
      const markerElement = createMarkerElement(primaryMarkerColor, {
        opacity: 1,
        size: 16,
      });
      currentMarker = new maplibregl.Marker({
        element: markerElement,
        anchor: "bottom",
      })
        .setLngLat([active.lon, active.lat])
        .addTo(mapInstance);
    }

    const positions = active ? [active, ...history] : history;
    if (positions.length === 0) {
      if (lastViewportKey !== "baseline") {
        mapInstance.easeTo({ center: [0, 0], zoom: 1.5, duration: 700 });
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
        zoom: 6.5,
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
      padding: { top: 60, bottom: 100, left: 80, right: 80 },
      duration: 900,
      maxZoom: 7.5,
    });
  }

  async function initialiseMap() {
    if (mapInstance || !hasMapData) return;
    await tick();
    if (mapInstance || !mapContainer) return;
    if (!pmtilesProtocol) {
      pmtilesProtocol = new Protocol();
      maplibregl.addProtocol("pmtiles", pmtilesProtocol.tile);
    }
    mapInstance = new maplibregl.Map({
      container: mapContainer,
      style: createBaseStyle(),
      center: [0, 0],
      zoom: 1.5,
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

  onMount(() => {
    initialiseMap();
  });

  onDestroy(() => {
    teardownMapInstance();
    if (pmtilesProtocol && typeof maplibregl.removeProtocol === "function") {
      try {
        maplibregl.removeProtocol("pmtiles");
      } catch (error) {
        // ignore removal issues to avoid disrupting teardown
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
  class="story-view"
  style={storyStyleVars(styleConfig)}
  on:wheel={handleWheel}
>
  <header class="masthead" class:compact={activeIndex > 0}>
    {#if hasRegistryEntries}
      <div class="toolbar">
        <button
          type="button"
          class="close-story"
          on:click={handleClose}
          aria-label="Close story and return to the landing page"
        >
          <svg
            class="icon"
            viewBox="0 0 24 24"
            role="presentation"
            aria-hidden="true"
          >
            <path d={mdiClose} />
          </svg>
          <span class="btn-label">Close story</span>
        </button>
      </div>
    {/if}
    <div class="masthead-content">
      <div class="full-info">
        <p class="eyebrow">Life Data Stories</p>
        <h1>{personName}</h1>
        {#if hasPersonSummary}
          <p class="summary">{personSummary}</p>
        {:else if hasDataset}
          <p class="summary placeholder">
            A summary is not available, but key life events are listed below.
          </p>
        {/if}
        <div class="meta">
          {#if yearsLabel}
            <span>{yearsLabel}</span>
          {/if}
          {#if rolesLabel}
            <span>{rolesLabel}</span>
          {/if}
        </div>
      </div>
      {#if portrait?.image}
        <figure class="portrait">
          <img
            src={portrait.image}
            alt={portrait.alt ?? `Portrait of ${personName}`}
            loading="lazy"
            decoding="async"
          />
          {#if portrait.caption || portrait.source}
            <figcaption>
              {#if portrait.caption}
                <span>{portrait.caption}</span>
              {/if}
              {#if portrait.source}
                <a href={portrait.source} target="_blank" rel="noreferrer"
                  >{sourceLabel(portrait.source)}</a
                >
              {/if}
            </figcaption>
          {/if}
        </figure>
      {/if}
    </div>
    <div class="compact-info" aria-live="polite">
      <span class="name">{personName}</span>
      {#if yearsLabel}
        <span class="separator">·</span>
        <span class="lifespan">{yearsLabel}</span>
      {/if}
      <button
        type="button"
        class="close-story compact"
        on:click={handleClose}
        aria-label="Close story and return to the landing page"
      >
        <svg
          class="icon"
          viewBox="0 0 24 24"
          role="presentation"
          aria-hidden="true"
        >
          <path d={mdiClose} />
        </svg>
      </button>
    </div>
  </header>

  <div class="slides-wrapper" class:map-enabled={hasMapData}>
    <main
      class="slides"
      aria-live="polite"
      bind:this={slidesContainer}
      on:scroll={handleScroll}
    >
      {#if totalPanels > 0}
        {#each slides as slide}
          <section
            class="slide"
            class:spacer={slide.type === "spacer"}
            aria-hidden={slide.type === "spacer"}
            aria-label={slide.type === "spacer"
              ? null
              : `Slide ${slide.eventIndex + 1} of ${totalSlides}: ${slide.title}`}
          >
            {#if slide.type !== "spacer"}
              <div class="content">
                <p class="date">{formatDate(slide)}</p>
                {#if formatAgeLabel(slide.age)}
                  <p class="age">{formatAgeLabel(slide.age)}</p>
                {/if}
                <h2>{slide.title}</h2>
                <p class="description">{slide.description}</p>
                <ul class="details">
                  {#if slide.locations?.length}
                    <li>
                      <span class="label">
                        <svg
                          class="icon icon-inline"
                          viewBox="0 0 24 24"
                          role="presentation"
                          aria-hidden="true"
                        >
                          <path d={mdiMapMarkerOutline} />
                        </svg>
                        <span class="label-text">Location</span>
                      </span>
                      <span>{formatLocations(slide.locations)}</span>
                    </li>
                  {/if}
                  {#if slide.sources?.length}
                    <li>
                      <span class="label">
                        <svg
                          class="icon icon-inline"
                          viewBox="0 0 24 24"
                          role="presentation"
                          aria-hidden="true"
                        >
                          <path d={mdiLinkVariant} />
                        </svg>
                        <span class="label-text">Sources</span>
                      </span>
                      <span class="sources">
                        {#each slide.sources as source}
                          <a href={source} target="_blank" rel="noreferrer"
                            >{sourceLabel(source)}</a
                          >
                        {/each}
                      </span>
                    </li>
                  {/if}
                </ul>
              </div>
            {/if}
          </section>
        {/each}
      {:else}
        <section class="slide empty">
          <div class="content">
            <h2>Events unavailable</h2>
            <p>
              We could not find notable events for {personName}. Try
              regenerating the dataset.
            </p>
          </div>
        </section>
      {/if}
    </main>
    {#if hasMapData}
      <div class="map-overlay" aria-hidden="true">
        <div class="map-gradient" />
        <div class="map-frame">
          <div class="map-container" bind:this={mapContainer} />
        </div>
      </div>
    {/if}
  </div>
  {#if hasEvents}
    <div
      class="indicator"
      role="group"
      aria-label={`Event ${activeEventIndex + 1} of ${totalSlides}`}
      style={`--indicator-progress: ${indicatorProgress}`}
    >
      <div class="indicator-content">
        {#if totalPanels > 1}
          <div class="indicator-nav">
            <button
              type="button"
              class="nav-btn prev"
              on:click={prevSlide}
              aria-label="Go to previous slide"
              disabled={activeIndex === 0}
            >
              <svg
                class="icon"
                viewBox="0 0 24 24"
                role="presentation"
                aria-hidden="true"
              >
                <path d={mdiChevronLeft} />
              </svg>
            </button>
            <button
              type="button"
              class="nav-btn next"
              on:click={nextSlide}
              aria-label="Go to next slide"
              disabled={activeIndex >= totalPanels - 1}
            >
              <svg
                class="icon"
                viewBox="0 0 24 24"
                role="presentation"
                aria-hidden="true"
              >
                <path d={mdiChevronRight} />
              </svg>
            </button>
          </div>
        {/if}
        <div class="indicator-track" class:single={!hasMultipleEvents}>
          <div class="dots-container">
            {#if activeIndex > 0}
              <span class="indicator-highlight" class:single={!hasMultipleEvents} />
            {/if}
            <button
              type="button"
              class="dot square"
              class:active={activeIndex === 0}
              on:click={() => scrollToIndex(0)}
              aria-label="Show overview"
              aria-current={activeIndex === 0 ? "true" : undefined}
            >
              <svg
                class="dot-icon"
                viewBox="0 0 24 24"
                role="img"
                aria-hidden="true"
              >
                <path d={mdiHome} />
              </svg>
            </button>
            {#each eventSlides as _, idx}
              <button
                type="button"
                class="dot"
                class:active={idx === activeEventIndex}
                on:click={() => goToEvent(idx)}
                aria-label={`Show event ${idx + 1} of ${totalSlides}`}
                aria-current={idx === activeEventIndex ? "true" : undefined}
              >
                <svg
                  class="dot-icon"
                  viewBox="0 0 24 24"
                  role="img"
                  aria-hidden="true"
                >
                  <path d={indicatorIcons[idx] ?? mdiCircleSmall} />
                </svg>
              </button>
            {/each}
          </div>
        </div>
      </div>
    </div>
  {/if}
</div>

<style>
  .story-view {
    flex: 1 1 auto;
    display: flex;
    flex-direction: column;
    position: relative;
    background-color: rgba(var(--story-bg-rgb, 15, 23, 42), 0.55);
    color: #e2e8f0;
    isolation: isolate;
    min-height: 100vh;
  }

  .story-view::before {
    content: "";
    position: absolute;
    inset: 0;
    pointer-events: none;
    background-image: var(--story-pattern-image, none);
    background-size: 260px 260px;
    background-repeat: repeat;
    opacity: var(--story-pattern-opacity, 0.16);
    mix-blend-mode: soft-light;
    z-index: 0;
  }

  .story-view > * {
    position: relative;
    z-index: 1;
  }

  .masthead {
    padding: 1.75rem 1.5rem 1.25rem;
    display: flex;
    flex-direction: column;
    background: linear-gradient(
        180deg,
        rgba(255, 255, 255, 0.03) 0%,
        rgba(0, 0, 0, 0.28) 100%
      ),
      rgba(var(--story-bg-rgb, 15, 23, 42), 0.58);
    backdrop-filter: blur(12px);
    border-bottom: 1px solid rgba(148, 163, 184, 0.16);
    position: sticky;
    top: 0;
    z-index: 2;
    transition: padding 0.25s ease;
  }

  .toolbar {
    display: flex;
    flex-wrap: wrap;
    gap: 1rem;
    margin-bottom: 1.25rem;
    align-items: center;
  }

  .full-info {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .masthead-content {
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
  }

  .compact-info {
    display: none;
    align-items: center;
    gap: 0.6rem;
    font-size: 0.95rem;
    font-weight: 600;
    color: #e2e8f0;
    white-space: nowrap;
    max-width: 100%;
    overflow: hidden;
  }

  .compact-info span {
    min-width: 0;
  }

  .compact-info .name {
    font-weight: 700;
    letter-spacing: 0.01em;
    overflow-x: auto;
    white-space: nowrap;
    text-overflow: clip;
    -ms-overflow-style: none;
    scrollbar-width: none;
    touch-action: pan-x;
    padding-bottom: 0.1rem;
  }

  .compact-info .name::-webkit-scrollbar {
    display: none;
  }

  .compact-info .separator {
    color: rgba(148, 163, 184, 0.8);
    flex: 0 0 auto;
  }

  .compact-info .lifespan {
    color: #94a3b8;
    font-weight: 500;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .close-story {
    border: 1px solid var(--story-primary, rgba(148, 163, 184, 0.3));
    background: rgba(255, 255, 255, 0.05);
    color: var(--story-primary, #e2e8f0);
    border-radius: 999px;
    padding: 0.45rem 0.95rem;
    font-size: 0.85rem;
    font-weight: 600;
    cursor: pointer;
    flex: 0 0 auto;
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    transition:
      border-color 0.2s ease,
      background-color 0.2s ease,
      color 0.2s ease;
  }

  .close-story:hover,
  .close-story:focus {
    border-color: var(--story-primary, rgba(148, 163, 184, 0.6));
    background: rgba(255, 255, 255, 0.12);
    outline: none;
  }

  .close-story.compact {
    flex: 0 0 auto;
    padding: 0.35rem 0.75rem;
    font-size: 0.8rem;
    gap: 0.4rem;
  }

  .close-story .btn-label {
    line-height: 1;
  }

  .icon {
    width: 1.1em;
    height: 1.1em;
    fill: currentColor;
    flex: 0 0 auto;
  }

  .nav-btn .icon {
    width: 1.2em;
    height: 1.2em;
  }

  .icon-inline {
    width: 1em;
    height: 1em;
  }

  .masthead.compact {
    padding: 0.85rem 1.25rem;
    flex-direction: row;
    align-items: center;
  }

  .masthead.compact .toolbar {
    display: none;
  }

  .masthead.compact .full-info {
    display: none;
  }

  .masthead.compact .masthead-content {
    display: none;
  }

  .masthead.compact .compact-info {
    display: flex;
    width: 100%;
    justify-content: space-between;
    gap: 0.75rem;
  }

  .eyebrow {
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.75rem;
    color: var(--story-secondary, #38bdf8);
    margin: 0;
  }

  h1 {
    margin: 0;
    font-size: 1.9rem;
    line-height: 1.1;
    color: var(--story-primary, #f8fafc);
  }

  .summary {
    margin: 0;
    font-size: 0.95rem;
    color: rgba(226, 232, 240, 0.88);
    transition:
      opacity 0.25s ease,
      transform 0.25s ease;
  }

  .summary.placeholder {
    color: #94a3b8;
    font-style: italic;
  }

  .meta {
    display: flex;
    flex-wrap: wrap;
    gap: 0.75rem;
    font-size: 0.8rem;
    color: rgba(148, 163, 184, 0.85);
    transition: font-size 0.25s ease;
  }

  .masthead:not(.compact) .compact-info {
    display: none;
  }

  .slides-wrapper {
    flex: 1 1 auto;
    position: relative;
    min-height: 0;
    height: calc(100vh - var(--header-height, 0px));
    display: flex;
    flex-direction: column;
  }

  .slides {
    flex: 1 1 auto;
    display: flex;
    scroll-snap-type: x mandatory;
    overflow-x: auto;
    overflow-y: hidden;
    scroll-behavior: smooth;
    position: relative;
    height: 100%;
  }

  .slide {
    scroll-snap-align: start;
    flex: 0 0 100%;
    height: 100%;
    min-height: 100%;
    padding: 2.75rem 1.5rem 3.25rem;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: stretch;
    position: relative;
    gap: 1.25rem;
    background-color: rgb(var(--story-bg-rgb, 15, 23, 42));
    border-right: 1px solid rgba(148, 163, 184, 0.12);
    overflow: hidden;
  }

  .slides-wrapper.map-enabled .slide {
    padding-bottom: 16rem;
  }

  .slide::before {
    content: "";
    position: absolute;
    inset: 0;
    background: linear-gradient(
      180deg,
      rgba(255, 255, 255, 0.03) 0%,
      rgba(0, 0, 0, 0.22) 100%
    );
    mix-blend-mode: soft-light;
    pointer-events: none;
    z-index: 0;
  }

  .slide::after {
    content: "";
    position: absolute;
    inset: 0;
    background-image: var(--story-pattern-image, none);
    background-size: 260px 260px;
    background-repeat: repeat;
    opacity: var(--story-pattern-opacity, 0.16);
    mix-blend-mode: soft-light;
    mask-image: linear-gradient(
      160deg,
      rgba(0, 0, 0, 1) 0%,
      rgba(0, 0, 0, 0.65) 40%,
      rgba(0, 0, 0, 0.3) 60%,
      rgba(0, 0, 0, 0) 80%
    );
    -webkit-mask-image: linear-gradient(
      160deg,
      rgba(0, 0, 0, 1) 0%,
      rgba(0, 0, 0, 0.65) 40%,
      rgba(0, 0, 0, 0.3) 60%,
      rgba(0, 0, 0, 0) 80%
    );
    pointer-events: none;
    z-index: 2;
  }

  .slide > * {
    position: relative;
    z-index: 3;
  }

  .slide > .content {
    align-self: center;
    width: min(48rem, 100%);
    margin: 0 auto;
  }

  .map-overlay {
    position: absolute;
    inset: auto 0 0;
    height: clamp(240px, 45vh, 340px);
    pointer-events: none;
    z-index: 2;
  }

  .map-gradient {
    position: absolute;
    top: -70px;
    left: 0;
    right: 0;
    height: 160px;
    background: linear-gradient(
      177deg,
      rgba(var(--story-bg-rgb, 15, 23, 42)) 67%,
      rgba(var(--story-bg-rgb, 15, 23, 42), 0.2) 85%,
      rgba(var(--story-bg-rgb, 15, 23, 42), 0) 90%,
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

  :global(.story-map-marker) {
    display: block;
    border-radius: 50%;
    border: 2px solid rgba(2, 6, 23, 0.65);
    box-shadow: 0 8px 18px rgba(2, 6, 23, 0.5);
  }

  .nav-btn {
    pointer-events: auto;
    width: 2.4rem;
    height: 2.4rem;
    border-radius: 999px;
    border: 1px solid var(--story-primary, rgba(148, 163, 184, 0.35));
    background: rgba(255, 255, 255, 0.05);
    color: var(--story-primary, #e2e8f0);
    font-size: 1.15rem;
    font-weight: 600;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    transition:
      background-color 0.2s ease,
      border-color 0.2s ease,
      color 0.2s ease,
      transform 0.2s ease;
  }

  .nav-btn:hover,
  .nav-btn:focus {
    background: rgba(255, 255, 255, 0.15);
    border-color: var(--story-primary, rgba(148, 163, 184, 0.6));
    transform: scale(1.05);
    outline: none;
  }

  .nav-btn:disabled {
    opacity: 0.35;
    cursor: default;
    transform: none;
  }

  .slide.spacer {
    background: transparent;
    border-right: none;
    pointer-events: none;
    display: block;
    height: 100%;
    min-height: 100%;
    padding: 0;
  }

  .slide.empty {
    text-align: center;
  }

  .slide.empty .content {
    max-width: 48ch;
    margin: 0 auto;
    gap: 1rem;
    align-self: center;
  }

  .slide.empty h2 {
    font-size: 1.5rem;
    margin-bottom: 0.25rem;
  }

  .slide.empty p {
    color: #94a3b8;
  }

  .indicator {
    --dot-size: clamp(1.25rem, 3vw, 1.6rem);
    --dot-gap: 0rem;
    position: fixed;
    bottom: 1.25rem;
    left: 50%;
    transform: translateX(-50%);
    width: min(96vw, 1020px);
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0;
    pointer-events: none;
    z-index: 5;
  }

  /* Keep the indicator visually present but allow underlying slides to receive
     pointer events (so dragging/panning works anywhere). Only the nav buttons
     inside the indicator should accept pointer events. */
  .indicator-content {
    pointer-events: auto;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 0.75rem;
    width: 100%;
  }

  .indicator-nav {
    pointer-events: auto;
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
    gap: 1.25rem;
  }

  .indicator-track {
    pointer-events: auto;
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 100%;
    padding: 0.65rem 0.75rem;
    border-radius: 9999px;
    background: rgba(15, 23, 42, 0.65);
    backdrop-filter: blur(6px);
    box-shadow: 0 10px 30px rgba(15, 23, 42, 0.25);
    border: 1px solid rgba(148, 163, 184, 0.2);
  }

  .indicator-track.single {
    justify-content: center;
    width: auto;
    min-width: auto;
  }

  .dots-container {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
    max-width: min(90vw, 860px);
  }

  .nav-btn {
    pointer-events: auto;
    width: 2.6rem;
    height: 2.6rem;
    border-radius: 999px;
    border: 1px solid var(--story-primary, rgba(148, 163, 184, 0.35));
    background: rgba(255, 255, 255, 0.05);
    color: var(--story-primary, #e2e8f0);
    font-size: 1.15rem;
    font-weight: 600;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    flex: 0 0 auto;
    transition:
      background-color 0.2s ease,
      border-color 0.2s ease,
      color 0.2s ease,
      transform 0.2s ease;
  }

  .nav-btn:hover,
  .nav-btn:focus {
    background: rgba(255, 255, 255, 0.15);
    border-color: var(--story-primary, rgba(148, 163, 184, 0.6));
    transform: scale(1.05);
    outline: none;
  }

  .nav-btn:disabled {
    opacity: 0.35;
    cursor: default;
    transform: none;
  }

  .indicator-highlight {
    position: absolute;
    top: 50%;
    left: 0;
    width: var(--dot-size);
    height: var(--dot-size);
    border-radius: 9999px;
    background: var(--story-secondary, rgba(56, 189, 248, 0.45));
    opacity: 0.45;
    transform: translateX(
        calc(var(--indicator-progress) * (100% - var(--dot-size)))
      )
      translateY(-50%);
    transition:
      transform 0.35s cubic-bezier(0.22, 1, 0.36, 1),
      background-color 0.3s ease;
    z-index: 0;
    pointer-events: none;
  }

  .indicator-highlight.single {
    left: 50%;
    transform: translate(-50%, -50%);
  }

  .dot {
    appearance: none;
    border: none;
    padding: 0;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    position: relative;
    z-index: 1;
    width: var(--dot-size);
    height: var(--dot-size);
    border-radius: 9999px;
    background: rgba(148, 163, 184, 0.3);
    transition:
      background-color 0.25s ease,
      transform 0.25s ease;
    flex: 0 0 auto;
  }

  .dot.square {
    border-radius: 20%;
  }

  .dot.active {
    background: var(--story-secondary, #38bdf8);
    transform: scale(1.2);
  }

  .dot-icon {
    width: calc(var(--dot-size) * 0.72);
    height: calc(var(--dot-size) * 0.72);
    fill: rgba(226, 232, 240, 0.95);
    transition:
      fill 0.25s ease,
      transform 0.25s ease;
  }

  .dot.active .dot-icon {
    fill: #0f172a;
    transform: scale(1.05);
  }

  .dot:focus-visible {
    outline: 2px solid var(--story-secondary, #38bdf8);
    outline-offset: 2px;
  }

  .portrait {
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    align-items: center;
    text-align: center;
  }

  .portrait img {
    width: min(220px, 80vw);
    height: auto;
    border-radius: 1rem;
    box-shadow: 0 10px 25px rgba(15, 23, 42, 0.45);
    border: 1px solid rgba(148, 163, 184, 0.3);
  }

  .portrait figcaption {
    font-size: 0.75rem;
    color: #94a3b8;
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
  }

  .portrait figcaption a {
    color: var(--story-secondary, #facc15);
    text-decoration: none;
    font-weight: 500;
  }

  .portrait figcaption a:hover,
  .portrait figcaption a:focus {
    text-decoration: underline;
  }

  .content {
    display: flex;
    flex-direction: column;
    gap: 0.8rem;
  }

  .date {
    margin: 0;
    font-size: 0.9rem;
    color: var(--story-secondary, #38bdf8);
    font-weight: 600;
  }

  .age {
    margin: 0;
    font-size: 0.85rem;
    color: rgba(148, 163, 184, 0.85);
  }

  h2 {
    margin: 0;
    font-size: 1.35rem;
    line-height: 1.25;
    color: var(--story-primary, #f8fafc);
  }

  .description {
    margin: 0;
    font-size: 1rem;
    color: #e2e8f0;
  }

  .details {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    font-size: 0.85rem;
  }

  .details li {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
  }

  .label {
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.7rem;
    color: rgba(148, 163, 184, 0.76);
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
  }

  .label-text {
    line-height: 1;
  }

  .sources {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
  }

  .sources a {
    color: var(--story-secondary, #facc15);
    text-decoration: none;
    font-weight: 500;
  }

  .sources a:hover,
  .sources a:focus {
    text-decoration: underline;
  }

  @media (min-width: 768px) {
    .masthead {
      padding: 2rem 3rem 1.5rem;
    }

    .toolbar {
      margin-bottom: 1.75rem;
    }

    .masthead-content {
      flex-direction: row;
      align-items: flex-start;
      gap: 2.5rem;
    }

    h1 {
      font-size: 2.4rem;
    }

    .slides {
      height: 100%;
    }

    .slide {
      padding: 3.5rem 4rem 4rem;
      gap: 1.75rem;
    }

    .slides-wrapper.map-enabled .slide {
      padding-bottom: 18rem;
    }

    h2 {
      font-size: 1.85rem;
    }

    .description {
      font-size: 1.05rem;
      max-width: 48ch;
    }

    .details {
      font-size: 0.9rem;
      flex-direction: row;
      gap: 2rem;
    }

    .details li {
      max-width: 22rem;
    }

    .masthead.compact {
      padding: 1rem 2.5rem;
    }

    .compact-info {
      font-size: 1.05rem;
    }

    .portrait img {
      width: 260px;
    }
  }
</style>
