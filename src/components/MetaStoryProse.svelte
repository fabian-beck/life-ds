<script>
  // Inline prose renderer for meta story text: emphasizes the name of each
  // person who has their own individual story (the story's main people) with
  // the same `.person-mention` treatment used on the story slides and the
  // network/map cards, and turns each into a link into that person's story.
  // The link carries `from_meta` (so the story's close button returns here)
  // together with any landing filters behind it, and remembers the reader's
  // scroll position first, matching how the timeline, network and map open a
  // story.
  import { segmentPersonMentions } from "../utils/personNames.js";
  import { saveMetaStoryScroll } from "../stores/metaStoryScroll.js";
  import { queryParams, personStoryHref } from "../stores/queryParams.js";

  export let text = "";
  export let people = []; // [{ id, name, aliases, color }]
  export let metaStoryId = null;
  export let currentLanguage = "en";

  $: segments = segmentPersonMentions(text, people);
  $: colorById = new Map(people.map((p) => [p.id, p.color]));

  function hrefFor(personId) {
    return personStoryHref({
      language: currentLanguage,
      personId,
      metaStoryId,
      fromLanding: $queryParams.from_landing,
    });
  }

  function openStory() {
    // Persist scroll before the hash change navigates away.
    if (metaStoryId) saveMetaStoryScroll(metaStoryId);
  }
</script>

{#each segments as seg}{#if seg.type === "text"}{seg.content}{:else}<a
      class="person-mention"
      href={hrefFor(seg.person.id)}
      style={`--mention-color: ${colorById.get(seg.person.id) || "#38bdf8"}`}
      on:click={openStory}>{seg.content}</a
    >{/if}{/each}

<style>
  /* Mirrors the story slides' and network cards' `.person-mention`: a bold,
     softly glowing name in the person's own story color. As a link it stays
     inline (no underline until hover) so the prose reads naturally. */
  .person-mention {
    font-weight: 700;
    color: inherit;
    text-decoration: none;
    cursor: pointer;
    text-shadow: 0 0 6px var(--mention-color, rgba(56, 189, 248, 0.35));
    transition: color 0.15s ease;
  }

  .person-mention:hover,
  .person-mention:focus-visible {
    color: var(--mention-color, #38bdf8);
    text-decoration: underline;
    text-underline-offset: 0.15em;
  }

  .person-mention:hover {
    outline: none;
  }

  .person-mention:focus-visible {
    outline: 2px solid var(--mention-color, #38bdf8);
    outline-offset: 2px;
    border-radius: 0.15em;
  }
</style>
