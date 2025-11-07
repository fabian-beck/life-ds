<script>
  import dataset from "../data/alan_turing_life_events.json";

  const { person, events = [] } = dataset;

  const yearsLabel =
    person?.birth_date && person?.death_date
      ? `${new Date(person.birth_date).getFullYear()} - ${new Date(person.death_date).getFullYear()}`
      : person?.birth_date
        ? `${new Date(person.birth_date).getFullYear()}`
        : "";

  const rolesLabel = Array.isArray(person?.primary_roles)
    ? person.primary_roles.join(" · ")
    : "";

  const eventSlides = [...events]
    .sort((a, b) => toTimestamp(a) - toTimestamp(b))
    .map((event, eventIndex) => ({ ...event, eventIndex }));
  const slides = [{ type: "spacer" }, ...eventSlides];
  const totalSlides = eventSlides.length;
  const totalPanels = slides.length;
  let activeIndex = 0;
  $: activeEventIndex =
    totalSlides > 0
      ? Math.min(Math.max(activeIndex - 1, 0), totalSlides - 1)
      : -1;

  function toTimestamp(event) {
    if (!event?.date) return Number.POSITIVE_INFINITY;
    const precision = event.date_precision ?? "day";
    const iso =
      precision === "year"
        ? `${event.date}-01-01T00:00:00Z`
        : precision === "month"
          ? `${event.date}-01T00:00:00Z`
          : `${event.date}T00:00:00Z`;
    return Date.parse(iso);
  }

  const formatters = {
    day: new Intl.DateTimeFormat("en", { dateStyle: "long" }),
    month: new Intl.DateTimeFormat("en", { year: "numeric", month: "long" }),
    year: new Intl.DateTimeFormat("en", { year: "numeric" }),
  };

  function formatDate(event) {
    if (!event?.date) return "Date unavailable";
    const precision = event.date_precision ?? "day";
    const formatter = formatters[precision] ?? formatters.day;
    const iso =
      precision === "year"
        ? `${event.date}-01-01T00:00:00Z`
        : precision === "month"
          ? `${event.date}-01T00:00:00Z`
          : `${event.date}T00:00:00Z`;
    return formatter.format(new Date(iso));
  }

  function formatAgeLabel(age) {
    if (age === null || age === undefined) return null;
    if (age === 0) return "At birth";
    return `Age ${age}`;
  }

  function formatLocations(locations = []) {
    return locations.join(" · ");
  }

  function sourceLabel(url) {
    try {
      const { hostname } = new URL(url);
      return hostname.replace(/^www\./, "");
    } catch (error) {
      return url;
    }
  }

  function handleScroll(event) {
    if (totalPanels === 0) {
      activeIndex = 0;
      return;
    }
    const { scrollLeft, clientWidth } = event.target;
    if (!clientWidth) return;
    const index = Math.round(scrollLeft / clientWidth);
    activeIndex = Math.min(Math.max(index, 0), totalPanels - 1);
  }
</script>

