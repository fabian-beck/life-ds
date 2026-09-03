<script>
  import { tick, onMount, onDestroy } from "svelte";
  import {
    buildSlides,
    eventToSlideIndex,
    rawEventToSlideIndex,
    slideToEventIndex,
  } from "../utils/story/storyModel.js";
  import { relatedPersonsByRole } from "../utils/story/personMatching.js";
  import { replace } from "svelte-spa-router";
  import { location } from "../stores/router.js";
  import CloseButton from "./CloseButton.svelte";
  import { mdiAccountMultipleOutline } from "@mdi/js";
  import {
    queryParams,
    buildUrlWithParams,
    navigationContext,
  } from "../stores/queryParams";
  import ImageViewer from "./ImageViewer.svelte";
  import NetworkModal from "./NetworkModal.svelte";
  import OverviewSlide from "./OverviewSlide.svelte";
  import StoryLoadingSlide from "./StoryLoadingSlide.svelte";
  import EventSlide from "./EventSlide.svelte";
  import EventDepth from "./EventDepth.svelte";
  import ChapterSlide from "./ChapterSlide.svelte";
  import ConclusionSlide from "./ConclusionSlide.svelte";
  // StoryMap is imported on demand where it is rendered: it pulls in MapLibre
  // and its basemap dependencies (~1.1 MB), and only stories with location data
  // ever show it. storyMapComponent stays null until the chunk resolves, which
  // the existing null check in resetMapViewport() already accounts for.
  import Timeline from "./Timeline.svelte";
  import AIDisclaimerModal from "./AIDisclaimerModal.svelte";
  import AIGeneratedButton from "./AIGeneratedButton.svelte";
  import { _, currentLanguage } from "../stores/language";
  import { clamp, displayName, storyStyleVars } from "../utils/helpers.js";
  import { createAxisLock } from "../utils/gestureAxis.js";
  import {
    computeYearsLabel,
    createDateFormatters,
    toTimestamp,
  } from "../utils/story/dates.js";
  import {
    getEventDepth,
    hasBackgroundReport,
    selectDeepEventIndexes,
  } from "../utils/story/eventDepth.js";
  import { resolveEventIcon } from "../utils/story/eventIcons.js";
  import {
    getMigrationPath,
    isCoordinate,
    normalizeAllLocations,
    normalizePrimaryLocation,
  } from "../utils/story/geo.js";
  import { collectStoryImages } from "../utils/story/images.js";
  import { logEvent } from "../evaluation/log.js";

  export let dataset = null;
  export let egoNetwork = null;
  export let personsRegistry = null;
  export let personStylesRegistry = null;
  export let isLoading = false;
  export let loadingStage = null;
  export let activeIndex = 0;
  export let targetEventIndex = null; // Optional: if set, navigate to this event index
  export let styleConfig = null;
  export let onClose = () => {};
  export let onSlideChange = () => {};

  let enlargedImage = null;
  let currentImageGlobalIndex = -1;
  let visibleDateNote = null;
  let visiblePersonInfo = null;
  let visibleAnnotation = null;

  // An open popup is drawn from the foot of the description, which is where the
  // invitation down sits. Two things cannot have that spot, and the one the
  // reader just asked for wins.
  $: popupOpen =
    visibleDateNote !== null ||
    visiblePersonInfo !== null ||
    visibleAnnotation !== null;
  let showAIModal = false;

  // Network modal state - reactive to URL query parameter
  $: showNetworkModal = $queryParams.network;
  $: closeStoryLabel = $queryParams.from_meta
    ? $_("story.close_story_to_collection")
    : $_("story.close_story");

  // Timeline expanded state - check if timeline parameter is in URL
  $: hasTimelineParam = new URLSearchParams($location.split("?")[1] || "").has(
    "timeline"
  );
  // Default to collapsed unless explicitly set via URL parameter
  $: initialTimelineExpanded = hasTimelineParam ? $queryParams.timeline : false;

  const DEFAULT_COORDINATES = null;
  let lastDatasetName = null;
  let datasetName = null;
  let mastheadElement = null;
  let mastheadHeight = 0;
  let storyViewElement = null;
  let storyMapComponent = null;

  // Make formatters reactive based on current language
  $: formatters = createDateFormatters($currentLanguage);

  $: person = dataset?.person ?? {};
  $: events = Array.isArray(dataset?.events) ? dataset.events : [];
  $: chapters = Array.isArray(dataset?.chapters) ? dataset.chapters : [];
  $: portrait = person?.portrait;
  $: personName = displayName(person?.name);
  $: personSummary = person?.summary ?? "";
  $: birthDate = person?.birth_date ?? person?.birthDate ?? null;
  $: yearsLabel = computeYearsLabel(person, $currentLanguage);
  $: roles = Array.isArray(person?.primary_roles) ? person.primary_roles : [];
  $: eventSlides = events
    // Capture each event's original position in the source array before
    // sorting — external references (LandingMap markers, meta-story
    // event_index entries) address events by this raw position, not by
    // where the story's chronological sort ends up placing them.
    .map((event, rawIndex) => ({ ...event, rawIndex }))
    .sort((a, b) => toTimestamp(a) - toTimestamp(b))
    .map((event, eventIndex) => ({ ...event, eventIndex }))
    .map((event) => ({
      ...event,
      coordinates: normalizePrimaryLocation(event),
      allCoordinates: normalizeAllLocations(event),
    }));
  $: totalSlides = eventSlides.length;
  $: conclusion = dataset?.conclusion ?? null;

  // Collect all unique sources from events for the conclusion slide
  $: allSources = (() => {
    const sourcesSet = new Set();
    events.forEach((event) => {
      if (Array.isArray(event.sources)) {
        event.sources.forEach((source) => sourcesSet.add(source));
      }
    });
    return Array.from(sourcesSet);
  })();

  // Compute related persons by role overlap
  $: relatedPersons = relatedPersonsByRole({
    person,
    registry: personsRegistry,
    egoNetwork,
  });

  $: slides = buildSlides({
    events: eventSlides,
    chapters,
    conclusion,
    relatedPersons,
    allSources,
  });

  $: totalPanels = slides.length;

  // Normalize an out-of-range slide index (a malformed deep link, or a story
  // that shrank on regeneration) once the real panel count is known — not the
  // single-slide placeholder shown while the dataset is still loading, which
  // would otherwise clamp the request to slide 0 before the true count exists.
  // Leaving it out of range means the initial-scroll logic below never runs,
  // which leaves the whole story hidden behind the initial-loading class
  // forever.
  $: if (
    !isLoading &&
    dataset &&
    totalPanels > 0 &&
    activeIndex !== undefined &&
    activeIndex !== null &&
    (activeIndex < 0 || activeIndex >= totalPanels)
  ) {
    activeIndex = clamp(activeIndex, 0, totalPanels - 1);
  }

  $: slideIndexToEventIndex = slideToEventIndex(slides);
  $: eventIndexToSlideIndex = eventToSlideIndex(slides);
  $: rawEventIndexToSlideIndex = rawEventToSlideIndex(slides);

  // What a slide is called, for its own `aria-label` and for the status region
  // that announces slide changes. One expression, so the two cannot drift.
  function slideLabel(slide) {
    if (!slide) return "";
    if (slide.type === "overview") return `Overview: ${personName}`;
    if (slide.type === "chapter") return `Chapter: ${slide.chapter.headline}`;
    if (slide.type === "conclusion") return $_("conclusion.aria_label");
    return `Slide ${slide.eventIndex + 1} of ${totalSlides}: ${slide.title}`;
  }

  // Navigating a story moves the scroll position; it inserts nothing. So the
  // one thing worth announcing has to be published deliberately, from a region
  // that holds the slide's identity and nothing else. `main.slides` used to
  // carry `aria-live` instead, which announced the whole biography on load —
  // every slide arrives in a single insertion — and then went silent for every
  // slide change after it.
  $: currentSlideLabel = isLoading ? "" : slideLabel(slides[activeIndex]);

  $: hasMapData = eventSlides.some((event) => isCoordinate(event.coordinates));
  $: hasMultipleEvents = totalSlides > 1;
  $: hasNetworkConnections =
    egoNetwork?.connections && egoNetwork.connections.length > 0;

  // The events a reader can go deeper into. Sideways is the story's own axis —
  // one event after another — so downward is left free to mean something else:
  // the same event, further in. Only a life's landmarks offer it, roughly one
  // per chapter, so the gesture stays rare enough to mean something.
  $: deepEventIndexes = selectDeepEventIndexes(eventSlides, egoNetwork);

  // Selected as a landmark AND carrying the report that is the whole of the
  // layer. The selection is what the report writer fills against, so it names
  // the events worth a report; a life whose reports are not written yet simply
  // offers no way down. Both the markup and the measurement below ask here, so
  // the two cannot drift apart. The selection is passed in rather than read
  // from the closure, so that asking the question is what makes a caller
  // depend on it.
  function slideHasDepth(slide, deepIndexes) {
    return (
      slide?.type === "event" &&
      deepIndexes.has(slide.eventIndex) &&
      hasBackgroundReport(slide)
    );
  }

  // How far into the active slide's depth layer the reader has come, 0 to 1.
  // The story map fades out over the same interval: it belongs to the event
  // above, and it would otherwise sit lit behind a page of running text.
  let depthProgress = 0;

  // A slide keeps its scroll position while it is in the DOM, so the progress
  // has to be re-read when the reader arrives rather than assumed to be 0.
  // Only from a slide that has somewhere to go: reading it costs a synchronous
  // layout, taken in the frame a slide change has just dirtied the whole strip
  // in, and four slides in five have no depth layer to report on.
  $: if (activeIndex >= 0) {
    depthProgress = 0;
    if (slideHasDepth(slides[activeIndex], deepEventIndexes)) {
      measureActiveDepth();
    }
  }

  function readDepthProgress(section) {
    const travel = section.scrollHeight - section.clientHeight;
    if (travel <= 1) return 0;
    // Full fade by the time the fold has been scrolled away, not by the end of
    // the depth layer: a long context page would otherwise keep the map half
    // lit for its whole length.
    return clamp(
      section.scrollTop / Math.min(travel, section.clientHeight),
      0,
      1
    );
  }

  function measureActiveDepth() {
    if (typeof document === "undefined") return;
    tick().then(() => {
      const section = slidesContainer?.children?.[activeIndex];
      if (section instanceof HTMLElement) {
        depthProgress = readDepthProgress(section);
      }
    });
  }

  function handleSlideScroll(event, index) {
    if (index !== activeIndex) return;
    depthProgress = readDepthProgress(event.currentTarget);
  }

  // Moves the active slide down into its depth layer or back up to the event.
  // The fold is exactly one screen, so a screen is also the step a long
  // context page moves by when the keys drive it.
  function scrollSlideTo(target) {
    const section = slidesContainer?.children?.[activeIndex];
    if (!(section instanceof HTMLElement)) return;
    // A command like any other: the wheel run it may have interrupted is done.
    explicitNavAt = Date.now();
    if (target === "fold") {
      section.scrollTo({ top: 0, behavior: "smooth" });
      return;
    }
    if (target === "depth") {
      section.scrollTo({ top: section.clientHeight, behavior: "smooth" });
      return;
    }
    section.scrollBy({ top: target, behavior: "smooth" });
  }

  // Flattened collection of all images across the story with event metadata
  $: allImages = collectStoryImages(
    portrait,
    eventSlides,
    eventIndexToSlideIndex
  );

  // Track the last activeIndex value to detect external changes (e.g., from browser history)
  let lastPropActiveIndex = activeIndex;

  // Track the last notified index to avoid duplicate notifications
  let lastNotifiedIndex = activeIndex;

  // True while a finger (or the mouse) is dragging along the compact timeline
  let isTimelineScrubbing = false;

  // Track the last processed targetEventIndex to avoid reprocessing
  let lastProcessedEventIndex = null;

  // Convert targetEventIndex (a raw source-array index, per LandingMap and
  // meta-story event_index references) to a slide index when dataset is
  // ready. Resolved via rawEventIndexToSlideIndex, not eventIndexToSlideIndex
  // — the latter is keyed by chronological-sort position, which can differ
  // from the raw index external links actually address.
  $: if (
    targetEventIndex !== null &&
    targetEventIndex !== undefined &&
    targetEventIndex !== lastProcessedEventIndex &&
    rawEventIndexToSlideIndex &&
    rawEventIndexToSlideIndex.size > 0
  ) {
    const targetSlideIndex = rawEventIndexToSlideIndex.get(
      Number(targetEventIndex)
    );

    if (targetSlideIndex !== undefined && targetSlideIndex >= 0) {
      // Mark as processed
      lastProcessedEventIndex = targetEventIndex;

      // Clear the event param from URL and replace with slide param
      // This will cause activeIndex to update, which will trigger the normal scroll logic
      updateStoryUrl({ slide: targetSlideIndex });
    }
  }

  // When activeIndex prop changes externally (browser back/forward), scroll to it
  $: if (
    activeIndex !== lastPropActiveIndex &&
    slidesContainer &&
    totalPanels > 0
  ) {
    lastPropActiveIndex = activeIndex;
    // Only scroll if not currently in a programmatic scroll and initial scroll is done
    if (scrollState === SCROLL_STATE.IDLE && initialScrollDone) {
      requestScrollTo(activeIndex, {
        source: "prop-change",
        immediate: false,
      });
    }
  }

  // Notify parent when slide changes (only when actually different from last notification)
  // Include source information to help parent decide whether to push or replace history
  // A timeline scrub is exempt until the finger lifts: it crosses every slide
  // between where it started and where it ends, and rewriting the route for each
  // one records slides nobody stopped on while running the browser's own limit
  // on history rewrites down. Dropping the flag re-runs this block, so the slide
  // the drag settled on is still reported.
  $: if (
    activeIndex !== undefined &&
    activeIndex !== lastNotifiedIndex &&
    !isTimelineScrubbing
  ) {
    lastNotifiedIndex = activeIndex;
    onSlideChange({
      detail: activeIndex,
      source:
        scrollState === SCROLL_STATE.USER_SCROLLING
          ? "user-scroll"
          : currentNavigationSource,
    });
  }

  // Update activeEventIndex to use the slide-to-event mapping
  $: activeEventIndex = (() => {
    const mappedIndex = slideIndexToEventIndex.get(activeIndex);
    // null means chapter slide, -1 means overview, number >= 0 means event
    if (mappedIndex === null || mappedIndex === -1) {
      return -1;
    }
    return mappedIndex;
  })();

  // Determine if current slide is a chapter, conclusion, invention, or publication slide (for map fade)
  $: isChapterSlide = (() => {
    if (activeIndex < 0 || activeIndex >= slides.length) return false;
    const slide = slides[activeIndex];
    const slideType = slide?.type;

    // Fade map for chapter/conclusion slides
    if (slideType === "chapter" || slideType === "conclusion") return true;

    // Also fade map for invention and publication events
    if (
      slideType === "event" &&
      (slide?.event_class?.type === "invention" ||
        slide?.event_class?.type === "publication")
    )
      return true;

    return false;
  })();

  $: activeCoordinates =
    activeEventIndex >= 0
      ? (eventSlides[activeEventIndex]?.coordinates ?? DEFAULT_COORDINATES)
      : DEFAULT_COORDINATES;

  $: activeMigrationPath =
    activeEventIndex >= 0 && eventSlides[activeEventIndex]
      ? getMigrationPath(eventSlides[activeEventIndex])
      : null;

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

  $: datasetName = dataset?.person?.name ?? null;

  // The evaluation log's record of a story opening — its size, so that how
  // much of it a reader saw can be computed later — and of every slide the
  // reader lands on, with the mechanism that brought them there. Both are
  // no-ops outside the evaluation deployment.
  let loggedStoryName = null;
  let loggedSlideIndex = null;
  $: if (datasetName && slides.length > 0 && datasetName !== loggedStoryName) {
    loggedStoryName = datasetName;
    loggedSlideIndex = null;
    logEvent("story.open", {
      name: personName,
      slides: slides.length,
      events: eventSlides.length,
      deep: deepEventIndexes.size,
    });
  }
  $: if (
    loggedStoryName &&
    activeIndex !== loggedSlideIndex &&
    !isTimelineScrubbing
  ) {
    loggedSlideIndex = activeIndex;
    logEvent("story.navigate", {
      index: activeIndex,
      slideType: slides[activeIndex]?.type ?? null,
      event: slideIndexToEventIndex.get(activeIndex) ?? null,
      source:
        scrollState === SCROLL_STATE.USER_SCROLLING
          ? "user-scroll"
          : currentNavigationSource,
      total: slides.length,
    });
  }

  // The depth layer, for the same log: entering it on a slide, and how far
  // down the reader got before leaving that slide.
  let depthLogSlide = -1;
  let depthLogMax = 0;
  let depthLogEntered = false;
  $: trackDepthForLog(activeIndex, depthProgress);
  function trackDepthForLog(index, progress) {
    if (index !== depthLogSlide) {
      closeDepthLog();
      depthLogSlide = index;
    }
    if (progress > depthLogMax) depthLogMax = progress;
    if (!depthLogEntered && progress > 0.35) {
      depthLogEntered = true;
      logEvent("story.depth", {
        action: "enter",
        index,
        event: slideIndexToEventIndex.get(index) ?? null,
      });
    }
  }
  function closeDepthLog() {
    if (depthLogSlide >= 0 && depthLogMax > 0) {
      logEvent("story.depth", {
        action: "leave",
        index: depthLogSlide,
        event: slideIndexToEventIndex.get(depthLogSlide) ?? null,
        progress: Math.round(depthLogMax * 100) / 100,
      });
    }
    depthLogMax = 0;
    depthLogEntered = false;
  }

  $: if (datasetName !== lastDatasetName) {
    // Only reset scroll state when changing to a different person (not on initial load)
    const isPersonChange = lastDatasetName !== null && lastDatasetName !== "";

    lastDatasetName = datasetName;

    // Reset map viewport when person changes
    if (storyMapComponent) {
      storyMapComponent.resetViewport();
    }

    if (isPersonChange) {
      // Reset scroll flags only when switching between persons
      initialScrollDone = false;
      initialScrollPending = false;
    }

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

  // Track previous activeIndex to detect actual changes
  let previousActiveIndex = activeIndex;

  // Rewrite the story URL in place, changing only what the caller names.
  // Everything else — including the reader's from_meta/from_landing origin —
  // is carried through, so no call site can forget it. Always replace(), not
  // push(): view state must not create history entries.
  function updateStoryUrl(patch) {
    const basePath = $location.split("?")[0];
    replace(
      buildUrlWithParams(basePath, {
        slide: activeIndex,
        timeline: $queryParams.timeline,
        network: $queryParams.network,
        ...navigationContext($queryParams),
        ...patch,
      })
    );
  }

  // Close date note and network modal when slide actually changes
  $: if (activeIndex !== undefined && activeIndex !== previousActiveIndex) {
    visibleDateNote = null;
    visiblePersonInfo = null;
    visibleAnnotation = null;
    // Close network modal when slide changes by updating URL
    if ($queryParams.network) {
      updateStoryUrl({ network: false });
    }
    previousActiveIndex = activeIndex;
  }

  let slidesContainer;
  let initialScrollDone = false;
  let initialScrollPending = false;

  // Scroll state machine (replaces boolean isScrolling flag)
  const SCROLL_STATE = {
    IDLE: "idle",
    USER_SCROLLING: "user_scrolling",
    PROGRAMMATIC: "programmatic",
    SETTLING: "settling",
  };
  let scrollState = SCROLL_STATE.IDLE;
  let scrollStateTimeout = null;
  let currentNavigationSource = "programmatic"; // Track source of current navigation
  let scrollHandlerTimeout = null;
  let scrollendSupported = null;

  // The slide the current programmatic scroll was sent to, how often it has
  // been sent again, and the position the settle check last saw. The target
  // outlives the scroll call because the animation can be killed on the way —
  // see settleProgrammaticScroll below.
  let programmaticTargetIndex = null;
  let programmaticRetries = 0;
  let settleCheckLeft = null;

  // How long the settle check waits between looks at a container still moving.
  const SETTLE_RECHECK_MS = 150;
  // How often a scroll found at rest off its target is sent again before the
  // position is accepted as it stands.
  const PROGRAMMATIC_RETRY_LIMIT = 2;

  // Declares a programmatic scroll finished only once the container is really
  // at rest — and on the slide the scroll was sent to. Neither is guaranteed
  // by the events alone: scrollend can arrive while the animation still runs,
  // a browser without scrollend leaves only a timer that knows nothing of the
  // animation's length, and any mid-flight interruption — a layout jolt, an
  // image decoding into place — cancels the animation outright, whereupon the
  // mandatory snap carries the strip back to the slide the reader just left.
  // Sampling any of those moments wrote the abandoned position into
  // activeIndex and the URL, which is how an arrow-key slide change visibly
  // undid itself halfway through. So: still moving, look again; at rest off
  // target, send the scroll again; at rest on target, or out of retries,
  // settle and sync.
  function settleProgrammaticScroll(delayMs) {
    if (scrollStateTimeout) {
      clearTimeout(scrollStateTimeout);
    }
    settleCheckLeft = slidesContainer ? slidesContainer.scrollLeft : null;
    scrollStateTimeout = setTimeout(() => {
      scrollStateTimeout = null;
      // A reader's own gesture claims the scroll wherever it is; the check
      // stands down rather than steering against a finger or a wheel.
      if (
        scrollState !== SCROLL_STATE.PROGRAMMATIC &&
        scrollState !== SCROLL_STATE.SETTLING
      ) {
        return;
      }
      if (!slidesContainer) return;
      const { scrollLeft, clientWidth } = slidesContainer;
      if (scrollLeft !== settleCheckLeft) {
        settleProgrammaticScroll(SETTLE_RECHECK_MS);
        return;
      }
      const restIndex = clientWidth
        ? clamp(Math.round(scrollLeft / clientWidth), 0, totalPanels - 1)
        : null;
      if (
        restIndex !== null &&
        programmaticTargetIndex !== null &&
        restIndex !== programmaticTargetIndex &&
        programmaticRetries < PROGRAMMATIC_RETRY_LIMIT
      ) {
        programmaticRetries += 1;
        scrollState = SCROLL_STATE.PROGRAMMATIC;
        slidesContainer.scrollTo({
          left: programmaticTargetIndex * clientWidth,
          behavior: "smooth",
        });
        settleProgrammaticScroll(SETTLE_RECHECK_MS);
        return;
      }
      scrollState = SCROLL_STATE.IDLE;
      syncActiveIndexFromScroll();
    }, delayMs);
  }

  // Detect scrollend event support (lazy check)
  function detectScrollendSupport() {
    if (scrollendSupported !== null) return scrollendSupported;
    scrollendSupported = "onscrollend" in window;
    return scrollendSupported;
  }

  // Setup scroll event listeners including scrollend
  function setupScrollListeners() {
    if (slidesContainer && detectScrollendSupport()) {
      slidesContainer.addEventListener("scrollend", handleScrollEnd);
    }
  }

  // Handle scrollend event (fired when scroll completes)
  function handleScrollEnd() {
    if (scrollState === SCROLL_STATE.PROGRAMMATIC) {
      scrollState = SCROLL_STATE.SETTLING;
      // Allow snap to finish, then hand the verdict to the settle check —
      // this scrollend may be premature, and the rest position wrong.
      settleProgrammaticScroll(100);
    } else if (scrollState === SCROLL_STATE.USER_SCROLLING) {
      scrollState = SCROLL_STATE.IDLE;
      syncActiveIndexFromScroll();
    }
  }

  // Sync activeIndex from current scroll position
  function syncActiveIndexFromScroll() {
    if (!slidesContainer || totalPanels === 0 || !initialScrollDone) return;

    // A scroll still in flight is not a position anybody chose: sampling it
    // reports whichever panel is being passed over, not the destination. Every
    // legitimate caller drops back to IDLE first, so this only rejects timers
    // left over from a scroll that has already been superseded.
    if (
      scrollState === SCROLL_STATE.PROGRAMMATIC ||
      scrollState === SCROLL_STATE.SETTLING
    ) {
      return;
    }

    const { scrollLeft, clientWidth } = slidesContainer;
    if (!clientWidth) return;

    const clampedIndex = clamp(
      Math.round(scrollLeft / clientWidth),
      0,
      totalPanels - 1
    );
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

  async function requestScrollTo(targetIndex, options = {}) {
    const {
      immediate = false,
      source = "unknown",
      updateStateImmediately = false,
    } = options;

    if (!slidesContainer) return;

    // Validate and clamp
    const clampedIndex = Math.min(Math.max(targetIndex, 0), totalPanels - 1);

    // Cancel any pending scroll operations, including a debounced sample of
    // the position this scroll is about to leave behind.
    if (scrollStateTimeout) {
      clearTimeout(scrollStateTimeout);
      scrollStateTimeout = null;
    }
    if (scrollHandlerTimeout) {
      clearTimeout(scrollHandlerTimeout);
      scrollHandlerTimeout = null;
    }

    // Update state machine
    scrollState = SCROLL_STATE.PROGRAMMATIC;
    currentNavigationSource = source; // Track the source of this navigation
    programmaticTargetIndex = clampedIndex;
    programmaticRetries = 0;

    // Every source but "prop-change" is a reader's own command, and marks the
    // moment for the wheel handler's staleness check. "prop-change" is the
    // component reacting to state it already has — most often the no-op scroll
    // after a wheel navigation — and marking it would date the very wheel run
    // that is still steering.
    if (source !== "prop-change") {
      explicitNavAt = Date.now();
    }

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
    const scrollLeft = clampedIndex * clientWidth;

    // A container already on target does not scroll, and a scroll that never
    // starts fires no scrollend — the state machine would wait for one
    // forever, stuck in PROGRAMMATIC and deaf to every scroll the reader
    // makes next. This is the everyday case, not a corner: an arrow key
    // pressed at either end of the story lands here, and so does the
    // "prop-change" scroll that follows every user navigation. The instant
    // scrollTo cancels whatever animation might still be in flight; the state
    // settles here instead of waiting.
    if (Math.abs(slidesContainer.scrollLeft - scrollLeft) < 1) {
      slidesContainer.scrollTo({ left: scrollLeft, behavior: "instant" });
      scrollState = SCROLL_STATE.IDLE;
      return;
    }

    slidesContainer.scrollTo({
      left: scrollLeft,
      // "instant", not "auto": the container sets `scroll-behavior: smooth`, and
      // "auto" defers to it, so an immediate scroll used to animate like any
      // other. That is why a scrub trailed the finger and the initial scroll
      // swept through the story before settling on the requested slide.
      behavior: immediate ? "instant" : "smooth",
    });

    // Without scrollend the settle check is the only finish line. Its first
    // look waits out the typical animation; a container still moving then is
    // simply looked at again, so a slow animation is never sampled mid-flight.
    if (!detectScrollendSupport()) {
      settleProgrammaticScroll(immediate ? 50 : 600);
    }
  }

  // `source` names the control that asked, for the evaluation log; the
  // arrows and the keys move the same way.
  function prevSlide(source = "button") {
    if (totalPanels === 0) return;
    const targetIndex = Math.max(0, activeIndex - 1);
    requestScrollTo(targetIndex, {
      source,
      updateStateImmediately: true,
    });
  }

  function nextSlide(source = "button") {
    if (totalPanels === 0) return;
    const targetIndex = Math.min(totalPanels - 1, activeIndex + 1);
    requestScrollTo(targetIndex, {
      source,
      updateStateImmediately: true,
    });
  }

  function goToEvent(eventIndex) {
    if (!Number.isInteger(eventIndex)) return;
    const clamped = clamp(eventIndex, 0, Math.max(eventSlides.length - 1, 0));
    // Use the event-to-slide mapping to find the correct slide index
    const targetIndex = eventIndexToSlideIndex.get(clamped);
    if (targetIndex === undefined || totalPanels === 0) return;
    requestScrollTo(targetIndex, {
      source: "timeline_event",
      updateStateImmediately: true,
    });
  }

  function goToSlide(slideIndex) {
    if (!Number.isInteger(slideIndex)) return;
    const clamped = clamp(slideIndex, 0, Math.max(totalPanels - 1, 0));
    if (totalPanels === 0) return;
    requestScrollTo(clamped, {
      source: "timeline_chapter",
      updateStateImmediately: true,
    });
  }

  // Dragging along the compact timeline moves the slide under the finger, so
  // every step jumps rather than animates: a smooth scroll would still be
  // easing toward one slide while the finger has already passed two more.
  function scrubToIndex(index) {
    requestScrollTo(index, {
      source: "timeline_scrub",
      immediate: true,
      updateStateImmediately: true,
    });
  }

  function handleScrubStart() {
    isTimelineScrubbing = true;
  }

  function handleScrubEnd() {
    isTimelineScrubbing = false;
  }

  // Wrapper for Timeline component callbacks
  function scrollToIndexExternal(index, immediate = false) {
    requestScrollTo(index, {
      source: "timeline_scrubber",
      immediate,
      updateStateImmediately: !immediate, // Smooth = optimistic update
    });
  }

  function enlargeImage(imageData, slide = null) {
    // Find this image in the flattened collection
    const globalIndex = allImages.findIndex((img) => {
      if (img.url !== imageData.url) return false;
      // If slide context provided, match the event index too
      if (slide && img.eventIndex !== slide.eventIndex) return false;
      return true;
    });

    currentImageGlobalIndex = globalIndex >= 0 ? globalIndex : 0;
    enlargedImage =
      globalIndex >= 0
        ? allImages[globalIndex]
        : { ...imageData, slideIndex: activeIndex };
    logEvent("story.image", {
      action: "open",
      index: currentImageGlobalIndex,
      event: enlargedImage?.eventIndex ?? null,
    });
  }

  function closeEnlargedImage() {
    if (enlargedImage) logEvent("story.image", { action: "close" });
    enlargedImage = null;
    currentImageGlobalIndex = -1;
  }

  function handleImageNavigate(newIndex) {
    if (newIndex >= 0 && newIndex < allImages.length) {
      currentImageGlobalIndex = newIndex;
      enlargedImage = allImages[newIndex];
      logEvent("story.image", {
        action: "navigate",
        index: newIndex,
        event: enlargedImage?.eventIndex ?? null,
      });
    }
  }

  function handleJumpToEvent(slideIndex) {
    if (slideIndex >= 0 && slideIndex < slides.length) {
      logEvent("story.image", { action: "jump", index: slideIndex });
      requestScrollTo(slideIndex, {
        source: "image-viewer-jump",
        updateStateImmediately: true,
      });
    }
  }

  function handleScroll() {
    // Ignore during programmatic scrolls
    if (
      scrollState === SCROLL_STATE.PROGRAMMATIC ||
      scrollState === SCROLL_STATE.SETTLING
    ) {
      return;
    }

    // A reload rebuilding the panels moves the container on its own — until
    // the initial scroll has anchored it on the requested slide, its position
    // says nothing about where the reader is. Reading it here would promote
    // the reflow to a user scroll and write the passing slide into the URL.
    if (!initialScrollDone || totalPanels === 0) {
      return;
    }

    // Promote to user scrolling if idle
    if (scrollState === SCROLL_STATE.IDLE) {
      scrollState = SCROLL_STATE.USER_SCROLLING;
      currentNavigationSource = "user-scroll"; // User is manually scrolling
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

  let lastVerticalWheelAt = 0;

  // A quiet spell longer than this ends a wheel run — shared by the axis lock
  // and the staleness check below, so the two cannot disagree about where one
  // run ends and the next begins.
  const WHEEL_GAP_MS = 150;

  // One turn of a wheel and one push of a trackpad both arrive as a run of
  // events, and the run is what the reader meant — a single event out of it
  // that happens to point sideways is not an instruction to leave the slide.
  // A wheel has no equivalent of a finger lifting, so a pause ends the run.
  const wheelLock = createAxisLock({ threshold: 12, gapMs: WHEEL_GAP_MS });

  // When the run now arriving began, and when the last explicit navigation —
  // a key, a button, the timeline — started. Comparing the two is what tells
  // a live gesture from the momentum tail of one that already ended.
  let wheelRunStartedAt = 0;
  let lastWheelEventAt = null;
  let explicitNavAt = 0;

  function handleWheel(event) {
    if (event.ctrlKey) return;
    if (!slidesContainer || totalPanels === 0) return;

    const now = Date.now();
    if (lastWheelEventAt === null || now - lastWheelEventAt > WHEEL_GAP_MS) {
      wheelRunStartedAt = now;
    }
    lastWheelEventAt = now;
    // A trackpad keeps sending momentum events after the fingers have lifted,
    // so a run regularly straddles a key press: the reader scrolls, presses an
    // arrow key, and the tail of the dead gesture arrives while the slide
    // change is still animating. Each tail event retargets the scroll to
    // wherever it happens to be, the snap then carries the reader back to the
    // slide they just left, and the press looks like it undid itself. The tail
    // is recognizable by its age — the run began before the navigation did —
    // and a stale run has nothing left to say. A fresh gesture starts a new
    // run and steers as before.
    if (wheelRunStartedAt <= explicitNavAt) {
      event.preventDefault();
      return;
    }

    const wheelAxis = wheelLock.move(event.deltaX, event.deltaY, now);
    // Too little of the gesture has arrived to say which way it leans. The
    // story waits rather than guessing: the slide under the pointer scrolls on
    // its own in the meantime, which is the answer a short gesture down wanted
    // anyway.
    if (wheelAxis === null) return;

    const dominantDelta = wheelAxis === "x" ? event.deltaX : event.deltaY;
    if (!dominantDelta) return;

    // Slides are overflow-y auto; when the hovered slide's content overflows
    // and can still scroll in the wheel direction, let it scroll natively
    // instead of converting the delta into horizontal slide navigation.
    if (wheelAxis === "y") {
      const slide = event.target?.closest?.(".slide");
      if (slide && slide.scrollHeight > slide.clientHeight + 1) {
        const canScroll =
          event.deltaY > 0
            ? slide.scrollTop + slide.clientHeight < slide.scrollHeight - 1
            : slide.scrollTop > 0;
        if (canScroll) {
          lastVerticalWheelAt = Date.now();
          return;
        }
        // One flick of the wheel arrives as a run of events. Without this the
        // tail of the flick that opened the depth layer would carry straight
        // on to the next slide, and the reader would be shown the context and
        // taken off it in a single gesture. Leaving the event needs a gesture
        // of its own.
        if (
          slide.classList.contains("has-depth") &&
          Date.now() - lastVerticalWheelAt < 400
        ) {
          event.preventDefault();
          return;
        }
      }
    }

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
    if (
      event.target.tagName === "INPUT" ||
      event.target.tagName === "TEXTAREA" ||
      event.target.isContentEditable
    ) {
      return;
    }

    if (totalPanels === 0) return;

    // Down and up drive the second axis where a slide has one: the reader goes
    // into the event before the keys carry them on to the next. Left and right
    // stay the story's axis and always move a slide. A slide that merely
    // overflows is not a slide with a second axis, and keeps every key it had.
    const section = slidesContainer?.children?.[activeIndex];
    const hasDepth =
      section instanceof HTMLElement && section.classList.contains("has-depth");

    if (["ArrowDown", "PageDown"].includes(event.key) && hasDepth) {
      if (section.scrollTop < section.scrollHeight - section.clientHeight - 1) {
        event.preventDefault();
        // The first press lands on the head of the depth layer; a context page
        // longer than a screen takes another press per screen after that.
        scrollSlideTo(section.scrollTop < 1 ? "depth" : section.clientHeight);
        return;
      }
    } else if (["ArrowUp", "PageUp"].includes(event.key) && hasDepth) {
      if (section.scrollTop > 1) {
        event.preventDefault();
        scrollSlideTo(
          section.scrollTop <= section.clientHeight + 1
            ? "fold"
            : -section.clientHeight
        );
        return;
      }
    }

    if (["ArrowLeft", "ArrowUp", "PageUp"].includes(event.key)) {
      event.preventDefault();
      prevSlide("keyboard");
    } else if (["ArrowRight", "ArrowDown", "PageDown"].includes(event.key)) {
      event.preventDefault();
      nextSlide("keyboard");
    } else if (event.key === "Home") {
      event.preventDefault();
      requestScrollTo(0, {
        source: "keyboard",
        updateStateImmediately: true,
      });
    } else if (event.key === "End") {
      event.preventDefault();
      requestScrollTo(totalPanels - 1, {
        source: "keyboard",
        updateStateImmediately: true,
      });
    }
  }

  // px of travel before a drag is called horizontal or vertical. Short enough
  // that a swipe still answers at once, long enough that the wobble at the
  // start of one does not answer for it.
  const TOUCH_AXIS_THRESHOLD = 12;
  // A flick has to cover ground as well as be quick. Without this a fast,
  // barely-moving finger counted as a swipe.
  const MIN_FLICK_DISTANCE = 24;

  // A finger lifting ends its gesture outright, so this lock needs no pause to
  // tell one drag from the next.
  const touchLock = createAxisLock({ threshold: TOUCH_AXIS_THRESHOLD });

  let touchStartX = null;
  let touchStartScrollLeft = null;
  let touchStartTime = null;
  let lastTouchX = null;
  let lastTouchY = null;
  let lastTouchTime = null;

  function resetTouchState() {
    touchStartX = null;
    touchStartScrollLeft = null;
    touchStartTime = null;
    lastTouchX = null;
    lastTouchY = null;
    lastTouchTime = null;
    touchLock.reset();
  }

  function handleTouchStart(event) {
    if (!slidesContainer) return;
    const touch = event.touches[0];
    touchStartX = touch.clientX;
    touchStartScrollLeft = slidesContainer.scrollLeft;
    touchStartTime = Date.now();
    lastTouchX = touch.clientX;
    lastTouchY = touch.clientY;
    lastTouchTime = touchStartTime;
    touchLock.reset();
  }

  function handleTouchMove(event) {
    if (touchStartX === null || !slidesContainer) return;
    const touch = event.touches[0];
    const deltaX = touchStartX - touch.clientX;

    const wasDecided = touchLock.axis !== null;
    const touchAxis = touchLock.move(
      touch.clientX - lastTouchX,
      touch.clientY - lastTouchY
    );

    // Track last position for velocity calculation
    lastTouchX = touch.clientX;
    lastTouchY = touch.clientY;
    lastTouchTime = Date.now();

    if (touchAxis === "x" && !wasDecided) {
      // Set state WITHOUT toggling scroll-snap
      scrollState = SCROLL_STATE.USER_SCROLLING;
    }

    // A vertical drag belongs to the slide's own scroll — the depth layer of
    // the event the reader is on. The story stays where it is under it. A drag
    // too short to lean either way moves nothing at all yet.
    if (touchAxis !== "x") return;

    event.preventDefault();
    // Direct 1:1 mapping - no damping
    slidesContainer.scrollLeft = touchStartScrollLeft + deltaX;
  }

  function handleTouchEnd() {
    if (!slidesContainer || touchStartX === null || touchLock.axis !== "x") {
      // A vertical drag never moved the story, so there is nothing to settle
      // and no slide to change: leaving the event takes a sideways gesture.
      // The scroll state is left alone rather than forced idle — a gesture
      // that never claimed the container has no business releasing it either.
      resetTouchState();
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

    if (
      Math.abs(velocity) > velocityThreshold &&
      Math.abs(deltaX) > MIN_FLICK_DISTANCE
    ) {
      // Fast swipe - use velocity
      direction = velocity > 0 ? 1 : -1; // positive deltaX = swipe left = next slide
    } else if (Math.abs(deltaX) > swipeThreshold) {
      // Slow but long swipe - use distance
      direction = deltaX > 0 ? 1 : -1;
    }

    resetTouchState();

    if (direction !== 0) {
      const targetIndex = clamp(activeIndex + direction, 0, totalPanels - 1);
      requestScrollTo(targetIndex, {
        source: "touch",
        updateStateImmediately: true,
      });
    } else {
      // Snap back to current slide
      requestScrollTo(activeIndex, {
        source: "touch",
        updateStateImmediately: false,
      });
    }
  }

  function toggleDateNote(eventIndex) {
    visibleDateNote = visibleDateNote === eventIndex ? null : eventIndex;
    logEvent("story.date_note", {
      event: eventIndex,
      open: visibleDateNote === eventIndex,
    });
  }

  function toggleAnnotation(eventIndex, termKey) {
    const compositeKey = `${eventIndex}-${termKey}`;
    visibleAnnotation =
      visibleAnnotation === compositeKey ? null : compositeKey;
    logEvent("story.annotation", {
      event: eventIndex,
      term: termKey,
      open: visibleAnnotation === compositeKey,
    });
  }

  function handleClickOutside(event) {
    // Check if click is outside the date-wrapper, person-info-wrapper, or annotated-term
    const dateWrapper = event.target.closest(".date-wrapper");
    const personWrapper = event.target.closest(".person-info-wrapper");
    const annotatedTerm = event.target.closest(".annotated-term");
    const annotationPopup = event.target.closest(".annotation-popup");
    const modal = event.target.closest(".network-modal");
    if (!dateWrapper && visibleDateNote !== null) {
      visibleDateNote = null;
    }
    if (!personWrapper && visiblePersonInfo !== null) {
      visiblePersonInfo = null;
    }
    if (!annotatedTerm && !annotationPopup && visibleAnnotation !== null) {
      visibleAnnotation = null;
    }
    if (!modal && showNetworkModal) {
      const modalOverlay = event.target.closest(".modal-overlay");
      if (modalOverlay && event.target === modalOverlay) {
        closeNetworkModal(); // Use the function to update URL properly
      }
    }
  }

  function togglePersonInfo(personKey) {
    visiblePersonInfo = visiblePersonInfo === personKey ? null : personKey;
    logEvent("story.person_info", {
      key: personKey,
      open: visiblePersonInfo === personKey,
      where: "slide",
    });
  }

  function handleCloseStory() {
    logEvent("story.close", { via: "button" });
    onClose();
  }

  function openNetworkModal() {
    setNetworkModal(true);
  }

  function closeNetworkModal() {
    setNetworkModal(false);
  }

  function setNetworkModal(show) {
    updateStoryUrl({ network: show });
  }

  function openAIModal() {
    showAIModal = true;
    logEvent("story.ai_modal", { open: true });
  }

  function closeAIModal() {
    showAIModal = false;
  }

  function handleTimelineExpandChange(event) {
    updateStoryUrl({ timeline: event.detail.expanded });
  }

  // Handle initial scroll when component loads with a specific slide index
  $: {
    if (
      !initialScrollDone &&
      slidesContainer &&
      totalPanels > activeIndex &&
      activeIndex > 0 &&
      !initialScrollPending
    ) {
      initialScrollPending = true;
      tick()
        .then(() => {
          // Wait for all slide DOM elements to be rendered
          // This is crucial for correct scroll positioning, especially on first load
          return new Promise((resolve) => {
            const checkSlides = () => {
              const renderedSlides =
                slidesContainer.querySelectorAll("section.slide").length;
              if (renderedSlides >= totalPanels) {
                // All slides are rendered, wait one more frame for layout
                requestAnimationFrame(() => resolve());
              } else {
                // Not ready yet, check again soon
                setTimeout(checkSlides, 10);
              }
            };
            checkSlides();
          });
        })
        .then(() => {
          requestScrollTo(activeIndex, {
            source: "initial",
            immediate: true,
          });
          initialScrollDone = true;
          initialScrollPending = false;
        });
    } else if (
      !initialScrollDone &&
      slidesContainer &&
      totalPanels > 0 &&
      activeIndex === 0 &&
      // Don't mark as done if we're waiting to process an event parameter
      // or if we just processed one (lastProcessedEventIndex will be set)
      !(
        targetEventIndex !== null &&
        targetEventIndex !== lastProcessedEventIndex
      ) &&
      lastProcessedEventIndex === null
    ) {
      // No initial scroll needed (starting at index 0)
      initialScrollDone = true;
    }
  }

  // Per slide, whether its own content already needs more than a screen. Only
  // a deep slide reads it, and only to give its fold the extra room.
  let foldOverrun = [];

  /* A slide keeps room free at its foot — for the story map, and for the
     timeline controls floating over it — in `.slide-reserve`, which gives that
     room back when the content needs it. It may give it back only while the
     content still ends clear of the controls. Past that the slide has to scroll
     whatever the reserve does, and then the reserve is what the reader scrolls
     the last line into: give it up and the text stops over the map and behind
     the previous and next buttons, with no scroll left to lift it.

     So the rule is: a slide that is going to scroll anyway keeps its reserve
     whole. Whether it is going to scroll is not a question CSS can ask, so each
     slide measures its own content and hands the answer back as
     `--slide-reserve-shrink`. Nothing that property changes feeds back into the
     measurement — the slide is a fixed height, the content does not shrink, and
     the room comes from the reserve's floor rather than its used height — so
     this settles in one pass. */
  function watchContentFit(section, index) {
    const content = section.querySelector(".content");
    const reserve = section.querySelector(".slide-reserve");
    if (!content || !reserve || typeof ResizeObserver === "undefined") return;

    const measure = () => {
      const style = getComputedStyle(section);
      const room =
        section.clientHeight -
        parseFloat(style.paddingTop) -
        parseFloat(style.paddingBottom) -
        parseFloat(getComputedStyle(reserve).minHeight);
      const overruns = content.getBoundingClientRect().height > room;
      section.style.setProperty("--slide-reserve-shrink", overruns ? "0" : "1");
      // A deep slide's fold is one screen tall by declaration, which is only
      // safe while the event fits in one. This is the same measurement saying
      // when it does not.
      if (foldOverrun[index] !== overruns) {
        foldOverrun[index] = overruns;
        foldOverrun = foldOverrun;
      }
    };

    const observer = new ResizeObserver(measure);
    observer.observe(section);
    observer.observe(content);

    return {
      destroy: () => observer.disconnect(),
    };
  }

  onMount(() => {
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
        slidesContainer.removeEventListener("scrollend", handleScrollEnd);
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
    closeDepthLog();
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
</script>

<!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
<div
  bind:this={storyViewElement}
  class="story-view"
  class:reading-depth={depthProgress > 0.35}
  style="{storyStyleVars(styleConfig)}; --header-height: {mastheadHeight}px"
  on:wheel={handleWheel}
  on:click={handleClickOutside}
  on:keydown={handleKeydown}
  tabindex="-1"
  role="region"
  aria-label={$_("story.story_viewer")}
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
      <div class="header-actions">
        {#if hasNetworkConnections}
          <button
            type="button"
            class="header-network-btn"
            on:click={openNetworkModal}
            aria-label={$_("story.show_network")}
          >
            <svg
              class="icon"
              viewBox="0 0 24 24"
              role="presentation"
              aria-hidden="true"
            >
              <path d={mdiAccountMultipleOutline} />
            </svg>
          </button>
        {/if}
        <CloseButton
          variant="theme"
          size="responsive"
          ariaLabel={closeStoryLabel}
          on:click={handleCloseStory}
          class="compact"
        />
      </div>
    </div>
  </header>

  <div class="ai-label-wrapper">
    <AIGeneratedButton variant="small" onClick={openAIModal} />
  </div>

  <!-- Announces which slide the reader is on, and nothing else. -->
  <p class="slide-status" aria-live="polite">{currentSlideLabel}</p>

  <div class="slides-wrapper" class:map-enabled={hasMapData}>
    <main
      class="slides"
      class:initial-loading={!initialScrollDone && activeIndex > 0}
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
          <StoryLoadingSlide {loadingStage} />
          <div class="slide-reserve" aria-hidden="true"></div>
        </section>
      {:else if totalPanels > 0}
        {#each slides as slide, index (slide.type === "chapter" ? `chapter-${index}` : slide.type === "conclusion" ? "conclusion" : slide.eventIndex)}
          <!-- Every slide is in the DOM at once inside one scroll-snap
               container. Without this, the whole story is live for the keyboard
               and for assistive technology: Tab walks out of the visible slide
               into controls belonging to later ones, the browser scrolls each
               into view, and the scroll handler carries the reader forward
               through slides they never asked to see. `inert` takes the
               inactive ones out of the tab order and the accessibility tree at
               once, leaving the arrow keys as the way to move between slides. -->
          {@const isDeep = slideHasDepth(slide, deepEventIndexes)}
          <section
            class="slide slide-loaded"
            class:overview={slide.type === "overview"}
            class:chapter={slide.type === "chapter"}
            class:conclusion={slide.type === "conclusion"}
            class:has-depth={isDeep}
            class:fold-overrun={isDeep && foldOverrun[index]}
            inert={index !== activeIndex}
            aria-hidden={index !== activeIndex}
            aria-label={slideLabel(slide)}
            on:scroll={(event) => handleSlideScroll(event, index)}
            use:watchContentFit={index}
          >
            {#if isDeep}
              <!-- A deep slide is two screens, and the first one has to be
                   exactly a screen: the fold holds the event and nothing else,
                   so the depth layer below it starts out of sight and the
                   reader meets it only by going there. -->
              <div class="slide-fold">
                <EventSlide
                  {slide}
                  {birthDate}
                  {egoNetwork}
                  {portrait}
                  {styleConfig}
                  {formatters}
                  {visibleDateNote}
                  {visiblePersonInfo}
                  {visibleAnnotation}
                  isActive={index === activeIndex}
                  onEnlargeImage={enlargeImage}
                  onToggleDateNote={toggleDateNote}
                  onTogglePersonInfo={togglePersonInfo}
                  onToggleAnnotation={toggleAnnotation}
                  onOpenNetwork={openNetworkModal}
                />
                <!-- Placed in the flow, right after the event, and lifted into
                     the corner by CSS on every slide whose fold is a screen
                     tall. On a slide whose text overruns a screen there is no
                     corner to lift it into, and it stays here, at the end of
                     the reading. -->
                <button
                  type="button"
                  class="depth-affordance"
                  class:yielded={popupOpen}
                  style="opacity: {popupOpen
                    ? 0
                    : 1 - Math.min(depthProgress * 2.5, 1)}"
                  tabindex={index === activeIndex &&
                  depthProgress < 0.5 &&
                  !popupOpen
                    ? 0
                    : -1}
                  aria-label={$_("story.depth.open")}
                  on:click={() => scrollSlideTo("depth")}
                >
                  <span class="depth-affordance-label"
                    >{$_("story.depth.more")}</span
                  >
                  <span class="depth-affordance-chevrons" aria-hidden="true">
                    <span class="depth-chevron"></span>
                    <span class="depth-chevron"></span>
                  </span>
                </button>
                <div class="slide-reserve" aria-hidden="true"></div>
              </div>
              <EventDepth
                {slide}
                depth={getEventDepth(slide, egoNetwork)}
                {egoNetwork}
                subjectName={personName}
                {styleConfig}
                {visiblePersonInfo}
                onEnlargeImage={enlargeImage}
                onReturnToEvent={() => scrollSlideTo("fold")}
                onTogglePersonInfo={togglePersonInfo}
                onOpenNetwork={openNetworkModal}
              />
            {:else if slide.type === "overview"}
              <OverviewSlide
                {person}
                {portrait}
                {personName}
                {yearsLabel}
                {roles}
                {styleConfig}
                {personSummary}
                onEnlargeImage={enlargeImage}
              />
            {:else if slide.type === "chapter"}
              <ChapterSlide
                chapter={slide.chapter}
                personStyle={styleConfig}
                {egoNetwork}
                {formatters}
                activeSlideIndex={activeIndex}
                slideIndex={index}
                onOpenNetwork={openNetworkModal}
              />
            {:else if slide.type === "conclusion"}
              <ConclusionSlide
                conclusion={slide.conclusion}
                relatedPersons={slide.relatedPersons}
                allSources={slide.allSources}
                {personStylesRegistry}
              />
            {:else if slide.type !== "spacer"}
              <EventSlide
                {slide}
                {birthDate}
                {egoNetwork}
                {portrait}
                {styleConfig}
                {formatters}
                {visibleDateNote}
                {visiblePersonInfo}
                {visibleAnnotation}
                isActive={index === activeIndex}
                onEnlargeImage={enlargeImage}
                onToggleDateNote={toggleDateNote}
                onTogglePersonInfo={togglePersonInfo}
                onToggleAnnotation={toggleAnnotation}
                onOpenNetwork={openNetworkModal}
              />
            {/if}
            <!-- The room a slide keeps free below its content — for the story
                 map, and for the breathing space the chapter, conclusion, and
                 overview slides ask for — is held by this element rather than
                 by the slide's own bottom padding. Padding is part of the
                 scrollable area, so a fixed reserve made slides scroll whose
                 content was already fully on screen: the scrollbar promised
                 something below and delivered empty margin. As a flex item the
                 reserve yields its height when there is not enough room for it,
                 which leaves the slide scrolling only when the content itself
                 overruns the screen. A deep slide keeps its reserve inside the
                 fold, where the event it belongs to is. -->
            {#if !isDeep}
              <div class="slide-reserve" aria-hidden="true"></div>
            {/if}
          </section>
        {/each}
      {/if}
    </main>
    {#if hasMapData}
      {#await import("./StoryMap.svelte") then { default: StoryMap }}
        <StoryMap
          bind:this={storyMapComponent}
          {activeCoordinates}
          allActiveCoordinates={activeEventIndex >= 0
            ? (eventSlides[activeEventIndex]?.allCoordinates ?? [])
            : []}
          {markerTrail}
          {hasMapData}
          {activeIndex}
          {isChapterSlide}
          {styleConfig}
          {depthProgress}
          migrationPath={activeMigrationPath}
        />
      {/await}
    {/if}
  </div>
  <Timeline
    {activeIndex}
    {totalSlides}
    {totalPanels}
    {activeEventIndex}
    {hasMultipleEvents}
    {indicatorProgress}
    {indicatorIcons}
    {eventSlides}
    {slides}
    {chapters}
    initialExpanded={initialTimelineExpanded}
    onPrevSlide={prevSlide}
    onNextSlide={nextSlide}
    onGoToEvent={goToEvent}
    onGoToSlide={goToSlide}
    onScrollToIndex={scrollToIndexExternal}
    onScrubToIndex={scrubToIndex}
    on:expandchange={handleTimelineExpandChange}
    on:scrubstart={handleScrubStart}
    on:scrubend={handleScrubEnd}
  />
</div>

<ImageViewer
  image={enlargedImage}
  {styleConfig}
  {allImages}
  currentIndex={currentImageGlobalIndex}
  activeSlideIndex={activeIndex}
  onClose={closeEnlargedImage}
  onNavigate={handleImageNavigate}
  onJumpToEvent={handleJumpToEvent}
/>

{#if showNetworkModal}
  <NetworkModal
    {egoNetwork}
    {personName}
    {portrait}
    {styleConfig}
    onClose={closeNetworkModal}
  />
{/if}

<AIDisclaimerModal show={showAIModal} onClose={closeAIModal} />

<style>
  /* Below the fold the slide stops being a slide and becomes a page of
     reading, so the story's own chrome gets out of the way with the map: the
     timeline, its arrows and the chapter pill are all fixed over the foot of
     the screen, which on the fold is the map and here is the middle of a
     paragraph. The way back is the button at the end of the report, and
     scrolling up brings the chrome back with the event. */
  .story-view :global(.indicator) {
    transition:
      opacity 0.35s ease,
      visibility 0s;
  }

  /* Hidden, not merely transparent: the timeline's own container passes clicks
     through but its buttons take them back, so a faded-out arrow would still
     answer a tap in the middle of the report. */
  .story-view.reading-depth :global(.indicator) {
    opacity: 0;
    visibility: hidden;
    transition:
      opacity 0.35s ease,
      visibility 0s linear 0.35s;
  }

  .story-view {
    display: flex;
    flex-direction: column;
    position: fixed;
    inset: 0;
    /* Where the slide is allowed to raise its voice. The side ramp stays quiet
       across the content column and lifts toward the viewport edge; because the
       column is `min(54rem, 100%)` wide, the quiet stretch is written as
       `50% ∓ 27rem` and collapses to nothing on a viewport narrower than the
       column—exactly where a lift would land under the text. The drop ramp is
       the same idea below the content, plus a soft lift in the top band the
       masthead blurs over. Slides scroll horizontally, so both ramps are sized
       to the slide box, which is one viewport wide and tall. */
    --pattern-side-lift: linear-gradient(
      90deg,
      var(--pattern-edge-lift) 0%,
      var(--pattern-quiet) max(0px, 50% - 27rem),
      var(--pattern-quiet) min(100%, 50% + 27rem),
      var(--pattern-edge-lift) 100%
    );
    --pattern-drop-lift: linear-gradient(
      180deg,
      var(--pattern-edge-lift-soft) 0%,
      var(--pattern-quiet) 13%,
      var(--pattern-quiet) 62%,
      var(--pattern-edge-lift) 96%
    );
    /* The same two shapes again, this time as the mask that confines the second
       coat to the margins. Multiple mask layers composite with `add`, so the
       two ramps union and a corner counts as margin on either count. */
    --pattern-side-mask: linear-gradient(
      90deg,
      rgba(0, 0, 0, 1) 0%,
      rgba(0, 0, 0, 0) max(0px, 50% - 27rem),
      rgba(0, 0, 0, 0) min(100%, 50% + 27rem),
      rgba(0, 0, 0, 1) 100%
    );
    --pattern-drop-mask: linear-gradient(
      180deg,
      rgba(0, 0, 0, 0.45) 0%,
      rgba(0, 0, 0, 0) 13%,
      rgba(0, 0, 0, 0) 62%,
      rgba(0, 0, 0, 1) 96%
    );

    /* Both coats carry this as their topmost background layer. Off by default:
       fully transparent, so it changes nothing. Story maps switch it on below.
       See `--pattern-map-guard` under `.slides-wrapper.map-enabled`. */
    --pattern-map-guard: linear-gradient(
      rgb(50% 50% 50% / 0%),
      rgb(50% 50% 50% / 0%)
    );
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

  .ai-label-wrapper {
    position: absolute;
    top: var(--header-height, 2.5rem);
    left: 0;
    z-index: 2; /* Above slides (z-index: 1), below masthead (z-index: 3) */
    display: contents;
  }

  .ai-label-wrapper :global(button) {
    position: absolute;
    top: var(--header-height, 2.5rem);
    left: -0.25rem;
    z-index: 2; /* Above slides (z-index: 1), below masthead (z-index: 3) */
  }

  /* Adjust AI label position for landscape mobile */
  @media (max-height: 450px) {
    .ai-label-wrapper :global(button) {
      top: auto;
      bottom: 0.5rem;
      left: 0.5rem;
    }
  }

  /* The loading slide fades in; the skeleton it holds is StoryLoadingSlide. */
  .loading-slide {
    animation: fadeIn 0.3s ease;
  }

  /* Hide slides container during initial scroll to prevent flash */
  .slides.initial-loading {
    opacity: 0;
  }

  @keyframes fadeIn {
    from {
      opacity: 0;
    }
    to {
      opacity: 1;
    }
  }

  .story-view::before {
    content: "";
    position: absolute;
    inset: 0;
    pointer-events: none;
    background-color: var(--story-primary, #38bdf8);
    background-image: var(--story-pattern-image, none);
    background-size: var(--story-pattern-size, 400px);
    background-repeat: repeat;
    background-position: calc(var(--story-pattern-size, 400px) / -2)
      calc(var(--story-pattern-size, 400px) / -2);
    background-blend-mode: multiply;
    opacity: 0.7;
    mix-blend-mode: overlay;
    z-index: 0;
  }

  .story-view > * {
    position: relative;
    z-index: 1;
  }

  .masthead {
    padding: 0.5rem 2vw;
    display: flex;
    flex-direction: row;
    align-items: center;
    background:
      linear-gradient(
        180deg,
        rgba(255, 255, 255, 0.03) 0%,
        rgba(0, 0, 0, 0.28) 100%
      ),
      rgba(var(--story-bg-rgb, 15, 23, 42), 0.58);
    backdrop-filter: blur(12px);
    border-bottom: 1px solid rgba(148, 163, 184, 0.16);
    position: sticky;
    top: 0;
    z-index: 3;
  }

  .compact-info {
    display: flex;
    width: 100%;
    justify-content: space-between;
    align-items: center;
    gap: clamp(0.5rem, 0.9vh, 0.75rem);
    font-size: clamp(0.85rem, 1.1vh, 0.95rem);
    font-weight: 600;
    color: #e2e8f0;
    white-space: nowrap;
    max-width: 100%;
    /*
     * Clip only sideways. A plain `overflow: hidden` also clips vertically, and
     * the tallest header button sits flush against that edge, which shaves its
     * rounded border at the top and bottom. `clip` on one axis leaves the other
     * axis genuinely `visible` instead of promoting it to `auto`.
     */
    overflow-x: clip;
    overflow-y: visible;
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

  .header-actions {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-left: auto;
    flex-shrink: 0;
  }

  .header-network-btn {
    appearance: none;
    border: 1px solid rgba(148, 163, 184, 0.3);
    background: rgba(255, 255, 255, 0.05);
    color: var(--story-primary, #e2e8f0);
    padding: 0;
    border-radius: 50%;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 2rem;
    height: 2rem;
    transition:
      background-color 0.2s ease,
      border-color 0.2s ease,
      transform 0.15s ease;
  }

  .header-network-btn .icon {
    width: 1.1rem;
    height: 1.1rem;
    fill: currentColor;
  }

  .header-network-btn:hover,
  .header-network-btn:focus {
    background: rgba(255, 255, 255, 0.12);
    border-color: var(--story-primary, rgba(148, 163, 184, 0.6));
    transform: scale(1.05);
    outline: none;
  }

  .header-network-btn:active {
    transform: scale(0.95);
  }

  /* Compact masthead for landscape mobile (short viewports)
     - Applies to rotated phones with limited vertical space
     - Makes header more compact and positioned on right side only */
  @media (max-height: 450px) {
    .masthead {
      position: absolute;
      top: 0;
      right: 0;
      left: auto;
      width: auto;
      max-width: 40%;
      padding: 0.15rem 0.35rem;
      border-radius: 0 0 0 0.5rem;
      border: none;
      border-left: 1px solid rgba(148, 163, 184, 0.15);
      border-bottom: 1px solid rgba(148, 163, 184, 0.15);
      background: rgba(var(--story-bg-rgb, 15, 23, 42), 0.5);
      backdrop-filter: blur(8px);
      z-index: 10;
    }

    .compact-info {
      font-size: 0.65rem;
      gap: 0.35rem;
      justify-content: flex-end;
    }

    .compact-info .name {
      max-width: 8rem;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .compact-info .lifespan {
      display: none;
    }

    .compact-info .separator {
      display: none;
    }

    .header-actions {
      gap: 0.25rem;
    }

    .header-network-btn {
      width: 1.5rem;
      height: 1.5rem;
    }

    .header-network-btn .icon {
      width: 0.85rem;
      height: 0.85rem;
    }

    .slide {
      --slide-bottom-base: 2.5rem;
      padding: 0.15rem 1rem var(--slide-bottom-base);
    }

    .loading-slide {
      gap: 0.25rem;
    }

    .slides-wrapper.map-enabled
      .slide:not(.overview):not(.chapter):not(.conclusion) {
      --slide-bottom-total: 12rem;
    }

    .slide.overview,
    .slide.chapter,
    .slide.conclusion {
      padding-top: 0.5rem;
      --slide-bottom-total: 6rem;
    }
  }

  /* Carries no visual weight: the slide it names is already on screen. Kept in
     the layout (not `display: none`) so assistive technology reads it. */
  .slide-status {
    position: absolute;
    width: 1px;
    height: 1px;
    margin: -1px;
    padding: 0;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
    border: 0;
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
    /* The story's axis is driven from `handleTouchMove`, which only takes a
       drag it has judged sideways. Left to itself the browser would pan this
       container as well, on whatever sideways component a drag down happens to
       carry, and a slide half a screen out snaps to its neighbor when the
       finger lifts. Vertical panning stays native: that is the slide's own
       scroll, into the depth layer. */
    touch-action: pan-y pinch-zoom;
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
    /* `--slide-bottom-base` is the padding every slide keeps no matter what.
       Anything a slide wants beyond it is a `--slide-bottom-total` that
       `.slide-reserve` makes up, and gives back when the content needs the
       room — but never past `--slide-bottom-clear`, which is how far up the
       previous and next buttons and the timeline bar reach. Text that ends
       under those is text nobody can read. The controls shrink on a short
       screen and so does this, which keeps it from eating a landscape slide. */
    --slide-bottom-base: 3.25rem;
    --slide-bottom-clear: min(10rem, 35vh);
    --slide-bottom-total: var(--slide-bottom-base);
    padding: 0rem 1.5rem var(--slide-bottom-base);
    display: flex;
    flex-direction: column;
    justify-content: flex-start;
    align-items: stretch;
    position: relative;
    /* The top-to-bottom shading used to live on `.slide::before`, blended over
       exactly this color and nothing else. Folding it into the slide's own
       background is equivalent and frees the pseudo-element for the margin
       pattern. */
    background-color: rgb(var(--story-bg-rgb, 15, 23, 42));
    background-image: linear-gradient(
      180deg,
      rgba(255, 255, 255, 0.03) 0%,
      rgba(0, 0, 0, 0.22) 100%
    );
    background-blend-mode: soft-light;
    border-right: 1px solid rgba(148, 163, 184, 0.12);
    overflow-y: auto;
    /* A slide scrolls down and no further. Scrolling into the depth layer is
       the one gesture the browser still drives itself, and a trackpad never
       sends that gesture straight: the sideways part of it used to chain out
       of the slide into the story behind it, which nudged the strip toward the
       next slide until it snapped there. Containing the scroll keeps a gesture
       aimed at the event inside the event. */
    overscroll-behavior: contain;
    /* A slide is expensive to paint — two full-screen pattern layers of its
       own, blended, over a background of its own — and the whole story is in
       the DOM at once, which is what makes a transition stutter. It is not
       expensive enough to be worth `content-visibility: auto` here, which was
       tried and reverted: on a slide carrying an event panel Chromium painted
       the top of the slide and left the rest transparent, with the story map
       showing through where the description belonged. Layout was correct and
       identical either way, so nothing in the application could see it — only
       a screenshot could. */
  }

  /* A deep slide always scrolls, so a scrollbar here would say nothing the
     affordance does not say better — and the horizontal one is hidden the same
     way, which is what makes the two axes read as one gesture apiece. */
  .slide.has-depth {
    scrollbar-width: none;
    -ms-overflow-style: none;
    /* Room under the event for the invitation down. A story with a map already
       keeps more than this (the rule below sets 16rem and outranks it); a story
       without one would otherwise let the description run to the foot of the
       slide, straight through the affordance. */
    --slide-bottom-total: 9rem;
  }

  .slide.has-depth::-webkit-scrollbar {
    display: none;
  }

  /* The fold is the slide as it was: one screen, the event alone on it. Its
     height is the slide's own — the content box plus the bottom padding the
     slide keeps for the controls — so the depth layer below begins exactly at
     the bottom edge of the screen and not a line above it. */
  .slide-fold {
    display: flex;
    flex-direction: column;
    flex: 0 0 auto;
    /* A definite height, not a minimum: it is what lets the reserve below the
       event shrink here exactly as it does on a slide with nothing under it,
       so a deep slide is laid out like its neighbors. */
    height: calc(100% + var(--slide-bottom-base));
  }

  /* The escape hatch, set by `watchContentFit` when the event's own text
     cannot fit a screen: the fold grows, and takes the invitation and the
     depth layer down with it, rather than having the last lines run under one
     and over the other. */
  .slide.fold-overrun .slide-fold {
    height: auto;
    min-height: calc(100% + var(--slide-bottom-base));
  }

  .slide-fold > :global(.content) {
    flex-shrink: 0;
    align-self: center;
    width: min(54rem, 100%);
    /* The event and the invitation under it are centered in the fold as one
       block, exactly as the event alone is centered on a slide with no depth
       below it: the free space is split between the margin above the event and
       the one below the invitation, so nothing opens up between them. */
    margin: auto auto 0;
  }

  .slide-fold > .slide-reserve {
    margin-top: auto;
  }

  /* The invitation down. It sits above the timeline, fades as the reader takes
     it, and rides the slide's own scroll away with the fold it belongs to. */
  /* Directly under the event's last line, and small: anywhere lower it sits
     over the map, which is the one thing on the slide that has to stay legible
     under it. Held to the right so it reads as a control rather than as
     another line of the text. */
  .depth-affordance {
    align-self: flex-end;
    flex: 0 0 auto;
    margin: 0.9rem 0 0;
    z-index: 4;
    appearance: none;
    display: flex;
    flex-direction: row;
    align-items: center;
    gap: 0.4rem;
    padding: 0.35rem 0.75rem;
    border-radius: 999px;
    border: 1px solid rgba(148, 163, 184, 0.28);
    background: rgba(8, 12, 24, 0.55);
    backdrop-filter: blur(8px);
    color: rgba(226, 232, 240, 0.92);
    font-family: var(--story-body-font, Inter, sans-serif);
    font-size: 0.72rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    cursor: pointer;
    transition:
      opacity 0.2s ease,
      border-color 0.2s ease;
  }

  /* Out of the way, and out of reach: a chip at zero opacity that still takes
     a tap is worse than one that is merely invisible. */
  .depth-affordance.yielded {
    pointer-events: none;
  }

  .depth-affordance:hover {
    border-color: var(--story-secondary, #38bdf8);
  }

  .depth-affordance-chevrons {
    display: block;
    width: 1.1rem;
    height: 0.95rem;
    position: relative;
  }

  /* Two chevrons, the second trailing the first: the shape of a descent, and
     the one moving thing on a slide that is otherwise still. */
  .depth-chevron {
    position: absolute;
    left: 50%;
    top: 0;
    width: 0.5rem;
    height: 0.5rem;
    margin-left: -0.25rem;
    border-right: 1.5px solid var(--story-secondary, #38bdf8);
    border-bottom: 1.5px solid var(--story-secondary, #38bdf8);
    transform: translateY(0) rotate(45deg);
    animation: depth-beckon 2.4s ease-in-out infinite;
  }

  /* Offset as well as delayed, so the pair reads as a descent even in a still
     frame — and for a reader whose system asks for no motion at all. */
  .depth-chevron:last-child {
    top: 0.3rem;
    animation-delay: 0.18s;
    opacity: 0.5;
  }

  @keyframes depth-beckon {
    0%,
    55%,
    100% {
      transform: translateY(0) rotate(45deg);
    }
    25% {
      transform: translateY(0.22rem) rotate(45deg);
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .depth-chevron {
      animation: none;
      transform: translateY(0) rotate(45deg);
    }
  }

  @media (max-width: 640px) {
    .depth-affordance {
      font-size: 0.68rem;
      padding: 0.4rem 0.75rem 0.3rem;
    }
  }

  /* A short screen has little room between the event and the controls, so the
     chip gives up its label and carries the invitation in the chevrons alone. */
  @media (max-height: 480px) {
    .depth-affordance-label {
      display: none;
    }

    .depth-affordance {
      padding: 0.3rem 0.6rem 0.35rem;
    }
  }

  /* The content keeps its natural height: when a slide has to scroll it is the
     reserve below that gives way first, and only once it is gone does the slide
     scroll at all. Global because every `.content` on a real slide belongs to
     one of the slide components, outside this file's scoping. */
  .slide > :global(.content) {
    flex-shrink: 0;
  }

  /* An event floats in the room the map band leaves it, placed by how much of
     it there is: a short event centers in the free space, a long one rises
     toward the top as its auto margins give way, and once they are gone the
     reserve yields and the slide scrolls. Both margins are auto so the split
     adapts to the viewport as well as to the text — a taller screen carries
     the event lower instead of pinning it under the masthead over a void. The
     overview, chapter, and conclusion slides keep their own flex-start
     anchoring; the `:not()` chain also outweighs the component's own
     `margin: 0 auto`, which stays as the horizontal fallback. */
  .slide:not(.overview):not(.chapter):not(.conclusion) > :global(.content) {
    margin-top: auto;
    margin-bottom: auto;
  }

  /* `--slide-reserve-shrink` comes from `watchContentFit`: 1 while the content
     fits, so the reserve gives up whatever room the content needs and the slide
     never scrolls over empty margin; 0 once the content overruns, because then
     the reader has to scroll anyway and the reserve is what they scroll the
     last line into. The floor holds either way, so a slide that never runs the
     measurement still stops its content short of the controls. */
  .slide-reserve {
    flex-grow: 0;
    flex-shrink: var(--slide-reserve-shrink, 1);
    flex-basis: calc(var(--slide-bottom-total) - var(--slide-bottom-base));
    min-height: calc(
      min(var(--slide-bottom-total), var(--slide-bottom-clear)) -
        var(--slide-bottom-base)
    );
    pointer-events: none;
  }

  /* The loading slide is the one slide with two stacked children of its own, so
     the space between them belongs to it rather than to every slide. */
  .loading-slide {
    gap: 1.25rem;
  }

  .slide-loaded {
    animation: fadeIn 0.3s ease-out;
  }

  .slides-wrapper.map-enabled
    .slide:not(.overview):not(.chapter):not(.conclusion) {
    --slide-bottom-total: 16rem;
  }

  /* The story map is the one thing that occupies a slide's lower margin, and it
     has to stay readable: it is a `45vh` band along the bottom of the slides
     wrapper, and the base coat paints over it (the map sits at `z-index: 1`,
     between the two coats). So where a mapless slide gets its loudest pattern,
     a map slide has to give it up.

     The guard is a wash of exactly 50% gray, which is the identity for
     `overlay`—the blend both coats use—so raising its alpha retires a coat
     without darkening or lightening anything. Painting it as the topmost
     background layer, rather than masking, is what lets it override the coats'
     own masks: the margin coat's mask is a union of two ramps, and a union can
     only ever add.

     It eases in over 10rem so nothing draws a line across the slide, and it
     reaches full gray 6rem below the map's top edge: the pattern is still
     present where the map begins and fades out inside the band the map's own
     top gradient paints in the slide color, which is transparent by about the
     same depth, so the ornament reaches into the map without ever lying over
     legible tiles. The map's gradient is left as it is; only the pattern
     reaches in. The overview slide is left out: the map is hidden while it is
     on screen. */
  .slides-wrapper.map-enabled .slide:not(.overview) {
    --pattern-map-guard: linear-gradient(
      180deg,
      rgb(50% 50% 50% / 0%) 0%,
      rgb(50% 50% 50% / 0%) calc(100% - 45vh - 4rem),
      rgb(50% 50% 50% / 100%) calc(100% - 45vh + 6rem),
      rgb(50% 50% 50% / 100%) 100%
    );
  }

  .slide.chapter,
  .slide.conclusion {
    justify-content: flex-start;
    padding-top: 1rem;
    --slide-bottom-total: 8rem;
    position: relative;
  }

  /* A slide carries the pattern in two coats, both painted from the same image
     at the same offset so they land stroke on stroke. `::after` is an even base
     wash across the whole slide. `::before` is the margin coat: masked away
     behind the content column and at full strength along the sides and below
     the content, where it roughly doubles the pattern.

     Doubling the coat rather than turning one up is what makes the margins
     read. The wash blends with `overlay` onto a very dark slide, so its
     contrast is capped at twice the background luminance no matter how bright
     the strokes are painted—and most story palettes already pick a near-white
     primary, leaving `--pattern-edge-lift` little room to work with. A second
     coat is not capped that way.

     Before this, a single coat faded out below 70% of the slide: the loudest
     ornament sat behind the headline and the empty lower half was left bare.
     That fade was also what kept the pattern off the story map, which the guard
     layer above now does deliberately rather than as a side effect. */
  .slide::before,
  .slide::after {
    content: "";
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    background-color: var(--story-primary, #38bdf8);
    background-image:
      var(--pattern-map-guard), var(--story-pattern-image, none),
      var(--pattern-side-lift), var(--pattern-drop-lift);
    background-size:
      100% 100%,
      var(--story-pattern-size, 400px),
      100% 100%,
      100% 100%;
    background-repeat: no-repeat, repeat, no-repeat, no-repeat;
    background-blend-mode: normal, multiply, screen, screen;
    background-position:
      0 0,
      calc(var(--story-pattern-size, 400px) / -2)
        calc(
          -1 * var(--header-height, 0px) - var(--story-pattern-size, 400px) / 2
        ),
      0 0,
      0 0;
    mix-blend-mode: overlay;
    pointer-events: none;
  }

  .slide::before {
    mask-image: var(--pattern-side-mask), var(--pattern-drop-mask);
    -webkit-mask-image: var(--pattern-side-mask), var(--pattern-drop-mask);
    mask-size: 100% 100%;
    -webkit-mask-size: 100% 100%;
    mask-repeat: no-repeat;
    -webkit-mask-repeat: no-repeat;
    z-index: 0;
  }

  .slide::after {
    /* Trimmed from a flat 1 so the content column ends up a shade calmer than
       it was, which is the other half of the contrast the margins gain. */
    opacity: var(--pattern-core-alpha);
    z-index: 2;
  }

  .slide > * {
    position: relative;
    z-index: 3;
  }

  /* The loading spinner is the one slide child that hangs off the slide rather
     than standing in its flow, so it opts out of the rule above. Stated here,
     and not left to the component that draws it, because the two declarations
     are equally specific: which one wins would otherwise depend on the order
     the bundler happens to emit the two stylesheets in. */
  .slide > :global(.loading-indicator) {
    position: absolute;
  }

  /* A fold lays out the first screen of a deep event, but it must not become
     the containing block for the event picture: the fold occupies the slide's
     padded content box, which leaves the picture inset from the real corner.
     The slide itself is the stable containing block at every breakpoint. */
  .slide > .slide-fold {
    position: static;
  }

  /* Event images are the exception to the slide's in-flow children. This
     covers ordinary events and events wrapped in a fold without compensating
     for either of the slide's breakpoint-dependent padding values. */
  .slide > :global(.event-images),
  .slide-fold > :global(.event-images) {
    position: absolute;
    top: 0;
    right: 0;
  }

  .slide.overview {
    justify-content: flex-start;
    padding-top: 1rem;
    --slide-bottom-total: 8rem;
    position: relative;
  }

  /* Tablet and desktop styles
     - Requires both width (768px+) AND height (600px+) to prevent
       applying desktop styles to landscape phones with short viewports */
  @media (min-width: 768px) and (min-height: 600px) {
    .masthead {
      padding: 1rem 2vw;
    }

    .slides {
      height: 100%;
    }

    .slide {
      --slide-bottom-base: 4rem;
      padding: 3.5rem 4rem var(--slide-bottom-base);
    }

    .loading-slide {
      gap: 1.75rem;
    }

    .slides-wrapper.map-enabled
      .slide:not(.overview):not(.chapter):not(.conclusion) {
      --slide-bottom-total: 18rem;
    }

    .slide.chapter,
    .slide.conclusion {
      padding-top: 2.5rem;
    }

    .compact-info {
      font-size: 1.05rem;
    }

    .slide.overview {
      padding-top: 2.5rem;
    }
  }
</style>
