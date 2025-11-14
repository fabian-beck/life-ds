<script>
  export let entries = [];
  export let getSummary = () => "";
  export let getStyle = () => ({});
  export let onSelectPerson = () => {};

  function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
  }

  function displayName(name = "") {
    if (typeof name !== "string") return "";
    return name.replace(/_/g, " ").replace(/\s+/g, " ").trim();
  }

  function handleSelect(id) {
    if (!id) return;
    onSelectPerson({ detail: id });
  }

  function summaryFor(entry) {
    return entry?.summary ?? getSummary(entry);
  }

  function initialsFromName(name = "") {
    const cleaned = displayName(name);
    const parts = cleaned
      .split(/\s+/)
      .map((segment) => segment.trim())
      .filter(Boolean);
    if (parts.length === 0) {
      return "";
    }
    if (parts.length === 1) {
      return parts[0].slice(0, 2).toUpperCase();
    }
    const first = parts[0].charAt(0).toUpperCase();
    const last = parts[parts.length - 1].charAt(0).toUpperCase();
    return `${first}${last}`;
  }

  function cardStyleVars(style) {
    if (!style || typeof style !== "object") return "";
    const segments = [];
    if (style.background) segments.push(`--card-bg: ${style.background}`);
    if (style.primary) segments.push(`--card-primary: ${style.primary}`);
    if (style.secondary) segments.push(`--card-secondary: ${style.secondary}`);
    if (style.backgroundPatternDataUrl) {
      segments.push(
        `--card-pattern-image: url("${style.backgroundPatternDataUrl}")`
      );
    }
    if (typeof style.patternOpacity === "number") {
      const opacity = clamp(style.patternOpacity, 0, 1);
      segments.push(`--card-pattern-opacity: ${opacity}`);
    }
    if (style.headingFont) {
      segments.push(`--card-heading-font: "${style.headingFont}", Inter, sans-serif`);
    }
    if (style.bodyFont) {
      segments.push(`--card-body-font: "${style.bodyFont}", Inter, sans-serif`);
    }
    return segments.join("; ");
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
      {#each entries as entry (entry.id)}
        {@const summary = summaryFor(entry)}
        {@const style = entry.style ?? getStyle(entry.id)}
        <article class="person-card" style={cardStyleVars(style)}>
          <figure class="person-thumb">
            {#if entry?.portrait?.image}
              <img
                src={entry.portrait.image}
                alt={entry.portrait.alt ??
                  `Portrait of ${displayName(entry.name)}`}
                loading="lazy"
                decoding="async"
              />
            {:else}
              <div class="thumb-fallback" aria-hidden="true">
                {initialsFromName(entry.name)}
              </div>
            {/if}
          </figure>
          <div class="card-body">
            <div class="card-header">
              <h2>{displayName(entry.name)}</h2>
              {#if entry.lifespan || (entry.primaryRoles?.length ?? 0) > 0}
                <p class="card-meta">
                  {#if entry.lifespan}
                    <span>{entry.lifespan}</span>
                  {/if}
                  {#if entry.lifespan && (entry.primaryRoles?.length ?? 0) > 0}
                    <span class="meta-separator" aria-hidden="true">·</span>
                  {/if}
                  {#if (entry.primaryRoles?.length ?? 0) > 0}
                    <span>{entry.primaryRoles.join(" · ")}</span>
                  {/if}
                </p>
              {/if}
            </div>
            {#if summary}
              <p class="card-summary">{summary}</p>
            {:else}
              <p class="card-summary placeholder">
                A summary is not available yet, but the timeline is ready.
              </p>
            {/if}
            <div class="card-footer">
              <button
                type="button"
                class="card-action"
                on:click={() => handleSelect(entry.id)}
                aria-label={`Open life story for ${displayName(entry.name)}`}
              >
                View story
              </button>
            </div>
          </div>
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
      rgba(15, 23, 42, 0.94) 0%,
      rgba(15, 23, 42, 0.9) 35%,
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
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 1.5rem;
    grid-auto-rows: 1fr;
  }

  .landing-empty {
    margin: 0;
    font-size: 1rem;
    color: #94a3b8;
  }

  .person-card {
    position: relative;
    display: grid;
    grid-template-columns: 82px 1fr;
    align-items: stretch;
    gap: 1rem;
    padding: 1.25rem 1.35rem;
    border-radius: 1rem;
    background-color: var(--card-bg, rgba(15, 23, 42, 0.94));
    border: 1px solid rgba(148, 163, 184, 0.18);
    box-shadow: 0 14px 32px rgba(15, 23, 42, 0.32);
    transition:
      transform 0.22s ease,
      border-color 0.22s ease,
      box-shadow 0.22s ease;
    min-height: 0;
    overflow: hidden;
    color: #e2e8f0;
    isolation: isolate;
  }

  .person-card::before,
  .person-card::after {
    content: "";
    position: absolute;
    inset: 0;
    border-radius: inherit;
    pointer-events: none;
    z-index: 0;
  }

  .person-card::before {
    background-image: var(--card-pattern-image, none);
    background-size: 220px 220px;
    background-repeat: repeat;
    opacity: var(--card-pattern-opacity, 0.18);
    mix-blend-mode: soft-light;
  }

  .person-card::after {
    background: linear-gradient(
      180deg,
      rgba(255, 255, 255, 0.04) 0%,
      rgba(0, 0, 0, 0.48) 100%
    );
  }

  .person-card:hover,
  .person-card:focus-within {
    transform: translateY(-4px);
    border-color: var(--card-secondary, rgba(56, 189, 248, 0.45));
    box-shadow: 0 18px 36px rgba(15, 23, 42, 0.42);
  }

  .person-card > * {
    position: relative;
    z-index: 1;
  }

  .person-thumb {
    margin: 0;
    width: 82px;
    height: 82px;
    border-radius: 0.9rem;
    overflow: hidden;
    background: rgba(15, 23, 42, 0.6);
    border: 1px solid rgba(148, 163, 184, 0.2);
    display: flex;
    align-items: center;
    justify-content: center;
    position: relative;
  }

  .person-thumb img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    object-position: top;
    display: block;
  }

  .thumb-fallback {
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    background: radial-gradient(
        circle at 30% 30%,
        var(--card-secondary, rgba(56, 189, 248, 0.35)),
        transparent 70%
      ),
      rgba(30, 41, 59, 0.82);
    color: var(--card-secondary, #e0f2fe);
    font-weight: 700;
    font-size: 1.2rem;
    letter-spacing: 0.08em;
  }

  .card-body {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    min-width: 0;
  }

  .card-header {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
  }

  .person-card h2 {
    margin: 0;
    font-size: 1.2rem;
    line-height: 1.2;
    color: var(--card-primary, #f8fafc);
    font-family: var(--card-heading-font, Inter, sans-serif);
  }

  .card-meta {
    margin: 0;
    display: flex;
    flex-wrap: wrap;
    gap: 0.45rem;
    font-size: 0.8rem;
    color: rgba(226, 232, 240, 0.72);
    font-family: var(--card-body-font, Inter, sans-serif);
  }

  .card-meta .meta-separator {
    color: rgba(148, 163, 184, 0.65);
  }

  .card-summary {
    margin: 0;
    font-size: 0.92rem;
    color: rgba(203, 213, 225, 0.92);
    line-height: 1.45;
    display: -webkit-box;
    -webkit-line-clamp: 4;
    -webkit-box-orient: vertical;
    overflow: hidden;
    font-family: var(--card-body-font, Inter, sans-serif);
  }

  .card-summary.placeholder {
    color: #94a3b8;
    font-style: italic;
  }

  .card-footer {
    margin-top: auto;
  }

  .card-action {
    align-self: flex-start;
    padding: 0.45rem 1rem;
    border-radius: 999px;
    border: 1px solid var(--card-secondary, rgba(56, 189, 248, 0.5));
    background: rgba(56, 189, 248, 0.16);
    color: var(--card-secondary, #38bdf8);
    font-size: 0.85rem;
    font-weight: 600;
    letter-spacing: 0.02em;
    cursor: pointer;
    transition:
      background-color 0.2s ease,
      border-color 0.2s ease,
      color 0.2s ease,
      transform 0.2s ease;
  }

  .card-action:hover,
  .card-action:focus {
    background: var(--card-secondary, #38bdf8);
    border-color: var(--card-secondary, #38bdf8);
    color: #0f172a;
    transform: translateY(-1px);
    outline: none;
  }

  .eyebrow {
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.75rem;
    color: var(--card-secondary, #38bdf8);
    margin: 0;
  }

  @media (max-width: 480px) {
    .person-card {
      grid-template-columns: 70px 1fr;
      padding: 1.1rem 1.2rem;
    }

    .person-thumb {
      width: 70px;
      height: 70px;
    }
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
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    }

    .person-card {
      padding: 1.5rem 1.75rem;
      grid-template-columns: 92px 1fr;
    }

    .person-thumb {
      width: 92px;
      height: 92px;
    }

    .person-card h2 {
      font-size: 1.3rem;
    }
  }
</style>
