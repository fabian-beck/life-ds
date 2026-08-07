<script>
  import { mdiChevronUp, mdiOpenInNew } from "@mdi/js";
  import { _ } from "../stores/language";
  import {
    composeDepthParagraphs,
    getThumbnailUrl,
    sourceLabel,
  } from "../utils/storyHelpers.js";

  export let slide = {};
  export let depth = null;
  export let onEnlargeImage = () => {};
  export let onReturnToEvent = () => {};

  $: paragraphs = composeDepthParagraphs(depth, $_);

  // A picture belongs in the passage rather than at the head of it, so they are
  // dealt out between the paragraphs: the first after the scene is set, the
  // next further down. An event with one picture — most of them — puts it after
  // the opening paragraph, which is where a chapter would put it too.
  $: figures = depth?.images ?? [];
  function figureAfter(index) {
    return figures[index] ?? null;
  }
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

    {#each paragraphs as paragraph, index (index)}
      <p class="depth-paragraph" class:depth-lead={index === 0}>
        {#each paragraph as segment, position (position)}{#if segment.href}<a
              class="depth-subject depth-subject-link"
              href={segment.href}
              target="_blank"
              rel="noreferrer">{segment.text}</a
            >{:else if segment.subject}<span class="depth-subject"
              >{segment.text}</span
            >{:else}{segment.text}{/if}{/each}
      </p>

      {#if figureAfter(index)}
        {@const image = figureAfter(index)}
        <figure class="depth-figure">
          <button
            type="button"
            class="depth-figure-button"
            on:click={() => onEnlargeImage(image, slide)}
            aria-label={$_("story.enlarge_image")}
          >
            <img
              src={getThumbnailUrl(image.url, 800)}
              alt=""
              loading="lazy"
              decoding="async"
            />
          </button>
          {#if image.caption || image.creator || image.license}
            <figcaption>
              {#if image.caption}<span>{image.caption}</span>{/if}
              <!-- The credit the lightbox carries, printed where the reader
                   does not have to open anything to read it. -->
              {#if image.creator || image.license}
                <span class="figure-credit"
                  >{#if image.creator}{image.creator}{/if}{#if image.creator && image.license}<span
                      aria-hidden="true">&#32;·&#32;</span
                    >{/if}{#if image.license}{#if image.licenseUrl}<a
                        class="depth-link"
                        href={image.licenseUrl}
                        target="_blank"
                        rel="noreferrer">{image.license}</a
                      >{:else}{image.license}{/if}{/if}</span
                >
              {/if}
            </figcaption>
          {/if}
        </figure>
      {/if}
    {/each}

    {#if depth?.sources?.length}
      <p class="depth-sources">
        <span>{$_("story.depth.read_at")}</span>
        {#each depth.sources as source, index (source)}{#if index > 0}<span
              aria-hidden="true">&#32;·&#32;</span
            >{/if}<a
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

  /* No card, no rules, no icons, no headings, and above all no line per
     record: this is a short chapter of background, and it is set like one. The
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

  .depth-paragraph {
    margin: 0;
    font-family: var(--story-body-font, Inter, sans-serif);
    font-size: 1rem;
    line-height: 1.7;
    color: rgba(226, 232, 240, 0.92);
    text-wrap: pretty;
  }

  /* The opening paragraph sets the scene, so it carries a little more voice
     than the ones that follow it. */
  .depth-lead {
    color: rgba(241, 245, 249, 0.96);
  }

  /* What a sentence is about, marked inside the sentence rather than pulled
     out in front of it. Where the dataset knows an article for it, the mark is
     the link. */
  .depth-subject {
    font-weight: 600;
    color: var(--story-primary, #f8fafc);
  }

  .depth-subject-link {
    color: var(--story-secondary, #38bdf8);
    text-decoration: none;
    border-bottom: 1px solid rgba(148, 163, 184, 0.35);
  }

  .depth-subject-link:hover {
    border-bottom-color: var(--story-secondary, #38bdf8);
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

    .depth-paragraph {
      font-size: 0.95rem;
      line-height: 1.65;
    }
  }
</style>
