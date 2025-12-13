<script>
  import { mdiMapMarkerOutline } from "@mdi/js";
  import PersonChip from "./PersonChip.svelte";
  import { _ } from "../stores/language";
  import { getSubcategory } from "../utils/storyHelpers.js";

  export let chapter = {};
  export let personId = "";
  export let personName = "";
  export let personStyle = null;
  export let egoNetwork = null;
  export let activeSlideIndex = -1; // Track active slide to close popups on navigation
  export let onOpenNetwork = null; // Callback to open the network modal

  let visiblePersonInfo = null;

  // Close person info popup when slide changes
  $: if (activeSlideIndex !== undefined) {
    visiblePersonInfo = null;
  }

  // Format date range for chapter
  $: dateRangeLabel = (() => {
    if (!chapter) return "";

    const start = chapter.date_start;
    const end = chapter.date_end;
    const ageStart = chapter.age_start;
    const ageEnd = chapter.age_end;

    const parts = [];

    // Date range
    if (start && end) {
      parts.push(`${start} – ${end}`);
    } else if (start) {
      parts.push(start);
    }

    // Age range
    if (ageStart !== undefined && ageEnd !== undefined) {
      if (ageStart === 0) {
        parts.push($_("story.at_birth") + ` – ${$_("story.age", { age: ageEnd })}`);
      } else {
        parts.push(`${$_("story.age", { age: ageStart })} – ${$_("story.age", { age: ageEnd })}`);
      }
    }

    return parts.join(" • ");
  })();

  // Match involved people against ego network
  $: involvedPeople = (() => {
    if (!chapter.involved_people || !Array.isArray(chapter.involved_people)) {
      return [];
    }
    if (!egoNetwork?.connections) {
      return [];
    }

    return chapter.involved_people
      .map((personName) => {
        const connection = egoNetwork.connections.find(
          (c) => c.person_name === personName
        );
        return connection ? { ...connection, personKey: personName } : null;
      })
      .filter(Boolean);
  })();

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

<div class="content chapter-content" on:click={handleClickOutside}>
  <div class="chapter-box">
    <h2 class="chapter-headline">{chapter.headline || ""}</h2>

    {#if dateRangeLabel || chapter.location}
      <div class="chapter-metadata">
        {#if dateRangeLabel}
          <span class="chapter-date-range">{dateRangeLabel}</span>
        {/if}
        {#if chapter.location}
          <span class="chapter-location">
            <svg
              class="location-icon"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <path d={mdiMapMarkerOutline} />
            </svg>
            {chapter.location}
          </span>
        {/if}
      </div>
    {/if}

    {#if chapter.description}
      <p class="chapter-description">{chapter.description}</p>
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
    padding-top: clamp(0.0rem, 8vh, 10rem);
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

  .chapter-headline {
    font-family: var(--story-heading-font, sans-serif);
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
    gap: 0.5rem 1.25rem;
    font-family: var(--story-body-font, sans-serif);
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

  .chapter-description {
    font-family: var(--story-body-font, sans-serif);
    font-size: clamp(0.9375rem, 2vw, 1.0625rem);
    line-height: 1.6;
    color: #e2e8f0;
    margin: 0;
    max-width: 36rem;
    text-wrap: balance;
    text-shadow:
      0 2px 8px rgba(0, 0, 0, 0.8),
      0 1px 4px rgba(0, 0, 0, 0.9);
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

    .chapter-description {
      font-size: clamp(0.875rem, 3vw, 0.9375rem);
    }
  }
</style>
