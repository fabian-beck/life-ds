<script>
  // Typographic punctuation drawn from the meta story's own visual identity:
  // the separator glyph and the ornamental rule of `meta_story_styles.json`,
  // used the way a printed article uses fleurons.
  //
  //   "divider"  separates two prose regions (glyph between two hairlines)
  //   "closing"  ends the last prose region
  //
  // The article's opening marks are not here: they are part of the masthead
  // in MetaStoryView, where they bracket the title block instead of sitting
  // under it.
  //
  // Purely decorative, so it is hidden from assistive technology; the parent
  // renders it only for stories that actually have a style.
  export let variant = "divider";
</script>

<div class="ornament" aria-hidden="true">
  {#if variant === "divider"}
    <span class="hairline"></span>
    <span class="glyph"></span>
    <span class="hairline"></span>
  {:else}
    <span class="mark"></span>
  {/if}
</div>

<style>
  .ornament {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.75rem;
    margin: 2rem 0;
  }

  .hairline {
    flex: 1 1 0;
    max-width: 8rem;
    height: 1px;
    background: linear-gradient(
      90deg,
      transparent,
      color-mix(in srgb, var(--ms-accent, #38bdf8) 55%, transparent)
    );
  }

  .hairline:last-child {
    background: linear-gradient(
      270deg,
      transparent,
      color-mix(in srgb, var(--ms-accent, #38bdf8) 55%, transparent)
    );
  }

  .glyph {
    width: 1.15rem;
    height: 1.15rem;
    flex: 0 0 auto;
    background-image: var(--ms-glyph, none);
    background-position: center;
    background-size: contain;
    background-repeat: no-repeat;
  }

  .mark {
    width: 15rem;
    max-width: 100%;
    height: 1.5rem;
    background-image: var(--ms-ornament, none);
    background-position: center;
    background-size: contain;
    background-repeat: no-repeat;
  }
</style>
