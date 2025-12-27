<script>
  import { _ } from "../stores/language";
  import { push } from "svelte-spa-router";
  import PersonCard from "./PersonCard.svelte";
  import MetaStoryTimeline from "./MetaStoryTimeline.svelte";

  export let metaStoryData = null;
  export let personsRegistry = [];
  export let currentLanguage = "en";
  export let getStyle = () => ({});
  export let isLoading = false;

  // Helper to get person data by ID
  function getPersonById(personId) {
    return personsRegistry.find(p => p.id === personId);
  }

  // Navigate to person's story at specific event
  function viewPersonEvent(personId, eventIndex) {
    push(`/${currentLanguage}/story/${personId}?slide=${eventIndex}`);
  }

  // Navigate back to landing
  function backToLanding() {
    push(`/${currentLanguage}`);
  }

  // Navigate to person's story
  function viewPerson(person) {
    push(`/${currentLanguage}/story/${person.id}`);
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

    <!-- Subtopics section -->
    {#if metaStoryData.subtopics?.length}
      <section class="subtopics">
        <h2>{$_('meta_story.subtopics_heading')}</h2>
        {#each metaStoryData.subtopics as subtopic}
          <div class="subtopic">
            <h3>{subtopic.title}</h3>
            <p>{subtopic.description}</p>
            <div class="person-cards">
              {#each subtopic.person_ids as personId}
                {@const person = getPersonById(personId)}
                {#if person}
                  <PersonCard
                    {person}
                    personStyle={getStyle(personId)}
                    onClick={viewPerson}
                  />
                {/if}
              {/each}
            </div>
          </div>
        {/each}
      </section>
    {/if}

    <!-- Chapters section -->
    {#if metaStoryData.chapters?.length}
      <section class="chapters">
        <h2>{$_('meta_story.chapters_heading')}</h2>
        <MetaStoryTimeline
          chapters={metaStoryData.chapters}
          personsRegistry={personsRegistry}
          onEventClick={viewPersonEvent}
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

  /* Subtopics */
  .subtopic {
    margin-bottom: 2rem;
  }

  .subtopic h3 {
    font-size: 1.5rem;
    margin-bottom: 0.75rem;
  }

  .subtopic p {
    line-height: 1.7;
    color: #cbd5e1;
    margin-bottom: 1rem;
  }

  .person-cards {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 1rem;
    width: 100%;
  }

  /* Chapters section - styles handled in MetaStoryTimeline component */

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

    .event-item {
      grid-template-columns: 1fr;
      gap: 0.25rem;
    }
  }
</style>
