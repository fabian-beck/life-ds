<script>
  export let chapters = [];
  export let personsRegistry = [];
  export let onEventClick = () => {};

  // Helper to get person data by ID
  function getPersonById(personId) {
    return personsRegistry.find(p => p.id === personId);
  }

  // Calculate total year span across all chapters
  $: totalSpan = (() => {
    if (!chapters || chapters.length === 0) return 1;
    const years = chapters.flatMap(c => [
      parseInt(c.date_start),
      parseInt(c.date_end)
    ]);
    const span = Math.max(...years) - Math.min(...years);
    return span > 0 ? span : 1; // Prevent division by zero
  })();

  // Generate grid template columns based on proportional date ranges
  $: gridTemplate = (() => {
    if (!chapters || chapters.length === 0) return '1fr';

    return chapters.map(chapter => {
      const span = parseInt(chapter.date_end) - parseInt(chapter.date_start);
      // Ensure minimum width for very short chapters (at least 1 year)
      const widthFr = Math.max(span, 1);
      return `${widthFr}fr`;
    }).join(' ');
  })();
</script>

<div class="meta-timeline-container">
  <div class="chapters-row" style="--grid-template: {gridTemplate};">
    {#each chapters as chapter, index}
      <div class="chapter" data-chapter-index={index}>
        <div class="chapter-header">
          <h3>{chapter.title}</h3>
          <div class="date-range">
            {chapter.date_start} - {chapter.date_end}
          </div>
        </div>
        <div class="chapter-body">
          <p class="bridge">{chapter.bridge_statement}</p>
          <ul class="event-list">
            {#each chapter.person_events as event}
              {@const person = getPersonById(event.person_id)}
              <li>
                <button
                  class="event-item"
                  on:click={() => onEventClick(event.person_id, event.event_index)}
                >
                  <span class="event-date">{event.event_date}</span>
                  <span class="event-person">{person?.name || event.person_id}</span>
                  <span class="event-title">{event.event_title}</span>
                </button>
              </li>
            {/each}
          </ul>
        </div>
      </div>
    {/each}
  </div>
</div>

<style>
  /* Container */
  .meta-timeline-container {
    width: 100%;
    overflow-x: auto;
    overflow-y: visible;
    padding: 1rem 0;
  }

  /* Grid layout for chapters */
  .chapters-row {
    display: grid;
    grid-template-columns: var(--grid-template);
    gap: 0;
    min-width: max-content;
  }

  /* Individual chapter column */
  .chapter {
    border-right: 1px solid rgba(56, 189, 248, 0.3);
    padding: 1rem;
    min-height: 400px;
    background: rgba(15, 23, 42, 0.3);
  }

  .chapter:nth-child(even) {
    background: rgba(15, 23, 42, 0.5);
  }

  .chapter:last-child {
    border-right: none;
  }

  /* Chapter header */
  .chapter-header {
    margin-bottom: 1rem;
    border-bottom: 2px solid rgba(56, 189, 248, 0.3);
    padding-bottom: 0.75rem;
  }

  .chapter-header h3 {
    font-family: var(--heading-font, 'Space Grotesk', sans-serif);
    font-size: 1.25rem;
    margin: 0 0 0.5rem 0;
    color: #38bdf8;
    line-height: 1.3;
  }

  .date-range {
    font-size: 0.875rem;
    color: #94a3b8;
    font-weight: 500;
  }

  /* Chapter body */
  .chapter-body {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .bridge {
    font-style: italic;
    color: #94a3b8;
    margin: 0;
    line-height: 1.6;
    font-size: 0.9rem;
  }

  /* Event list */
  .event-list {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .event-item {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    padding: 0.75rem;
    background: rgba(15, 23, 42, 0.5);
    border: 1px solid rgba(56, 189, 248, 0.2);
    border-radius: 0.5rem;
    cursor: pointer;
    text-align: left;
    width: 100%;
    transition: all 0.2s;
  }

  .event-item:hover {
    background: rgba(56, 189, 248, 0.1);
    border-color: rgba(56, 189, 248, 0.4);
  }

  .event-date {
    color: #94a3b8;
    font-size: 0.75rem;
    font-weight: 500;
  }

  .event-person {
    color: #38bdf8;
    font-weight: 500;
    font-size: 0.875rem;
  }

  .event-title {
    color: #e2e8f0;
    font-size: 0.875rem;
    line-height: 1.4;
  }

  /* Responsive */
  @media (max-width: 768px) {
    .chapters-row {
      display: flex;
      flex-direction: column;
      gap: 1.5rem;
    }

    .chapter {
      border-right: none;
      border-bottom: 1px solid rgba(56, 189, 248, 0.3);
      min-height: auto;
    }

    .chapter:last-child {
      border-bottom: none;
    }
  }
</style>
