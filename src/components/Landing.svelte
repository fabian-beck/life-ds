<script>
  import { createEventDispatcher } from "svelte";

  export let entries = [];
  export let getSummary = () => "";

  const dispatch = createEventDispatcher();

  function handleSelect(id) {
    if (!id) return;
    dispatch("selectPerson", id);
  }
</script>

<section class="landing">
  <div class="landing-hero">
    <p class="eyebrow">Life Data Stories</p>
    <h1>Explore remarkable lives through data stories</h1>
    <p>
      Choose a person to reveal their biographical timeline, rich with
      milestones, roles, and sources.
    </p>
  </div>
  <div class="landing-grid">
    {#if entries.length > 0}
      {#each entries as entry}
        <article class="person-card">
          <h2>{entry.name}</h2>
          {#if getSummary(entry)}
            <p>{getSummary(entry)}</p>
          {:else}
            <p>A summary is not available yet, but the timeline is ready.</p>
          {/if}
          <button
            type="button"
            on:click={() => handleSelect(entry.id)}
            aria-label={`Open life story for ${entry.name}`}
          >
            View story
          </button>
        </article>
      {/each}
    {:else}
      <p class="landing-empty">
        Add a person dataset to begin exploring life stories.
      </p>
    {/if}
  </div>
</section>

<style>
  .landing {
    flex: 1 1 auto;
    display: flex;
    flex-direction: column;
    gap: 2.5rem;
    padding: 3rem 1.5rem 4rem;
    background: linear-gradient(
      180deg,
      rgba(15, 23, 42, 0.92) 0%,
      rgba(15, 23, 42, 0.88) 40%,
      rgba(15, 23, 42, 0.82) 100%
    );
  }

  .landing-hero {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    max-width: 60ch;
  }

  .landing-hero h1 {
    font-size: 2.1rem;
    margin: 0;
    line-height: 1.15;
  }

  .landing-hero p {
    margin: 0;
    font-size: 1rem;
    color: #cbd5f5;
  }

  .landing-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
    gap: 1.5rem;
  }

  .landing-empty {
    margin: 0;
    font-size: 1rem;
    color: #94a3b8;
  }

  .person-card {
    display: flex;
    flex-direction: column;
    gap: 0.9rem;
    padding: 1.5rem;
    border-radius: 1rem;
    background: rgba(30, 41, 59, 0.75);
    border: 1px solid rgba(148, 163, 184, 0.18);
    box-shadow: 0 12px 30px rgba(15, 23, 42, 0.28);
  }

  .person-card h2 {
    margin: 0;
    font-size: 1.35rem;
    line-height: 1.2;
  }

  .person-card p {
    margin: 0;
    font-size: 0.95rem;
    color: #e2e8f0;
  }

  .person-card button {
    align-self: flex-start;
    padding: 0.55rem 1.1rem;
    border-radius: 999px;
    border: none;
    font-size: 0.9rem;
    font-weight: 600;
    background: #38bdf8;
    color: #0f172a;
    cursor: pointer;
    transition:
      transform 0.2s ease,
      box-shadow 0.2s ease;
  }

  .person-card button:hover,
  .person-card button:focus {
    transform: translateY(-1px);
    box-shadow: 0 6px 18px rgba(56, 189, 248, 0.45);
    outline: none;
  }

  @media (min-width: 768px) {
    .landing {
      padding: 4rem 3rem 5rem;
      gap: 3rem;
    }

    .landing-hero h1 {
      font-size: 2.6rem;
    }

    .landing-grid {
      gap: 2rem;
    }
  }
</style>
