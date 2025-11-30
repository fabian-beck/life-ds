<script>
  import {
    mdiChevronLeft,
    mdiChevronRight,
    mdiHome,
    mdiChevronUp,
    mdiChevronDown,
  } from "@mdi/js";
  import { _ } from "../stores/language";
  import { fade } from "svelte/transition";

  export let activeIndex = 0;
  export let totalSlides = 0;
  export let activeEventIndex = -1;
  export let hasMultipleEvents = false;
  export let indicatorProgress = 0;
  export let indicatorIcons = [];
  export let eventSlides = []; // Array of event objects with titles
  export let chapters = []; // Array of chapter objects with headlines
  export let onPrevSlide = () => {};
  export let onNextSlide = () => {};
  export let onGoToEvent = () => {};
  export let onScrollToIndex = () => {};

  let isExpanded = false;
  let isDragging = false;
  let trackElement = null;
  let dragStartX = null;
  let expandedContainerElement = null;

  $: totalPanels = totalSlides > 0 ? totalSlides + 1 : 1; // +1 for overview slide
  $: hasEvents = totalSlides > 0;
  $: hasChapters = Array.isArray(chapters) && chapters.length > 0;

  // Group events by chapter for display
  $: groupedEvents = (() => {
    if (!hasChapters) {
      return [{ chapter: null, events: eventSlides.map((event, idx) => ({ ...event, originalIndex: idx })) }];
    }

    // Create a map of chapter IDs to chapter objects
    const chapterMap = new Map(chapters.map(ch => [ch.id, ch]));

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
            events: []
          });
        }
        groups.get(chapterId).events.push(eventWithIndex);
      } else {
        uncategorized.push(eventWithIndex);
      }
    });

    // Convert to array in chapter order
    const result = chapters
      .filter(ch => groups.has(ch.id))
      .map(ch => groups.get(ch.id));

    // Add uncategorized events at the end if any
    if (uncategorized.length > 0) {
      result.push({ chapter: null, events: uncategorized });
    }

    return result;
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
    const chapter = chapters.find(ch => ch.id === currentEvent.chapter);
    return chapter || null;
  })();

  // Scroll active event into view when first expanding (but allow manual scroll after)
  let hasScrolledToActive = false;
  $: if (isExpanded) {
    if (!hasScrolledToActive && expandedContainerElement && activeEventIndex >= 0) {
      // Use setTimeout to ensure DOM is ready after expansion animation
      setTimeout(() => {
        const activeElement = expandedContainerElement?.querySelector(`[data-event-index="${activeEventIndex}"]`);
        if (activeElement) {
          activeElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
          hasScrolledToActive = true;
        }
      }, 100);
    }
  } else {
    hasScrolledToActive = false;
  }

  function toggleExpanded() {
    isExpanded = !isExpanded;
  }

  function handleTrackPointerDown(event) {
    if (isExpanded || !trackElement) return;

    // Don't start dragging if clicking on the chapter indicator button
    if (event.target.closest(".chapter-indicator-box")) return;

    // Accept all pointer types (mouse, pen, touch)
    isDragging = true;
    dragStartX = event.clientX;
    trackElement.setPointerCapture(event.pointerId);
    updateSlideFromPosition(event.clientX);

    // Prevent event from bubbling to slides container
    event.stopPropagation();
  }

  function handleTrackPointerMove(event) {
    if (!isDragging) return;
    updateSlideFromPosition(event.clientX);
  }

  function handleTrackPointerUp(event) {
    if (!isDragging) return;
    isDragging = false;
    if (trackElement) {
      trackElement.releasePointerCapture(event.pointerId);
    }
    // Snap to the current active slide
    onScrollToIndex(activeIndex);
  }

  function updateSlideFromPosition(clientX) {
    if (!trackElement) return;
    const rect = trackElement.getBoundingClientRect();
    const x = clientX - rect.left;
    const progress = Math.max(0, Math.min(1, x / rect.width));
    const targetIndex = Math.round(progress * (totalPanels - 1));
    onScrollToIndex(targetIndex, true); // immediate scroll during drag
  }
</script>

