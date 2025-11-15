<script>
  import { tick, onMount, onDestroy } from "svelte";
  import {
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
    mdiMagnifyPlusOutline,
    mdiInformationOutline,
    mdiWikipedia,
    mdiAccountOutline,
  } from "@mdi/js";
  import "maplibre-gl/dist/maplibre-gl.css";
  import maplibregl from "maplibre-gl";
  import { Protocol } from "pmtiles";
  import { layers, namedFlavor } from "@protomaps/basemaps";
  import ImageViewer from "./ImageViewer.svelte";
  import Timeline from "./Timeline.svelte";

  export let dataset = null;
  export let egoNetwork = null;
  export let activeIndex = 0;
  export let hasRegistryEntries = false;
  export let styleConfig = null;
  export let onClose = () => {};
  export let onSlideChange = () => {};

  let enlargedImage = null;
  let enlargedImageContext = null; // Store event context for caption
  let visibleDateNote = null; // Track which event's date note is visible
  let visiblePersonInfo = null; // Track which person's info is visible

  const DEFAULT_COORDINATES = null;
  // Stable default basemap provided by Protomaps demo bucket (v4). Users can
  // override via VITE_PROTOMAPS_PM_TILES_URL if they prefer a daily build or
  // self-hosted archive.
  const DEFAULT_PM_TILES_URL = "https://demo-bucket.protomaps.com/v4.pmtiles";
  const PRIMARY_PM_TILES_URL =
    import.meta.env.VITE_PROTOMAPS_PM_TILES_URL ?? DEFAULT_PM_TILES_URL;
  const FALLBACK_PM_TILES_URL =
    import.meta.env.VITE_PROTOMAPS_PM_TILES_FALLBACK_URL ??
    "https://protomaps.github.io/tiles/v3/20240820.pmtiles";
  let pmtilesUrl = PRIMARY_PM_TILES_URL;
  let basemapError = null; // non-null if we failed to resolve any tiles source
  let basemapResolved = false;
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
        `--story-pattern-image: url(${style.backgroundPatternDataUrl})`
      );
    }
    if (style.headingFont) {
      segments.push(
        `--story-heading-font: "${style.headingFont}", Inter, sans-serif`
      );
    }
    if (style.bodyFont) {
      segments.push(
        `--story-body-font: "${style.bodyFont}", Inter, sans-serif`
      );
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
  $: slides =
    totalSlides > 0
      ? [{ type: "overview" }, ...eventSlides]
      : [{ type: "overview" }];
  $: totalPanels = slides.length;
  $: hasEvents = totalSlides > 0;
  $: hasMapData = eventSlides.some((event) => isCoordinate(event.coordinates));
  $: hasMultipleEvents = totalSlides > 1;
  $: if (totalPanels === 0 && activeIndex !== 0) {
    activeIndex = 0;
  } else if (totalPanels > 0 && activeIndex >= totalPanels) {
    activeIndex = totalPanels - 1;
  }

  // Notify parent when slide changes
  $: if (activeIndex !== undefined) {
    onSlideChange({ detail: activeIndex });
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
    rgbaFromHex(primaryMarkerColor, 0.7) ?? "rgba(56, 189, 248, 0.7)";

  $: datasetName = dataset?.person?.name ?? null;
  $: if (datasetName !== lastDatasetName) {
    lastDatasetName = datasetName;
    lastViewportKey = "";
    initialScrollDone = false; // Reset scroll flag when dataset changes
  }

  // Close date note when slide changes
  $: if (activeIndex !== undefined) {
    visibleDateNote = null;
    visiblePersonInfo = null;
  }

  let slidesContainer;
  let initialScrollDone = false;

  async function scrollToIndex(index, immediate = false) {
    if (!slidesContainer) return;
    const clamped = Math.min(Math.max(index, 0), totalPanels - 1);
    // wait for DOM to settle
    await tick();
    const { clientWidth } = slidesContainer;
    if (!clientWidth) return;
    slidesContainer.scrollTo({
      left: clamped * clientWidth,
      behavior: immediate ? "auto" : "smooth",
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
    onClose();
  }

  function enlargeImage(imageData, eventContext) {
    enlargedImage = imageData; // Now stores full image object with url, caption, source
    enlargedImageContext = eventContext;
  }

  function closeEnlargedImage() {
    enlargedImage = null;
    enlargedImageContext = null;
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
    if (labelOverride) {
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
    if (!label) return "Date unavailable";
    return label;
  }

  function getDateNote(event) {
    if (!event) return null;
    const supplementalNote =
      typeof event.date_note === "string" && event.date_note.trim()
        ? event.date_note.trim()
        : null;
    return supplementalNote;
  }

  function toggleDateNote(eventIndex) {
    if (visibleDateNote === eventIndex) {
      visibleDateNote = null;
    } else {
      visibleDateNote = eventIndex;
    }
  }

  function handleClickOutside(event) {
    // Check if click is outside the date-wrapper or person-info-wrapper
    const dateWrapper = event.target.closest(".date-wrapper");
    const personWrapper = event.target.closest(".person-info-wrapper");
    if (!dateWrapper && visibleDateNote !== null) {
      visibleDateNote = null;
    }
    if (!personWrapper && visiblePersonInfo !== null) {
      visiblePersonInfo = null;
    }
  }

  function togglePersonInfo(personKey, event) {
    if (visiblePersonInfo === personKey) {
      visiblePersonInfo = null;
    } else {
      visiblePersonInfo = personKey;
      // Wait for DOM update to position tooltip
      tick().then(() => {
        const button = event?.target?.closest(".person-chip");
        if (!button) return;

        const tooltip = button.nextElementSibling;
        if (!tooltip || !tooltip.classList.contains("person-info-tooltip"))
          return;

        const buttonRect = button.getBoundingClientRect();
        const tooltipRect = tooltip.getBoundingClientRect();
        const viewportWidth = window.innerWidth;
        const padding = 16; // Minimum padding from edge

        // Check if tooltip would overflow on the right
        const wouldOverflowRight =
          buttonRect.left + tooltipRect.width > viewportWidth - padding;

        // Check if tooltip would overflow on the left
        const wouldOverflowLeft = buttonRect.left < padding;

        if (wouldOverflowRight && !wouldOverflowLeft) {
          // Align to right edge of button
          tooltip.style.left = "auto";
          tooltip.style.right = "0";
          tooltip.style.transform = "none";
        } else if (wouldOverflowLeft) {
          // Align to left edge of button
          tooltip.style.left = "0";
          tooltip.style.right = "auto";
          tooltip.style.transform = "none";
        } else {
          // Default position (left-aligned)
          tooltip.style.left = "0";
          tooltip.style.right = "auto";
          tooltip.style.transform = "none";
        }
      });
    }
  }

  function getRelevantPeople(event) {
    if (!egoNetwork?.connections || !Array.isArray(egoNetwork.connections)) {
      return [];
    }

    const eventText =
      `${event?.title ?? ""} ${event?.description ?? ""}`.toLowerCase();
    const eventYear = event?.date ? parseInt(event.date.substring(0, 4)) : null;

    return egoNetwork.connections
      .filter((connection) => {
        // Check if person's name appears in event text
        const personName = connection.person_name.toLowerCase();
        if (!eventText.includes(personName)) {
          return false;
        }

        // Check if event year falls within relationship timeframe
        if (eventYear) {
          const startYear = connection.start_year;
          const endYear = connection.end_year;
          if (startYear && eventYear < startYear) {
            return false;
          }
          if (endYear && eventYear > endYear) {
            return false;
          }
        }

        return true;
      })
      .slice(0, 5); // Limit to 5 people per event
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
      const urlObj = new URL(url);
      const { hostname, pathname } = urlObj;

      // Handle Wikipedia URLs specially to extract article title
      if (hostname.includes("wikipedia.org")) {
        const match = pathname.match(/\/wiki\/(.+)/);
        if (match) {
          // Decode and format the article title
          const title = decodeURIComponent(match[1])
            .replace(/_/g, " ")
            .replace(/#.*$/, ""); // Remove anchor links
          return { label: title, isWikipedia: true };
        }
      }

      // For other URLs, show hostname
      return { label: hostname.replace(/^www\./, ""), isWikipedia: false };
    } catch (error) {
      return { label: url, isWikipedia: false };
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

  function handleImageLoad(event) {
    const img = event.target;
    if (!img || !img.naturalWidth || !img.naturalHeight) return;

    const aspectRatio = img.naturalWidth / img.naturalHeight;
    let horizontalRadius, verticalRadius;

    if (aspectRatio > 1) {
      // Landscape: wider than tall
      horizontalRadius = Math.min(92, 80 + (aspectRatio - 1) * 8);
      verticalRadius = 85;
    } else {
      // Portrait: taller than wide
      horizontalRadius = 85;
      verticalRadius = Math.min(95, 88 + (1 / aspectRatio - 1) * 5);
    }

    // Use a linear gradient from all four sides to create rounded rect effect
    const maskImage = `
      linear-gradient(to right, transparent 0%, black ${100 - horizontalRadius}%, black ${horizontalRadius}%, transparent 100%),
      linear-gradient(to bottom, transparent 0%, black ${100 - verticalRadius}%, black ${verticalRadius}%, transparent 100%),
      radial-gradient(at top left, transparent 0%, transparent 8%, black 12%),
      radial-gradient(at top right, transparent 0%, transparent 8%, black 12%),
      radial-gradient(at bottom left, transparent 0%, transparent 8%, black 12%),
      radial-gradient(at bottom right, transparent 0%, transparent 8%, black 12%)
    `;

    const maskComposite = "intersect";

    img.style.maskImage = maskImage;
    img.style.webkitMaskImage = maskImage;
    img.style.maskComposite = maskComposite;
    img.style.webkitMaskComposite = maskComposite;
  }
  function handleThumbnailLoad(event) {
    const img = event.target;
    if (!img || !img.naturalWidth || !img.naturalHeight) return;

    const aspectRatio = img.naturalWidth / img.naturalHeight;
    let horizontalRadius, verticalRadius;

    // For thumbnails positioned at top-right
    if (aspectRatio > 1) {
      // Landscape
      horizontalRadius = Math.min(95, 80 + (aspectRatio - 1) * 10);
      verticalRadius = 80;
    } else {
      // Portrait
      horizontalRadius = 80;
      verticalRadius = Math.min(98, 85 + (1 / aspectRatio - 1) * 10);
    }

    const maskImage = `radial-gradient(
      ellipse ${horizontalRadius}% ${verticalRadius}% at 85% 15%,
      rgba(0, 0, 0, 1) 50%,
      rgba(0, 0, 0, 0.98) 65%,
      rgba(0, 0, 0, 0.85) 78%,
      rgba(0, 0, 0, 0.5) 88%,
      rgba(0, 0, 0, 0) 97%
    )`;

    img.style.maskImage = maskImage;
    img.style.webkitMaskImage = maskImage;
  }

  async function resolvePmtilesUrl() {
    if (basemapResolved) return pmtilesUrl;
    const candidates = [PRIMARY_PM_TILES_URL, FALLBACK_PM_TILES_URL].filter(
      (url, idx, arr) => Boolean(url) && arr.indexOf(url) === idx
    );
    for (const url of candidates) {
      try {
        const res = await fetch(url, { method: "HEAD" });
        if (res.ok) {
          pmtilesUrl = url;
          basemapError = null;
          basemapResolved = true;
          basemapStyleCache = null; // force rebuild style with final URL
          return pmtilesUrl;
        }
      } catch (_err) {
        // ignore and continue
      }
    }
    basemapError = "Basemap unavailable (PMTiles 404). Map disabled.";
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
      // abort map creation if basemap not available
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

  // Handle initial scroll when component loads with a specific slide index
  $: if (
    !initialScrollDone &&
    slidesContainer &&
    totalPanels > 0 &&
    activeIndex > 0
  ) {
    tick().then(() => {
      scrollToIndex(activeIndex, true);
      initialScrollDone = true;
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

<!-- svelte-ignore a11y-click-events-have-key-events -->
<!-- svelte-ignore a11y-no-static-element-interactions -->
<div
  class="story-view"
  style={storyStyleVars(styleConfig)}
  on:wheel={handleWheel}
  on:click={handleClickOutside}
>
  <header class="masthead" class:compact={true}>
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
          <button
            type="button"
            class="portrait-button"
            on:click={() =>
              enlargeImage(
                {
                  url: portrait.image,
                  caption: portrait.caption || null,
                  source: portrait.source || null,
                },
                { title: personName }
              )}
            aria-label="Enlarge portrait"
          >
            <img
              src={portrait.image}
              alt={portrait.alt ?? `Portrait of ${personName}`}
              loading="lazy"
              decoding="async"
              on:load={handleImageLoad}
            />
            <span class="enlarge-icon portrait-enlarge">
              <svg
                class="icon"
                viewBox="0 0 24 24"
                role="presentation"
                aria-hidden="true"
              >
                <path d={mdiMagnifyPlusOutline} />
              </svg>
            </span>
          </button>
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
            class:overview={slide.type === "overview"}
            aria-label={slide.type === "overview"
              ? `Overview: ${personName}`
              : `Slide ${slide.eventIndex + 1} of ${totalSlides}: ${slide.title}`}
          >
            {#if slide.type === "overview"}
              <div class="content overview-content">
                {#if portrait?.image}
                  <figure class="overview-portrait">
                    <button
                      type="button"
                      class="portrait-button"
                      on:click={() =>
                        enlargeImage(
                          {
                            url: portrait.image,
                            caption: portrait.caption || null,
                            source: portrait.source || null,
                          },
                          { title: personName }
                        )}
                      aria-label="Enlarge portrait"
                    >
                      <img
                        src={portrait.image}
                        alt={portrait.alt ?? `Portrait of ${personName}`}
                        loading="lazy"
                        decoding="async"
                        on:load={handleImageLoad}
                      />
                      <span class="enlarge-icon portrait-enlarge">
                        <svg
                          class="icon"
                          viewBox="0 0 24 24"
                          role="presentation"
                          aria-hidden="true"
                        >
                          <path d={mdiMagnifyPlusOutline} />
                        </svg>
                      </span>
                    </button>
                  </figure>
                {/if}
                <div class="overview-text">
                  <p class="eyebrow">Life Data Stories</p>
                  <h2>{personName}</h2>
                  {#if yearsLabel}
                    <p class="overview-years">{yearsLabel}</p>
                  {/if}
                  {#if rolesLabel}
                    <p class="overview-roles">{rolesLabel}</p>
                  {/if}
                  {#if hasPersonSummary}
                    <p class="description">{personSummary}</p>
                  {:else if hasDataset}
                    <p class="description placeholder">
                      A summary is not available, but key life events are listed
                      below.
                    </p>
                  {/if}
                </div>
              </div>
            {:else if slide.type !== "spacer"}
              {#if slide.images?.length}
                <div class="event-images">
                  {#each slide.images as imageData}
                    {@const imgUrl =
                      typeof imageData === "string" ? imageData : imageData.url}
                    {@const imgObj =
                      typeof imageData === "string"
                        ? { url: imageData, caption: null, source: null }
                        : imageData}
                    <button
                      type="button"
                      class="image-thumbnail"
                      on:click={() => enlargeImage(imgObj, slide)}
                      aria-label="Enlarge image"
                    >
                      <img
                        src={imgUrl}
                        alt={imgObj.caption || `Related to ${slide.title}`}
                        loading="lazy"
                        decoding="async"
                        on:load={handleThumbnailLoad}
                      />
                      <span class="enlarge-icon">
                        <svg
                          class="icon"
                          viewBox="0 0 24 24"
                          role="presentation"
                          aria-hidden="true"
                        >
                          <path d={mdiMagnifyPlusOutline} />
                        </svg>
                      </span>
                    </button>
                  {/each}
                </div>
              {/if}
              <div class="content">
                <div class="date-wrapper">
                  <p class="date">{formatDate(slide)}</p>
                  {#if getDateNote(slide)}
                    <button
                      type="button"
                      class="date-info-btn"
                      on:click|stopPropagation={() =>
                        toggleDateNote(slide.eventIndex)}
                      aria-label="Show date explanation"
                      aria-expanded={visibleDateNote === slide.eventIndex}
                    >
                      <svg
                        class="icon icon-inline"
                        viewBox="0 0 24 24"
                        role="presentation"
                        aria-hidden="true"
                      >
                        <path d={mdiInformationOutline} />
                      </svg>
                    </button>
                    {#if visibleDateNote === slide.eventIndex}
                      <div class="date-note-tooltip">
                        {getDateNote(slide)}
                      </div>
                    {/if}
                  {/if}
                </div>
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
                        {#each slide.sources as source, idx}
                          {@const sourceInfo = sourceLabel(source)}
                          {#if idx > 0}<span class="source-separator">·</span
                            >{/if}
                          <a
                            href={source}
                            target="_blank"
                            rel="noreferrer"
                            class="source-link"
                          >
                            {#if sourceInfo.isWikipedia}
                              <svg
                                class="icon icon-inline wiki-icon"
                                viewBox="0 0 24 24"
                                role="presentation"
                                aria-hidden="true"
                              >
                                <path d={mdiWikipedia} />
                              </svg>
                            {/if}
                            {sourceInfo.label}
                          </a>
                        {/each}
                      </span>
                    </li>
                  {/if}
                </ul>
                {#each [getRelevantPeople(slide)] as relevantPeople}
                  {#if relevantPeople.length > 0}
                    <ul class="details">
                      <li>
                        <span class="label">
                          <svg
                            class="icon icon-inline"
                            viewBox="0 0 24 24"
                            role="presentation"
                            aria-hidden="true"
                          >
                            <path d={mdiAccountOutline} />
                          </svg>
                          <span class="label-text">People</span>
                        </span>
                        <div class="people-list">
                          {#each relevantPeople as person, idx}
                            {@const personKey = `${slide.eventIndex}-${idx}`}
                            <div class="person-info-wrapper">
                              <button
                                type="button"
                                class="person-chip"
                                on:click|stopPropagation={(e) =>
                                  togglePersonInfo(personKey, e)}
                                aria-label={`Show information about ${person.person_name}`}
                                aria-expanded={visiblePersonInfo === personKey}
                              >
                                <span class="person-name"
                                  >{person.person_name}</span
                                >
                                <span class="person-role"
                                  >{person.relationship_type}</span
                                >
                              </button>
                              {#if visiblePersonInfo === personKey}
                                <div class="person-info-tooltip">
                                  <p class="tooltip-title">
                                    {person.person_name}
                                  </p>
                                  <p class="tooltip-relationship">
                                    {person.relationship_description}
                                  </p>
                                  {#if person.start_year || person.end_year}
                                    <p class="tooltip-years">
                                      {#if person.start_year && person.end_year}
                                        {person.start_year}–{person.end_year}
                                      {:else if person.start_year}
                                        From {person.start_year}
                                      {:else if person.end_year}
                                        Until {person.end_year}
                                      {/if}
                                    </p>
                                  {/if}
                                  {#if person.shared_activities?.length}
                                    <p class="tooltip-activities">
                                      {person.shared_activities.join(", ")}
                                    </p>
                                  {/if}
                                </div>
                              {/if}
                            </div>
                          {/each}
                        </div>
                      </li>
                    </ul>
                  {/if}
                {/each}
              </div>
            {/if}
          </section>
        {/each}
      {/if}
    </main>
    {#if hasMapData}
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
    {/if}
  </div>
  <Timeline
    {activeIndex}
    {totalSlides}
    {activeEventIndex}
    {hasMultipleEvents}
    {indicatorProgress}
    {indicatorIcons}
    {eventSlides}
    onPrevSlide={prevSlide}
    onNextSlide={nextSlide}
    onGoToEvent={goToEvent}
    onScrollToIndex={scrollToIndex}
  />
</div>

<ImageViewer image={enlargedImage} onClose={closeEnlargedImage} />

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
    background-size: 200px 200px;
    background-repeat: repeat;
    opacity: 0.35;
    mix-blend-mode: overlay;
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
    font-family: var(--story-heading-font, Inter, sans-serif);
  }

  .summary {
    margin: 0;
    font-size: 0.95rem;
    color: rgba(226, 232, 240, 0.88);
    font-family: var(--story-body-font, Inter, sans-serif);
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

  .slides-wrapper.map-enabled .slide:not(.overview) {
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
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    width: 100%;
    height: 100%;
    background-image: var(--story-pattern-image, none);
    background-size: 200px 200px;
    background-repeat: repeat;
    background-position: 0 0;
    mix-blend-mode: overlay;
    mask-image: linear-gradient(
      180deg,
      rgba(0, 0, 0, 1) 0%,
      rgba(0, 0, 0, 1) 40%,
      rgba(0, 0, 0, 0) 70%
    );
    -webkit-mask-image: linear-gradient(
      180deg,
      rgba(0, 0, 0, 1) 0%,
      rgba(0, 0, 0, 1) 40%,
      rgba(0, 0, 0, 0) 70%
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

  .slide.overview {
    justify-content: center;
    padding-bottom: 6rem;
  }

  .overview-content {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2rem;
    text-align: center;
    max-width: 56rem;
  }

  .overview-portrait {
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    align-items: center;
  }

  .overview-portrait img {
    width: min(220px, 75vw);
    height: auto;
    border-radius: 1rem;
    box-shadow: none;
    border: none;
    filter: saturate(0.55) contrast(0.8) brightness(0.92);
    mask-image: radial-gradient(
      ellipse 60% 70% at center,
      rgba(0, 0, 0, 1) 35%,
      rgba(0, 0, 0, 0.95) 50%,
      rgba(0, 0, 0, 0.7) 65%,
      rgba(0, 0, 0, 0.35) 78%,
      rgba(0, 0, 0, 0) 90%
    );
    -webkit-mask-image: radial-gradient(
      ellipse 60% 70% at center,
      rgba(0, 0, 0, 1) 35%,
      rgba(0, 0, 0, 0.95) 50%,
      rgba(0, 0, 0, 0.7) 65%,
      rgba(0, 0, 0, 0.35) 78%,
      rgba(0, 0, 0, 0) 90%
    );
  }

  .overview-text {
    display: flex;
    flex-direction: column;
    gap: 0.65rem;
  }

  .overview-text h2 {
    font-size: 1.5rem;
    line-height: 1.1;
    margin: 0;
    font-family: var(--story-heading-font, Inter, sans-serif);
  }

  .overview-years {
    font-size: 0.9rem;
    color: rgba(148, 163, 184, 0.95);
    font-weight: 500;
    margin: 0;
  }

  .overview-roles {
    font-size: 0.85rem;
    color: var(--story-secondary, #38bdf8);
    font-weight: 500;
    margin: 0;
  }

  .overview-text .eyebrow {
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.7rem;
    color: var(--story-secondary, #38bdf8);
    margin: 0;
  }

  .overview-text .description {
    margin-top: 0.5rem;
    font-size: 0.9rem;
    line-height: 1.6;
    max-width: 52ch;
    margin-left: auto;
    margin-right: auto;
    font-family: var(--story-body-font, Inter, sans-serif);
  }

  .overview-text .description.placeholder {
    color: #94a3b8;
    font-style: italic;
  }

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

  :global(.story-map-marker) {
    display: block;
    border-radius: 50%;
    border: 2px solid rgba(2, 6, 23, 0.65);
    box-shadow: 0 8px 18px rgba(2, 6, 23, 0.5);
  }

  .portrait {
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    align-items: center;
    text-align: center;
  }

  .portrait-button {
    appearance: none;
    border: none;
    padding: 0;
    margin: 0;
    cursor: pointer;
    display: block;
    position: relative;
    background: transparent;
    transition: transform 0.2s ease;
  }

  .portrait-button:hover,
  .portrait-button:focus {
    transform: scale(1.02);
    outline: none;
  }

  .portrait-enlarge {
    position: absolute;
    bottom: 0.5rem;
    right: 0.5rem;
    width: 2rem;
    height: 2rem;
    background: rgba(15, 23, 42, 0.85);
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    pointer-events: none;
    opacity: 0;
    transition: opacity 0.2s ease;
  }

  .portrait-button:hover .portrait-enlarge,
  .portrait-button:focus .portrait-enlarge {
    opacity: 1;
  }

  .portrait-enlarge .icon {
    width: 1.25rem;
    height: 1.25rem;
    fill: var(--story-secondary, #38bdf8);
  }

  .portrait img {
    width: min(220px, 80vw);
    height: auto;
    border-radius: 1rem;
    box-shadow: none;
    border: none;
    filter: saturate(0.55) contrast(0.8) brightness(0.92);
    /* Default mask to prevent pop-out before JS loads */
    mask-image: radial-gradient(
      ellipse 60% 70% at center,
      rgba(0, 0, 0, 1) 35%,
      rgba(0, 0, 0, 0.95) 50%,
      rgba(0, 0, 0, 0.7) 65%,
      rgba(0, 0, 0, 0.35) 78%,
      rgba(0, 0, 0, 0) 90%
    );
    -webkit-mask-image: radial-gradient(
      ellipse 60% 70% at center,
      rgba(0, 0, 0, 1) 35%,
      rgba(0, 0, 0, 0.95) 50%,
      rgba(0, 0, 0, 0.7) 65%,
      rgba(0, 0, 0, 0.35) 78%,
      rgba(0, 0, 0, 0) 90%
    );
  }

  .content {
    display: flex;
    flex-direction: column;
    gap: 0.8rem;
  }

  .event-images {
    position: absolute;
    top: 0;
    right: 0;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    z-index: 4;
  }

  .image-thumbnail {
    appearance: none;
    border: none;
    padding: 0;
    margin: 0;
    cursor: pointer;
    display: block;
    position: relative;
    width: 240px;
    height: 240px;
    border-radius: 0;
    overflow: hidden;
    background: transparent;
    transition:
      transform 0.2s ease,
      box-shadow 0.2s ease;
    box-shadow: none;
  }

  .image-thumbnail:hover,
  .image-thumbnail:focus {
    transform: scale(1.05);
    border-color: transparent;
    box-shadow: none;
    outline: none;
  }

  .image-thumbnail img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
    filter: saturate(0.35) contrast(0.6) brightness(0.82);
    transition:
      filter 0.2s ease,
      mask-image 0.2s ease,
      -webkit-mask-image 0.2s ease;
    /* Default mask to prevent pop-out before JS loads */
    mask-image: radial-gradient(
      ellipse 85% 85% at 85% 15%,
      rgba(0, 0, 0, 1) 50%,
      rgba(0, 0, 0, 0.98) 65%,
      rgba(0, 0, 0, 0.85) 78%,
      rgba(0, 0, 0, 0.5) 88%,
      rgba(0, 0, 0, 0) 97%
    );
    -webkit-mask-image: radial-gradient(
      ellipse 85% 85% at 85% 15%,
      rgba(0, 0, 0, 1) 50%,
      rgba(0, 0, 0, 0.98) 65%,
      rgba(0, 0, 0, 0.85) 78%,
      rgba(0, 0, 0, 0.5) 88%,
      rgba(0, 0, 0, 0) 97%
    );
  }

  .image-thumbnail:hover img,
  .image-thumbnail:focus img {
    filter: saturate(0.6) contrast(0.75) brightness(0.92);
  }

  .enlarge-icon {
    position: absolute;
    bottom: 0.25rem;
    right: 0.25rem;
    width: 1.5rem;
    height: 1.5rem;
    background: rgba(15, 23, 42, 0.8);
    border-radius: 0.25rem;
    display: flex;
    align-items: center;
    justify-content: center;
    pointer-events: none;
    opacity: 0;
    transition: opacity 0.2s ease;
  }

  .image-thumbnail:hover .enlarge-icon,
  .image-thumbnail:focus .enlarge-icon {
    opacity: 1;
  }

  .enlarge-icon .icon {
    width: 1rem;
    height: 1rem;
    fill: var(--story-secondary, #38bdf8);
  }

  .date {
    margin: 0;
    font-size: 0.9rem;
    color: var(--story-secondary, #38bdf8);
    font-weight: 600;
  }

  .date-wrapper {
    position: relative;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .date-info-btn {
    appearance: none;
    border: none;
    background: rgba(255, 255, 255, 0.08);
    color: var(--story-secondary, #38bdf8);
    padding: 0.25rem;
    border-radius: 50%;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    transition:
      background-color 0.2s ease,
      color 0.2s ease,
      transform 0.2s ease;
    flex: 0 0 auto;
    width: 1.5rem;
    height: 1.5rem;
  }

  .date-info-btn:hover,
  .date-info-btn:focus {
    background: rgba(255, 255, 255, 0.15);
    color: var(--story-primary, #f8fafc);
    transform: scale(1.1);
    outline: none;
  }

  .date-info-btn[aria-expanded="true"] {
    background: rgba(255, 255, 255, 0.2);
    color: var(--story-primary, #f8fafc);
  }

  .date-note-tooltip {
    position: absolute;
    top: calc(100% + 0.5rem);
    left: 0;
    right: 0;
    background: rgba(15, 23, 42, 0.95);
    backdrop-filter: blur(8px);
    border: 1px solid rgba(148, 163, 184, 0.3);
    border-radius: 0.5rem;
    padding: 0.75rem 1rem;
    font-size: 0.85rem;
    color: #e2e8f0;
    line-height: 1.5;
    box-shadow: 0 8px 20px rgba(0, 0, 0, 0.4);
    z-index: 10;
    animation: fadeInTooltip 0.2s ease;
  }

  @keyframes fadeInTooltip {
    from {
      opacity: 0;
      transform: translateY(-0.5rem);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
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
    font-family: var(--story-heading-font, Inter, sans-serif);
    text-shadow:
      0 2px 8px rgba(0, 0, 0, 0.8),
      0 1px 4px rgba(0, 0, 0, 0.9);
  }

  .description {
    margin: 0;
    font-size: 1rem;
    color: #e2e8f0;
    font-family: var(--story-body-font, Inter, sans-serif);
  }

  .details {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    font-size: 0.85rem;
    font-family: var(--story-body-font, Inter, sans-serif);
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
    align-items: center;
  }

  .source-separator {
    color: rgba(148, 163, 184, 0.4);
    font-weight: 300;
    user-select: none;
  }

  .source-link {
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
  }

  .sources a {
    color: rgba(148, 163, 184, 0.75);
    text-decoration: none;
    font-weight: 400;
    font-size: 0.8rem;
    transition: color 0.2s ease;
  }

  .sources a:hover,
  .sources a:focus {
    color: var(--story-secondary, #94a3b8);
    text-decoration: underline;
  }

  .wiki-icon {
    opacity: 0.7;
    flex-shrink: 0;
  }

  .people-list {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
  }

  .person-info-wrapper {
    position: relative;
  }

  .person-chip {
    appearance: none;
    border: 1px solid rgba(148, 163, 184, 0.3);
    background: rgba(255, 255, 255, 0.05);
    color: #e2e8f0;
    padding: 0.4rem 0.75rem;
    border-radius: 999px;
    font-size: 0.8rem;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    transition:
      background-color 0.2s ease,
      border-color 0.2s ease,
      transform 0.2s ease;
  }

  .person-chip:hover,
  .person-chip:focus {
    background: rgba(255, 255, 255, 0.12);
    border-color: var(--story-secondary, rgba(148, 163, 184, 0.5));
    transform: translateY(-1px);
    outline: none;
  }

  .person-chip[aria-expanded="true"] {
    background: rgba(255, 255, 255, 0.15);
    border-color: var(--story-secondary, rgba(148, 163, 184, 0.6));
  }

  .person-name {
    font-weight: 600;
    color: #e2e8f0;
  }

  .person-role {
    font-weight: 400;
    color: var(--story-secondary, #94a3b8);
    font-size: 0.75rem;
    text-transform: capitalize;
  }

  .person-info-tooltip {
    position: absolute;
    top: calc(100% + 0.5rem);
    left: 0;
    min-width: 280px;
    max-width: min(340px, 90vw);
    background: rgba(15, 23, 42, 0.95);
    backdrop-filter: blur(8px);
    border: 1px solid rgba(148, 163, 184, 0.3);
    border-radius: 0.5rem;
    padding: 0.75rem 1rem;
    box-shadow: 0 8px 20px rgba(0, 0, 0, 0.4);
    z-index: 10;
    animation: fadeInTooltip 0.2s ease;
    transition:
      left 0.2s ease,
      right 0.2s ease,
      transform 0.2s ease;
  }

  .tooltip-title {
    margin: 0 0 0.5rem 0;
    font-size: 0.9rem;
    font-weight: 600;
    color: var(--story-primary, #f8fafc);
  }

  .tooltip-relationship {
    margin: 0 0 0.5rem 0;
    font-size: 0.85rem;
    color: #e2e8f0;
    line-height: 1.5;
  }

  .tooltip-years {
    margin: 0 0 0.5rem 0;
    font-size: 0.75rem;
    color: var(--story-secondary, #94a3b8);
    font-weight: 500;
  }

  .tooltip-activities {
    margin: 0;
    font-size: 0.75rem;
    color: rgba(148, 163, 184, 0.85);
    font-style: italic;
    line-height: 1.4;
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

    .slides-wrapper.map-enabled .slide:not(.overview) {
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

    .portrait-enlarge {
      width: 2.5rem;
      height: 2.5rem;
      bottom: 0.75rem;
      right: 0.75rem;
    }

    .portrait-enlarge .icon {
      width: 1.5rem;
      height: 1.5rem;
    }

    .portrait img {
      width: 260px;
      filter: saturate(0.55) contrast(0.8) brightness(0.92);
      /* Default mask */
      mask-image: radial-gradient(
        ellipse 60% 70% at center,
        rgba(0, 0, 0, 1) 35%,
        rgba(0, 0, 0, 0.95) 50%,
        rgba(0, 0, 0, 0.7) 65%,
        rgba(0, 0, 0, 0.35) 78%,
        rgba(0, 0, 0, 0) 90%
      );
      -webkit-mask-image: radial-gradient(
        ellipse 60% 70% at center,
        rgba(0, 0, 0, 1) 35%,
        rgba(0, 0, 0, 0.95) 50%,
        rgba(0, 0, 0, 0.7) 65%,
        rgba(0, 0, 0, 0.35) 78%,
        rgba(0, 0, 0, 0) 90%
      );
    }

    .event-images {
      top: 0;
      right: 0;
    }

    .image-thumbnail {
      width: 280px;
      height: 280px;
    }

    .image-thumbnail img {
      filter: saturate(0.35) contrast(0.6) brightness(0.82);
      /* Default mask */
      mask-image: radial-gradient(
        ellipse 75% 75% at 85% 15%,
        rgba(0, 0, 0, 1) 50%,
        rgba(0, 0, 0, 0.98) 65%,
        rgba(0, 0, 0, 0.85) 78%,
        rgba(0, 0, 0, 0.5) 88%,
        rgba(0, 0, 0, 0) 97%
      );
      -webkit-mask-image: radial-gradient(
        ellipse 75% 75% at 85% 15%,
        rgba(0, 0, 0, 1) 50%,
        rgba(0, 0, 0, 0.98) 65%,
        rgba(0, 0, 0, 0.85) 78%,
        rgba(0, 0, 0, 0.5) 88%,
        rgba(0, 0, 0, 0) 97%
      );
    }

    .image-thumbnail:hover img,
    .image-thumbnail:focus img {
      filter: saturate(0.6) contrast(0.75) brightness(0.92);
    }

    .enlarge-icon {
      width: 1.75rem;
      height: 1.75rem;
    }

    .enlarge-icon .icon {
      width: 1.15rem;
      height: 1.15rem;
    }

    .overview-portrait img {
      width: 340px;
    }

    .overview-text h2 {
      font-size: 2.5rem;
    }

    .overview-years {
      font-size: 1.1rem;
    }

    .overview-roles {
      font-size: 1rem;
    }

    .overview-text .description {
      font-size: 1.1rem;
    }
  }
</style>
