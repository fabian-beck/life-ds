<script>
  import { onMount } from 'svelte';

  export let chapters = [];
  export let personsRegistry = [];
  export let onEventClick = () => {};
  export let subtopics = [];
  export let scrollProgress = 0; // 0 to 1, representing horizontal scroll position

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
  const THEME_TITLE_HEIGHT = 45; // Compact theme title row with adequate spacing
  const PERSON_ROW_HEIGHT = 42; // Compact person rows with enough space for names
  const THEME_SPACING = 12; // Spacing between theme groups

  // Calculate timeline width in pixels
  $: timelineWidthPx = totalSpan * PIXELS_PER_YEAR;

  // Calculate scroll indicator position based on scroll progress
  $: scrollIndicatorLeftPx = scrollProgress * timelineWidthPx;

  // Calculate current year at scroll indicator position
  $: currentIndicatorYear = (() => {
    if (!timelineBounds) return null;
    const yearsFromStart = (scrollIndicatorLeftPx / PIXELS_PER_YEAR);
    const year = Math.round(timelineBounds.minYear + yearsFromStart);
    return Math.max(timelineBounds.minYear, Math.min(year, timelineBounds.maxYear));
  })();

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

  // Calculate total timeline height needed
  $: timelineHeightPx = (() => {
    if (!themesWithPersons || themesWithPersons.length === 0) return 300;

    // Fixed heights for top sections
    const chaptersRowHeight = 60; // .chapters-row height
    const yearAxisHeight = 40; // .year-axis height
    const yearAxisMarginTop = 5;
    const personsLayerMarginTop = 10;

    // Calculate persons layer height
    let personsLayerHeight = 0;
    themesWithPersons.forEach((theme, index) => {
      personsLayerHeight += THEME_TITLE_HEIGHT;
      personsLayerHeight += theme.persons.length * PERSON_ROW_HEIGHT;
      if (index < themesWithPersons.length - 1) {
        personsLayerHeight += THEME_SPACING;
      }
    });

    // Add some bottom padding
    const bottomPadding = 20;

    return chaptersRowHeight + yearAxisMarginTop + yearAxisHeight + personsLayerMarginTop + personsLayerHeight + bottomPadding;
  })();

  // Extract events for each person from chapters
  $: personEventsData = (() => {
    console.log('[MetaStoryTimeline] Processing person events data');
    console.log('  chapters:', chapters?.length || 0);
    console.log('  themesWithPersons:', themesWithPersons?.length || 0);

    if (!chapters || chapters.length === 0 || !themesWithPersons) {
      console.log('  -> No chapters or themes, returning empty Map');
      return new Map();
    }

    const eventsByPerson = new Map();

    chapters.forEach((chapter, chapterIndex) => {
      console.log(`  Chapter ${chapterIndex}: "${chapter.title}"`);
      console.log('    person_events:', chapter.person_events?.length || 0);

      if (!chapter.person_events) {
        console.log('    -> No person_events in this chapter');
        return;
      }

      chapter.person_events.forEach((event, eventIndex) => {
        console.log(`    Event ${eventIndex}:`, {
          person_id: event.person_id,
          event_date: event.event_date,
          event_title: event.event_title,
          event_index: event.event_index
        });

        if (!eventsByPerson.has(event.person_id)) {
          eventsByPerson.set(event.person_id, []);
        }

        const eventYear = getYear(event.event_date);
        console.log(`      eventYear: ${eventYear}`);

        if (!eventYear) {
          console.log('      -> No valid year, skipping');
          return;
        }

        const offsetYears = eventYear - timelineBounds.minYear;
        const leftPx = offsetYears * PIXELS_PER_YEAR;

        console.log(`      offsetYears: ${offsetYears}, leftPx: ${leftPx}`);

        eventsByPerson.get(event.person_id).push({
          ...event,
          title: event.event_title,
          date: event.event_date,
          year: eventYear,
          leftPx: leftPx,
          chapterTitle: chapter.title
        });
      });
    });

    console.log('  Final eventsByPerson Map:', eventsByPerson);
    console.log('  Total persons with events:', eventsByPerson.size);
    eventsByPerson.forEach((events, personId) => {
      console.log(`    ${personId}: ${events.length} events`);
    });

    return eventsByPerson;
  })();

  // Tooltip state management
  let activeEventTooltip = null; // { personId, eventIndex, event, x, y }
  let tooltipElement = null; // DOM reference for positioning

  function showEventTooltip(personId, eventIndex, event, clickEvent) {
    const rect = clickEvent.target.getBoundingClientRect();
    activeEventTooltip = {
      personId,
      eventIndex,
      event,
      x: rect.left + rect.width / 2,
      y: rect.top
    };
  }

  function hideEventTooltip() {
    activeEventTooltip = null;
  }

  function handleEventClick(personId, event) {
    // Navigate to the specific event in the person's story
    // Use event_index from the meta story data which references the actual event index in life_events.json
    const targetIndex = event.event_index !== undefined ? event.event_index : 0;
    console.log(`[Navigate] Going to /story/${personId}/${targetIndex}`);
    window.location.hash = `/story/${personId}/${targetIndex}`;
  }

  // Handle person click - navigate to their story
  function handlePersonClick(personId) {
    window.location.hash = `/story/${personId}`;
  }

  // Click-outside handler to close tooltip
  onMount(() => {
    function handleClickOutside(event) {
      if (activeEventTooltip && tooltipElement && !tooltipElement.contains(event.target)) {
        hideEventTooltip();
      }
    }

    document.addEventListener('click', handleClickOutside);

    return () => {
      document.removeEventListener('click', handleClickOutside);
    };
  });
