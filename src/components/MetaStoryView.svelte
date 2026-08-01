<script>
  import { _ } from "../stores/language";
  import { replace } from "svelte-spa-router";
  import { onMount, onDestroy } from "svelte";
  import { fade } from "svelte/transition";
  import MetaStoryTimeline from "./MetaStoryTimeline.svelte";
  import MetaStoryBody from "./MetaStoryBody.svelte";
  import MetaStoryOrnament from "./MetaStoryOrnament.svelte";
  import PersonCard from "./PersonCard.svelte";
  import ImageViewer from "./ImageViewer.svelte";
  import CloseButton from "./CloseButton.svelte";
  import AIGeneratedButton from "./AIGeneratedButton.svelte";
  import AIDisclaimerModal from "./AIDisclaimerModal.svelte";
  import {
    consumeMetaStoryScroll,
    saveMetaStoryScroll,
  } from "../stores/metaStoryScroll.js";
  import { queryParams, originQuery } from "../stores/queryParams.js";
  import { restoreFocusTrigger } from "../stores/returnFocus.js";
  import { displayName } from "../utils/helpers.js";
  import {
    metaStoryStyle,
    metaStoryStyleVars,
  } from "../utils/metaStoryStyles.js";
  import { mdiChevronLeft, mdiChevronRight } from "@mdi/js";
  import personStylesData from "../../data/person_styles.json";

  export let metaStoryData = null;
  export let personsRegistry = [];
  export let currentLanguage = "en";
  export let isLoading = false;

  const personStyles = personStylesData.styles;

  // The story's own visual identity — colors, fonts, and the SVG marks that
  // punctuate its prose. Language-independent, so the same entry serves every
  // translation. Stories without one keep the neutral editorial palette the
  // stylesheet declares as fallbacks, and render no ornaments.
  $: storyStyle = metaStoryStyle(metaStoryData?.meta_story?.id);
  $: storyStyleVars = metaStoryStyleVars(storyStyle);

  // The story's own people — those with an individual story — resolved to
  // { id, name, aliases, color } so their names can be emphasized and linked
  // wherever they appear in the story's prose. The registry supplies the name
  // in the reader's language, while the social network's main nodes keep the
  // original-language name (graph data is never translated); both are offered
  // to the matcher, because a translated story mixes them — the prose says
  // "Heinrich II." while the graph still says "Henry II". Colors come from
  // each person's story style. Only people present in the registry (i.e. with
  // an individual story) are kept.
  $: storyPeople = buildStoryPeople(metaStoryData, personsRegistry);

  // Same names keyed by id, for the components that build their own people
  // lists out of untranslated technical data (network nodes, map events).
  $: personAliases = Object.fromEntries(
    storyPeople.map((person) => [person.id, [person.name, ...person.aliases]])
  );

  function buildStoryPeople(data, registry) {
    const ids = data?.meta_story?.person_ids;
    if (!ids?.length) return [];
    const nodeNames = new Map(
      (data.social_network?.nodes || [])
        .filter((n) => n.type === "main")
        .map((n) => [n.id, n.name])
    );
    const registered = new Map((registry || []).map((p) => [p.id, p.name]));
    const clean = (name) => (name || "").replace(/_/g, " ").trim();
    return ids
      .filter((id) => registered.has(id))
      .map((id) => {
        const names = [clean(registered.get(id)), clean(nodeNames.get(id))]
          .filter(Boolean)
          .filter((name, index, all) => all.indexOf(name) === index);
        return {
          id,
          name: names[0] || id,
          aliases: names.slice(1),
          color: personStyles[id]?.primary || "#38bdf8",
        };
      });
  }

  // Everyone the story is built from, resolved to full registry entries so the
  // closing cards can show portrait, lifespan and roles (the same card the end
  // of an individual story uses for related people). Ordered chronologically by
  // birth date, like the rest of the story. People without an individual story
  // are skipped — a card whose only purpose is to open a story needs one.
  $: storyPersonCards = buildPersonCards(metaStoryData, personsRegistry);

  function buildPersonCards(data, registry) {
    const ids = data?.meta_story?.person_ids;
    if (!ids?.length) return [];
    const byId = new Map((registry || []).map((p) => [p.id, p]));
    return ids
      .map((id) => byId.get(id))
      .filter(Boolean)
      .sort(
        (a, b) =>
          birthYear(a) - birthYear(b) ||
          displayName(a.name).localeCompare(displayName(b.name))
      );
  }

  // Leading year of an ISO-ish birth date ("1815-12-10"); people without one
  // sort last rather than jumping to the front of the list.
  function birthYear(person) {
    const year = Number.parseInt(String(person?.birthDate ?? ""), 10);
    return Number.isFinite(year) ? year : Number.POSITIVE_INFINITY;
  }

  // PersonCard expects the normalized (camelCase) style shape App.svelte builds;
  // the raw registry carries everything a card needs, so map it here.
  function cardStyle(personId) {
    const raw = personStyles[personId];
    if (!raw) return null;
    return {
      primary: raw.primary,
      secondary: raw.secondary,
      headingFont: raw.heading_font,
      bodyFont: raw.body_font,
    };
  }

  // Carry the meta story context so the story's close button returns here, and
  // the landing filters with it so the way out of the collection is unchanged.
  function personStoryHref(personId) {
    const search = originQuery(
      metaStoryData?.meta_story?.id,
      $queryParams.from_landing
    );
    return (
      `#/${currentLanguage}/story/${personId}` + (search ? `?${search}` : "")
    );
  }

  // Remember where the reader left the meta story before jumping into a story.
  function rememberScroll() {
    const metaStoryId = metaStoryData?.meta_story?.id;
    if (metaStoryId) saveMetaStoryScroll(metaStoryId);
  }

  // Shared props for every prose renderer / body in the story.
  $: proseContext = {
    people: storyPeople,
    metaStoryId: metaStoryData?.meta_story?.id ?? null,
    currentLanguage,
  };

  // The article renders only once its data resolves, so mount is too early to
  // focus it. Taken the first time the element exists instead.
  let metaStoryViewElement;
  let metaStoryFocused = false;
  $: if (metaStoryViewElement && !metaStoryFocused) {
    metaStoryFocused = true;
    metaStoryViewElement.focus({ preventScroll: true });
  }

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

  // Navigate back to landing, restoring the filters it was left with
  function backToLanding() {
    const fromLanding = $queryParams.from_landing;
    replace(`/${currentLanguage}` + (fromLanding ? `?${fromLanding}` : ""));
    restoreFocusTrigger("[data-landing-heading]");
  }

  // Every prose region of a composed story is a list of blocks —
  // paragraph | image | quote — rendered by MetaStoryBody. Stories composed
  // before that unification stored plain strings (and the opening a separate
  // image), so they are normalized to the same shape here.
  function toBlocks(value, legacyImage = null) {
    if (Array.isArray(value)) return value;
    if (typeof value !== "string" || !value.trim()) return [];
    const blocks = String(value)
      .split(/\n\s*\n/)
      .filter((paragraph) => paragraph.trim())
      .map((paragraph) => ({ type: "paragraph", text: paragraph.trim() }));
    if (legacyImage?.url) {
      blocks.unshift({ type: "image", image: legacyImage, layout: "full" });
    }
    return blocks;
  }

  $: openingBlocks = Array.isArray(metaStoryData?.opening)
    ? metaStoryData.opening
    : toBlocks(metaStoryData?.opening?.text, metaStoryData?.opening?.image);
  $: descriptionBlocks = toBlocks(
    metaStoryData?.description ?? metaStoryData?.meta_story?.description
  );
  // The closing section's prose. Legacy stories split it into a body block
  // list plus a trailing string; both render as one region now.
  $: conclusionBlocks = [
    ...toBlocks(metaStoryData?.section_bodies?.conclusion),
    ...toBlocks(metaStoryData?.conclusion),
  ];

  // Composed story-specific section headings, falling back to generic labels
  $: sectionHeadings = metaStoryData?.section_headings || {};
  // Composed section bodies: the prose between a section's heading and its
  // interactive component.
  $: sectionBodies = metaStoryData?.section_bodies || {};

  // Every picture in the story, in reading order, so the lightbox can page
  // through them. Mirrors the conditions the template renders the figures
  // under, so an image never appears in the gallery without being on the page.
  $: galleryImages = collectStoryImages(
    metaStoryData,
    openingBlocks,
    descriptionBlocks,
    conclusionBlocks
  );

  function collectStoryImages(data, opening, description, conclusion) {
    if (!data) return [];
    const images = [];
    const addBody = (blocks) => {
      (blocks || []).forEach((block) => {
        if (block?.type === "image" && block.image?.url)
          images.push(block.image);
      });
    };
    const bodies = data.section_bodies || {};

    addBody(opening);
    addBody(description);
    if (data.chapters?.length) addBody(bodies.timeline);
    if (data.social_network?.links?.length) addBody(bodies.network);
    if (data.geo_map?.clusters?.length) addBody(bodies.map);
    addBody(conclusion);
    return images;
  }

  // Lightbox state
  let enlargedImage = null;
  let enlargedGallery = [];
  let enlargedIndex = 0;

  function openEnlargedImage(image) {
    const index = galleryImages.indexOf(image);
    enlargedGallery = index >= 0 ? galleryImages : [image];
    enlargedIndex = index >= 0 ? index : 0;
    enlargedImage = enlargedGallery[enlargedIndex];
  }

  function closeEnlargedImage() {
    enlargedImage = null;
  }

  function handleImageNavigate(index) {
    if (index < 0 || index >= enlargedGallery.length) return;
    enlargedIndex = index;
    enlargedImage = enlargedGallery[index];
  }

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

    // The lightbox owns the arrow keys while it is open (it navigates images);
    // this listener was registered first, so it has to step aside itself.
    if (enlargedImage) return;

    // These shortcuts mirror the timeline's own prev/next buttons, which only
    // render while the section is scroll-locked (pinned) — so the shortcut
    // must not fire before/after that, e.g. at the top of the article.
    if (!isScrollLockActive) return;

    // Step aside while any modal dialog is open (AI disclaimer, network
    // modal, ...) so it can't navigate the page behind it.
    if (document.querySelector('[role="dialog"][aria-modal="true"]')) return;

    // Don't intercept typing, or keyboard behavior owned by a focused control
    // outside the timeline itself (the sticky header's buttons, map controls,
    // links, etc.) — only an unfocused page or focus already inside the
    // timeline lets these shortcuts through.
    const activeElement = document.activeElement;
    if (
      activeElement &&
      activeElement !== document.body &&
      !timelineContainer.contains(activeElement)
    ) {
      return;
    }
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
  <!-- Focusable and focused on mount, the way the story view is: a route change
       otherwise drops the keyboard reader to the top of the document. -->
  <div
    class="meta-story-view"
    class:styled={!!storyStyle}
    style={storyStyleVars}
    bind:this={metaStoryViewElement}
    tabindex="-1"
    role="region"
    aria-label={metaStoryData?.meta_story?.title ??
      $_("meta_story.back_to_stories")}
  >
    <!-- The story's color and pattern, painted behind the whole page rather
         than behind the text column, so the article sits inside its own
         atmosphere instead of on a tinted strip. -->
    {#if storyStyle}
      <div class="story-backdrop" aria-hidden="true"></div>
    {/if}

    <!-- Sticky header - appears when scrolling down -->
    {#if showStickyHeader}
      <div class="sticky-header-group" transition:fade={{ duration: 200 }}>
        <header class="meta-sticky-header" bind:this={stickyHeaderElement}>
          <div class="sticky-compact-info">
            <span class="sticky-name">{metaStoryData.meta_story.title}</span>
            {#if storyStyle?.separatorGlyphDataUrl}
              <span class="separator glyph-separator" aria-hidden="true"></span>
            {:else}
              <span class="separator">·</span>
            {/if}
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
      <!-- The masthead is one object, not a stack of lines with a rule under
           it: an accent bracket opens at the top left and the story's glyph
           sits on its corner, so title, tagline and dateline are set against
           something rather than followed by decoration. The bracket is the
           whole apparatus — nothing terminates the dateline, because the
           block is already closed and a second mark would only be a mark. -->
      <div class="masthead">
        {#if storyStyle?.separatorGlyphDataUrl}
          <span class="masthead-mark" aria-hidden="true"></span>
        {/if}
        <h1>{metaStoryData.meta_story.title}</h1>
        <p class="tagline">{metaStoryData.meta_story.tagline}</p>
        <p class="date-range">
          {$_("meta_story.date_range", {
            start: metaStoryData.meta_story.date_range_start,
            end: metaStoryData.meta_story.date_range_end,
          })}
        </p>
      </div>
      <MetaStoryBody
        blocks={openingBlocks}
        variant="opening"
        {...proseContext}
        onEnlarge={openEnlargedImage}
      />
      <!-- The cold open and the description are two prose regions with no
           subhead between them; the story's own glyph marks the break. -->
      {#if storyStyle?.separatorGlyphDataUrl && openingBlocks.length && descriptionBlocks.length}
        <MetaStoryOrnament />
      {/if}
      <MetaStoryBody
        blocks={descriptionBlocks}
        {...proseContext}
        onEnlarge={openEnlargedImage}
      />
    </header>

    <!-- Chapters section - scroll proxy container for horizontal scroll lock -->
    {#if metaStoryData.chapters?.length}
      <section class="chapters-section">
        <h2>{sectionHeadings.timeline || $_("meta_story.chapters_heading")}</h2>
        <MetaStoryBody
          blocks={sectionBodies.timeline}
          {...proseContext}
          onEnlarge={openEnlargedImage}
        />

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
        <MetaStoryBody
          blocks={sectionBodies.network}
          {...proseContext}
          onEnlarge={openEnlargedImage}
        />
        {#await import("./MetaStoryNetwork.svelte") then { default: MetaStoryNetwork }}
          <MetaStoryNetwork
            network={metaStoryData.social_network}
            metaStoryId={metaStoryData.meta_story.id}
            {personAliases}
            {currentLanguage}
          />
        {/await}
      </section>
    {/if}

    <!-- Map section - the story's places, usually the last stop before the
         conclusion -->
    {#if metaStoryData.geo_map?.clusters?.length}
      <section class="map-section">
        <h2>{sectionHeadings.map || $_("meta_story.map_heading")}</h2>
        <MetaStoryBody
          blocks={sectionBodies.map}
          {...proseContext}
          onEnlarge={openEnlargedImage}
        />
        {#await import("./MetaStoryMap.svelte") then { default: MetaStoryMap }}
          <MetaStoryMap
            geoMap={metaStoryData.geo_map}
            metaStoryId={metaStoryData.meta_story.id}
            {personAliases}
            {currentLanguage}
          />
        {/await}
      </section>
    {/if}

    <!-- Conclusion section -->
    {#if conclusionBlocks.length}
      <section class="conclusion">
        <h2>
          {sectionHeadings.conclusion || $_("meta_story.conclusion_heading")}
        </h2>
        <MetaStoryBody
          blocks={conclusionBlocks}
          {...proseContext}
          onEnlarge={openEnlargedImage}
        />
        <!-- End mark: the article's prose stops here, the cast follows. -->
        {#if storyStyle?.ornamentDataUrl}
          <MetaStoryOrnament variant="closing" />
        {/if}
      </section>
    {/if}

    <!-- The story's people - closing cards linking into each individual story,
         mirroring the related people at the end of a person's story -->
    {#if storyPersonCards.length}
      <section class="people-section">
        <h2>{$_("meta_story.people_heading")}</h2>
        <div class="people-grid">
          {#each storyPersonCards as person (person.id)}
            <PersonCard
              {person}
              personStyle={cardStyle(person.id)}
              href={personStoryHref(person.id)}
              ariaLabel={$_("meta_story.people_open_story", {
                name: displayName(person.name),
              })}
              onNavigate={rememberScroll}
            />
          {/each}
        </div>
      </section>
    {/if}
  </div>
{/if}

<ImageViewer
  image={enlargedImage}
  allImages={enlargedGallery}
  currentIndex={enlargedIndex}
  onClose={closeEnlargedImage}
  onNavigate={handleImageNavigate}
/>

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

  /* A story with its own identity keeps the same four roles, but tinted
     toward its primary color: the accent becomes the story's, and the three
     inks pick up just enough of it that the page reads as one temperature
     without losing the contrast running prose needs. The tint is deliberately
     strongest on the muted tone (datelines, captions) and weakest on the
     headline ink, which stays near-white. */
  .meta-story-view.styled {
    --ms-accent: var(--ms-primary, #38bdf8);
    --ms-ink: color-mix(in srgb, var(--ms-primary, #38bdf8) 10%, #eef2f8);
    --ms-body: color-mix(in srgb, var(--ms-primary, #38bdf8) 8%, #cbd5e1);
    --ms-muted: color-mix(in srgb, var(--ms-primary, #38bdf8) 25%, #94a3b8);
  }

  /* The story's color and pattern, fixed behind the scrolling article. The
     pattern is the same black-and-white tile the person stories use — tinted
     by the primary color through multiply/overlay — but held far quieter and
     faded toward the bottom of the viewport, because this page is a long
     read rather than a full-screen slide. */
  .story-backdrop {
    position: fixed;
    inset: 0;
    z-index: -1;
    pointer-events: none;
    background-color: var(--ms-page-bg, transparent);
    /* The article is a fixed 800px column with the backdrop pinned to the
       viewport behind it, so on anything wider than the column the two side
       bands never carry text at any scroll position. That is where the pattern
       is allowed to come up; the ramp collapses to nothing once the viewport is
       no wider than the column. */
    --ms-side-mask: linear-gradient(
      90deg,
      rgba(0, 0, 0, 1) 0%,
      rgba(0, 0, 0, 0) max(0px, 50% - 25rem),
      rgba(0, 0, 0, 0) min(100%, 50% + 25rem),
      rgba(0, 0, 0, 1) 100%
    );
    --ms-side-lift: linear-gradient(
      90deg,
      var(--pattern-edge-lift) 0%,
      var(--pattern-quiet) max(0px, 50% - 25rem),
      var(--pattern-quiet) min(100%, 50% + 25rem),
      var(--pattern-edge-lift) 100%
    );
  }

  /* Two coats of the same tile, carried the way a story slide carries them:
     `::after` is an even base wash and `::before` a side coat masked to the
     bands beside the column, where the two together roughly double the pattern.
     The backdrop used to hold a single coat at a quarter of that strength,
     fading to almost nothing down the viewport—faint enough that on a dim
     screen the page read as flat color. What keeps it off the prose now is the
     same thing that keeps it off a slide's headline: the column, not the
     overall strength. */
  .story-backdrop::before,
  .story-backdrop::after {
    content: "";
    position: absolute;
    inset: 0;
    background-color: var(--ms-primary, #38bdf8);
    background-image: var(--ms-pattern-image, none), var(--ms-side-lift);
    background-size:
      340px,
      100% 100%;
    background-repeat: repeat, no-repeat;
    background-blend-mode: multiply, screen;
    mix-blend-mode: overlay;
  }

  .story-backdrop::after {
    /* A slide shows a headline and a paragraph; this page is a long read, and
       its tile is denser—340px against a slide's 500px—so the same alpha puts
       about twice a slide's pattern behind running prose. The base wash takes a
       little over half of `--pattern-core-alpha`, which lands the column where a
       slide's column sits, and the side coat carries the difference. */
    opacity: calc(var(--pattern-core-alpha) * 0.55);
  }

  .story-backdrop::before {
    mask-image: var(--ms-side-mask);
    -webkit-mask-image: var(--ms-side-mask);
    mask-size: 100% 100%;
    -webkit-mask-size: 100% 100%;
    mask-repeat: no-repeat;
    -webkit-mask-repeat: no-repeat;
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

  /* The masthead rides on the story's own background instead of the generic
     slate, so it does not read as a foreign bar over a colored page. */
  .styled .meta-sticky-header {
    background:
      linear-gradient(
        180deg,
        rgba(255, 255, 255, 0.03) 0%,
        rgba(0, 0, 0, 0.28) 100%
      ),
      rgba(var(--ms-page-bg-rgb, 15, 23, 42), 0.72);
    border-bottom-color: color-mix(in srgb, var(--ms-accent) 30%, transparent);
  }

  .sticky-ai-button {
    /* Hangs the tag off the bottom edge of the sticky header. `display: flex`
       drops the inline line box that would otherwise pad the tag downward;
       the one-pixel overlap then keeps fractional header heights from
       revealing a seam without covering the label itself. */
    position: absolute;
    top: calc(var(--sticky-header-height, 3.5rem) - 1px);
    left: -0.25rem;
    z-index: -1; /* Below sticky header */
    display: flex;
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

  /* The story's own glyph in place of the interpunct, as on the story slides. */
  .glyph-separator {
    display: inline-block;
    width: 0.9em;
    height: 0.9em;
    background-image: var(--ms-glyph, none);
    background-position: center;
    background-size: contain;
    background-repeat: no-repeat;
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
    margin-bottom: 0;
  }

  .masthead {
    position: relative;
    margin-bottom: 2rem;
  }

  /* The bracket: a hairline along the top that fades out to the right, and a
     spine down the left edge that fades out below the dateline. Two open arms
     rather than a frame — a closed box would read as a card, and the block has
     to stay part of the page. The panel behind them is the story's accent at a
     few percent, just enough to bind the lines into one object. */
  .styled .masthead {
    padding: 1.15rem 0 1rem 1.4rem;
    background: linear-gradient(
      118deg,
      color-mix(in srgb, var(--ms-accent) 8%, transparent) 0%,
      transparent 62%
    );
  }

  .styled .masthead::before {
    content: "";
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    width: 2px;
    background: linear-gradient(
      180deg,
      color-mix(in srgb, var(--ms-accent) 80%, transparent) 0%,
      color-mix(in srgb, var(--ms-accent) 45%, transparent) 55%,
      transparent 100%
    );
  }

  .styled .masthead::after {
    content: "";
    position: absolute;
    left: 0;
    right: 0;
    top: 0;
    height: 1px;
    background: linear-gradient(
      90deg,
      color-mix(in srgb, var(--ms-accent) 75%, transparent) 0%,
      transparent 80%
    );
  }

  /* The story's glyph sits on the corner where the two arms meet, centered on
     the joint so it reads as the pivot of the bracket rather than as a bullet
     next to the title. */
  .masthead-mark {
    position: absolute;
    left: -0.62rem;
    top: -0.62rem;
    width: 1.25rem;
    height: 1.25rem;
    background-image: var(--ms-glyph, none);
    background-position: center;
    background-size: contain;
    background-repeat: no-repeat;
  }

  /* Every prose region — the cold open, the description, the section bodies
     and the closing — is the same body copy, styled once in MetaStoryBody. */

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

  /* In a styled story the subhead rule takes the story's color and the glyph
     marks each section, so the same mark that separates prose also opens it. */
  .styled h2 {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    border-bottom-color: color-mix(in srgb, var(--ms-accent) 40%, transparent);
  }

  .styled h2::before {
    content: "";
    flex: 0 0 auto;
    width: 0.9em;
    height: 0.9em;
    background-image: var(--ms-glyph, none);
    background-position: center;
    background-size: contain;
    background-repeat: no-repeat;
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
  .network-section,
  .map-section {
    margin-bottom: 3rem;
  }

  /* Conclusion — the same body copy as the rest of the article; its own
     subhead already sets it apart, so it needs no italic or size shift. */
  .conclusion p {
    font-size: 1.0625rem;
    line-height: 1.75;
    color: var(--ms-body);
  }

  /* Closing person cards — the story's cast, each linking into their own story */
  .people-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
    gap: 1rem;

    /* The page background is the same near-black as PersonCard's default
       surface, so lift the cards a step to keep them readable as objects. */
    --card-bg: rgba(30, 41, 59, 0.55);
    --card-bg-hover: rgba(30, 41, 59, 0.85);
    --card-border: rgba(148, 163, 184, 0.22);
    --card-border-hover: rgba(148, 163, 184, 0.45);
  }

  /* Only the frames pick up the story's color: the card surfaces have to stay
     a step lighter than the page to read as objects, and what is inside them
     already belongs to each person's own story. */
  .styled .people-grid {
    --card-border: color-mix(in srgb, var(--ms-accent) 25%, transparent);
    --card-border-hover: color-mix(in srgb, var(--ms-accent) 50%, transparent);
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
    background: rgba(var(--ms-page-bg-rgb, 15, 23, 42), 0.65);
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

  /* In a styled story the pager belongs to the timeline it drives, so it takes
     the story's frame colour rather than the generic slate. */
  .styled .timeline-nav-btn {
    border-color: color-mix(in srgb, var(--ms-accent) 40%, transparent);
  }

  .styled .timeline-nav-btn:hover:not(:disabled),
  .styled .timeline-nav-btn:focus:not(:disabled) {
    border-color: color-mix(in srgb, var(--ms-accent) 70%, transparent);
  }

  .timeline-nav-btn.prev {
    left: 1rem;
  }

  .timeline-nav-btn.next {
    right: 1rem;
  }

  .timeline-nav-btn:hover:not(:disabled),
  .timeline-nav-btn:focus:not(:disabled) {
    background: rgba(var(--ms-page-bg-rgb, 15, 23, 42), 0.85);
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
      bottom: 0;
      display: flex;
      flex-direction: column;
      align-items: flex-end;
    }

    .meta-sticky-header {
      position: relative;
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
      /* Keep the tag in flow with the compact header; the one-pixel overlap
         prevents fractional layout rounding from revealing a seam. */
      position: relative;
      top: -1px;
      right: auto;
      left: auto;
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

    .people-grid {
      grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
      gap: 0.75rem;
    }
  }
</style>