{#if hasEvents}
  <div
    class="indicator"
    class:expanded={isExpanded}
    role="group"
    aria-label={$_('timeline.show_event', { index: activeEventIndex + 1, total: totalSlides })}
    style={`--indicator-progress: ${indicatorProgress}`}
  >
    <div class="indicator-content">
      {#if totalPanels > 1 && !isExpanded}
        <div class="indicator-nav">
          <button
            type="button"
            class="nav-btn prev"
            on:click={onPrevSlide}
            aria-label={$_('timeline.previous_slide')}
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
            aria-label={$_('timeline.next_slide')}
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
        class:dragging={isDragging}
        bind:this={trackElement}
        on:pointerdown={handleTrackPointerDown}
        on:pointermove={handleTrackPointerMove}
        on:pointerup={handleTrackPointerUp}
        on:pointercancel={handleTrackPointerUp}
        role="slider"
        aria-valuemin="0"
        aria-valuemax={totalPanels - 1}
        aria-valuenow={activeIndex}
        aria-label={$_('timeline.scrubber')}
        tabindex={isExpanded ? -1 : 0}
      >
        {#if isExpanded}
          <button
            type="button"
            class="collapse-button"
            on:click={toggleExpanded}
            aria-label={$_('timeline.collapse')}
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
        <div class="dots-container" class:expanded={isExpanded} bind:this={expandedContainerElement}>
          {#if activeIndex > 0 && !isExpanded}
            <span
              class="indicator-highlight"
              class:single={!hasMultipleEvents}
            />
          {/if}
          {#if !isExpanded}
            <div class="dot-wrapper home-dot">
              <button
                type="button"
                class="dot square"
                class:active={activeIndex === 0}
                on:click={() => onScrollToIndex(0)}
                aria-label={$_('timeline.show_overview')}
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
            {#each Array(totalSlides) as _, idx}
              <div class="dot-wrapper">
                <button
                  type="button"
                  class="dot"
                  class:active={idx === activeEventIndex}
                  on:click={() => onGoToEvent(idx)}
                  aria-label={`Show event ${idx + 1} of ${totalSlides}`}
                  aria-current={idx === activeEventIndex ? "true" : undefined}
                >
                  <svg
                    class="dot-icon"
                    viewBox="0 0 24 24"
                    role="img"
                    aria-hidden="true"
                  >
                    <path d={indicatorIcons[idx]} />
                  </svg>
                </button>
              </div>
            {/each}
            <button
              type="button"
              class="chapter-indicator-box"
              class:has-chapter={currentChapter}
              on:click={toggleExpanded}
              aria-label={currentChapter
                ? ($_('timeline.expand_to_chapter', { chapter: currentChapter.headline }) || `Expand timeline to ${currentChapter.headline}`)
                : (isExpanded ? $_('timeline.collapse') : $_('timeline.expand'))}
              aria-expanded={isExpanded}
            >
              <div class="chapter-indicator-content">
                {#if currentChapter}
                  <span class="chapter-indicator-label" transition:fade={{ duration: 300 }} key={currentChapter.id}>
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
            <div class="expanded-timeline-container">
              <div class="timeline-item home-item">
                <button
                  type="button"
                  class="dot square"
                  class:active={activeIndex === 0}
                  on:click={() => onScrollToIndex(0)}
                  aria-label={$_('timeline.show_overview')}
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
                <div class="timeline-content">
                  <span class="event-title">Overview</span>
                </div>
              </div>
              {#each groupedEvents as group, groupIndex}
                {#if group.chapter}
                  {@const chapterAge = group.chapter.age_start ?? 0}
                  <div class="chapter-header" style="--event-age: {chapterAge};">
                    <h3 class="chapter-headline">{group.chapter.headline}</h3>
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
                  <div class="timeline-item" data-event-index={idx} style="--event-age: {eventAge};">
                    <button
                      type="button"
                      class="dot"
                      class:active={idx === activeEventIndex}
                      on:click={() => onGoToEvent(idx)}
                      aria-label={`Show event ${idx + 1} of ${totalSlides}`}
                      aria-current={idx === activeEventIndex ? "true" : undefined}
                    >
                      <svg
                        class="dot-icon"
                        viewBox="0 0 24 24"
                        role="img"
                        aria-hidden="true"
                      >
                        <path d={indicatorIcons[idx]} />
                      </svg>
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
    transition: fill 0.2s ease, transform 0.2s ease;
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
    gap: 0.75rem;
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
    cursor: pointer;
    user-select: none;
    touch-action: manipulation; /* Allows default touch, disables double-tap zoom */
    transition:
      padding 1s cubic-bezier(0.22, 1, 0.36, 1),
      background 1s cubic-bezier(0.22, 1, 0.36, 1),
      height 1s cubic-bezier(0.22, 1, 0.36, 1);
  }

  .indicator-track.dragging {
    cursor: grabbing;
    background: rgba(15, 23, 42, 0.75);
  }

  .indicator-track:not(.expanded):hover {
    background: rgba(15, 23, 42, 0.7);
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
    justify-content: space-between;
    width: 100%;
    max-width: min(90vw, 860px);
    z-index: 2;
    transition:
      flex-direction 0.8s cubic-bezier(0.22, 1, 0.36, 1),
      gap 0.8s cubic-bezier(0.22, 1, 0.36, 1),
      justify-content 0.8s cubic-bezier(0.22, 1, 0.36, 1);
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
    transition: all 0.8s cubic-bezier(0.22, 1, 0.36, 1);
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
    width: 100%;
    opacity: 0;
    animation: fadeIn 0.4s ease forwards;
    padding-left: calc(var(--event-age) * (100cqw - 200px) / 100);
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

  .timeline-item:nth-child(1) { animation-delay: 0.1s; }
  .timeline-item:nth-child(2) { animation-delay: 0.15s; }
  .timeline-item:nth-child(3) { animation-delay: 0.2s; }
  .timeline-item:nth-child(4) { animation-delay: 0.25s; }
  .timeline-item:nth-child(5) { animation-delay: 0.3s; }
  .timeline-item:nth-child(n+6) { animation-delay: 0.35s; }

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

  .chapter-years {
    font-size: 0.7rem;
    color: rgba(148, 163, 184, 0.7);
    font-weight: 500;
    line-height: 1.2;
  }

  @container (max-width: 600px) {
    .chapter-years {
      font-size: 0.65rem;
    }
  }

  @container (max-width: 400px) {
    .chapter-years {
      font-size: 0.6rem;
    }
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
    border-radius: 4px;
    background: var(--story-secondary, rgba(56, 189, 248, 0.45));
    opacity: 0.45;
    transform: translateX(
        calc(var(--indicator-progress) * (100% - var(--dot-size)))
      )
      translateY(-50%);
    transition:
      transform 0.35s cubic-bezier(0.22, 1, 0.36, 1),
      background-color 0.3s ease,
      opacity 0.3s ease;
    z-index: 0;
    pointer-events: none;
  }

  .indicator.expanded .indicator-highlight {
    opacity: 0;
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
    pointer-events: all;
  }

  .indicator-track.dragging .dot {
    pointer-events: none;
  }

  .dot.square {
    border-radius: 4px;
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
    left: 50%;
    transform: translateX(-50%);
    width: auto;
    max-width: min(90vw, 600px);
    pointer-events: auto;
    z-index: 10;
    cursor: pointer;
    background: transparent;
  }

  /* When no chapter, make it a compact icon-only button */
  .chapter-indicator-box:not(.has-chapter) .chapter-indicator-content {
    padding: 0.45rem;
    border-radius: 50%;
    width: 2.5rem;
    height: 2.5rem;
  }

  .chapter-indicator-box:not(.has-chapter) .chapter-chevron {
    width: 1.3rem;
    height: 1.3rem;
  }

  .chapter-indicator-content {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    padding: 0.5rem 1rem;
    border-radius: 0.75rem;
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
  }

  .chapter-chevron {
    width: 1.1rem;
    height: 1.1rem;
    fill: var(--story-primary, rgba(226, 232, 240, 0.7));
    flex-shrink: 0;
    transition: transform 0.2s ease, fill 0.2s ease;
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
      width: 2.25rem;
      height: 2.25rem;
      padding: 0.4rem;
    }

    .chapter-indicator-box:not(.has-chapter) .chapter-chevron {
      width: 1.2rem;
      height: 1.2rem;
    }
  }

  @media (max-width: 480px) {
    .chapter-indicator-label {
      font-size: 0.7rem;
    }

    .chapter-indicator-content {
      padding: 0.35rem 0.75rem;
      gap: 0.4rem;
    }

    .chapter-chevron {
      width: 0.9rem;
      height: 0.9rem;
    }

    .chapter-indicator-box:not(.has-chapter) .chapter-indicator-content {
      width: 2rem;
      height: 2rem;
      padding: 0.35rem;
    }

    .chapter-indicator-box:not(.has-chapter) .chapter-chevron {
      width: 1.1rem;
      height: 1.1rem;
    }
  }
</style>
