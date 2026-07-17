<script>
  import {
    mdiInformationOutline,
    mdiAccountOutline,
    mdiMagnifyPlusOutline,
    mdiLightbulbOnOutline,
    mdiRing,
    mdiStar,
    mdiBook,
    mdiMapMarkerMultiple,
  } from "@mdi/js";
  import { onDestroy } from "svelte";
  import { _ } from "../stores/language";
  import {
    formatDate,
    getDateNote,
    getThumbnailUrl,
    getValidImages,
    getSubcategory,
    getRelevantPeople,
    parseDescriptionSegments,
    findPersonInNetwork,
  } from "../utils/storyHelpers.js";
  import PersonChip from "./PersonChip.svelte";

  export let slide = {};
  export let egoNetwork = null;
  export let styleConfig = null;
  export let formatters = {};
  export let visibleDateNote = null;
  export let visiblePersonInfo = null;
  export let visibleAnnotation = null;
  export let isActive = false;
  export let onEnlargeImage = () => {};
  export let onToggleDateNote = () => {};
  export let onTogglePersonInfo = () => {};
  export let onToggleAnnotation = () => {};
  export let onOpenNetwork = () => {};

  function handleAnnotationClick(termKey, _segment) {
    onToggleAnnotation(slide.eventIndex, termKey);
  }

  $: validImages = getValidImages(slide.images);
  $: relevantPeople = getRelevantPeople(slide, egoNetwork);
  $: dateLabel = formatDate(slide, formatters);
  $: dateNote = getDateNote(slide);
  $: descriptionSegments = parseDescriptionSegments(
    slide.description,
    slide.annotations,
    relevantPeople
  );

  // Create a reactive map of which annotations should be visible
  $: annotationVisibilityMap = descriptionSegments.reduce((map, segment) => {
    if (segment.type === "annotation") {
      const compositeKey = `${slide.eventIndex}-${segment.termKey}`;
      map[segment.termKey] = visibleAnnotation === compositeKey;
    }
    return map;
  }, {});

  function formatAgeLabel(age) {
    if (age == null) return null;
    return age === 0 ? $_("story.at_birth") : $_("story.age", { age });
  }

  function getEventClassIcon(eventClass) {
    if (!eventClass?.type) return null;

    switch (eventClass.type) {
      case "invention":
        return mdiLightbulbOnOutline;
      case "marriage_partnership":
        return mdiRing;
      case "publication":
        return mdiBook;
      case "migration":
        return mdiMapMarkerMultiple;
      default:
        return mdiStar;
    }
  }

  function getEventClassLabel(eventClass) {
    if (!eventClass?.type) return "";

    switch (eventClass.type) {
      case "invention":
        return eventClass.title || "Invention";
      case "marriage_partnership":
        return eventClass.subtype === "marriage" ? "Marriage" : "Partnership";
      default:
        return eventClass.type;
    }
  }

  $: eventClassIcon = getEventClassIcon(slide.event_class);
  $: eventClassLabel = getEventClassLabel(slide.event_class);

  let imageLoadStateKey = "";
  let imageLoadGeneration = 0;
  let loadedImageUrls = new Set();
  let failedImageUrls = new Set();

  $: {
    const nextImageLoadStateKey = validImages
      .map((imageData) =>
        typeof imageData === "string" ? imageData : imageData.url
      )
      .join("|");
    if (nextImageLoadStateKey !== imageLoadStateKey) {
      imageLoadStateKey = nextImageLoadStateKey;
      imageLoadGeneration += 1;
      loadedImageUrls = new Set();
      failedImageUrls = new Set();
    }
  }

  function markImageLoaded(imageUrl) {
    loadedImageUrls = new Set(loadedImageUrls).add(imageUrl);
  }

  function handleThumbnailError(imageUrl) {
    failedImageUrls = new Set(failedImageUrls).add(imageUrl);
  }

  // Sizes the thumbnail container and mask from the image's aspect ratio and
  // the current viewport. Re-run on resize/rotation, not only on load.
  function applyImageLayout(img) {
    const imageAspect = img.naturalWidth / img.naturalHeight;

    // Get ACTUAL viewport dimensions in pixels
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    const viewportAspect = viewportWidth / viewportHeight;

    // Base bounds in relative units (vw/vh)
    let baseMaxWidth, baseMaxHeight;

    if (imageAspect < 0.8) {
      // Portrait images - allow taller bounds
      baseMaxWidth = 55; // vw
      baseMaxHeight = 75; // vh
    } else if (imageAspect > 1.25) {
      // Landscape images - allow wider bounds
      baseMaxWidth = 75; // vw
      baseMaxHeight = 55; // vh
    } else {
      // Square/near-square images - balanced bounds
      baseMaxWidth = 58; // vw
      baseMaxHeight = 58; // vh
    }

    // Aspect ratio correction factor: adjusts bounds based on how well the image
    // aspect ratio matches the viewport aspect ratio.
    //
    // KEY INSIGHT: Images should be LARGER when their orientation matches the viewport,
    // and SMALLER when orientations conflict.
    //
    // Calculate similarity: when both are portrait or both are landscape, aspects are similar.
    // When one is portrait and one is landscape, they differ significantly.

    // Measure how much image aspect differs from viewport aspect
    const aspectRatioDifference = Math.abs(
      Math.log(imageAspect / viewportAspect)
    );

    // Convert difference to a correction factor:
    // - Small difference (good match) → factor close to 1.0 or above
    // - Large difference (bad match) → factor well below 1.0
    //
    // Using exp(-k * difference) where k controls sensitivity
    const correctionFactor = Math.exp(-0.5 * aspectRatioDifference);

    // Clamp the factor to prevent extreme adjustments
    const clampedFactor = Math.max(0.65, Math.min(1.0, correctionFactor));

    // Adjust max width by the correction factor
    const adjustedMaxWidth = baseMaxWidth * clampedFactor;
    const adjustedMaxHeight = baseMaxHeight;

    // Calculate effective viewport aspect from adjusted bounds (in pixels)
    const maxWidthPx = (adjustedMaxWidth / 100) * viewportWidth;
    const maxHeightPx = (adjustedMaxHeight / 100) * viewportHeight;
    const effectiveViewportAspect = maxWidthPx / maxHeightPx;

    // Calculate container dimensions that preserve aspect ratio
    let containerWidth, containerHeight;

    if (imageAspect > effectiveViewportAspect) {
      // Wide image - width hits max first
      containerWidth = adjustedMaxWidth;
      containerHeight =
        (adjustedMaxWidth / imageAspect) * (viewportWidth / viewportHeight);
    } else {
      // Tall image - height hits max first
      containerHeight = adjustedMaxHeight;
      containerWidth =
        adjustedMaxHeight * imageAspect * (viewportHeight / viewportWidth);
    }

    // Apply container dimensions
    img.parentElement.style.width = `${containerWidth}vw`;
    img.parentElement.style.height = `${containerHeight}vh`;

    // Shift the image's visual center away from the gradient's faded left and
    // bottom edges. The offset scales with its rendered shorter edge so it
    // remains proportional for portrait, landscape, and square images.
    const shortEdgePx = Math.min(
      (containerWidth / 100) * viewportWidth,
      (containerHeight / 100) * viewportHeight
    );
    img.parentElement.style.setProperty(
      "--image-edge-offset",
      `${shortEdgePx * 0.2}px`
    );

    // Calculate mask ellipse based on aspect ratio
    let horizontalRadius, verticalRadius;

    if (imageAspect > 1) {
      horizontalRadius = Math.min(95, 80 + (imageAspect - 1) * 10);
      verticalRadius = 80;
    } else {
      horizontalRadius = 80;
      verticalRadius = Math.min(98, 85 + (1 / imageAspect - 1) * 10);
    }

    const maskImage = `radial-gradient(
      ellipse ${horizontalRadius}% ${verticalRadius}% at 85% 15%,
      rgba(0, 0, 0, 1) 50%,
      rgba(0, 0, 0, 0.98) 65%,
      rgba(0, 0, 0, 0.85) 78%,
      rgba(0, 0, 0, 0.5) 88%,
      rgba(0, 0, 0, 0) 97%
    )`;

    img.style.maskImage = maskImage;
    img.style.webkitMaskImage = maskImage;
  }

  function handleThumbnailLoad(event, imageUrl) {
    const img = event.target;
    if (!img || !img.naturalWidth || !img.naturalHeight) {
      handleThumbnailError(imageUrl);
      return;
    }
    const currentLoadGeneration = imageLoadGeneration;

    applyImageLayout(img);

    requestAnimationFrame(() => {
      if (currentLoadGeneration === imageLoadGeneration) {
        markImageLoaded(imageUrl);
      }
    });
  }

  let imagesContainer = null;
  let imageResizeTimeout = null;

  function handleWindowResize() {
    if (imageResizeTimeout) clearTimeout(imageResizeTimeout);
    imageResizeTimeout = setTimeout(() => {
      imageResizeTimeout = null;
      if (!imagesContainer) return;
      for (const img of imagesContainer.querySelectorAll("img")) {
        if (img.naturalWidth && img.naturalHeight) {
          applyImageLayout(img);
        }
      }
    }, 150);
  }

  onDestroy(() => {
    if (imageResizeTimeout) clearTimeout(imageResizeTimeout);
  });
