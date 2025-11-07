<script>
  import registry from "../data/persons.json";

  const datasetModules = import.meta.glob("../data/people/*_life_events.json", {
    eager: true,
    import: "default",
  });

  const datasetMap = Object.entries(datasetModules).reduce(
    (accumulator, [path, data]) => {
      const segments = path.split("/");
      const fileName = segments[segments.length - 1] ?? "";
      const id = fileName.replace("_life_events.json", "");
      accumulator[id] = data;
      return accumulator;
    },
    {}
  );

  const registryEntries = (() => {
    const entries = [];
    const seen = new Set();
    if (Array.isArray(registry?.people)) {
      for (const entry of registry.people) {
        if (!entry?.id) continue;
        if (!datasetMap[entry.id]) continue;
        entries.push(entry);
        seen.add(entry.id);
      }
    }
    for (const id of Object.keys(datasetMap)) {
      if (seen.has(id)) continue;
      const data = datasetMap[id];
      const fallbackName = data?.person?.name ?? id.replace(/_/g, " ");
      entries.push({
        id,
        name: fallbackName,
        file: `people/${id}_life_events.json`,
      });
    }
    entries.sort((a, b) => a.name.localeCompare(b.name));
    return entries;
  })();

  let selectedPersonId =
    registryEntries[0]?.id ?? Object.keys(datasetMap)[0] ?? null;
  let previousPersonId = selectedPersonId;

  let dataset = selectedPersonId
    ? (datasetMap[selectedPersonId] ?? null)
    : null;
  let person = dataset?.person ?? {};
  let events = Array.isArray(dataset?.events) ? dataset.events : [];
  let portrait = person?.portrait;
  let personName = person?.name ?? "Select a person";
  let personSummary = person?.summary ?? "";
  let yearsLabel = "";
  let rolesLabel = "";
  let eventSlides = [];
  let totalSlides = 0;
  let slides = [];
  let totalPanels = 0;
  let hasEvents = totalSlides > 0;
  let hasDataset = Boolean(dataset);
  let hasPersonSummary = Boolean(personSummary);
  let activeIndex = 0;
  let activeEventIndex = -1;

  const formatters = {
    day: new Intl.DateTimeFormat("en", { dateStyle: "long" }),
    month: new Intl.DateTimeFormat("en", { year: "numeric", month: "long" }),
    year: new Intl.DateTimeFormat("en", { year: "numeric" }),
  };

  $: dataset = selectedPersonId ? (datasetMap[selectedPersonId] ?? null) : null;
  $: person = dataset?.person ?? {};
  $: events = Array.isArray(dataset?.events) ? dataset.events : [];
  $: portrait = person?.portrait;
  $: personName = person?.name ?? "Select a person";
  $: personSummary = person?.summary ?? "";
  $: yearsLabel = computeYearsLabel(person);
  $: rolesLabel = Array.isArray(person?.primary_roles)
    ? person.primary_roles.join(" · ")
    : "";
  $: eventSlides = events
    .slice()
    .sort((a, b) => toTimestamp(a) - toTimestamp(b))
    .map((event, eventIndex) => ({ ...event, eventIndex }));
  $: totalSlides = eventSlides.length;
  $: slides = totalSlides > 0 ? [{ type: "spacer" }, ...eventSlides] : [];
  $: totalPanels = slides.length;
  $: hasEvents = totalSlides > 0;
  $: hasDataset = Boolean(dataset);
  $: hasPersonSummary = Boolean(personSummary);
  $: activeEventIndex =
    totalSlides > 0
      ? Math.min(Math.max(activeIndex - 1, 0), totalSlides - 1)
      : -1;
  $: if (selectedPersonId !== previousPersonId) {
    activeIndex = 0;
    previousPersonId = selectedPersonId;
  }

  function computeYearsLabel(currentPerson) {
    if (!currentPerson) return "";
    const { birth_date: birth, death_date: death } = currentPerson;
    if (birth && death) {
      const birthYear = new Date(birth).getFullYear();
      const deathYear = new Date(death).getFullYear();
      if (!Number.isNaN(birthYear) && !Number.isNaN(deathYear)) {
        return `${birthYear} - ${deathYear}`;
      }
    }
    if (birth) {
      const birthYear = new Date(birth).getFullYear();
      if (!Number.isNaN(birthYear)) {
        return `${birthYear}`;
      }
    }
    return "";
  }

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
    {#if registryEntries.length > 0}
      <div class="toolbar">
        <div class="person-selector">
          <label for="person-select">Select person</label>
          <select id="person-select" bind:value={selectedPersonId}>
            {#each registryEntries as entry}
              <option value={entry.id}>{entry.name}</option>
            {/each}
          </select>
        </div>
      </div>
    {/if}
    <div class="masthead-content">
      <div class="full-info">
        <p class="eyebrow">Life Data Stories</p>
        <h1>{personName}</h1>
        {#if hasPersonSummary}
          <p class="summary">{personSummary}</p>
        {:else if hasDataset}
          <p class="summary placeholder">
            A summary is not available, but key life events are listed below.
          </p>
        {:else}
          <p class="summary placeholder">
            Select a person to explore their life timeline.
          </p>
        {/if}
        <div class="meta">
          {#if yearsLabel}
            <span>{yearsLabel}</span>
          {/if}
          {#if rolesLabel}
            <span>{rolesLabel}</span>
          {/if}
        </div>
      </div>
      {#if portrait?.image}
        <figure class="portrait">
          <img
            src={portrait.image}
            alt={portrait.alt ?? `Portrait of ${personName}`}
            loading="lazy"
            decoding="async"
          />
          {#if portrait.caption || portrait.source}
            <figcaption>
              {#if portrait.caption}
                <span>{portrait.caption}</span>
              {/if}
              {#if portrait.source}
                <a href={portrait.source} target="_blank" rel="noreferrer"
                  >{sourceLabel(portrait.source)}</a
                >
              {/if}
            </figcaption>
          {/if}
        </figure>
      {/if}
    </div>
    <div class="compact-info" aria-live="polite">
      <span class="name">{personName}</span>
      {#if yearsLabel}
        <span class="separator">·</span>
        <span class="lifespan">{yearsLabel}</span>
      {/if}
    </div>
  </header>

  <main class="slides" aria-live="polite" on:scroll={handleScroll}>
    {#if totalPanels > 0}
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
    {:else}
      <section class="slide empty">
        <div class="content">
          {#if hasDataset}
            <h2>Events unavailable</h2>
            <p>
              We could not find notable events for {personName}. Try
              regenerating the dataset.
            </p>
          {:else}
            <h2>Select a person to begin</h2>
            <p>
              Choose a person from the dropdown above to load their life events
              timeline.
            </p>
          {/if}
        </div>
      </section>
    {/if}
  </main>
  {#if hasEvents}
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

  .toolbar {
    display: flex;
    flex-wrap: wrap;
    gap: 1rem;
    margin-bottom: 1.25rem;
  }

  .person-selector {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
    min-width: min(260px, 100%);
  }

  .person-selector label {
    font-size: 0.7rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: rgba(148, 163, 184, 0.85);
  }

  .person-selector select {
    appearance: none;
    padding: 0.55rem 0.75rem;
    border-radius: 0.75rem;
    border: 1px solid rgba(148, 163, 184, 0.25);
    background: rgba(15, 23, 42, 0.6);
    color: #e2e8f0;
    font-size: 0.95rem;
    transition:
      border-color 0.2s ease,
      background-color 0.2s ease;
  }

  .person-selector select:focus {
    outline: none;
    border-color: #38bdf8;
    background: rgba(15, 23, 42, 0.8);
  }

  .full-info {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .masthead-content {
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
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

  .masthead.compact .toolbar {
    display: none;
  }

  .masthead.compact .full-info {
    display: none;
  }

  .masthead.compact .masthead-content {
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

  .summary.placeholder {
    color: #94a3b8;
    font-style: italic;
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

  .slide.empty {
    align-items: center;
    text-align: center;
  }

  .slide.empty .content {
    max-width: 48ch;
    margin: 0 auto;
    gap: 1rem;
  }

  .slide.empty h2 {
    font-size: 1.5rem;
    margin-bottom: 0.25rem;
  }

  .slide.empty p {
    color: #94a3b8;
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

  .portrait {
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    align-items: center;
    text-align: center;
  }

  .portrait img {
    width: min(220px, 80vw);
    height: auto;
    border-radius: 1rem;
    box-shadow: 0 10px 25px rgba(15, 23, 42, 0.45);
    border: 1px solid rgba(148, 163, 184, 0.3);
  }

  .portrait figcaption {
    font-size: 0.75rem;
    color: #94a3b8;
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
  }

  .portrait figcaption a {
    color: #facc15;
    text-decoration: none;
    font-weight: 500;
  }

  .portrait figcaption a:hover,
  .portrait figcaption a:focus {
    text-decoration: underline;
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

    .toolbar {
      margin-bottom: 1.75rem;
    }

    .person-selector {
      min-width: 280px;
    }

    .masthead-content {
      flex-direction: row;
      align-items: flex-start;
      gap: 2.5rem;
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

    .portrait img {
      width: 260px;
    }
  }
</style>
