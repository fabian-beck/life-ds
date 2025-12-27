<script>
  import { _ } from "../stores/language";
  import { push } from "svelte-spa-router";
  import { onMount, onDestroy } from "svelte";
  import MetaStoryTimeline from "./MetaStoryTimeline.svelte";

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
  let scrollSyncTimeout; // Debounce horizontal->vertical scroll sync
  let verticalScrollTimeout; // Throttle vertical->horizontal updates
  let lastTimelineScrollLeft = 0; // Track last known timeline scroll position

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
    if (isUpdatingScroll) return; // Prevent feedback loop

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
      const scrollProgress = Math.min(scrolledPastTop / proxyHeight, 1);

      // Apply to timeline horizontal scroll
      const maxTimelineScroll = actualTimelineContainer.scrollWidth - actualTimelineContainer.clientWidth;
      const newScrollLeft = scrollProgress * maxTimelineScroll;

      // Update timeline scroll directly without debouncing
      isUpdatingScroll = true;
      actualTimelineContainer.scrollLeft = newScrollLeft;
      lastTimelineScrollLeft = newScrollLeft; // Track expected position

      // Use requestAnimationFrame to reset flag
      requestAnimationFrame(() => {
        isUpdatingScroll = false;
      });
    } else {
      isScrollLockActive = false;
    }
  }

  // Handle horizontal timeline scroll and sync to vertical scroll position
  function handleTimelineScroll() {
    if (isUpdatingScroll) return; // Prevent feedback loop

    if (!scrollProxyContainer || !timelineContainer || proxyHeight === 0 || !isScrollLockActive) {
      return;
    }

    const actualTimelineContainer = timelineContainer.querySelector('.meta-timeline-container');
    if (!actualTimelineContainer) return;

    const currentScrollLeft = actualTimelineContainer.scrollLeft;

    // Only sync if scroll position changed from what we set programmatically
    // This means user is manually scrolling the timeline
    const scrollDiff = Math.abs(currentScrollLeft - lastTimelineScrollLeft);
    if (scrollDiff < 1) {
      // Scroll position matches our last update - this is from vertical scroll, not user input
      return;
    }

    // User is manually scrolling timeline, sync to vertical scroll
    clearTimeout(scrollSyncTimeout);
    scrollSyncTimeout = setTimeout(() => {
      const maxTimelineScroll = actualTimelineContainer.scrollWidth - actualTimelineContainer.clientWidth;
      const scrollProgress = maxTimelineScroll > 0 ? currentScrollLeft / maxTimelineScroll : 0;

      // Calculate target vertical scroll position
      const rect = scrollProxyContainer.getBoundingClientRect();
      const proxyContainerTop = rect.top + window.scrollY;
      const targetScrollY = proxyContainerTop + (scrollProgress * proxyHeight);

      // Update vertical scroll position
      isUpdatingScroll = true;
      lastTimelineScrollLeft = currentScrollLeft; // Update tracked position

      requestAnimationFrame(() => {
        window.scrollTo(0, targetScrollY);
        setTimeout(() => {
          isUpdatingScroll = false;
        }, 10);
      });
    }, 50); // Slightly longer debounce for manual scroll
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

  onMount(() => {
    window.addEventListener('scroll', handleVerticalScroll, { passive: true });
    window.addEventListener('resize', handleResize);

    // Attach scroll listener to actual timeline container for bidirectional sync
    if (timelineContainer) {
      const actualTimelineContainer = timelineContainer.querySelector('.meta-timeline-container');
      if (actualTimelineContainer) {
        actualTimelineContainer.addEventListener('scroll', handleTimelineScroll, { passive: true });
      }

      timelineContainer.addEventListener('wheel', preventNativeHorizontalScroll, { passive: false });
    }
  });

  onDestroy(() => {
    window.removeEventListener('scroll', handleVerticalScroll);
    window.removeEventListener('resize', handleResize);

    if (timelineContainer) {
      const actualTimelineContainer = timelineContainer.querySelector('.meta-timeline-container');
      if (actualTimelineContainer) {
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
                chapters={metaStoryData.chapters}
                personsRegistry={personsRegistry}
                onEventClick={viewPersonEvent}
                subtopics={metaStoryData.subtopics}
              />
            </div>
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

  /* Responsive */
  @media (max-width: 640px) {
    .meta-story-view {
      padding: 1rem;
    }

    h1 {
      font-size: 2rem;
    }
  }
</style>
