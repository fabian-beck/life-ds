<script>
  import { _ } from "../stores/language";
  import { push } from "svelte-spa-router";
  import { onMount, onDestroy } from "svelte";
  import MetaStoryTimeline from "./MetaStoryTimeline.svelte";
  import { mdiChevronLeft, mdiChevronRight } from '@mdi/js';

  export let metaStoryData = null;
  export let personsRegistry = [];
  export let currentLanguage = "en";
  export let getStyle = () => ({});
  export let isLoading = false;

  // Scroll proxy variables
  let scrollProxyContainer;
  let timelineContainer;
  let proxyHeight = 0;
  let isScrollLockActive = false;
  let resizeTimeout;
  let isUpdatingScroll = false; // Prevent infinite scroll loops
  let lastTimelineScrollLeft = 0; // Track last known timeline scroll position
  let scrollProgress = 0; // 0 to 1, current scroll position for timeline indicator
  let lastScrollOrigin = null; // Track origin of last scroll: 'vertical' | 'horizontal' | null
  let timelineScrollListenerAttached = false; // Track if listener is attached

  // Navigate to person's story at specific event
  function viewPersonEvent(personId, eventIndex) {
    push(`/${currentLanguage}/story/${personId}?slide=${eventIndex}`);
  }

  // Navigate back to landing
  function backToLanding() {
    push(`/${currentLanguage}`);
  }

  // Calculate proxy height based on timeline's horizontal scroll distance
  $: if (timelineContainer && metaStoryData?.chapters?.length) {
    // Use requestAnimationFrame to ensure DOM is updated
    requestAnimationFrame(() => {
      calculateProxyHeight();
    });
  }

  // Attach scroll listener to timeline after it renders
  $: if (timelineContainer && !timelineScrollListenerAttached) {
    // Use setTimeout to ensure MetaStoryTimeline has rendered its DOM
    setTimeout(() => {
      // Check if timelineContainer still exists (component might have been destroyed)
      if (!timelineContainer) return;

      const actualTimelineContainer = timelineContainer.querySelector('.meta-timeline-container');
      if (actualTimelineContainer) {
        actualTimelineContainer.addEventListener('scroll', handleTimelineScroll, { passive: true });
        timelineScrollListenerAttached = true;
      }
    }, 100);
  }

  function calculateProxyHeight() {
    if (!timelineContainer) {
      return;
    }

    // Find the actual scrollable .meta-timeline-container inside MetaStoryTimeline
    const actualTimelineContainer = timelineContainer.querySelector('.meta-timeline-container');

    if (!actualTimelineContainer) {
      return;
    }

    const scrollWidth = actualTimelineContainer.scrollWidth;
    const clientWidth = actualTimelineContainer.clientWidth;
    proxyHeight = Math.max(scrollWidth - clientWidth, 0);
  }

  // Handle vertical scroll and translate to horizontal timeline scroll
  function handleVerticalScroll() {
    // Only skip if the last update came from horizontal scroll or navigation
    if (isUpdatingScroll && (lastScrollOrigin === 'horizontal' || lastScrollOrigin === 'navigation')) return;

    if (!scrollProxyContainer || !timelineContainer || proxyHeight === 0) {
      return;
    }

    // Find the actual scrollable container
    const actualTimelineContainer = timelineContainer.querySelector('.meta-timeline-container');
    if (!actualTimelineContainer) return;

    const rect = scrollProxyContainer.getBoundingClientRect();
    const containerTop = rect.top;
    const containerBottom = rect.bottom;
    const viewportHeight = window.innerHeight;

    // Check if we're in the scroll-lock zone
    // Lock activates when container top reaches viewport top
    if (containerTop <= 0 && containerBottom > viewportHeight) {
      isScrollLockActive = true;

      // Calculate scroll progress (0 to 1)
      const scrolledPastTop = Math.abs(containerTop);
      const currentScrollProgress = Math.min(scrolledPastTop / proxyHeight, 1);
      scrollProgress = currentScrollProgress; // Update for scroll indicator

      // Apply to timeline horizontal scroll
      const maxTimelineScroll = actualTimelineContainer.scrollWidth - actualTimelineContainer.clientWidth;
      const newScrollLeft = currentScrollProgress * maxTimelineScroll;

      // Update timeline scroll directly without debouncing
      isUpdatingScroll = true;
      lastScrollOrigin = 'vertical'; // Track that this update came from vertical scroll
      actualTimelineContainer.scrollLeft = newScrollLeft;
      lastTimelineScrollLeft = newScrollLeft; // Track expected position

      // Use consistent timing for flag reset
      requestAnimationFrame(() => {
        isUpdatingScroll = false;
      });
    } else {
      isScrollLockActive = false;
      // Update scroll progress based on actual timeline scroll when not in lock zone
      if (actualTimelineContainer) {
        const maxTimelineScroll = actualTimelineContainer.scrollWidth - actualTimelineContainer.clientWidth;
        scrollProgress = maxTimelineScroll > 0 ? actualTimelineContainer.scrollLeft / maxTimelineScroll : 0;
      }
    }
  }

  // Handle horizontal timeline scroll and sync to vertical scroll position
  function handleTimelineScroll() {
    // Only skip if the last update came from vertical scroll or navigation
    if (isUpdatingScroll && (lastScrollOrigin === 'vertical' || lastScrollOrigin === 'navigation')) return;

    if (!scrollProxyContainer || !timelineContainer || proxyHeight === 0) {
      return;
    }

    const actualTimelineContainer = timelineContainer.querySelector('.meta-timeline-container');
    if (!actualTimelineContainer) return;

    const currentScrollLeft = actualTimelineContainer.scrollLeft;

    // Only sync if scroll position changed from what we set programmatically
    // This means user is manually scrolling the timeline
    const scrollDiff = Math.abs(currentScrollLeft - lastTimelineScrollLeft);

    if (scrollDiff < 2) {
      // Scroll position matches our last update (within 2px for sub-pixel rendering tolerance)
      // This is likely from vertical scroll, not user input
      // Update lastTimelineScrollLeft to prevent drift
      lastTimelineScrollLeft = currentScrollLeft;
      return;
    }

    // User is manually scrolling timeline, sync to vertical scroll immediately for smooth momentum
    const maxTimelineScroll = actualTimelineContainer.scrollWidth - actualTimelineContainer.clientWidth;
    const currentScrollProgress = maxTimelineScroll > 0 ? currentScrollLeft / maxTimelineScroll : 0;
    scrollProgress = currentScrollProgress; // Update for scroll indicator

    // Calculate target vertical scroll position
    const rect = scrollProxyContainer.getBoundingClientRect();
    const proxyContainerTop = rect.top + window.scrollY;
    const targetScrollY = proxyContainerTop + (currentScrollProgress * proxyHeight);

    // Set flag BEFORE scrolling to prevent any feedback
    isUpdatingScroll = true;
    lastScrollOrigin = 'horizontal'; // Track that this update came from horizontal scroll
    lastTimelineScrollLeft = currentScrollLeft; // Update tracked position

    // Use scrollTo with instant behavior to avoid animation delays
    window.scrollTo({
      top: targetScrollY,
      left: 0,
      behavior: 'instant'
    });

    // Reset flag after a brief delay to ensure scroll event has been processed
    setTimeout(() => {
      isUpdatingScroll = false;
    }, 50);
  }

  // Handle window resize
  function handleResize() {
    clearTimeout(resizeTimeout);
    resizeTimeout = setTimeout(() => {
      calculateProxyHeight();
    }, 150);
  }

  // Prevent native horizontal scroll during scroll lock
  function preventNativeHorizontalScroll(event) {
    if (isScrollLockActive && Math.abs(event.deltaX) > 0) {
      // Only prevent horizontal scroll input during scroll lock
      event.preventDefault();
    }
  }

  // Reference to MetaStoryTimeline component
  let metaTimelineComponent;

  // Navigation state
  let canNavigatePrev = false;
  let canNavigateNext = false;
  let navigationTimeout = null;

  // Update navigation button states based on current position
  // This reactive statement re-runs whenever scrollProgress changes,
  // ensuring button states update during manual scrolling
  $: if (metaTimelineComponent && scrollProgress !== undefined) {
    canNavigatePrev = metaTimelineComponent.getPrevYear?.() !== null;
    canNavigateNext = metaTimelineComponent.getNextYear?.() !== null;
  }

  function handleNextYear() {
    if (!metaTimelineComponent) return;

    const nextYear = metaTimelineComponent.getNextYear?.();
    if (nextYear === null) return;

    const targetScrollProgress = metaTimelineComponent.yearToScrollProgress?.(nextYear);
    if (targetScrollProgress === null) return;

    navigateToScrollProgress(targetScrollProgress);
  }

  function handlePrevYear() {
    if (!metaTimelineComponent) return;

    const prevYear = metaTimelineComponent.getPrevYear?.();
    if (prevYear === null) return;

    const targetScrollProgress = metaTimelineComponent.yearToScrollProgress?.(prevYear);
    if (targetScrollProgress === null) return;

    navigateToScrollProgress(targetScrollProgress);
  }

  function navigateToScrollProgress(targetScrollProgress) {
    if (!scrollProxyContainer || !timelineContainer) return;

    // Cancel any in-progress navigation
    if (navigationTimeout !== null) {
      clearTimeout(navigationTimeout);
      navigationTimeout = null;
    }

    // Find the actual timeline container
    const actualTimelineContainer = timelineContainer.querySelector('.meta-timeline-container');
    if (!actualTimelineContainer) return;

    // Calculate target vertical scroll position
    const rect = scrollProxyContainer.getBoundingClientRect();
    const proxyContainerTop = rect.top + window.scrollY;
    const targetScrollY = proxyContainerTop + (targetScrollProgress * proxyHeight);

    // Calculate target horizontal scroll position for timeline
    const maxTimelineScroll = actualTimelineContainer.scrollWidth - actualTimelineContainer.clientWidth;
    const targetScrollLeft = targetScrollProgress * maxTimelineScroll;

    // Set flag to prevent feedback loops
    isUpdatingScroll = true;
    lastScrollOrigin = 'navigation';

    // Update scroll progress and timeline horizontal scroll immediately for visual feedback
    scrollProgress = targetScrollProgress;
    actualTimelineContainer.scrollLeft = targetScrollLeft;
    lastTimelineScrollLeft = targetScrollLeft;

    // Smooth scroll vertically to target year
    window.scrollTo({
      top: targetScrollY,
      left: 0,
      behavior: 'smooth'
    });

    // Reset flag after smooth scroll completes (~500ms)
    navigationTimeout = setTimeout(() => {
      isUpdatingScroll = false;
      lastScrollOrigin = null;
      navigationTimeout = null;
    }, 500);
  }

  // Keyboard shortcuts for timeline navigation
  function handleMetaTimelineKeydown(event) {
    // Only active when meta story data is loaded
    if (!metaStoryData || !timelineContainer) return;

    // Don't intercept when typing in input fields
    const activeElement = document.activeElement;
    if (activeElement?.tagName === 'INPUT' ||
        activeElement?.tagName === 'TEXTAREA' ||
        activeElement?.isContentEditable) {
      return;
    }

    if (event.key === 'ArrowLeft') {
      event.preventDefault();
      event.stopPropagation();
      handlePrevYear();
    } else if (event.key === 'ArrowRight') {
      event.preventDefault();
      event.stopPropagation();
      handleNextYear();
    }
  }

  onMount(() => {
    window.addEventListener('keydown', handleMetaTimelineKeydown);
    window.addEventListener('scroll', handleVerticalScroll, { passive: true });
    window.addEventListener('resize', handleResize);

    // Timeline scroll listener is now attached reactively (see reactive statement above)
    // Wheel listener for preventing native horizontal scroll
    if (timelineContainer) {
      timelineContainer.addEventListener('wheel', preventNativeHorizontalScroll, { passive: false });
    }
  });

  onDestroy(() => {
    window.removeEventListener('keydown', handleMetaTimelineKeydown);
    window.removeEventListener('scroll', handleVerticalScroll);
    window.removeEventListener('resize', handleResize);

    if (timelineContainer) {
      const actualTimelineContainer = timelineContainer.querySelector('.meta-timeline-container');
      if (actualTimelineContainer && timelineScrollListenerAttached) {
        actualTimelineContainer.removeEventListener('scroll', handleTimelineScroll);
      }
      timelineContainer.removeEventListener('wheel', preventNativeHorizontalScroll);
    }
  });
