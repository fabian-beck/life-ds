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
    mdiAccountMultipleOutline,
  } from "@mdi/js";
  import "maplibre-gl/dist/maplibre-gl.css";
  import maplibregl from "maplibre-gl";
  import { Protocol } from "pmtiles";
  import { layers, namedFlavor } from "@protomaps/basemaps";
  import ImageViewer from "./ImageViewer.svelte";
  import NetworkModal from "./NetworkModal.svelte";
  import PersonChip from "./PersonChip.svelte";
  import Timeline from "./Timeline.svelte";
  import { _, currentLanguage } from "../stores/language";

  export let dataset = null;
  export let egoNetwork = null;
  export let isLoading = false;
  export let loadingStage = null;
  export let activeIndex = 0;
  export let hasRegistryEntries = false;
  export let styleConfig = null;
  export let onClose = () => {};
  export let onSlideChange = () => {};

  let enlargedImage = null;
  let enlargedImageContext = null; // Store event context for caption
  let visibleDateNote = null; // Track which event's date note is visible
  let visiblePersonInfo = null; // Track which person's info is visible
  let visibleSources = null; // Track which event's sources popup is visible
  let showNetworkModal = false; // Track if network modal is open

  const DEFAULT_COORDINATES = null;
  // Local basemap (zoom 0-5) extracted from Protomaps v4 demo bucket.
  // Users can override via VITE_PROTOMAPS_PM_TILES_URL environment variable.
  const DEFAULT_PM_TILES_URL = "/basemap.pmtiles";
  const PRIMARY_PM_TILES_URL =
    import.meta.env.VITE_PROTOMAPS_PM_TILES_URL ?? DEFAULT_PM_TILES_URL;
  const FALLBACK_PM_TILES_URL =
    import.meta.env.VITE_PROTOMAPS_PM_TILES_FALLBACK_URL ??
    DEFAULT_PM_TILES_URL;
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
  let mastheadElement = null;
  let mastheadHeight = 0;
  let storyViewElement = null;

  let primaryMarkerColor = "#38BDF8";
  let fadedMarkerColor = "rgba(56, 189, 248, 0.35)";

  let pmtilesProtocol = null;
  let basemapStyleCache = null;

  $: UNKNOWN_LOCATION_LABEL = $_("story.location_unknown");

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

  // Make formatters reactive based on current language
  $: formatters = {
    day: new Intl.DateTimeFormat($currentLanguage, { dateStyle: "long" }),
    month: new Intl.DateTimeFormat($currentLanguage, {
      year: "numeric",
      month: "long",
    }),
    year: new Intl.DateTimeFormat($currentLanguage, { year: "numeric" }),
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
      segments.push(`--story-pattern-size: 500px`);
    }
    if (style.separatorGlyphDataUrl) {
      segments.push(
        `--story-separator-glyph: url(${style.separatorGlyphDataUrl})`
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
  $: chapters = Array.isArray(dataset?.chapters) ? dataset.chapters : [];
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
    initialScrollPending = false;
    scrollState = SCROLL_STATE.IDLE;

    // Clear any pending timeouts
    if (scrollStateTimeout) {
      clearTimeout(scrollStateTimeout);
      scrollStateTimeout = null;
    }
    if (scrollHandlerTimeout) {
      clearTimeout(scrollHandlerTimeout);
      scrollHandlerTimeout = null;
    }
  }

  // Close date note when slide changes
  $: if (activeIndex !== undefined) {
    visibleDateNote = null;
    visiblePersonInfo = null;
    visibleSources = null;
    showNetworkModal = false;
  }

  let slidesContainer;
  let initialScrollDone = false;
  let initialScrollPending = false;
  let descriptionOverflows = new Set(); // Track which descriptions overflow

  // Scroll state machine (replaces boolean isScrolling flag)
  const SCROLL_STATE = {
    IDLE: 'idle',
    USER_SCROLLING: 'user_scrolling',
    PROGRAMMATIC: 'programmatic',
    SETTLING: 'settling'
  };
  let scrollState = SCROLL_STATE.IDLE;
  let scrollStateTimeout = null;
  let scrollHandlerTimeout = null;
  let scrollendSupported = null;

  // Detect scrollend event support (lazy check)
  function detectScrollendSupport() {
    if (scrollendSupported !== null) return scrollendSupported;
    scrollendSupported = 'onscrollend' in window;
    return scrollendSupported;
  }

  // Setup scroll event listeners including scrollend
  function setupScrollListeners() {
    if (slidesContainer && detectScrollendSupport()) {
      slidesContainer.addEventListener('scrollend', handleScrollEnd);
    }
  }

  // Handle scrollend event (fired when scroll completes)
  function handleScrollEnd() {
    if (scrollState === SCROLL_STATE.PROGRAMMATIC) {
      scrollState = SCROLL_STATE.SETTLING;
      // Allow snap to finish
      setTimeout(() => {
        scrollState = SCROLL_STATE.IDLE;
        syncActiveIndexFromScroll();
      }, 100);
    } else if (scrollState === SCROLL_STATE.USER_SCROLLING) {
      scrollState = SCROLL_STATE.IDLE;
      syncActiveIndexFromScroll();
    }
  }

  // Sync activeIndex from current scroll position
  function syncActiveIndexFromScroll() {
    if (!slidesContainer || totalPanels === 0) return;

    const { scrollLeft, clientWidth } = slidesContainer;
    if (!clientWidth) return;

    const index = Math.round(scrollLeft / clientWidth);
    const clampedIndex = Math.min(Math.max(index, 0), totalPanels - 1);

    if (activeIndex !== clampedIndex) {
      activeIndex = clampedIndex;
    }
  }

  // Measure masthead height and update CSS variable
  function updateMastheadHeight() {
    if (mastheadElement) {
      mastheadHeight = mastheadElement.offsetHeight;
    }
  }

  function checkOverflow(element, slideId) {
    if (!element) return;

    const check = () => {
      const isOverflowing = element.scrollHeight > element.clientHeight;
      if (isOverflowing) {
        descriptionOverflows.add(slideId);
      } else {
        descriptionOverflows.delete(slideId);
      }
      descriptionOverflows = descriptionOverflows; // Trigger reactivity
    };

    // Check immediately and after content loads
    check();
    setTimeout(check, 0);

    return {
      destroy() {
        descriptionOverflows.delete(slideId);
        descriptionOverflows = descriptionOverflows;
      },
    };
  }

  async function requestScrollTo(targetIndex, options = {}) {
    const {
      immediate = false,
      source = 'unknown',
      updateStateImmediately = false
    } = options;

    if (!slidesContainer) return;

    // Validate and clamp
    const clampedIndex = Math.min(Math.max(targetIndex, 0), totalPanels - 1);

    // Cancel any pending scroll operations
    if (scrollStateTimeout) {
      clearTimeout(scrollStateTimeout);
      scrollStateTimeout = null;
    }

    // Update state machine
    scrollState = SCROLL_STATE.PROGRAMMATIC;

    // Optionally update activeIndex immediately (optimistic update)
    if (updateStateImmediately) {
      activeIndex = clampedIndex;
    }

    // Wait for DOM to settle
    await tick();

    const { clientWidth } = slidesContainer;
    if (!clientWidth) {
      scrollState = SCROLL_STATE.IDLE;
      return;
    }

    // Perform scroll
    slidesContainer.scrollTo({
      left: clampedIndex * clientWidth,
      behavior: immediate ? "auto" : "smooth",
    });

    // Fallback timeout if scrollend not supported
    if (!detectScrollendSupport()) {
      const duration = immediate ? 50 : 600;
      scrollStateTimeout = setTimeout(() => {
        scrollState = SCROLL_STATE.IDLE;
        syncActiveIndexFromScroll();
      }, duration);
    }
  }

  function prevSlide() {
    if (totalPanels === 0) return;
    const targetIndex = Math.max(0, activeIndex - 1);
    requestScrollTo(targetIndex, {
      source: 'button',
      updateStateImmediately: true
    });
  }

  function nextSlide() {
    if (totalPanels === 0) return;
    const targetIndex = Math.min(totalPanels - 1, activeIndex + 1);
    requestScrollTo(targetIndex, {
      source: 'button',
      updateStateImmediately: true
    });
  }

  function goToEvent(eventIndex) {
    if (!Number.isInteger(eventIndex)) return;
    const clamped = clamp(eventIndex, 0, Math.max(eventSlides.length - 1, 0));
    const targetIndex = clamped + 1;
    if (totalPanels === 0) return;
    requestScrollTo(targetIndex, {
      source: 'timeline_event',
      updateStateImmediately: true
    });
  }

  // Wrapper for Timeline component callbacks
  function scrollToIndexExternal(index, immediate = false) {
    requestScrollTo(index, {
      source: 'timeline_scrubber',
      immediate,
      updateStateImmediately: !immediate  // Smooth = optimistic update
    });
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
    // Ignore during programmatic scrolls
    if (scrollState === SCROLL_STATE.PROGRAMMATIC ||
        scrollState === SCROLL_STATE.SETTLING) {
      return;
    }

    if (totalPanels === 0) {
      activeIndex = 0;
      return;
    }

    // Promote to user scrolling if idle
    if (scrollState === SCROLL_STATE.IDLE) {
      scrollState = SCROLL_STATE.USER_SCROLLING;
    }

    // Debounce activeIndex updates to avoid excessive reactivity
    if (scrollHandlerTimeout) {
      clearTimeout(scrollHandlerTimeout);
    }

    scrollHandlerTimeout = setTimeout(() => {
      syncActiveIndexFromScroll();
    }, 50);

    // Fallback: detect scroll end via timeout if scrollend unavailable
    if (!detectScrollendSupport()) {
      if (scrollStateTimeout) {
        clearTimeout(scrollStateTimeout);
      }
      scrollStateTimeout = setTimeout(() => {
        if (scrollState === SCROLL_STATE.USER_SCROLLING) {
          scrollState = SCROLL_STATE.IDLE;
          syncActiveIndexFromScroll();
        }
      }, 150);
    }
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

    // Update state (was missing before!)
    scrollState = SCROLL_STATE.USER_SCROLLING;

    slidesContainer.scrollBy({
      left: dominantDelta,
      behavior: "smooth",
    });
  }

  function handleKeydown(event) {
    // Ignore if user is typing in an input field
    if (event.target.tagName === 'INPUT' ||
        event.target.tagName === 'TEXTAREA' ||
        event.target.isContentEditable) {
      return;
    }

    if (totalPanels === 0) return;

    if (event.key === 'ArrowLeft') {
      event.preventDefault();
      prevSlide();
    } else if (event.key === 'ArrowRight') {
      event.preventDefault();
      nextSlide();
    }
  }

  let touchStartX = null;
  let touchStartY = null;
  let touchStartScrollLeft = null;
  let touchStartTime = null;
  let lastTouchX = null;
  let lastTouchTime = null;

  function handleTouchStart(event) {
    if (!slidesContainer) return;
    const touch = event.touches[0];
    touchStartX = touch.clientX;
    touchStartY = touch.clientY;
    touchStartScrollLeft = slidesContainer.scrollLeft;
    touchStartTime = Date.now();
    lastTouchX = touch.clientX;
    lastTouchTime = touchStartTime;

    // Set state WITHOUT toggling scroll-snap
    scrollState = SCROLL_STATE.USER_SCROLLING;
  }

  function handleTouchMove(event) {
    if (touchStartX === null || !slidesContainer) return;
    const touch = event.touches[0];
    const deltaX = touchStartX - touch.clientX;
    const deltaY = touchStartY - touch.clientY;

    // Track last position for velocity calculation
    lastTouchX = touch.clientX;
    lastTouchTime = Date.now();

    // Only handle horizontal swipes
    if (Math.abs(deltaX) > Math.abs(deltaY)) {
      event.preventDefault();
      // Direct 1:1 mapping - no damping
      slidesContainer.scrollLeft = touchStartScrollLeft + deltaX;
    }
  }

  function handleTouchEnd(event) {
    if (!slidesContainer || touchStartX === null) {
      scrollState = SCROLL_STATE.IDLE;
      touchStartX = null;
      touchStartY = null;
      touchStartScrollLeft = null;
      touchStartTime = null;
      lastTouchX = null;
      lastTouchTime = null;
      return;
    }

    // Calculate swipe velocity
    const deltaX = touchStartX - lastTouchX;
    const deltaTime = lastTouchTime - touchStartTime;
    const velocity = deltaTime > 0 ? deltaX / deltaTime : 0; // pixels per ms

    // Decide whether to move to next/prev slide based on velocity or distance
    const swipeThreshold = slidesContainer.clientWidth * 0.3; // 30% of screen width
    const velocityThreshold = 0.3; // pixels per ms

    let direction = 0;

    if (Math.abs(velocity) > velocityThreshold) {
      // Fast swipe - use velocity
      direction = velocity > 0 ? 1 : -1; // positive deltaX = swipe left = next slide
    } else if (Math.abs(deltaX) > swipeThreshold) {
      // Slow but long swipe - use distance
      direction = deltaX > 0 ? 1 : -1;
    }

    // Reset touch state
    touchStartX = null;
    touchStartY = null;
    touchStartScrollLeft = null;
    touchStartTime = null;
    lastTouchX = null;
    lastTouchTime = null;

    if (direction !== 0) {
      const targetIndex = clamp(activeIndex + direction, 0, totalPanels - 1);
      requestScrollTo(targetIndex, {
        source: 'touch',
        updateStateImmediately: true
      });
    } else {
      // Snap back to current slide
      requestScrollTo(activeIndex, {
        source: 'touch',
        updateStateImmediately: false
      });
    }
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
    // Check if click is outside the date-wrapper, person-info-wrapper, or sources-wrapper
    const dateWrapper = event.target.closest(".date-wrapper");
    const personWrapper = event.target.closest(".person-info-wrapper");
    const sourcesWrapper = event.target.closest(".sources-wrapper");
    const modal = event.target.closest(".network-modal");
    if (!dateWrapper && visibleDateNote !== null) {
      visibleDateNote = null;
    }
    if (!personWrapper && visiblePersonInfo !== null) {
      visiblePersonInfo = null;
    }
    if (!sourcesWrapper && visibleSources !== null) {
      visibleSources = null;
    }
    if (!modal && showNetworkModal) {
      const modalOverlay = event.target.closest(".modal-overlay");
      if (modalOverlay && event.target === modalOverlay) {
        showNetworkModal = false;
      }
    }
  }

  function togglePersonInfo(personKey) {
    if (visiblePersonInfo === personKey) {
      visiblePersonInfo = null;
    } else {
      visiblePersonInfo = personKey;
    }
  }

  function toggleSources(eventIndex) {
    if (visibleSources === eventIndex) {
      visibleSources = null;
    } else {
      visibleSources = eventIndex;
    }
  }

  function getSubcategory(relationshipType) {
    if (!relationshipType || !relationshipType.includes("/")) {
      return null;
    }
    return relationshipType.split("/")[1];
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

  function openNetworkModal() {
    showNetworkModal = true;
  }

  function closeNetworkModal() {
    showNetworkModal = false;
  }

  function formatAgeLabel(age) {
    if (age === null || age === undefined) return null;
    if (age === 0) return $_("story.at_birth");
    return $_("story.age", { age });
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

  function getThumbnailUrl(imageUrl, width = 400) {
    if (!imageUrl || typeof imageUrl !== "string") return imageUrl;

    // Optimize Wikimedia Commons images
    if (imageUrl.includes("upload.wikimedia.org/wikipedia/commons/")) {
      // Convert full URL to thumbnail URL
      const parts = imageUrl.split("/wikipedia/commons/");
      if (parts.length === 2) {
        const [base, path] = parts;
        const filename = path.split("/").pop();
        return `${base}/wikipedia/commons/thumb/${path}/${width}px-${filename}`;
      }
    }

    // Return original URL for non-Wikimedia images
    return imageUrl;
  }

  function getValidImages(images) {
    if (!Array.isArray(images) || images.length === 0) return [];

    return images.filter((imageData) => {
      const url = typeof imageData === "string" ? imageData : imageData?.url;
      // Basic URL validation - check if it's a valid string and looks like a URL
      if (!url || typeof url !== "string") return false;

      // Filter out TIFF images (not supported by browsers)
      const lowerUrl = url.toLowerCase();
      if (
        lowerUrl.endsWith(".tif") ||
        lowerUrl.endsWith(".tiff") ||
        lowerUrl.includes(".tif?") ||
        lowerUrl.includes(".tiff?")
      ) {
        return false;
      }

      try {
        new URL(url);
        return true;
      } catch {
        return false;
      }
    });
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
      markerElement.classList.add("current");
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
    activeIndex > 0 &&
    !initialScrollPending
  ) {
    initialScrollPending = true;
    tick().then(() => {
      requestScrollTo(activeIndex, {
        source: 'initial',
        immediate: true
      });
      initialScrollDone = true;
      initialScrollPending = false;
    });
  }

  onMount(() => {
    initialiseMap();
    updateMastheadHeight();

    // Setup scroll event listeners
    if (slidesContainer) {
      setupScrollListeners();
    }

    // Focus story view to enable keyboard navigation
    if (storyViewElement) {
      storyViewElement.focus();
    }

    // Update height on window resize for Android viewport changes
    const resizeObserver = new ResizeObserver(() => {
      updateMastheadHeight();
    });

    if (mastheadElement) {
      resizeObserver.observe(mastheadElement);
    }

    return () => {
      resizeObserver.disconnect();

      // Cleanup scroll listeners
      if (slidesContainer && detectScrollendSupport()) {
        slidesContainer.removeEventListener('scrollend', handleScrollEnd);
      }

      // Clear pending timeouts
      if (scrollStateTimeout) {
        clearTimeout(scrollStateTimeout);
        scrollStateTimeout = null;
      }
      if (scrollHandlerTimeout) {
        clearTimeout(scrollHandlerTimeout);
        scrollHandlerTimeout = null;
      }
    };
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

    // Final cleanup
    if (scrollStateTimeout) {
      clearTimeout(scrollStateTimeout);
      scrollStateTimeout = null;
    }
    if (scrollHandlerTimeout) {
      clearTimeout(scrollHandlerTimeout);
      scrollHandlerTimeout = null;
    }
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
  bind:this={storyViewElement}
  class="story-view"
  style="{storyStyleVars(styleConfig)}; --header-height: {mastheadHeight}px"
  on:wheel={handleWheel}
  on:click={handleClickOutside}
  on:keydown={handleKeydown}
  tabindex="-1"
  role="region"
  aria-label="Story viewer"
>
  <header class="masthead" bind:this={mastheadElement}>
    <div class="compact-info" aria-live="polite">
      <span class="name">{personName}</span>
      {#if yearsLabel}
        {#if styleConfig?.separatorGlyphDataUrl}
          <span class="separator glyph-separator" aria-hidden="true"></span>
        {:else}
          <span class="separator">·</span>
        {/if}
        <span class="lifespan">{yearsLabel}</span>
      {/if}
      <button
        type="button"
        class="close-story compact"
        on:click={handleClose}
        aria-label={$_("story.close_story")}
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
      on:touchstart={handleTouchStart}
      on:touchmove={handleTouchMove}
      on:touchend={handleTouchEnd}
    >
      {#if isLoading}
        <section
          class="slide overview loading-slide"
          aria-label={$_("story.loading_life")}
        >
          <div class="content overview-content">
            <div class="skeleton-portrait"></div>
            <div class="overview-text">
              <div class="skeleton-text skeleton-eyebrow"></div>
              <div class="skeleton-text skeleton-title"></div>
              <div class="skeleton-text skeleton-years"></div>
              <div class="skeleton-text skeleton-roles"></div>
              <div class="skeleton-paragraph">
                <div class="skeleton-text skeleton-line"></div>
                <div class="skeleton-text skeleton-line"></div>
                <div
                  class="skeleton-text skeleton-line"
                  style="width: 80%;"
                ></div>
              </div>
            </div>
          </div>
          <div class="loading-indicator">
            <div class="spinner"></div>
            <p class="loading-text">
              {#if loadingStage === "initial" || loadingStage === "dataset"}
                {$_("story.loading_life")}
              {:else if loadingStage === "network"}
                {$_("story.loading_network")}
              {:else}
                {$_("story.loading_life")}
              {/if}
            </p>
          </div>
        </section>
      {:else if totalPanels > 0}
        {#each slides as slide}
          <section
            class="slide slide-loaded"
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
                      aria-label={$_("story.enlarge_portrait")}
                    >
                      <img
                        src={getThumbnailUrl(portrait.image, 400)}
                        srcset={`${getThumbnailUrl(portrait.image, 400)} 1x, ${getThumbnailUrl(portrait.image, 800)} 2x`}
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
                  <h2>{personName}</h2>
                  {#if yearsLabel}
                    <p class="overview-years">{yearsLabel}</p>
                  {/if}
                  {#if rolesLabel}
                    <p class="overview-roles">{rolesLabel}</p>
                  {/if}
                  {#if hasPersonSummary}
                    <p
                      class="description"
                      class:has-fade={descriptionOverflows.has("overview")}
                      use:checkOverflow={"overview"}
                    >
                      {personSummary}
                    </p>
                  {:else if hasDataset}
                    <p class="description placeholder">
                      {$_("story.no_summary")}
                    </p>
                  {/if}
                </div>
              </div>
            {:else if slide.type !== "spacer"}
              {@const validImages = getValidImages(slide.images)}
              {#if validImages.length > 0}
                <div class="event-images">
                  {#each validImages as imageData}
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
                      aria-label={$_("story.enlarge_image")}
                    >
                      <img
                        src={getThumbnailUrl(imgUrl, 400)}
                        srcset={`${getThumbnailUrl(imgUrl, 400)} 1x, ${getThumbnailUrl(imgUrl, 800)} 2x`}
                        alt=""
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
              <div class="content event-content">
                <div class="event-header">
                  <div class="date-wrapper">
                    <p class="date">{formatDate(slide)}</p>
                    {#if formatAgeLabel(slide.age)}
                      {#if styleConfig?.separatorGlyphDataUrl}
                        <span
                          class="separator glyph-separator"
                          aria-hidden="true"
                        ></span>
                      {:else}
                        <span class="separator">·</span>
                      {/if}
                      <p class="age">{formatAgeLabel(slide.age)}</p>
                    {/if}
                    {#if getDateNote(slide)}
                      <button
                        type="button"
                        class="date-info-btn"
                        on:click|stopPropagation={() =>
                          toggleDateNote(slide.eventIndex)}
                        aria-label={$_("story.show_date_explanation")}
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
                  <h2>{slide.title}</h2>
                </div>
                <div class="event-body">
                  <div class="event-description">
                    <p
                      class="description"
                      class:has-fade={descriptionOverflows.has(
                        slide.eventIndex
                      )}
                      use:checkOverflow={slide.eventIndex}
                    >
                      {slide.description}
                    </p>
                  </div>
                  <div class="event-details">
                    {#each [getRelevantPeople(slide)] as relevantPeople}
                      {#if relevantPeople.length > 0}
                        <ul class="details">
                          <li>
                            <span class="label" aria-label="People">
                              <svg
                                class="icon icon-inline"
                                viewBox="0 0 24 24"
                                role="presentation"
                                aria-hidden="true"
                              >
                                <path d={mdiAccountOutline} />
                              </svg>
                            </span>
                            <div class="people-list">
                              {#each relevantPeople as person, idx}
                                {@const personKey = `${slide.eventIndex}-${idx}`}
                                {@const subcategory = getSubcategory(
                                  person.relationship_type
                                )}
                                <PersonChip
                                  {person}
                                  {personKey}
                                  {visiblePersonInfo}
                                  {subcategory}
                                  onToggle={togglePersonInfo}
                                />
                              {/each}
                              <button
                                type="button"
                                class="show-all-btn"
                                on:click={openNetworkModal}
                                aria-label={$_("story.show_network")}
                              >
                                <svg
                                  class="icon icon-inline"
                                  viewBox="0 0 24 24"
                                  role="presentation"
                                  aria-hidden="true"
                                >
                                  <path d={mdiAccountMultipleOutline} />
                                </svg>
                              </button>
                            </div>
                          </li>
                        </ul>
                      {/if}
                    {/each}
                    {#if (slide.locations?.length && formatLocations(slide.locations) !== UNKNOWN_LOCATION_LABEL) || slide.sources?.length}
                      <ul class="details details-compact">
                        <li>
                          {#if slide.locations?.length && formatLocations(slide.locations) !== UNKNOWN_LOCATION_LABEL}
                            <span class="label" aria-label="Location">
                              <svg
                                class="icon icon-inline"
                                viewBox="0 0 24 24"
                                role="presentation"
                                aria-hidden="true"
                              >
                                <path d={mdiMapMarkerOutline} />
                              </svg>
                            </span>
                            <span>{formatLocations(slide.locations)}</span>
                          {/if}
                          {#if slide.sources?.length}
                            <div class="sources-wrapper">
                              <span class="label" aria-label="Sources">
                                <svg
                                  class="icon icon-inline"
                                  viewBox="0 0 24 24"
                                  role="presentation"
                                  aria-hidden="true"
                                >
                                  <path d={mdiLinkVariant} />
                                </svg>
                              </span>
                              <button
                                type="button"
                                class="sources-toggle-btn"
                                on:click|stopPropagation={() =>
                                  toggleSources(slide.eventIndex)}
                                aria-label={$_("story.show_sources")}
                                aria-expanded={visibleSources ===
                                  slide.eventIndex}
                              >
                                {slide.sources.length === 1
                                  ? $_("story.source_one", { count: 1 })
                                  : $_("story.source_other", {
                                      count: slide.sources.length,
                                    })}
                                <svg
                                  class="icon icon-inline"
                                  viewBox="0 0 24 24"
                                  role="presentation"
                                  aria-hidden="true"
                                >
                                  <path d={mdiInformationOutline} />
                                </svg>
                              </button>
                              {#if visibleSources === slide.eventIndex}
                                <div class="sources-popup">
                                  <ul class="sources-list">
                                    {#each slide.sources as source, idx}
                                      {@const sourceInfo = sourceLabel(source)}
                                      <li>
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
                                      </li>
                                    {/each}
                                  </ul>
                                </div>
                              {/if}
                            </div>
                          {/if}
                        </li>
                      </ul>
                    {/if}
                  </div>
                </div>
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
    {chapters}
    onPrevSlide={prevSlide}
    onNextSlide={nextSlide}
    onGoToEvent={goToEvent}
    onScrollToIndex={scrollToIndexExternal}
  />
</div>

<ImageViewer image={enlargedImage} onClose={closeEnlargedImage} />

{#if showNetworkModal}
  <NetworkModal
    {egoNetwork}
    {personName}
    {styleConfig}
    onClose={closeNetworkModal}
  />
{/if}

<style>
  .story-view {
    display: flex;
    flex-direction: column;
    position: fixed;
    inset: 0;
    background-color: rgba(var(--story-bg-rgb, 15, 23, 42), 0.55);
    color: #e2e8f0;
    isolation: isolate;
    overflow: hidden;
    height: 100vh;
    height: 100dvh;
  }

  .story-view:focus {
    outline: none;
  }

  /* Loading skeleton styles */
  .loading-slide {
    animation: fadeIn 0.3s ease;
  }

  @keyframes fadeIn {
    from {
      opacity: 0;
    }
    to {
      opacity: 1;
    }
  }

  .skeleton-portrait {
    width: min(220px, 80vw);
    height: min(220px, 30vh);
    border-radius: 1rem;
    background: linear-gradient(
      90deg,
      rgba(148, 163, 184, 0.1) 0%,
      rgba(148, 163, 184, 0.2) 50%,
      rgba(148, 163, 184, 0.1) 100%
    );
    background-size: 200% 100%;
    animation: shimmer 2s infinite;
  }

  .skeleton-text {
    height: 1em;
    border-radius: 0.25rem;
    background: linear-gradient(
      90deg,
      rgba(148, 163, 184, 0.1) 0%,
      rgba(148, 163, 184, 0.2) 50%,
      rgba(148, 163, 184, 0.1) 100%
    );
    background-size: 200% 100%;
    animation: shimmer 2s infinite;
    margin-bottom: 0.5rem;
  }

  .skeleton-eyebrow {
    width: 120px;
    height: 0.7rem;
  }

  .skeleton-title {
    width: 280px;
    max-width: 90%;
    height: 1.5rem;
    margin-top: 0.5rem;
  }

  .skeleton-years {
    width: 100px;
    height: 0.9rem;
  }

  .skeleton-roles {
    width: 200px;
    max-width: 70%;
    height: 0.85rem;
  }

  .skeleton-paragraph {
    margin-top: 1rem;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .skeleton-line {
    width: 100%;
    height: 0.9rem;
  }

  @keyframes shimmer {
    0% {
      background-position: 200% 0;
    }
    100% {
      background-position: -200% 0;
    }
  }

  .loading-indicator {
    position: absolute;
    bottom: 4rem;
    left: 50%;
    transform: translateX(-50%);
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.75rem;
    z-index: 10;
  }

  .spinner {
    width: 32px;
    height: 32px;
    border: 3px solid rgba(148, 163, 184, 0.2);
    border-top-color: var(--story-secondary, #38bdf8);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }

  .loading-text {
    margin: 0;
    font-size: 0.9rem;
    color: rgba(148, 163, 184, 0.9);
    font-weight: 500;
    animation: pulse 2s ease-in-out infinite;
  }

  @keyframes pulse {
    0%,
    100% {
      opacity: 1;
    }
    50% {
      opacity: 0.5;
    }
  }

  .story-view::before {
    content: "";
    position: absolute;
    inset: 0;
    pointer-events: none;
    background-image: var(--story-pattern-image, none);
    background-size: var(--story-pattern-size, 400px);
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
    padding: 0.5rem 1rem;
    display: flex;
    flex-direction: row;
    align-items: center;
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
  }

  /* Responsive scaling: Height-based breakpoints (600px, 700px, 800px)
     - Mobile portrait and short landscape: use defaults
     - Taller viewports: progressively increase spacing and font sizes */
  @media (min-height: 600px) {
    .masthead {
      padding: 0.65rem 1.15rem;
    }
  }

  @media (min-height: 700px) {
    .masthead {
      padding: 0.75rem 1.2rem;
    }
  }

  @media (min-height: 800px) {
    .masthead {
      padding: 0.85rem 1.25rem;
    }
  }

  .compact-info {
    display: flex;
    width: 100%;
    justify-content: space-between;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.85rem;
    font-weight: 600;
    color: #e2e8f0;
    white-space: nowrap;
    max-width: 100%;
    overflow: hidden;
  }

  /* Increase font size based on viewport height */
  @media (min-height: 600px) {
    .compact-info {
      gap: 0.65rem;
      font-size: 0.9rem;
    }
  }

  @media (min-height: 700px) {
    .compact-info {
      gap: 0.7rem;
      font-size: 0.925rem;
    }
  }

  @media (min-height: 800px) {
    .compact-info {
      gap: 0.75rem;
      font-size: 0.95rem;
    }
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

  .compact-info .separator.glyph-separator {
    width: 1em;
    height: 1em;
    display: inline-block;
    background-image: var(--story-separator-glyph);
    background-size: contain;
    background-repeat: no-repeat;
    background-position: center;
    opacity: 0.7;
    vertical-align: middle;
    margin: 0 0.15rem;
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
    padding: 0.3rem 0.7rem;
    font-size: 0.75rem;
    font-weight: 600;
    cursor: pointer;
    flex: 0 0 auto;
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    transition:
      border-color 0.2s ease,
      background-color 0.2s ease,
      color 0.2s ease;
  }

  /* Increase close button size based on viewport height */
  @media (min-height: 600px) {
    .close-story {
      padding: 0.35rem 0.8rem;
      font-size: 0.8rem;
      gap: 0.4rem;
    }
  }

  @media (min-height: 700px) {
    .close-story {
      padding: 0.4rem 0.875rem;
      font-size: 0.825rem;
      gap: 0.425rem;
    }
  }

  @media (min-height: 800px) {
    .close-story {
      padding: 0.45rem 0.95rem;
      font-size: 0.85rem;
      gap: 0.45rem;
    }
  }

  /* Compact masthead for landscape mobile (short viewports)
     - Applies to rotated phones with limited vertical space
     - Makes header more compact to preserve screen real estate */
  @media (max-height: 500px) and (orientation: landscape) {
    .masthead {
      padding: 0.35rem 0.9rem;
    }

    .compact-info {
      font-size: 0.75rem;
      gap: 0.4rem;
    }

    .close-story {
      padding: 0.25rem 0.6rem;
      font-size: 0.7rem;
      gap: 0.3rem;
    }
  }

  .close-story:hover,
  .close-story:focus {
    border-color: var(--story-primary, rgba(148, 163, 184, 0.6));
    background: rgba(255, 255, 255, 0.12);
    outline: none;
  }

  .close-story.compact {
    flex: 0 0 auto;
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

  .label .icon-inline {
    width: 1.15em;
    height: 1.15em;
  }

  .slides-wrapper {
    flex: 1 1 auto;
    position: relative;
    min-height: 0;
    display: flex;
    flex-direction: column;
    overflow: hidden;
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
    scrollbar-width: none;
    -ms-overflow-style: none;
  }

  .slides::-webkit-scrollbar {
    display: none;
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
    overflow: visible;
  }

  .slide-loaded {
    animation: fadeIn 0.3s ease-out;
  }

  @keyframes fadeIn {
    from {
      opacity: 0;
    }
    to {
      opacity: 1;
    }
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
    background-size: var(--story-pattern-size, 400px);
    background-repeat: repeat;
    background-position: 0 calc(-1 * var(--header-height, 0px));
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
    width: min(54rem, 100%);
    margin: 0 auto;
  }

  /* Two-column layout for event content on wide screens */
  .event-content {
    display: flex;
    flex-direction: column;
  }

  .event-header {
    width: 100%;
    flex-shrink: 0;
  }

  .event-body {
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
    flex-shrink: 0;
  }

  .event-description {
    width: 100%;
  }

  .event-details {
    width: 100%;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  /* Adjust spacing based on viewport height */
  @media (min-height: 600px) {
    .event-body {
      margin-top: 0.5rem;
    }
  }

  @media (min-height: 800px) {
    .event-body {
      margin-top: 1rem;
    }
  }

  @media (min-height: 1000px) {
    .event-body {
      margin-top: 1.25rem;
    }
  }

  /* Two-column layout for landscape mobile and wider screens */
  @media (min-width: 640px) and (orientation: landscape), (min-width: 900px) {
    .event-body {
      display: grid;
      grid-template-columns: 2fr 1fr;
      gap: 2rem;
      align-items: start;
    }

    .event-description {
      grid-column: 1;
    }

    .event-details {
      grid-column: 2;
    }
  }

  .slide.overview {
    justify-content: flex-start;
    padding-top: 2rem;
    padding-bottom: 8rem;
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
    width: fit-content;
  }

  .overview-portrait img {
    max-width: 100%;
    max-height: min(30dvh, 220px);
    width: auto;
    height: auto;
    object-fit: contain;
    border-radius: 1rem;
    box-shadow: none;
    border: none;
    filter: saturate(0.55) contrast(0.8) brightness(0.92);
    mask-image: radial-gradient(
      ellipse 45% 55% at center,
      rgba(0, 0, 0, 1) 35%,
      rgba(0, 0, 0, 0.95) 50%,
      rgba(0, 0, 0, 0.7) 65%,
      rgba(0, 0, 0, 0.35) 78%,
      rgba(0, 0, 0, 0) 90%
    );
    -webkit-mask-image: radial-gradient(
      ellipse 45% 55% at center,
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
    margin-left: auto;
    margin-right: auto;
    font-family: var(--story-body-font, Inter, sans-serif);
    max-height: 30vh;
    overflow-y: auto;
  }

  .overview-text .description.has-fade {
    padding-bottom: 1.5em;
    padding-right: 0.5em;
    -webkit-mask-image: linear-gradient(
      to bottom,
      black calc(100% - 2em),
      transparent 100%
    );
    mask-image: linear-gradient(
      to bottom,
      black calc(100% - 2em),
      transparent 100%
    );
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

  .portrait-button {
    appearance: none;
    border: none;
    padding: 0;
    margin: 0;
    cursor: pointer;
    display: block;
    position: relative;
    background: transparent;
  }

  .portrait-button:focus {
    outline: none;
  }

  .content {
    display: flex;
    flex-direction: column;
    gap: 0.8rem;
    position: relative;
    z-index: 4;
  }

  .event-images {
    position: absolute;
    top: 0;
    right: 0;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    z-index: 3;
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
    box-shadow: none;
  }

  .image-thumbnail:focus {
    outline: none;
  }

  .image-thumbnail img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
    filter: saturate(0.35) contrast(0.6) brightness(0.82);
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

  .enlarge-icon {
    position: absolute;
    bottom: 0.25rem;
    right: 0;
    width: 1.5rem;
    height: 1.5rem;
    background: rgba(15, 23, 42, 0.8);
    border-radius: 0.25rem;
    display: flex;
    align-items: center;
    justify-content: center;
    pointer-events: none;
    opacity: 1;
    transition: opacity 0.2s ease;
  }

  .enlarge-icon .icon {
    width: 1rem;
    height: 1rem;
    fill: var(--story-primary, #f8fafc);
  }

  .date {
    margin: 0;
    font-size: 0.9rem;
    color: var(--story-secondary, #38bdf8);
    font-weight: 600;
    text-shadow:
      0 2px 8px rgba(0, 0, 0, 0.8),
      0 1px 4px rgba(0, 0, 0, 0.9);
  }

  .date-wrapper {
    position: relative;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .date-wrapper .separator.glyph-separator {
    width: 0.9em;
    height: 0.9em;
    display: inline-block;
    background-image: var(--story-separator-glyph);
    background-size: contain;
    background-repeat: no-repeat;
    background-position: center;
    opacity: 0.6;
    vertical-align: middle;
    flex-shrink: 0;
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
    text-shadow:
      0 2px 8px rgba(0, 0, 0, 0.8),
      0 1px 4px rgba(0, 0, 0, 0.9);
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
    font-size: 0.9rem;
    color: #e2e8f0;
    font-family: var(--story-body-font, Inter, sans-serif);
    text-shadow:
      0 2px 8px rgba(0, 0, 0, 0.8),
      0 1px 4px rgba(0, 0, 0, 0.9);
    max-height: 25vh;
    overflow-y: auto;
  }

  .description.has-fade {
    padding-bottom: 1.5em;
    padding-right: 0.5em;
    -webkit-mask-image: linear-gradient(
      to bottom,
      black calc(100% - 2em),
      transparent 100%
    );
    mask-image: linear-gradient(
      to bottom,
      black calc(100% - 2em),
      transparent 100%
    );
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
    text-shadow:
      0 2px 8px rgba(0, 0, 0, 0.8),
      0 1px 4px rgba(0, 0, 0, 0.9);
  }

  .details li {
    display: flex;
    flex-direction: row;
    gap: 0.5rem;
    align-items: baseline;
  }

  .details.details-compact li {
    display: flex;
    flex-direction: row;
    flex-wrap: wrap;
    gap: 0.75rem;
    align-items: center;
  }

  .details li > span:not(.label),
  .details li > div {
    flex: 1;
    min-width: 0;
  }

  .details.details-compact li > span:not(.label) {
    flex: 0 1 auto;
  }

  .label {
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.7rem;
    color: rgba(148, 163, 184, 0.76);
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    flex-shrink: 0;
  }

  .label-text {
    line-height: 1;
  }

  .sources-wrapper {
    position: relative;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex: 1;
    min-width: 0;
  }

  .sources-toggle-btn {
    appearance: none;
    border: none;
    background: rgba(255, 255, 255, 0.08);
    color: var(--story-secondary, #38bdf8);
    padding: 0.35rem 0.65rem;
    border-radius: 999px;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 0.35rem;
    font-size: 0.75rem;
    font-weight: 500;
    transition:
      background-color 0.2s ease,
      color 0.2s ease,
      transform 0.2s ease;
    flex-shrink: 0;
  }

  .sources-toggle-btn:hover,
  .sources-toggle-btn:focus {
    background: rgba(255, 255, 255, 0.15);
    color: var(--story-primary, #f8fafc);
    transform: scale(1.05);
    outline: none;
  }

  .sources-toggle-btn[aria-expanded="true"] {
    background: rgba(255, 255, 255, 0.2);
    color: var(--story-primary, #f8fafc);
  }

  .sources-popup {
    position: absolute;
    top: calc(100% + 0.5rem);
    left: 0;
    right: 0;
    background: rgba(15, 23, 42, 0.95);
    backdrop-filter: blur(8px);
    border: 1px solid rgba(148, 163, 184, 0.3);
    border-radius: 0.5rem;
    padding: 0.75rem;
    box-shadow: 0 8px 20px rgba(0, 0, 0, 0.4);
    z-index: 10;
    animation: fadeInTooltip 0.2s ease;
    max-height: 200px;
    overflow-y: auto;
  }

  .sources-list {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .sources-list li {
    display: block;
  }

  .source-link {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    color: rgba(148, 163, 184, 0.85);
    text-decoration: none;
    font-weight: 400;
    font-size: 0.8rem;
    transition: color 0.2s ease;
    word-break: break-word;
  }

  .source-link:hover,
  .source-link:focus {
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

  .people-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    flex-wrap: wrap;
  }

  .show-all-btn {
    appearance: none;
    border: 1px solid var(--story-primary, rgba(148, 163, 184, 0.3));
    background: rgba(255, 255, 255, 0.05);
    color: var(--story-primary, #e2e8f0);
    padding: 0.35rem 0.65rem;
    border-radius: 999px;
    font-size: 0.75rem;
    font-weight: 600;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    transition:
      background-color 0.2s ease,
      border-color 0.2s ease,
      transform 0.2s ease;
  }

  .show-all-btn:hover,
  .show-all-btn:focus {
    background: rgba(255, 255, 255, 0.12);
    border-color: var(--story-primary, rgba(148, 163, 184, 0.6));
    transform: translateY(-1px);
    outline: none;
  }

  /* Tablet and desktop styles
     - Requires both width (768px+) AND height (600px+) to prevent
       applying desktop styles to landscape phones with short viewports */
  @media (min-width: 768px) and (min-height: 600px) {
    .masthead {
      padding: 1rem 2.5rem;
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
    }

    .details {
      font-size: 0.9rem;
      flex-direction: column;
      max-width: none;
      width: 100%;
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
      right: 0;
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
      width: min(380px, 35vw);
      height: min(380px, 35vh);
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

    .enlarge-icon {
      width: 1.75rem;
      height: 1.75rem;
    }

    .enlarge-icon .icon {
      width: 1.15rem;
      height: 1.15rem;
    }

    .overview-portrait img {
      max-width: 340px;
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
