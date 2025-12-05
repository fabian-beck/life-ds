<script>
  import {
    mdiMapMarkerOutline,
    mdiLinkVariant,
    mdiInformationOutline,
    mdiWikipedia,
    mdiAccountOutline,
    mdiAccountMultipleOutline,
    mdiMagnifyPlusOutline,
  } from "@mdi/js";
  import { _ } from "../stores/language";
  import { joinWithSeparator } from "../utils/helpers.js";
  import {
    formatDate,
    getDateNote,
    getThumbnailUrl,
    getValidImages,
    sourceLabel,
    getSubcategory,
    getRelevantPeople,
  } from "../utils/storyHelpers.js";
  import PersonChip from "./PersonChip.svelte";

  export let slide = {};
  export let egoNetwork = null;
  export let styleConfig = null;
  export let formatters = {};
  export let visibleDateNote = null;
  export let visiblePersonInfo = null;
  export let visibleSources = null;
  export let visibleAnnotation = null;
  export let descriptionOverflows = new Set();
  export let onEnlargeImage = () => {};
  export let onToggleDateNote = () => {};
  export let onTogglePersonInfo = () => {};
  export let onToggleSources = () => {};
  export let onToggleAnnotation = () => {};
  export let onOpenNetwork = () => {};
  export let checkOverflow = () => {};

  $: UNKNOWN_LOCATION_LABEL = $_("story.location_unknown");
  $: validImages = getValidImages(slide.images);
  $: relevantPeople = getRelevantPeople(slide, egoNetwork);
  $: dateLabel = formatDate(slide, formatters);
  $: dateNote = getDateNote(slide);
  $: descriptionSegments = parseAnnotations(
    slide.description,
    slide.annotations
  );

  function formatAgeLabel(age) {
    if (age == null) return null;
    return age === 0 ? $_("story.at_birth") : $_("story.age", { age });
  }

  function formatLocations(locations = []) {
    if (!locations.length) return UNKNOWN_LOCATION_LABEL;

    // Extract historic names from location objects
    const names = locations
      .filter(loc => loc && loc.name_historic)
      .map(loc => loc.name_historic);

    if (names.length === 0) return UNKNOWN_LOCATION_LABEL;

    return joinWithSeparator(names, styleConfig);
  }

  function parseAnnotations(description, annotations = {}) {
    if (!annotations || Object.keys(annotations).length === 0) {
      return [{ type: 'text', content: description }];
    }

    const pattern = /\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g;
    const segments = [];
    let lastIndex = 0;
    let match;

    while ((match = pattern.exec(description)) !== null) {
      // Add text before annotation
      if (match.index > lastIndex) {
        segments.push({
          type: 'text',
          content: description.slice(lastIndex, match.index)
        });
      }

      const termKey = match[1];
      const displayText = match[2] || match[1];
      const annotation = annotations[termKey];

      if (annotation) {
        segments.push({
          type: 'annotation',
          termKey,
          displayText,
          annotation
        });
      } else {
        // Fallback if annotation missing
        segments.push({ type: 'text', content: displayText });
      }

      lastIndex = pattern.lastIndex;
    }

    // Add remaining text
    if (lastIndex < description.length) {
      segments.push({
        type: 'text',
        content: description.slice(lastIndex)
      });
    }

    return segments;
  }

  function handleThumbnailLoad(event) {
    const img = event.target;
    if (!img || !img.naturalWidth || !img.naturalHeight) return;

    const aspectRatio = img.naturalWidth / img.naturalHeight;
    let horizontalRadius, verticalRadius;

    if (aspectRatio > 1) {
      horizontalRadius = Math.min(95, 80 + (aspectRatio - 1) * 10);
      verticalRadius = 80;
    } else {
      horizontalRadius = 80;
      verticalRadius = Math.min(98, 85 + (1 / aspectRatio - 1) * 10);
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
</script>

{#if validImages.length > 0}
  <div class="event-images">
    {#each validImages as imageData}
      {@const imgUrl = typeof imageData === "string" ? imageData : imageData.url}
      {@const imgObj = typeof imageData === "string"
        ? { url: imageData, caption: null, source: null }
        : imageData}
      <button
        type="button"
        class="image-thumbnail"
        on:click={() => onEnlargeImage(imgObj, slide)}
        aria-label={$_("story.enlarge_image")}
      >
        <img
          src={getThumbnailUrl(imgUrl, 400)}
          srcset={`${getThumbnailUrl(imgUrl, 400)} 1x, ${getThumbnailUrl(imgUrl, 800)} 2x`}
          alt=""
          loading="lazy"
          decoding="async"
          on:load={handleThumbnailLoad}
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
  </div>
  <div class="event-body">
    <div class="event-description">
      <p
        class="description"
        class:has-fade={descriptionOverflows.has(slide.eventIndex)}
        use:checkOverflow={slide.eventIndex}
      >
{#each descriptionSegments as segment}{#if segment.type === 'text'}{segment.content}{:else if segment.type === 'annotation'}<button type="button" class="annotated-term" on:click|stopPropagation={() => onToggleAnnotation(segment.termKey)} aria-expanded={visibleAnnotation === segment.termKey} aria-label={$_('story.show_explanation')}>{segment.displayText}<span class="annotation-indicator" aria-hidden="true">?</span></button>{#if visibleAnnotation === segment.termKey}<span class="annotation-popup">{segment.annotation.explanation}{#if segment.annotation.wikipedia_url}<a href={segment.annotation.wikipedia_url} target="_blank" rel="noreferrer" class="annotation-link">{$_('story.read_more')}</a>{/if}</span>{/if}{/if}{/each}
      </p>
    </div>
    <div class="event-details">
      {#if relevantPeople.length > 0}
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
              {#each relevantPeople as person, idx}
                {@const personKey = `${slide.eventIndex}-${idx}`}
                {@const subcategory = getSubcategory(person.relationship_type)}
                <PersonChip
                  {person}
                  {personKey}
                  {visiblePersonInfo}
                  {subcategory}
                  onToggle={onTogglePersonInfo}
                />
              {/each}
              <button
                type="button"
                class="show-all-btn"
                on:click={onOpenNetwork}
                aria-label={$_("story.show_network")}
              >
                <svg
                  class="icon icon-inline"
                  viewBox="0 0 24 24"
                  role="presentation"
                  aria-hidden="true"
                >
                  <path d={mdiAccountMultipleOutline} />
                </svg>
              </button>
            </div>
          </li>
        </ul>
      {/if}
      {#if (slide.locations?.length && slide.locations.some(loc => loc.name_historic)) || slide.sources?.length}
        <ul class="details details-compact">
          <li>
            {#if slide.locations?.length && slide.locations.some(loc => loc.name_historic)}
              <span class="label" aria-label="Location">
                <svg
                  class="icon icon-inline"
                  viewBox="0 0 24 24"
                  role="presentation"
                  aria-hidden="true"
                >
                  <path d={mdiMapMarkerOutline} />
                </svg>
              </span>
              <span>{@html formatLocations(slide.locations)}</span>
            {/if}
            {#if slide.sources?.length}
              <div class="sources-wrapper">
                <span class="label" aria-label="Sources">
                  <svg
                    class="icon icon-inline"
                    viewBox="0 0 24 24"
                    role="presentation"
                    aria-hidden="true"
                  >
                    <path d={mdiLinkVariant} />
                  </svg>
                </span>
                <button
                  type="button"
                  class="sources-toggle-btn"
                  on:click|stopPropagation={() => onToggleSources(slide.eventIndex)}
                  aria-label={$_("story.show_sources")}
                  aria-expanded={visibleSources === slide.eventIndex}
                >
                  {slide.sources.length === 1
                    ? $_("story.source_one", { count: 1 })
                    : $_("story.source_other", { count: slide.sources.length })}
                  <svg
                    class="icon icon-inline"
                    viewBox="0 0 24 24"
                    role="presentation"
                    aria-hidden="true"
                  >
                    <path d={mdiInformationOutline} />
                  </svg>
                </button>
                {#if visibleSources === slide.eventIndex}
                  <div class="sources-popup">
                    <ul class="sources-list">
                      {#each slide.sources as source}
                        {@const sourceInfo = sourceLabel(source)}
                        <li>
                          <a
                            href={source}
                            target="_blank"
                            rel="noreferrer"
                            class="source-link"
                          >
                            {#if sourceInfo.isWikipedia}
                              <svg
                                class="icon icon-inline wiki-icon"
                                viewBox="0 0 24 24"
                                role="presentation"
                                aria-hidden="true"
                              >
                                <path d={mdiWikipedia} />
                              </svg>
                            {/if}
                            {sourceInfo.label}
                          </a>
                        </li>
                      {/each}
                    </ul>
                  </div>
                {/if}
              </div>
            {/if}
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
  }

  .event-content {
    display: flex;
    flex-direction: column;
  }

  .event-header {
    width: 100%;
    flex-shrink: 0;
  }

  .event-body {
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
    flex-shrink: 0;
  }

  .event-description {
    width: 100%;
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
      gap: 2rem;
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
    appearance: none;
    border: none;
    padding: 0;
    margin: 0;
    cursor: pointer;
    display: block;
    position: relative;
    width: 240px;
    height: 240px;
    border-radius: 0;
    overflow: hidden;
    background: transparent;
    box-shadow: none;
  }

  .image-thumbnail:focus {
    outline: none;
  }

  .image-thumbnail img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
    filter: saturate(0.35) contrast(0.6) brightness(0.82);
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
    opacity: 1;
    transition: opacity 0.2s ease;
  }

  .enlarge-icon .icon {
    width: 1rem;
    height: 1rem;
    fill: var(--story-primary, #f8fafc);
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
    max-height: 25vh;
    overflow-y: auto;
  }

  .description.has-fade {
    padding-bottom: 1.5em;
    padding-right: 0.5em;
    -webkit-mask-image: linear-gradient(
      to bottom,
      black calc(100% - 2em),
      transparent 100%
    );
    mask-image: linear-gradient(
      to bottom,
      black calc(100% - 2em),
      transparent 100%
    );
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

  .details.details-compact li {
    display: flex;
    flex-direction: row;
    flex-wrap: wrap;
    gap: 0.75rem;
    align-items: center;
  }

  .details li > span:not(.label),
  .details li > div {
    flex: 1;
    min-width: 0;
  }

  .details.details-compact li > span:not(.label) {
    flex: 0 1 auto;
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

  .show-all-btn {
    appearance: none;
    border: 1px solid var(--story-primary, rgba(148, 163, 184, 0.3));
    background: rgba(255, 255, 255, 0.05);
    color: var(--story-primary, #e2e8f0);
    padding: 0.35rem 0.65rem;
    border-radius: 999px;
    font-size: 0.75rem;
    font-weight: 600;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    transition:
      background-color 0.2s ease,
      border-color 0.2s ease,
      transform 0.2s ease;
  }

  .show-all-btn:hover,
  .show-all-btn:focus {
    background: rgba(255, 255, 255, 0.12);
    border-color: var(--story-primary, rgba(148, 163, 184, 0.6));
    transform: translateY(-1px);
    outline: none;
  }

  .sources-wrapper {
    position: relative;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex: 1;
    min-width: 0;
  }

  .sources-toggle-btn {
    appearance: none;
    border: none;
    background: rgba(255, 255, 255, 0.08);
    color: var(--story-secondary, #38bdf8);
    padding: 0.35rem 0.65rem;
    border-radius: 999px;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 0.35rem;
    font-size: 0.75rem;
    font-weight: 500;
    transition:
      background-color 0.2s ease,
      color 0.2s ease,
      transform 0.2s ease;
    flex-shrink: 0;
  }

  .sources-toggle-btn:hover,
  .sources-toggle-btn:focus {
    background: rgba(255, 255, 255, 0.15);
    color: var(--story-primary, #f8fafc);
    transform: scale(1.05);
    outline: none;
  }

  .sources-toggle-btn[aria-expanded="true"] {
    background: rgba(255, 255, 255, 0.2);
    color: var(--story-primary, #f8fafc);
  }

  .sources-popup {
    position: absolute;
    top: calc(100% + 0.5rem);
    left: 0;
    right: 0;
    background: rgba(15, 23, 42, 0.95);
    backdrop-filter: blur(8px);
    border: 1px solid rgba(148, 163, 184, 0.3);
    border-radius: 0.5rem;
    padding: 0.75rem;
    box-shadow: 0 8px 20px rgba(0, 0, 0, 0.4);
    z-index: 10;
    animation: fadeInTooltip 0.2s ease;
    max-height: 200px;
    overflow-y: auto;
  }

  .sources-list {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .sources-list li {
    display: block;
  }

  .source-link {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    color: rgba(148, 163, 184, 0.85);
    text-decoration: none;
    font-weight: 400;
    font-size: 0.8rem;
    transition: color 0.2s ease;
    word-break: break-word;
  }

  .source-link:hover,
  .source-link:focus {
    color: var(--story-secondary, #94a3b8);
    text-decoration: underline;
  }

  .wiki-icon {
    opacity: 0.7;
    flex-shrink: 0;
  }

  /* Tablet and desktop styles */
  @media (min-width: 768px) and (min-height: 600px) {
    h2 {
      font-size: 1.85rem;
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

    .image-thumbnail {
      width: min(380px, 35vw);
      height: min(380px, 35vh);
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

  .annotation-popup {
    position: absolute;
    top: calc(100% + 0.5rem);
    left: 50%;
    transform: translateX(-50%);
    min-width: 200px;
    max-width: 300px;
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

  /* Responsive positioning */
  @media (max-width: 768px) {
    .annotation-popup {
      left: 0;
      right: 0;
      transform: none;
      max-width: none;
    }
  }
</style>
