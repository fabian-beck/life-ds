<script>
  import { mdiClose, mdiRefresh, mdiChevronLeft, mdiChevronRight, mdiArrowRight } from "@mdi/js";
  import { onMount, onDestroy } from "svelte";
  import { _ } from "../stores/language";
  import { storyStyleVars } from "../utils/helpers.js";

  export let image = null; // { url, caption, source, eventIndex, eventTitle, slideIndex, ... }
  export let onClose = () => {};
  export let styleConfig = null;
  export let allImages = [];
  export let currentIndex = 0;
  export let activeSlideIndex = 0;
  export let onNavigate = () => {};
  export let onJumpToEvent = () => {};

  let container;
  let imageElement;
  let imageWrapper;
  let scale = 1;
  let translateX = 0;
  let translateY = 0;
  let isDragging = false;
  let startX = 0;
  let startY = 0;
  let imageLoaded = false;

  // Touch handling
  let initialDistance = 0;
  let initialScale = 1;
  let touchSwipeStartX = null;
  let touchSwipeStartY = null;
  let touchSwipeStartTime = null;
  let lastTouchX = null;
  let lastTouchY = null;

  $: transform = `translate(${translateX}px, ${translateY}px) scale(${scale})`;

  // Caption visibility: hide when zoomed or dragging
  $: showCaption = scale <= 1 && !isDragging;

  // Determine if current image is from a different slide than active slide
  $: isDifferentSlide =
    image &&
    image.slideIndex !== undefined &&
    image.slideIndex >= 0 &&
    image.slideIndex !== activeSlideIndex;

  // Determine if the image is from the overview slide (eventTitle is null)
  $: isFromOverview = image && image.eventTitle === null;

  // Navigation availability
  $: canGoPrev = currentIndex > 0;
  $: canGoNext = currentIndex < allImages.length - 1;
  $: hasMultipleImages = allImages.length > 1;

  // Reset view and loading state when image changes
  $: if (image) {
    resetView();
    imageLoaded = false;
  }

  // Preload adjacent images
  $: if (image && allImages.length > 1) {
    if (currentIndex < allImages.length - 1) {
      const nextImg = new Image();
      nextImg.src = allImages[currentIndex + 1].url;
    }
    if (currentIndex > 0) {
      const prevImg = new Image();
      prevImg.src = allImages[currentIndex - 1].url;
    }
  }

  /**
   * Extract a human-readable source name from a URL.
   * Returns provider name like "Flickr", "Wikimedia Commons", etc.
   */
  function getSourceName(url) {
    if (!url) return "";
    try {
      const hostname = new URL(url).hostname.toLowerCase();
      if (hostname.includes("flickr.com")) return "Flickr";
      if (hostname.includes("commons.wikimedia.org")) return "Wikimedia Commons";
      if (hostname.includes("wikimedia.org")) return "Wikimedia";
      if (hostname.includes("wikipedia.org")) return "Wikipedia";
      if (hostname.includes("met.museum") || hostname.includes("metmuseum.org")) return "The Met";
      if (hostname.includes("smithsonian")) return "Smithsonian";
      if (hostname.includes("loc.gov")) return "Library of Congress";
      if (hostname.includes("europeana.eu")) return "Europeana";
      if (hostname.includes("unsplash.com")) return "Unsplash";
      // Fallback: extract domain name
      const parts = hostname.replace("www.", "").split(".");
      return parts[0].charAt(0).toUpperCase() + parts[0].slice(1);
    } catch {
      return "Source";
    }
  }

  function handleWheel(event) {
    if (!container || !imageWrapper) return;
    event.preventDefault();

    const delta = -event.deltaY;
    const scaleChange = delta > 0 ? 1.1 : 0.9;
    const newScale = Math.max(0.5, Math.min(scale * scaleChange, 10));

    // Get mouse position relative to the viewport
    const rect = container.getBoundingClientRect();
    const mouseX = event.clientX - rect.left - rect.width / 2;
    const mouseY = event.clientY - rect.top - rect.height / 2;

    // Calculate new translation to zoom towards mouse position
    const scaleRatio = newScale / scale;
    translateX = mouseX + (translateX - mouseX) * scaleRatio;
    translateY = mouseY + (translateY - mouseY) * scaleRatio;
    scale = newScale;
  }

  function handleMouseDown(event) {
    if (event.button !== 0) return; // Only left click
    event.preventDefault();
    isDragging = true;
    startX = event.clientX - translateX;
    startY = event.clientY - translateY;
  }

  function handleMouseMove(event) {
    if (!isDragging) return;
    event.preventDefault();
    translateX = event.clientX - startX;
    translateY = event.clientY - startY;
  }

  function handleMouseUp() {
    isDragging = false;
  }

  function handleDoubleClick(event) {
    if (!container) return;
    event.preventDefault();

    if (scale > 1) {
      // Reset to fit
      resetView();
    } else {
      // Zoom to 2x at click position
      const rect = container.getBoundingClientRect();
      const clickX = event.clientX - rect.left - rect.width / 2;
      const clickY = event.clientY - rect.top - rect.height / 2;

      const scaleRatio = 2 / scale;
      translateX = clickX + (translateX - clickX) * scaleRatio;
      translateY = clickY + (translateY - clickY) * scaleRatio;
      scale = 2;
    }
  }

  function getTouchDistance(touches) {
    const dx = touches[0].clientX - touches[1].clientX;
    const dy = touches[0].clientY - touches[1].clientY;
    return Math.sqrt(dx * dx + dy * dy);
  }

  function getTouchCenter(touches) {
    return {
      x: (touches[0].clientX + touches[1].clientX) / 2,
      y: (touches[0].clientY + touches[1].clientY) / 2,
    };
  }

  function handleTouchStart(event) {
    if (event.touches.length === 1) {
      // Single touch - start dragging and track for swipe
      isDragging = true;
      startX = event.touches[0].clientX - translateX;
      startY = event.touches[0].clientY - translateY;
      touchSwipeStartX = event.touches[0].clientX;
      touchSwipeStartY = event.touches[0].clientY;
      touchSwipeStartTime = Date.now();
      lastTouchX = event.touches[0].clientX;
      lastTouchY = event.touches[0].clientY;
    } else if (event.touches.length === 2) {
      // Two touches - prepare for pinch zoom
      event.preventDefault();
      isDragging = false;
      touchSwipeStartX = null;
      initialDistance = getTouchDistance(event.touches);
      initialScale = scale;
    }
  }

  function handleTouchMove(event) {
    if (event.touches.length === 1 && isDragging) {
      // Single touch drag
      event.preventDefault();
      translateX = event.touches[0].clientX - startX;
      translateY = event.touches[0].clientY - startY;
      lastTouchX = event.touches[0].clientX;
      lastTouchY = event.touches[0].clientY;
    } else if (event.touches.length === 2) {
      // Pinch zoom
      event.preventDefault();
      const currentDistance = getTouchDistance(event.touches);
      const scaleChange = currentDistance / initialDistance;
      const newScale = Math.max(0.5, Math.min(initialScale * scaleChange, 10));

      const center = getTouchCenter(event.touches);
      const rect = container.getBoundingClientRect();
      const centerX = center.x - rect.left - rect.width / 2;
      const centerY = center.y - rect.top - rect.height / 2;

      const scaleRatio = newScale / scale;
      translateX = centerX + (translateX - centerX) * scaleRatio;
      translateY = centerY + (translateY - centerY) * scaleRatio;
      scale = newScale;
    }
  }

  function handleTouchEnd(event) {
    if (event.touches.length === 0) {
      isDragging = false;

      // Check for swipe gesture (only when not zoomed)
      if (touchSwipeStartX !== null && scale === 1 && hasMultipleImages) {
        const deltaX = touchSwipeStartX - lastTouchX;
        const deltaY = touchSwipeStartY - lastTouchY;
        const deltaTime = Date.now() - touchSwipeStartTime;
        const velocity = deltaTime > 0 ? Math.abs(deltaX) / deltaTime : 0;

        // Horizontal swipe with sufficient velocity and distance
        if (velocity > 0.3 && Math.abs(deltaX) > 50 && Math.abs(deltaX) > Math.abs(deltaY)) {
          if (deltaX > 0 && canGoNext) {
            goToNextImage();
          } else if (deltaX < 0 && canGoPrev) {
            goToPrevImage();
          }
        }
      }

      touchSwipeStartX = null;
      touchSwipeStartY = null;
      touchSwipeStartTime = null;
    } else if (event.touches.length === 1) {
      // One finger lifted, resume dragging with remaining finger
      isDragging = true;
      startX = event.touches[0].clientX - translateX;
      startY = event.touches[0].clientY - translateY;
      touchSwipeStartX = null;
    }
  }

  function resetView() {
    scale = 1;
    translateX = 0;
    translateY = 0;
  }

  function closeViewer() {
    resetView();
    onClose();
  }

  function goToPrevImage() {
    if (canGoPrev) {
      resetView();
      imageLoaded = false;
      onNavigate(currentIndex - 1);
    }
  }

  function goToNextImage() {
    if (canGoNext) {
      resetView();
      imageLoaded = false;
      onNavigate(currentIndex + 1);
    }
  }

  function jumpToEvent() {
    if (image && image.slideIndex >= 0) {
      onJumpToEvent(image.slideIndex);
      onClose();
    }
  }

  function handleKeydown(event) {
    // Only handle keyboard events when image viewer is open
    if (!image) return;

    if (event.key === "Escape") {
      event.stopPropagation();
      closeViewer();
    } else if (event.key === "r" || event.key === "R") {
      event.stopPropagation();
      resetView();
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      event.stopPropagation();
      goToPrevImage();
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      event.stopPropagation();
      goToNextImage();
    } else if (event.key === "+" || event.key === "=") {
      event.stopPropagation();
      scale = Math.min(scale * 1.2, 10);
    } else if (event.key === "-" || event.key === "_") {
      event.stopPropagation();
      scale = Math.max(scale * 0.8, 0.5);
    }
  }

  function handleBackdropClick(event) {
    if (event.target === event.currentTarget) {
      closeViewer();
    }
  }

  function handleImageLoad() {
    imageLoaded = true;
  }

  onMount(() => {
    window.addEventListener("keydown", handleKeydown);
    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
  });

  onDestroy(() => {
    window.removeEventListener("keydown", handleKeydown);
    window.removeEventListener("mousemove", handleMouseMove);
    window.removeEventListener("mouseup", handleMouseUp);
  });
