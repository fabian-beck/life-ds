<script>
  import MetaStoryFigure from "./MetaStoryFigure.svelte";
  import MetaStoryProse from "./MetaStoryProse.svelte";

  // A composed section body (Phase 8): an ordered list of blocks —
  // { type: "paragraph", text } | { type: "image", image, layout } |
  // { type: "quote", text, attribution? }. Renders nothing when absent, so
  // uncomposed stories are unaffected.
  export let blocks = null;

  // Story people (with individual stories) so their names are emphasized and
  // linked in the body prose, matching the rest of the meta story text.
  export let people = [];
  export let metaStoryId = null;
  export let currentLanguage = "en";

  $: proseContext = { people, metaStoryId, currentLanguage };
</script>

{#if blocks?.length}
  <div class="story-body">
    {#each blocks as block}
      {#if block.type === "paragraph" && block.text}
        <p class="body-text">
          <MetaStoryProse text={block.text} {...proseContext} />
        </p>
      {:else if block.type === "image" && block.image}
        <MetaStoryFigure image={block.image} layout={block.layout} />
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

  /* Pulled quote — accent hairline, body face, muted attribution. */
  .body-quote {
    margin: 1.5rem 0;
    padding: 0.25rem 0 0.25rem 1.25rem;
    border-left: 2px solid var(--ms-accent, #38bdf8);
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
