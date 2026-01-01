<script>
  import { onMount } from 'svelte';
  import { fade } from 'svelte/transition';
  import { _ } from '../stores/language.js';
  import personStylesData from '../../data/person_styles.json';

  export let chapters = [];
  export let personsRegistry = [];
  export let onEventClick = () => {};
  export let subtopics = [];
  export let scrollProgress = 0; // 0 to 1, representing horizontal scroll position
  export let isSticky = false; // Whether timeline is in sticky/fullscreen mode

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

  // Calculate visible viewport bounds in pixel coordinates
  $: viewportBounds = (() => {
    if (typeof window === 'undefined') {
      return null;
    }

    const container = document.querySelector('.meta-timeline-container');
    if (!container) {
      return null;
    }

    const viewportWidthPx = container.clientWidth;
    const scrollLeftPx = scrollProgress * Math.max(0, timelineWidthPx - viewportWidthPx);

    return {
      left: scrollLeftPx,
      right: scrollLeftPx + viewportWidthPx
    };
  })();

  // Track which persons are visible in viewport (as array for Svelte reactivity)
  $: visiblePersonIds = (() => {
    if (!viewportBounds || !themesWithPersons) {
      return [];
    }

    const visible = [];
    const VISIBILITY_MARGIN = 100; // Extra pixels for smooth transitions

    themesWithPersons.forEach((theme, themeIdx) => {
      theme.persons.forEach((personData, personIdx) => {
        const personLeft = personData.leftPx;
        const personRight = personData.leftPx + personData.widthPx;

        // Check overlap with viewport (with margin)
        const isVisible = (
          personRight > (viewportBounds.left - VISIBILITY_MARGIN) &&
          personLeft < (viewportBounds.right + VISIBILITY_MARGIN)
        );

        if (isVisible) {
          visible.push(personData.personId);
        }
      });
    });

    return visible;
  })();

  // Convert to Set for fast lookup (but keep reactive dependency on array)
  $: visiblePersons = new Set(visiblePersonIds);

  // Detect when scroll indicator hovers over event markers
  $: {
    // Don't trigger tooltip updates while we're calculating placement
    if (isCalculatingPlacement) {
      // Skip this reactive block to prevent infinite loops
    } else {
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
                personTopPx: calculatePersonTop(themeIndex, personIndex, visiblePersonIds)
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
      // Check if we're already showing a tooltip for this exact cluster
      const isShowingSameCluster = activeEventTooltip &&
        !activeEventTooltip.clickTriggered &&
        activeEventTooltip.events &&
        activeEventTooltip.events.length === closestCluster.events.length &&
        activeEventTooltip.events.every((evt, idx) =>
          evt.personId === closestCluster.events[idx].personId &&
          evt.eventIndex === closestCluster.events[idx].eventIndex
        );

      if (!isShowingSameCluster) {
        if (indicatorHoverTimeout) clearTimeout(indicatorHoverTimeout);

        indicatorHoverTimeout = setTimeout(() => {
          // Double-check we're not in the middle of calculating placement
          if (!isCalculatingPlacement && (!activeEventTooltip || !activeEventTooltip.clickTriggered)) {
            showGroupedEventTooltip(closestCluster);
          }
        }, 600);
      }
    } else if (!closestCluster) {
      if (indicatorHoverTimeout) {
        clearTimeout(indicatorHoverTimeout);
        indicatorHoverTimeout = null;
      }
      if (activeEventTooltip && !activeEventTooltip.clickTriggered) {
        hideEventTooltip();
      }
    }
    } // End of isCalculatingPlacement check
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

  // Determine which chapter is currently active based on year indicator position
  $: currentChapterByIndicator = (() => {
    if (!currentIndicatorYear || !chaptersWithPositions || chaptersWithPositions.length === 0) {
      return null;
    }

    // Find the chapter whose date range contains the current indicator year
    const activeChapter = chaptersWithPositions.find(chapter => {
      const startYear = parseInt(chapter.date_start);
      const endYear = parseInt(chapter.date_end);
      return currentIndicatorYear >= startYear && currentIndicatorYear <= endYear;
    });

    return activeChapter || null;
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

  // Heights for collapsed vs expanded states
  const PERSON_ROW_HEIGHT_COLLAPSED = 10; // Desktop collapsed height
  const PERSON_ROW_HEIGHT_COLLAPSED_MOBILE = 8; // Mobile collapsed height (not used in calculation, just CSS)

  // Calculate vertical offset for theme title
  function calculateThemeTop(themeIndex, _visibleIds) {
    if (!themesWithPersons) return 0;
    const visibleSet = new Set(_visibleIds);

    let offset = 0;
    for (let i = 0; i < themeIndex; i++) {
      offset += THEME_TITLE_HEIGHT;

      // Add height for each person in this theme (accounting for collapsed state)
      themesWithPersons[i].persons.forEach(personData => {
        const isVisible = visibleSet.has(personData.personId);
        offset += isVisible ? PERSON_ROW_HEIGHT : PERSON_ROW_HEIGHT_COLLAPSED;
      });

      offset += THEME_SPACING;
    }
    return offset;
  }

  // Calculate vertical offset for person within theme
  function calculatePersonTop(themeIndex, personIndex, _visibleIds) {
    if (!themesWithPersons) return 0;
    const visibleSet = new Set(_visibleIds);

    let offset = calculateThemeTop(themeIndex, _visibleIds);
    offset += THEME_TITLE_HEIGHT;

    // Add height for each person before this one in the same theme
    for (let i = 0; i < personIndex; i++) {
      const personData = themesWithPersons[themeIndex].persons[i];
      const isVisible = visibleSet.has(personData.personId);
      offset += isVisible ? PERSON_ROW_HEIGHT : PERSON_ROW_HEIGHT_COLLAPSED;
    }

    return offset;
  }

  // Calculate total timeline height needed (always use full expanded height to prevent jumps)
  $: timelineHeightPx = (() => {
    if (!themesWithPersons || themesWithPersons.length === 0) return 300;

    // Fixed heights for top sections
    const topPadding = 100; // .timeline-wrapper padding-top for fixed chapter header
    const yearAxisHeight = 40; // .year-axis height
    const yearAxisMarginTop = 5;
    const personsLayerMarginTop = 10;

    // Calculate persons layer height (always use expanded height to prevent layout shifts)
    let personsLayerHeight = 0;
    themesWithPersons.forEach((theme, index) => {
      personsLayerHeight += THEME_TITLE_HEIGHT;

      // Always use expanded height for all persons to maintain consistent container height
      theme.persons.forEach(personData => {
        personsLayerHeight += PERSON_ROW_HEIGHT;
      });

      if (index < themesWithPersons.length - 1) {
        personsLayerHeight += THEME_SPACING;
      }
    });

    // Add some bottom padding
    const bottomPadding = 20;

    return topPadding + yearAxisMarginTop + yearAxisHeight + personsLayerMarginTop + personsLayerHeight + bottomPadding;
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

  // Cache for density map performance
  let cachedDensityMap = null;
  let lastDensityMapScroll = 0;

  // Guard against infinite tooltip placement loops
  let isCalculatingPlacement = false;

  // Helper to render tooltip content for runtime measurement
  function renderTooltipContentForMeasurement(config) {
    const { events } = config;

    // Build HTML structure matching actual tooltip
    const eventItems = events.map(evt => `
      <div class="event-item" style="--item-primary: ${evt.colors.primary}; --item-primary-rgb: ${evt.colors.primaryRgb};">
        <div class="event-item-header">
          <div class="event-item-header-content">
            <div class="event-person-name">${evt.personName}</div>
            <div class="event-item-title">${evt.event.title}</div>
          </div>
          <button class="tooltip-action-compact">→</button>
        </div>
        ${evt.event.theme_connection ? `
          <p class="event-item-description">${evt.event.theme_connection}</p>
        ` : ''}
      </div>
    `).join('');

    return `<div class="tooltip-events">${eventItems}</div>`;
  }

  // Measure actual tooltip dimensions at runtime (replaces static estimates)
  function measureTooltipDimensions(tooltipConfig) {
    // Create invisible clone of tooltip for measurement
    const measurementElement = document.createElement('div');
    measurementElement.className = `event-tooltip ${
      tooltipConfig.events.length > 1 ? 'grouped' : ''
    }`;

    // Apply max-width constraints to match actual tooltip CSS
    // Use consistent width for both single and multiple events
    // Reserve space for nav buttons (40px on each side)
    const maxWidth = Math.min(540, (window.innerWidth - 80) * 0.9);

    measurementElement.style.cssText = `
      position: fixed;
      visibility: hidden;
      pointer-events: none;
      top: -10000px;
      left: -10000px;
      max-width: ${maxWidth}px;
      opacity: 0;
      z-index: -9999;
    `;

    // Render tooltip content structure
    measurementElement.innerHTML = renderTooltipContentForMeasurement(tooltipConfig);

    // Prevent this measurement from triggering any events or observers
    measurementElement.setAttribute('data-measuring', 'true');

    document.body.appendChild(measurementElement);

    const rect = measurementElement.getBoundingClientRect();
    const dimensions = {
      width: rect.width,
      height: rect.height,
      safeWidth: rect.width + 8,  // Safety margin for borders/scrollbars
      safeHeight: rect.height + 8
    };

    document.body.removeChild(measurementElement);

    return dimensions;
  }

  // Gather all boundary constraints for placement decisions
  function gatherBoundaryConstraints(triggerElement) {
    const timelineContainer = document.querySelector('.meta-timeline-container');

    return {
      viewport: {
        left: 40,  // Padding to avoid prev/next buttons
        top: 0,
        right: window.innerWidth - 40,  // Padding to avoid prev/next buttons
        bottom: window.innerHeight,
        width: window.innerWidth - 80,  // Account for both side paddings
        height: window.innerHeight
      },
      container: timelineContainer
        ? timelineContainer.getBoundingClientRect()
        : null,
      trigger: triggerElement.getBoundingClientRect(),
      scrollLeft: timelineContainer?.scrollLeft || 0
    };
  }

  // Generate 8 placement candidates (not just 2)
  function generatePlacementCandidates(boundaries, dimensions) {
    const { trigger, viewport } = boundaries;
    const CLEARANCE = 12;

    // Calculate trigger center for proximity scoring
    const triggerCenterX = trigger.left + (trigger.width / 2);
    const triggerCenterY = trigger.top + (trigger.height / 2);

    // Clamp trigger X position to visible viewport bounds
    // This prevents tooltips from being positioned off-screen when timeline is scrolled
    const safeMargin = 10;
    const clampedTriggerLeft = Math.max(
      viewport.left + dimensions.safeWidth * 0.5 + safeMargin,
      Math.min(trigger.left, viewport.right - dimensions.safeWidth * 0.5 - safeMargin)
    );
    const clampedTriggerRight = Math.max(
      viewport.left + dimensions.safeWidth + safeMargin,
      Math.min(trigger.right, viewport.right - safeMargin)
    );
    const clampedTriggerCenterX = Math.max(
      viewport.left + dimensions.safeWidth * 0.5 + safeMargin,
      Math.min(triggerCenterX, viewport.right - dimensions.safeWidth * 0.5 - safeMargin)
    );

    return [
      // Priority 1: Top-center (default preference)
      {
        name: 'top-center',
        x: clampedTriggerCenterX,
        y: trigger.top - CLEARANCE,
        anchor: { x: 0.5, y: 1.0 },
        priority: 1
      },

      // Priority 2: Bottom-center (mobile-friendly)
      {
        name: 'bottom-center',
        x: clampedTriggerCenterX,
        y: trigger.bottom + CLEARANCE,
        anchor: { x: 0.5, y: 0.0 },
        priority: 2
      },

      // Priority 3: Horizontal placements (for vertical constraints)
      {
        name: 'left-middle',
        x: clampedTriggerLeft - CLEARANCE,
        y: triggerCenterY,
        anchor: { x: 1.0, y: 0.5 },
        priority: 3
      },

      {
        name: 'right-middle',
        x: clampedTriggerRight + CLEARANCE,
        y: triggerCenterY,
        anchor: { x: 0.0, y: 0.5 },
        priority: 3
      },

      // Priority 4: Corner placements (last resort)
      {
        name: 'top-left',
        x: clampedTriggerLeft,
        y: trigger.top - CLEARANCE,
        anchor: { x: 0.0, y: 1.0 },
        priority: 4
      },

      {
        name: 'top-right',
        x: clampedTriggerRight,
        y: trigger.top - CLEARANCE,
        anchor: { x: 1.0, y: 1.0 },
        priority: 4
      },

      {
        name: 'bottom-left',
        x: clampedTriggerLeft,
        y: trigger.bottom + CLEARANCE,
        anchor: { x: 0.0, y: 0.0 },
        priority: 4
      },

      {
        name: 'bottom-right',
        x: clampedTriggerRight,
        y: trigger.bottom + CLEARANCE,
        anchor: { x: 1.0, y: 0.0 },
        priority: 4
      }
    ];
  }

  // Analyze timeline density to prefer empty space (with caching for performance)
  function analyzeTimelineDensity(forceRefresh = false) {
    const timelineContainer = document.querySelector('.meta-timeline-container');
    if (!timelineContainer) return null;

    const currentScroll = timelineContainer.scrollLeft;
    const scrollDelta = Math.abs(currentScroll - lastDensityMapScroll);

    // Use cache if scroll movement < 100px
    if (!forceRefresh && cachedDensityMap && scrollDelta < 100) {
      return cachedDensityMap;
    }

    const personsLayer = timelineContainer.querySelector('.persons-layer');
    if (!personsLayer) return null;

    const containerRect = timelineContainer.getBoundingClientRect();

    // Create density grid (50px cells)
    const CELL_SIZE = 50;
    const gridWidth = Math.ceil(containerRect.width / CELL_SIZE);
    const gridHeight = Math.ceil(containerRect.height / CELL_SIZE);

    const densityGrid = Array(gridHeight).fill(0).map(() =>
      Array(gridWidth).fill(0)
    );

    // Mark cells occupied by event markers (high density)
    const allMarkers = Array.from(personsLayer.querySelectorAll('.event-marker'));
    allMarkers.forEach(marker => {
      const rect = marker.getBoundingClientRect();
      const cellX = Math.floor((rect.left - containerRect.left + timelineContainer.scrollLeft) / CELL_SIZE);
      const cellY = Math.floor((rect.top - containerRect.top) / CELL_SIZE);

      if (cellX >= 0 && cellX < gridWidth && cellY >= 0 && cellY < gridHeight) {
        densityGrid[cellY][cellX] += 1.0; // Markers are high priority obstacles
      }
    });

    // Mark cells occupied by person lifespans (lower density)
    const allLifespans = Array.from(personsLayer.querySelectorAll('.person-lifespan'));
    allLifespans.forEach(lifespan => {
      const rect = lifespan.getBoundingClientRect();
      const startCell = Math.floor((rect.left - containerRect.left + timelineContainer.scrollLeft) / CELL_SIZE);
      const endCell = Math.floor((rect.right - containerRect.left + timelineContainer.scrollLeft) / CELL_SIZE);
      const cellY = Math.floor((rect.top - containerRect.top) / CELL_SIZE);

      for (let x = startCell; x <= endCell && x < gridWidth; x++) {
        if (x >= 0 && cellY >= 0 && cellY < gridHeight) {
          densityGrid[cellY][x] += 0.3; // Lifespans are lower priority
        }
      }
    });

    cachedDensityMap = {
      grid: densityGrid,
      cellSize: CELL_SIZE,
      containerRect: containerRect
    };
    lastDensityMapScroll = currentScroll;

    return cachedDensityMap;
  }

  // Calculate density score for a placement
  function calculateDensityScore(placement, dimensions, densityMap) {
    if (!densityMap) return 0;

    const { grid, cellSize, containerRect } = densityMap;

    // Calculate tooltip bounding box
    const tooltipRect = {
      left: placement.x - (dimensions.safeWidth * placement.anchor.x),
      top: placement.y - (dimensions.safeHeight * placement.anchor.y),
      width: dimensions.safeWidth,
      height: dimensions.safeHeight
    };

    // Determine which cells the tooltip would overlap
    const startCellX = Math.floor((tooltipRect.left - containerRect.left) / cellSize);
    const endCellX = Math.floor((tooltipRect.left + tooltipRect.width - containerRect.left) / cellSize);
    const startCellY = Math.floor((tooltipRect.top - containerRect.top) / cellSize);
    const endCellY = Math.floor((tooltipRect.top + tooltipRect.height - containerRect.top) / cellSize);

    let totalDensity = 0;
    let cellCount = 0;

    for (let y = startCellY; y <= endCellY; y++) {
      for (let x = startCellX; x <= endCellX; x++) {
        if (y >= 0 && y < grid.length && x >= 0 && x < grid[0].length) {
          totalDensity += grid[y][x];
          cellCount++;
        }
      }
    }

    // Return average density (0 = empty space, higher = more crowded)
    return cellCount > 0 ? totalDensity / cellCount : 0;
  }

  // Comprehensive boundary checking
  function calculateBoundaryScore(placement, dimensions, boundaries) {
    const { viewport } = boundaries;

    // Calculate tooltip bounding box based on anchor point
    const tooltipRect = {
      left: placement.x - (dimensions.safeWidth * placement.anchor.x),
      top: placement.y - (dimensions.safeHeight * placement.anchor.y),
      right: placement.x + (dimensions.safeWidth * (1 - placement.anchor.x)),
      bottom: placement.y + (dimensions.safeHeight * (1 - placement.anchor.y))
    };

    let clipping = 0;
    const violations = [];

    // Check all four viewport edges
    if (tooltipRect.left < viewport.left) {
      const overflow = viewport.left - tooltipRect.left;
      clipping += overflow;
      violations.push(`left: ${overflow.toFixed(0)}px`);
    }

    if (tooltipRect.right > viewport.right) {
      const overflow = tooltipRect.right - viewport.right;
      clipping += overflow;
      violations.push(`right: ${overflow.toFixed(0)}px`);
    }

    if (tooltipRect.top < viewport.top) {
      const overflow = viewport.top - tooltipRect.top;
      clipping += overflow;
      violations.push(`top: ${overflow.toFixed(0)}px`);
    }

    if (tooltipRect.bottom > viewport.bottom) {
      const overflow = tooltipRect.bottom - viewport.bottom;
      clipping += overflow;
      violations.push(`bottom: ${overflow.toFixed(0)}px`);
    }

    return {
      clipping,        // Total pixels clipped (0 = no clipping)
      violations,      // List of boundary violations
      tooltipRect      // Final computed position
    };
  }

  // Multi-factor scoring system to select optimal placement
  function selectOptimalPlacement(candidates, dimensions, boundaries, densityMap) {
    const scoredCandidates = candidates.map(candidate => {
      let score = 0;
      const debugReasons = [];

      // Factor 1: Boundary compliance (CRITICAL - 100 points or disqualified)
      const boundaryScore = calculateBoundaryScore(candidate, dimensions, boundaries);
      if (boundaryScore.clipping > 0) {
        score = -1000; // Disqualified
        debugReasons.push(`CLIPPED: ${boundaryScore.violations.join(', ')}`);
      } else {
        score += 100;
        debugReasons.push('✓ No clipping');
      }

      // Factor 2: Empty space preference (50 points max)
      const densityScore = calculateDensityScore(candidate, dimensions, densityMap);
      const emptySpacePoints = Math.max(0, 50 - (densityScore * 10));
      score += emptySpacePoints;
      debugReasons.push(`Density: ${densityScore.toFixed(2)} → ${emptySpacePoints.toFixed(1)}pts`);

      // Factor 3: Proximity to trigger (30 points max)
      const triggerCenterX = boundaries.trigger.left + (boundaries.trigger.width / 2);
      const triggerCenterY = boundaries.trigger.top + (boundaries.trigger.height / 2);
      const distance = Math.sqrt(
        Math.pow(candidate.x - triggerCenterX, 2) +
        Math.pow(candidate.y - triggerCenterY, 2)
      );
      const proximityPoints = Math.max(0, 30 - (distance / 10));
      score += proximityPoints;
      debugReasons.push(`Distance: ${distance.toFixed(0)}px → ${proximityPoints.toFixed(1)}pts`);

      // Factor 4: Priority bonus (20 points max)
      const priorityPoints = (5 - candidate.priority) * 5;
      score += priorityPoints;
      debugReasons.push(`Priority: ${candidate.priority} → ${priorityPoints}pts`);

      return {
        ...candidate,
        score,
        debugReasons,
        boundaryScore: boundaryScore
      };
    });

    // Sort by score (highest first)
    scoredCandidates.sort((a, b) => b.score - a.score);

    // Return best candidate (or fallback if all clipped)
    const best = scoredCandidates[0];

    if (best.score < 0) {
      return generateFallbackPlacement(boundaries, dimensions);
    }

    return best;
  }

  // Fallback placement when all candidates clip
  function generateFallbackPlacement(boundaries, dimensions) {
    const { viewport, trigger } = boundaries;

    // Strategy: Center horizontally, position at top of viewport with scroll
    const x = Math.min(
      Math.max(
        trigger.left + (trigger.width / 2),
        dimensions.safeWidth / 2 + 10
      ),
      viewport.right - dimensions.safeWidth / 2 - 10
    );

    const y = viewport.top + 60; // 60px from top

    return {
      name: 'fallback-top',
      x,
      y,
      anchor: { x: 0.5, y: 0.0 },
      priority: 5,
      score: -500, // Negative score indicates fallback
      isFallback: true,
      debugReasons: ['All placements violated boundaries - using fallback']
    };
  }

  // Mobile-specific optimizations
  function applyMobileOptimizations(placement, dimensions, boundaries) {
    const { viewport } = boundaries;
    const isMobile = viewport.width < 768;
    const isVerySmall = viewport.width < 400 || viewport.height < 500;

    if (!isMobile) return placement;

    // Very small screens: Force bottom placement with constrained width
    if (isVerySmall) {
      const maxWidth = viewport.width - 20;

      // If tooltip is too tall for viewport, enable internal scrolling
      if (dimensions.safeHeight > viewport.height * 0.7) {
        return {
          ...placement,
          name: 'mobile-scroll-bottom',
          x: viewport.width / 2,
          y: viewport.top + 60,
          anchor: { x: 0.5, y: 0.0 },
          maxWidth,
          maxHeight: viewport.height * 0.7,
          enableInternalScroll: true,
          mobileOverride: true
        };
      }

      // Otherwise, prefer bottom placement (thumb-friendly)
      if (!placement.name.includes('bottom')) {
        return {
          ...placement,
          name: 'mobile-bottom',
          y: Math.min(
            boundaries.trigger.bottom + 20,
            viewport.bottom - dimensions.safeHeight - 10
          ),
          anchor: { x: 0.5, y: 0.0 },
          maxWidth,
          mobileOverride: true
        };
      }
    }

    return placement;
  }

  // Main placement orchestrator - unified logic for all tooltips
  function calculateTooltipPlacement(triggerElement, tooltipConfig) {
    // Guard against infinite loops
    if (isCalculatingPlacement) {
      return null;
    }

    isCalculatingPlacement = true;

    try {
      // Phase 1: Gather information
      const dimensions = measureTooltipDimensions(tooltipConfig);
      const boundaries = gatherBoundaryConstraints(triggerElement);
      const densityMap = analyzeTimelineDensity();

      // Phase 2: Generate candidates
      const candidates = generatePlacementCandidates(boundaries, dimensions);

      // Phase 3: Score and select optimal placement
      let placement = selectOptimalPlacement(
        candidates,
        dimensions,
        boundaries,
        densityMap
      );

      // Phase 4: Apply mobile optimizations
      placement = applyMobileOptimizations(placement, dimensions, boundaries);

      // Phase 5: Return final placement with dimensions
      return {
        ...placement,
        dimensions,
        boundaries
      };
    } finally {
      // Reset flag after a small delay to let reactive statements settle
      setTimeout(() => {
        isCalculatingPlacement = false;
      }, 50);
    }
  }

  function showEventTooltip(personId, eventIndex, event, clickEvent) {
    // Clear any pending indicator hover timeout
    if (indicatorHoverTimeout) {
      clearTimeout(indicatorHoverTimeout);
      indicatorHoverTimeout = null;
    }

    // Build event configuration
    const person = getPersonById(personId);
    const colors = getPersonColors(personId);

    const eventConfig = {
      events: [{
        personId,
        eventIndex,
        event,
        personName: person.name.replace(/_/g, ' '),
        colors
      }],
      clickTriggered: true
    };

    // Use unified placement algorithm
    const placement = calculateTooltipPlacement(clickEvent.target, eventConfig);

    // Update reactive state (only if placement succeeded)
    if (placement) {
      activeEventTooltip = {
        ...eventConfig,
        ...placement,
        year: event.year
      };
    }
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

    // Find topmost event for vertical positioning
    const topEvent = cluster.events.reduce((top, evt) =>
      evt.personTopPx < top.personTopPx ? evt : top
    );

    // Create virtual trigger element at cluster position
    const virtualTrigger = {
      getBoundingClientRect: () => {
        const x = containerRect.left + cluster.leftPx - scrollLeft + 40;
        const y = containerRect.top + 60 + 40 + 10 + topEvent.personTopPx + 15;

        return {
          left: x,
          top: y,
          right: x + 24,
          bottom: y + 24,
          width: 24,
          height: 24
        };
      }
    };

    const eventConfig = {
      events: cluster.events,
      clickTriggered: false
    };

    // Use unified placement algorithm
    const placement = calculateTooltipPlacement(virtualTrigger, eventConfig);

    // Update reactive state (only if placement succeeded)
    if (placement) {
      activeEventTooltip = {
        ...eventConfig,
        ...placement,
        year: cluster.events[0].event.year
      };
    }
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

      // Invalidate density map cache on significant scroll
      const timelineContainer = document.querySelector('.meta-timeline-container');
      if (timelineContainer) {
        const scrollDelta = Math.abs(timelineContainer.scrollLeft - lastDensityMapScroll);
        if (scrollDelta > 100) {
          cachedDensityMap = null;
        }
      }
    }

    function handleResize() {
      // Invalidate density map on viewport change
      cachedDensityMap = null;

      // Close tooltips on resize (position may be invalid)
      if (activeEventTooltip) {
        hideEventTooltip();
      }
    }

    const timelineContainer = document.querySelector('.meta-timeline-container');

    document.addEventListener('click', handleClickOutside);
    window.addEventListener('resize', handleResize);
    if (timelineContainer) {
      timelineContainer.addEventListener('scroll', handleScroll);
    }

    return () => {
      document.removeEventListener('click', handleClickOutside);
      window.removeEventListener('resize', handleResize);
      if (timelineContainer) {
        timelineContainer.removeEventListener('scroll', handleScroll);
      }

      // Clear timeout on unmount
      if (indicatorHoverTimeout) {
        clearTimeout(indicatorHoverTimeout);
      }

      // Clear cache
      cachedDensityMap = null;
    };
  });
</script>

<div class="meta-timeline-container">
  <!-- Fixed chapter header display - only shown when timeline is sticky -->
  {#if isSticky && currentChapterByIndicator}
    {#key currentChapterByIndicator.id}
      <div class="fixed-chapter-header" in:fade={{ duration: 300, delay: 100 }} out:fade={{ duration: 200 }}>
        <div class="chapter-title-display">
          <div class="chapter-header-main">
            <h3 class="chapter-title-text">{currentChapterByIndicator.title}</h3>
            <span class="chapter-year-range">
              {parseInt(currentChapterByIndicator.date_start)}–{parseInt(currentChapterByIndicator.date_end)}
            </span>
          </div>
          {#if currentChapterByIndicator.bridge_statement}
            <p class="chapter-description">{currentChapterByIndicator.bridge_statement}</p>
          {/if}
        </div>
      </div>
    {/key}
  {/if}

  <div class="timeline-wrapper" class:with-header-space={isSticky} style="width: {timelineWidthPx}px;">
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
          <div class="theme-title-row" style="left: {theme.leftPx}px; width: {theme.widthPx}px; top: {calculateThemeTop(themeIndex, visiblePersonIds)}px;">
            <h4 class="theme-title">{theme.title}</h4>
          </div>
        {/if}

        <!-- Persons in this theme -->
        {#each theme.persons as personData, personIndex}
          {@const colors = getPersonColors(personData.personId)}
          <div
            class="person-lifespan"
            class:alive={personData.isAlive}
            class:collapsed={!visiblePersonIds.includes(personData.personId)}
            style="
              left: {personData.leftPx}px;
              width: {personData.widthPx}px;
              top: {calculatePersonTop(themeIndex, personIndex, visiblePersonIds)}px;
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
    <div class="scroll-indicator" style="left: {scrollIndicatorLeftPx}px; top: 90px;">
      {#if currentIndicatorYear}
        <div class="scroll-indicator-label">{currentIndicatorYear}</div>
      {/if}
    </div>
  </div>
</div>

<!-- Event tooltip (single or grouped) - rendered outside timeline container for proper fixed positioning -->
{#if activeEventTooltip}
  <div
    class="event-tooltip"
    class:grouped={activeEventTooltip.events.length > 1}
    data-mobile-scroll={activeEventTooltip.enableInternalScroll || false}
    bind:this={tooltipElement}
    style="
      left: {activeEventTooltip.x}px;
      top: {activeEventTooltip.y}px;
      --anchor-x: {activeEventTooltip.anchor.x};
      --anchor-y: {activeEventTooltip.anchor.y};
      --tooltip-max-width: {activeEventTooltip.maxWidth ? `${activeEventTooltip.maxWidth}px` : 'min(540px, calc(90vw - 80px))'};
      --tooltip-max-height: {activeEventTooltip.maxHeight ? `${activeEventTooltip.maxHeight}px` : 'none'};
      --tooltip-overflow: {activeEventTooltip.enableInternalScroll ? 'auto' : 'visible'};
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

<style>
  /* Container - full width and height scrollable panel */
  .meta-timeline-container {
    width: 100%;
    height: 100vh;
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

  /* Wrapper - fills full height to prevent layout jumps */
  .timeline-wrapper {
    position: relative;
    margin-left: 40px;
    height: 100%;
    padding-top: 0;
    transition: padding-top 0.2s ease;
  }

  /* Add padding only when sticky to make room for fixed chapter header */
  .timeline-wrapper.with-header-space {
    padding-top: 100px;
  }

  /* Fixed chapter header - positioned at top, doesn't scroll */
  .fixed-chapter-header {
    position: fixed;
    top: 0.75rem;
    left: 50%;
    transform: translateX(-50%);
    z-index: 100;
    pointer-events: none;
  }

  .chapter-title-display {
    background: rgba(15, 23, 42, 0.9);
    backdrop-filter: blur(12px);
    border: 1px solid rgba(56, 189, 248, 0.5);
    border-radius: 0.5rem;
    padding: 0.6rem 1rem;
    box-shadow: 0 4px 12px rgba(15, 23, 42, 0.4);
    max-width: 700px;

    /* Smooth transitions */
    transition: all 0.3s cubic-bezier(0.22, 1, 0.36, 1);
  }

  .chapter-title-display:hover {
    border-color: rgba(56, 189, 248, 0.7);
    box-shadow: 0 6px 16px rgba(15, 23, 42, 0.5);
  }

  .chapter-header-main {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.6rem;
    margin-bottom: 0.35rem;
  }

  .chapter-title-text {
    font-family: var(--heading-font, 'Space Grotesk', sans-serif);
    font-size: 0.95rem;
    font-weight: 600;
    color: #38bdf8;
    margin: 0;
    line-height: 1.2;
  }

  .chapter-year-range {
    font-family: var(--body-font, 'IBM Plex Sans', sans-serif);
    font-size: 0.7rem;
    font-weight: 500;
    color: rgba(148, 163, 184, 0.9);
    background: rgba(56, 189, 248, 0.1);
    padding: 0.2rem 0.4rem;
    border-radius: 0.25rem;
    white-space: nowrap;
  }

  .chapter-description {
    font-family: var(--body-font, 'IBM Plex Sans', sans-serif);
    font-size: 0.8rem;
    line-height: 1.35;
    color: #cbd5e1;
    margin: 0;
    text-align: left;
    font-style: italic;
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
    transition: top 0.3s ease-out;
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
    transition: height 0.3s ease-out, top 0.3s ease-out, transform 0.2s ease-out;
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

  /* Collapsed state - reduced height when not in viewport */
  .person-lifespan.collapsed {
    height: 10px;
  }

  /* Hide portraits when collapsed */
  .person-lifespan.collapsed .person-portrait {
    opacity: 0;
    transform: translateY(-50%) scale(0.6);
    transition: opacity 0.3s ease-out, transform 0.3s ease-out;
  }

  /* Hide person names when collapsed */
  .person-lifespan.collapsed .person-name-wrapper {
    opacity: 0;
    transition: opacity 0.3s ease-out;
  }

  /* Hide dates when collapsed */
  .person-lifespan.collapsed .person-dates {
    opacity: 0;
    transition: opacity 0.3s ease-out;
  }

  /* Reduce lifespan line height when collapsed */
  .person-lifespan.collapsed .person-line {
    height: 2px;
    transition: height 0.3s ease-out;
  }

  /* Keep event markers visible but smaller */
  .person-lifespan.collapsed .event-marker {
    transform: translate(-50%, -50%) scale(0.7);
    transition: transform 0.3s ease-out;
  }

  /* Restore height on hover for better UX */
  .person-lifespan.collapsed:hover {
    height: 30px;
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

  /* Scroll position indicator - full height */
  .scroll-indicator {
    position: absolute;
    /* top is set inline (90px) */
    height: calc(100% - 90px);
    width: 2px;
    background: none;
    border-left: 2px dashed rgba(56, 189, 248, 0.4);
    pointer-events: none;
    z-index: 15;
    transition: left 0.1s ease-out;
    display: flex;
    flex-direction: column;
    justify-content: flex-start;
  }

  /* Scroll indicator year label - vertically centered on timeline axis */
  .scroll-indicator-label {
    position: sticky;
    top: -20px;
    transform: translateX(-50%);
    background: rgba(15, 23, 42, 0.65);
    backdrop-filter: blur(6px);
    color: #e2e8f0;
    font-size: 0.875rem;
    font-weight: 600;
    padding: 4px 8px;
    border-radius: 999px;
    border: 1px solid rgba(148, 163, 184, 0.35);
    white-space: nowrap;
    width: fit-content;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
    z-index: 10;
  }

  /* Responsive - keep horizontal scrolling on mobile */
  @media (max-width: 768px) {
    .meta-timeline-container {
      padding: 0.5rem;
    }

    /* Fixed chapter header - mobile adjustments */
    .fixed-chapter-header {
      top: 0.5rem;
      left: 50%;
      transform: translateX(-50%);
    }

    .chapter-title-display {
      padding: 0.6rem 0.75rem;
      max-width: calc(100vw - 2rem);
      width: calc(100vw - 2rem);
    }

    .chapter-header-main {
      flex-direction: row;
      gap: 0.5rem;
      margin-bottom: 0.4rem;
      align-items: center;
    }

    .chapter-title-text {
      font-size: 0.9rem;
      flex: 1;
      min-width: 0;
    }

    .chapter-year-range {
      font-size: 0.7rem;
      padding: 0.2rem 0.4rem;
      flex-shrink: 0;
    }

    .chapter-description {
      font-size: 0.75rem;
      line-height: 1.4;
      text-align: left;
    }

    /* Adjust person elements for mobile */
    .person-lifespan {
      height: 24px;
    }

    /* Mobile collapsed state */
    .person-lifespan.collapsed {
      height: 8px;
    }

    .person-lifespan.collapsed:hover {
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

  /* Very small screens */
  @media (max-width: 480px) {
    .fixed-chapter-header {
      top: 0.35rem;
    }

    .chapter-title-display {
      padding: 0.5rem 0.65rem;
      max-width: calc(100vw - 0.7rem);
    }

    .chapter-header-main {
      gap: 0.35rem;
      margin-bottom: 0.35rem;
    }

    .chapter-title-text {
      font-size: 0.8rem;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      max-width: 100%;
    }

    .chapter-year-range {
      font-size: 0.65rem;
      padding: 0.15rem 0.35rem;
    }

    .chapter-description {
      font-size: 0.7rem;
      line-height: 1.3;
      display: -webkit-box;
      -webkit-line-clamp: 3;
      -webkit-box-orient: vertical;
      overflow: hidden;
      text-overflow: ellipsis;
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

  /* Event tooltip - now supports multiple placement modes */
  .event-tooltip {
    position: fixed;
    width: min(540px, calc(90vw - 80px));
    background: rgb(15, 23, 42);
    border: 2px solid rgba(56, 189, 248, 0.5);
    border-radius: 0.5rem;
    padding: 0.75rem;
    box-shadow: 0 8px 20px rgba(0, 0, 0, 0.6);
    z-index: 10000;
    font-family: var(--body-font, 'IBM Plex Sans', sans-serif);

    /* Mobile constraint overrides */
    width: var(--tooltip-max-width, min(540px, calc(90vw - 80px)));
    max-height: var(--tooltip-max-height, none);
    overflow-y: var(--tooltip-overflow, visible);

    /* Dynamic transform based on anchor point */
    transform: translate(
      calc(-100% * var(--anchor-x, 0.5)),
      calc(-100% * var(--anchor-y, 0.5))
    );
    animation: fadeInTooltip 0.2s ease;
  }

  /* Mobile scroll override */
  .event-tooltip[data-mobile-scroll="true"] .tooltip-events {
    max-height: inherit;
    overflow-y: auto;
  }

  @keyframes fadeInTooltip {
    from {
      opacity: 0;
      transform: translate(
        calc(-100% * var(--anchor-x, 0.5)),
        calc(-100% * var(--anchor-y, 0.5) - 10px)
      );
    }
    to {
      opacity: 1;
      transform: translate(
        calc(-100% * var(--anchor-x, 0.5)),
        calc(-100% * var(--anchor-y, 0.5))
      );
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

  /* Grouped tooltip - same width as single tooltip for consistency */
  .event-tooltip.grouped {
    /* Width is consistent with single tooltips */
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
