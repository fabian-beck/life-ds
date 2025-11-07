<script>
  import dataset from '../data/alan_turing_life_events.json';

  const { person, events = [] } = dataset;

  const slides = [...events].sort((a, b) => toTimestamp(a) - toTimestamp(b));
  const totalSlides = slides.length;

  function toTimestamp(event) {
    if (!event?.date) return Number.POSITIVE_INFINITY;
    const precision = event.date_precision ?? 'day';
    const iso =
      precision === 'year'
        ? `${event.date}-01-01T00:00:00Z`
        : precision === 'month'
        ? `${event.date}-01T00:00:00Z`
        : `${event.date}T00:00:00Z`;
    return Date.parse(iso);
  }

  const formatters = {
    day: new Intl.DateTimeFormat('en', { dateStyle: 'long' }),
    month: new Intl.DateTimeFormat('en', { year: 'numeric', month: 'long' }),
    year: new Intl.DateTimeFormat('en', { year: 'numeric' })
  };

  function formatDate(event) {
    if (!event?.date) return 'Date unavailable';
    const precision = event.date_precision ?? 'day';
    const formatter = formatters[precision] ?? formatters.day;
    const iso =
      precision === 'year'
        ? `${event.date}-01-01T00:00:00Z`
        : precision === 'month'
        ? `${event.date}-01T00:00:00Z`
        : `${event.date}T00:00:00Z`;
    return formatter.format(new Date(iso));
  }

  function formatAgeLabel(age) {
    if (age === null || age === undefined) return null;
    if (age === 0) return 'At birth';
    return `Age ${age}`;
  }

  function formatLocations(locations = []) {
    return locations.join(' · ');
  }

  function sourceLabel(url) {
    try {
      const { hostname } = new URL(url);
      return hostname.replace(/^www\./, '');
    } catch (error) {
      return url;
    }
  }
</script>

<div class="shell">
  <header class="masthead">
    <p class="eyebrow">Life Data Stories</p>
    <h1>{person.name}</h1>
    <p class="summary">{person.summary}</p>
    <div class="meta">
      <span>{new Date(person.birth_date).getFullYear()} – {new Date(person.death_date).getFullYear()}</span>
      <span>{person.primary_roles.join(' · ')}</span>
    </div>
  </header>

  <main class="slides" aria-live="polite">
    {#each slides as event, index}
      <section class="slide" aria-label={`Slide ${index + 1} of ${totalSlides}: ${event.title}`}>
        <div class="count">{index + 1} / {totalSlides}</div>
        <div class="content">
          <p class="date">{formatDate(event)}</p>
          {#if formatAgeLabel(event.age)}
            <p class="age">{formatAgeLabel(event.age)}</p>
          {/if}
          <h2>{event.title}</h2>
          <p class="description">{event.description}</p>
          <ul class="details">
            {#if event.locations?.length}
              <li>
                <span class="label">Location</span>
                <span>{formatLocations(event.locations)}</span>
              </li>
            {/if}
            {#if event.sources?.length}
              <li>
                <span class="label">Sources</span>
                <span class="sources">
                  {#each event.sources as source}
                    <a href={source} target="_blank" rel="noreferrer">{sourceLabel(source)}</a>
                  {/each}
                </span>
              </li>
            {/if}
          </ul>
        </div>
      </section>
    {/each}
  </main>
</div>

<style>
  :global(body) {
    overscroll-behavior: contain;
  }

  :global(:root) {
    --header-height: 11.5rem;
  }

  .shell {
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    color: #e2e8f0;
  }

  .masthead {
    padding: 1.75rem 1.5rem 1.25rem;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    background: rgba(15, 23, 42, 0.92);
    backdrop-filter: blur(12px);
    border-bottom: 1px solid rgba(148, 163, 184, 0.16);
    position: sticky;
    top: 0;
    z-index: 2;
  }

  .eyebrow {
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.75rem;
    color: #38bdf8;
    margin: 0;
  }

  h1 {
    margin: 0;
    font-size: 1.9rem;
    line-height: 1.1;
  }

  .summary {
    margin: 0;
    font-size: 0.95rem;
    color: #cbd5f5;
  }

  .meta {
    display: flex;
    flex-wrap: wrap;
    gap: 0.75rem;
    font-size: 0.8rem;
    color: #94a3b8;
  }

  .slides {
    flex: 1 1 auto;
    scroll-snap-type: y mandatory;
    overflow-y: auto;
    height: calc(100vh - var(--header-height));
  }

  .slide {
    scroll-snap-align: start;
    min-height: calc(100vh - var(--header-height));
    padding: 2.75rem 1.5rem 3.25rem;
    display: flex;
    flex-direction: column;
    justify-content: center;
    position: relative;
    gap: 1.25rem;
    background: linear-gradient(180deg, rgba(15, 23, 42, 0.82) 0%, rgba(15, 23, 42, 0.6) 100%);
    border-bottom: 1px solid rgba(148, 163, 184, 0.12);
  }

  .count {
    position: absolute;
    top: 1.25rem;
    right: 1.5rem;
    font-size: 0.8rem;
    letter-spacing: 0.08em;
    color: rgba(148, 163, 184, 0.85);
  }

  .content {
    display: flex;
    flex-direction: column;
    gap: 0.8rem;
  }

  .date {
    margin: 0;
    font-size: 0.9rem;
    color: #38bdf8;
    font-weight: 600;
  }

  .age {
    margin: 0;
    font-size: 0.85rem;
    color: #94a3b8;
  }

  h2 {
    margin: 0;
    font-size: 1.35rem;
    line-height: 1.25;
  }

  .description {
    margin: 0;
    font-size: 1rem;
    color: #e2e8f0;
  }

  .details {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    font-size: 0.85rem;
  }

  .details li {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
  }

  .label {
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.7rem;
    color: rgba(148, 163, 184, 0.8);
  }

  .sources {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
  }

  .sources a {
    color: #facc15;
    text-decoration: none;
    font-weight: 500;
  }

  .sources a:hover,
  .sources a:focus {
    text-decoration: underline;
  }

  @media (min-width: 768px) {
    :global(:root) {
      --header-height: 9.5rem;
    }

    .masthead {
      padding: 2rem 3rem 1.5rem;
    }

    h1 {
      font-size: 2.4rem;
    }

    .slides {
      height: calc(100vh - var(--header-height));
    }

    .slide {
      min-height: calc(100vh - var(--header-height));
      padding: 3.5rem 4rem 4rem;
      gap: 1.75rem;
    }

    h2 {
      font-size: 1.85rem;
    }

    .description {
      font-size: 1.05rem;
      max-width: 48ch;
    }

    .details {
      font-size: 0.9rem;
      flex-direction: row;
      gap: 2rem;
    }

    .details li {
      max-width: 22rem;
    }
  }
</style>
