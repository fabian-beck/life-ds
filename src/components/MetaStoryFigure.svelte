<script>
  import { mdiMagnifyPlusOutline } from "@mdi/js";
  import { _ } from "../stores/language";

  // An image the story composer selected from a person's story slides
  // ({ url, caption, source, ... }); renders nothing when absent.
  export let image = null;
  // "opening" floats the figure beside the cold-open text on wide screens.
  export let variant = "section";
  // Body-block layout (composer's choice): "left"/"right" float the figure
  // beside the following text on wide screens, "full" (or null) spans the
  // column.
  export let layout = null;
  // Called with this image when the reader clicks it; when absent the figure
  // stays a plain, non-interactive image.
  export let onEnlarge = null;

  $: canEnlarge = typeof onEnlarge === "function";
</script>

{#if image?.url}
  <figure
    class="story-figure"
    class:opening={variant === "opening"}
    class:float-left={layout === "left"}
    class:float-right={layout === "right"}
  >
    {#if canEnlarge}
      <button
        type="button"
        class="image-button"
        on:click={() => onEnlarge(image)}
        aria-label={$_("meta_story.enlarge_image")}
        title={$_("meta_story.enlarge_image")}
      >
        <img src={image.url} alt={image.caption || ""} loading="lazy" />
        <span class="zoom-hint" aria-hidden="true">
          <svg viewBox="0 0 24 24" role="presentation">
            <path d={mdiMagnifyPlusOutline} />
          </svg>
        </span>
      </button>
    {:else}
      <img src={image.url} alt={image.caption || ""} loading="lazy" />
    {/if}
    {#if image.caption || image.source}
      <figcaption>
        {#if image.caption}<span class="caption-text">{image.caption}</span
          >{/if}
        {#if image.source}
          <a
            class="caption-source"
            href={image.source}
            target="_blank"
            rel="noopener noreferrer">{$_("meta_story.image_source")}</a
          >
        {/if}
      </figcaption>
    {/if}
  </figure>
{/if}

<style>
  .story-figure {
    margin: 1.5rem 0;
  }

  img {
    display: block;
    width: 100%;
    max-width: 100%;
    border-radius: 0.5rem;
    border: 1px solid rgba(148, 163, 184, 0.2);
  }

  /* Click target for the lightbox — a bare button so the image keeps its own
     box, with a magnifier badge as the affordance. */
  .image-button {
    display: block;
    position: relative;
    width: 100%;
    padding: 0;
    border: none;
    background: none;
    cursor: zoom-in;
    font: inherit;
    color: inherit;
    line-height: 0;
  }

  .image-button img {
    transition:
      border-color 0.2s ease,
      filter 0.2s ease;
  }

  .image-button:hover img,
  .image-button:focus-visible img {
    border-color: var(--ms-accent, #38bdf8);
    filter: brightness(1.05);
  }

  .image-button:focus-visible {
    outline: 2px solid var(--ms-accent, #38bdf8);
    outline-offset: 3px;
    border-radius: 0.5rem;
  }

  .zoom-hint {
    position: absolute;
    right: 0.5rem;
    bottom: 0.5rem;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 1.9rem;
    height: 1.9rem;
    border-radius: 999px;
    background: rgba(15, 23, 42, 0.65);
    border: 1px solid rgba(148, 163, 184, 0.35);
    opacity: 0.55;
    transition: opacity 0.2s ease;
    pointer-events: none;
  }

  .image-button:hover .zoom-hint,
  .image-button:focus-visible .zoom-hint {
    opacity: 1;
  }

  .zoom-hint svg {
    width: 1.1rem;
    height: 1.1rem;
    fill: #e2e8f0;
  }

  /* Portrait scans (tall book pages, standing portraits) would otherwise fill
     the whole viewport at full width and push the text they illustrate below
     the fold. Cap the height and let the image shrink to fit instead. */
  @media (max-width: 699px) {
    img {
      width: auto;
      max-height: 45vh;
      margin: 0 auto;
    }

    /* Shrink the click target to the (centred, narrower) image so the zoom
       badge stays on the picture instead of the empty column beside it. */
    .image-button {
      width: fit-content;
      max-width: 100%;
      margin: 0 auto;
    }
  }

  figcaption {
    margin-top: 0.4rem;
    font-size: 0.8rem;
    line-height: 1.45;
    color: #94a3b8;
  }

  .caption-source {
    margin-left: 0.4rem;
    color: #38bdf8;
    text-decoration: none;
    white-space: nowrap;
  }

  .caption-source:hover,
  .caption-source:focus {
    text-decoration: underline;
  }

  /* Opening and floated body figures sit beside their text on wide screens */
  @media (min-width: 700px) {
    .story-figure.opening,
    .story-figure.float-right {
      float: right;
      width: 42%;
      margin: 0.25rem 0 1rem 1.5rem;
    }

    .story-figure.float-left {
      float: left;
      width: 42%;
      margin: 0.25rem 1.5rem 1rem 0;
    }
  }
</style>
