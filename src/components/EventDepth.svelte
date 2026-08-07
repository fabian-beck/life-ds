<script>
  import { mdiChevronUp, mdiOpenInNew } from "@mdi/js";
  import { _ } from "../stores/language";
  import { getThumbnailUrl, sourceLabel } from "../utils/storyHelpers.js";
  import { relationshipTypeLabel } from "../utils/relationshipLabels.js";

  export let slide = {};
  export let depth = null;
  export let onEnlargeImage = () => {};
  export let onReturnToEvent = () => {};

  // The place opens the passage, because where a thing happened is the first
  // thing a reader needs to picture. Two names are worth a sentence — the one
  // the event happened under and the one a map carries today; one name is
  // worth half of one.
  $: placeSentences = (depth?.places ?? [])
    .filter((place) => place.historic || place.modern)
    .map((place) => {
      const historic = place.historic || place.modern;
      const modern = place.modern || place.historic;
      return historic !== modern
        ? $_("story.depth.place_then_now", { historic, modern })
        : $_("story.depth.place_one", { name: historic });
    });

  // One figure carries the passage; a row of thumbnails would make it a
  // gallery again. The rest of an event's pictures stay where they are, on the
  // slide above and in the lightbox.
  $: figure = depth?.images?.[0] ?? null;
</script>

<section
  class="event-depth"
  aria-label={$_("story.depth.region", { title: slide.title ?? "" })}
