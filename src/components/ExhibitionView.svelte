<script>
  export let dataset = null;
  export let isLoading = false;
  export let styleConfig = null;

  // Extract events from dataset
  $: events = dataset?.events ?? [];
  $: person = dataset?.person ?? null;
  $: roles = person?.primary_roles ?? [];

  // Number of columns = number of events
  $: totalColumns = events.length;

  // Generate floating role tags with varied positions, sizes, and animation delays
  $: floatingRoles = roles.flatMap((role, roleIndex) => {
    // Create 3-5 instances of each role
    const count = 3 + Math.floor(Math.random() * 3);
    return Array.from({ length: count }, (_, i) => {
      const seed = roleIndex * 10 + i;
      return {
        text: role,
        left: ((seed * 37 + i * 71) % 96) + 2, // 2-98% (ultra wide)
        top: ((seed * 53 + i * 41) % 96) + 2, // 2-98% (full height)
        size: 0.7 + (seed % 5) * 0.25, // 0.7-1.7rem
        delay: (seed * 0.7) % 20, // 0-20s delay
        duration: 25 + (seed % 15), // 25-40s duration
        direction: seed % 2 === 0 ? 1 : -1, // alternate directions
      };
    });
  });

  // Compute style variables
  $: primaryColor = styleConfig?.primary ?? "#38BDF8";
  $: secondaryColor = styleConfig?.secondary ?? "#FACC15";
  $: backgroundColor = styleConfig?.background ?? "#0F172A";
  $: backgroundRgb = styleConfig?.backgroundRgb ?? "15, 23, 42";
  $: backgroundPatternDataUrl = styleConfig?.backgroundPatternDataUrl ?? null;
  $: headingFont = styleConfig?.headingFont ?? "Inter";
  $: bodyFont = styleConfig?.bodyFont ?? "Inter";

  // Format display name (underscore to space)
  function displayName(value = "") {
    if (typeof value !== "string") return "";
    return value.replace(/_/g, " ").replace(/\s+/g, " ").trim();
  }

  // Format year from date string
  function formatYear(dateStr) {
    if (!dateStr) return "";
    const match = dateStr.match(/^(-?\d+)/);
    return match ? match[1] : "";
  }
</script>

<div
  class="exhibition-container"
  style="
    --primary-color: {primaryColor};
    --secondary-color: {secondaryColor};
    --background-color: {backgroundColor};
    --background-rgb: {backgroundRgb};
    --heading-font: {headingFont};
    --body-font: {bodyFont};
    {backgroundPatternDataUrl
    ? `--background-pattern: url('${backgroundPatternDataUrl}');`
    : ''}
  "
