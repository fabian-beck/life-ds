<script>
  import { _ } from "../stores/language";

  // An image the story composer selected from a person's story slides
  // ({ url, caption, source, ... }); renders nothing when absent.
  export let image = null;
  // "opening" floats the figure beside the cold-open text on wide screens.
  export let variant = "section";
</script>

{#if image?.url}
  <figure class="story-figure" class:opening={variant === "opening"}>
    <img src={image.url} alt={image.caption || ""} loading="lazy" />
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

  /* Opening figure sits beside the cold-open text on wide screens */
  @media (min-width: 700px) {
    .story-figure.opening {
      float: right;
      width: 42%;
      margin: 0.25rem 0 1rem 1.5rem;
    }
  }
</style>
