<script>
  import {
    mdiChevronLeft,
    mdiChevronRight,
    mdiHome,
    mdiChevronUp,
    mdiChevronDown,
    mdiMapMarkerOutline,
    mdiLightbulbOnOutline,
    mdiCradle,
    mdiRing,
    mdiBook,
  } from "@mdi/js";
  import { _ } from "../stores/language";
  import { extractYear } from "../utils/storyHelpers.js";
  import { fade } from "svelte/transition";
  import { createEventDispatcher } from "svelte";
  import { mdiIconMap } from "virtual:mdi-icon-map";

  export let activeIndex = 0;
  export let totalSlides = 0;
  export let totalPanels = 0; // Total number of slides including overview and chapter slides
  export let activeEventIndex = -1;
  export let hasMultipleEvents = false;
  export let indicatorProgress = 0;
  export let indicatorIcons = []; // Fallback icons (deprecated, prefer event_type_icon in eventSlides)
  export let eventSlides = []; // Array of event objects with titles and event_type_icon
  export let slides = []; // Array of all slides including chapter slides
  export let chapters = []; // Array of chapter objects with headlines
  export let onPrevSlide = () => {};
  export let onNextSlide = () => {};
  export let onGoToEvent = () => {};
  export let onGoToSlide = () => {}; // Navigate to specific slide index (for chapter slides)
  export let onScrollToIndex = () => {};
  export let initialExpanded = false; // NEW: Initial expanded state from URL

  const dispatch = createEventDispatcher();

  $: isExpanded = initialExpanded;

  // Helper function to resolve MDI icon path from icon name (e.g., "mdi-crown" -> SVG path).
  // Uses a static lookup map generated from scripts/icon_categories.py — tree-shakeable.
  // Unknown icon strings return null (graceful fallback).
  function resolveIconPath(iconName) {
    if (!iconName || typeof iconName !== "string") return null;
    return mdiIconMap[iconName] ?? null;
  }

  // Helper function to get icon for event_class
  function getEventClassIcon(eventClass) {
    if (!eventClass?.type) return null;

    switch (eventClass.type) {
      case "birth":
        return mdiCradle;
      case "invention":
        return mdiLightbulbOnOutline;
      case "marriage_partnership":
        return mdiRing;
      case "publication":
        return mdiBook;
      case "migration":
        return resolveIconPath("mdi-map-marker-multiple");
      default:
        return null;
    }
  }

  // Build icon array from event_class first, then event_type_icon, with fallback to indicatorIcons
  $: eventIcons = eventSlides.map((event, idx) => {
    // Priority 1: event_class icon
    if (event.event_class) {
      const classIcon = getEventClassIcon(event.event_class);
      if (classIcon) return classIcon;
    }

    // Priority 2: event_type_icon
    if (event.event_type_icon) {
      const iconPath = resolveIconPath(event.event_type_icon);
      if (iconPath) return iconPath;
    }

    // Priority 3: fallback to indicatorIcons
    return indicatorIcons[idx] || null;
  });
  let expandedContainerElement = null;

  $: hasEvents = totalSlides > 0;
  $: hasChapters = Array.isArray(chapters) && chapters.length > 0;

  // Group events by chapter for display
  $: groupedEvents = (() => {
    if (!hasChapters) {
      return [
        {
          chapter: null,
          events: eventSlides.map((event, idx) => ({
            ...event,
            originalIndex: idx,
          })),
        },
      ];
    }

    // Create a map of chapter IDs to chapter objects
    const chapterMap = new Map(chapters.map((ch) => [ch.id, ch]));

    // Group events by their chapter
    const groups = new Map();

    eventSlides.forEach((event, idx) => {
      const eventWithIndex = { ...event, originalIndex: idx };
      if (event.chapter && chapterMap.has(event.chapter)) {
        const chapterId = event.chapter;
        if (!groups.has(chapterId)) {
          groups.set(chapterId, {
            chapter: chapterMap.get(chapterId),
            events: [],
          });
        }
        groups.get(chapterId).events.push(eventWithIndex);
      } else {
        // For events without a chapter, assign them to the appropriate chapter based on date
        // Compare at year granularity: chapter bounds are usually year-precision
        // ("1938") while events may carry full dates ("1938-05-01"), and a raw
        // string comparison would push end-year events out of their chapter.
        let assignedChapter = null;
        const eventYear = extractYear(event.date);
        for (const chapter of chapters) {
          const startYear = extractYear(chapter.date_start);
          const endYear = extractYear(chapter.date_end);
          if (
            Number.isFinite(eventYear) &&
            Number.isFinite(startYear) &&
            Number.isFinite(endYear) &&
            eventYear >= startYear &&
            eventYear <= endYear
          ) {
            assignedChapter = chapter.id;
            break;
          }
        }

        // If we found a matching chapter by date, add to that chapter
        if (assignedChapter && chapterMap.has(assignedChapter)) {
          if (!groups.has(assignedChapter)) {
            groups.set(assignedChapter, {
              chapter: chapterMap.get(assignedChapter),
              events: [],
            });
          }
          groups.get(assignedChapter).events.push(eventWithIndex);
        } else {
          // If no matching chapter found, create a standalone group (will be inserted in chronological order below)
          const standaloneKey = `_standalone_${idx}`;
          groups.set(standaloneKey, {
            chapter: null,
            events: [eventWithIndex],
            sortDate: event.date, // Add sort date for ordering
          });
        }
      }
    });

    // Convert to array and sort by chapter date (or event date for standalone groups)
    const result = Array.from(groups.values()).sort((a, b) => {
      const dateA = a.chapter ? a.chapter.date_start : a.sortDate || "9999";
      const dateB = b.chapter ? b.chapter.date_start : b.sortDate || "9999";
      return dateA.localeCompare(dateB);
    });

    return result;
  })();

  // Build flat list of items with chapter dots for collapsed timeline
  // Each item represents a slide (overview, chapter, conclusion, or event) with timeline dot
  $: timelineItems = (() => {
    if (!slides || slides.length === 0) {
      return [];
    }

    const items = [];
    let eventCount = 0;

    // Iterate through slides array (excluding overview slide at index 0)
    for (let i = 1; i < slides.length; i++) {
      const slide = slides[i];

      if (slide.type === "chapter") {
        // Chapter slide gets a chapter dot
        items.push({
          type: "chapter",
          chapter: slide.chapter,
          slideIndex: i,
        });
      } else if (slide.type === "conclusion") {
        // Conclusion slide gets a conclusion dot
        items.push({
          type: "conclusion",
          slideIndex: i,
        });
      } else {
        // Event slide gets an event dot (event slides don't have type property)
        items.push({
          type: "event",
          index: eventCount,
          slideIndex: i,
        });
        eventCount++;
      }
    }

    return items;
  })();

  // Compute current chapter for active slide (either from event or chapter slide)
  $: currentChapter = (() => {
    // First check if we're on a chapter slide
    if (activeIndex > 0 && activeIndex < slides.length) {
      const currentSlide = slides[activeIndex];
      if (currentSlide?.type === "chapter" && currentSlide?.chapter) {
        return currentSlide.chapter;
      }
      // Check if we're on a conclusion slide
      if (currentSlide?.type === "conclusion") {
        return {
          id: "conclusion",
          headline: $_("conclusion.title").toUpperCase(),
        };
      }
    }

    // Otherwise check if active event has a chapter
    if (activeEventIndex < 0 || activeEventIndex >= eventSlides.length) {
      return null; // Overview slide or invalid index
    }

    const currentEvent = eventSlides[activeEventIndex];
    if (!currentEvent?.chapter || !hasChapters) {
      return null; // Event has no chapter or no chapters exist
    }

    // Find the chapter object by ID
    const chapter = chapters.find((ch) => ch.id === currentEvent.chapter);
    return chapter || null;
  })();

  // Calculate horizontal offset for chapter indicator based on active slide position
  $: chapterIndicatorOffset = (() => {
    if (activeIndex === 0 || totalPanels === 0) {
      return 0; // Centered when on overview
    }

    // Calculate position as percentage based on activeIndex (includes chapter slides)
    // activeIndex ranges from 0 (overview) to totalPanels - 1
    // We want first content slide (index 1) at left, last slide at right
    const progress = (activeIndex - 1) / Math.max(1, totalPanels - 2);

    // Map to offset range: -20% to +20% (leftward for early slides, rightward for later slides)
    // Subtract 0.5 to center around 0, multiply by 40% for range
    const offset = (progress - 0.5) * 40;

    return offset;
  })();

  // Scroll active event into view when first expanding (but allow manual scroll after)
  let hasScrolledToActive = false;
  $: if (isExpanded) {
    if (
      !hasScrolledToActive &&
      expandedContainerElement &&
      activeEventIndex >= 0
    ) {
      // Use setTimeout to ensure DOM is ready after expansion animation
      setTimeout(() => {
        const activeElement = expandedContainerElement?.querySelector(
          `[data-event-index="${activeEventIndex}"]`
        );
        if (activeElement) {
          activeElement.scrollIntoView({ behavior: "smooth", block: "center" });
          hasScrolledToActive = true;
        }
      }, 100);
    }
  } else {
    hasScrolledToActive = false;
  }

  function toggleExpanded() {
    // The URL owns this state: the dispatch below makes StoryView rewrite the
    // timeline param, which flows back through initialExpanded and re-runs the
    // reactive assignment above with the same value. Setting it here first is
    // deliberate, so the toggle paints without waiting for that round trip.
    // eslint-disable-next-line svelte/no-reactive-reassign
    isExpanded = !isExpanded;
    dispatch("expandchange", { expanded: isExpanded });
  }
