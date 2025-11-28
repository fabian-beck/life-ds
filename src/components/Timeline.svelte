<script>
  import {
    mdiChevronLeft,
    mdiChevronRight,
    mdiHome,
    mdiChevronUp,
    mdiChevronDown,
  } from "@mdi/js";

  export let activeIndex = 0;
  export let totalSlides = 0;
  export let activeEventIndex = -1;
  export let hasMultipleEvents = false;
  export let indicatorProgress = 0;
  export let indicatorIcons = [];
  export let eventSlides = []; // Array of event objects with titles
  export let onPrevSlide = () => {};
  export let onNextSlide = () => {};
  export let onGoToEvent = () => {};
  export let onScrollToIndex = () => {};

  let isExpanded = false;
  let isDragging = false;
  let trackElement = null;
  let dragStartX = null;

  $: totalPanels = totalSlides > 0 ? totalSlides + 1 : 1; // +1 for overview slide
  $: hasEvents = totalSlides > 0;

  function toggleExpanded() {
    isExpanded = !isExpanded;
  }

  function handleTrackPointerDown(event) {
    if (isExpanded || !trackElement) return;

    // Don't start dragging if clicking on the expand toggle button
    if (event.target.closest(".expand-toggle")) return;

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
    aria-label={`Event ${activeEventIndex + 1} of ${totalSlides}`}
    style={`--indicator-progress: ${indicatorProgress}`}
  >
    <div class="indicator-content">
      {#if totalPanels > 1 && !isExpanded}
        <div class="indicator-nav">
          <button
            type="button"
            class="nav-btn prev"
            on:click={onPrevSlide}
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
            on:click={onNextSlide}
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
        aria-label="Timeline scrubber"
        tabindex={isExpanded ? -1 : 0}
      >
        <button
          type="button"
          class="expand-toggle"
          on:click={toggleExpanded}
          aria-label={isExpanded ? "Collapse timeline" : "Expand timeline"}
          aria-expanded={isExpanded}
        >
          <svg
            class="icon"
            viewBox="0 0 24 24"
            role="presentation"
            aria-hidden="true"
          >
            <path d={isExpanded ? mdiChevronDown : mdiChevronUp} />
          </svg>
        </button>
        <div class="dots-container" class:expanded={isExpanded}>
          {#if activeIndex > 0 && !isExpanded}
            <span
              class="indicator-highlight"
              class:single={!hasMultipleEvents}
            />
          {/if}
          <div
            class="dot-wrapper home-dot"
            class:expanded={isExpanded}
            style={`--dot-x-pos: 0%`}
          >
            <button
              type="button"
              class="dot square"
              class:active={activeIndex === 0}
              on:click={() => onScrollToIndex(0)}
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
          </div>
          {#each Array(totalSlides) as _, idx}
            {@const eventTitle = eventSlides[idx]?.title || `Event ${idx + 1}`}
            {@const eventYear = eventSlides[idx]?.date
              ? eventSlides[idx].date.split("-")[0]
              : ""}
            {@const isFirstHalf = idx < totalSlides / 2}
            {@const totalItems = totalSlides + 1}
            {@const xPos = ((idx + 1) / (totalItems - 1)) * 100}
            <div
              class="dot-wrapper"
              class:expanded={isExpanded}
              style={`--dot-index: ${idx}; --total-dots: ${totalSlides}; --dot-x-pos: ${xPos}%`}
            >
              {#if isExpanded && eventYear}
                <span class="event-year">{eventYear}</span>
              {/if}
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
              {#if isExpanded}
                <span
                  class="event-label"
                  class:left={!isFirstHalf}
                  class:right={isFirstHalf}
                >
                  {eventTitle}
                </span>
              {/if}
            </div>
          {/each}
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

  .expand-toggle {
    pointer-events: auto;
    position: absolute;
    top: -2.3rem;
    left: 50%;
    transform: translateX(-50%);
    width: 2.8rem;
    height: 2.8rem;
    border-radius: 1.5rem 1.5rem 0.5rem 0.5rem;
    border: 1px solid rgba(148, 163, 184, 0.2);
    border-bottom: none;
    background: rgba(15, 23, 42, 0.65);
    backdrop-filter: blur(6px);
    color: var(--story-primary, #e2e8f0);
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    transition:
      background-color 0.2s ease,
      border-color 0.2s ease,
      transform 0.2s ease,
      top 1s cubic-bezier(0.22, 1, 0.36, 1);
    box-shadow: 0 10px 30px rgba(15, 23, 42, 0.25);
  }

  .indicator-track.expanded .expand-toggle {
    top: 1rem;
    border-radius: 1.5rem;
    border: 1px solid rgba(148, 163, 184, 0.2);
    z-index: 100;
  }

  .expand-toggle:hover,
  .expand-toggle:focus {
    background: rgba(15, 23, 42, 0.85);
    border-color: rgba(148, 163, 184, 0.3);
    transform: translateX(-50%) scale(1.05);
    outline: none;
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
    padding: 2rem 1.5rem;
    height: 100%;
    background: rgba(15, 23, 42, 0.85);
    overflow: hidden;
    position: relative;
  }

  .indicator-track.expanded::before,
  .indicator-track.expanded::after {
    content: "";
    position: absolute;
    top: 0;
    bottom: 0;
    width: 1rem;
    pointer-events: none;
    z-index: 10;
  }

  .indicator-track.expanded::before {
    left: 0;
    background: linear-gradient(
      to right,
      rgba(15, 23, 42, 0.85) 0%,
      rgba(15, 23, 42, 0.6) 40%,
      transparent 100%
    );
  }

  .indicator-track.expanded::after {
    right: 0;
    background: linear-gradient(
      to left,
      rgba(15, 23, 42, 0.85) 0%,
      rgba(15, 23, 42, 0.6) 40%,
      transparent 100%
    );
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
    flex-direction: column;
    align-items: flex-start;
    justify-content: flex-start;
    gap: 0;
    height: 100%;
    width: 100%;
  }

  .dot-wrapper {
    display: contents;
    transition: all 0.8s cubic-bezier(0.22, 1, 0.36, 1);
  }

  .dot-wrapper.home-dot.expanded {
    display: flex;
    align-items: center;
    position: absolute;
    left: var(--dot-x-pos, 0);
    top: 0;
    transform: translateX(calc(var(--dot-size) / -2));
  }

  .dot-wrapper.expanded {
    display: flex;
    align-items: center;
    gap: 0;
    width: auto;
    position: absolute;
    left: var(--dot-x-pos, 0);
    top: calc((100% / (var(--total-dots) + 1)) * (var(--dot-index) + 1));
    transform: translate(calc(var(--dot-size) / -2), -50%);
    transition:
      top 0.9s cubic-bezier(0.22, 1, 0.36, 1),
      left 0.9s cubic-bezier(0.22, 1, 0.36, 1),
      opacity 0.8s ease;
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

  .event-label {
    font-size: 0.8rem;
    color: rgba(226, 232, 240, 0.95);
    white-space: nowrap;
    opacity: 0;
    transition: opacity 0.4s ease 0.9s;
    pointer-events: none;
    font-weight: 500;
    max-width: 12rem;
    overflow: hidden;
    text-overflow: ellipsis;
    position: absolute;
  }

  .dot-wrapper.expanded .event-label {
    opacity: 1;
  }

  .event-label.right {
    left: calc(100% + 0.75rem);
    transform-origin: left center;
  }

  .event-label.left {
    right: calc(100% + 0.75rem);
    transform-origin: right center;
    text-align: right;
  }

  .event-year {
    position: absolute;
    top: calc(var(--dot-size) * -0.75);
    left: 50%;
    transform: translateX(-50%);
    font-size: 0.7rem;
    color: rgba(148, 163, 184, 0.85);
    font-weight: 500;
    white-space: nowrap;
    opacity: 0;
    transition: opacity 0.4s ease 0.9s;
    pointer-events: none;
  }

  .dot-wrapper.expanded .event-year {
    opacity: 1;
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
</style>
