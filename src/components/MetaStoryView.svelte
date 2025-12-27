<script>
  import { _ } from "../stores/language";
  import { push } from "svelte-spa-router";
  import MetaStoryTimeline from "./MetaStoryTimeline.svelte";

  export let metaStoryData = null;
  export let personsRegistry = [];
  export let currentLanguage = "en";
  export let getStyle = () => ({});
  export let isLoading = false;

  // Navigate to person's story at specific event
  function viewPersonEvent(personId, eventIndex) {
    push(`/${currentLanguage}/story/${personId}?slide=${eventIndex}`);
  }

  // Navigate back to landing
  function backToLanding() {
    push(`/${currentLanguage}`);
  }
</script>

<!-- Loading state -->
{#if isLoading}
  <div class="loading">Loading meta story...</div>
{:else if metaStoryData}
  <div class="meta-story-view">
    <!-- Header section -->
    <header class="meta-story-header">
      <button on:click={backToLanding} class="back-button">
        ← {$_('meta_story.back_to_stories')}
      </button>
      <h1>{metaStoryData.meta_story.title}</h1>
      <p class="tagline">{metaStoryData.meta_story.tagline}</p>
      <p class="date-range">
        {$_('meta_story.date_range', {
          start: metaStoryData.meta_story.date_range_start,
          end: metaStoryData.meta_story.date_range_end
        })}
      </p>
      <p class="description">{metaStoryData.meta_story.description}</p>
    </header>

    <!-- Chapters section - full width, breaks out of container -->
    {#if metaStoryData.chapters?.length}
      <section class="chapters-fullwidth">
        <h2>{$_('meta_story.chapters_heading')}</h2>
        <MetaStoryTimeline
          chapters={metaStoryData.chapters}
          personsRegistry={personsRegistry}
          onEventClick={viewPersonEvent}
          subtopics={metaStoryData.subtopics}
        />
      </section>
    {/if}

    <!-- Conclusion section -->
    {#if metaStoryData.conclusion}
      <section class="conclusion">
        <h2>{$_('meta_story.conclusion_heading')}</h2>
        <p>{metaStoryData.conclusion}</p>
      </section>
    {/if}
  </div>
{/if}

<style>
  /* Container */
  .meta-story-view {
    max-width: 800px;
    margin: 0 auto;
    padding: 2rem 1rem;
    font-family: var(--body-font, 'IBM Plex Sans', sans-serif);
  }

  /* Header */
  .meta-story-header {
    margin-bottom: 3rem;
  }

  .back-button {
    background: rgba(56, 189, 248, 0.1);
    color: #38bdf8;
    border: 1px solid rgba(56, 189, 248, 0.3);
    padding: 0.5rem 1rem;
    border-radius: 0.5rem;
    cursor: pointer;
    margin-bottom: 1.5rem;
  }

  .back-button:hover {
    background: rgba(56, 189, 248, 0.2);
    border-color: rgba(56, 189, 248, 0.5);
  }

  h1 {
    font-family: var(--heading-font, 'Space Grotesk', sans-serif);
    font-size: 2.5rem;
    margin-bottom: 0.5rem;
  }

  .tagline {
    font-size: 1.25rem;
    color: #38bdf8;
    margin-bottom: 0.5rem;
  }

  .date-range {
    color: #94a3b8;
    margin-bottom: 1.5rem;
  }

  .description {
    line-height: 1.7;
    color: #cbd5e1;
  }

  /* Sections */
  section {
    margin-bottom: 3rem;
  }

  h2 {
    font-family: var(--heading-font, 'Space Grotesk', sans-serif);
    font-size: 1.875rem;
    margin-bottom: 1.5rem;
    border-bottom: 2px solid rgba(56, 189, 248, 0.3);
    padding-bottom: 0.5rem;
  }

  /* Chapters section - full width */
  .chapters-fullwidth {
    width: 100vw;
    margin-left: calc(-50vw + 50%);
    margin-bottom: 3rem;
    padding: 0;
  }

  .chapters-fullwidth h2 {
    font-family: var(--heading-font, 'Space Grotesk', sans-serif);
    font-size: 1.875rem;
    margin: 0 auto 1.5rem;
    max-width: 800px;
    padding: 0 1rem 0.5rem;
    border-bottom: 2px solid rgba(56, 189, 248, 0.3);
  }

  /* Conclusion */
  .conclusion p {
    font-size: 1.125rem;
    line-height: 1.8;
    color: #cbd5e1;
    font-style: italic;
  }

  /* Loading state */
  .loading {
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 100vh;
    font-size: 1.25rem;
    color: #94a3b8;
  }

  /* Responsive */
  @media (max-width: 640px) {
    .meta-story-view {
      padding: 1rem;
    }

    h1 {
      font-size: 2rem;
    }
  }
</style>
