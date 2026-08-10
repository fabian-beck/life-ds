<script>
  import { mdiMapMarkerOutline } from "@mdi/js";
  import PersonChip from "./PersonChip.svelte";
  import { _ } from "../stores/language";
  import { extractYear, formatSingleDate } from "../utils/story/dates.js";
  import { getThumbnailUrl } from "../utils/story/images.js";
  import {
    getChapterPeople,
    getSubcategory,
  } from "../utils/story/personMatching.js";

  export let chapter = {};
  export let personStyle = null;
  export let egoNetwork = null;
  export let formatters = {};
  export let activeSlideIndex = -1; // Track active slide to close popups on navigation
  export let onOpenNetwork = null; // Callback to open the network modal

  let visiblePersonInfo = null;

  // Close person info popup when slide changes
  $: if (activeSlideIndex !== undefined) {
    visiblePersonInfo = null;
  }

  // Format date range for chapter
  $: dateLabel = (() => {
    if (!chapter) return "";

    const start = chapter.date_start;
    const end = chapter.date_end;

    // Date range - always use year precision for chapters. The full date
    // goes to the formatter (the shared parser handles BCE and unpadded
    // years); the numeric years only decide whether the range collapses.
    const startYear = extractYear(start);
    const endYear = extractYear(end);

    const startLabel = formatSingleDate(start, "year", formatters);
    const endLabel = formatSingleDate(end, "year", formatters);

    if (startLabel && endLabel && startYear !== endYear) {
      return `${startLabel} – ${endLabel}`;
    } else if (startLabel) {
      return startLabel;
    }
    return "";
  })();

  // Format age range for chapter
  $: ageLabel = (() => {
    if (!chapter) return "";

    const ageStart = chapter.age_start;
    const ageEnd = chapter.age_end;

    if (ageStart !== undefined && ageEnd !== undefined) {
      if (ageStart === 0) {
        return $_("story.at_birth") + ` – ${$_("story.age", { age: ageEnd })}`;
      } else {
        return $_("story.age", { age: ageStart }) + ` – ${ageEnd}`;
      }
    }
    return "";
  })();

  // The chapter's abstract illustration, when one has been generated. It is
  // decoration and carries no caption, so it is hidden from assistive
  // technology rather than given an alt text describing a metaphor.
  $: illustration = chapter?.illustration?.medium ? chapter.illustration : null;

  // Match involved people against ego network using shared fuzzy matching
  $: involvedPeople = getChapterPeople(chapter, egoNetwork).map((person) => ({
    ...person,
    personKey: person._originalName,
  }));

  function togglePersonInfo(personKey) {
    visiblePersonInfo = visiblePersonInfo === personKey ? null : personKey;
  }

  function handleClickOutside(event) {
    const personWrapper = event.target.closest(".person-info-wrapper");
    if (!personWrapper && visiblePersonInfo !== null) {
      visiblePersonInfo = null;
    }
  }
</script>

<div
  class="content chapter-content"
  class:with-illustration={illustration}
  on:click={handleClickOutside}
  on:keydown={(e) =>
    e.key === "Escape" && visiblePersonInfo && (visiblePersonInfo = null)}
  role="presentation"