<div class="shell">
  <header class="masthead" class:compact={activeIndex > 0}>
    <div class="full-info">
      <p class="eyebrow">Life Data Stories</p>
      <h1>{person.name}</h1>
      <p class="summary">{person.summary}</p>
      <div class="meta">
        {#if yearsLabel}
          <span>{yearsLabel}</span>
        {/if}
        {#if rolesLabel}
          <span>{rolesLabel}</span>
        {/if}
      </div>
    </div>
    <div class="compact-info" aria-live="polite">
      <span class="name">{person.name}</span>
      {#if yearsLabel}
        <span class="separator">·</span>
        <span class="lifespan">{yearsLabel}</span>
      {/if}
    </div>
  </header>

  <main class="slides" aria-live="polite" on:scroll={handleScroll}>
    {#each slides as slide, index}
      <section
        class="slide"
        class:spacer={slide.type === "spacer"}
        aria-hidden={slide.type === "spacer"}
        aria-label={slide.type === "spacer"
          ? null
          : `Slide ${slide.eventIndex + 1} of ${totalSlides}: ${slide.title}`}
      >
        {#if slide.type !== "spacer"}
          <div class="content">
            <p class="date">{formatDate(slide)}</p>
            {#if formatAgeLabel(slide.age)}
              <p class="age">{formatAgeLabel(slide.age)}</p>
            {/if}
            <h2>{slide.title}</h2>
            <p class="description">{slide.description}</p>
            <ul class="details">
              {#if slide.locations?.length}
                <li>
                  <span class="label">Location</span>
                  <span>{formatLocations(slide.locations)}</span>
                </li>
              {/if}
              {#if slide.sources?.length}
                <li>
                  <span class="label">Sources</span>
                  <span class="sources">
                    {#each slide.sources as source}
                      <a href={source} target="_blank" rel="noreferrer"
                        >{sourceLabel(source)}</a
                      >
                    {/each}
                  </span>
                </li>
              {/if}
            </ul>
          </div>
        {/if}
      </section>
    {/each}
  </main>
  {#if totalSlides > 0}
    <div
      class="indicator"
      role="img"
      aria-label={`Event ${activeEventIndex + 1} of ${totalSlides}`}
      style={`--active-index: ${activeEventIndex}`}
    >
      <div class="indicator-track">
        <span class="indicator-highlight" />
        {#each eventSlides as _, idx}
          <span class="dot" class:active={idx === activeEventIndex} />
        {/each}
      </div>
    </div>
  {/if}
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
    background: rgba(15, 23, 42, 0.92);
    backdrop-filter: blur(12px);
    border-bottom: 1px solid rgba(148, 163, 184, 0.16);
    position: sticky;
    top: 0;
    z-index: 2;
    transition: padding 0.25s ease;
  }

  .full-info {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .compact-info {
    display: none;
    align-items: center;
    gap: 0.6rem;
    font-size: 0.95rem;
    font-weight: 600;
    color: #e2e8f0;
    white-space: nowrap;
    max-width: 100%;
    overflow: hidden;
  }

  .compact-info span {
    min-width: 0;
  }

  .compact-info .name {
    font-weight: 700;
    letter-spacing: 0.01em;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .compact-info .separator {
    color: rgba(148, 163, 184, 0.8);
    flex: 0 0 auto;
  }

  .compact-info .lifespan {
    color: #94a3b8;
    font-weight: 500;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .masthead.compact {
    padding: 0.85rem 1.25rem;
    flex-direction: row;
    align-items: center;
  }

  .masthead.compact .full-info {
    display: none;
  }

  .masthead.compact .compact-info {
    display: flex;
    width: 100%;
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
    transition:
      opacity 0.25s ease,
      transform 0.25s ease;
  }

  .meta {
    display: flex;
    flex-wrap: wrap;
    gap: 0.75rem;
    font-size: 0.8rem;
    color: #94a3b8;
    transition: font-size 0.25s ease;
  }

  .masthead:not(.compact) .compact-info {
    display: none;
  }

  .slides {
    flex: 1 1 auto;
    display: flex;
    scroll-snap-type: x mandatory;
    overflow-x: auto;
    overflow-y: hidden;
    height: calc(100vh - var(--header-height));
    scroll-behavior: smooth;
    position: relative;
  }

  .slide {
    scroll-snap-align: start;
    flex: 0 0 100%;
    height: 100%;
    padding: 2.75rem 1.5rem 3.25rem;
    display: flex;
    flex-direction: column;
    justify-content: center;
    position: relative;
    gap: 1.25rem;
    background: linear-gradient(
      180deg,
      rgba(15, 23, 42, 0.82) 0%,
      rgba(15, 23, 42, 0.6) 100%
    );
    border-right: 1px solid rgba(148, 163, 184, 0.12);
  }

  .slide.spacer {
    background: transparent;
    border-right: none;
    pointer-events: none;
  }

  .indicator {
    --dot-size: 0.55rem;
    --dot-gap: 0.5rem;
    position: fixed;
    bottom: 2rem;
    left: 50%;
    transform: translateX(-50%);
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0.4rem 0.75rem;
    border-radius: 9999px;
    background: rgba(15, 23, 42, 0.65);
    backdrop-filter: blur(6px);
    box-shadow: 0 10px 30px rgba(15, 23, 42, 0.25);
    pointer-events: none;
    z-index: 5;
  }

  .indicator::after {
    content: "";
    position: absolute;
    inset: 0;
    border-radius: inherit;
    border: 1px solid rgba(148, 163, 184, 0.2);
    pointer-events: none;
  }

  .indicator-track {
    position: relative;
    display: flex;
    align-items: center;
    gap: var(--dot-gap);
  }

  .indicator-highlight {
    position: absolute;
    top: 50%;
    left: 0;
    width: var(--dot-size);
    height: var(--dot-size);
    border-radius: 9999px;
    background: rgba(56, 189, 248, 0.4);
    transform: translateX(
        calc(var(--active-index) * (var(--dot-size) + var(--dot-gap)))
      )
      translateY(-50%);
    transition:
      transform 0.35s cubic-bezier(0.22, 1, 0.36, 1),
      background-color 0.3s ease;
    z-index: 0;
  }

  .dot {
    position: relative;
    z-index: 1;
    width: var(--dot-size);
    height: var(--dot-size);
    border-radius: 9999px;
    background: rgba(148, 163, 184, 0.3);
    transition:
      background-color 0.25s ease,
      transform 0.25s ease;
  }

  .dot.active {
    background: #38bdf8;
    transform: scale(1.2);
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

    .masthead.compact {
      padding: 1rem 2.5rem;
    }

    .compact-info {
      font-size: 1.05rem;
    }
  }
</style>
