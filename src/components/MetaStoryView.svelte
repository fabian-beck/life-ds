<script>
  import { _ } from "../stores/language";
  import { push } from "svelte-spa-router";
  import { onMount, onDestroy } from "svelte";
  import { fade } from "svelte/transition";
  import MetaStoryTimeline from "./MetaStoryTimeline.svelte";
  import MetaStoryFigure from "./MetaStoryFigure.svelte";
  import CloseButton from "./CloseButton.svelte";
  import AIGeneratedButton from "./AIGeneratedButton.svelte";
  import AIDisclaimerModal from "./AIDisclaimerModal.svelte";
  import { consumeMetaStoryScroll } from "../stores/metaStoryScroll.js";
  import { mdiChevronLeft, mdiChevronRight } from "@mdi/js";

  export let metaStoryData = null;
  export let personsRegistry = [];
  export let currentLanguage = "en";
  export let isLoading = false;

  // Scroll proxy variables
  const MIN_PROXY_HEIGHT = 1500; // Minimum vertical scroll distance (px) to traverse any timeline
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
  let scrollRestoreHandled = false; // Whether the remembered scroll position has been applied

  // Navigate back to landing
  function backToLanding() {
    push(`/${currentLanguage}`);
  }

  // Composed cold open (Phase 7): split into paragraphs for rendering
  $: openingParagraphs = metaStoryData?.opening?.text
    ? metaStoryData.opening.text.split(/\n\s*\n/).filter((p) => p.trim())
    : [];

  // Composed story-specific section headings, falling back to generic labels
  $: sectionHeadings = metaStoryData?.section_headings || {};
  $: sectionImages = metaStoryData?.section_images || {};

  // Calculate proxy height based on timeline's horizontal scroll distance
  $: if (timelineContainer && metaStoryData?.chapters?.length) {
    // Use requestAnimationFrame to ensure DOM is updated
    requestAnimationFrame(() => {
      calculateProxyHeight();
    });
  }

  // Once the timeline is laid out (proxy container is tall enough to scroll),
  // restore the scroll position the reader left from when opening a person's
  // story. Runs at most once per mount; a fresh visit has nothing stored.
  $: if (!scrollRestoreHandled && proxyHeight > 0 && metaStoryData) {
    restoreScrollPosition();
  }

  function restoreScrollPosition() {
    scrollRestoreHandled = true;
    const metaStoryId = metaStoryData?.meta_story?.id;
    const savedScrollY = consumeMetaStoryScroll(metaStoryId);
    if (savedScrollY == null || savedScrollY <= 0) return;

    // The scroll-proxy container height depends on proxyHeight, which may still
    // be growing as the timeline finishes measuring. Retry across a few frames
    // until the page is tall enough to reach the saved offset, then let the
    // window scroll handler translate it back into horizontal timeline scroll.
    let attempts = 0;
    const applyScroll = () => {
      const maxScroll =
        document.documentElement.scrollHeight - window.innerHeight;
      window.scrollTo(0, Math.min(savedScrollY, Math.max(maxScroll, 0)));
      if (maxScroll < savedScrollY && attempts < 12) {
        attempts += 1;
        requestAnimationFrame(applyScroll);
      }
    };
    requestAnimationFrame(applyScroll);
  }

  // Attach scroll listener to timeline after it renders
  $: if (timelineContainer && !timelineScrollListenerAttached) {
    // Use setTimeout to ensure MetaStoryTimeline has rendered its DOM
    setTimeout(() => {
      // Check if timelineContainer still exists (component might have been destroyed)
      if (!timelineContainer) return;

      const actualTimelineContainer = timelineContainer.querySelector(
        ".meta-timeline-container"
      );
      if (actualTimelineContainer) {
        actualTimelineContainer.addEventListener(
          "scroll",
          handleTimelineScroll,
          { passive: true }
        );
        timelineScrollListenerAttached = true;
      }
    }, 100);
  }

  function calculateProxyHeight() {
    if (!timelineContainer) {
      return;
    }

    // Find the actual scrollable .meta-timeline-container inside MetaStoryTimeline
    const actualTimelineContainer = timelineContainer.querySelector(
      ".meta-timeline-container"
    );

    if (!actualTimelineContainer) {
      return;
    }

    const scrollWidth = actualTimelineContainer.scrollWidth;
    const clientWidth = actualTimelineContainer.clientWidth;
    const rawProxyHeight = Math.max(scrollWidth - clientWidth, 0);
    proxyHeight = Math.max(rawProxyHeight, MIN_PROXY_HEIGHT);
  }

  // Handle vertical scroll and translate to horizontal timeline scroll
  function handleVerticalScroll() {
    // Update sticky header visibility
    handleHeaderVisibility();

    // Only skip if the last update came from horizontal scroll or navigation
    if (
      isUpdatingScroll &&
      (lastScrollOrigin === "horizontal" || lastScrollOrigin === "navigation")
    )
      return;

    if (!scrollProxyContainer || !timelineContainer || proxyHeight === 0) {
      return;
    }

    // Find the actual scrollable container
    const actualTimelineContainer = timelineContainer.querySelector(
      ".meta-timeline-container"
    );
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
      const maxTimelineScroll =
        actualTimelineContainer.scrollWidth -
        actualTimelineContainer.clientWidth;
      const newScrollLeft = currentScrollProgress * maxTimelineScroll;

      // Update timeline scroll directly without debouncing
      isUpdatingScroll = true;
      lastScrollOrigin = "vertical"; // Track that this update came from vertical scroll
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
        const maxTimelineScroll =
          actualTimelineContainer.scrollWidth -
          actualTimelineContainer.clientWidth;
        scrollProgress =
          maxTimelineScroll > 0
            ? actualTimelineContainer.scrollLeft / maxTimelineScroll
            : 0;
      }
    }
  }

  // Handle horizontal timeline scroll and sync to vertical scroll position
  function handleTimelineScroll() {
    // Only skip if the last update came from vertical scroll or navigation
    if (
      isUpdatingScroll &&
      (lastScrollOrigin === "vertical" || lastScrollOrigin === "navigation")
    )
      return;

    if (!scrollProxyContainer || !timelineContainer || proxyHeight === 0) {
      return;
    }

    const actualTimelineContainer = timelineContainer.querySelector(
      ".meta-timeline-container"
    );
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
    const maxTimelineScroll =
      actualTimelineContainer.scrollWidth - actualTimelineContainer.clientWidth;
    const currentScrollProgress =
      maxTimelineScroll > 0 ? currentScrollLeft / maxTimelineScroll : 0;
    scrollProgress = currentScrollProgress; // Update for scroll indicator

    // Calculate target vertical scroll position
    const rect = scrollProxyContainer.getBoundingClientRect();
    const proxyContainerTop = rect.top + window.scrollY;
    const targetScrollY =
      proxyContainerTop + currentScrollProgress * proxyHeight;

    // Set flag BEFORE scrolling to prevent any feedback
    isUpdatingScroll = true;
    lastScrollOrigin = "horizontal"; // Track that this update came from horizontal scroll
    lastTimelineScrollLeft = currentScrollLeft; // Update tracked position

    // Use scrollTo with instant behavior to avoid animation delays
    window.scrollTo({
      top: targetScrollY,
      left: 0,
      behavior: "instant",
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

  // Sticky header state
  let showStickyHeader = false;
  const headerScrollThreshold = 300; // pixels scrolled before showing sticky header
  let stickyHeaderElement = null;
  let stickyHeaderHeight = 0;

  // AI disclaimer modal state
  let showAIModal = false;

  function openAIModal() {
    showAIModal = true;
  }

  function closeAIModal() {
    showAIModal = false;
  }

  // Handle sticky header visibility based on scroll position
  function handleHeaderVisibility() {
    const scrollY = window.scrollY;
    showStickyHeader = scrollY > headerScrollThreshold;
  }

  // Update sticky header height when it appears/changes
  $: if (stickyHeaderElement && showStickyHeader) {
    stickyHeaderHeight = stickyHeaderElement.offsetHeight;
    // Update CSS custom property for AI button positioning
    if (typeof document !== "undefined") {
      document.documentElement.style.setProperty(
        "--sticky-header-height",
        `${stickyHeaderHeight}px`
      );
    }
  } else {
    stickyHeaderHeight = 0;
    if (typeof document !== "undefined") {
      document.documentElement.style.setProperty(
        "--sticky-header-height",
        "0px"
      );
    }
  }

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

    const targetScrollProgress =
      metaTimelineComponent.yearToScrollProgress?.(nextYear);
    if (targetScrollProgress === null) return;

    navigateToScrollProgress(targetScrollProgress);
  }

  function handlePrevYear() {
    if (!metaTimelineComponent) return;

    const prevYear = metaTimelineComponent.getPrevYear?.();
    if (prevYear === null) return;

    const targetScrollProgress =
      metaTimelineComponent.yearToScrollProgress?.(prevYear);
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
    const actualTimelineContainer = timelineContainer.querySelector(
      ".meta-timeline-container"
    );
    if (!actualTimelineContainer) return;

    // Calculate target vertical scroll position
    const rect = scrollProxyContainer.getBoundingClientRect();
    const proxyContainerTop = rect.top + window.scrollY;
    const targetScrollY =
      proxyContainerTop + targetScrollProgress * proxyHeight;

    // Calculate target horizontal scroll position for timeline
    const maxTimelineScroll =
      actualTimelineContainer.scrollWidth - actualTimelineContainer.clientWidth;
    const targetScrollLeft = targetScrollProgress * maxTimelineScroll;

    // Set flag to prevent feedback loops
    isUpdatingScroll = true;
    lastScrollOrigin = "navigation";

    // Update scroll progress and timeline horizontal scroll immediately for visual feedback
    scrollProgress = targetScrollProgress;
    actualTimelineContainer.scrollLeft = targetScrollLeft;
    lastTimelineScrollLeft = targetScrollLeft;

    // Smooth scroll vertically to target year
    window.scrollTo({
      top: targetScrollY,
      left: 0,
      behavior: "smooth",
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
    if (
      activeElement?.tagName === "INPUT" ||
      activeElement?.tagName === "TEXTAREA" ||
      activeElement?.isContentEditable
    ) {
      return;
    }

    if (event.key === "ArrowLeft") {
      event.preventDefault();
      event.stopPropagation();
      handlePrevYear();
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      event.stopPropagation();
      handleNextYear();
    }
  }

  onMount(() => {
    window.addEventListener("keydown", handleMetaTimelineKeydown);
    window.addEventListener("scroll", handleVerticalScroll, { passive: true });
    window.addEventListener("resize", handleResize);

    // Timeline scroll listener is now attached reactively (see reactive statement above)
    // Wheel listener for preventing native horizontal scroll
    if (timelineContainer) {
      timelineContainer.addEventListener(
        "wheel",
        preventNativeHorizontalScroll,
        { passive: false }
      );
    }
  });

  onDestroy(() => {
    window.removeEventListener("keydown", handleMetaTimelineKeydown);
    window.removeEventListener("scroll", handleVerticalScroll);
    window.removeEventListener("resize", handleResize);

    if (timelineContainer) {
      const actualTimelineContainer = timelineContainer.querySelector(
        ".meta-timeline-container"
      );
      if (actualTimelineContainer && timelineScrollListenerAttached) {
        actualTimelineContainer.removeEventListener(
          "scroll",
          handleTimelineScroll
        );
      }
      timelineContainer.removeEventListener(
        "wheel",
        preventNativeHorizontalScroll
      );
    }
  });
</script>

<!-- Loading state -->
{#if isLoading}
  <div class="loading">Loading meta story...</div>
{:else if metaStoryData}
  <div class="meta-story-view">
    <!-- Sticky header - appears when scrolling down -->
    {#if showStickyHeader}
      <div class="sticky-header-group" transition:fade={{ duration: 200 }}>
        <header class="meta-sticky-header" bind:this={stickyHeaderElement}>
          <div class="sticky-compact-info">
            <span class="sticky-name">{metaStoryData.meta_story.title}</span>
            <span class="separator">·</span>
            <span class="sticky-years">
              {metaStoryData.meta_story.date_range_start}–{metaStoryData
                .meta_story.date_range_end}
            </span>
            <CloseButton
              variant="light"
              size="responsive"
              ariaLabel={$_("meta_story.back_to_stories")}
              on:click={backToLanding}
              class="close-meta-story"
            />
          </div>
        </header>
        <!-- AI button positioned below sticky header -->
        <div class="sticky-ai-button">
          <AIGeneratedButton variant="small" onClick={openAIModal} />
        </div>
      </div>
    {/if}

    <!-- Header section -->
    <header class="meta-story-header">
      <div class="header-controls">
        <div class="header-ai-button">
          <AIGeneratedButton variant="large" onClick={openAIModal} />
        </div>
        <CloseButton
          variant="light"
          size="medium"
          position="absolute"
          ariaLabel={$_("meta_story.back_to_stories")}
          on:click={backToLanding}
        />
      </div>
      <h1>{metaStoryData.meta_story.title}</h1>
      <p class="tagline">{metaStoryData.meta_story.tagline}</p>
      <p class="date-range">
        {$_("meta_story.date_range", {
          start: metaStoryData.meta_story.date_range_start,
          end: metaStoryData.meta_story.date_range_end,
        })}
      </p>
      {#if openingParagraphs.length}
        <div class="opening">
          <MetaStoryFigure
            image={metaStoryData.opening.image}
            variant="opening"
          />
          {#each openingParagraphs as paragraph}
            <p class="opening-text">{paragraph}</p>
          {/each}
        </div>
      {/if}
      <p class="description">{metaStoryData.meta_story.description}</p>
    </header>

    <!-- Chapters section - scroll proxy container for horizontal scroll lock -->
    {#if metaStoryData.chapters?.length}
      <section class="chapters-section">
        <h2>{sectionHeadings.timeline || $_("meta_story.chapters_heading")}</h2>
        {#if metaStoryData.timeline_intro}
          <p class="timeline-intro">{metaStoryData.timeline_intro}</p>
        {/if}
        <MetaStoryFigure image={sectionImages.timeline} />

        <div
          class="scroll-proxy-container"
          bind:this={scrollProxyContainer}
          style="height: {proxyHeight +
            (typeof window !== 'undefined' ? window.innerHeight : 800)}px;"
        >
          <div
            class="timeline-sticky-wrapper"
            style="top: {stickyHeaderHeight}px;"
          >
            <div
              class="timeline-horizontal-container"
              bind:this={timelineContainer}
            >
              <MetaStoryTimeline
                bind:this={metaTimelineComponent}
                metaStoryId={metaStoryData.meta_story.id}
                chapters={metaStoryData.chapters}
                {personsRegistry}
                subtopics={metaStoryData.subtopics}
                {scrollProgress}
                isSticky={isScrollLockActive}
                {stickyHeaderHeight}
              />
            </div>

            <!-- Timeline navigation buttons - only show when in scroll lock zone -->
            {#if metaTimelineComponent && isScrollLockActive && (canNavigatePrev || canNavigateNext)}
              <button
                type="button"
                class="timeline-nav-btn prev"
                on:click={handlePrevYear}
                disabled={!canNavigatePrev}
                aria-label={$_("meta_story.prev_year")}
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
                aria-label={$_("meta_story.next_year")}
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

    <!-- Social network section - follows the timeline -->
    {#if metaStoryData.social_network?.links?.length}
      <section class="network-section">
        <h2>{sectionHeadings.network || $_("meta_story.network_heading")}</h2>
        <p class="network-intro">
          {metaStoryData.social_network?.narration?.intro ||
            $_("meta_story.network_subtitle")}
        </p>
        <MetaStoryFigure image={sectionImages.network} />
        {#await import("./MetaStoryNetwork.svelte") then { default: MetaStoryNetwork }}
          <MetaStoryNetwork
            network={metaStoryData.social_network}
            metaStoryId={metaStoryData.meta_story.id}
            {currentLanguage}
          />
        {/await}
      </section>
    {/if}

    <!-- Conclusion section -->
    {#if metaStoryData.conclusion}
      <section class="conclusion">
        <h2>
          {sectionHeadings.conclusion || $_("meta_story.conclusion_heading")}
        </h2>
        <MetaStoryFigure image={sectionImages.conclusion} />
        <p>{metaStoryData.conclusion}</p>
      </section>
    {/if}
  </div>
{/if}

<AIDisclaimerModal show={showAIModal} onClose={closeAIModal} />

<style>
  /* Container */
  .meta-story-view {
    max-width: 800px;
    margin: 0 auto;
    padding: 2rem 1rem;
    font-family: var(--body-font, "IBM Plex Sans", sans-serif);

    /* Editorial type palette — one ink, one body tone, one muted tone, one
       accent. Every text style below draws from these four so the story reads
       as a single typographic system instead of a stack of ad-hoc sizes and
       colors. Conventions borrowed from print editing: display font for
       headline and subheads, everything else in the body face at one size;
       the accent (drop cap, links, hairline) is used sparingly. */
    --ms-ink: #e8edf4; /* headline + subheads */
    --ms-body: #cbd5e1; /* all running prose */
    --ms-muted: #94a3b8; /* dateline, standfirsts, captions */
    --ms-accent: #38bdf8; /* drop cap, links, hairline — sparingly */

    color: var(--ms-body);
    line-height: 1.75;
  }

  /* Sticky header group - wrapper for synchronized fade transition */
  .sticky-header-group {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    z-index: 150; /* Above timeline chapter header (100) */
    pointer-events: none;
  }

  .sticky-header-group > * {
    pointer-events: auto;
  }

  /* Sticky header - appears when scrolling down, styled like StoryView masthead */
  .meta-sticky-header {
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
      rgba(15, 23, 42, 0.58);
    backdrop-filter: blur(12px);
    border-bottom: 1px solid rgba(148, 163, 184, 0.16);
  }

  .sticky-ai-button {
    position: absolute;
    top: calc(var(--sticky-header-height, 3.5rem) - 0.35rem);
    left: -0.25rem;
    z-index: -1; /* Below sticky header */
  }

  .sticky-compact-info {
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

  .sticky-compact-info span {
    min-width: 0;
  }

  .sticky-name {
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

  .sticky-name::-webkit-scrollbar {
    display: none;
  }

  .sticky-compact-info .separator {
    color: rgba(148, 163, 184, 0.8);
    flex: 0 0 auto;
  }

  .sticky-years {
    color: #94a3b8;
    font-weight: 500;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  /* Header */
  .meta-story-header {
    position: relative;
    margin-bottom: 3rem;
  }

  .header-controls {
    position: relative;
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 1rem;
  }

  .header-ai-button {
    margin-right: auto;
  }

  h1 {
    font-family: var(--heading-font, "Space Grotesk", sans-serif);
    font-size: 2.5rem;
    line-height: 1.15;
    color: var(--ms-ink);
    margin-bottom: 0.5rem;
  }

  /* Deck / standfirst — the story's one-line summary. Set in the body face at
     a muted tone rather than the accent color, so the headline and the drop
     cap stay the loudest elements on the page (editorial convention). */
  .tagline {
    font-size: 1.25rem;
    font-weight: 400;
    line-height: 1.4;
    color: var(--ms-muted);
    margin-bottom: 0.75rem;
  }

  /* Dateline — small, uppercase, letter-spaced like a print kicker. */
  .date-range {
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--ms-muted);
    margin-bottom: 1.5rem;
  }

  /* Composed cold open — visually leads before the wider description */
  .opening {
    margin-bottom: 1.5rem;
  }

  /* Contain the floated opening figure (see MetaStoryFigure) */
  .opening::after {
    content: "";
    display: table;
    clear: both;
  }

  /* Running prose — the cold open, the description and the conclusion are all
     the same body copy: one size, one tone, one measure. The only thing that
     sets the opening apart is the raised initial. */
  .opening-text,
  .description {
    font-size: 1.0625rem;
    line-height: 1.75;
    color: var(--ms-body);
    margin-bottom: 1rem;
  }

  /* Raised initial rather than a floated drop cap: a floated cap reserves
     only the glyph's own width, so narrow letters ("In 1911...", "It...")
     read as a stray vertical rule and leave the wrapped lines indented
     against nothing. Raising the letter is glyph-width independent. */
  .opening-text:first-of-type::first-letter {
    font-family: var(--heading-font, "Space Grotesk", sans-serif);
    font-size: 1.9em;
    line-height: 1;
    padding-right: 0.06em;
    color: var(--ms-accent);
  }

  /* Sections */
  section {
    margin-bottom: 3rem;
  }

  /* Subheads — one step down from the headline, closed off with a neutral
     hairline rather than a colored rule so the accent stays reserved for the
     drop cap and links. */
  h2 {
    font-family: var(--heading-font, "Space Grotesk", sans-serif);
    font-size: 1.5rem;
    font-weight: 600;
    color: var(--ms-ink);
    margin-bottom: 1.25rem;
    border-bottom: 1px solid rgba(148, 163, 184, 0.25);
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

  /* Timeline wrapper - sticks to top during scroll lock (top position set dynamically) */
  .timeline-sticky-wrapper {
    position: sticky;
    /* top is set dynamically via inline style to account for sticky header */
    height: 100vh;
    overflow: visible; /* Changed from hidden to allow tooltips to overflow */
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

  /* Social network */
  .network-section {
    margin-bottom: 3rem;
  }

  /* Section standfirsts — the intro line under a subhead. Body size, muted
     tone, held to a comfortable measure so they read as secondary to the copy
     that follows. */
  .network-intro,
  .timeline-intro {
    font-size: 1.0625rem;
    color: var(--ms-muted);
    line-height: 1.7;
    margin-bottom: 1.25rem;
    max-width: 62ch;
  }

  /* Conclusion — the same body copy as the rest of the article; its own
     subhead already sets it apart, so it needs no italic or size shift. */
  .conclusion p {
    font-size: 1.0625rem;
    line-height: 1.75;
    color: var(--ms-body);
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
    bottom: 2rem;
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
    transform: scale(1.05);
    outline: none;
  }

  .timeline-nav-btn:disabled {
    opacity: 0.35;
    cursor: not-allowed;
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

  /* Landscape mobile - compact sticky header on right side */
  @media (max-height: 450px) {
    .sticky-header-group {
      /* Extend to full height for landscape mobile so AI button can be at bottom */
      bottom: 0;
    }

    .meta-sticky-header {
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
      background: rgba(15, 23, 42, 0.5);
      backdrop-filter: blur(8px);
      z-index: 10;
      gap: 0.35rem;
    }

    .sticky-ai-button {
      /* Position directly below the ultra-compact header on the right */
      position: absolute;
      top: 1.4rem; /* Just below the compact header (~20px header height + small gap) */
      right: 0;
      left: auto;
      bottom: auto;
      z-index: 5;
    }

    /* Timeline should not reserve vertical space for header (header is on right) */
    .timeline-sticky-wrapper {
      top: 0 !important;
    }

    .sticky-compact-info {
      font-size: 0.65rem;
      gap: 0.35rem;
      justify-content: flex-end;
    }

    .sticky-name {
      max-width: 8rem;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .sticky-years {
      display: none;
    }

    .sticky-compact-info .separator {
      display: none;
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