>
  <article class="depth-prose">
    <p class="depth-eyebrow">{$_("story.depth.heading")}</p>
    <!-- The event's own headline has scrolled off by the time anyone reads
         this, and a passage nobody can attach to anything is worse than no
         passage at all. -->
    {#if slide.title}
      <p class="depth-title">{slide.title}</p>
    {/if}

    {#each placeSentences as sentence, index (index)}
      <p class="depth-lead">{sentence}</p>
    {/each}

    {#if figure}
      <figure class="depth-figure">
        <button
          type="button"
          class="depth-figure-button"
          on:click={() => onEnlargeImage(figure, slide)}
          aria-label={$_("story.enlarge_image")}
        >
          <img
            src={getThumbnailUrl(figure.url, 800)}
            alt=""
            loading="lazy"
            decoding="async"
          />
        </button>
        {#if figure.caption || figure.creator || figure.license}
          <figcaption>
            {#if figure.caption}<span class="figure-caption"
                >{figure.caption}</span
              >{/if}
            <!-- The credit the lightbox carries, printed where the reader does
                 not have to open anything to read it. -->
            {#if figure.creator || figure.license}
              <span class="figure-credit">
                {#if figure.creator}{figure.creator}{/if}{#if figure.creator && figure.license}<span
                    aria-hidden="true">&#32;·&#32;</span
                  >{/if}{#if figure.license}{#if figure.licenseUrl}<a
                      class="depth-link"
                      href={figure.licenseUrl}
                      target="_blank"
                      rel="noreferrer">{figure.license}</a
                    >{:else}{figure.license}{/if}{/if}
              </span>
            {/if}
          </figcaption>
        {/if}
      </figure>
    {/if}

    <!-- The terms the event's own sentences lean on, each one a paragraph of
         background rather than an entry in a glossary. -->
    {#each depth?.terms ?? [] as term (term.term)}
      <p class="depth-paragraph">
        <span class="depth-subject">{term.term}</span><span
          class="depth-dash"
          aria-hidden="true">&#32;—&#32;</span
        >{term.explanation}{#if term.wikipediaUrl}<a
            class="depth-link"
            href={term.wikipediaUrl}
            target="_blank"
            rel="noreferrer">{$_("story.read_more")}</a
          >{/if}
      </p>
    {/each}

    {#each depth?.people ?? [] as person (person.person_name)}
      <p class="depth-paragraph">
        <span class="depth-subject">{person.person_name}</span
        >{#if person.relationship_type}<span class="depth-role"
            >, {relationshipTypeLabel($_, person.relationship_type)}</span
          >{/if}<span class="depth-dash" aria-hidden="true">&#32;—&#32;</span
        >{person.relationship_description ?? ""}
      </p>
    {/each}

    {#if depth?.sources?.length}
      <p class="depth-sources">
        <span class="depth-sources-lead">{$_("story.depth.read_at")}</span>
        {#each depth.sources as source, index (source)}{#if index > 0}<span
              aria-hidden="true"
            >
              ·
            </span>{/if}<a
            class="depth-link"
            href={source}
            target="_blank"
            rel="noreferrer"
            >{sourceLabel(source).label}<svg
              class="source-icon"
              viewBox="0 0 24 24"
              aria-hidden="true"><path d={mdiOpenInNew} /></svg
            ></a
          >{/each}
      </p>
    {/if}

    <button type="button" class="depth-return" on:click={onReturnToEvent}>
      <svg class="depth-return-icon" viewBox="0 0 24 24" aria-hidden="true">
        <path d={mdiChevronUp} />
      </svg>
      {$_("story.depth.back")}
    </button>
  </article>
</section>

<style>
  /* The passage under the fold is a second screen, not a longer slide: it
     starts below the fold and fills at least the rest of the way, so the reader
     arrives on a page of its own rather than on the tail of the event. */
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

  /* No card, no rules, no icons: this is meant to read as the story going on
     in a quieter voice, and a panel with headings reads as an appendix. The
     measure is narrower than the slide's, because this is the one place in the
     app with more than a few sentences to run. */
  .depth-prose {
    display: flex;
    flex-direction: column;
    gap: 1.15rem;
    width: min(38rem, 100%);
    margin: 0 auto;
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
    margin: -0.85rem 0 0;
    font-family: var(--story-heading-font, Inter, sans-serif);
    font-size: 1.15rem;
    font-weight: 600;
    line-height: 1.25;
    color: var(--story-primary, #f8fafc);
    text-wrap: balance;
  }

  .depth-lead,
  .depth-paragraph {
    margin: 0;
    font-family: var(--story-body-font, Inter, sans-serif);
    font-size: 1rem;
    line-height: 1.65;
    color: rgba(226, 232, 240, 0.92);
    text-wrap: pretty;
  }

  /* The lead sets the scene, so it carries a little more voice than the
     paragraphs that follow it. */
  .depth-lead {
    color: rgba(241, 245, 249, 0.96);
  }

  /* What a paragraph is about, run into the sentence rather than set above it
     as a label. */
  .depth-subject {
    font-weight: 600;
    color: var(--story-primary, #f8fafc);
  }

  .depth-role {
    color: rgba(203, 213, 225, 0.7);
  }

  .depth-dash {
    color: rgba(203, 213, 225, 0.55);
  }

  .depth-figure {
    margin: 0.35rem 0;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .depth-figure-button {
    appearance: none;
    padding: 0;
    border: none;
    background: transparent;
    cursor: pointer;
    display: block;
    border-radius: 0.4rem;
    overflow: hidden;
    line-height: 0;
  }

  .depth-figure-button img {
    width: 100%;
    height: auto;
    display: block;
    /* The same treatment the event's own picture gets on the slide above, so
       the two read as one story rather than as an article and its stock
       photograph. */
    filter: saturate(0.45) contrast(0.8) brightness(0.88);
  }

  .depth-figure figcaption {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
    font-family: var(--story-body-font, Inter, sans-serif);
    font-size: 0.8rem;
    line-height: 1.45;
    color: rgba(203, 213, 225, 0.75);
  }

  .figure-credit {
    color: rgba(203, 213, 225, 0.55);
  }

  .depth-sources {
    margin: 0.35rem 0 0;
    font-family: var(--story-body-font, Inter, sans-serif);
    font-size: 0.8rem;
    line-height: 1.6;
    color: rgba(203, 213, 225, 0.6);
  }

  .depth-sources-lead {
    letter-spacing: 0.04em;
  }

  .depth-link {
    margin-left: 0.35rem;
    color: var(--story-secondary, #38bdf8);
    text-decoration: none;
    border-bottom: 1px solid rgba(148, 163, 184, 0.3);
    white-space: nowrap;
  }

  .depth-link:hover {
    border-bottom-color: var(--story-secondary, #38bdf8);
  }

  .source-icon {
    width: 0.75rem;
    height: 0.75rem;
    margin-left: 0.2rem;
    fill: currentColor;
    vertical-align: -0.05rem;
  }

  .depth-return {
    align-self: flex-start;
    appearance: none;
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    margin-top: 0.6rem;
    padding: 0.45rem 0.9rem;
    border-radius: 999px;
    border: 1px solid rgba(148, 163, 184, 0.28);
    background: rgba(15, 23, 42, 0.5);
    color: rgba(226, 232, 240, 0.85);
    font-family: var(--story-body-font, Inter, sans-serif);
    font-size: 0.78rem;
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

    .depth-prose {
      gap: 1rem;
    }

    .depth-lead,
    .depth-paragraph {
      font-size: 0.95rem;
      line-height: 1.6;
    }
  }
</style>