</script>

<!-- Loading state -->
{#if isLoading}
  <div class="loading">Loading meta story...</div>
{:else if metaStoryData}
  <div class="meta-story-view">
    <!-- Header section -->
    <header class="meta-story-header">
      <button on:click={backToLanding} class="back-button">
        ← {$_('meta_story.back_to_stories')}
      </button>
      <h1>{metaStoryData.meta_story.title}</h1>
      <p class="tagline">{metaStoryData.meta_story.tagline}</p>
      <p class="date-range">
        {$_('meta_story.date_range', {
          start: metaStoryData.meta_story.date_range_start,
          end: metaStoryData.meta_story.date_range_end
        })}
      </p>
      <p class="description">{metaStoryData.meta_story.description}</p>
    </header>

    <!-- Chapters section - scroll proxy container for horizontal scroll lock -->
    {#if metaStoryData.chapters?.length}
      <section class="chapters-section">
        <h2>{$_('meta_story.chapters_heading')}</h2>

        <div
          class="scroll-proxy-container"
          bind:this={scrollProxyContainer}
          style="height: {proxyHeight + (typeof window !== 'undefined' ? window.innerHeight : 800)}px;"
        >
          <div class="timeline-sticky-wrapper">
            <div class="timeline-horizontal-container" bind:this={timelineContainer}>
              <MetaStoryTimeline
                bind:this={metaTimelineComponent}
                chapters={metaStoryData.chapters}
                personsRegistry={personsRegistry}
                onEventClick={viewPersonEvent}
                subtopics={metaStoryData.subtopics}
                scrollProgress={scrollProgress}
              />
            </div>

            <!-- Timeline navigation buttons - only show when in scroll lock zone -->
            {#if metaTimelineComponent && isScrollLockActive && (canNavigatePrev || canNavigateNext)}
              <button
                type="button"
                class="timeline-nav-btn prev"
                on:click={handlePrevYear}
                disabled={!canNavigatePrev}
                aria-label={$_('meta_story.prev_year')}
              >
                <svg class="icon" viewBox="0 0 24 24" aria-hidden="true">
                  <path d={mdiChevronLeft} />
                </svg>
              </button>

              <button
                type="button"
                class="timeline-nav-btn next"
                on:click={handleNextYear}
                disabled={!canNavigateNext}
                aria-label={$_('meta_story.next_year')}
              >
                <svg class="icon" viewBox="0 0 24 24" aria-hidden="true">
                  <path d={mdiChevronRight} />
                </svg>
              </button>
            {/if}
          </div>
        </div>
      </section>
    {/if}

    <!-- Conclusion section -->
    {#if metaStoryData.conclusion}
      <section class="conclusion">
        <h2>{$_('meta_story.conclusion_heading')}</h2>
        <p>{metaStoryData.conclusion}</p>
      </section>
    {/if}
  </div>
{/if}

<style>
  /* Container */
  .meta-story-view {
    max-width: 800px;
    margin: 0 auto;
    padding: 2rem 1rem;
    font-family: var(--body-font, 'IBM Plex Sans', sans-serif);
  }

  /* Header */
  .meta-story-header {
    margin-bottom: 3rem;
  }

  .back-button {
    background: rgba(56, 189, 248, 0.1);
    color: #38bdf8;
    border: 1px solid rgba(56, 189, 248, 0.3);
    padding: 0.5rem 1rem;
    border-radius: 0.5rem;
    cursor: pointer;
    margin-bottom: 1.5rem;
  }

  .back-button:hover {
    background: rgba(56, 189, 248, 0.2);
    border-color: rgba(56, 189, 248, 0.5);
  }

  h1 {
    font-family: var(--heading-font, 'Space Grotesk', sans-serif);
    font-size: 2.5rem;
    margin-bottom: 0.5rem;
  }

  .tagline {
    font-size: 1.25rem;
    color: #38bdf8;
    margin-bottom: 0.5rem;
  }

  .date-range {
    color: #94a3b8;
    margin-bottom: 1.5rem;
  }

  .description {
    line-height: 1.7;
    color: #cbd5e1;
  }

  /* Sections */
  section {
    margin-bottom: 3rem;
  }

  h2 {
    font-family: var(--heading-font, 'Space Grotesk', sans-serif);
    font-size: 1.875rem;
    margin-bottom: 1.5rem;
    border-bottom: 2px solid rgba(56, 189, 248, 0.3);
    padding-bottom: 0.5rem;
  }

  /* Chapters section - wrapper for heading and scroll proxy */
  .chapters-section {
    margin-bottom: 3rem;
  }

  /* Scroll proxy container - tall container for vertical scroll -> horizontal scroll translation */
  .scroll-proxy-container {
    position: relative;
    width: 100vw;
    margin-left: calc(-50vw + 50%);
    /* Height set dynamically via inline style */
  }

  /* Timeline wrapper - sticks to top during scroll lock */
  .timeline-sticky-wrapper {
    position: sticky;
    top: 0;
    height: 100vh;
    overflow: hidden;
    z-index: 50;
  }

  /* Timeline horizontal scroll container */
  .timeline-horizontal-container {
    height: 100vh;
    overflow-x: auto;
    overflow-y: hidden;
    overscroll-behavior-x: none;
    -webkit-overflow-scrolling: touch;
  }

  /* Hide scrollbar but keep scrollable */
  .timeline-horizontal-container::-webkit-scrollbar {
    display: none;
  }

  .timeline-horizontal-container {
    scrollbar-width: none;
  }

  /* Conclusion */
  .conclusion p {
    font-size: 1.125rem;
    line-height: 1.8;
    color: #cbd5e1;
    font-style: italic;
  }

  /* Loading state */
  .loading {
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 100vh;
    font-size: 1.25rem;
    color: #94a3b8;
  }

  /* Timeline navigation buttons */
  .timeline-nav-btn {
    position: fixed;
    top: 50%;
    transform: translateY(-50%);
    width: 2.8rem;
    height: 2.8rem;
    border-radius: 999px;
    border: 1px solid rgba(148, 163, 184, 0.35);
    background: rgba(15, 23, 42, 0.65);
    backdrop-filter: blur(6px);
    color: #e2e8f0;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    z-index: 60; /* Above timeline (z-index: 50), below modals (z-index: 10000) */
    transition:
      background-color 0.2s ease,
      border-color 0.2s ease,
      transform 0.2s ease;
  }

  .timeline-nav-btn.prev {
    left: 1rem;
  }

  .timeline-nav-btn.next {
    right: 1rem;
  }

  .timeline-nav-btn:hover:not(:disabled),
  .timeline-nav-btn:focus:not(:disabled) {
    background: rgba(15, 23, 42, 0.85);
    border-color: rgba(148, 163, 184, 0.6);
    transform: translateY(-50%) scale(1.05);
    outline: none;
  }

  .timeline-nav-btn:disabled {
    opacity: 0.35;
    cursor: not-allowed;
    transform: translateY(-50%);
  }

  .timeline-nav-btn .icon {
    width: 1.5rem;
    height: 1.5rem;
    fill: currentColor;
  }

  /* Responsive */
  @media (max-width: 768px) {
    .timeline-nav-btn {
      width: 2.5rem;
      height: 2.5rem;
    }

    .timeline-nav-btn.prev {
      left: 0.5rem;
    }

    .timeline-nav-btn.next {
      right: 0.5rem;
    }

    .timeline-nav-btn .icon {
      width: 1.3rem;
      height: 1.3rem;
    }
  }

  @media (max-height: 500px) {
    .timeline-nav-btn {
      width: 2.2rem;
      height: 2.2rem;
    }
  }

  @media (max-width: 640px) {
    .meta-story-view {
      padding: 1rem;
    }

    h1 {
      font-size: 2rem;
    }
  }
</style>
