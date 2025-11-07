<script>
  import { createEventDispatcher, tick } from "svelte";
  import {
    mdiChevronLeft,
    mdiChevronRight,
    mdiClose,
    mdiMapMarkerOutline,
    mdiLinkVariant,
  } from "@mdi/js";

  export let dataset = null;
  export let activeIndex = 0;
  export let hasRegistryEntries = false;
  export let styleConfig = null;

  const dispatch = createEventDispatcher();

  const formatters = {
    day: new Intl.DateTimeFormat("en", { dateStyle: "long" }),
    month: new Intl.DateTimeFormat("en", { year: "numeric", month: "long" }),
    year: new Intl.DateTimeFormat("en", { year: "numeric" }),
  };

  function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
  }

  function storyStyleVars(style) {
    if (!style || typeof style !== "object") return "";
    const segments = [];
    if (style.background) segments.push(`--story-bg: ${style.background}`);
    if (style.primary) segments.push(`--story-primary: ${style.primary}`);
    if (style.secondary) segments.push(`--story-secondary: ${style.secondary}`);
    if (style.backgroundPatternDataUrl) {
      segments.push(
        `--story-pattern-image: url(\"${style.backgroundPatternDataUrl}\")`
      );
    }
    if (typeof style.patternOpacity === "number") {
      const opacity = clamp(style.patternOpacity, 0, 1);
      segments.push(`--story-pattern-opacity: ${opacity}`);
    }
    return segments.join("; ");
  }

  $: person = dataset?.person ?? {};
  $: events = Array.isArray(dataset?.events) ? dataset.events : [];
  $: portrait = person?.portrait;
  $: personName = person?.name ?? "Select a person";
  $: personSummary = person?.summary ?? "";
  $: hasDataset = Boolean(dataset);
  $: hasPersonSummary = Boolean(personSummary);
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
  $: if (totalPanels === 0 && activeIndex !== 0) {
    activeIndex = 0;
  } else if (totalPanels > 0 && activeIndex >= totalPanels) {
    activeIndex = totalPanels - 1;
  }

  $: activeEventIndex =
    totalSlides > 0
      ? Math.min(Math.max(activeIndex - 1, 0), totalSlides - 1)
      : -1;

  let slidesContainer;

  async function scrollToIndex(index) {
    if (!slidesContainer) return;
    const clamped = Math.min(Math.max(index, 0), totalPanels - 1);
    // wait for DOM to settle
    await tick();
    const { clientWidth } = slidesContainer;
    if (!clientWidth) return;
    slidesContainer.scrollTo({
      left: clamped * clientWidth,
      behavior: "smooth",
    });
  }

  function prevSlide() {
    if (totalPanels === 0) return;
    activeIndex = Math.max(0, activeIndex - 1);
    scrollToIndex(activeIndex);
  }

  function nextSlide() {
    if (totalPanels === 0) return;
    activeIndex = Math.min(totalPanels - 1, activeIndex + 1);
    scrollToIndex(activeIndex);
  }

  function handleClose() {
    dispatch("close");
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

  function handleWheel(event) {
    if (event.ctrlKey) return;
    if (!slidesContainer || totalPanels === 0) return;
    const dominantDelta =
      Math.abs(event.deltaX) > Math.abs(event.deltaY)
        ? event.deltaX
        : event.deltaY;
    if (!dominantDelta) return;
    event.preventDefault();
    slidesContainer.scrollBy({
      left: dominantDelta,
      behavior: "smooth",
    });
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
</script>

<div
  class="story-view"
  style={storyStyleVars(styleConfig)}
  on:wheel={handleWheel}
>
  <header class="masthead" class:compact={activeIndex > 0}>
    {#if hasRegistryEntries}
      <div class="toolbar">
        <button
          type="button"
          class="close-story"
          on:click={handleClose}
          aria-label="Close story and return to the landing page"
        >
          <svg
            class="icon"
            viewBox="0 0 24 24"
            role="presentation"
            aria-hidden="true"
          >
            <path d={mdiClose} />
          </svg>
          <span class="btn-label">Close story</span>
        </button>
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
      <button
        type="button"
        class="close-story compact"
        on:click={handleClose}
        aria-label="Close story and return to the landing page"
      >
        <svg
          class="icon"
          viewBox="0 0 24 24"
          role="presentation"
          aria-hidden="true"
        >
          <path d={mdiClose} />
        </svg>
      </button>
    </div>
  </header>

  <div class="slides-wrapper">
    <main
      class="slides"
      aria-live="polite"
      bind:this={slidesContainer}
      on:scroll={handleScroll}
    >
      {#if totalPanels > 0}
        {#each slides as slide}
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
                      <span class="label">
                        <svg
                          class="icon icon-inline"
                          viewBox="0 0 24 24"
                          role="presentation"
                          aria-hidden="true"
                        >
                          <path d={mdiMapMarkerOutline} />
                        </svg>
                        <span class="label-text">Location</span>
                      </span>
                      <span>{formatLocations(slide.locations)}</span>
                    </li>
                  {/if}
                  {#if slide.sources?.length}
                    <li>
                      <span class="label">
                        <svg
                          class="icon icon-inline"
                          viewBox="0 0 24 24"
                          role="presentation"
                          aria-hidden="true"
                        >
                          <path d={mdiLinkVariant} />
                        </svg>
                        <span class="label-text">Sources</span>
                      </span>
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
            <h2>Events unavailable</h2>
            <p>
              We could not find notable events for {personName}. Try
              regenerating the dataset.
            </p>
          </div>
        </section>
      {/if}
    </main>
  </div>
  {#if hasEvents}
    <div
      class="indicator"
      role="img"
      aria-label={`Event ${activeEventIndex + 1} of ${totalSlides}`}
      style={`--active-index: ${activeEventIndex}`}
    >
      <div class="indicator-content">
        {#if totalPanels > 1}
          <!-- Prev/Next controls live inside the fixed indicator so the rest of
               the interface stays scrollable. -->
          <button
            type="button"
            class="nav-btn prev"
            on:click={prevSlide}
            aria-label="Go to previous slide"
            disabled={activeIndex === 0}
          >
            <svg
              class="icon"
              viewBox="0 0 24 24"
              role="presentation"
              aria-hidden="true"
            >
              <path d={mdiChevronLeft} />
            </svg>
          </button>
        {/if}
        <div class="indicator-track">
          <span class="indicator-highlight" />
          {#each eventSlides as _, idx}
            <span class="dot" class:active={idx === activeEventIndex} />
          {/each}
        </div>
        {#if totalPanels > 1}
          <button
            type="button"
            class="nav-btn next"
            on:click={nextSlide}
            aria-label="Go to next slide"
            disabled={activeIndex >= totalPanels - 1}
          >
            <svg
              class="icon"
              viewBox="0 0 24 24"
              role="presentation"
              aria-hidden="true"
            >
              <path d={mdiChevronRight} />
            </svg>
          </button>
        {/if}
      </div>
    </div>
  {/if}
</div>

<style>
  .story-view {
    flex: 1 1 auto;
    display: flex;
    flex-direction: column;
    position: relative;
    background-color: var(--story-bg, #0f172a);
    color: #e2e8f0;
    isolation: isolate;
  }

  .story-view::before {
    content: "";
    position: absolute;
    inset: 0;
    pointer-events: none;
    background-image: var(--story-pattern-image, none);
    background-size: 260px 260px;
    background-repeat: repeat;
    opacity: var(--story-pattern-opacity, 0.16);
    mix-blend-mode: soft-light;
    z-index: 0;
  }

  .story-view > * {
    position: relative;
    z-index: 1;
  }

  .masthead {
    padding: 1.75rem 1.5rem 1.25rem;
    display: flex;
    flex-direction: column;
    background: linear-gradient(
        180deg,
        rgba(255, 255, 255, 0.06) 0%,
        rgba(0, 0, 0, 0.55) 100%
      ),
      var(--story-bg, rgba(15, 23, 42, 0.92));
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
    align-items: center;
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
    overflow-x: auto;
    white-space: nowrap;
    text-overflow: clip;
    -ms-overflow-style: none;
    scrollbar-width: none;
    touch-action: pan-x;
    padding-bottom: 0.1rem;
  }

  .compact-info .name::-webkit-scrollbar {
    display: none;
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

  .close-story {
    border: 1px solid var(--story-primary, rgba(148, 163, 184, 0.3));
    background: rgba(255, 255, 255, 0.05);
    color: var(--story-primary, #e2e8f0);
    border-radius: 999px;
    padding: 0.45rem 0.95rem;
    font-size: 0.85rem;
    font-weight: 600;
    cursor: pointer;
    flex: 0 0 auto;
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    transition:
      border-color 0.2s ease,
      background-color 0.2s ease,
      color 0.2s ease;
  }

  .close-story:hover,
  .close-story:focus {
    border-color: var(--story-primary, rgba(148, 163, 184, 0.6));
    background: rgba(255, 255, 255, 0.12);
    outline: none;
  }

  .close-story.compact {
    flex: 0 0 auto;
    padding: 0.35rem 0.75rem;
    font-size: 0.8rem;
    gap: 0.4rem;
  }

  .close-story .btn-label {
    line-height: 1;
  }

  .icon {
    width: 1.1em;
    height: 1.1em;
    fill: currentColor;
    flex: 0 0 auto;
  }

  .nav-btn .icon {
    width: 1.2em;
    height: 1.2em;
  }

  .icon-inline {
    width: 1em;
    height: 1em;
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
    justify-content: space-between;
    gap: 0.75rem;
  }

  .eyebrow {
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.75rem;
    color: var(--story-secondary, #38bdf8);
    margin: 0;
  }

  h1 {
    margin: 0;
    font-size: 1.9rem;
    line-height: 1.1;
    color: var(--story-primary, #f8fafc);
  }

  .summary {
    margin: 0;
    font-size: 0.95rem;
    color: rgba(226, 232, 240, 0.88);
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
    color: rgba(148, 163, 184, 0.85);
    transition: font-size 0.25s ease;
  }

  .masthead:not(.compact) .compact-info {
    display: none;
  }

  .slides-wrapper {
    flex: 1 1 auto;
    position: relative;
    min-height: calc(100vh - var(--header-height, 0px));
  }

  .slides {
    flex: 1 1 auto;
    display: flex;
    scroll-snap-type: x mandatory;
    overflow-x: auto;
    overflow-y: hidden;
    height: calc(100vh - var(--header-height, 0px));
    scroll-behavior: smooth;
    position: relative;
  }

  .slide {
    scroll-snap-align: start;
    flex: 0 0 100%;
    height: 100%;
    min-height: 100%;
    padding: 2.75rem 1.5rem 3.25rem;
    display: flex;
    flex-direction: column;
    justify-content: center;
    position: relative;
    gap: 1.25rem;
    background-color: var(--story-bg, #0f172a);
    border-right: 1px solid rgba(148, 163, 184, 0.12);
    overflow: hidden;
  }

  .slide::before {
    content: "";
    position: absolute;
    inset: 0;
    background: linear-gradient(
      180deg,
      rgba(255, 255, 255, 0.05) 0%,
      rgba(0, 0, 0, 0.55) 100%
    );
    mix-blend-mode: soft-light;
    pointer-events: none;
    z-index: 0;
  }

  .slide > * {
    position: relative;
    z-index: 1;
  }

  .nav-btn {
    pointer-events: auto;
    width: 2.4rem;
    height: 2.4rem;
    border-radius: 999px;
    border: 1px solid var(--story-primary, rgba(148, 163, 184, 0.35));
    background: rgba(255, 255, 255, 0.05);
    color: var(--story-primary, #e2e8f0);
    font-size: 1.15rem;
    font-weight: 600;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    transition:
      background-color 0.2s ease,
      border-color 0.2s ease,
      color 0.2s ease,
      transform 0.2s ease;
  }

  .nav-btn:hover,
  .nav-btn:focus {
    background: rgba(255, 255, 255, 0.15);
    border-color: var(--story-primary, rgba(148, 163, 184, 0.6));
    transform: scale(1.05);
    outline: none;
  }

  .nav-btn:disabled {
    opacity: 0.35;
    cursor: default;
    transform: none;
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
    padding: 0.5rem 1.1rem;
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

  /* Keep the indicator visually present but allow underlying slides to receive
     pointer events (so dragging/panning works anywhere). Only the nav buttons
     inside the indicator should accept pointer events. */
  .indicator-content {
    pointer-events: auto;
    display: flex;
    align-items: center;
    gap: 0.9rem;
  }

  .indicator .nav-btn {
    pointer-events: auto;
  }

  /* Let the track and dots remain transparent to pointer input so users can
     drag the slides even when starting the gesture over the indicator area. */
  .indicator-track {
    pointer-events: none;
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
    background: var(--story-secondary, rgba(56, 189, 248, 0.45));
    opacity: 0.45;
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
    background: var(--story-secondary, #38bdf8);
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
    color: var(--story-secondary, #facc15);
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
    color: var(--story-secondary, #38bdf8);
    font-weight: 600;
  }

  .age {
    margin: 0;
    font-size: 0.85rem;
    color: rgba(148, 163, 184, 0.85);
  }

  h2 {
    margin: 0;
    font-size: 1.35rem;
    line-height: 1.25;
    color: var(--story-primary, #f8fafc);
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
    color: rgba(148, 163, 184, 0.76);
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
  }

  .label-text {
    line-height: 1;
  }

  .sources {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
  }

  .sources a {
    color: var(--story-secondary, #facc15);
    text-decoration: none;
    font-weight: 500;
  }

  .sources a:hover,
  .sources a:focus {
    text-decoration: underline;
  }

  @media (min-width: 768px) {
    .masthead {
      padding: 2rem 3rem 1.5rem;
    }

    .toolbar {
      margin-bottom: 1.75rem;
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
      height: calc(100vh - var(--header-height, 0px));
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