</script>

{#if hasEvents}
  <div
    class="indicator"
    class:expanded={isExpanded}
    role="group"
    aria-label={$_("timeline.show_event", {
      index: activeEventIndex + 1,
      total: totalSlides,
    })}
    style={`--indicator-progress: ${indicatorProgress}`}
  >
    <div class="indicator-content">
      {#if totalPanels > 1 && !isExpanded}
        <div class="indicator-nav">
          <button
            type="button"
            class="nav-btn prev"
            on:click={onPrevSlide}
            aria-label={$_("timeline.previous_slide")}
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
            on:click={onNextSlide}
            aria-label={$_("timeline.next_slide")}
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
      <div
        class="indicator-track"
        class:single={!hasMultipleEvents}
        class:expanded={isExpanded}
        role="group"
        aria-label={$_("timeline.scrubber")}
      >
        {#if isExpanded}
          <button
            type="button"
            class="collapse-button"
            on:click={toggleExpanded}
            aria-label={$_("timeline.collapse")}
            aria-expanded={isExpanded}
          >
            <svg
              class="icon"
              viewBox="0 0 24 24"
              role="presentation"
              aria-hidden="true"
            >
              <path d={mdiChevronDown} />
            </svg>
          </button>
        {/if}
        <div
          class="dots-container"
          class:expanded={isExpanded}
          bind:this={expandedContainerElement}
          on:wheel|stopPropagation
        >
          {#if !isExpanded}
            <div class="dot-wrapper home-dot">
              <button
                type="button"
                class="dot square"
                class:active={activeIndex === 0}
                style="transform: scale({activeIndex === 0
                  ? 1.6
                  : activeEventIndex === 0
                    ? 1.3
                    : 1.0}); z-index: {activeIndex === 0
                  ? 16
                  : activeEventIndex === 0
                    ? 13
                    : 10};"
                on:click={() => onScrollToIndex(0)}
                aria-label={$_("timeline.show_overview")}
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
            </div>
            {#each timelineItems as item}
              {#if item.type === "chapter"}
                {@const chapterSlideIndex = item.slideIndex}
                {@const distance = Math.abs(chapterSlideIndex - activeIndex)}
                {@const scale =
                  distance === 0
                    ? 1.6
                    : distance === 1
                      ? 1.3
                      : distance === 2
                        ? 1.15
                        : 1.0}
                {@const translate =
                  distance === 0
                    ? 0
                    : Math.abs(distance) === 1
                      ? (chapterSlideIndex - activeIndex) * 0.3
                      : Math.abs(distance) === 2
                        ? (chapterSlideIndex - activeIndex) * 0.15
                        : 0}
                <div class="dot-wrapper">
                  <button
                    type="button"
                    class="dot chapter-dot"
                    class:active={activeIndex === item.slideIndex}
                    style="transform: scale({scale}) translateX({translate}rem); z-index: {Math.round(
                      scale * 10
                    )};"
                    on:click={() => onGoToSlide(item.slideIndex)}
                    aria-label={$_("timeline.go_to_chapter", {
                      chapter: item.chapter.headline,
                    })}
                    aria-current={activeIndex === item.slideIndex
                      ? "true"
                      : undefined}
                  >
                    <span class="dot-inner-chapter"></span>
                  </button>
                </div>
              {:else if item.type === "conclusion"}
                {@const conclusionSlideIndex = item.slideIndex}
                {@const distance = Math.abs(conclusionSlideIndex - activeIndex)}
                {@const scale =
                  distance === 0
                    ? 1.6
                    : distance === 1
                      ? 1.3
                      : distance === 2
                        ? 1.15
                        : 1.0}
                {@const translate =
                  distance === 0
                    ? 0
                    : Math.abs(distance) === 1
                      ? (conclusionSlideIndex - activeIndex) * 0.3
                      : Math.abs(distance) === 2
                        ? (conclusionSlideIndex - activeIndex) * 0.15
                        : 0}
                <div class="dot-wrapper">
                  <button
                    type="button"
                    class="dot conclusion-dot square"
                    class:active={activeIndex === item.slideIndex}
                    style="transform: scale({scale}) translateX({translate}rem); z-index: {Math.round(
                      scale * 10
                    )};"
                    on:click={() => onGoToSlide(item.slideIndex)}
                    aria-label={$_("timeline.go_to_conclusion")}
                    aria-current={activeIndex === item.slideIndex
                      ? "true"
                      : undefined}
                  >
                    <span class="dot-inner-conclusion"></span>
                  </button>
                </div>
              {:else if item.type === "event"}
                {@const idx = item.index}
                {@const eventSlideIndex = item.slideIndex}
                {@const distance = Math.abs(eventSlideIndex - activeIndex)}
                {@const scale =
                  distance === 0
                    ? 1.6
                    : distance === 1
                      ? 1.3
                      : distance === 2
                        ? 1.15
                        : 1.0}
                {@const translate =
                  distance === 0
                    ? 0
                    : Math.abs(distance) === 1
                      ? (eventSlideIndex - activeIndex) * 0.3
                      : Math.abs(distance) === 2
                        ? (eventSlideIndex - activeIndex) * 0.15
                        : 0}
                <div class="dot-wrapper">
                  <button
                    type="button"
                    class="dot"
                    class:active={idx === activeEventIndex}
                    style="transform: scale({scale}) translateX({translate}rem); z-index: {Math.round(
                      scale * 10
                    )};"
                    on:click={() => onGoToEvent(idx)}
                    aria-label={`Show event ${idx + 1} of ${totalSlides}`}
                    aria-current={idx === activeEventIndex ? "true" : undefined}
                  >
                    {#if eventIcons[idx]}
                      <svg
                        class="dot-icon"
                        viewBox="0 0 24 24"
                        role="img"
                        aria-hidden="true"
                      >
                        <path d={eventIcons[idx]} />
                      </svg>
                    {/if}
                  </button>
                </div>
              {/if}
            {/each}
            <button
              type="button"
              class="chapter-indicator-box"
              class:has-chapter={currentChapter}
              class:show-event-count={activeIndex === 0 && !currentChapter}
              style="--chapter-offset: {chapterIndicatorOffset}%;"
              on:click={toggleExpanded}
              aria-label={currentChapter
                ? $_("timeline.expand_to_chapter", {
                    chapter: currentChapter.headline,
                  }) || `Expand timeline to ${currentChapter.headline}`
                : isExpanded
                  ? $_("timeline.collapse")
                  : $_("timeline.expand")}
              aria-expanded={isExpanded}
            >
              <div class="chapter-indicator-content">
                {#if currentChapter}
                  {#key currentChapter.id}
                    <span
                      class="chapter-indicator-label"
                      transition:fade={{ duration: 300 }}
                    >
                      {currentChapter.headline}
                    </span>
                  {/key}
                {:else if activeIndex === 0 && totalSlides > 0}
                  <span
                    class="chapter-indicator-label event-count-label"
                    transition:fade={{ duration: 300 }}
                  >
                    {$_(
                      `timeline.event_${totalSlides === 1 ? "one" : "other"}`,
                      { count: totalSlides }
                    )}
                  </span>
                {/if}
                <svg
                  class="chapter-chevron"
                  viewBox="0 0 24 24"
                  role="presentation"
                  aria-hidden="true"
                >
                  <path d={mdiChevronUp} />
                </svg>
              </div>
            </button>
          {:else}
            <div class="expanded-timeline-container">
              <div
                class="timeline-item home-item clickable"
                class:active={activeIndex === 0}
                role="button"
                tabindex="0"
                on:click={() => onScrollToIndex(0)}
                on:keydown={(e) =>
                  (e.key === "Enter" || e.key === " ") && onScrollToIndex(0)}
              >
                <button
                  type="button"
                  class="dot square"
                  class:active={activeIndex === 0}
                  style="transform: scale({activeIndex === 0
                    ? 1.4
                    : 1.0}); transition: transform 0.25s ease;"
                  on:click|stopPropagation={() => onScrollToIndex(0)}
                  aria-label={$_("timeline.show_overview")}
                  aria-current={activeIndex === 0 ? "true" : undefined}
                  tabindex="-1"
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
                <div class="timeline-content">
                  <span class="event-title">Overview</span>
                </div>
              </div>
              {#each groupedEvents as group}
                {#if group.chapter}
                  {@const chapterAge = group.chapter.age_start ?? 0}
                  {@const chapterLocation = group.chapter.location}
                  {@const chapterSlideIndex = slides.findIndex(
                    (s) =>
                      s.type === "chapter" && s.chapter.id === group.chapter.id
                  )}
                  <div
                    class="chapter-header clickable"
                    class:active={activeIndex === chapterSlideIndex}
                    style="--event-age: {chapterAge};"
                    role="button"
                    tabindex="0"
                    on:click={() =>
                      chapterSlideIndex >= 0 && onGoToSlide(chapterSlideIndex)}
                    on:keydown={(e) =>
                      (e.key === "Enter" || e.key === " ") &&
                      chapterSlideIndex >= 0 &&
                      onGoToSlide(chapterSlideIndex)}
                  >
                    {#if chapterAge > 0}
                      <span class="age-line chapter-age-line"></span>
                    {/if}
                    <h3 class="chapter-headline">{group.chapter.headline}</h3>
                    {#if chapterLocation}
                      <div class="chapter-meta">
                        <div class="chapter-meta-item">
                          <svg
                            class="chapter-meta-icon"
                            viewBox="0 0 24 24"
                            role="presentation"
                            aria-hidden="true"
                          >
                            <path d={mdiMapMarkerOutline} />
                          </svg>
                          <span class="chapter-meta-text"
                            >{chapterLocation}</span
                          >
                        </div>
                      </div>
                    {/if}
                  </div>
                {/if}
                {#each group.events as event}
                  {@const idx = event.originalIndex}
                  {@const eventTitle = event.title || `Event ${idx + 1}`}
                  {@const eventYear = event.date
                    ? event.date.split("-")[0]
                    : ""}
                  {@const eventAge = event.age ?? 0}
                  <div
                    class="timeline-item clickable"
                    class:active={idx === activeEventIndex}
                    data-event-index={idx}
                    style="--event-age: {eventAge};"
                    role="button"
                    tabindex="0"
                    on:click={() => onGoToEvent(idx)}
                    on:keydown={(e) =>
                      (e.key === "Enter" || e.key === " ") && onGoToEvent(idx)}
                  >
                    <div class="event-box">
                      {#if eventAge > 0}
                        <span class="age-line"></span>
                      {/if}
                      <button
                        type="button"
                        class="dot"
                        class:active={idx === activeEventIndex}
                        style="transform: scale({idx === activeEventIndex
                          ? 1.4
                          : 1.0}); transition: transform 0.25s ease;"
                        on:click|stopPropagation={() => onGoToEvent(idx)}
                        aria-label={`Show event ${idx + 1} of ${totalSlides}`}
                        aria-current={idx === activeEventIndex
                          ? "true"
                          : undefined}
                        tabindex="-1"
                      >
                        {#if eventIcons[idx]}
                          <svg
                            class="dot-icon"
                            viewBox="0 0 24 24"
                            role="img"
                            aria-hidden="true"
                          >
                            <path d={eventIcons[idx]} />
                          </svg>
                        {/if}
                      </button>
                      <div class="timeline-content">
                        {#if eventYear || eventAge > 0}
                          <span class="event-metadata">
                            {#if eventYear}
                              <span class="event-year">{eventYear}</span>
                            {/if}
                            {#if eventAge > 0}
                              {#if eventYear}
                                <span class="metadata-separator">•</span>
                              {/if}
                              <span class="age-label"
                                >{$_("story.age", { age: eventAge })}</span
                              >
                            {/if}
                          </span>
                        {/if}
                        <span class="event-title">{eventTitle}</span>
                      </div>
                    </div>
                  </div>
                {/each}
              {/each}

              <!-- Add conclusion at the end of expanded timeline if it exists -->
              {#if slides[slides.length - 1]?.type === "conclusion"}
                {@const conclusionSlideIndex = slides.length - 1}
                <div
                  class="timeline-item home-item conclusion-item"
                  class:active={activeIndex === conclusionSlideIndex}
                  role="button"
                  tabindex="0"
                  on:click={() => onGoToSlide(conclusionSlideIndex)}
                  on:keydown={(e) =>
                    (e.key === "Enter" || e.key === " ") &&
                    onGoToSlide(conclusionSlideIndex)}
                >
                  <button
                    type="button"
                    class="dot square conclusion-dot"
                    class:active={activeIndex === conclusionSlideIndex}
                    style="transform: scale({activeIndex ===
                    conclusionSlideIndex
                      ? 1.4
                      : 1.0}); transition: transform 0.25s ease;"
                    on:click|stopPropagation={() =>
                      onGoToSlide(conclusionSlideIndex)}
                    aria-label={$_("timeline.show_conclusion")}
                    aria-current={activeIndex === conclusionSlideIndex
                      ? "true"
                      : undefined}
                    tabindex="-1"
                  >
                    <span class="dot-inner-conclusion"></span>
                  </button>
                  <div class="timeline-content">
                    <span class="event-title"
                      >{$_("conclusion.title").toUpperCase()}</span
                    >
                  </div>
                </div>
              {/if}
            </div>
          {/if}
        </div>
      </div>
    </div>
  </div>
{/if}

<style>
  .indicator {
    --dot-size: clamp(1.25rem, 3vw, 1.6rem);
    --dot-gap: 0rem;
    position: fixed;
    top: auto;
    bottom: 0.75rem;
    left: 50%;
    transform: translateX(-50%);
    width: min(96vw, 1020px);
    height: auto;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 0;
    pointer-events: none; /* Container lets events pass through */
    z-index: 5;
  }

  .indicator.expanded {
    top: 0.75rem;
    bottom: 0.75rem;
    height: calc(100vh - 1.5rem);
    transition:
      top 1s cubic-bezier(0.22, 1, 0.36, 1),
      bottom 1s cubic-bezier(0.22, 1, 0.36, 1),
      height 1s cubic-bezier(0.22, 1, 0.36, 1);
  }

  .collapse-button {
    appearance: none;
    border: none;
    padding: 0.45rem;
    pointer-events: auto;
    position: absolute;
    top: 1rem;
    left: 50%;
    transform: translateX(-50%);
    width: 2.5rem;
    height: 2.5rem;
    border-radius: 50%;
    background: rgba(15, 23, 42, 0.85);
    backdrop-filter: blur(8px);
    border: 1px solid var(--story-primary, rgba(148, 163, 184, 0.3));
    box-shadow: 0 4px 12px rgba(15, 23, 42, 0.3);
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    transition:
      background-color 0.3s ease,
      border-color 0.3s ease,
      box-shadow 0.3s ease,
      transform 0.2s ease;
    z-index: 100;
  }

  .collapse-button .icon {
    width: 1.3rem;
    height: 1.3rem;
    fill: var(--story-primary, rgba(226, 232, 240, 0.7));
    transition:
      fill 0.2s ease,
      transform 0.2s ease;
  }

  .collapse-button:hover,
  .collapse-button:focus {
    border-color: var(--story-primary, rgba(148, 163, 184, 0.5));
    box-shadow: 0 6px 16px rgba(15, 23, 42, 0.4);
    transform: translateX(-50%) translateY(-2px);
    outline: none;
  }

  .collapse-button:hover .icon,
  .collapse-button:focus .icon {
    fill: var(--story-primary, rgba(226, 232, 240, 0.95));
    transform: translateY(1px);
  }

  .collapse-button:focus-visible {
    outline: 2px solid var(--story-primary, rgba(148, 163, 184, 0.6));
    outline-offset: 2px;
  }

  .indicator-content {
    pointer-events: auto;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 3rem;
    width: 100%;
    height: 100%;
    transition:
      gap 1s cubic-bezier(0.22, 1, 0.36, 1),
      padding-top 1s cubic-bezier(0.22, 1, 0.36, 1);
  }

  .indicator.expanded .indicator-content {
    justify-content: flex-start;
  }

  .indicator-nav {
    pointer-events: auto;
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
    gap: 1.25rem;
    transition: opacity 0.3s ease;
  }

  .indicator.expanded .indicator-nav {
    opacity: 0;
    pointer-events: none;
  }

  .indicator-track {
    pointer-events: auto; /* Track captures events, container above lets them pass through */
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 100%;
    padding: 0.65rem 0.75rem;
    border-radius: 1.5rem;
    background: rgba(15, 23, 42, 0.65);
    backdrop-filter: blur(6px);
    box-shadow: 0 10px 30px rgba(15, 23, 42, 0.25);
    border: 1px solid rgba(148, 163, 184, 0.2);
    cursor: default;
    user-select: none;
    transition:
      padding 1s cubic-bezier(0.22, 1, 0.36, 1),
      background 1s cubic-bezier(0.22, 1, 0.36, 1),
      height 1s cubic-bezier(0.22, 1, 0.36, 1);
  }

  .indicator-track.expanded {
    border-radius: 1.5rem;
    padding: 0;
    height: 100%;
    background: rgba(15, 23, 42, 0.85);
    overflow: visible;
    position: relative;
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
    justify-content: flex-start;
    width: 100%;
    max-width: min(90vw, 860px);
    z-index: 2;
    transition:
      flex-direction 0.8s cubic-bezier(0.22, 1, 0.36, 1),
      gap 0.8s cubic-bezier(0.22, 1, 0.36, 1),
      justify-content 0.8s cubic-bezier(0.22, 1, 0.36, 1);
  }

  .dots-container:not(.expanded) {
    /* Distribute items across full width with flex-grow */
    justify-content: space-between;
  }

  /* On narrow screens, allow items to overlap by using negative margins */
  @media (max-width: 768px) {
    .dots-container:not(.expanded) .dot-wrapper:not(.home-dot) .dot {
      margin-left: -0.3rem;
    }
  }

  @media (max-width: 480px) {
    .dots-container:not(.expanded) .dot-wrapper:not(.home-dot) .dot {
      margin-left: -0.5rem;
    }
  }

  @media (max-width: 380px) {
    .dots-container:not(.expanded) .dot-wrapper:not(.home-dot) .dot {
      margin-left: -0.7rem;
    }
  }

  .dots-container.expanded {
    max-width: 100%;
    height: 100%;
    width: 100%;
    padding: 1rem;
    overflow-y: auto;
    overflow-x: hidden;
    scrollbar-width: thin;
    scrollbar-color: rgba(148, 163, 184, 0.3) transparent;
    scroll-padding-top: 0.5rem;
    scroll-behavior: smooth;
    align-items: flex-start;
    justify-content: flex-start;
    border-radius: 1.5rem;
  }

  .dots-container.expanded::-webkit-scrollbar {
    width: 6px;
  }

  .dots-container.expanded::-webkit-scrollbar-track {
    background: transparent;
  }

  .dots-container.expanded::-webkit-scrollbar-thumb {
    background-color: rgba(148, 163, 184, 0.3);
    border-radius: 3px;
  }

  .dots-container.expanded::-webkit-scrollbar-thumb:hover {
    background-color: rgba(148, 163, 184, 0.5);
  }

  .dot-wrapper {
    display: contents;
  }

  /* Chapter dots - smaller than event dots */
  .dot.chapter-dot {
    width: calc(var(--dot-size) * 0.5);
    height: calc(var(--dot-size) * 0.5);
    min-width: calc(var(--dot-size) * 0.5);
    min-height: calc(var(--dot-size) * 0.5);
    padding: 0;
    background: transparent;
    border: none;
    flex: 0 0 auto; /* Ensure chapter dots don't shrink */
    transition:
      background-color 0.25s ease,
      transform 0.4s cubic-bezier(0.22, 1, 0.36, 1);
  }

  .dot-inner-chapter {
    width: 100%;
    height: 100%;
    border: none;
    background: rgba(148, 163, 184, 0.3);
    border-radius: 50%;
    transition:
      background-color 0.25s ease,
      transform 0.25s ease;
  }

  .dot.chapter-dot:hover .dot-inner-chapter {
    background: rgba(148, 163, 184, 0.5);
  }

  .dot.chapter-dot.active .dot-inner-chapter {
    background: var(--story-secondary, #38bdf8);
  }

  /* Conclusion dots - small square */
  .dot.conclusion-dot {
    width: calc(var(--dot-size) * 0.5);
    height: calc(var(--dot-size) * 0.5);
    min-width: calc(var(--dot-size) * 0.5);
    min-height: calc(var(--dot-size) * 0.5);
    padding: 0;
    background: transparent;
    border: none;
    flex: 0 0 auto;
    transition:
      background-color 0.25s ease,
      transform 0.4s cubic-bezier(0.22, 1, 0.36, 1);
  }

  .dot-inner-conclusion {
    width: 100%;
    height: 100%;
    border: none;
    background: rgba(148, 163, 184, 0.3);
    border-radius: 2px; /* Small rounded corners for square */
    transition:
      background-color 0.25s ease,
      transform 0.25s ease;
  }

  .dot.conclusion-dot:hover .dot-inner-conclusion {
    background: rgba(148, 163, 184, 0.5);
  }

  .dot.conclusion-dot.active .dot-inner-conclusion {
    background: var(--story-secondary, #38bdf8);
  }

  /* Conclusion item in expanded timeline */
  .timeline-item.conclusion-item {
    margin-top: 0.5rem;
    padding: 0.35rem 0.5rem;
    margin-right: -0.5rem;
    margin-left: -0.5rem;
    width: calc(100% + 1rem);
    border-radius: 0;
    cursor: pointer;
    transition: background-color 0.2s ease;
  }

  .timeline-item.conclusion-item:hover {
    background: rgba(148, 163, 184, 0.08);
  }

  .timeline-item.conclusion-item:focus {
    outline: 2px solid var(--story-primary, rgba(148, 163, 184, 0.4));
    outline-offset: 2px;
    background: rgba(148, 163, 184, 0.05);
  }

  .timeline-item.conclusion-item:focus:not(:focus-visible) {
    outline: none;
  }

  .timeline-item.home-item.conclusion-item .event-title {
    font-weight: 700;
    font-style: normal;
    letter-spacing: 0.05em;
  }

  .expanded-timeline-container {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    width: 100%;
    padding: 0.5rem 0.25rem 0.5rem 0.25rem;
    min-height: min-content;
    container-type: inline-size;
  }

  .timeline-item {
    --event-age: 0;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    width: calc(100% - var(--event-age) * (100cqw - 200px) / 100);
    opacity: 0;
    animation: fadeIn 0.4s ease forwards;
    margin-left: calc(var(--event-age) * (100cqw - 200px) / 100);
    position: relative;
  }

  .event-box {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex: 1;
    position: relative;
  }

  .age-line {
    position: absolute;
    right: 100%;
    height: 1px;
    background: linear-gradient(
      to left,
      rgba(148, 163, 184, 0.4) 0%,
      rgba(148, 163, 184, 0.15) 70%,
      transparent 100%
    );
    width: calc(var(--event-age) * (100cqw - 200px) / 100 - 0.5rem);
    pointer-events: none;
  }

  .event-metadata {
    display: flex;
    align-items: center;
    gap: 0.3rem;
    line-height: 1.2;
  }

  .metadata-separator {
    font-size: 0.6rem;
    color: rgba(148, 163, 184, 0.5);
    font-weight: 400;
  }

  .age-label {
    font-size: 0.7rem;
    color: rgba(148, 163, 184, 0.75);
    font-weight: 500;
    white-space: nowrap;
    font-family: var(--story-body-font, Inter, sans-serif);
    letter-spacing: 0.01em;
  }

  @container (max-width: 600px) {
    .age-label {
      font-size: 0.65rem;
    }

    .metadata-separator {
      font-size: 0.55rem;
    }
  }

  @container (max-width: 400px) {
    .age-label {
      font-size: 0.6rem;
    }

    .metadata-separator {
      font-size: 0.5rem;
    }
  }

  .timeline-item.clickable {
    cursor: pointer;
    padding: 0.35rem 0.5rem;
    margin-top: -0.35rem;
    margin-bottom: -0.35rem;
    margin-right: -0.5rem;
    margin-left: calc(var(--event-age) * (100cqw - 200px) / 100 - 0.5rem);
    width: calc(100% - var(--event-age) * (100cqw - 200px) / 100 + 1rem);
    border-radius: 0;
    transition: background-color 0.2s ease;
  }

  .timeline-item.clickable:hover {
    background: rgba(148, 163, 184, 0.08);
  }

  .timeline-item.clickable:focus {
    outline: 2px solid var(--story-primary, rgba(148, 163, 184, 0.4));
    outline-offset: 2px;
    background: rgba(148, 163, 184, 0.05);
  }

  .timeline-item.clickable:focus:not(:focus-visible) {
    outline: none;
  }

  @keyframes fadeIn {
    from {
      opacity: 0;
      transform: translateX(-10px);
    }
    to {
      opacity: 1;
      transform: translateX(0);
    }
  }

  .timeline-item:nth-child(1) {
    animation-delay: 0.1s;
  }
  .timeline-item:nth-child(2) {
    animation-delay: 0.15s;
  }
  .timeline-item:nth-child(3) {
    animation-delay: 0.2s;
  }
  .timeline-item:nth-child(4) {
    animation-delay: 0.25s;
  }
  .timeline-item:nth-child(5) {
    animation-delay: 0.3s;
  }
  .timeline-item:nth-child(n + 6) {
    animation-delay: 0.35s;
  }

  .timeline-content {
    display: flex;
    flex-direction: column;
    gap: 0.1rem;
    flex: 1;
    min-width: 0;
  }

  .event-title {
    font-size: 0.9rem;
    font-weight: 500;
    color: rgba(226, 232, 240, 0.95);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    line-height: 1.3;
    font-family: var(--story-body-font, Inter, sans-serif);
  }

  @container (max-width: 600px) {
    .event-title {
      font-size: 0.8rem;
    }
  }

  @container (max-width: 400px) {
    .event-title {
      font-size: 0.75rem;
    }
  }

  .timeline-item.home-item .event-title {
    font-weight: 600;
  }

  .chapter-header {
    --event-age: 0;
    display: flex;
    flex-direction: column;
    gap: 0.1rem;
    margin-top: 0.75rem;
    margin-bottom: 0.35rem;
    margin-left: calc(var(--event-age) * (100cqw - 200px) / 100);
    width: calc(100% - var(--event-age) * (100cqw - 200px) / 100);
    padding: 0.3rem 0 0.3rem 0.5rem;
    border-left: 2px solid var(--story-primary, rgba(148, 163, 184, 0.5));
    background: linear-gradient(
      to right,
      rgba(var(--primary-rgb, 94, 208, 255), 0.08) 0%,
      transparent 100%
    );
    position: relative;
  }

  .chapter-age-line {
    position: absolute;
    right: 100%;
    top: 50%;
    transform: translateY(-50%);
    height: 2px;
    background: linear-gradient(
      to left,
      var(--story-primary, rgba(148, 163, 184, 0.6)) 0%,
      rgba(148, 163, 184, 0.25) 70%,
      transparent 100%
    );
    width: calc(var(--event-age) * (100cqw - 200px) / 100 - 0.5rem);
    pointer-events: none;
  }

  .chapter-header.clickable {
    cursor: pointer;
    padding: 0.5rem 0.5rem 0.5rem 0.5rem;
    margin-top: calc(0.75rem - 0.2rem);
    margin-bottom: calc(0.35rem - 0.2rem);
    margin-right: -0.5rem;
    margin-left: calc(var(--event-age) * (100cqw - 200px) / 100 - 0.5rem);
    width: calc(100% - var(--event-age) * (100cqw - 200px) / 100 + 1rem);
    border-radius: 0;
    transition:
      background-color 0.2s ease,
      border-color 0.2s ease;
  }

  .chapter-header.clickable:hover {
    background: linear-gradient(
      to right,
      rgba(var(--primary-rgb, 94, 208, 255), 0.15) 0%,
      rgba(148, 163, 184, 0.06) 100%
    );
    border-left-color: var(--story-primary, rgba(148, 163, 184, 0.7));
  }

  .chapter-header.clickable:focus {
    outline: 2px solid var(--story-primary, rgba(148, 163, 184, 0.4));
    outline-offset: 2px;
    background: linear-gradient(
      to right,
      rgba(var(--primary-rgb, 94, 208, 255), 0.12) 0%,
      rgba(148, 163, 184, 0.05) 100%
    );
  }

  .chapter-header.clickable:focus:not(:focus-visible) {
    outline: none;
  }

  .chapter-header.clickable.active {
    background: linear-gradient(
      to right,
      rgba(var(--primary-rgb, 94, 208, 255), 0.2) 0%,
      rgba(148, 163, 184, 0.08) 100%
    );
    border-left-color: var(--story-secondary, #38bdf8);
    border-left-width: 3px;
  }

  .chapter-header:first-of-type {
    margin-top: 0.5rem;
  }

  .chapter-headline {
    font-size: 0.95rem;
    font-weight: 600;
    color: var(--story-primary, rgba(226, 232, 240, 0.95));
    margin: 0;
    line-height: 1.3;
    letter-spacing: 0.01em;
    font-family: var(--story-heading-font, Inter, sans-serif);
  }

  @container (max-width: 600px) {
    .chapter-headline {
      font-size: 0.85rem;
    }
  }

  @container (max-width: 400px) {
    .chapter-headline {
      font-size: 0.8rem;
    }
  }

  .chapter-meta {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
    margin-top: 0.25rem;
  }

  .chapter-meta-item {
    display: flex;
    align-items: flex-start;
    gap: 0.3rem;
    font-size: 0.75rem;
    color: var(--story-primary, rgba(226, 232, 240, 0.7));
    line-height: 1.4;
  }

  .chapter-meta-icon {
    width: 0.9rem;
    height: 0.9rem;
    fill: var(--story-primary, rgba(226, 232, 240, 0.6));
    flex-shrink: 0;
    margin-top: 0.1rem;
  }

  .chapter-meta-text {
    font-family: var(--story-body-font, Inter, sans-serif);
  }

  @container (max-width: 600px) {
    .chapter-meta {
      gap: 0.35rem 0.75rem;
    }

    .chapter-meta-item {
      font-size: 0.7rem;
    }

    .chapter-meta-icon {
      width: 0.8rem;
      height: 0.8rem;
    }
  }

  .nav-btn {
    pointer-events: auto;
    width: 2.8rem;
    height: 2.8rem;
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

  .dot {
    appearance: none;
    border: none;
    padding: 0;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    position: relative;
    width: var(--dot-size);
    height: var(--dot-size);
    border-radius: 9999px;
    background: rgba(148, 163, 184, 0.3);
    transition:
      background-color 0.25s ease,
      transform 0.4s cubic-bezier(0.22, 1, 0.36, 1);
    flex: 0 0 auto;
    pointer-events: all;
  }

  .dot.square {
    border-radius: 4px;
  }

  .dot.active {
    background: var(--story-secondary, #38bdf8);
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

  .event-year {
    font-size: 0.7rem;
    color: rgba(148, 163, 184, 0.85);
    font-weight: 500;
    white-space: nowrap;
    line-height: 1.2;
  }

  @container (max-width: 600px) {
    .event-year {
      font-size: 0.65rem;
    }
  }

  @container (max-width: 400px) {
    .event-year {
      font-size: 0.6rem;
    }
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

  /* Chapter indicator for collapsed timeline */
  .chapter-indicator-box {
    appearance: none;
    border: none;
    padding: 0;
    position: absolute;
    bottom: calc(100% + 0.25rem);
    left: calc(50% + var(--chapter-offset, 0%));
    transform: translateX(-50%);
    width: auto;
    max-width: min(90vw, 600px);
    pointer-events: auto;
    z-index: 10;
    cursor: pointer;
    background: transparent;
    transition: left 0.4s cubic-bezier(0.22, 1, 0.36, 1);
  }

  /* When no chapter and not showing event count, make it a compact icon-only button */
  .chapter-indicator-box:not(.has-chapter):not(.show-event-count)
    .chapter-indicator-content {
    padding: 0.6rem;
    border-radius: 50%;
    width: 3.25rem;
    height: 3.25rem;
  }

  .chapter-indicator-box:not(.has-chapter):not(.show-event-count)
    .chapter-chevron {
    width: 1.5rem;
    height: 1.5rem;
  }

  /* When showing event count on overview slide */
  .chapter-indicator-box.show-event-count .chapter-indicator-content {
    padding: 0.7rem 1.25rem;
    border-radius: 1rem;
  }

  .event-count-label {
    font-size: 0.85rem;
    font-weight: 600;
  }

  .chapter-indicator-content {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    padding: 0.7rem 1.25rem;
    border-radius: 1rem;
    background: rgba(15, 23, 42, 0.85);
    backdrop-filter: blur(8px);
    border: 1px solid var(--story-primary, rgba(148, 163, 184, 0.3));
    box-shadow: 0 4px 12px rgba(15, 23, 42, 0.3);
    transition:
      border-color 0.3s ease,
      box-shadow 0.3s ease,
      transform 0.2s ease;
  }

  .chapter-indicator-box:hover .chapter-indicator-content,
  .chapter-indicator-box:focus .chapter-indicator-content {
    border-color: var(--story-primary, rgba(148, 163, 184, 0.5));
    box-shadow: 0 6px 16px rgba(15, 23, 42, 0.4);
    transform: translateY(-2px);
  }

  .chapter-indicator-box:focus {
    outline: none;
  }

  .chapter-indicator-box:focus-visible .chapter-indicator-content {
    outline: 2px solid var(--story-primary, rgba(148, 163, 184, 0.6));
    outline-offset: 2px;
  }

  .chapter-indicator-label {
    font-size: 0.85rem;
    font-weight: 500;
    color: var(--story-primary, rgba(226, 232, 240, 0.95));
    text-align: center;
    line-height: 1.3;
    letter-spacing: 0.01em;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 100%;
    font-family: var(--story-heading-font, Inter, sans-serif);
  }

  .chapter-chevron {
    width: 1.1rem;
    height: 1.1rem;
    fill: var(--story-primary, rgba(226, 232, 240, 0.7));
    flex-shrink: 0;
    transition:
      transform 0.2s ease,
      fill 0.2s ease;
  }

  .chapter-indicator-box:hover .chapter-chevron,
  .chapter-indicator-box:focus .chapter-chevron {
    fill: var(--story-primary, rgba(226, 232, 240, 0.95));
    transform: translateY(-1px);
  }

  /* Responsive sizing */
  @media (max-width: 768px) {
    .chapter-indicator-label {
      font-size: 0.75rem;
    }

    .event-count-label {
      font-size: 0.75rem;
    }

    .chapter-indicator-content {
      padding: 0.4rem 0.85rem;
    }

    .chapter-chevron {
      width: 1rem;
      height: 1rem;
    }

    .chapter-indicator-box:not(.has-chapter):not(.show-event-count)
      .chapter-indicator-content {
      width: 3rem;
      height: 3rem;
      padding: 0.5rem;
    }

    .chapter-indicator-box:not(.has-chapter):not(.show-event-count)
      .chapter-chevron {
      width: 1.4rem;
      height: 1.4rem;
    }

    .chapter-indicator-box.show-event-count .chapter-indicator-content {
      padding: 0.4rem 0.85rem;
    }
  }

  @media (max-width: 480px) {
    .chapter-indicator-label {
      font-size: 0.7rem;
    }

    .event-count-label {
      font-size: 0.7rem;
    }

    .chapter-indicator-content {
      padding: 0.5rem 0.9rem;
      gap: 0.4rem;
    }

    .chapter-chevron {
      width: 0.95rem;
      height: 0.95rem;
    }

    .chapter-indicator-box:not(.has-chapter):not(.show-event-count)
      .chapter-indicator-content {
      width: 2.75rem;
      height: 2.75rem;
      padding: 0.45rem;
    }

    .chapter-indicator-box:not(.has-chapter):not(.show-event-count)
      .chapter-chevron {
      width: 1.1rem;
      height: 1.1rem;
    }

    .chapter-indicator-box.show-event-count .chapter-indicator-content {
      padding: 0.5rem 0.9rem;
    }
  }

  /* Landscape mobile optimizations - compact timeline for short viewports */
  @media (max-height: 450px) {
    .indicator {
      --dot-size: clamp(1rem, 2.5vw, 1.25rem);
      bottom: 0.35rem;
    }

    .indicator-track {
      padding: 0.4rem 0.6rem;
      border-radius: 1rem;
    }

    .nav-btn {
      width: 2.2rem;
      height: 2.2rem;
    }

    .chapter-indicator-box {
      bottom: calc(100% + 0.15rem);
    }

    .chapter-indicator-content {
      padding: 0.35rem 0.75rem;
      border-radius: 0.75rem;
    }

    .chapter-indicator-label {
      font-size: 0.65rem;
    }

    .chapter-chevron {
      width: 0.85rem;
      height: 0.85rem;
    }

    .chapter-indicator-box:not(.has-chapter):not(.show-event-count)
      .chapter-indicator-content {
      width: 2.25rem;
      height: 2.25rem;
      padding: 0.35rem;
    }

    .chapter-indicator-box:not(.has-chapter):not(.show-event-count)
      .chapter-chevron {
      width: 1rem;
      height: 1rem;
    }

    .chapter-indicator-box.show-event-count .chapter-indicator-content {
      padding: 0.35rem 0.75rem;
    }

    .event-count-label {
      font-size: 0.65rem;
    }
  }
</style>
