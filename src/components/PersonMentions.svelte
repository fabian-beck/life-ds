<script>
  // Renders prose with the people in it emphasized — the `.person-mention`
  // treatment the story slides, the network modal and the meta story's
  // narration cards and prose blocks all share.
  //
  // The loop this replaces was written out five times. It is three lines, but
  // whitespace-sensitive ones: a newline between `{#each}` and `{#if}` puts a
  // space in the middle of a sentence, which is why every copy was formatted
  // into the same run-on shape and why a sixth copy was a bad idea.
  //
  // The styling is deliberately not here. `.person-mention` is declared once
  // in `app.css` for the story surfaces and once in `meta-frames.css` for the
  // meta story's `.ms-steps` cards; leaving it global is what lets EventSlide
  // keep rendering its own markup (its segments carry annotations this
  // component knows nothing about) and still look identical.
  import { segmentPersonMentions } from "../utils/personNames.js";

  // Either hand over prose plus the people who might appear in it...
  export let text = null;
  export let people = [];
  // ...or segments a caller produced itself. The network modal highlights
  // unique relationship subcategories alongside names, which name matching
  // alone cannot find.
  export let segments = null;

  // A mention's color, where the surface tints names per person. Meta-story
  // narration does; the slides and the modal take their glow from the
  // surrounding story style instead and pass nothing.
  export let colorFor = null;
  // Given, each mention becomes a link into that person's story.
  export let hrefFor = null;
  export let onNavigate = null;
  // An extra class per person — the network marks its bridging people so they
  // read as secondary.
  export let classFor = null;

  $: resolved = segments ?? segmentPersonMentions(text ?? "", people);

  function classesFor(person) {
    const extra = classFor?.(person);
    return extra ? `person-mention ${extra}` : "person-mention";
  }

  // `undefined` leaves the attribute off entirely, so a surface that does not
  // tint names emits no empty `style`.
  function styleFor(person) {
    const color = colorFor?.(person);
    return color ? `--mention-color: ${color}` : undefined;
  }
</script>

{#each resolved as seg}{#if seg.type !== "person"}{seg.content}{:else if hrefFor}<a
      class={classesFor(seg.person)}
      href={hrefFor(seg.person)}
      style={styleFor(seg.person)}
      on:click={onNavigate}>{seg.content}</a
    >{:else}<strong class={classesFor(seg.person)} style={styleFor(seg.person)}
      >{seg.content}</strong
    >{/if}{/each}

<style>
  /* Only the link variant, which only the meta story's prose blocks use. The
     `<strong>` variants are styled by the ambient `.person-mention` rules —
     `app.css` on the story surfaces, `.ms-steps` in `meta-frames.css` on the
     narration cards. The prose blocks sit under neither, so the link carries
     the meta family's weight and per-person glow itself, and stays inline (no
     underline until hover) so the prose still reads as prose. */
  a.person-mention {
    font-weight: 700;
    color: inherit;
    text-decoration: none;
    cursor: pointer;
    text-shadow: 0 0 6px var(--mention-color, rgb(56 189 248 / 35%));
    transition: color 0.15s ease;
  }

  a.person-mention:hover,
  a.person-mention:focus-visible {
    color: var(--mention-color, #38bdf8);
    text-decoration: underline;
    text-underline-offset: 0.15em;
  }

  a.person-mention:hover {
    outline: none;
  }

  a.person-mention:focus-visible {
    outline: 2px solid var(--mention-color, #38bdf8);
    outline-offset: 2px;
    border-radius: 0.15em;
  }
</style>