</script>

<svelte:window on:resize={handleWindowResize} />

{#if validImages.length > 0}
  <div class="event-images" bind:this={imagesContainer}>
    {#each validImages as imageData}
      {@const imgUrl =
        typeof imageData === "string" ? imageData : imageData.url}
      {@const imgObj =
        typeof imageData === "string"
          ? { url: imageData, caption: null, source: null }
          : imageData}
      <button
        type="button"
        class="image-thumbnail"
        class:image-visible={isActive && loadedImageUrls.has(imgUrl)}
        class:image-failed={failedImageUrls.has(imgUrl)}
        on:click={() => onEnlargeImage(imgObj, slide)}
        aria-label={$_("story.enlarge_image")}
      >
        {#if !loadedImageUrls.has(imgUrl) && !failedImageUrls.has(imgUrl)}
          <span class="image-loading" aria-hidden="true">
            <span class="spinner"></span>
          </span>
        {/if}
        <img
          src={getThumbnailUrl(imgUrl, 400)}
          srcset={`${getThumbnailUrl(imgUrl, 400)} 1x, ${getThumbnailUrl(imgUrl, 800)} 2x`}
          alt=""
          loading="lazy"
          decoding="async"
          on:load={(event) => handleThumbnailLoad(event, imgUrl)}
          on:error={() => handleThumbnailError(imgUrl)}
        />
        <span class="enlarge-icon">
          <svg
            class="icon"
            viewBox="0 0 24 24"
            role="presentation"
            aria-hidden="true"
          >
            <path d={mdiMagnifyPlusOutline} />
          </svg>
        </span>
      </button>
    {/each}
  </div>
{/if}

<div class="content event-content">
  <div class="event-header">
    <div class="date-wrapper">
      <p class="date">{dateLabel}</p>
      {#if formatAgeLabel(slide.age)}
        {#if styleConfig?.separatorGlyphDataUrl}
          <span class="separator glyph-separator" aria-hidden="true"></span>
        {:else}
          <span class="separator">·</span>
        {/if}
        <p class="age">{formatAgeLabel(slide.age)}</p>
      {/if}
      {#if dateNote}
        <button
          type="button"
          class="date-info-btn"
          on:click|stopPropagation={() => onToggleDateNote(slide.eventIndex)}
          aria-label={$_("story.show_date_explanation")}
          aria-expanded={visibleDateNote === slide.eventIndex}
        >
          <svg
            class="icon icon-inline"
            viewBox="0 0 24 24"
            role="presentation"
            aria-hidden="true"
          >
            <path d={mdiInformationOutline} />
          </svg>
        </button>
        {#if visibleDateNote === slide.eventIndex}
          <div class="date-note-tooltip">
            {dateNote}
          </div>
        {/if}
      {/if}
    </div>
    <h2>{slide.title}</h2>
    {#if eventClassIcon && eventClassLabel && slide.event_class?.type !== "invention" && slide.event_class?.type !== "marriage_partnership" && slide.event_class?.type !== "publication"}
      <div class="event-class-badge">
        <svg
          class="icon icon-inline"
          viewBox="0 0 24 24"
          role="presentation"
          aria-hidden="true"
        >
          <path d={eventClassIcon} />
        </svg>
        <span class="event-class-label">{eventClassLabel}</span>
      </div>
    {/if}
  </div>
  <div class="event-body">
    <div class="event-description">
      {#if slide.event_class?.type === "marriage_partnership"}
        {@const partnerPerson = findPersonInNetwork(
          slide.event_class.partner,
          egoNetwork
        )}
        <div class="marriage-pretext">
          <div class="marriage-meta-line">
            <svg
              class="icon marriage-icon-inline"
              viewBox="0 0 24 24"
              role="presentation"
              aria-hidden="true"
            >
              <path d={mdiRing} />
            </svg>
            <span class="marriage-inline-label"
              >{slide.event_class.subtype === "marriage"
                ? "Marriage"
                : "Partnership"}</span
            >
            {#if slide.event_class.characterization}
              <span class="marriage-separator">·</span>
              <span class="marriage-characterization-inline"
                >{slide.event_class.characterization}</span
              >
            {/if}
            {#if slide.event_class.children}
              <span class="marriage-separator">·</span>
              <span class="marriage-children-inline"
                >{slide.event_class.children}
                {slide.event_class.children === 1 ? "child" : "children"}</span
              >
            {/if}
            {#if slide.event_class.duration}
              <span class="marriage-separator">·</span>
              <span class="marriage-duration-inline"
                >{slide.event_class.duration}</span
              >
            {/if}
          </div>
          {#if partnerPerson}
            {@const personKey = `${slide.eventIndex}-partner`}
            {@const subcategory = getSubcategory(
              partnerPerson.relationship_type
            )}
            <div class="marriage-partner-chips">
              <PersonChip
                person={partnerPerson}
                {personKey}
                {visiblePersonInfo}
                {subcategory}
                {styleConfig}
                onToggle={onTogglePersonInfo}
                {onOpenNetwork}
              />
            </div>
          {/if}
        </div>
      {/if}
      <p class="description">
        {#each descriptionSegments as segment}{#if segment.type === "text"}{segment.content}{:else if segment.type === "annotation"}<span
              role="button"
              tabindex="0"
              class="annotated-term"
              data-term-key={segment.termKey}
              on:click|stopPropagation={() =>
                handleAnnotationClick(segment.termKey, segment)}
              on:keydown={(e) =>
                (e.key === "Enter" || e.key === " ") &&
                handleAnnotationClick(segment.termKey, segment)}
              aria-expanded={annotationVisibilityMap[segment.termKey]}
              aria-label={$_("story.show_explanation")}
              >{segment.displayText}<span
                class="annotation-indicator"
                aria-hidden="true">?</span
              ></span
            >{:else if segment.type === "person"}<strong class="person-mention"
              >{segment.content}</strong
            >{/if}{/each}
      </p>
      {#each descriptionSegments.filter((s) => s.type === "annotation" && annotationVisibilityMap[s.termKey]) as segment (segment.termKey)}
        <div class="annotation-popup-container">
          <div class="annotation-popup">
            <span class="annotation-term-label">{segment.displayText}:</span>
            {segment.annotation.explanation}
            {#if segment.annotation.wikipedia_url}
              <a
                href={segment.annotation.wikipedia_url}
                target="_blank"
                rel="noreferrer"
                class="annotation-link">{$_("story.read_more")}</a
              >
            {/if}
          </div>
        </div>
      {/each}
      {#if slide.event_class?.type === "invention"}
        <div class="invention-info-box">
          <div class="invention-header">
            <svg
              class="icon invention-icon"
              viewBox="0 0 24 24"
              role="presentation"
              aria-hidden="true"
            >
              <path d={mdiLightbulbOnOutline} />
            </svg>
            <h3 class="invention-title">{slide.event_class.title}</h3>
          </div>
          {#if slide.event_class.description}
            <p class="invention-description">{slide.event_class.description}</p>
          {/if}
          {#if slide.event_class.impact}
            <div class="invention-impact">
              <span class="impact-label">Impact:</span><span
                class="impact-text"
              >
                {slide.event_class.impact}</span
              >
            </div>
          {/if}
        </div>
      {/if}
      {#if slide.event_class?.type === "publication"}
        <div class="publication-info-box">
          <div class="publication-header">
            <svg
              class="icon publication-icon"
              viewBox="0 0 24 24"
              role="presentation"
              aria-hidden="true"
            >
              <path d={mdiBook} />
            </svg>
            <h3 class="publication-title">{slide.event_class.title}</h3>
          </div>
          <div class="publication-meta">
            <span class="publication-type-badge"
              >{slide.event_class.publication_type || "Publication"}</span
            >
            {#if slide.event_class.significance}
              <span class="publication-separator">·</span>
              <span class="publication-significance"
                >{slide.event_class.significance}</span
              >
            {/if}
          </div>
          {#if slide.event_class.impact}
            <div class="publication-impact">
              <span class="impact-label">Impact:</span><span
                class="impact-text"
              >
                {slide.event_class.impact}</span
              >
            </div>
          {/if}
        </div>
      {/if}
    </div>
    <div class="event-details">
      {#if slide.event_class?.type === "marriage_partnership" && relevantPeople.length > 0}
        {@const partnerPerson = findPersonInNetwork(
          slide.event_class.partner,
          egoNetwork
        )}
        {@const otherPeople = partnerPerson
          ? relevantPeople.filter(
              (p) => p.person_name !== partnerPerson.person_name
            )
          : relevantPeople}
        {#if otherPeople.length > 0}
          <ul class="details">
            <li>
              <span class="label" aria-label="People">
                <svg
                  class="icon icon-inline"
                  viewBox="0 0 24 24"
                  role="presentation"
                  aria-hidden="true"
                >
                  <path d={mdiAccountOutline} />
                </svg>
              </span>
              <div class="people-list">
                {#each otherPeople as person, idx (person.person_name)}
                  {@const personKey = `${slide.eventIndex}-other-${idx}`}
                  {@const subcategory = getSubcategory(
                    person.relationship_type
                  )}
                  <PersonChip
                    {person}
                    {personKey}
                    {visiblePersonInfo}
                    {subcategory}
                    {styleConfig}
                    onToggle={onTogglePersonInfo}
                    {onOpenNetwork}
                  />
                {/each}
              </div>
            </li>
          </ul>
        {/if}
      {:else if relevantPeople.length > 0}
        <ul class="details">
          <li>
            <span class="label" aria-label="People">
              <svg
                class="icon icon-inline"
                viewBox="0 0 24 24"
                role="presentation"
                aria-hidden="true"
              >
                <path d={mdiAccountOutline} />
              </svg>
            </span>
            <div class="people-list">
              {#each relevantPeople as person, idx (person.person_name)}
                {@const personKey = `${slide.eventIndex}-${idx}`}
                {@const subcategory = getSubcategory(person.relationship_type)}
                <PersonChip
                  {person}
                  {personKey}
                  {visiblePersonInfo}
                  {subcategory}
                  {styleConfig}
                  onToggle={onTogglePersonInfo}
                  {onOpenNetwork}
                />
              {/each}
            </div>
          </li>
        </ul>
      {/if}
    </div>
  </div>
</div>

<style>
  .content {
    display: flex;
    flex-direction: column;
    gap: 0.8rem;
    position: relative;
    z-index: 4;
    align-self: center;
    width: min(54rem, 100%);
    margin: 0 auto;
    pointer-events: none;
  }

  .event-content {
    display: flex;
    flex-direction: column;
    padding-top: clamp(0rem, 8vh, 10rem);
  }

  .event-header {
    width: 100%;
    flex-shrink: 0;
  }

  .event-class-badge {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.4rem 0.75rem;
    margin-top: 0.5rem;
    background: rgba(255, 255, 255, 0.1);
    backdrop-filter: blur(8px);
    border: 1px solid rgba(255, 255, 255, 0.2);
    border-radius: 999px;
    font-size: 0.8rem;
    font-weight: 600;
    color: var(--story-secondary, #38bdf8);
    text-shadow:
      0 2px 8px rgba(0, 0, 0, 0.8),
      0 1px 4px rgba(0, 0, 0, 0.9);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
    transition: all 0.2s ease;
    pointer-events: none;
  }

  .event-class-badge .icon {
    width: 1em;
    height: 1em;
    fill: currentColor;
  }

  .event-class-label {
    font-family: var(--story-body-font, Inter, sans-serif);
    letter-spacing: 0.02em;
  }

  .event-body {
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
    flex-shrink: 0;
  }

  .event-description {
    width: 100%;
    position: relative;
  }

  .invention-info-box {
    width: 100%;
    background: rgba(255, 255, 255, 0.05);
    backdrop-filter: blur(12px);
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-left: 3px solid var(--story-secondary, #38bdf8);
    border-radius: 0.5rem;
    padding: 0.75rem;
    margin-top: 0.75rem;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
    pointer-events: auto;
  }

  .invention-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.4rem;
  }

  .invention-icon {
    width: 1.25rem;
    height: 1.25rem;
    fill: var(--story-secondary, #38bdf8);
    flex-shrink: 0;
  }

  .invention-title {
    margin: 0;
    font-size: 1rem;
    font-weight: 700;
    color: var(--story-primary, #f8fafc);
    font-family: var(--story-heading-font, Inter, sans-serif);
    text-shadow:
      0 2px 8px rgba(0, 0, 0, 0.8),
      0 1px 4px rgba(0, 0, 0, 0.9);
  }

  .invention-description {
    margin: 0 0 0.4rem 0;
    font-size: 0.85rem;
    line-height: 1.5;
    color: rgba(226, 232, 240, 0.95);
    font-family: var(--story-body-font, Inter, sans-serif);
    text-shadow:
      0 2px 8px rgba(0, 0, 0, 0.8),
      0 1px 4px rgba(0, 0, 0, 0.9);
  }

  .invention-impact {
    margin-top: 0.4rem;
    padding-top: 0.4rem;
    border-top: 1px solid rgba(255, 255, 255, 0.1);
    line-height: 1.5;
  }

  .impact-label {
    display: inline;
    font-size: 0.75rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--story-secondary, #38bdf8);
    font-family: var(--story-body-font, Inter, sans-serif);
    text-shadow:
      0 2px 8px rgba(0, 0, 0, 0.8),
      0 1px 4px rgba(0, 0, 0, 0.9);
  }

  .impact-text {
    display: inline;
    font-size: 0.8rem;
    line-height: 1.6;
    color: rgba(226, 232, 240, 0.9);
    font-family: var(--story-body-font, Inter, sans-serif);
    font-style: italic;
    text-shadow:
      0 2px 8px rgba(0, 0, 0, 0.8),
      0 1px 4px rgba(0, 0, 0, 0.9);
  }

  .publication-info-box {
    width: 100%;
    background: rgba(255, 255, 255, 0.05);
    backdrop-filter: blur(12px);
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-left: 3px solid var(--story-secondary, #38bdf8);
    border-radius: 0.5rem;
    padding: 0.75rem;
    margin-top: 0.75rem;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
    pointer-events: auto;
  }

  .publication-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.5rem;
  }

  .publication-icon {
    width: 1.25rem;
    height: 1.25rem;
    fill: var(--story-secondary, #38bdf8);
    flex-shrink: 0;
  }

  .publication-title {
    margin: 0;
    font-size: 1rem;
    font-weight: 700;
    color: var(--story-primary, #f8fafc);
    font-family: var(--story-heading-font, Inter, sans-serif);
    text-shadow:
      0 2px 8px rgba(0, 0, 0, 0.8),
      0 1px 4px rgba(0, 0, 0, 0.9);
  }

  .publication-meta {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 0.4rem;
    margin-bottom: 0.5rem;
    font-size: 0.85rem;
    line-height: 1.5;
    color: rgba(226, 232, 240, 0.9);
    font-family: var(--story-body-font, Inter, sans-serif);
    text-shadow:
      0 2px 8px rgba(0, 0, 0, 0.8),
      0 1px 4px rgba(0, 0, 0, 0.9);
  }

  .publication-type-badge {
    display: inline-flex;
    align-items: center;
    padding: 0.2rem 0.5rem;
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 999px;
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: capitalize;
    color: var(--story-secondary, #38bdf8);
    letter-spacing: 0.02em;
  }

  .publication-separator {
    color: rgba(148, 163, 184, 0.6);
    font-size: 0.9em;
  }

  .publication-significance {
    font-style: italic;
    color: rgba(226, 232, 240, 0.85);
    text-transform: capitalize;
  }

  .publication-impact {
    margin-top: 0.4rem;
    padding-top: 0.4rem;
    border-top: 1px solid rgba(255, 255, 255, 0.1);
    line-height: 1.5;
  }

  .marriage-pretext {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    margin-bottom: 0.75rem;
    padding: 0.75rem;
    background: rgba(255, 255, 255, 0.05);
    backdrop-filter: blur(8px);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-left: 3px solid var(--story-secondary, #38bdf8);
    border-radius: 0.5rem;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
  }

  .marriage-meta-line {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 0.4rem;
    font-size: 0.85rem;
    line-height: 1.5;
    color: rgba(226, 232, 240, 0.9);
    font-family: var(--story-body-font, Inter, sans-serif);
    text-shadow:
      0 2px 8px rgba(0, 0, 0, 0.8),
      0 1px 4px rgba(0, 0, 0, 0.9);
  }

  .marriage-icon-inline {
    width: 1em;
    height: 1em;
    fill: var(--story-secondary, #38bdf8);
    flex-shrink: 0;
  }

  .marriage-inline-label {
    font-weight: 600;
    color: var(--story-secondary, #38bdf8);
  }

  .marriage-separator {
    color: rgba(148, 163, 184, 0.6);
    font-size: 0.9em;
  }

  .marriage-characterization-inline {
    font-style: italic;
    color: rgba(226, 232, 240, 0.85);
  }

  .marriage-children-inline,
  .marriage-duration-inline {
    color: rgba(226, 232, 240, 0.85);
  }

  .marriage-partner-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
  }

  .event-details {
    width: 100%;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  @media (orientation: landscape) {
    .event-body {
      display: grid;
      grid-template-columns: 2fr 1fr;
      gap: 1.5rem;
      align-items: start;
    }

    .event-description {
      grid-column: 1;
    }

    .event-details {
      grid-column: 2;
    }
  }

  .event-images {
    position: absolute;
    top: 0;
    right: 0;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    z-index: 3;
  }

  .image-thumbnail {
    --image-edge-offset: 0px;
    appearance: none;
    border: none;
    padding: 0;
    margin: 0;
    cursor: pointer;
    display: block;
    position: relative;
    /* Fallback values before JavaScript runs - updated to match new max bounds */
    max-width: 75vw;
    max-height: 75vh;
    width: 60vw;
    height: 60vh;
    border-radius: 0;
    overflow: hidden;
    background: transparent;
    box-shadow: none;
    transform: translate(
      var(--image-edge-offset),
      calc(-1 * var(--image-edge-offset))
    );
  }

  .image-thumbnail:focus {
    outline: none;
  }

  .image-thumbnail img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    object-position: top right;
    display: block;
    filter: saturate(0.35) contrast(0.6) brightness(0.82);
    opacity: 0;
    transition: opacity 180ms ease-out;
    mask-image: radial-gradient(
      ellipse 85% 85% at 85% 15%,
      rgba(0, 0, 0, 1) 50%,
      rgba(0, 0, 0, 0.98) 65%,
      rgba(0, 0, 0, 0.85) 78%,
      rgba(0, 0, 0, 0.5) 88%,
      rgba(0, 0, 0, 0) 97%
    );
    -webkit-mask-image: radial-gradient(
      ellipse 85% 85% at 85% 15%,
      rgba(0, 0, 0, 1) 50%,
      rgba(0, 0, 0, 0.98) 65%,
      rgba(0, 0, 0, 0.85) 78%,
      rgba(0, 0, 0, 0.5) 88%,
      rgba(0, 0, 0, 0) 97%
    );
  }

  .image-thumbnail.image-visible img {
    opacity: 1;
    transition: opacity 300ms ease-in 100ms;
  }

  .image-thumbnail.image-failed {
    display: none;
  }

  .image-loading {
    position: absolute;
    top: 0.5rem;
    right: 0.5rem;
    width: 1.25rem;
    height: 1.25rem;
    display: grid;
    place-items: center;
    pointer-events: none;
    z-index: 1;
  }

  .spinner {
    width: 100%;
    height: 100%;
    border: 2px solid rgba(248, 250, 252, 0.2);
    border-top-color: var(--story-secondary, #38bdf8);
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
  }

  .enlarge-icon {
    position: absolute;
    bottom: 0.25rem;
    right: 0;
    width: 1.5rem;
    height: 1.5rem;
    background: rgba(15, 23, 42, 0.8);
    border-radius: 0.25rem;
    display: flex;
    align-items: center;
    justify-content: center;
    pointer-events: none;
    opacity: 0;
    transition: opacity 0.2s ease;
  }

  .image-thumbnail.image-visible .enlarge-icon {
    opacity: 1;
  }

  .enlarge-icon .icon {
    width: 1rem;
    height: 1rem;
    fill: var(--story-primary, #f8fafc);
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }

  .date {
    margin: 0;
    font-size: 0.9rem;
    color: var(--story-secondary, #38bdf8);
    font-weight: 600;
    text-shadow:
      0 2px 8px rgba(0, 0, 0, 0.8),
      0 1px 4px rgba(0, 0, 0, 0.9);
  }

  .date-wrapper {
    position: relative;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .date-wrapper .separator {
    color: rgba(148, 163, 184, 0.8);
    flex: 0 0 auto;
  }

  .date-wrapper .separator.glyph-separator {
    width: 0.9em;
    height: 0.9em;
    display: inline-block;
    background-image: var(--story-separator-glyph);
    background-size: contain;
    background-repeat: no-repeat;
    background-position: center;
    opacity: 0.6;
    vertical-align: middle;
    flex-shrink: 0;
  }

  .date-info-btn {
    appearance: none;
    border: none;
    background: rgba(255, 255, 255, 0.08);
    color: var(--story-secondary, #38bdf8);
    padding: 0.25rem;
    border-radius: 50%;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    transition:
      background-color 0.2s ease,
      color 0.2s ease,
      transform 0.2s ease;
    flex: 0 0 auto;
    width: 1.5rem;
    height: 1.5rem;
    pointer-events: auto;
  }

  .date-info-btn:hover,
  .date-info-btn:focus {
    background: rgba(255, 255, 255, 0.15);
    color: var(--story-primary, #f8fafc);
    transform: scale(1.1);
    outline: none;
  }

  .date-info-btn[aria-expanded="true"] {
    background: rgba(255, 255, 255, 0.2);
    color: var(--story-primary, #f8fafc);
  }

  .date-note-tooltip {
    position: absolute;
    top: calc(100% + 0.5rem);
    left: 0;
    right: 0;
    background: rgba(15, 23, 42, 0.95);
    backdrop-filter: blur(8px);
    border: 1px solid rgba(148, 163, 184, 0.3);
    border-radius: 0.5rem;
    padding: 0.75rem 1rem;
    font-size: 0.85rem;
    color: #e2e8f0;
    line-height: 1.5;
    box-shadow: 0 8px 20px rgba(0, 0, 0, 0.4);
    z-index: 10;
    animation: fadeInTooltip 0.2s ease;
  }

  @keyframes fadeInTooltip {
    from {
      opacity: 0;
      transform: translateY(-0.5rem);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  .age {
    margin: 0;
    font-size: 0.85rem;
    color: rgba(148, 163, 184, 0.85);
    font-family: var(--story-body-font, Inter, sans-serif);
    text-shadow:
      0 2px 8px rgba(0, 0, 0, 0.8),
      0 1px 4px rgba(0, 0, 0, 0.9);
  }

  h2 {
    margin: 0;
    font-size: 1.35rem;
    line-height: 1.25;
    color: var(--story-primary, #f8fafc);
    font-family: var(--story-heading-font, Inter, sans-serif);
    text-shadow:
      0 2px 8px rgba(0, 0, 0, 0.8),
      0 1px 4px rgba(0, 0, 0, 0.9);
  }

  .description {
    margin: 0;
    font-size: 0.9rem;
    color: #e2e8f0;
    font-family: var(--story-body-font, Inter, sans-serif);
    text-shadow:
      0 2px 8px rgba(0, 0, 0, 0.8),
      0 1px 4px rgba(0, 0, 0, 0.9);
  }

  .icon {
    width: 1.1em;
    height: 1.1em;
    fill: currentColor;
    flex: 0 0 auto;
  }

  .icon-inline {
    width: 1em;
    height: 1em;
  }

  .label .icon-inline {
    width: 1.15em;
    height: 1.15em;
  }

  .details {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    font-size: 0.85rem;
    font-family: var(--story-body-font, Inter, sans-serif);
    text-shadow:
      0 2px 8px rgba(0, 0, 0, 0.8),
      0 1px 4px rgba(0, 0, 0, 0.9);
  }

  .details li {
    display: flex;
    flex-direction: row;
    gap: 0.5rem;
    align-items: baseline;
  }

  .details li > span:not(.label),
  .details li > div {
    flex: 1;
    min-width: 0;
  }

  .label {
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.7rem;
    color: rgba(148, 163, 184, 0.76);
    font-family: var(--story-body-font, Inter, sans-serif);
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    flex-shrink: 0;
  }

  .people-list {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
  }

  /* Tablet and desktop styles */
  @media (min-width: 768px) and (min-height: 600px) {
    h2 {
      font-size: 1.85rem;
    }

    .event-class-badge {
      font-size: 0.9rem;
      padding: 0.5rem 0.9rem;
      margin-top: 0.75rem;
    }

    .invention-info-box {
      padding: 1.5rem;
      margin-top: 1.25rem;
    }

    .invention-title {
      font-size: 1.25rem;
    }

    .invention-description {
      font-size: 1rem;
    }

    .impact-text {
      font-size: 0.95rem;
    }

    .publication-info-box {
      padding: 1.5rem;
      margin-top: 1.25rem;
    }

    .publication-title {
      font-size: 1.25rem;
    }

    .publication-meta {
      font-size: 0.95rem;
    }

    .publication-type-badge {
      font-size: 0.8rem;
    }

    .marriage-pretext {
      padding: 1rem;
    }

    .marriage-meta-line {
      font-size: 0.95rem;
    }

    .description {
      font-size: 1.05rem;
    }

    .details {
      font-size: 0.9rem;
      flex-direction: column;
      max-width: none;
      width: 100%;
    }

    .event-images {
      top: 0;
      right: 0;
    }

    .image-thumbnail img {
      filter: saturate(0.35) contrast(0.6) brightness(0.82);
      mask-image: radial-gradient(
        ellipse 75% 75% at 85% 15%,
        rgba(0, 0, 0, 1) 50%,
        rgba(0, 0, 0, 0.98) 65%,
        rgba(0, 0, 0, 0.85) 78%,
        rgba(0, 0, 0, 0.5) 88%,
        rgba(0, 0, 0, 0) 97%
      );
      -webkit-mask-image: radial-gradient(
        ellipse 75% 75% at 85% 15%,
        rgba(0, 0, 0, 1) 50%,
        rgba(0, 0, 0, 0.98) 65%,
        rgba(0, 0, 0, 0.85) 78%,
        rgba(0, 0, 0, 0.5) 88%,
        rgba(0, 0, 0, 0) 97%
      );
    }

    .enlarge-icon {
      width: 1.75rem;
      height: 1.75rem;
    }

    .enlarge-icon .icon {
      width: 1.15rem;
      height: 1.15rem;
    }
  }

  /* Annotation styles */
  .annotated-term {
    all: unset;
    display: inline;
    white-space: normal;
    color: var(--story-secondary, #38bdf8);
    text-decoration: underline;
    text-decoration-style: dotted;
    text-underline-offset: 2px;
    cursor: help;
    font: inherit;
    line-height: inherit;
    position: relative;
    transition: color 0.2s ease;
    -webkit-user-select: text;
    user-select: text;
    pointer-events: auto;
  }

  .annotated-term:hover,
  .annotated-term:focus {
    color: var(--story-primary, #f8fafc);
    outline: none;
  }

  .annotation-indicator {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 0.9em;
    height: 0.9em;
    border-radius: 50%;
    background: rgba(56, 189, 248, 0.2);
    font-size: 0.7em;
    font-weight: 700;
    margin-left: 0.15em;
    vertical-align: super;
    line-height: 1;
  }

  .annotation-popup-container {
    position: absolute;
    top: 100%;
    left: 0;
    right: 0;
    z-index: 100;
  }

  .annotation-popup {
    position: relative;
    margin-top: 0.5rem;
    min-width: 200px;
    max-width: 100%;
    background: rgba(15, 23, 42, 0.98);
    backdrop-filter: blur(12px);
    border: 1px solid rgba(148, 163, 184, 0.4);
    border-radius: 0.5rem;
    padding: 0.75rem 1rem;
    font-size: 0.85rem;
    color: #e2e8f0;
    line-height: 1.5;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5);
    z-index: 100;
    animation: fadeInTooltip 0.2s ease;
    text-align: left;
    pointer-events: auto;
    white-space: normal;
    text-decoration: none;
  }

  .annotation-term-label {
    font-weight: 600;
    color: var(--story-secondary, #38bdf8);
  }

  .annotation-link {
    display: block;
    margin-top: 0.5rem;
    color: var(--story-secondary, #38bdf8);
    text-decoration: none;
    font-size: 0.8rem;
    font-weight: 500;
    transition: color 0.2s ease;
  }

  .annotation-link:hover {
    color: var(--story-primary, #f8fafc);
    text-decoration: underline;
  }

  /* Person name highlighting */
  .person-mention {
    font-weight: bold;
    text-shadow: 0 0 4px var(--story-secondary, rgba(56, 189, 248, 0.25));
  }

  /* Responsive positioning */
  @media (max-width: 768px) {
    .annotation-popup {
      max-width: 100%;
    }
  }

  /* Landscape mobile optimizations for short viewports */
  @media (max-height: 450px) {
    .event-header {
      display: flex;
      flex-direction: row;
      align-items: baseline;
      gap: 0.75rem;
      flex-wrap: wrap;
    }

    /* Title first, date second */
    .event-header h2 {
      order: 1;
    }

    .event-header .date-wrapper {
      order: 2;
    }

    .date-wrapper {
      flex-shrink: 0;
    }

    h2 {
      font-size: 1.1rem;
      margin: 0;
      flex-shrink: 1;
      min-width: 0;
    }

    .date {
      font-size: 0.8rem;
    }

    .age {
      font-size: 0.75rem;
    }

    .description {
      font-size: 0.8rem;
      max-height: 35vh;
    }

    .details {
      font-size: 0.75rem;
      gap: 0.5rem;
    }

    .label {
      font-size: 0.6rem;
    }

    .event-body {
      gap: 0.5rem;
    }

    .content {
      gap: 0.2rem;
    }
  }
</style>
