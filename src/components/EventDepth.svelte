<script>
  import {
    mdiMapMarkerOutline,
    mdiBookOpenPageVariantOutline,
    mdiImageOutline,
    mdiAccountOutline,
    mdiLinkVariant,
    mdiChevronUp,
    mdiOpenInNew,
  } from "@mdi/js";
  import { _ } from "../stores/language";
  import { getThumbnailUrl, sourceLabel } from "../utils/storyHelpers.js";
  import { relationshipTypeLabel } from "../utils/relationshipLabels.js";

  export let slide = {};
  export let depth = null;
  export let onEnlargeImage = () => {};
  export let onReturnToEvent = () => {};

  // A place is worth naming here when the sources hold two names for it: the
  // one the event happened under and the one a reader could find today. Where
  // they agree there is nothing to explain, and the map already says where.
  $: places = (depth?.places ?? []).filter(
    (place) => place.historic || place.modern
  );
  $: hasTwoNames = places.some(
    (place) => place.historic && place.modern && place.historic !== place.modern
  );
</script>

<section
  class="event-depth"
  aria-label={$_("story.depth.region", { title: slide.title ?? "" })}
>
  <div class="depth-inner">
    <p class="depth-eyebrow">{$_("story.depth.heading")}</p>
    <!-- The event's own headline has scrolled off by the time anyone reads
         this, and a page of context nobody can attach to anything is worse
         than no page at all. -->
    {#if slide.title}
      <p class="depth-title">{slide.title}</p>
    {/if}

    {#if places.length > 0}
      <div class="depth-block">
        <h3 class="depth-label">
          <svg class="depth-icon" viewBox="0 0 24 24" aria-hidden="true">
            <path d={mdiMapMarkerOutline} />
          </svg>
          {$_("story.depth.place")}
        </h3>
        <ul class="place-list">
          {#each places as place (`${place.historic}-${place.modern}`)}
            <li class="place">
              <span class="place-historic"
                >{place.historic || place.modern}</span
              >{#if place.historic && place.modern && place.historic !== place.modern}<span
                  class="place-arrow"
                  aria-hidden="true">→</span
                ><span class="place-modern">{place.modern}</span>{/if}
            </li>
          {/each}
        </ul>
        {#if hasTwoNames}
          <p class="depth-note">{$_("story.depth.place_note")}</p>
        {/if}
      </div>
    {/if}

    {#if depth?.terms?.length}
      <div class="depth-block">
        <h3 class="depth-label">
          <svg class="depth-icon" viewBox="0 0 24 24" aria-hidden="true">
            <path d={mdiBookOpenPageVariantOutline} />
          </svg>
          {$_("story.depth.terms")}
        </h3>
        <dl class="term-list">
          {#each depth.terms as term (term.term)}
            <dt class="term">{term.term}</dt>
            <dd class="term-explanation">
              {term.explanation}
              {#if term.wikipediaUrl}
                <a
                  class="depth-link"
                  href={term.wikipediaUrl}
                  target="_blank"
                  rel="noreferrer">{$_("story.read_more")}</a
                >
              {/if}
            </dd>
          {/each}
        </dl>
      </div>
    {/if}

    {#if depth?.images?.length}
      <div class="depth-block">
        <h3 class="depth-label">
          <svg class="depth-icon" viewBox="0 0 24 24" aria-hidden="true">
            <path d={mdiImageOutline} />
          </svg>
          {$_("story.depth.images")}
        </h3>
        <ul class="figure-list">
          {#each depth.images as image (image.url)}
            <li class="figure">
              <button
                type="button"
                class="figure-thumb"
                on:click={() => onEnlargeImage(image, slide)}
                aria-label={$_("story.enlarge_image")}
              >
                <img
                  src={getThumbnailUrl(image.url, 200)}
                  alt=""
                  loading="lazy"
                  decoding="async"
                />
              </button>
              <div class="figure-text">
                {#if image.caption}
                  <p class="figure-caption">{image.caption}</p>
                {/if}
                <!-- The credit line the lightbox carries, printed where the
                     reader does not have to open anything to read it. -->
                {#if image.creator || image.license}
                  <p class="figure-credit">
                    {#if image.creator}<span class="figure-creator"
                        >{image.creator}</span
                      >{/if}{#if image.creator && image.license}<span
                        class="figure-dot"
                        aria-hidden="true">·</span
                      >{/if}{#if image.license}{#if image.licenseUrl}<a
                          class="depth-link"
                          href={image.licenseUrl}
                          target="_blank"
                          rel="noreferrer">{image.license}</a
                        >{:else}<span>{image.license}</span>{/if}{/if}
                  </p>
                {/if}
              </div>
            </li>
          {/each}
        </ul>
      </div>
    {/if}

    {#if depth?.people?.length}
      <div class="depth-block">
        <h3 class="depth-label">
          <svg class="depth-icon" viewBox="0 0 24 24" aria-hidden="true">
            <path d={mdiAccountOutline} />
          </svg>
          {$_("story.people")}
        </h3>
        <ul class="person-list">
          {#each depth.people as person (person.person_name)}
            <li class="person">
              <p class="person-line">
                <span class="person-name">{person.person_name}</span>
                {#if person.relationship_type}
                  <span class="person-role"
                    >{relationshipTypeLabel($_, person.relationship_type)}</span
                  >
                {/if}
              </p>
              {#if person.relationship_description}
                <p class="person-description">
                  {person.relationship_description}
                </p>
              {/if}
            </li>
          {/each}
        </ul>
      </div>
    {/if}

    {#if depth?.sources?.length}
      <div class="depth-block">
        <h3 class="depth-label">
          <svg class="depth-icon" viewBox="0 0 24 24" aria-hidden="true">
            <path d={mdiLinkVariant} />
          </svg>
          {$_("story.depth.sources")}
        </h3>
        <ul class="source-list">
          {#each depth.sources as source (source)}
            <li>
              <a
                class="source-link"
                href={source}
                target="_blank"
                rel="noreferrer"
              >
                {sourceLabel(source).label}
                <svg class="source-icon" viewBox="0 0 24 24" aria-hidden="true">
                  <path d={mdiOpenInNew} />
                </svg>
              </a>
            </li>
          {/each}
        </ul>
      </div>
    {/if}

    <button type="button" class="depth-return" on:click={onReturnToEvent}>
      <svg class="depth-return-icon" viewBox="0 0 24 24" aria-hidden="true">
        <path d={mdiChevronUp} />
      </svg>
      {$_("story.depth.back")}
    </button>
  </div>
</section>

<style>
  /* The depth layer is a second screen, not a longer slide: it starts below
     the fold and fills at least the rest of the way, so the reader arrives on
     a page of its own rather than on the tail of the event. */
  .event-depth {
    position: relative;
    z-index: 4;
    /* The slide is a column flex container with a definite height, so without
       this the depth layer is treated as slack and squeezed to fit the screen
       the fold already fills — taking its own foot, and the way back up, off
       the bottom of the scroll. */
    flex: 0 0 auto;
    min-height: 100%;
    width: min(54rem, 100%);
    margin: 0 auto;
    padding: 2.5rem 0 var(--slide-bottom-clear, 8rem);
    display: flex;
    flex-direction: column;
  }

  .depth-inner {
    display: flex;
    flex-direction: column;
    gap: 1.75rem;
    /* The reference register: quieter than the slide above it, closer to a
       page of notes than to a panel. */
    background: rgba(8, 12, 24, 0.66);
    backdrop-filter: blur(10px);
    border: 1px solid rgba(148, 163, 184, 0.16);
    border-radius: 0.75rem;
    padding: 1.5rem;
  }

  .depth-eyebrow {
    margin: 0;
    font-family: var(--story-body-font, Inter, sans-serif);
    font-size: 0.7rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--story-secondary, #38bdf8);
    opacity: 0.85;
  }

  .depth-title {
    margin: -1.25rem 0 0;
    font-family: var(--story-heading-font, Inter, sans-serif);
    font-size: 1.1rem;
    font-weight: 600;
    line-height: 1.25;
    color: var(--story-primary, #f8fafc);
    text-wrap: balance;
  }

  .depth-block {
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
  }

  .depth-label {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    margin: 0;
    font-family: var(--story-heading-font, Inter, sans-serif);
    font-size: 0.95rem;
    font-weight: 600;
    color: rgba(248, 250, 252, 0.92);
  }

  .depth-icon {
    width: 1rem;
    height: 1rem;
    fill: var(--story-secondary, #38bdf8);
    flex: 0 0 auto;
  }

  .depth-note {
    margin: 0;
    font-size: 0.75rem;
    color: rgba(203, 213, 225, 0.65);
  }

  .place-list,
  .figure-list,
  .person-list,
  .source-list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .place {
    font-family: var(--story-body-font, Inter, sans-serif);
    font-size: 0.95rem;
    color: rgba(226, 232, 240, 0.95);
  }

  .place-arrow {
    margin: 0 0.45rem;
    color: var(--story-secondary, #38bdf8);
  }

  .place-modern {
    color: rgba(203, 213, 225, 0.75);
  }

  .term-list {
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .term {
    font-family: var(--story-body-font, Inter, sans-serif);
    font-weight: 600;
    font-size: 0.95rem;
    color: var(--story-primary, #f8fafc);
  }

  .term-explanation {
    margin: 0.15rem 0 0;
    font-size: 0.9rem;
    line-height: 1.55;
    color: rgba(226, 232, 240, 0.85);
  }

  .figure {
    display: flex;
    gap: 0.75rem;
    align-items: flex-start;
  }

  .figure-thumb {
    appearance: none;
    border: 1px solid rgba(148, 163, 184, 0.2);
    border-radius: 0.4rem;
    overflow: hidden;
    padding: 0;
    background: transparent;
    cursor: pointer;
    flex: 0 0 auto;
    width: 4.5rem;
    height: 4.5rem;
  }

  .figure-thumb img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }

  .figure-text {
    min-width: 0;
  }

  .figure-caption {
    margin: 0;
    font-size: 0.9rem;
    line-height: 1.45;
    color: rgba(226, 232, 240, 0.9);
  }

  .figure-credit {
    margin: 0.2rem 0 0;
    font-size: 0.75rem;
    color: rgba(203, 213, 225, 0.65);
  }

  .figure-dot {
    margin: 0 0.35rem;
  }

  .person-line {
    margin: 0;
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: 0.5rem;
  }

  .person-name {
    font-family: var(--story-body-font, Inter, sans-serif);
    font-weight: 600;
    font-size: 0.95rem;
    color: var(--story-primary, #f8fafc);
  }

  .person-role {
    font-size: 0.75rem;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--story-secondary, #38bdf8);
  }

  .person-description {
    margin: 0.2rem 0 0;
    font-size: 0.9rem;
    line-height: 1.55;
    color: rgba(226, 232, 240, 0.85);
  }

  .source-link,
  .depth-link {
    color: var(--story-secondary, #38bdf8);
    text-decoration: none;
    border-bottom: 1px solid rgba(148, 163, 184, 0.35);
  }

  .depth-link {
    margin-left: 0.35rem;
    font-size: 0.85rem;
  }

  .source-link {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    font-size: 0.9rem;
    word-break: break-word;
  }

  .source-icon {
    width: 0.85rem;
    height: 0.85rem;
    fill: currentColor;
    flex: 0 0 auto;
  }

  .source-link:hover,
  .depth-link:hover {
    border-bottom-color: var(--story-secondary, #38bdf8);
  }

  .depth-return {
    align-self: center;
    appearance: none;
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    margin-top: 0.25rem;
    padding: 0.5rem 1rem;
    border-radius: 999px;
    border: 1px solid rgba(148, 163, 184, 0.3);
    background: rgba(15, 23, 42, 0.65);
    color: rgba(226, 232, 240, 0.9);
    font-family: var(--story-body-font, Inter, sans-serif);
    font-size: 0.8rem;
    cursor: pointer;
  }

  .depth-return-icon {
    width: 1rem;
    height: 1rem;
    fill: currentColor;
  }

  .depth-return:hover {
    border-color: var(--story-secondary, #38bdf8);
  }

  @media (max-width: 640px) {
    .event-depth {
      padding-top: 1.5rem;
    }

    .depth-inner {
      gap: 1.4rem;
      padding: 1.1rem;
      border-radius: 0.6rem;
    }

    .term-explanation,
    .person-description,
    .figure-caption {
      font-size: 0.85rem;
    }
  }
</style>
