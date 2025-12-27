<script>
  export let chapters = [];
  export let personsRegistry = [];
  export let onEventClick = () => {};

  // Helper to get person data by ID
  function getPersonById(personId) {
    return personsRegistry.find(p => p.id === personId);
  }

  // Extract year from date string (YYYY-MM-DD or YYYY)
  function getYear(dateString) {
    if (!dateString) return null;
    return parseInt(dateString.split('-')[0]);
  }

  // Calculate timeline boundaries (min/max years across all chapters)
  $: timelineBounds = (() => {
    if (!chapters || chapters.length === 0) return { minYear: 1800, maxYear: 2000 };
    const years = chapters.flatMap(c => [
      parseInt(c.date_start),
      parseInt(c.date_end)
    ]);
    return {
      minYear: Math.min(...years),
      maxYear: Math.max(...years)
    };
  })();

  // Calculate total year span
  $: totalSpan = (() => {
    const span = timelineBounds.maxYear - timelineBounds.minYear;
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

  // Define pixels per year scale
  const PIXELS_PER_YEAR = 15;

  // Calculate timeline width in pixels
  $: timelineWidthPx = totalSpan * PIXELS_PER_YEAR;

  // Generate year markers for the axis
  $: yearMarkers = (() => {
    const markers = [];
    const { minYear, maxYear } = timelineBounds;

    // Calculate appropriate interval (every 10, 20, 50, or 100 years)
    const span = maxYear - minYear;
    let interval = 10;
    if (span > 200) interval = 50;
    if (span > 500) interval = 100;

    // Generate markers at interval
    const startYear = Math.ceil(minYear / interval) * interval;
    for (let year = startYear; year <= maxYear; year += interval) {
      const offsetYears = year - minYear;
      const leftPx = offsetYears * PIXELS_PER_YEAR;
      markers.push({ year, leftPx });
    }

    return markers;
  })();

  // Calculate chapter positions in pixels
  $: chaptersWithPositions = (() => {
    if (!chapters || chapters.length === 0) return [];

    return chapters.map(chapter => {
      const startYear = parseInt(chapter.date_start);
      const endYear = parseInt(chapter.date_end);
      const offsetYears = startYear - timelineBounds.minYear;
      const span = endYear - startYear;

      // Remove date range from title (e.g., "Title (1815-1899)" -> "Title")
      const titleWithoutDates = chapter.title.replace(/\s*\(\d{4}-\d{4}\)\s*$/, '');

      return {
        ...chapter,
        title: titleWithoutDates,
        leftPx: offsetYears * PIXELS_PER_YEAR,
        widthPx: span * PIXELS_PER_YEAR
      };
    });
  })();

  // Extract unique persons from all chapters and calculate their timeline positions
  $: personsWithPositions = (() => {
    if (!chapters || chapters.length === 0 || !personsRegistry) return [];

    // Get unique person IDs from all chapters
    const personIds = new Set();
    chapters.forEach(chapter => {
      chapter.person_events?.forEach(event => {
        personIds.add(event.person_id);
      });
    });

    // Calculate position and width for each person in pixels
    return Array.from(personIds).map(personId => {
      const person = getPersonById(personId);
      if (!person) return null;

      const birthYear = getYear(person.birthDate);
      const deathYear = getYear(person.deathDate);

      if (!birthYear) return null;

      const startOffset = birthYear - timelineBounds.minYear;
      const endYear = deathYear || timelineBounds.maxYear;
      const lifespan = endYear - birthYear;

      return {
        person,
        personId,
        birthYear,
        deathYear,
        leftPx: startOffset * PIXELS_PER_YEAR,
        widthPx: lifespan * PIXELS_PER_YEAR,
        isAlive: !deathYear
      };
    }).filter(p => p !== null);
  })();
</script>

<div class="meta-timeline-container">
  <div class="timeline-wrapper" style="width: {timelineWidthPx}px;">
    <!-- Chapters row -->
    <div class="chapters-row">
      {#each chaptersWithPositions as chapter, index}
        <div
          class="chapter"
          data-chapter-index={index}
          style="left: {chapter.leftPx}px; width: {chapter.widthPx}px;"
        >
          <div class="chapter-header">
            <h3>{chapter.title}</h3>
          </div>
          <div class="chapter-body">
            <p class="bridge">{chapter.bridge_statement}</p>
          </div>
        </div>
      {/each}
    </div>

    <!-- Year axis -->
    <div class="year-axis">
      {#each yearMarkers as marker}
        <div class="year-marker" style="left: {marker.leftPx}px;">
          <div class="year-tick"></div>
          <div class="year-label">{marker.year}</div>
        </div>
      {/each}
    </div>

    <!-- Person lifespans -->
    <div class="persons-layer">
      {#each personsWithPositions as personData, index}
        <div
          class="person-lifespan"
          class:alive={personData.isAlive}
          style="left: {personData.leftPx}px; width: {personData.widthPx}px; top: {index * 50}px;"
          title="{personData.person.name.replace(/_/g, ' ')} ({personData.birthYear}–{personData.deathYear || 'present'})"
        >
          <div class="person-bar">
            <span class="person-birth">{personData.birthYear}</span>
            <span class="person-name">{personData.person.name.replace(/_/g, ' ')}</span>
            <span class="person-death">{personData.deathYear || '...'}</span>
          </div>
        </div>
      {/each}
    </div>
  </div>
</div>

<style>
  /* Container - full width scrollable panel */
  .meta-timeline-container {
    width: 100%;
    height: 100vh;
    overflow-x: auto;
    overflow-y: auto;
    padding: 1rem;
    background: rgba(4, 10, 24, 0.95);
  }

  /* Wrapper - fixed width based on timeline scale */
  .timeline-wrapper {
    position: relative;
    min-height: 600px;
  }

  /* Chapters row - absolute positioning */
  .chapters-row {
    position: relative;
    height: 150px;
    z-index: 1;
  }

  /* Individual chapter - absolutely positioned */
  .chapter {
    position: absolute;
    top: 0;
    height: 100%;
    border-right: 1px solid rgba(56, 189, 248, 0.3);
    padding: 1rem;
    background: rgba(15, 23, 42, 0.2);
  }

  .chapter:nth-child(even) {
    background: rgba(15, 23, 42, 0.3);
  }

  /* Chapter header */
  .chapter-header {
    margin-bottom: 0.75rem;
  }

  .chapter-header h3 {
    font-family: var(--heading-font, 'Space Grotesk', sans-serif);
    font-size: 1rem;
    margin: 0;
    color: #38bdf8;
    line-height: 1.3;
  }

  /* Chapter body */
  .chapter-body {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .bridge {
    font-style: italic;
    color: #94a3b8;
    margin: 0;
    line-height: 1.5;
    font-size: 0.85rem;
  }

  /* Year axis */
  .year-axis {
    position: relative;
    height: 60px;
    margin-top: 10px;
    border-top: 2px solid rgba(56, 189, 248, 0.4);
    z-index: 5;
  }

  .year-marker {
    position: absolute;
    top: 0;
  }

  .year-tick {
    width: 2px;
    height: 12px;
    background: rgba(56, 189, 248, 0.6);
    margin: 0 auto;
  }

  .year-label {
    margin-top: 4px;
    font-size: 0.75rem;
    color: #94a3b8;
    font-weight: 500;
    text-align: center;
    white-space: nowrap;
  }

  /* Persons layer */
  .persons-layer {
    position: relative;
    margin-top: 20px;
    min-height: 400px;
    z-index: 10;
  }

  /* Individual person lifespan */
  .person-lifespan {
    position: absolute;
    height: 40px;
    transition: all 0.2s;
  }

  .person-lifespan:hover {
    z-index: 100;
    transform: translateY(-2px);
  }

  .person-bar {
    height: 100%;
    background: linear-gradient(135deg, rgba(56, 189, 248, 0.6), rgba(154, 123, 255, 0.6));
    border: 2px solid rgba(56, 189, 248, 0.8);
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 12px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
    cursor: pointer;
  }

  .person-lifespan:hover .person-bar {
    background: linear-gradient(135deg, rgba(56, 189, 248, 0.8), rgba(154, 123, 255, 0.8));
    border-color: rgba(56, 189, 248, 1);
    box-shadow: 0 4px 12px rgba(56, 189, 248, 0.4);
  }

  .person-lifespan.alive .person-bar {
    background: linear-gradient(135deg, rgba(34, 197, 94, 0.6), rgba(56, 189, 248, 0.6));
    border-color: rgba(34, 197, 94, 0.8);
  }

  .person-lifespan.alive:hover .person-bar {
    background: linear-gradient(135deg, rgba(34, 197, 94, 0.8), rgba(56, 189, 248, 0.8));
    border-color: rgba(34, 197, 94, 1);
  }

  .person-birth {
    font-size: 0.75rem;
    color: #e2e8f0;
    font-weight: 500;
    white-space: nowrap;
    margin-right: 8px;
  }

  .person-name {
    font-weight: 600;
    font-size: 0.875rem;
    color: #ffffff;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    flex: 1;
  }

  .person-death {
    font-size: 0.75rem;
    color: #e2e8f0;
    font-weight: 500;
    margin-left: 8px;
    white-space: nowrap;
  }

  /* Responsive - keep horizontal scrolling on mobile */
  @media (max-width: 768px) {
    .meta-timeline-container {
      padding: 0.5rem;
    }

    /* Keep horizontal scroll behavior on mobile */
    .timeline-wrapper {
      /* Width is calculated dynamically, don't override */
    }

    /* Make chapters slightly narrower on mobile for easier scanning */
    .chapter-header h3 {
      font-size: 0.875rem;
    }

    .bridge {
      font-size: 0.75rem;
    }

    /* Adjust person bars for mobile */
    .person-bar {
      padding: 0 8px;
    }

    .person-name {
      font-size: 0.75rem;
    }

    .person-birth,
    .person-death {
      font-size: 0.65rem;
    }
  }
</style>