>
  <div class="chapter-box">
    {#if illustration}
      <img
        class="chapter-illustration"
        src={getThumbnailUrl(illustration, 400)}
        srcset={`${getThumbnailUrl(illustration, 400)} 1x, ${getThumbnailUrl(illustration, 800)} 2x`}
        alt=""
        aria-hidden="true"
        loading="lazy"
        decoding="async"
      />
    {/if}

    <h2 class="chapter-headline">{chapter.headline || ""}</h2>

    {#if dateLabel || ageLabel || chapter.location}
      <div class="chapter-metadata">
        {#if dateLabel}
          <span class="chapter-date-range">{dateLabel}</span>
        {/if}
        {#if dateLabel && ageLabel}
          {#if personStyle?.separatorGlyphDataUrl}
            <span class="separator glyph-separator" aria-hidden="true"></span>
          {:else}
            <span class="separator">·</span>
          {/if}
        {/if}
        {#if ageLabel}
          <span class="chapter-age-range">{ageLabel}</span>
        {/if}
        {#if (dateLabel || ageLabel) && chapter.location}
          {#if personStyle?.separatorGlyphDataUrl}
            <span class="separator glyph-separator" aria-hidden="true"></span>
          {:else}
            <span class="separator">·</span>
          {/if}
        {/if}
        {#if chapter.location}
          <span class="chapter-location">
            <svg class="location-icon" viewBox="0 0 24 24" aria-hidden="true">
              <path d={mdiMapMarkerOutline} />
            </svg>
            {chapter.location}
          </span>
        {/if}
      </div>
    {/if}

    {#if involvedPeople.length > 0}
      <div class="chapter-people">
        {#each involvedPeople as person (person.personKey)}
          {@const subcategory = getSubcategory(person.relationship_type)}
          <PersonChip
            {person}
            personKey={person.personKey}
            {visiblePersonInfo}
            {subcategory}
            onToggle={togglePersonInfo}
            {onOpenNetwork}
            styleConfig={personStyle}
          />
        {/each}
      </div>
    {/if}
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

  .chapter-content {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.8rem;
    padding-top: clamp(0rem, 8vh, 10rem);
  }

  .chapter-box {
    max-width: 42rem;
    width: 100%;
    text-align: center;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 1rem;
    padding: 2rem;
  }

  /* The illustration is atmosphere, not an exhibit: it carries the chapter's
     theme as an abstract emblem and has to read as part of the background the
     headline sits on. So it is printed the way the portrait is — its own black
     ground kept, its edges dissolved into the slide by a radial mask — and then
     taken down in opacity until the story's background pattern shows through
     it. Anything more solid turns the slide into a picture with a caption. */
  .chapter-illustration {
    width: min(20rem, 58vw);
    max-height: min(30dvh, 18rem);
    aspect-ratio: 1;
    object-fit: contain;
    margin-bottom: -0.75rem;
    opacity: 0.72;
    pointer-events: none;

    /* The fade has to be complete before the mask circle reaches the edge of a
       square image — at `farthest-corner` sizing that edge is at 70.7%, and a
       fade still running there leaves the black ground showing as four faint
       straight lines where the story's background pattern stops. */
    mask-image: radial-gradient(
      circle at center,
      rgba(0, 0, 0, 1) 25%,
      rgba(0, 0, 0, 0.85) 42%,
      rgba(0, 0, 0, 0.4) 57%,
      rgba(0, 0, 0, 0) 68%
    );
    -webkit-mask-image: radial-gradient(
      circle at center,
      rgba(0, 0, 0, 1) 25%,
      rgba(0, 0, 0, 0.85) 42%,
      rgba(0, 0, 0, 0.4) 57%,
      rgba(0, 0, 0, 0) 68%
    );
  }

  /* An illustration is a third of a screen on its own, so the slide stops
     reserving the empty run-up it keeps when the headline is all there is. */
  .chapter-content.with-illustration {
    padding-top: clamp(0rem, 2vh, 3rem);
  }

  .chapter-content.with-illustration .chapter-box {
    gap: 0.5rem;
  }

  .chapter-headline {
    font-family: var(--story-heading-font, Inter, sans-serif);
    font-size: clamp(1.5rem, 4vw, 2.25rem);
    font-weight: 700;
    line-height: 1.2;
    color: var(--story-primary, #f8fafc);
    margin: 0;
    text-wrap: balance;
    text-shadow:
      0 2px 8px rgba(0, 0, 0, 0.8),
      0 1px 4px rgba(0, 0, 0, 0.9);
  }

  .chapter-metadata {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    font-family: var(--story-body-font, Inter, sans-serif);
    font-size: 0.8125rem;
    color: var(--story-secondary, #38bdf8);
    font-weight: 500;
    text-shadow:
      0 2px 8px rgba(0, 0, 0, 0.8),
      0 1px 4px rgba(0, 0, 0, 0.9);
  }

  .chapter-date-range {
    font-variant-numeric: tabular-nums;
  }

  .chapter-age-range {
    font-variant-numeric: tabular-nums;
  }

  .separator {
    color: rgba(148, 163, 184, 0.8);
    flex: 0 0 auto;
  }

  .separator.glyph-separator {
    width: 0.9em;
    height: 0.9em;
    display: inline-block;
    background-image: var(--story-separator-glyph);
    background-size: contain;
    background-repeat: no-repeat;
    background-position: center;
    opacity: 0.6;
    vertical-align: middle;
  }

  .chapter-location {
    display: flex;
    align-items: center;
    gap: 0.25rem;
  }

  .location-icon {
    width: 0.875rem;
    height: 0.875rem;
    fill: currentColor;
    opacity: 0.8;
  }

  .chapter-people {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 0.5rem;
    margin-top: 0.25rem;
  }

  @media (max-width: 640px) {
    .chapter-box {
      gap: 0.875rem;
      padding: 1.25rem;
    }

    .chapter-headline {
      font-size: clamp(1.25rem, 6vw, 1.75rem);
    }

    .chapter-metadata {
      font-size: 0.75rem;
      gap: 0.4rem 1rem;
    }
  }
</style>
