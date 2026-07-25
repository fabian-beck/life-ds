<script>
  export let items = [];
  export let styleConfig = null;
  export let fallback = " · ";
  export let compact = false;

  $: values = Array.isArray(items)
    ? items.filter((item) => item !== null && item !== undefined)
    : [];
  $: separatorImage = styleConfig?.separatorGlyphDataUrl
    ? `url("${styleConfig.separatorGlyphDataUrl}")`
    : null;
</script>

{#each values as item, index}
  {#if index > 0}
    {#if separatorImage}
      <span
        class="separator-glyph"
        class:compact
        style:background-image={separatorImage}
        aria-hidden="true"
      ></span>
    {:else}
      {fallback}
    {/if}
  {/if}
  {item}
{/each}

<style>
  .separator-glyph {
    display: inline-block;
    width: 1em;
    height: 1em;
    margin: 0 0.5rem;
    vertical-align: middle;
    background-position: center;
    background-size: contain;
    background-repeat: no-repeat;
  }

  .separator-glyph.compact {
    width: 0.85em;
    height: 0.85em;
    margin: 0 0.35rem;
  }
</style>
