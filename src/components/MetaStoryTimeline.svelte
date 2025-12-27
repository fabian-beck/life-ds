<script>
  export let chapters = [];
  export let personsRegistry = [];
  export let onEventClick = () => {};
  export let subtopics = [];

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

  // Constants for theme grouping vertical spacing
  const THEME_TITLE_HEIGHT = 60; // Increased to add more space below title
  const PERSON_ROW_HEIGHT = 50;
  const THEME_SPACING = 10; // Reduced spacing between theme groups

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

  // Helper: Extract persons from chapters (fallback when no subtopics)
  function extractPersonsFromChapters() {
    if (!chapters || chapters.length === 0 || !personsRegistry) return [];

    const personIds = new Set();
    chapters.forEach(chapter => {
      chapter.person_events?.forEach(event => {
        personIds.add(event.person_id);
      });
    });

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
        isAlive: !deathYear,
        portrait: person.portrait?.thumbnail || person.portrait?.image
      };
    }).filter(p => p !== null);
  }

  // Group persons by subtopic/theme, preserving theme order
  $: themesWithPersons = (() => {
    if (!subtopics || subtopics.length === 0 || !personsRegistry) {
      // Fallback: show all persons from chapters ungrouped
      return [{
        title: null,
        themeId: null,
        persons: extractPersonsFromChapters(),
        leftPx: 0,
        widthPx: 0
      }];
    }

    // Create theme groups from subtopics
    return subtopics.map(subtopic => {
      const persons = subtopic.person_ids
        .map(personId => {
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
            isAlive: !deathYear,
            portrait: person.portrait?.thumbnail || person.portrait?.image
          };
        })
        .filter(p => p !== null)
        .sort((a, b) => a.birthYear - b.birthYear);

      // Calculate theme title row bounds (leftmost to rightmost person)
      let themeLeftPx = 0;
      let themeWidthPx = 0;
      if (persons.length > 0) {
        const minLeft = Math.min(...persons.map(p => p.leftPx));
        const maxRight = Math.max(...persons.map(p => p.leftPx + p.widthPx));
        themeLeftPx = minLeft;
        themeWidthPx = maxRight - minLeft;
      }

      return {
        title: subtopic.title,
        themeId: subtopic.id,
        persons: persons,
        leftPx: themeLeftPx,
        widthPx: themeWidthPx
      };
    }).filter(theme => theme.persons.length > 0);
  })();

  // Calculate vertical offset for theme title
  function calculateThemeTop(themeIndex) {
    let offset = 0;
    for (let i = 0; i < themeIndex; i++) {
      offset += THEME_TITLE_HEIGHT;
      offset += themesWithPersons[i].persons.length * PERSON_ROW_HEIGHT;
      offset += THEME_SPACING;
    }
    return offset;
  }

  // Calculate vertical offset for person within theme
  function calculatePersonTop(themeIndex, personIndex) {
    let offset = calculateThemeTop(themeIndex);
    offset += THEME_TITLE_HEIGHT;
    offset += personIndex * PERSON_ROW_HEIGHT;
    return offset;
  }

  // Handle person click - navigate to their story
  function handlePersonClick(personId) {
    window.location.hash = `/story/${personId}`;
  }
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

    <!-- Person lifespans grouped by theme -->
    <div class="persons-layer">
      {#each themesWithPersons as theme, themeIndex}
        <!-- Theme title row (only if title exists) -->
        {#if theme.title}
          <div class="theme-title-row" style="left: {theme.leftPx}px; width: {theme.widthPx}px; top: {calculateThemeTop(themeIndex)}px;">
            <h4 class="theme-title">{theme.title}</h4>
          </div>
        {/if}

        <!-- Persons in this theme -->
        {#each theme.persons as personData, personIndex}
          <div
            class="person-lifespan"
            class:alive={personData.isAlive}
            style="left: {personData.leftPx}px; width: {personData.widthPx}px; top: {calculatePersonTop(themeIndex, personIndex)}px;"
            title="{personData.person.name.replace(/_/g, ' ')} ({personData.birthYear}–{personData.deathYear || 'present'})"
            on:click={() => handlePersonClick(personData.personId)}
            on:keydown={(e) => e.key === 'Enter' && handlePersonClick(personData.personId)}
            role="button"
            tabindex="0"
          >
            <div class="person-name-wrapper">
              <div class="person-name-label">
                {personData.person.name.replace(/_/g, ' ')}
              </div>
            </div>
            {#if personData.portrait}
              <div class="person-portrait">
                <img
                  src={personData.portrait}
                  alt={personData.person.name.replace(/_/g, ' ')}
                  class="portrait-image"
                />
              </div>
            {/if}
            <div class="person-line"></div>
            <div class="person-dates">
              <span class="person-birth">{personData.birthYear}</span>
              <span class="person-death">{personData.deathYear || '...'}</span>
            </div>
          </div>
        {/each}
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
    margin-left: 40px;
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
    min-height: auto;
    z-index: 10;
  }

  /* Theme title row */
  .theme-title-row {
    position: absolute;
    height: 40px;
    display: flex;
    align-items: center;
    background: rgba(15, 23, 42, 0.6);
    border-bottom: 1px solid rgba(56, 189, 248, 0.2);
    z-index: 5;
  }

  .theme-title {
    position: sticky;
    left: 0;
    font-family: var(--heading-font, 'Space Grotesk', sans-serif);
    font-size: 1.1rem;
    font-weight: 600;
    color: #38bdf8;
    margin: 0;
    padding: 0;
    white-space: nowrap;
    background: rgba(4, 10, 24, 0.95);
    line-height: 1;
  }

  /* Individual person lifespan */
  .person-lifespan {
    position: absolute;
    height: 28px;
    transition: all 0.2s;
    cursor: pointer;
    outline: none;
  }

  .person-lifespan:hover {
    z-index: 100;
    transform: translateY(-2px);
  }

  .person-lifespan:focus-visible {
    outline: 2px solid rgba(56, 189, 248, 1);
    outline-offset: 2px;
  }

  /* Person name wrapper - positioned above the line */
  .person-name-wrapper {
    position: absolute;
    left: 34px;
    right: 0;
    top: -10px;
    height: 14px;
    overflow: visible;
    pointer-events: none;
  }

  /* Person name label - sticky horizontal positioning */
  .person-name-label {
    position: sticky;
    left: 0;
    font-weight: 600;
    font-size: 1rem;
    color: #e2e8f0;
    white-space: nowrap;
    padding: 0;
    background: transparent;
    width: fit-content;
    pointer-events: none;
    line-height: 1;
  }

  /* Portrait thumbnail container */
  .person-portrait {
    position: absolute;
    left: -24px;
    top: 50%;
    transform: translateY(-50%);
    width: 56px;
    height: 56px;
    border-radius: 50%;
    border: 3px solid rgba(56, 189, 248, 0.8);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.4);
    background: rgba(15, 23, 42, 0.9);
    transition: all 0.2s;
    z-index: 10;
    overflow: hidden;
  }

  /* Portrait image inside container */
  .portrait-image {
    width: 100%;
    height: 100%;
    object-fit: cover;
    object-position: center 35%;
    scale: 1.25;
  }

  .person-lifespan:hover .person-portrait {
    border-color: rgba(56, 189, 248, 1);
    box-shadow: 0 4px 12px rgba(56, 189, 248, 0.6);
    transform: translateY(-50%) scale(1.1);
  }

  .person-lifespan.alive .person-portrait {
    border-color: rgba(34, 197, 94, 0.8);
  }

  .person-lifespan.alive:hover .person-portrait {
    border-color: rgba(34, 197, 94, 1);
  }

  /* Person lifespan line */
  .person-line {
    position: absolute;
    left: 32px;
    right: 0;
    top: 50%;
    transform: translateY(-50%);
    height: 4px;
    background: linear-gradient(90deg, rgba(56, 189, 248, 0.6), rgba(154, 123, 255, 0.6));
    border-radius: 2px;
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.3);
    cursor: pointer;
    transition: all 0.2s;
  }

  .person-lifespan:hover .person-line {
    height: 6px;
    background: linear-gradient(90deg, rgba(56, 189, 248, 0.8), rgba(154, 123, 255, 0.8));
    box-shadow: 0 2px 8px rgba(56, 189, 248, 0.4);
  }

  .person-lifespan.alive .person-line {
    background: linear-gradient(90deg, rgba(34, 197, 94, 0.6), rgba(56, 189, 248, 0.6));
  }

  .person-lifespan.alive:hover .person-line {
    background: linear-gradient(90deg, rgba(34, 197, 94, 0.8), rgba(56, 189, 248, 0.8));
    box-shadow: 0 2px 8px rgba(34, 197, 94, 0.4);
  }

  /* Person dates container */
  .person-dates {
    position: absolute;
    left: 32px;
    right: 0;
    top: calc(50% + 3px);
    display: flex;
    justify-content: space-between;
    pointer-events: none;
  }

  .person-birth,
  .person-death {
    font-size: 0.7rem;
    color: #94a3b8;
    font-weight: 500;
    white-space: nowrap;
    background: rgba(4, 10, 24, 0.8);
    padding: 1px 4px;
    border-radius: 2px;
    line-height: 1;
  }

  /* Responsive - keep horizontal scrolling on mobile */
  @media (max-width: 768px) {
    .meta-timeline-container {
      padding: 0.5rem;
    }

    /* Make chapters slightly narrower on mobile for easier scanning */
    .chapter-header h3 {
      font-size: 0.875rem;
    }

    .bridge {
      font-size: 0.75rem;
    }

    /* Adjust person elements for mobile */
    .person-lifespan {
      height: 24px;
    }

    .person-portrait {
      width: 48px;
      height: 48px;
      left: -20px;
      border-width: 2px;
    }

    .person-line {
      left: 28px;
      height: 3px;
    }

    .person-lifespan:hover .person-line {
      height: 5px;
    }

    .person-dates {
      left: 28px;
    }

    .portrait-image {
      scale: 1.25;
      object-position: center 35%;
    }

    .person-name-wrapper {
      left: 30px;
      top: -8px;
      height: 12px;
    }

    .person-name-label {
      font-size: 0.875rem;
    }

    .person-dates {
      top: calc(50% + 2px);
    }

    .person-birth,
    .person-death {
      font-size: 0.65rem;
    }

    .theme-title-row {
      height: 32px;
    }

    .theme-title {
      font-size: 0.95rem;
    }
  }
</style>
