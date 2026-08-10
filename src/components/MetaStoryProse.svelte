<script>
  // Meta-story prose with the story's own people linked into their individual
  // stories. The mention rendering itself is `PersonMentions`; what belongs
  // here is where the link goes: `from_meta` (so the story's close button
  // returns here) together with any landing filters behind it, and the
  // reader's scroll position remembered first — matching how the timeline,
  // network and map open a story.
  import PersonMentions from "./PersonMentions.svelte";
  import { saveMetaStoryScroll } from "../stores/metaStoryScroll.js";
  import { queryParams, personStoryHref } from "../stores/queryParams.js";

  export let text = "";
  export let people = []; // [{ id, name, aliases, color }]
  export let metaStoryId = null;
  export let currentLanguage = "en";

  $: colorById = new Map(people.map((p) => [p.id, p.color]));

  function hrefFor(person) {
    return personStoryHref({
      language: currentLanguage,
      personId: person.id,
      metaStoryId,
      fromLanding: $queryParams.from_landing,
    });
  }

  function openStory() {
    // Persist scroll before the hash change navigates away.
    if (metaStoryId) saveMetaStoryScroll(metaStoryId);
  }
</script>

<PersonMentions
  {text}
  {people}
  {hrefFor}
  colorFor={(person) => colorById.get(person.id) || "#38bdf8"}
  onNavigate={openStory}
/>