>
  {#if isLoading}
    <div class="loading">
      <span>Loading...</span>
    </div>
  {:else if !dataset}
    <div class="error">
      <span>No data available</span>
    </div>
  {:else}
    <!-- Floating role tags in background -->
    <div class="floating-roles">
      {#each floatingRoles as role, i}
        <span
          class="floating-role"
          style="
            left: {role.left}%;
            top: {role.top}%;
            font-size: {role.size}rem;
            animation-delay: -{role.delay}s;
            animation-duration: {role.duration}s;
            --drift-direction: {role.direction};
          "
        >
          {role.text}
        </span>
      {/each}
    </div>

    <!-- Header with repeating person name -->
    <header class="exhibition-header">
      <div class="name-marquee">
        {#each Array(10) as _, i}
          <span class="name-item">
            {displayName(person?.name)}
            {#if person?.birth_date || person?.death_date}
              <span class="life-span"
                >{formatYear(person?.birth_date)}–{formatYear(
                  person?.death_date
                )}</span
              >
            {/if}
          </span>
        {/each}
      </div>
    </header>

    <!-- Events grid with featured box -->
    <div class="events-container" style="--total-columns: {totalColumns};">
      <div>
        <!-- Featured box spanning first two columns -->
        <div class="featured-box">
          <!-- Content TBD -->
        </div>

        <!-- Event cards -->
        {#each events as event}
          <div class="event-card">
            <div class="event-year">{formatYear(event.date)}</div>
            <div class="event-title">{event.title}</div>
          </div>
        {/each}
      </div>
    </div>
  {/if}
</div>

<style>
  .exhibition-container {
    width: 100vw;
    height: 100vh;
    background-color: var(--background-color);
    background-image: var(--background-pattern);
    background-size: 160px 160px;
    background-blend-mode: soft-light;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    font-family: var(--body-font), "Inter", sans-serif;
    color: #e2e8f0;
    position: relative;
  }

  .floating-roles {
    position: absolute;
    inset: 0;
    pointer-events: none;
    z-index: 0;
    overflow: hidden;
  }

  .floating-role {
    position: absolute;
    font-family: var(--heading-font), "Inter", sans-serif;
    font-weight: 300;
    text-transform: uppercase;
    letter-spacing: 0.15em;
    color: var(--primary-color);
    opacity: 0.12;
    white-space: nowrap;
    animation: float-drift linear infinite;
    will-change: transform;
  }

  @keyframes float-drift {
    0% {
      transform: translate(0, 0) rotate(0deg);
    }
    25% {
      transform: translate(calc(var(--drift-direction) * 2vw), -18vh)
        rotate(calc(var(--drift-direction) * 2deg));
    }
    50% {
      transform: translate(calc(var(--drift-direction) * 3vw), 12vh)
        rotate(0deg);
    }
    75% {
      transform: translate(calc(var(--drift-direction) * 1vw), 28vh)
        rotate(calc(var(--drift-direction) * -1deg));
    }
    100% {
      transform: translate(0, 0) rotate(0deg);
    }
  }

  .loading,
  .error {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    font-size: 1.5rem;
    color: rgba(226, 232, 240, 0.6);
  }

  .exhibition-header {
    height: 10vh;
    display: flex;
    align-items: center;
    overflow: hidden;
    background: linear-gradient(
      to bottom,
      rgba(var(--background-rgb), 0.95),
      rgba(var(--background-rgb), 0.8)
    );
    border-bottom: 2px solid var(--primary-color);
    flex-shrink: 0;
    position: relative;
    z-index: 1;
  }

  .name-marquee {
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
    padding: 0 2rem;
    white-space: nowrap;
  }

  .name-item {
    font-family: var(--heading-font), "Inter", sans-serif;
    font-size: 2rem;
    font-weight: 700;
    color: var(--primary-color);
  }

  .life-span {
    font-size: 1.25rem;
    font-weight: 400;
    color: rgba(226, 232, 240, 0.7);
    margin-left: 0.5rem;
  }

  .events-container {
    flex: 1;
    padding: 2rem;
    overflow: auto;
    position: relative;
    z-index: 1;
    display: grid;
    grid-template-columns: repeat(var(--total-columns), 1fr);
    grid-template-rows: 1fr 1fr;
    align-items: center;
    gap: 1rem;
  }

  .events-container > div:first-child {
    display: contents;
  }

  .featured-box {
    grid-column: 1 / 3;
    grid-row: 1;
    background: rgba(var(--background-rgb), 0.7);
    border-radius: 0.5rem;
    border: 2px solid var(--primary-color);
    padding: 1.5rem;
    min-height: 200px;
    align-self: center;
    min-width: 0;
  }

  .event-card {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
    padding: 1rem 0.5rem;
    background: rgba(var(--background-rgb), 0.6);
    border-radius: 0.5rem;
    border: 1px solid rgba(226, 232, 240, 0.1);
    height: 120px;
    align-self: center;
    grid-row: 1;
    min-width: 0;
  }

  /* First two events go in row 2 below the featured box */
  .event-card:nth-child(2) {
    grid-column: 1;
    grid-row: 2;
  }

  .event-card:nth-child(3) {
    grid-column: 2;
    grid-row: 2;
  }

  .event-year {
    font-size: 1.25rem;
    font-weight: 600;
    color: var(--secondary-color);
    margin-bottom: 0.5rem;
  }

  .event-title {
    font-family: var(--heading-font), "Inter", sans-serif;
    font-size: 0.9rem;
    font-weight: 500;
    color: #e2e8f0;
    line-height: 1.3;
    overflow: hidden;
    display: -webkit-box;
    -webkit-line-clamp: 4;
    line-clamp: 4;
    -webkit-box-orient: vertical;
  }
</style>
