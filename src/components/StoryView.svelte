<script>
  import { tick, onMount, onDestroy } from "svelte";
  import { mdiClose } from "@mdi/js";
  import { replace, location } from "svelte-spa-router";
  import { queryParams, buildUrlWithParams } from "../stores/queryParams";
  import ImageViewer from "./ImageViewer.svelte";
  import NetworkModal from "./NetworkModal.svelte";
  import OverviewSlide from "./OverviewSlide.svelte";
  import EventSlide from "./EventSlide.svelte";
  import StoryMap from "./StoryMap.svelte";
  import Timeline from "./Timeline.svelte";
  import { _, currentLanguage } from "../stores/language";
  import {
    clamp,
    displayName,
    storyStyleVars,
    joinWithSeparator,
  } from "../utils/helpers.js";
  import {
    toTimestamp,
    normalizePrimaryLocation,
    normalizeAllLocations,
    isCoordinate,
    parseHexColor,
    rgbaFromHex,
    resolveEventIcon,
    computeYearsLabel,
    createDateFormatters,
  } from "../utils/storyHelpers.js";

  export let dataset = null;
  export let egoNetwork = null;
  export let isLoading = false;
  export let loadingStage = null;
  export let activeIndex = 0;
  export let styleConfig = null;
  export let onClose = () => {};
  export let onSlideChange = () => {};

  let enlargedImage = null;
  let visibleDateNote = null;
  let visiblePersonInfo = null;
  let visibleSources = null;
  let visibleAnnotation = null;

  // Network modal state - reactive to URL query parameter
  $: showNetworkModal = $queryParams.network;

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
  $: hasDataset = Boolean(dataset);
  $: yearsLabel = computeYearsLabel(person);
  $: rolesLabel = Array.isArray(person?.primary_roles)
    ? joinWithSeparator(person.primary_roles, styleConfig)
    : "";
  $: eventSlides = events
    .slice()
    .sort((a, b) => toTimestamp(a) - toTimestamp(b))
    .map((event, eventIndex) => ({ ...event, eventIndex }))
    .map((event) => ({
      ...event,
      coordinates: normalizePrimaryLocation(event),
      allCoordinates: normalizeAllLocations(event),
    }));
  $: totalSlides = eventSlides.length;
  $: slides =
    totalSlides > 0
      ? [{ type: "overview" }, ...eventSlides]
      : [{ type: "overview" }];
  $: totalPanels = slides.length;
  $: hasMapData = eventSlides.some((event) => isCoordinate(event.coordinates));
  $: hasMultipleEvents = totalSlides > 1;

  // Track the last activeIndex value to detect external changes (e.g., from browser history)
  let lastPropActiveIndex = activeIndex;

  // Track the last notified index to avoid duplicate notifications
  let lastNotifiedIndex = activeIndex;

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
  $: if (activeIndex !== undefined && activeIndex !== lastNotifiedIndex) {
    lastNotifiedIndex = activeIndex;
    onSlideChange({
      detail: activeIndex,
      source:
        scrollState === SCROLL_STATE.USER_SCROLLING
          ? "user-scroll"
          : currentNavigationSource,
    });
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

  $: datasetName = dataset?.person?.name ?? null;
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

  // Close date note and network modal when slide actually changes
  $: if (activeIndex !== undefined && activeIndex !== previousActiveIndex) {
    visibleDateNote = null;
    visiblePersonInfo = null;
    visibleSources = null;
    visibleAnnotation = null;
    // Close network modal when slide changes by updating URL
    if ($queryParams.network) {
      const basePath = $location.split("?")[0];
      const newUrl = buildUrlWithParams(basePath, {
        slide: activeIndex,
        timeline: $queryParams.timeline,
        network: false,
      });
      replace(newUrl);
    }
    previousActiveIndex = activeIndex;
  }

  let slidesContainer;
  let initialScrollDone = false;
  let initialScrollPending = false;
  let descriptionOverflows = new Set(); // Track which descriptions overflow

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
    if (!slidesContainer || totalPanels === 0 || !initialScrollDone) return;

    const { scrollLeft, clientWidth } = slidesContainer;
    if (!clientWidth) return;

    const clampedIndex = clamp(Math.round(scrollLeft / clientWidth), 0, totalPanels - 1);
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
      isOverflowing
        ? descriptionOverflows.add(slideId)
        : descriptionOverflows.delete(slideId);
      descriptionOverflows = new Set(descriptionOverflows); // Trigger reactivity
    };

    // Check immediately and after content loads
    check();
    setTimeout(check, 0);

    return {
      destroy() {
        descriptionOverflows.delete(slideId);
        descriptionOverflows = new Set(descriptionOverflows);
      },
    };
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

    // Cancel any pending scroll operations
    if (scrollStateTimeout) {
      clearTimeout(scrollStateTimeout);
      scrollStateTimeout = null;
    }

    // Update state machine
    scrollState = SCROLL_STATE.PROGRAMMATIC;
    currentNavigationSource = source; // Track the source of this navigation

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
    slidesContainer.scrollTo({
      left: scrollLeft,
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
      source: "button",
      updateStateImmediately: true,
    });
  }

  function nextSlide() {
    if (totalPanels === 0) return;
    const targetIndex = Math.min(totalPanels - 1, activeIndex + 1);
    requestScrollTo(targetIndex, {
      source: "button",
      updateStateImmediately: true,
    });
  }

  function goToEvent(eventIndex) {
    if (!Number.isInteger(eventIndex)) return;
    const clamped = clamp(eventIndex, 0, Math.max(eventSlides.length - 1, 0));
    const targetIndex = clamped + 1;
    if (totalPanels === 0) return;
    requestScrollTo(targetIndex, {
      source: "timeline_event",
      updateStateImmediately: true,
    });
  }

  // Wrapper for Timeline component callbacks
  function scrollToIndexExternal(index, immediate = false) {
    requestScrollTo(index, {
      source: "timeline_scrubber",
      immediate,
      updateStateImmediately: !immediate, // Smooth = optimistic update
    });
  }

  function handleClose() {
    onClose();
  }

  function enlargeImage(imageData) {
    enlargedImage = imageData; // Now stores full image object with url, caption, source
  }

  function closeEnlargedImage() {
    enlargedImage = null;
  }

  function handleScroll() {
    // Ignore during programmatic scrolls
    if (
      scrollState === SCROLL_STATE.PROGRAMMATIC ||
      scrollState === SCROLL_STATE.SETTLING
    ) {
      return;
    }

    if (totalPanels === 0) {
      activeIndex = 0;
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
    if (
      event.target.tagName === "INPUT" ||
      event.target.tagName === "TEXTAREA" ||
      event.target.isContentEditable
    ) {
      return;
    }

    if (totalPanels === 0) return;

    if (event.key === "ArrowLeft") {
      event.preventDefault();
      prevSlide();
    } else if (event.key === "ArrowRight") {
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

  function handleTouchEnd() {
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
  }

  function toggleAnnotation(eventIndex, termKey) {
    const compositeKey = `${eventIndex}-${termKey}`;
    visibleAnnotation = visibleAnnotation === compositeKey ? null : compositeKey;
  }

  function handleClickOutside(event) {
    // Check if click is outside the date-wrapper, person-info-wrapper, sources-wrapper, or annotated-term
    const dateWrapper = event.target.closest(".date-wrapper");
    const personWrapper = event.target.closest(".person-info-wrapper");
    const sourcesWrapper = event.target.closest(".sources-wrapper");
    const annotatedTerm = event.target.closest(".annotated-term");
    const annotationPopup = event.target.closest(".annotation-popup");
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
  }

  function toggleSources(eventIndex) {
    visibleSources = visibleSources === eventIndex ? null : eventIndex;
  }

  function openNetworkModal() {
    setNetworkModal(true);
  }

  function closeNetworkModal() {
    setNetworkModal(false);
  }

  function setNetworkModal(show) {
    const basePath = $location.split("?")[0];
    const newUrl = buildUrlWithParams(basePath, {
      slide: activeIndex,
      timeline: $queryParams.timeline,
      network: show,
    });
    replace(newUrl);
  }

  function handleTimelineExpandChange(event) {
    const expanded = event.detail.expanded;

    // Build URL with or without timeline param
    const basePath = $location.split("?")[0];
    const newUrl = buildUrlWithParams(basePath, {
      slide: activeIndex,
      timeline: expanded,
      network: $queryParams.network,
    });

    // Always use replace() - modal state should not create history entries
    replace(newUrl);
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
          // Add a small delay to ensure DOM is fully rendered
          return new Promise((resolve) => {
            setTimeout(resolve, 50);
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
      activeIndex === 0
    ) {
      // No initial scroll needed (starting at index 0)
      initialScrollDone = true;
    }
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
      class:initial-loading={!initialScrollDone && activeIndex > 0}
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
        {#each slides as slide (slide.eventIndex)}
          <section
            class="slide slide-loaded"
            class:overview={slide.type === "overview"}
            aria-label={slide.type === "overview"
              ? `Overview: ${personName}`
              : `Slide ${slide.eventIndex + 1} of ${totalSlides}: ${slide.title}`}
          >
            {#if slide.type === "overview"}
              <OverviewSlide
                {person}
                {portrait}
                {personName}
                {yearsLabel}
                {rolesLabel}
                {personSummary}
                {egoNetwork}
                {descriptionOverflows}
                onEnlargeImage={enlargeImage}
                onOpenNetwork={openNetworkModal}
                {checkOverflow}
              />
            {:else if slide.type !== "spacer"}
              <EventSlide
                {slide}
                {egoNetwork}
                {styleConfig}
                {formatters}
                {visibleDateNote}
                {visiblePersonInfo}
                {visibleSources}
                {visibleAnnotation}
                {descriptionOverflows}
                onEnlargeImage={enlargeImage}
                onToggleDateNote={toggleDateNote}
                onTogglePersonInfo={togglePersonInfo}
                onToggleSources={toggleSources}
                onToggleAnnotation={toggleAnnotation}
                onOpenNetwork={openNetworkModal}
                {checkOverflow}
              />
            {/if}
          </section>
        {/each}
      {/if}
    </main>
    {#if hasMapData}
      <StoryMap
        bind:this={storyMapComponent}
        {activeCoordinates}
        allActiveCoordinates={activeEventIndex >= 0
          ? (eventSlides[activeEventIndex]?.allCoordinates ?? [])
          : []}
        {markerTrail}
        {hasMapData}
        {activeIndex}
        {styleConfig}
      />
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
    initialExpanded={$queryParams.timeline}
    onPrevSlide={prevSlide}
    onNextSlide={nextSlide}
    onGoToEvent={goToEvent}
    onScrollToIndex={scrollToIndexExternal}
    on:expandchange={handleTimelineExpandChange}
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
    z-index: 2;
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
    padding: clamp(0.3rem, 0.9vh, 0.45rem) clamp(0.7rem, 2.2vw, 0.95rem);
    font-size: clamp(0.75rem, 1.2vh, 0.85rem);
    font-weight: 600;
    cursor: pointer;
    flex: 0 0 auto;
    display: inline-flex;
    align-items: center;
    gap: clamp(0.35rem, 0.9vh, 0.45rem);
    transition:
      border-color 0.2s ease,
      background-color 0.2s ease,
      color 0.2s ease;
  }

  /* Compact masthead for landscape mobile (short viewports)
     - Applies to rotated phones with limited vertical space
     - Makes header more compact to preserve screen real estate */
  @media (max-height: 500px) {
    .masthead {
      padding: 0.15rem 0.5rem;
    }

    .compact-info {
      font-size: 0.7rem;
      gap: 0.4rem;
    }

    .close-story {
      padding: 0.15rem 0.5rem;
      font-size: 0.65rem;
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

  .icon {
    width: 1.1em;
    height: 1.1em;
    fill: currentColor;
    flex: 0 0 auto;
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

  .slide.overview {
    justify-content: flex-start;
    padding-top: 1rem;
    padding-bottom: 8rem;
    position: relative;
  }

  .overview-content {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 1rem;
    text-align: center;
    max-width: 56rem;
  }

  .overview-text {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
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

  .content {
    display: flex;
    flex-direction: column;
    gap: 0.8rem;
    position: relative;
    z-index: 4;
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
      padding: 3.5rem 4rem 4rem;
      gap: 1.75rem;
    }

    .slides-wrapper.map-enabled .slide:not(.overview) {
      padding-bottom: 18rem;
    }

    .compact-info {
      font-size: 1.05rem;
    }

    .slide.overview {
      padding-top: 2.5rem;
    }

    .overview-content {
      flex-direction: row;
      align-items: center;
      flex-wrap: wrap;
      text-align: left;
      justify-content: center;
      gap: 3rem;
    }

    .overview-text {
      flex: 1;
      min-width: 300px;
      align-items: flex-start;
    }
  }
</style>
