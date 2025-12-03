<script>
  import { mdiClose, mdiRefresh } from "@mdi/js";
  import { onMount, onDestroy } from "svelte";
  import { _ } from "../stores/language";

  export let image = null; // { url, caption, source }
  export let onClose = () => {};

  let container;
  let imageElement;
  let imageWrapper;
  let scale = 1;
  let translateX = 0;
  let translateY = 0;
  let isDragging = false;
  let startX = 0;
  let startY = 0;

  // Touch handling
  let initialDistance = 0;
  let initialScale = 1;

  $: transform = `translate(${translateX}px, ${translateY}px) scale(${scale})`;

  // Reset view when image changes
  $: if (image) {
    resetView();
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
      // Single touch - start dragging
      isDragging = true;
      startX = event.touches[0].clientX - translateX;
      startY = event.touches[0].clientY - translateY;
    } else if (event.touches.length === 2) {
      // Two touches - prepare for pinch zoom
      event.preventDefault();
      isDragging = false;
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
    } else if (event.touches.length === 1) {
      // One finger lifted, resume dragging with remaining finger
      isDragging = true;
      startX = event.touches[0].clientX - translateX;
      startY = event.touches[0].clientY - translateY;
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

  function handleKeydown(event) {
    if (event.key === "Escape") {
      closeViewer();
    } else if (event.key === "r" || event.key === "R") {
      resetView();
    } else if (event.key === "+" || event.key === "=") {
      scale = Math.min(scale * 1.2, 10);
    } else if (event.key === "-" || event.key === "_") {
      scale = Math.max(scale * 0.8, 0.5);
    }
  }

  function handleBackdropClick(event) {
    if (event.target === event.currentTarget) {
      closeViewer();
    }
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
    on:click={handleBackdropClick}
    on:keydown={(e) => e.key === "Enter" && handleBackdropClick(e)}
    on:wheel={handleWheel}
    role="button"
    tabindex="0"
    aria-label={$_("image.viewer_title")}
  >
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
        <img
          bind:this={imageElement}
          src={image.url}
          alt={image.caption || $_("image.enlarged_view")}
          draggable="false"
        />
      </div>
    </div>

    {#if image.caption || image.source}
      <div class="viewer-caption" on:click|stopPropagation role="presentation">
        {#if image.caption}
          <p class="caption-text">{image.caption}</p>
        {/if}
        {#if image.source}
          <p class="caption-source">
            {$_("image.source")}
            <a
              href={image.source}
              target="_blank"
              rel="noreferrer"
              on:click|stopPropagation
            >
              {$_("image.wikimedia_commons")}
            </a>
          </p>
        {/if}
      </div>
    {/if}

    <div class="viewer-hints">
      <p>
        {$_("image.help_text")}
      </p>
    </div>
  </div>
{/if}

<style>
  .image-viewer {
    position: fixed;
    inset: 0;
    background-color: rgba(0, 0, 0, 0.95);
    backdrop-filter: blur(8px);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    z-index: 10000;
    animation: fadeIn 0.2s ease;
    touch-action: none;
  }

  @keyframes fadeIn {
    from {
      opacity: 0;
    }
    to {
      opacity: 1;
    }
  }

  .viewer-controls {
    position: absolute;
    top: 1rem;
    right: 1rem;
    display: flex;
    gap: 0.75rem;
    z-index: 1002;
  }

  .control-btn {
    width: 3rem;
    height: 3rem;
    border-radius: 999px;
    border: 1px solid rgba(255, 255, 255, 0.3);
    background: rgba(0, 0, 0, 0.6);
    color: #ffffff;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    transition:
      background-color 0.2s ease,
      border-color 0.2s ease,
      transform 0.2s ease;
  }

  .control-btn:hover,
  .control-btn:focus {
    background: rgba(0, 0, 0, 0.8);
    border-color: rgba(255, 255, 255, 0.6);
    transform: scale(1.05);
    outline: none;
  }

  .icon {
    width: 1.5rem;
    height: 1.5rem;
    fill: currentColor;
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
  }

  .viewer-caption {
    position: absolute;
    bottom: 1rem;
    left: 50%;
    transform: translateX(-50%);
    background: rgba(15, 23, 42, 0.95);
    backdrop-filter: blur(8px);
    padding: 1rem 1.5rem;
    border-radius: 0.5rem;
    border: 1px solid rgba(148, 163, 184, 0.3);
    max-width: 90vw;
    text-align: center;
    z-index: 1001;
  }

  .caption-text {
    margin: 0 0 0.5rem 0;
    font-size: 1rem;
    font-weight: 600;
    color: #f8fafc;
  }

  .caption-source {
    margin: 0;
    font-size: 0.85rem;
    color: #94a3b8;
  }

  .caption-source a {
    color: #38bdf8;
    text-decoration: none;
    font-weight: 500;
  }

  .caption-source a:hover,
  .caption-source a:focus {
    text-decoration: underline;
  }

  .viewer-hints {
    position: absolute;
    top: 1rem;
    left: 50%;
    transform: translateX(-50%);
    background: rgba(15, 23, 42, 0.85);
    backdrop-filter: blur(4px);
    padding: 0.5rem 1rem;
    border-radius: 0.375rem;
    border: 1px solid rgba(148, 163, 184, 0.2);
    z-index: 1001;
    opacity: 0.7;
    transition: opacity 0.2s ease;
  }

  .viewer-hints:hover {
    opacity: 1;
  }

  .viewer-hints p {
    margin: 0;
    font-size: 0.75rem;
    color: #94a3b8;
    white-space: nowrap;
  }

  @media (max-width: 767px) {
    .viewer-hints {
      display: none;
    }

    .viewer-controls {
      top: 0.75rem;
      right: 0.75rem;
      gap: 0.5rem;
    }

    .control-btn {
      width: 2.5rem;
      height: 2.5rem;
    }

    .icon {
      width: 1.25rem;
      height: 1.25rem;
    }

    .viewer-caption {
      bottom: 0.75rem;
      padding: 0.75rem 1rem;
    }

    .caption-text {
      font-size: 0.9rem;
    }

    .caption-source {
      font-size: 0.8rem;
    }
  }
</style>