</script>

{#if image}
  <div
    class="image-viewer"
    style={storyStyleVars(styleConfig)}
    on:click={handleBackdropClick}
    on:keydown={(e) => e.key === "Enter" && handleBackdropClick(e)}
    on:wheel={handleWheel}
    role="button"
    tabindex="0"
    aria-label={$_("image.viewer_title")}
  >
    <!-- Top controls: reset and close -->
    <div class="viewer-controls">
      <button
        type="button"
        class="control-btn reset-btn"
        on:click={resetView}
        aria-label={$_("image.reset_view_short")}
        title={$_("image.reset_view")}
      >
        <svg
          class="icon"
          viewBox="0 0 24 24"
          role="presentation"
          aria-hidden="true"
        >
          <path d={mdiRefresh} />
        </svg>
      </button>
      <button
        type="button"
        class="control-btn close-btn"
        on:click={closeViewer}
        aria-label={$_("image.close")}
        title={$_("image.close_short")}
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

    <div
      class="image-container"
      bind:this={container}
      on:mousedown={handleMouseDown}
      on:dblclick={handleDoubleClick}
      on:touchstart={handleTouchStart}
      on:touchmove={handleTouchMove}
      on:touchend={handleTouchEnd}
      role="presentation"
    >
      <div
        class="image-wrapper"
        bind:this={imageWrapper}
        style="transform: {transform}; cursor: {isDragging
          ? 'grabbing'
          : scale > 1
            ? 'grab'
            : 'zoom-in'};"
        role="presentation"
      >
        {#if !imageLoaded}
          <div class="image-loading">
            <div class="spinner"></div>
          </div>
        {/if}
        <img
          bind:this={imageElement}
          src={image.url}
          alt={image.caption || $_("image.enlarged_view")}
          draggable="false"
          on:load={handleImageLoad}
          on:error={handleImageLoad}
          class:loaded={imageLoaded}
        />
      </div>
    </div>

    <!-- Bottom panel: navigation + caption + event context -->
    <div
      class="viewer-bottom-panel"
      class:hidden={!showCaption}
      on:click|stopPropagation
      role="presentation"
    >
      <!-- Context banner (when image is from different slide) -->
      {#if isDifferentSlide}
        <div class="event-context-row">
          <span class="context-info">
            {#if isFromOverview}
              <span class="context-label">{$_("image.from_overview")}</span>
            {:else}
              <span class="context-label">{$_("image.from_event")}:</span>
              <span class="context-title">{image.eventTitle}</span>
              {#if image.eventDate}
                <span class="context-separator">·</span>
                <span class="context-date">{image.eventDate}</span>
              {/if}
            {/if}
          </span>
          <button
            type="button"
            class="jump-to-event-btn"
            on:click={jumpToEvent}
            aria-label={isFromOverview ? $_("image.go_to_overview") : $_("image.go_to_event")}
          >
            {isFromOverview ? $_("image.go_to_overview") : $_("image.go_to_event")}
            <svg class="icon icon-small" viewBox="0 0 24 24" aria-hidden="true">
              <path d={mdiArrowRight} />
            </svg>
          </button>
        </div>
      {/if}

      <!-- Main content row: prev button, caption, next button -->
      <div class="caption-row">
        <!-- Previous button -->
        {#if hasMultipleImages}
          <button
            type="button"
            class="nav-btn"
            on:click={goToPrevImage}
            disabled={!canGoPrev}
            aria-label={$_("image.previous")}
          >
            <svg class="icon" viewBox="0 0 24 24" aria-hidden="true">
              <path d={mdiChevronLeft} />
            </svg>
          </button>
        {/if}

        <!-- Caption content -->
        <div class="caption-content">
          {#if image.caption}
            <p class="caption-text">{image.caption}</p>
          {/if}
          <p class="caption-meta">
            {#if hasMultipleImages}
              <span class="image-counter">{currentIndex + 1} / {allImages.length}</span>
            {/if}
            {#if image.creator || image.license || image.source}
              {#if hasMultipleImages}
                <span class="meta-separator">·</span>
              {/if}
              {#if image.creator}
                <span class="attribution-creator">{image.creator}</span>
              {/if}
              {#if image.license}
                {#if image.creator}<span class="meta-separator">·</span>{/if}
                {#if image.licenseUrl}
                  <a
                    href={image.licenseUrl}
                    target="_blank"
                    rel="noreferrer"
                    on:click|stopPropagation
                    class="attribution-license"
                  >{image.license}</a>
                {:else}
                  <span class="attribution-license">{image.license}</span>
                {/if}
              {/if}
              {#if image.originalImage || image.source}
                {#if image.creator || image.license}<span class="meta-separator">·</span>{/if}
                <a
                  href={image.originalImage || image.source}
                  target="_blank"
                  rel="noreferrer"
                  on:click|stopPropagation
                  class="attribution-source"
                >{getSourceName(image.originalImage || image.source)}</a>
              {/if}
            {/if}
          </p>
        </div>

        <!-- Next button -->
        {#if hasMultipleImages}
          <button
            type="button"
            class="nav-btn"
            on:click={goToNextImage}
            disabled={!canGoNext}
            aria-label={$_("image.next")}
          >
            <svg class="icon" viewBox="0 0 24 24" aria-hidden="true">
              <path d={mdiChevronRight} />
            </svg>
          </button>
        {/if}
      </div>
    </div>
  </div>
{/if}

<style>
  .image-viewer {
    position: fixed;
    inset: 0;
    background-color: rgba(var(--story-bg-rgb, 0, 0, 0), 0.95);
    backdrop-filter: blur(8px);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    z-index: 10000;
    animation: fadeIn 0.2s ease;
    touch-action: none;
    isolation: isolate;
  }

  /* Subtle pattern overlay matching StoryView */
  .image-viewer::before {
    content: "";
    position: absolute;
    inset: 0;
    pointer-events: none;
    background-color: var(--story-primary, #38bdf8);
    background-image: var(--story-pattern-image, none);
    background-size: var(--story-pattern-size, 400px);
    background-repeat: repeat;
    background-blend-mode: multiply;
    opacity: 0.12;
    mix-blend-mode: overlay;
    z-index: 0;
  }

  .image-viewer > * {
    position: relative;
    z-index: 1;
  }

  @keyframes fadeIn {
    from {
      opacity: 0;
    }
    to {
      opacity: 1;
    }
  }

  /* Top controls */
  .viewer-controls {
    position: absolute;
    top: 1rem;
    right: 1rem;
    display: flex;
    gap: 0.5rem;
    z-index: 1002;
  }

  .control-btn {
    width: 2.75rem;
    height: 2.75rem;
    border-radius: 999px;
    border: 1px solid rgba(255, 255, 255, 0.25);
    background: rgba(var(--story-bg-rgb, 0, 0, 0), 0.6);
    color: var(--story-primary, #ffffff);
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    transition:
      background-color 0.2s ease,
      border-color 0.2s ease,
      transform 0.2s ease,
      opacity 0.2s ease;
  }

  .control-btn:hover:not(:disabled),
  .control-btn:focus:not(:disabled) {
    background: rgba(var(--story-bg-rgb, 0, 0, 0), 0.8);
    border-color: var(--story-primary, rgba(255, 255, 255, 0.5));
    transform: scale(1.05);
    outline: none;
  }

  .control-btn:disabled {
    opacity: 0.3;
    cursor: not-allowed;
  }

  .icon {
    width: 1.4rem;
    height: 1.4rem;
    fill: currentColor;
  }

  .icon-small {
    width: 1rem;
    height: 1rem;
  }

  .image-container {
    flex: 1;
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
    position: relative;
  }

  .image-wrapper {
    display: flex;
    align-items: center;
    justify-content: center;
    transform-origin: center;
    transition: transform 0.05s ease-out;
    will-change: transform;
  }

  .image-container img {
    max-width: 95vw;
    max-height: 85vh;
    width: auto;
    height: auto;
    object-fit: contain;
    user-select: none;
    -webkit-user-select: none;
    -moz-user-select: none;
    -ms-user-select: none;
    pointer-events: none;
    opacity: 0;
    transition: opacity 0.2s ease;
  }

  .image-container img.loaded {
    opacity: 1;
  }

  /* Loading spinner */
  .image-loading {
    position: absolute;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .spinner {
    width: 40px;
    height: 40px;
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

  /* Bottom panel */
  .viewer-bottom-panel {
    position: absolute;
    bottom: 1rem;
    left: 50%;
    transform: translateX(-50%);
    background: rgba(var(--story-bg-rgb, 15, 23, 42), 0.95);
    backdrop-filter: blur(8px);
    border-radius: 0.75rem;
    border: 1px solid rgba(148, 163, 184, 0.25);
    max-width: min(90vw, 700px);
    z-index: 1001;
    opacity: 1;
    transition: opacity 0.3s ease;
    will-change: opacity;
    overflow: hidden;
  }

  .viewer-bottom-panel.hidden {
    opacity: 0;
    pointer-events: none;
  }

  /* Event context row */
  .event-context-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    padding: 0.6rem 1rem;
    background: rgba(var(--story-bg-rgb, 15, 23, 42), 0.5);
    border-bottom: 1px solid rgba(148, 163, 184, 0.15);
  }

  .context-info {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    flex-wrap: wrap;
    font-size: 0.8rem;
    font-family: var(--story-body-font, Inter, sans-serif);
  }

  .context-label {
    color: #94a3b8;
    font-weight: 500;
  }

  .context-title {
    color: var(--story-primary, #f8fafc);
    font-weight: 600;
  }

  .context-separator {
    color: rgba(148, 163, 184, 0.6);
  }

  .context-date {
    color: var(--story-secondary, #38bdf8);
    font-weight: 500;
  }

  .jump-to-event-btn {
    appearance: none;
    border: 1px solid var(--story-primary, rgba(148, 163, 184, 0.4));
    background: rgba(255, 255, 255, 0.05);
    color: var(--story-primary, #f8fafc);
    padding: 0.35rem 0.65rem;
    border-radius: 999px;
    font-size: 0.75rem;
    font-weight: 600;
    font-family: var(--story-body-font, Inter, sans-serif);
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    transition: all 0.2s ease;
    white-space: nowrap;
    flex-shrink: 0;
  }

  .jump-to-event-btn:hover,
  .jump-to-event-btn:focus {
    background: rgba(255, 255, 255, 0.12);
    border-color: var(--story-primary, rgba(148, 163, 184, 0.6));
    outline: none;
  }

  /* Caption row with navigation */
  .caption-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.75rem 0.5rem;
  }

  .nav-btn {
    width: 2.5rem;
    height: 2.5rem;
    border-radius: 999px;
    border: none;
    background: rgba(255, 255, 255, 0.05);
    color: var(--story-primary, #ffffff);
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    flex-shrink: 0;
    transition:
      background-color 0.2s ease,
      opacity 0.2s ease;
  }

  .nav-btn:hover:not(:disabled),
  .nav-btn:focus:not(:disabled) {
    background: rgba(255, 255, 255, 0.12);
    outline: none;
  }

  .nav-btn:disabled {
    opacity: 0.25;
    cursor: not-allowed;
  }

  .caption-content {
    flex: 1;
    min-width: 0;
    text-align: center;
    padding: 0 0.5rem;
  }

  .caption-text {
    margin: 0 0 0.35rem 0;
    font-size: 0.95rem;
    font-weight: 600;
    color: var(--story-primary, #f8fafc);
    font-family: var(--story-body-font, Inter, sans-serif);
  }

  .caption-meta {
    margin: 0;
    font-size: 0.75rem;
    color: #64748b;
    font-family: var(--story-body-font, Inter, sans-serif);
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.35rem;
    flex-wrap: wrap;
  }

  .image-counter {
    color: var(--story-secondary, #94a3b8);
    font-weight: 600;
  }

  .meta-separator {
    color: #475569;
  }

  .attribution-creator {
    color: #94a3b8;
  }

  .attribution-license,
  .attribution-source {
    color: #64748b;
    text-decoration: none;
  }

  a.attribution-license,
  a.attribution-source {
    color: var(--story-secondary, #64748b);
  }

  a.attribution-license:hover,
  a.attribution-license:focus,
  a.attribution-source:hover,
  a.attribution-source:focus {
    color: var(--story-primary, #94a3b8);
    text-decoration: underline;
  }

  /* Mobile styles */
  @media (max-width: 767px) {
    .viewer-controls {
      top: 0.75rem;
      right: 0.75rem;
      gap: 0.35rem;
    }

    .control-btn {
      width: 2.5rem;
      height: 2.5rem;
    }

    .icon {
      width: 1.25rem;
      height: 1.25rem;
    }

    /* Full-width bottom panel on mobile - more transparent and compact */
    .viewer-bottom-panel {
      bottom: 0;
      left: 0;
      right: 0;
      transform: none;
      max-width: 100%;
      border-radius: 0;
      border-left: none;
      border-right: none;
      border-bottom: none;
      background: rgba(var(--story-bg-rgb, 15, 23, 42), 0.75);
    }

    .event-context-row {
      flex-direction: row;
      align-items: center;
      gap: 0.5rem;
      padding: 0.4rem 0.6rem;
      background: rgba(var(--story-bg-rgb, 15, 23, 42), 0.4);
    }

    .context-info {
      font-size: 0.65rem;
      flex: 1;
      min-width: 0;
    }

    .context-title {
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      max-width: 140px;
      display: inline-block;
      vertical-align: middle;
    }

    .jump-to-event-btn {
      flex-shrink: 0;
      padding: 0.25rem 0.5rem;
      font-size: 0.65rem;
    }

    .caption-row {
      padding: 0.4rem 0.35rem;
      padding-bottom: calc(0.4rem + env(safe-area-inset-bottom, 0px));
      gap: 0.25rem;
    }

    .nav-btn {
      width: 2rem;
      height: 2rem;
    }

    .caption-content {
      padding: 0 0.25rem;
    }

    .caption-text {
      font-size: 0.75rem;
      margin-bottom: 0.15rem;
      line-height: 1.3;
    }

    .caption-meta {
      font-size: 0.6rem;
      gap: 0.25rem;
    }
  }

  /* Landscape mobile (short viewports) */
  @media (max-height: 500px) {
    .viewer-controls {
      top: 0.5rem;
      right: 0.5rem;
    }

    .control-btn {
      width: 2.25rem;
      height: 2.25rem;
    }

    .icon {
      width: 1.1rem;
      height: 1.1rem;
    }

    .viewer-bottom-panel {
      bottom: 0.5rem;
      background: rgba(var(--story-bg-rgb, 15, 23, 42), 0.7);
    }

    .event-context-row {
      padding: 0.3rem 0.5rem;
    }

    .caption-row {
      padding: 0.3rem 0.25rem;
      gap: 0.2rem;
    }

    .nav-btn {
      width: 1.75rem;
      height: 1.75rem;
    }

    .caption-text {
      font-size: 0.7rem;
      margin-bottom: 0.1rem;
    }

    .caption-meta {
      font-size: 0.55rem;
    }
  }
</style>