</script>

<div class="meta-timeline-container">
  <div class="timeline-wrapper" style="width: {timelineWidthPx}px; height: {timelineHeightPx}px;">
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

            <!-- Event markers -->
            {#if personEventsData.has(personData.personId)}
              {@const events = personEventsData.get(personData.personId)}
              {@const _ = console.log(`[Render] Person ${personData.personId} has ${events.length} events`)}
              {#each events as event, eventIndex}
                {@const relativeLeftPx = event.leftPx - personData.leftPx}
                {@const __ = console.log(`  Rendering event marker ${eventIndex}: ${event.title}`, {
                  eventYear: event.year,
                  personBirth: personData.birthYear,
                  absoluteLeftPx: event.leftPx,
                  personLeftPx: personData.leftPx,
                  relativeLeftPx: relativeLeftPx
                })}
                <div
                  class="event-marker"
                  style="left: {relativeLeftPx}px;"
                  on:click={(e) => {
                    e.stopPropagation();
                    showEventTooltip(personData.personId, eventIndex, event, e);
                  }}
                  on:keydown={(e) => {
                    if (e.key === 'Enter') {
                      e.stopPropagation();
                      showEventTooltip(personData.personId, eventIndex, event, e);
                    }
                  }}
                  role="button"
                  tabindex="0"
                  aria-label="{event.title} ({event.year})"
                >
                  <div class="event-dot"></div>
                </div>
              {/each}
            {:else}
              {@const ___ = console.log(`[Render] Person ${personData.personId} has NO events in personEventsData`)}
            {/if}
          </div>
        {/each}
      {/each}
    </div>

    <!-- Scroll position indicator -->
    <div class="scroll-indicator" style="left: {scrollIndicatorLeftPx}px; top: 60px; height: {timelineHeightPx - 60}px;">
      {#if currentIndicatorYear}
        <div class="scroll-indicator-label">{currentIndicatorYear}</div>
      {/if}
    </div>

    <!-- Event tooltip -->
    {#if activeEventTooltip}
      <div
        class="event-tooltip"
        bind:this={tooltipElement}
        style="left: {activeEventTooltip.x}px; top: {activeEventTooltip.y}px;"
        on:click={(e) => e.stopPropagation()}
        on:keydown={(e) => e.key === 'Escape' && hideEventTooltip()}
        role="dialog"
        aria-label="Event details"
      >
        <div class="tooltip-header">
          <h4 class="tooltip-title">{activeEventTooltip.event.title}</h4>
          <span class="tooltip-year">{activeEventTooltip.event.year}</span>
        </div>

        <button
          class="tooltip-action"
          on:click={() => handleEventClick(
            activeEventTooltip.personId,
            activeEventTooltip.event
          )}
        >
          Jump to Event →
        </button>
      </div>
    {/if}
  </div>
</div>

<style>
  /* Container - full width scrollable panel */
  .meta-timeline-container {
    width: 100%;
    overflow-x: auto;
    overflow-y: visible;
    padding: 1rem;
    background: rgba(4, 10, 24, 0.95);
  }

  /* Hide scrollbar but keep scrollable */
  .meta-timeline-container::-webkit-scrollbar {
    display: none;
  }

  .meta-timeline-container {
    scrollbar-width: none;
  }

  /* Wrapper - dynamically sized based on content */
  .timeline-wrapper {
    position: relative;
    margin-left: 40px;
  }

  /* Chapters row - absolute positioning */
  .chapters-row {
    position: relative;
    height: 60px;
    z-index: 1;
  }

  /* Individual chapter - absolutely positioned */
  .chapter {
    position: absolute;
    top: 0;
    height: 100%;
    border-right: 1px solid rgba(56, 189, 248, 0.3);
    padding: 0.5rem;
    background: rgba(15, 23, 42, 0.2);
  }

  .chapter:nth-child(even) {
    background: rgba(15, 23, 42, 0.3);
  }

  /* Chapter header */
  .chapter-header {
    margin-bottom: 0;
  }

  .chapter-header h3 {
    font-family: var(--heading-font, 'Space Grotesk', sans-serif);
    font-size: 0.9rem;
    margin: 0;
    color: #38bdf8;
    line-height: 1.2;
  }

  /* Year axis */
  .year-axis {
    position: relative;
    height: 40px;
    margin-top: 5px;
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
    margin-top: 10px;
    min-height: auto;
    z-index: 10;
  }

  /* Theme title row */
  .theme-title-row {
    position: absolute;
    height: 30px;
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
    font-size: 1rem;
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
    height: 30px;
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
    left: 26px;
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
    font-size: 0.9rem;
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
    left: -22px;
    top: 50%;
    transform: translateY(-50%);
    width: 44px;
    height: 44px;
    border-radius: 50%;
    border: 2px solid rgba(56, 189, 248, 0.8);
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
    left: 24px;
    right: 0;
    top: 50%;
    transform: translateY(-50%);
    height: 3px;
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
    left: 24px;
    right: 0;
    top: calc(50% + 2px);
    display: flex;
    justify-content: space-between;
    pointer-events: none;
  }

  .person-birth,
  .person-death {
    font-size: 0.65rem;
    color: #94a3b8;
    font-weight: 500;
    white-space: nowrap;
    background: rgba(4, 10, 24, 0.8);
    padding: 1px 3px;
    border-radius: 2px;
    line-height: 1;
  }

  /* Scroll position indicator */
  .scroll-indicator {
    position: absolute;
    width: 2px;
    background: none;
    border-left: 2px dashed rgba(56, 189, 248, 0.4);
    pointer-events: none;
    z-index: 0;
    transition: left 0.1s ease-out;
    display: flex;
    flex-direction: column;
    justify-content: flex-end;
  }

  /* Scroll indicator year label */
  .scroll-indicator-label {
    position: sticky;
    bottom: 0;
    transform: translateX(-50%);
    background: rgba(4, 10, 24, 0.95);
    color: #38bdf8;
    font-size: 0.875rem;
    font-weight: 600;
    padding: 4px 8px;
    border-radius: 4px;
    border: 1px solid rgba(56, 189, 248, 0.3);
    white-space: nowrap;
    width: fit-content;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
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

  /* Event markers */
  .event-marker {
    position: absolute;
    top: 50%;
    transform: translate(-50%, -50%);
    width: 24px;
    height: 24px;
    cursor: pointer;
    z-index: 20;
    transition: all 0.2s;
  }

  .event-marker:hover {
    z-index: 30;
    transform: translate(-50%, -50%) scale(1.15);
  }

  .event-marker:focus-visible {
    outline: 2px solid rgba(56, 189, 248, 1);
    outline-offset: 2px;
    border-radius: 50%;
  }

  .event-dot {
    width: 14px;
    height: 14px;
    background: rgba(56, 189, 248, 0.9);
    border: 2px solid rgba(255, 255, 255, 0.8);
    border-radius: 50%;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.4);
    transition: all 0.2s;
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
  }

  .event-marker:hover .event-dot {
    background: rgba(56, 189, 248, 1);
    border-color: rgba(255, 255, 255, 1);
    box-shadow: 0 4px 12px rgba(56, 189, 248, 0.6);
  }

  /* Event tooltip - matches PersonChip styling */
  .event-tooltip {
    position: fixed;
    min-width: 240px;
    max-width: min(320px, 90vw);
    background: rgba(15, 23, 42, 0.95);
    backdrop-filter: blur(8px);
    border: 1px solid rgba(148, 163, 184, 0.3);
    border-radius: 0.5rem;
    padding: 0.75rem;
    box-shadow: 0 8px 20px rgba(0, 0, 0, 0.4);
    z-index: 10000;
    transform: translate(-50%, calc(-100% - 12px));
    animation: fadeInTooltip 0.2s ease;
    font-family: var(--body-font, 'IBM Plex Sans', sans-serif);
  }

  @keyframes fadeInTooltip {
    from {
      opacity: 0;
      transform: translate(-50%, calc(-100% - 8px));
    }
    to {
      opacity: 1;
      transform: translate(-50%, calc(-100% - 12px));
    }
  }

  .tooltip-header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 0.5rem;
    margin-bottom: 0.5rem;
  }

  .tooltip-title {
    font-family: var(--heading-font, 'Space Grotesk', sans-serif);
    font-size: 0.85rem;
    font-weight: 600;
    color: #38bdf8;
    margin: 0;
    line-height: 1.2;
    flex: 1;
  }

  .tooltip-year {
    font-size: 0.7rem;
    color: #94a3b8;
    font-weight: 500;
    white-space: nowrap;
  }

  .tooltip-description {
    font-size: 0.75rem;
    line-height: 1.4;
    color: #cbd5e1;
    margin: 0 0 0.5rem 0;
    max-height: 4.2rem;
    overflow: hidden;
    text-overflow: ellipsis;
    display: -webkit-box;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
  }

  .tooltip-meta {
    display: flex;
    gap: 0.25rem;
    font-size: 0.7rem;
    color: #94a3b8;
    margin-bottom: 0.5rem;
    padding-top: 0.5rem;
    border-top: 1px solid rgba(148, 163, 184, 0.2);
  }

  .meta-label {
    font-weight: 500;
  }

  .meta-value {
    color: #cbd5e1;
  }

  .tooltip-action {
    width: 100%;
    background: rgba(56, 189, 248, 0.15);
    border: 1px solid rgba(56, 189, 248, 0.3);
    border-radius: 0.375rem;
    padding: 0.5rem 0.75rem;
    color: #38bdf8;
    font-size: 0.75rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s;
    font-family: var(--heading-font, 'Space Grotesk', sans-serif);
  }

  .tooltip-action:hover {
    background: rgba(56, 189, 248, 0.25);
    border-color: rgba(56, 189, 248, 0.5);
    transform: translateY(-1px);
    box-shadow: 0 2px 8px rgba(56, 189, 248, 0.3);
  }

  .tooltip-action:active {
    transform: translateY(0);
  }
</style>
