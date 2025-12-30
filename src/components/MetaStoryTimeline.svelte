<script>
  import { onMount } from 'svelte';
  import { _ } from '../stores/language.js';
  import personStylesData from '../../data/person_styles.json';

  export let chapters = [];
  export let personsRegistry = [];
  export let onEventClick = () => {};
  export let subtopics = [];
  export let scrollProgress = 0; // 0 to 1, representing horizontal scroll position

  // Person styles registry
  const personStyles = personStylesData.styles;

  // Helper to get person data by ID
  function getPersonById(personId) {
    return personsRegistry.find(p => p.id === personId);
  }

  // Helper to get person style colors
  function getPersonColors(personId) {
    const style = personStyles[personId];
    if (!style) {
      return {
        primary: '#38bdf8', // Default cyan
        secondary: '#9a7bff', // Default purple
        primaryRgb: '56, 189, 248',
        secondaryRgb: '154, 123, 255'
      };
    }

    // Convert hex to RGB
    const hexToRgb = (hex) => {
      const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
      return result
        ? `${parseInt(result[1], 16)}, ${parseInt(result[2], 16)}, ${parseInt(result[3], 16)}`
        : '255, 255, 255';
    };

    return {
      primary: style.primary,
      secondary: style.secondary,
      primaryRgb: hexToRgb(style.primary),
      secondaryRgb: hexToRgb(style.secondary)
    };
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

  // Detect when scroll indicator hovers over event markers
  $: {
    const HOVER_THRESHOLD = 8; // pixels of tolerance for intersection
    const eventsByPosition = new Map(); // leftPx -> [event objects]

    if (themesWithPersons && personEventsData && scrollIndicatorLeftPx > 0) {
      themesWithPersons.forEach((theme, themeIndex) => {
        theme.persons.forEach((personData, personIndex) => {
          const events = personEventsData.get(personData.personId);
          if (!events) return;

          events.forEach((event, eventIndex) => {
            // Check if scroll indicator is near this event's position
            if (Math.abs(event.leftPx - scrollIndicatorLeftPx) <= HOVER_THRESHOLD) {
              // Group by position
              if (!eventsByPosition.has(event.leftPx)) {
                eventsByPosition.set(event.leftPx, []);
              }

              eventsByPosition.get(event.leftPx).push({
                personId: personData.personId,
                eventIndex,
                event,
                personName: personData.person.name.replace(/_/g, ' '),
                colors: getPersonColors(personData.personId),
                themeIndex,
                personIndex,
                personTopPx: calculatePersonTop(themeIndex, personIndex)
              });
            }
          });
        });
      });
    }

    // Find the primary hovered cluster (closest to indicator)
    let closestCluster = null;
    let closestDistance = Infinity;

    eventsByPosition.forEach((events, leftPx) => {
      const distance = Math.abs(leftPx - scrollIndicatorLeftPx);
      if (distance < closestDistance) {
        closestDistance = distance;
        closestCluster = { leftPx, events };
      }
    });

    // Update hovered events set (for visual feedback on markers)
    const newHoveredEvents = new Set();
    if (closestCluster) {
      closestCluster.events.forEach(evt => {
        newHoveredEvents.add(`${evt.personId}-${evt.eventIndex}`);
      });
    }
    hoveredEventsByIndicator = newHoveredEvents;

    // Show grouped tooltip after delay
    if (closestCluster && (!activeEventTooltip || !activeEventTooltip.clickTriggered)) {
      if (indicatorHoverTimeout) clearTimeout(indicatorHoverTimeout);

      indicatorHoverTimeout = setTimeout(() => {
        if (!activeEventTooltip || !activeEventTooltip.clickTriggered) {
          showGroupedEventTooltip(closestCluster);
        }
      }, 600);
    } else if (!closestCluster) {
      if (indicatorHoverTimeout) {
        clearTimeout(indicatorHoverTimeout);
        indicatorHoverTimeout = null;
      }
      if (activeEventTooltip && !activeEventTooltip.clickTriggered) {
        hideEventTooltip();
      }
    }
  }

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
    if (!chapters || chapters.length === 0 || !themesWithPersons) {
      return new Map();
    }

    const eventsByPerson = new Map();

    chapters.forEach((chapter) => {
      if (!chapter.person_events) {
        return;
      }

      chapter.person_events.forEach((event) => {
        // Only include essential events (top priority)
        if (event.relevance_strength !== 'essential') {
          return;
        }

        if (!eventsByPerson.has(event.person_id)) {
          eventsByPerson.set(event.person_id, []);
        }

        const eventYear = getYear(event.event_date);

        if (!eventYear) {
          return;
        }

        const offsetYears = eventYear - timelineBounds.minYear;
        const leftPx = offsetYears * PIXELS_PER_YEAR;

        eventsByPerson.get(event.person_id).push({
          ...event,
          title: event.event_title,
          date: event.event_date,
          year: eventYear,
          leftPx: leftPx,
          chapterTitle: chapter.title,
          theme_connection: event.theme_connection,
          relevance_strength: event.relevance_strength
        });
      });
    });

    return eventsByPerson;
  })();

  // Extract unique years with events for navigation, including timeline start and end
  $: yearsWithEvents = (() => {
    if (!timelineBounds) return [];

    const yearSet = new Set();

    // Always include timeline start and end as navigable targets
    yearSet.add(timelineBounds.minYear);
    yearSet.add(timelineBounds.maxYear);

    // Add all years with events
    if (personEventsData && personEventsData.size > 0) {
      personEventsData.forEach((events) => {
        events.forEach((event) => {
          if (event.year) {
            yearSet.add(event.year);
          }
        });
      });
    }

    return Array.from(yearSet).sort((a, b) => a - b);
  })();

  // Export navigation functions for parent component
  export function getNextYear() {
    if (yearsWithEvents.length === 0 || currentIndicatorYear === null || currentIndicatorYear === undefined || !timelineBounds) return null;
    return yearsWithEvents.find(y => y > currentIndicatorYear) || null;
  }

  export function getPrevYear() {
    if (yearsWithEvents.length === 0 || currentIndicatorYear === null || currentIndicatorYear === undefined || !timelineBounds) return null;
    return [...yearsWithEvents].reverse().find(y => y < currentIndicatorYear) || null;
  }

  export function yearToScrollProgress(targetYear) {
    if (!timelineBounds || !targetYear || timelineWidthPx === 0) return null;

    // Calculate pixel position of target year on timeline
    const offsetYears = targetYear - timelineBounds.minYear;
    const targetLeftPx = offsetYears * PIXELS_PER_YEAR;

    // The scroll indicator is positioned at: scrollProgress * timelineWidthPx
    // We want: scrollIndicatorLeftPx === targetLeftPx
    // Therefore: scrollProgress * timelineWidthPx === targetLeftPx
    // Solving: scrollProgress = targetLeftPx / timelineWidthPx

    const scrollProgress = targetLeftPx / timelineWidthPx;

    // Clamp to valid range [0, 1]
    return Math.max(0, Math.min(scrollProgress, 1));
  }

  // Tooltip state management
  let activeEventTooltip = null; // { personId, eventIndex, event, x, y, placement }
  let tooltipElement = null; // DOM reference for positioning
  let hoveredEventsByIndicator = new Set(); // Track which events are hovered by scroll indicator
  let indicatorHoverTimeout = null; // Delay before showing tooltip on indicator hover

  function showEventTooltip(personId, eventIndex, event, clickEvent) {
    const rect = clickEvent.target.getBoundingClientRect();
    const viewportWidth = window.innerWidth;
    const tooltipWidth = 320; // max-width from CSS
    const tooltipHeight = 200; // estimated height

    // Calculate optimal position
    let x = rect.left + rect.width / 2;
    let y = rect.top;
    let placement = 'top'; // default: above the marker

    // Check if tooltip would go off the top
    if (rect.top < tooltipHeight + 20) {
      placement = 'bottom';
      y = rect.bottom;
    }

    // Check horizontal bounds and adjust
    let adjustedX = x;
    if (x - tooltipWidth / 2 < 10) {
      // Too close to left edge
      adjustedX = tooltipWidth / 2 + 10;
    } else if (x + tooltipWidth / 2 > viewportWidth - 10) {
      // Too close to right edge
      adjustedX = viewportWidth - tooltipWidth / 2 - 10;
    }

    // Clear any pending indicator hover timeout
    if (indicatorHoverTimeout) {
      clearTimeout(indicatorHoverTimeout);
      indicatorHoverTimeout = null;
    }

    // Find person data for colors
    const person = getPersonById(personId);
    const colors = getPersonColors(personId);

    activeEventTooltip = {
      events: [{
        personId,
        eventIndex,
        event,
        personName: person.name.replace(/_/g, ' '),
        colors
      }],
      year: event.year,
      x: adjustedX,
      y: y,
      placement: placement,
      clickTriggered: true // Mark as click-triggered
    };
  }

  function hideEventTooltip() {
    activeEventTooltip = null;
  }

  // Show grouped tooltip for event cluster (used by scroll indicator)
  function showGroupedEventTooltip(cluster) {
    const timelineContainer = document.querySelector('.meta-timeline-container');
    if (!timelineContainer) return;

    const containerRect = timelineContainer.getBoundingClientRect();
    const scrollLeft = timelineContainer.scrollLeft;

    // Calculate screen position for the cluster
    const eventLeftPx = cluster.leftPx;
    const screenX = containerRect.left + eventLeftPx - scrollLeft + 40;

    // Use the topmost event's vertical position
    const topEvent = cluster.events.reduce((top, evt) =>
      evt.personTopPx < top.personTopPx ? evt : top
    );
    const screenY = containerRect.top + 60 + 40 + 10 + topEvent.personTopPx + 15;

    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    const tooltipWidth = 520; // Much wider for grouped content

    // Estimate height based on event count (header + items)
    const baseHeight = 60; // Header
    const itemHeight = 110; // Per event (name + title + description + button)
    const estimatedHeight = Math.min(baseHeight + (cluster.events.length * itemHeight), 450);

    let placement = 'top';
    let y = screenY;

    // Prefer top with extra clearance for grouped tooltip
    const topClearance = 40; // Extra space above markers
    if (screenY - estimatedHeight - topClearance < 0) {
      placement = 'bottom';
      y = screenY + 30; // More clearance below markers
    } else {
      y = screenY - 20;
    }

    // Check bottom overflow when forced to bottom placement
    if (placement === 'bottom' && y + estimatedHeight + 20 > viewportHeight) {
      placement = 'top';
      y = screenY - 20;
    }

    // Horizontal centering with bounds checking
    let adjustedX = screenX;
    if (screenX - tooltipWidth / 2 < 10) {
      adjustedX = tooltipWidth / 2 + 10;
    } else if (screenX + tooltipWidth / 2 > viewportWidth - 10) {
      adjustedX = viewportWidth - tooltipWidth / 2 - 10;
    }

    activeEventTooltip = {
      events: cluster.events,
      year: cluster.events[0].event.year,
      x: adjustedX,
      y: y,
      placement: placement,
      clickTriggered: false
    };
  }

  function handleEventClick(personId, event) {
    // Navigate to the specific event in the person's story
    // Use event_index from the meta story data which references the actual event index in life_events.json
    const targetIndex = event.event_index !== undefined ? event.event_index : 0;
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

    // Close tooltip on scroll
    function handleScroll() {
      if (activeEventTooltip) {
        hideEventTooltip();
      }
    }

    const timelineContainer = document.querySelector('.meta-timeline-container');

    document.addEventListener('click', handleClickOutside);
    if (timelineContainer) {
      timelineContainer.addEventListener('scroll', handleScroll);
    }

    return () => {
      document.removeEventListener('click', handleClickOutside);
      if (timelineContainer) {
        timelineContainer.removeEventListener('scroll', handleScroll);
      }
      // Clear pending timeout on unmount
      if (indicatorHoverTimeout) {
        clearTimeout(indicatorHoverTimeout);
      }
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
          {@const colors = getPersonColors(personData.personId)}
          <div
            class="person-lifespan"
            class:alive={personData.isAlive}
            style="
              left: {personData.leftPx}px;
              width: {personData.widthPx}px;
              top: {calculatePersonTop(themeIndex, personIndex)}px;
              --person-primary: {colors.primary};
              --person-secondary: {colors.secondary};
              --person-primary-rgb: {colors.primaryRgb};
              --person-secondary-rgb: {colors.secondaryRgb};
            "
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
              {#each events as event, eventIndex}
                {@const relativeLeftPx = event.leftPx - personData.leftPx}
                {@const eventKey = `${personData.personId}-${eventIndex}`}
                {@const isHoveredByIndicator = hoveredEventsByIndicator.has(eventKey)}
                {@const isActive = activeEventTooltip && activeEventTooltip.personId === personData.personId && activeEventTooltip.eventIndex === eventIndex}
                <div
                  class="event-marker"
                  class:essential={event.relevance_strength === 'essential'}
                  class:supporting={event.relevance_strength === 'supporting'}
                  class:indicator-hover={isHoveredByIndicator}
                  class:active={isActive}
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

    <!-- Event tooltip (single or grouped) -->
    {#if activeEventTooltip}
      <div
        class="event-tooltip"
        class:placement-top={activeEventTooltip.placement === 'top'}
        class:placement-bottom={activeEventTooltip.placement === 'bottom'}
        class:grouped={activeEventTooltip.events.length > 1}
        bind:this={tooltipElement}
        style="
          left: {activeEventTooltip.x}px;
          top: {activeEventTooltip.y}px;
        "
        on:click={(e) => e.stopPropagation()}
        on:keydown={(e) => e.key === 'Escape' && hideEventTooltip()}
        role="dialog"
        aria-label="Event details"
      >
        <!-- Event list (always scrollable) -->
        <div class="tooltip-events">
          {#each activeEventTooltip.events as evt}
            <div
              class="event-item"
              style="
                --item-primary: {evt.colors.primary};
                --item-primary-rgb: {evt.colors.primaryRgb};
              "
            >
              <div class="event-item-header">
                <div class="event-item-header-content">
                  <div class="event-person-name">{evt.personName}</div>
                  <div class="event-item-title">{evt.event.title}</div>
                </div>
                <button
                  class="tooltip-action-compact"
                  on:click={() => handleEventClick(evt.personId, evt.event)}
                  title="Jump to event in person's story"
                >
                  →
                </button>
              </div>

              {#if evt.event.theme_connection}
                <p class="event-item-description">{evt.event.theme_connection}</p>
              {/if}
            </div>
          {/each}
        </div>
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
    background: transparent;
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
    border: 2px solid rgba(var(--person-primary-rgb), 0.8);
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
    border-color: rgba(var(--person-primary-rgb), 1);
    box-shadow: 0 4px 12px rgba(var(--person-primary-rgb), 0.6);
    transform: translateY(-50%) scale(1.1);
  }

  .person-lifespan.alive .person-portrait {
    border-color: rgba(var(--person-secondary-rgb), 0.8);
  }

  .person-lifespan.alive:hover .person-portrait {
    border-color: rgba(var(--person-secondary-rgb), 1);
  }

  /* Person lifespan line */
  .person-line {
    position: absolute;
    left: 24px;
    right: 0;
    top: 50%;
    transform: translateY(-50%);
    height: 3px;
    background: linear-gradient(90deg, rgba(var(--person-primary-rgb), 0.6), rgba(var(--person-secondary-rgb), 0.6));
    border-radius: 2px;
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.3);
    cursor: pointer;
    transition: all 0.2s;
  }

  .person-lifespan:hover .person-line {
    height: 6px;
    background: linear-gradient(90deg, rgba(var(--person-primary-rgb), 0.8), rgba(var(--person-secondary-rgb), 0.8));
    box-shadow: 0 2px 8px rgba(var(--person-primary-rgb), 0.4);
  }

  .person-lifespan.alive .person-line {
    background: linear-gradient(90deg, rgba(var(--person-secondary-rgb), 0.6), rgba(var(--person-primary-rgb), 0.6));
  }

  .person-lifespan.alive:hover .person-line {
    background: linear-gradient(90deg, rgba(var(--person-secondary-rgb), 0.8), rgba(var(--person-primary-rgb), 0.8));
    box-shadow: 0 2px 8px rgba(var(--person-secondary-rgb), 0.4);
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
    background: transparent;
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

  .event-marker:hover,
  .event-marker.indicator-hover {
    z-index: 30;
    transform: translate(-50%, -50%) scale(1.15);
  }

  /* Active state - event with open tooltip */
  .event-marker.active {
    z-index: 40;
    transform: translate(-50%, -50%) scale(1.25);
  }

  .event-marker:focus-visible {
    outline: 2px solid rgba(56, 189, 248, 1);
    outline-offset: 2px;
    border-radius: 50%;
  }

  .event-dot {
    width: 14px;
    height: 14px;
    background: rgba(var(--person-primary-rgb), 0.9);
    border: 2px solid rgba(255, 255, 255, 0.8);
    border-radius: 50%;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.4);
    transition: all 0.2s;
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
  }

  .event-marker:hover .event-dot,
  .event-marker.indicator-hover .event-dot {
    background: rgba(var(--person-primary-rgb), 1);
    border-color: rgba(255, 255, 255, 1);
    box-shadow: 0 4px 12px rgba(var(--person-primary-rgb), 0.6);
  }

  /* Active event marker - distinctive glow and pulsing animation */
  .event-marker.active .event-dot {
    background: rgba(var(--person-primary-rgb), 1);
    border: 3px solid #38bdf8;
    box-shadow:
      0 0 0 2px rgba(56, 189, 248, 0.4),
      0 0 20px rgba(var(--person-primary-rgb), 0.8),
      0 0 40px rgba(56, 189, 248, 0.4);
    animation: pulse-active 2s ease-in-out infinite;
  }

  @keyframes pulse-active {
    0%, 100% {
      box-shadow:
        0 0 0 2px rgba(56, 189, 248, 0.4),
        0 0 20px rgba(var(--person-primary-rgb), 0.8),
        0 0 40px rgba(56, 189, 248, 0.4);
    }
    50% {
      box-shadow:
        0 0 0 4px rgba(56, 189, 248, 0.6),
        0 0 30px rgba(var(--person-primary-rgb), 1),
        0 0 60px rgba(56, 189, 248, 0.6);
    }
  }

  /* Essential events: larger, more prominent */
  .event-marker.essential .event-dot {
    width: 18px;
    height: 18px;
    background: rgba(var(--person-primary-rgb), 1);
    border: 3px solid rgba(255, 255, 255, 0.9);
    box-shadow: 0 3px 8px rgba(var(--person-primary-rgb), 0.5);
  }

  .event-marker.essential:hover .event-dot,
  .event-marker.essential.indicator-hover .event-dot {
    box-shadow: 0 5px 15px rgba(var(--person-primary-rgb), 0.7);
  }

  /* Supporting events: standard size */
  .event-marker.supporting .event-dot {
    width: 14px;
    height: 14px;
    background: rgba(var(--person-primary-rgb), 0.8);
  }

  /* Event tooltip - styled with person's colors */
  .event-tooltip {
    position: fixed;
    min-width: 240px;
    max-width: min(320px, 90vw);
    background: rgb(15, 23, 42);
    border: 2px solid rgba(56, 189, 248, 0.5);
    border-radius: 0.5rem;
    padding: 0.75rem;
    box-shadow: 0 8px 20px rgba(0, 0, 0, 0.6);
    z-index: 10000;
    font-family: var(--body-font, 'IBM Plex Sans', sans-serif);
  }

  /* Placement: above the marker (default) */
  .event-tooltip.placement-top {
    transform: translate(-50%, calc(-100% - 12px));
    animation: fadeInTooltipTop 0.2s ease;
  }

  /* Placement: below the marker */
  .event-tooltip.placement-bottom {
    transform: translate(-50%, 12px);
    animation: fadeInTooltipBottom 0.2s ease;
  }

  @keyframes fadeInTooltipTop {
    from {
      opacity: 0;
      transform: translate(-50%, calc(-100% - 8px));
    }
    to {
      opacity: 1;
      transform: translate(-50%, calc(-100% - 12px));
    }
  }

  @keyframes fadeInTooltipBottom {
    from {
      opacity: 0;
      transform: translate(-50%, 8px);
    }
    to {
      opacity: 1;
      transform: translate(-50%, 12px);
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
    color: var(--tooltip-primary);
    margin: 0;
    line-height: 1.2;
    flex: 1;
  }

  .tooltip-year {
    font-size: 0.7rem;
    color: rgba(var(--tooltip-primary-rgb), 0.7);
    font-weight: 500;
    white-space: nowrap;
    background: rgba(var(--tooltip-primary-rgb), 0.1);
    padding: 2px 6px;
    border-radius: 3px;
  }

  .tooltip-description {
    font-size: 0.8rem;
    line-height: 1.5;
    color: #cbd5e1;
    margin: 0.5rem 0 0.75rem 0;
    border-left: 3px solid rgba(var(--tooltip-secondary-rgb), 0.5);
    padding-left: 0.5rem;
  }

  .tooltip-action {
    width: 100%;
    background: linear-gradient(135deg, rgba(var(--tooltip-primary-rgb), 0.15), rgba(var(--tooltip-secondary-rgb), 0.15));
    border: 1px solid rgba(var(--tooltip-primary-rgb), 0.4);
    border-radius: 0.375rem;
    padding: 0.5rem 0.75rem;
    color: var(--tooltip-primary);
    font-size: 0.75rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s;
    font-family: var(--heading-font, 'Space Grotesk', sans-serif);
  }

  .tooltip-action:hover {
    background: linear-gradient(135deg, rgba(var(--tooltip-primary-rgb), 0.25), rgba(var(--tooltip-secondary-rgb), 0.25));
    border-color: rgba(var(--tooltip-primary-rgb), 0.6);
    transform: translateY(-1px);
    box-shadow: 0 2px 8px rgba(var(--tooltip-primary-rgb), 0.4);
  }

  .tooltip-action:active {
    transform: translateY(0);
  }

  /* Grouped tooltip adjustments */
  .event-tooltip.grouped {
    min-width: 400px;
    max-width: min(560px, 90vw);
    max-height: 450px;
    display: flex;
    flex-direction: column;
    background: rgb(15, 23, 42);
  }

  /* Event list container - always scrollable with proper constraints */
  .tooltip-events {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    max-height: 400px;
    overflow-y: auto;
    overflow-x: hidden;
    padding-right: 0.25rem;
  }

  /* Individual event item */
  .event-item {
    position: relative;
    padding-left: 0.75rem;
    border-left: 3px solid var(--item-primary);
    min-width: 0; /* Allow flex children to shrink below content size */
  }

  .event-item + .event-item {
    padding-top: 0.75rem;
    border-top: 1px solid rgba(148, 163, 184, 0.2);
  }

  .event-item-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 0.75rem;
    margin-bottom: 0.5rem;
    min-width: 0;
  }

  .event-item-header-content {
    flex: 1;
    min-width: 0;
    overflow: hidden;
  }

  .event-person-name {
    font-family: var(--heading-font, 'Space Grotesk', sans-serif);
    font-size: 0.75rem;
    font-weight: 700;
    color: var(--item-primary);
    margin-bottom: 0.25rem;
    text-transform: none;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .event-item-title {
    font-family: var(--heading-font, 'Space Grotesk', sans-serif);
    font-size: 0.85rem;
    font-weight: 600;
    color: #e2e8f0;
    line-height: 1.3;
    word-wrap: break-word;
    overflow-wrap: break-word;
  }

  .event-item-description {
    font-size: 0.75rem;
    line-height: 1.4;
    color: #cbd5e1;
    margin: 0;
    word-wrap: break-word;
    overflow-wrap: break-word;
  }

  /* Compact jump button in top-right */
  .tooltip-action-compact {
    flex-shrink: 0;
    width: 28px;
    height: 28px;
    padding: 0;
    background: rgba(var(--item-primary-rgb), 0.15);
    border: 1px solid rgba(var(--item-primary-rgb), 0.4);
    border-radius: 4px;
    color: var(--item-primary);
    font-size: 1.1rem;
    font-weight: 700;
    line-height: 1;
    cursor: pointer;
    transition: all 0.2s;
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: Arial, sans-serif;
  }

  .tooltip-action-compact:hover {
    background: rgba(var(--item-primary-rgb), 0.3);
    border-color: rgba(var(--item-primary-rgb), 0.7);
    transform: translateX(2px);
  }

  .tooltip-action-compact:active {
    transform: translateX(0);
  }

  /* Scrollbar styling for event list */
  .tooltip-events::-webkit-scrollbar {
    width: 6px;
  }

  .tooltip-events::-webkit-scrollbar-track {
    background: rgba(15, 23, 42, 0.5);
    border-radius: 3px;
  }

  .tooltip-events::-webkit-scrollbar-thumb {
    background: rgba(56, 189, 248, 0.4);
    border-radius: 3px;
  }

  .tooltip-events::-webkit-scrollbar-thumb:hover {
    background: rgba(56, 189, 248, 0.6);
  }
</style>
