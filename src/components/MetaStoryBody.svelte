<script>
  import MetaStoryFigure from "./MetaStoryFigure.svelte";
  import MetaStoryProse from "./MetaStoryProse.svelte";

  // One composed prose region — the opening, the description, a section body,
  // or the closing: an ordered list of blocks —
  // { type: "paragraph", text } | { type: "image", image, layout } |
  // { type: "quote", text, attribution? }. Renders nothing when absent, so
  // uncomposed stories are unaffected.
  export let blocks = null;

  // "opening" marks the story's cold open: the same body copy as every other
  // region, set apart only by a raised initial and a lead figure.
  export let variant = null;

  // Story people (with individual stories) so their names are emphasized and
  // linked in the body prose, matching the rest of the meta story text.
  export let people = [];
  export let metaStoryId = null;
  export let currentLanguage = "en";
  // Called with an image block's image when the reader clicks it (opens the
  // story's lightbox); passed straight through to the figures.
  export let onEnlarge = null;

  $: proseContext = { people, metaStoryId, currentLanguage };
</script>

{#if blocks?.length}
  <div class="story-body" class:opening={variant === "opening"}>
    {#each blocks as block}
      {#if block.type === "paragraph" && block.text}
        <p class="body-text">
          <MetaStoryProse text={block.text} {...proseContext} />
        </p>
      {:else if block.type === "image" && block.image}
        <MetaStoryFigure
          image={block.image}
          layout={block.layout}
          variant={variant === "opening" ? "opening" : null}
          {onEnlarge}
        />
      {:else if block.type === "quote" && block.text}
        <blockquote class="body-quote">
          <p>“<MetaStoryProse text={block.text} {...proseContext} />”</p>
          {#if block.attribution}
            <cite>{block.attribution}</cite>
          {/if}
        </blockquote>
      {/if}
    {/each}
  </div>
{/if}

<style>
  .story-body {
    margin-bottom: 1.5rem;
  }

  /* Contain floated figures (layout: left/right) */
  .story-body::after {
    content: "";
    display: table;
    clear: both;
  }

  /* Same running prose as the rest of the article (see MetaStoryView's
     editorial palette; the custom properties inherit from .meta-story-view). */
  .body-text {
    font-size: 1.0625rem;
    line-height: 1.75;
    color: var(--ms-body, #cbd5e1);
    margin-bottom: 1rem;
  }

  /* Raised initial rather than a floated drop cap: a floated cap reserves
     only the glyph's own width, so narrow letters ("In 1911...", "It...")
     read as a stray vertical rule and leave the wrapped lines indented
     against nothing. Raising the letter is glyph-width independent. */
  .opening .body-text:first-of-type::first-letter {
    font-family: var(--heading-font, "Space Grotesk", sans-serif);
    font-size: 1.9em;
    line-height: 1;
    padding-right: 0.06em;
    color: var(--ms-accent, #38bdf8);
  }

  /* Pulled quote — accent hairline, body face, muted attribution. */
  .body-quote {
    margin: 1.5rem 0;
    padding: 0.25rem 0 0.25rem 1.25rem;
    border-left: max(2px, var(--ms-frame-rule-width, 2px))
      var(--ms-frame-border-style, solid) var(--ms-accent, #38bdf8);
    clear: both;
  }

  .body-quote p {
    font-size: 1.15rem;
    line-height: 1.6;
    font-style: italic;
    color: var(--ms-ink, #e8edf4);
    margin-bottom: 0.35rem;
  }

  .body-quote cite {
    display: block;
    font-size: 0.85rem;
    font-style: normal;
    color: var(--ms-muted, #94a3b8);
  }
</style>
