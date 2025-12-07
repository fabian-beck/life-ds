<script>
  import {
    mdiChevronLeft,
    mdiChevronRight,
    mdiHome,
    mdiChevronUp,
    mdiChevronDown,
    mdiAccountOutline,
    mdiMapMarkerOutline,
  } from "@mdi/js";
  import { _ } from "../stores/language";
  import { fade } from "svelte/transition";
  import { createEventDispatcher } from "svelte";
  import * as mdiIcons from "@mdi/js";
  import PersonChip from "./PersonChip.svelte";
  import { getSubcategory } from "../utils/storyHelpers.js";

  export let activeIndex = 0;
  export let totalSlides = 0;
  export let activeEventIndex = -1;
  export let hasMultipleEvents = false;
  export let indicatorProgress = 0;
  export let indicatorIcons = []; // Fallback icons (deprecated, prefer event_type_icon in eventSlides)
  export let eventSlides = []; // Array of event objects with titles and event_type_icon
  export let chapters = []; // Array of chapter objects with headlines
  export let egoNetwork = null; // Ego network data for person lookups
  export let styleConfig = null; // Style configuration for person chips
  export let onPrevSlide = () => {};
  export let onNextSlide = () => {};
  export let onGoToEvent = () => {};
  export let onScrollToIndex = () => {};
  export let onOpenNetwork = null; // Callback to open network modal
  export let initialExpanded = false; // NEW: Initial expanded state from URL

  const dispatch = createEventDispatcher();

  let isExpanded = initialExpanded;
  let visiblePersonInfo = null; // Track which person chip popup is visible

  // Make isExpanded reactive to initialExpanded prop changes
  $: isExpanded = initialExpanded;

  // Toggle person info popup
  function handleTogglePersonInfo(personKey) {
    visiblePersonInfo = visiblePersonInfo === personKey ? null : personKey;
  }

  // Close popup when clicking outside or on scroll
  function handleContainerClick(event) {
    // Close popup if clicking outside a person chip
    if (visiblePersonInfo && !event.target.closest('.person-info-wrapper')) {
      visiblePersonInfo = null;
    }
  }

  // Close popup when scrolling
  function handleContainerScroll() {
    if (visiblePersonInfo) {
      visiblePersonInfo = null;
    }
  }

  // Find person data from egoNetwork by name
  function findPersonInNetwork(personName) {
    if (!egoNetwork?.connections || !personName) return null;

    const nameLower = personName.toLowerCase().trim();

    // Try exact match first
    let match = egoNetwork.connections.find(
      (conn) => conn.person_name?.toLowerCase() === nameLower
    );

    if (match) return match;

    // Try partial match (first name + last name substring)
    const nameParts = nameLower.split(/\s+/);
    if (nameParts.length >= 2) {
      const firstName = nameParts[0];
      const lastName = nameParts[nameParts.length - 1];

      match = egoNetwork.connections.find((conn) => {
        const connName = conn.person_name?.toLowerCase() || "";
        return connName.includes(firstName) && connName.includes(lastName);
      });
    }

    // Try last name only match
    if (!match && nameParts.length >= 1) {
      const lastName = nameParts[nameParts.length - 1];
      match = egoNetwork.connections.find((conn) => {
        const connName = conn.person_name?.toLowerCase() || "";
        const connParts = connName.split(/\s+/);
        const connLastName = connParts[connParts.length - 1];
        return connLastName === lastName;
      });
    }

    return match || null;
  }

  // Get people data for a chapter's involved_people list (only returns people found in network)
  function getChapterPeople(chapter) {
    if (!chapter?.involved_people || !Array.isArray(chapter.involved_people)) {
      return [];
    }

    // Only return people that can be matched to the ego network
    return chapter.involved_people
      .map((name, idx) => {
        const networkPerson = findPersonInNetwork(name);
        if (networkPerson) {
          return {
            ...networkPerson,
            _originalName: name,
            _index: idx,
          };
        }
        return null;
      })
      .filter(Boolean);
  }

  // Helper function to resolve MDI icon path from icon name (e.g., "mdi-home" -> mdiHome)
  function resolveIconPath(iconName) {
    if (!iconName || typeof iconName !== 'string') return null;

    // Convert mdi-icon-name to mdiIconName format
    const camelCase = iconName
      .replace(/^mdi-/, '') // Remove 'mdi-' prefix
      .split('-')
      .map((word, index) =>
        index === 0 ? word : word.charAt(0).toUpperCase() + word.slice(1)
      )
      .join('');

    const iconKey = 'mdi' + camelCase.charAt(0).toUpperCase() + camelCase.slice(1);
    return mdiIcons[iconKey] || null;
  }

  // Build icon array from event_type_icon in eventSlides, with fallback to indicatorIcons
  $: eventIcons = eventSlides.map((event, idx) => {
    if (event.event_type_icon) {
      const iconPath = resolveIconPath(event.event_type_icon);
      if (iconPath) return iconPath;
    }
    // Fallback to indicatorIcons if event_type_icon not available or invalid
    return indicatorIcons[idx] || null;
  });
  let trackElement = null;
  let expandedContainerElement = null;

  $: totalPanels = totalSlides > 0 ? totalSlides + 1 : 1; // +1 for overview slide
  $: hasEvents = totalSlides > 0;
  $: hasChapters = Array.isArray(chapters) && chapters.length > 0;

  // Lens-based magnification: calculate scale for each dot based on distance from active
  $: dotScales = (() => {
    if (isExpanded) return Array(totalSlides).fill(1.0);

    const scales = [];
    for (let i = 0; i < totalSlides; i++) {
      const distance = Math.abs(i - activeEventIndex);

      if (distance === 0 && activeEventIndex >= 0) {
        scales.push(1.6); // Active dot: 60% larger
      } else if (distance === 1) {
        scales.push(1.3); // Adjacent dots: 30% larger
      } else if (distance === 2) {
        scales.push(1.15); // Next adjacent: 15% larger
      } else {
        scales.push(1.0); // Normal size
      }
    }
    return scales;
  })();

  // Lens "pushing" effect: push adjacent dots outward slightly
  $: dotTranslations = (() => {
    if (isExpanded) return Array(totalSlides).fill(0);

    const translations = [];
    for (let i = 0; i < totalSlides; i++) {
      const distance = i - activeEventIndex;

      if (distance === 0) {
        translations.push(0); // Active stays centered
      } else if (Math.abs(distance) === 1) {
        translations.push(distance * 0.3); // Push adjacent 0.3rem away
      } else if (Math.abs(distance) === 2) {
        translations.push(distance * 0.15); // Push next adjacent 0.15rem away
      } else {
        translations.push(0); // Others stay in place
      }
    }
    return translations;
  })();

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
    const uncategorized = [];

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
        uncategorized.push(eventWithIndex);
      }
    });

    // Convert to array in chapter order
    const result = chapters
      .filter((ch) => groups.has(ch.id))
      .map((ch) => groups.get(ch.id));

    // Add uncategorized events at the end if any
    if (uncategorized.length > 0) {
      result.push({ chapter: null, events: uncategorized });
    }

    return result;
  })();

  // Build flat list of items with chapter spacers for collapsed timeline
  $: timelineItems = (() => {
    if (!hasChapters) {
      // No chapters: just return all events in order
      return eventSlides.map((event, idx) => ({ type: 'event', index: idx }));
    }

    const items = [];
    let lastChapterId = null;

    eventSlides.forEach((event, idx) => {
      const currentChapterId = event.chapter || null;

      // Insert spacer when chapter changes (but not at the very start)
      if (currentChapterId !== lastChapterId && items.length > 0) {
        items.push({ type: 'spacer', chapterId: currentChapterId });
      }

      items.push({ type: 'event', index: idx });
      lastChapterId = currentChapterId;
    });

    return items;
  })();

  // Compute current chapter for active event
  $: currentChapter = (() => {
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
    if (activeEventIndex < 0 || totalSlides === 0) {
      return 0; // Centered when on overview
    }

    // Calculate position as percentage (0 = first event, 1 = last event)
    const progress = activeEventIndex / (totalSlides - 1);

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
    isExpanded = !isExpanded;
    // Dispatch event to parent so it can update the URL
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
        bind:this={trackElement}
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
          on:scroll={handleContainerScroll}
        >
          {#if !isExpanded}
            <div class="dot-wrapper home-dot">
              <button
                type="button"
                class="dot square"
                class:active={activeIndex === 0}
                style="transform: scale({activeIndex === 0 ? 1.6 : (activeEventIndex === 0 ? 1.3 : 1.0)}); z-index: {activeIndex === 0 ? 16 : (activeEventIndex === 0 ? 13 : 10)};"
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
            <div class="chapter-spacer" aria-hidden="true"></div>
            {#each timelineItems as item, i}
              {#if item.type === 'spacer'}
                <div class="chapter-spacer" aria-hidden="true"></div>
              {:else if item.type === 'event'}
                {@const idx = item.index}
                <div class="dot-wrapper">
                  <button
                    type="button"
                    class="dot"
                    class:active={idx === activeEventIndex}
                    style="transform: scale({dotScales[idx]}) translateX({dotTranslations[idx]}rem); z-index: {Math.round(dotScales[idx] * 10)};"
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
                  <span
                    class="chapter-indicator-label"
                    transition:fade={{ duration: 300 }}
                    key={currentChapter.id}
                  >
                    {currentChapter.headline}
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
            <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
            <div class="expanded-timeline-container" on:click={handleContainerClick}>
              <div
                class="timeline-item home-item clickable"
                class:active={activeIndex === 0}
                role="button"
                tabindex="0"
                on:click={() => onScrollToIndex(0)}
                on:keydown={(e) => (e.key === 'Enter' || e.key === ' ') && onScrollToIndex(0)}
              >
                <button
                  type="button"
                  class="dot square"
                  class:active={activeIndex === 0}
                  style="transform: scale({activeIndex === 0 ? 1.4 : 1.0}); transition: transform 0.25s ease;"
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
              {#each groupedEvents as group, groupIndex}
                {#if group.chapter}
                  {@const chapterAge = group.chapter.age_start ?? 0}
                  {@const chapterPeople = getChapterPeople(group.chapter)}
                  {@const chapterLocation = group.chapter.location}
                  <div
                    class="chapter-header"
                    style="--event-age: {chapterAge};"
                  >
                    <h3 class="chapter-headline">{group.chapter.headline}</h3>
                    {#if chapterPeople.length > 0 || chapterLocation}
                      <div class="chapter-meta">
                        {#if chapterPeople.length > 0}
                          <div class="chapter-meta-item chapter-people">
                            <svg
                              class="chapter-meta-icon"
                              viewBox="0 0 24 24"
                              role="presentation"
                              aria-hidden="true"
                            >
                              <path d={mdiAccountOutline} />
                            </svg>
                            <div class="chapter-people-list">
                              {#each chapterPeople as person, personIdx}
                                {@const personKey = `chapter-${group.chapter.id}-${personIdx}`}
                                {@const subcategory = getSubcategory(person.relationship_type)}
                                <PersonChip
                                  {person}
                                  {personKey}
                                  {visiblePersonInfo}
                                  {subcategory}
                                  {styleConfig}
                                  onToggle={handleTogglePersonInfo}
                                  {onOpenNetwork}
                                  containerSelector=".expanded-timeline-container"
                                />
                              {/each}
                            </div>
                          </div>
                        {/if}
                        {#if chapterLocation}
                          <div class="chapter-meta-item">
                            <svg
                              class="chapter-meta-icon"
                              viewBox="0 0 24 24"
                              role="presentation"
                              aria-hidden="true"
                            >
                              <path d={mdiMapMarkerOutline} />
                            </svg>
                            <span class="chapter-meta-text">{chapterLocation}</span>
                          </div>
                        {/if}
                      </div>
                    {/if}
                  </div>
                {:else if groupIndex > 0}
                  <div class="chapter-header">
                    <h3 class="chapter-headline">Other Events</h3>
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
                    on:keydown={(e) => (e.key === 'Enter' || e.key === ' ') && onGoToEvent(idx)}
                  >
                    <button
                      type="button"
                      class="dot"
                      class:active={idx === activeEventIndex}
                      style="transform: scale({idx === activeEventIndex ? 1.4 : 1.0}); transition: transform 0.25s ease;"
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
                      {#if eventYear}
                        <span class="event-year">{eventYear}</span>
                      {/if}
                      <span class="event-title">{eventTitle}</span>
                    </div>
                  </div>
                {/each}
              {/each}
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
    .dots-container:not(.expanded) .dot:not(.square) {
      margin-left: -0.3rem;
    }
    .dots-container:not(.expanded) .chapter-spacer {
      margin-left: -0.3rem;
      width: calc(var(--dot-size) * 0.7);
    }
  }

  @media (max-width: 480px) {
    .dots-container:not(.expanded) .dot:not(.square) {
      margin-left: -0.5rem;
    }
    .dots-container:not(.expanded) .chapter-spacer {
      margin-left: -0.5rem;
      width: calc(var(--dot-size) * 0.5);
    }
  }

  @media (max-width: 380px) {
    .dots-container:not(.expanded) .dot:not(.square) {
      margin-left: -0.7rem;
    }
    .dots-container:not(.expanded) .chapter-spacer {
      margin-left: -0.7rem;
      width: calc(var(--dot-size) * 0.3);
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

  /* Chapter spacer for visual clustering */
  .chapter-spacer {
    width: var(--dot-size);
    flex: 0 0 auto;
    pointer-events: none;
    opacity: 0;
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
  }

  .timeline-item.clickable {
    cursor: pointer;
    padding: 0.35rem 0.5rem;
    margin-top: -0.35rem;
    margin-bottom: -0.35rem;
    margin-right: -0.5rem;
    margin-left: calc(var(--event-age) * (100cqw - 200px) / 100 - 0.5rem);
    width: calc(100% - var(--event-age) * (100cqw - 200px) / 100 + 0.5rem);
    border-radius: 0.5rem;
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

  .chapter-people {
    align-items: center;
  }

  .chapter-people .chapter-meta-icon {
    margin-top: 0;
  }

  .chapter-people-list {
    display: flex;
    flex-wrap: wrap;
    gap: 0.25rem;
    align-items: center;
  }

  /* PersonChip styling within chapter headers */
  .chapter-people-list :global(.person-info-wrapper) {
    display: inline-flex;
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

  /* When no chapter, make it a compact icon-only button */
  .chapter-indicator-box:not(.has-chapter) .chapter-indicator-content {
    padding: 0.6rem;
    border-radius: 50%;
    width: 3.25rem;
    height: 3.25rem;
  }

  .chapter-indicator-box:not(.has-chapter) .chapter-chevron {
    width: 1.5rem;
    height: 1.5rem;
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

    .chapter-indicator-content {
      padding: 0.4rem 0.85rem;
    }

    .chapter-chevron {
      width: 1rem;
      height: 1rem;
    }

    .chapter-indicator-box:not(.has-chapter) .chapter-indicator-content {
      width: 3rem;
      height: 3rem;
      padding: 0.5rem;
    }

    .chapter-indicator-box:not(.has-chapter) .chapter-chevron {
      width: 1.4rem;
      height: 1.4rem;
    }
  }

  @media (max-width: 480px) {
    .chapter-indicator-label {
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

    .chapter-indicator-box:not(.has-chapter) .chapter-indicator-content {
      width: 2.75rem;
      height: 2.75rem;
      padding: 0.45rem;
    }

    .chapter-indicator-box:not(.has-chapter) .chapter-chevron {
      width: 1.1rem;
      height: 1.1rem;
    }
  }
</style>
