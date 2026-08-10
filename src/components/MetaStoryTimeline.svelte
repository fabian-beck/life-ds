<script>
  import { onMount } from "svelte";
  import { fade } from "svelte/transition";
  import { _ } from "../stores/language.js";
  import { displayName } from "../utils/helpers.js";
  import { saveMetaStoryScroll } from "../stores/metaStoryScroll.js";
  import { queryParams, personStoryHref } from "../stores/queryParams.js";
  import { extractYear } from "../utils/story/dates.js";
  import { createTooltipPlacementEngine } from "../utils/tooltipPlacement.js";
  import { assetUrl } from "../utils/assetUrl.js";
  import personStylesData from "../../data/person_styles.json";
  import { metaStoryStyle } from "../utils/metaStoryStyles.js";

  export let metaStoryId = null; // ID of the meta story (for navigation context)
  export let currentLanguage = "en"; // Route language prefix for story links
  export let chapters = [];
  export let personsRegistry = [];
  export let subtopics = [];
  export let scrollProgress = 0; // 0 to 1, representing horizontal scroll position
  export let isSticky = false; // Whether timeline is in sticky/fullscreen mode
  export let stickyHeaderHeight = 0; // Height of MetaStoryView's sticky header (for positioning)

  // Whether the story has a glyph to open its headings with — the chapter
  // header floating over the timeline and each theme's title are the
  // timeline's subheads, and carry the same mark as the article's.
  $: storyMarked = !!metaStoryStyle(metaStoryId)?.separatorGlyphDataUrl;

  // Person styles registry
  const personStyles = personStylesData.styles;

  // Helper to get person data by ID
  function getPersonById(personId) {
    return personsRegistry.find((p) => p.id === personId);
  }

  // Helper to get person style colors
  function getPersonColors(personId) {
    const style = personStyles[personId];
    if (!style) {
      return {
        primary: "#38bdf8", // Default cyan
        secondary: "#9a7bff", // Default purple
        primaryRgb: "56, 189, 248",
        secondaryRgb: "154, 123, 255",
      };
    }

    // Convert hex to RGB
    const hexToRgb = (hex) => {
      const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
      return result
        ? `${parseInt(result[1], 16)}, ${parseInt(result[2], 16)}, ${parseInt(result[3], 16)}`
        : "255, 255, 255";
    };

    return {
      primary: style.primary,
      secondary: style.secondary,
      primaryRgb: hexToRgb(style.primary),
      secondaryRgb: hexToRgb(style.secondary),
    };
  }

  // Extract year from a stored date via the shared parser, which handles the
  // shapes a naive split misses: unpadded pre-1000 years and BCE dates
  // ("-0500"), whose leading minus a split("-") reads as an empty year.
  function getYear(dateString) {
    const year = extractYear(dateString);
    return Number.isFinite(year) ? year : null;
  }

  // Person ids the timeline draws: named by the subtopics, or — when a story
  // predates subtopics — by the chapters' event references. The props are
  // passed in (rather than read from the closure) so the reactive blocks that
  // call this visibly depend on them.
  function resolvePersonIds(subtopicList, chapterList, registry) {
    const ids = new Set();
    if (subtopicList && subtopicList.length > 0 && registry) {
      subtopicList.forEach((subtopic) =>
        subtopic.person_ids?.forEach((id) => ids.add(id))
      );
    } else if (chapterList && chapterList.length > 0) {
      chapterList.forEach((chapter) =>
        chapter.person_events?.forEach((event) => ids.add(event.person_id))
      );
    }
    return ids;
  }

  // Calculate timeline boundaries (min/max years from meta story persons' birth/death dates)
  $: timelineBounds = (() => {
    const years = [];
    resolvePersonIds(subtopics, chapters, personsRegistry).forEach(
      (personId) => {
        const person = getPersonById(personId);
        if (!person) return;
        const birthYear = getYear(person.birthDate);
        const deathYear = getYear(person.deathDate);
        if (birthYear) years.push(birthYear);
        if (deathYear) years.push(deathYear);
      }
    );
    if (years.length === 0) return { minYear: 1800, maxYear: 2000 };
    return { minYear: Math.min(...years), maxYear: Math.max(...years) };
  })();

  // Calculate total year span
  $: totalSpan = (() => {
    const span = timelineBounds.maxYear - timelineBounds.minYear;
    return span > 0 ? span : 1; // Prevent division by zero
  })();

  // ============================================
  // ADAPTIVE TEMPORAL RESOLUTION
  // The active (uncompressed) pixels-per-year scale adapts to how much time the
  // story actually covers: short stories zoom in (up to 15 px/year), long ones
  // zoom out (down to 5 px/year), so the timeline needs a comparable amount of
  // horizontal scrolling regardless of era length. The scale is derived from the
  // ACTIVE span (years actually drawn at full scale) rather than the raw
  // min→max span, so a story with long empty gaps — already handled by gap
  // compression — isn't needlessly zoomed out.
  // ============================================
  const MIN_PIXELS_PER_YEAR = 5; // Long spans: zoomed out
  const MAX_PIXELS_PER_YEAR = 15; // Short spans: zoomed in
  const TARGET_ACTIVE_WIDTH_PX = 1800; // Preferred rendered width of the active span

  // Gap compression constants
  const GAP_THRESHOLD = 50; // Minimum years to trigger compression
  const GAP_PX_PER_YEAR = 1; // Reduced scale inside compressed gaps (vs 5-15 for active)
  const GAP_MIN_PX = 60; // Minimum pixel width for any compressed gap
  const BUFFER_YEARS = 5; // Years of full-scale padding kept around each gap edge

  // ============================================
  // GAP COMPRESSION: Segment-based non-linear mapping
  // Detects gaps >50 years where no persons are alive and compresses them
  // ============================================

  // Collect all person lifespan intervals for gap detection
  function collectPersonIntervals() {
    const intervals = [];
    resolvePersonIds(subtopics, chapters, personsRegistry).forEach(
      (personId) => {
        const person = getPersonById(personId);
        if (!person) return;
        const birthYear = getYear(person.birthDate);
        if (!birthYear) return;
        const deathYear = getYear(person.deathDate) || timelineBounds.maxYear;
        intervals.push({ start: birthYear, end: deathYear });
      }
    );
    return intervals;
  }

  // Calculate compressed pixel width for a gap (1px/year, minimum 60px)
  function gapPixelWidth(gapYears) {
    return Math.max(GAP_MIN_PX, gapYears * GAP_PX_PER_YEAR);
  }

  // Merge person lifespans into the buffered "active" year intervals that are
  // drawn at full scale (year domain only — no pixels, so the adaptive scale
  // below can be derived from it before any pixel mapping exists).
  $: bufferedIntervals = (() => {
    const { minYear, maxYear } = timelineBounds;
    const intervals = collectPersonIntervals();

    if (intervals.length === 0) return [];

    // Sort and merge overlapping intervals
    intervals.sort((a, b) => a.start - b.start);
    const merged = [{ ...intervals[0] }];

    for (let i = 1; i < intervals.length; i++) {
      const current = merged[merged.length - 1];
      if (intervals[i].start <= current.end) {
        current.end = Math.max(current.end, intervals[i].end);
      } else {
        merged.push({ ...intervals[i] });
      }
    }

    // Expand each merged interval by BUFFER_YEARS on each side, clamped to timeline bounds
    for (let i = 0; i < merged.length; i++) {
      merged[i].start = Math.max(minYear, merged[i].start - BUFFER_YEARS);
      merged[i].end = Math.min(maxYear, merged[i].end + BUFFER_YEARS);
    }

    // Re-merge in case buffers caused overlaps
    const buffered = [{ ...merged[0] }];
    for (let i = 1; i < merged.length; i++) {
      const current = buffered[buffered.length - 1];
      if (merged[i].start <= current.end) {
        current.end = Math.max(current.end, merged[i].end);
      } else {
        buffered.push({ ...merged[i] });
      }
    }

    return buffered;
  })();

  // Years rendered at full scale: the buffered intervals plus any sub-threshold
  // gaps (including the leading/trailing edges), which are not compressed.
  $: activeYearSpan = (() => {
    const { minYear, maxYear } = timelineBounds;
    if (bufferedIntervals.length === 0) return totalSpan;

    let span = bufferedIntervals.reduce(
      (sum, iv) => sum + (iv.end - iv.start),
      0
    );

    const edgesAndGaps = [];
    edgesAndGaps.push(bufferedIntervals[0].start - minYear);
    for (let i = 0; i < bufferedIntervals.length - 1; i++) {
      edgesAndGaps.push(
        bufferedIntervals[i + 1].start - bufferedIntervals[i].end
      );
    }
    edgesAndGaps.push(
      maxYear - bufferedIntervals[bufferedIntervals.length - 1].end
    );

    edgesAndGaps.forEach((gap) => {
      if (gap > 0 && gap < GAP_THRESHOLD) span += gap;
    });

    return span > 0 ? span : 1; // Prevent division by zero
  })();

  // Adaptive active scale: zoom to fit the active span into a target width,
  // clamped to [MIN_PIXELS_PER_YEAR, MAX_PIXELS_PER_YEAR].
  $: pixelsPerYear = Math.max(
    MIN_PIXELS_PER_YEAR,
    Math.min(MAX_PIXELS_PER_YEAR, TARGET_ACTIVE_WIDTH_PX / activeYearSpan)
  );

  // Build timeline segments: active ranges at full scale, gaps compressed
  $: timelineSegments = (() => {
    const { minYear, maxYear } = timelineBounds;
    const buffered = bufferedIntervals;

    if (buffered.length === 0) {
      // Single active segment spanning entire timeline
      return [
        {
          type: "active",
          yearStart: minYear,
          yearEnd: maxYear,
          pixelStart: 0,
          pixelEnd: (maxYear - minYear) * pixelsPerYear,
        },
      ];
    }

    // Build segments with cumulative pixel offsets
    const segments = [];
    let px = 0;

    // Leading edge: minYear to first interval start (after buffer, usually 0)
    if (minYear < buffered[0].start) {
      const gapYears = buffered[0].start - minYear;
      if (gapYears >= GAP_THRESHOLD) {
        const w = gapPixelWidth(gapYears);
        segments.push({
          type: "gap",
          yearStart: minYear,
          yearEnd: buffered[0].start,
          pixelStart: px,
          pixelEnd: px + w,
        });
        px += w;
      } else {
        const w = gapYears * pixelsPerYear;
        segments.push({
          type: "active",
          yearStart: minYear,
          yearEnd: buffered[0].start,
          pixelStart: px,
          pixelEnd: px + w,
        });
        px += w;
      }
    }

    for (let i = 0; i < buffered.length; i++) {
      // Active segment
      const years = buffered[i].end - buffered[i].start;
      const w = years * pixelsPerYear;
      segments.push({
        type: "active",
        yearStart: buffered[i].start,
        yearEnd: buffered[i].end,
        pixelStart: px,
        pixelEnd: px + w,
      });
      px += w;

      // Gap to next interval
      if (i < buffered.length - 1) {
        const gapYears = buffered[i + 1].start - buffered[i].end;
        if (gapYears >= GAP_THRESHOLD) {
          const w = gapPixelWidth(gapYears);
          segments.push({
            type: "gap",
            yearStart: buffered[i].end,
            yearEnd: buffered[i + 1].start,
            pixelStart: px,
            pixelEnd: px + w,
          });
          px += w;
        } else {
          // Small gap: treat as active at full scale
          const gw = gapYears * pixelsPerYear;
          segments.push({
            type: "active",
            yearStart: buffered[i].end,
            yearEnd: buffered[i + 1].start,
            pixelStart: px,
            pixelEnd: px + gw,
          });
          px += gw;
        }
      }
    }

    // Trailing edge: last interval end to maxYear (after buffer, usually 0)
    const lastEnd = buffered[buffered.length - 1].end;
    if (maxYear > lastEnd) {
      const gapYears = maxYear - lastEnd;
      if (gapYears >= GAP_THRESHOLD) {
        const w = gapPixelWidth(gapYears);
        segments.push({
          type: "gap",
          yearStart: lastEnd,
          yearEnd: maxYear,
          pixelStart: px,
          pixelEnd: px + w,
        });
        px += w;
      } else {
        const w = gapYears * pixelsPerYear;
        segments.push({
          type: "active",
          yearStart: lastEnd,
          yearEnd: maxYear,
          pixelStart: px,
          pixelEnd: px + w,
        });
        px += w;
      }
    }

    return segments;
  })();

  // Convert year to pixel position using segment-based mapping.
  // Reads the reactive `timelineSegments` / `pixelsPerYear`. Svelte does not
  // track dependencies inside function bodies, so correctness relies on every
  // reactive statement that calls this being declared BELOW those two (reactive
  // statements without a declared dependency run in source order) — keep it
  // that way when adding new derived values.
  function yearToPixel(year) {
    if (!timelineSegments || timelineSegments.length === 0) {
      return (year - timelineBounds.minYear) * pixelsPerYear;
    }

    const clampedYear = Math.max(
      timelineBounds.minYear,
      Math.min(year, timelineBounds.maxYear)
    );

    for (const seg of timelineSegments) {
      if (clampedYear >= seg.yearStart && clampedYear <= seg.yearEnd) {
        const yearSpan = seg.yearEnd - seg.yearStart;
        if (yearSpan === 0) return seg.pixelStart;
        const progress = (clampedYear - seg.yearStart) / yearSpan;
        return seg.pixelStart + progress * (seg.pixelEnd - seg.pixelStart);
      }
    }

    return timelineSegments[timelineSegments.length - 1].pixelEnd;
  }

  // Convert pixel position to year using segment-based mapping (inverse)
  function pixelToYear(px) {
    if (!timelineSegments || timelineSegments.length === 0) {
      return timelineBounds.minYear + px / pixelsPerYear;
    }

    for (const seg of timelineSegments) {
      if (px >= seg.pixelStart && px <= seg.pixelEnd) {
        const pxSpan = seg.pixelEnd - seg.pixelStart;
        if (pxSpan === 0) return seg.yearStart;
        const progress = (px - seg.pixelStart) / pxSpan;
        return seg.yearStart + progress * (seg.yearEnd - seg.yearStart);
      }
    }

    if (px > timelineSegments[timelineSegments.length - 1].pixelEnd) {
      return timelineBounds.maxYear;
    }
    return timelineBounds.minYear;
  }

  // Constants for theme grouping vertical spacing (base values before density adjustment)
  const THEME_TITLE_HEIGHT = 32; // Compact theme title row with reduced spacing
  const PERSON_ROW_HEIGHT = 42; // Compact person rows with enough space for names
  const THEME_SPACING = 8; // Spacing between theme groups
  const THEME_TITLE_GAP = 6; // Gap after theme title before first person
  const HEADER_RESERVE_HEIGHT = 48; // Reserved space for fixed chapter header

  // Calculate timeline width in pixels (uses segment-based mapping when gaps exist)
  $: timelineWidthPx = (() => {
    if (timelineSegments && timelineSegments.length > 0) {
      return timelineSegments[timelineSegments.length - 1].pixelEnd;
    }
    return totalSpan * pixelsPerYear;
  })();

  // ============================================
  // ADAPTIVE DENSITY SYSTEM
  // Condenses vertical spacing when content exceeds viewport
  // ============================================

  // Calculate available vertical height for persons layer
  $: availableHeight = (() => {
    // Fixed overhead: headerReserve + yearAxisMarginTop(40) + yearAxisHeight(28) + personsLayerMarginTop(10) + bottomPadding(20)
    const fixedOverhead = headerReserve + 40 + 28 + 10 + 20;
    const stickyOffset = stickyHeaderHeight || 0;
    // Use reactive viewportHeight state (updated on resize)
    return viewportHeight - fixedOverhead - stickyOffset;
  })();

  // Calculate required height for persons content (unconstrained)
  $: requiredContentHeight = (() => {
    if (!themesWithPersons || themesWithPersons.length === 0) return 0;
    let height = 0;
    themesWithPersons.forEach((theme, i) => {
      height += THEME_TITLE_HEIGHT + THEME_TITLE_GAP;
      height += theme.persons.length * PERSON_ROW_HEIGHT;
      if (i < themesWithPersons.length - 1) height += THEME_SPACING;
    });
    return height;
  })();

  // Compute density factor with adaptive minimum based on content crowdedness
  $: densityFactor = (() => {
    if (!themesWithPersons || requiredContentHeight <= 0) return 1.0;
    if (requiredContentHeight <= availableHeight) return 1.0;

    const rawFactor = availableHeight / requiredContentHeight;

    // Adaptive minimum: more content = allow more aggressive condensing
    const personCount = themesWithPersons.reduce(
      (sum, t) => sum + t.persons.length,
      0
    );

    // Scale min from 0.6 (sparse) down to 0.4 (very crowded)
    let adaptiveMin;
    if (personCount <= 5) {
      adaptiveMin = 0.6; // Sparse: preserve readability
    } else if (personCount <= 15) {
      adaptiveMin = 0.5; // Moderate: balanced condensing
    } else {
      adaptiveMin = 0.4; // Crowded: aggressive to fit content
    }

    return Math.max(adaptiveMin, Math.min(1.0, rawFactor));
  })();

  // Effective dimensions based on density factor
  $: effectiveThemeTitleHeight = Math.round(THEME_TITLE_HEIGHT * densityFactor);
  $: effectivePersonRowHeight = Math.round(PERSON_ROW_HEIGHT * densityFactor);
  $: effectiveThemeSpacing = Math.round(THEME_SPACING * densityFactor);
  $: effectiveThemeTitleGap = Math.round(THEME_TITLE_GAP * densityFactor);
  $: effectivePersonRowHeightCollapsed = Math.round(
    PERSON_ROW_HEIGHT_COLLAPSED * densityFactor
  );

  // Calculate scroll indicator position based on scroll progress
  $: scrollIndicatorLeftPx = scrollProgress * timelineWidthPx;

  // Calculate current year at scroll indicator position (uses segment-based inverse mapping)
  $: currentIndicatorYear = (() => {
    if (!timelineBounds) return null;
    const year = Math.round(pixelToYear(scrollIndicatorLeftPx));
    return Math.max(
      timelineBounds.minYear,
      Math.min(year, timelineBounds.maxYear)
    );
  })();

  // Calculate visible viewport bounds in pixel coordinates
  $: viewportBounds = (() => {
    if (typeof window === "undefined") {
      return null;
    }

    const container = document.querySelector(".meta-timeline-container");
    if (!container) {
      return null;
    }

    const viewportWidthPx = container.clientWidth;
    const scrollLeftPx =
      scrollProgress * Math.max(0, timelineWidthPx - viewportWidthPx);

    return {
      left: scrollLeftPx,
      right: scrollLeftPx + viewportWidthPx,
    };
  })();

  // Track which persons are visible in viewport (as array for Svelte reactivity)
  $: visiblePersonIds = (() => {
    if (!themesWithPersons) {
      return [];
    }

    // On initial load, if viewportBounds is not yet available, show persons at the start
    if (!viewportBounds) {
      const visible = [];
      const INITIAL_VIEWPORT_WIDTH =
        typeof window !== "undefined" ? window.innerWidth : 1200;
      const VISIBILITY_MARGIN = 100;

      themesWithPersons.forEach((theme) => {
        theme.persons.forEach((personData) => {
          const personLeft = personData.leftPx;
          const personRight = personData.leftPx + personData.widthPx;

          // Check if person is visible in initial viewport (starting at 0)
          const isVisible =
            personRight > 0 - VISIBILITY_MARGIN &&
            personLeft < INITIAL_VIEWPORT_WIDTH + VISIBILITY_MARGIN;

          if (isVisible) {
            visible.push(personData.personId);
          }
        });
      });

      return visible;
    }

    const visible = [];
    const VISIBILITY_MARGIN = 100; // Extra pixels for smooth transitions

    themesWithPersons.forEach((theme) => {
      theme.persons.forEach((personData) => {
        const personLeft = personData.leftPx;
        const personRight = personData.leftPx + personData.widthPx;

        // Check overlap with viewport (with margin)
        const isVisible =
          personRight > viewportBounds.left - VISIBILITY_MARGIN &&
          personLeft < viewportBounds.right + VISIBILITY_MARGIN;

        if (isVisible) {
          visible.push(personData.personId);
        }
      });
    });

    return visible;
  })();

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
              if (
                Math.abs(event.leftPx - scrollIndicatorLeftPx) <=
                HOVER_THRESHOLD
              ) {
                // Group by position
                if (!eventsByPosition.has(event.leftPx)) {
                  eventsByPosition.set(event.leftPx, []);
                }

                eventsByPosition.get(event.leftPx).push({
                  personId: personData.personId,
                  eventIndex,
                  event,
                  personName: displayName(personData.person.name),
                  colors: getPersonColors(personData.personId),
                  themeIndex,
                  personIndex,
                  personTopPx: calculatePersonTop(
                    themeIndex,
                    personIndex,
                    visiblePersonIds
                  ),
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
        closestCluster.events.forEach((evt) => {
          newHoveredEvents.add(`${evt.personId}-${evt.eventIndex}`);
        });
      }
      hoveredEventsByIndicator = newHoveredEvents;

      // Show grouped tooltip after delay
      if (
        closestCluster &&
        (!activeEventTooltip || !activeEventTooltip.clickTriggered)
      ) {
        // Check if we're already showing a tooltip for this exact cluster
        const isShowingSameCluster =
          activeEventTooltip &&
          !activeEventTooltip.clickTriggered &&
          activeEventTooltip.events &&
          activeEventTooltip.events.length === closestCluster.events.length &&
          activeEventTooltip.events.every(
            (evt, idx) =>
              evt.personId === closestCluster.events[idx].personId &&
              evt.eventIndex === closestCluster.events[idx].eventIndex
          );

        if (!isShowingSameCluster) {
          if (indicatorHoverTimeout) clearTimeout(indicatorHoverTimeout);

          indicatorHoverTimeout = setTimeout(() => {
            // Double-check we're not in the middle of calculating placement
            if (
              !isCalculatingPlacement &&
              (!activeEventTooltip || !activeEventTooltip.clickTriggered)
            ) {
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

  // Helper: check if a year falls inside a compressed gap segment
  function isYearInGap(year) {
    if (!timelineSegments) return false;
    return timelineSegments.some(
      (seg) => seg.type === "gap" && year > seg.yearStart && year < seg.yearEnd
    );
  }

  // Generate year markers for the axis (skip markers inside compressed gaps)
  $: yearMarkers = (() => {
    const markers = [];
    const { minYear, maxYear } = timelineBounds;

    // Calculate appropriate interval (every 10, 20, 50, or 100 years)
    const span = maxYear - minYear;
    let interval = 10;
    if (span > 200) interval = 50;
    if (span > 500) interval = 100;

    // Generate markers at interval, skipping those inside compressed gaps
    const startYear = Math.ceil(minYear / interval) * interval;
    for (let year = startYear; year <= maxYear; year += interval) {
      if (isYearInGap(year)) continue;
      const leftPx = yearToPixel(year);
      markers.push({ year, leftPx });
    }

    return markers;
  })();

  // Calculate chapter positions in pixels
  $: chaptersWithPositions = (() => {
    if (!chapters || chapters.length === 0) return [];

    return chapters.map((chapter) => {
      const startYear = getYear(chapter.date_start);
      const endYear = getYear(chapter.date_end);

      // Remove date range from title (e.g., "Title (1815-1899)" -> "Title")
      const titleWithoutDates = chapter.title.replace(
        /\s*\(\d{4}-\d{4}\)\s*$/,
        ""
      );

      return {
        ...chapter,
        title: titleWithoutDates,
        leftPx: yearToPixel(startYear),
        widthPx: yearToPixel(endYear) - yearToPixel(startYear),
      };
    });
  })();

  // Determine which chapter is currently active based on year indicator position
  $: currentChapterByIndicator = (() => {
    if (
      !currentIndicatorYear ||
      !chaptersWithPositions ||
      chaptersWithPositions.length === 0
    ) {
      return null;
    }

    // Find the chapter whose date range contains the current indicator year
    // Use exclusive end for all but the last chapter so that shared boundary years
    // (e.g., chapter 1 ends 1808, chapter 2 starts 1808) resolve to the later chapter.
    const lastIndex = chaptersWithPositions.length - 1;
    const activeChapter = chaptersWithPositions.find((chapter, idx) => {
      const startYear = getYear(chapter.date_start);
      const endYear = getYear(chapter.date_end);
      const endInclusive = idx === lastIndex;
      return (
        currentIndicatorYear >= startYear &&
        (endInclusive
          ? currentIndicatorYear <= endYear
          : currentIndicatorYear < endYear)
      );
    });

    return activeChapter || null;
  })();

  // Calculate the horizontal position for the sticky chapter header
  // It should follow the scroll indicator but stay within viewport boundaries
  $: chapterHeaderStyle = (() => {
    // Calculate top position: base offset (0.75rem) + sticky header height
    const topOffset =
      stickyHeaderHeight > 0 ? `${stickyHeaderHeight + 12}px` : "0.75rem";

    if (
      !isSticky ||
      !currentChapterByIndicator ||
      typeof window === "undefined"
    ) {
      return `left: 0; transform: translateX(50vw) translateX(-50%); top: ${topOffset};`;
    }

    const container = document.querySelector(".meta-timeline-container");
    if (!container) {
      return `left: 0; transform: translateX(50vw) translateX(-50%); top: ${topOffset};`;
    }

    const viewportWidth = container.clientWidth;

    // The indicator is at scrollIndicatorLeftPx relative to timeline-wrapper
    // We need its position relative to the viewport.
    const wrapper = container.querySelector(".timeline-wrapper");
    if (!wrapper) {
      return `left: 0; transform: translateX(50vw) translateX(-50%); top: ${topOffset};`;
    }

    const wrapperRect = wrapper.getBoundingClientRect();
    const indicatorViewportX = wrapperRect.left + scrollIndicatorLeftPx;

    // Use a fallback width if not yet measured to prevent jumpy initial positioning
    const currentWidth = chapterHeaderWidth || 400;
    const halfWidth = currentWidth / 2;
    const margin = 20; // Minimum margin from viewport edges

    const minX = halfWidth + margin;
    const maxX = viewportWidth - halfWidth - margin;

    // If the viewport is too small to even fit the header with margins, just center it
    if (maxX < minX) {
      return `left: 0; transform: translateX(50vw) translateX(-50%); top: ${topOffset};`;
    }

    const clampedX = Math.max(minX, Math.min(indicatorViewportX, maxX));

    // Use transform for positioning to avoid squishing the box when left is near viewport edge
    return `left: 0; transform: translateX(${clampedX}px) translateX(-50%); top: ${topOffset};`;
  })();

  // One drawn lifespan bar, or null when the person is unknown or undated.
  // Bounds are a parameter so callers visibly depend on timelineBounds.
  function personBar(personId, bounds) {
    const person = getPersonById(personId);
    if (!person) return null;
    const birthYear = getYear(person.birthDate);
    if (!birthYear) return null;
    const deathYear = getYear(person.deathDate);
    const endYear = deathYear || bounds.maxYear;
    return {
      person,
      personId,
      birthYear,
      deathYear,
      leftPx: yearToPixel(birthYear),
      widthPx: yearToPixel(endYear) - yearToPixel(birthYear),
      isAlive: !deathYear,
      portrait: assetUrl(person.portrait?.thumbnail || person.portrait?.image),
    };
  }

  // Helper: Extract persons from chapters (fallback when no subtopics)
  function extractPersonsFromChapters() {
    if (!chapters || chapters.length === 0 || !personsRegistry) return [];
    return Array.from(resolvePersonIds(null, chapters, personsRegistry))
      .map((personId) => personBar(personId, timelineBounds))
      .filter((p) => p !== null);
  }

  // Group persons by subtopic/theme, preserving theme order
  $: themesWithPersons = (() => {
    if (!subtopics || subtopics.length === 0 || !personsRegistry) {
      // Fallback: show all persons from chapters ungrouped
      return [
        {
          title: null,
          themeId: null,
          persons: extractPersonsFromChapters(),
          leftPx: 0,
          widthPx: 0,
        },
      ];
    }

    // Create theme groups from subtopics
    return subtopics
      .map((subtopic) => {
        const persons = subtopic.person_ids
          .map((personId) => personBar(personId, timelineBounds))
          .filter((p) => p !== null)
          .sort((a, b) => a.birthYear - b.birthYear);

        // Calculate theme title row bounds (leftmost to rightmost person)
        let themeLeftPx = 0;
        let themeWidthPx = 0;
        if (persons.length > 0) {
          const minLeft = Math.min(...persons.map((p) => p.leftPx));
          const maxRight = Math.max(
            ...persons.map((p) => p.leftPx + p.widthPx)
          );
          themeLeftPx = minLeft;
          themeWidthPx = maxRight - minLeft;
        }

        return {
          title: subtopic.title,
          themeId: subtopic.id,
          persons: persons,
          leftPx: themeLeftPx,
          widthPx: themeWidthPx,
        };
      })
      .filter((theme) => theme.persons.length > 0);
  })();

  // Heights for collapsed vs expanded states
  const PERSON_ROW_HEIGHT_COLLAPSED = 10; // Desktop collapsed height

  // Calculate vertical offset for theme title (uses effective heights for density adaptation)
  function calculateThemeTop(themeIndex, _visibleIds) {
    if (!themesWithPersons) return 0;
    const visibleSet = new Set(_visibleIds);

    let offset = 0;
    for (let i = 0; i < themeIndex; i++) {
      offset += effectiveThemeTitleHeight;

      // Add height for each person in this theme (accounting for collapsed state)
      themesWithPersons[i].persons.forEach((personData) => {
        const isVisible = visibleSet.has(personData.personId);
        offset += isVisible
          ? effectivePersonRowHeight
          : effectivePersonRowHeightCollapsed;
      });

      offset += effectiveThemeSpacing;
    }
    return offset;
  }

  // Calculate vertical offset for person within theme (uses effective heights for density adaptation)
  function calculatePersonTop(themeIndex, personIndex, _visibleIds) {
    if (!themesWithPersons) return 0;
    const visibleSet = new Set(_visibleIds);

    let offset = calculateThemeTop(themeIndex, _visibleIds);
    offset += effectiveThemeTitleHeight;

    // Add gap after theme title before first person
    offset += effectiveThemeTitleGap;

    // Add height for each person before this one in the same theme
    for (let i = 0; i < personIndex; i++) {
      const personData = themesWithPersons[themeIndex].persons[i];
      const isVisible = visibleSet.has(personData.personId);
      offset += isVisible
        ? effectivePersonRowHeight
        : effectivePersonRowHeightCollapsed;
    }

    return offset;
  }

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
        // All events are essential (weak events filtered during generation)
        if (!eventsByPerson.has(event.person_id)) {
          eventsByPerson.set(event.person_id, []);
        }

        const eventYear = getYear(event.event_date);

        if (!eventYear) {
          return;
        }

        const leftPx = yearToPixel(eventYear);

        eventsByPerson.get(event.person_id).push({
          ...event,
          title: event.event_title,
          date: event.event_date,
          year: eventYear,
          leftPx: leftPx,
          chapterTitle: chapter.title,
          theme_connection: event.theme_connection,
        });
      });
    });

    return eventsByPerson;
  })();

  // ============================================
  // OPPORTUNISTIC HISTORICAL-CONTEXT LABELS
  // Historical-context labels are decluttered globally: higher-priority events
  // claim their horizontal space first, and a label is only rendered if it fits
  // in one of a few stack rows without colliding with an already-placed label.
  // Events that can't fit keep their marker (diamond/bar) but drop the text
  // label (still reachable via hover/click). `priority` is an optional,
  // AI-generated field (higher = more important); when absent every event
  // shares a base priority and ties resolve by year, so placement stays
  // deterministic even before priorities exist in the data.
  // ============================================

  // Approximate label font metrics (font-size: 0.7rem ≈ 11.2px, white-space: nowrap)
  const LABEL_CHAR_PX = 6.3; // average glyph advance at the label font size
  const LABEL_MIN_PX = 24; // floor so very short titles still reserve space
  const LABEL_GAP_PX = 10; // minimum horizontal breathing room between labels
  const LABEL_MAX_ROWS = 3; // vertical rows available within the axis top margin

  // Estimate a label's rendered pixel width from its text length
  function estimateLabelWidth(text) {
    if (!text) return LABEL_MIN_PX;
    return Math.max(LABEL_MIN_PX, text.length * LABEL_CHAR_PX);
  }

  // Extract historical context events from chapters, with pixel positions and
  // opportunistic (priority-driven) label placement.
  $: historicalContextEvents = (() => {
    if (!chapters || chapters.length === 0) return [];

    // 1. Flatten every historical-context event across all chapters.
    const events = [];
    chapters.forEach((chapter) => {
      if (!chapter.historical_context) return;

      chapter.historical_context.forEach((event) => {
        const startYear = getYear(event.date_start);
        if (!startYear) return;

        const endYear = event.date_end ? getYear(event.date_end) : null;
        const leftPx = yearToPixel(startYear);
        const widthPx = endYear ? yearToPixel(endYear) - leftPx : 0;
        const labelPx = estimateLabelWidth(event.title);

        // Label horizontal extent depends on how the marker is anchored:
        //  • point markers are centre-anchored (CSS translateX(-50%))
        //  • range markers are left-anchored at leftPx (align-items: flex-start)
        const labelLeft = widthPx > 0 ? leftPx : leftPx - labelPx / 2;

        events.push({
          ...event,
          year: startYear,
          endYear,
          leftPx,
          widthPx,
          chapterTitle: chapter.title,
          labelLeft,
          labelRight: labelLeft + labelPx,
          priority: typeof event.priority === "number" ? event.priority : 0,
          stackIndex: 0,
          showLabel: false,
        });
      });
    });

    if (events.length === 0) return events;

    // 2. Place labels opportunistically in priority order. Each row tracks its
    //    occupied horizontal intervals; a label takes the lowest row it fits in
    //    (no overlap within LABEL_GAP_PX). If it fits in no row, its label is
    //    hidden (marker stays on the axis at row 0). Sorting a shallow copy
    //    still mutates the shared event objects returned below.
    const rows = Array.from({ length: LABEL_MAX_ROWS }, () => []);
    [...events]
      .sort((a, b) => b.priority - a.priority || a.year - b.year)
      .forEach((evt) => {
        for (let r = 0; r < LABEL_MAX_ROWS; r++) {
          const fits = rows[r].every(
            (iv) =>
              evt.labelRight + LABEL_GAP_PX <= iv.left ||
              evt.labelLeft - LABEL_GAP_PX >= iv.right
          );
          if (fits) {
            rows[r].push({ left: evt.labelLeft, right: evt.labelRight });
            evt.stackIndex = r;
            evt.showLabel = true;
            break;
          }
        }
      });

    return events;
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
    if (
      yearsWithEvents.length === 0 ||
      currentIndicatorYear === null ||
      currentIndicatorYear === undefined ||
      !timelineBounds
    )
      return null;
    return yearsWithEvents.find((y) => y > currentIndicatorYear) || null;
  }

  export function getPrevYear() {
    if (
      yearsWithEvents.length === 0 ||
      currentIndicatorYear === null ||
      currentIndicatorYear === undefined ||
      !timelineBounds
    )
      return null;
    return (
      [...yearsWithEvents].reverse().find((y) => y < currentIndicatorYear) ||
      null
    );
  }

  export function yearToScrollProgress(targetYear) {
    if (!timelineBounds || !targetYear || timelineWidthPx === 0) return null;

    // Calculate pixel position using segment-based mapping
    const targetLeftPx = yearToPixel(targetYear);

    const scrollProgress = targetLeftPx / timelineWidthPx;

    // Clamp to valid range [0, 1]
    return Math.max(0, Math.min(scrollProgress, 1));
  }

  // Tooltip state management
  let activeEventTooltip = null; // { personId, eventIndex, event, x, y, placement }
  let tooltipElement = null; // DOM reference for positioning
  let hoveredEventsByIndicator = new Set(); // Track which events are hovered by scroll indicator
  let indicatorHoverTimeout = null; // Delay before showing tooltip on indicator hover

  // Chapter header tracking
  let chapterHeaderWidth = 0;
  let chapterHeaderHeight = 0;

  // Space reserved at the top of the timeline for the floating chapter header.
  // The header can be taller than the static minimum when it carries a lead-in,
  // so grow the reserve to the measured header height (plus a gap) to keep the
  // year axis and the scroll-indicator year pill clear of the box.
  //
  // Kept as retained state (not a plain derivation) so that when the scroll
  // indicator sits in a gap with no active chapter, the reserve holds its last
  // value instead of collapsing to the minimum — otherwise the timeline jumps
  // up and back down as the box fades out and the next one fades in.
  let headerReserve = HEADER_RESERVE_HEIGHT;
  $: if (isSticky && currentChapterByIndicator && chapterHeaderHeight > 0) {
    headerReserve = Math.max(
      HEADER_RESERVE_HEIGHT,
      Math.ceil(chapterHeaderHeight) + 16
    );
  }

  // Leaving the pinned scroll-lock zone stops vertical page scroll from
  // driving this timeline's own (horizontal) scroll container, so the
  // scroll-close handler below never fires. Without this, a tooltip left
  // open here — position: fixed, so it doesn't track page scroll — would
  // stay glued to the screen over whatever section scrolls in next.
  $: if (!isSticky && activeEventTooltip) hideEventTooltip();

  // Viewport height tracking for density recalculation on resize
  let viewportHeight = typeof window !== "undefined" ? window.innerHeight : 800;

  // Guard against infinite tooltip placement loops
  let isCalculatingPlacement = false;

  // The placement engine owns candidate generation, density analysis, and
  // scoring; the component supplies its DOM specifics (container, measuring).
  const placementEngine = createTooltipPlacementEngine({
    getContainer: () => document.querySelector(".meta-timeline-container"),
    measureDimensions: measureTooltipDimensions,
  });

  // Build the same structure as the visible tooltip without parsing story
  // data as HTML. This element is only used for runtime size measurement.
  function createTooltipContentForMeasurement(config) {
    const tooltipEvents = document.createElement("div");
    tooltipEvents.className = "tooltip-events";

    for (const evt of config.events) {
      const eventItem = document.createElement("div");
      eventItem.className = "event-item";
      eventItem.classList.toggle("historical", Boolean(evt.isHistorical));
      eventItem.style.setProperty("--item-primary", evt.colors.primary);
      eventItem.style.setProperty("--item-primary-rgb", evt.colors.primaryRgb);

      const header = document.createElement("div");
      header.className = "event-item-header";
      const headerContent = document.createElement("div");
      headerContent.className = "event-item-header-content";

      if (evt.isHistorical) {
        const title = document.createElement("div");
        title.className = "event-item-title";
        title.textContent = evt.event.title ?? "";
        headerContent.appendChild(title);

        if (evt.dateRange) {
          const dateRange = document.createElement("div");
          dateRange.className = "event-date-range";
          dateRange.textContent = evt.dateRange;
          headerContent.appendChild(dateRange);
        }
      } else {
        const personName = document.createElement("div");
        personName.className = "event-person-name";
        personName.textContent = evt.personName ?? "";
        headerContent.appendChild(personName);

        const title = document.createElement("div");
        title.className = "event-item-title";
        title.textContent = evt.event.title ?? "";
        headerContent.appendChild(title);
      }

      header.appendChild(headerContent);

      if (evt.isHistorical && evt.wikipediaUrl) {
        const action = document.createElement("a");
        action.className = "tooltip-action-compact";
        action.textContent = "W";
        header.appendChild(action);
      } else if (!evt.isHistorical) {
        const action = document.createElement("button");
        action.className = "tooltip-action-compact";
        action.type = "button";
        action.textContent = "→";
        header.appendChild(action);
      }

      eventItem.appendChild(header);

      const description = evt.isHistorical
        ? evt.description
        : evt.event.theme_connection;
      if (description) {
        const descriptionElement = document.createElement("p");
        descriptionElement.className = "event-item-description";
        descriptionElement.textContent = description;
        eventItem.appendChild(descriptionElement);
      }

      tooltipEvents.appendChild(eventItem);
    }

    return tooltipEvents;
  }

  // Measure actual tooltip dimensions at runtime (replaces static estimates)
  function measureTooltipDimensions(tooltipConfig) {
    // Create invisible clone of tooltip for measurement
    const measurementElement = document.createElement("div");
    measurementElement.className = `event-tooltip ${
      tooltipConfig.events.length > 1 ? "grouped" : ""
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

    measurementElement.appendChild(
      createTooltipContentForMeasurement(tooltipConfig)
    );

    // Prevent this measurement from triggering any events or observers
    measurementElement.setAttribute("data-measuring", "true");

    document.body.appendChild(measurementElement);

    const rect = measurementElement.getBoundingClientRect();
    const dimensions = {
      width: rect.width,
      height: rect.height,
      safeWidth: rect.width + 8, // Safety margin for borders/scrollbars
      safeHeight: rect.height + 8,
    };

    document.body.removeChild(measurementElement);

    return dimensions;
  }

  // Main placement orchestrator. The re-entrancy guard stays here — it is a
  // reactive variable the hover block below watches — while the geometry
  // lives in the shared engine.
  function calculateTooltipPlacement(triggerElement, tooltipConfig) {
    // Guard against infinite loops
    if (isCalculatingPlacement) {
      return null;
    }

    isCalculatingPlacement = true;

    try {
      return placementEngine.calculate(triggerElement, tooltipConfig);
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
      events: [
        {
          personId,
          eventIndex,
          event,
          personName: displayName(person.name),
          colors,
        },
      ],
      clickTriggered: true,
    };

    // Use unified placement algorithm
    const placement = calculateTooltipPlacement(clickEvent.target, eventConfig);

    // Update reactive state (only if placement succeeded)
    if (placement) {
      activeEventTooltip = {
        ...eventConfig,
        ...placement,
        personId, // Add for active state detection
        eventIndex, // Add for active state detection
        year: event.year,
      };
    }
  }

  function hideEventTooltip() {
    activeEventTooltip = null;
  }

  // Show grouped tooltip for event cluster (used by scroll indicator)
  function showGroupedEventTooltip(cluster) {
    const timelineContainer = document.querySelector(
      ".meta-timeline-container"
    );
    if (!timelineContainer) return;

    const timelineWrapper =
      timelineContainer.querySelector(".timeline-wrapper");

    // Find ALL actual DOM elements for events in this cluster
    // Strategy: Find all event markers at the cluster's X position
    const clusterEventElements = [];

    if (timelineWrapper) {
      const allMarkers = Array.from(
        timelineWrapper.querySelectorAll(".event-marker")
      );
      const wrapperRect = timelineWrapper.getBoundingClientRect();
      const expectedX = wrapperRect.left + cluster.leftPx;

      // Find ALL markers at the cluster's X position (they're all part of the cluster)
      allMarkers.forEach((marker) => {
        const rect = marker.getBoundingClientRect();
        const markerCenterX = rect.left + rect.width / 2;

        // If this marker is at approximately the cluster's X position, include it
        if (Math.abs(markerCenterX - expectedX) < 10) {
          // 10px tolerance
          clusterEventElements.push({
            element: marker,
            rect: rect,
            eventData: null, // We don't need to match specific event data
          });
        }
      });
    }

    // If we couldn't find the DOM elements, bail out
    if (clusterEventElements.length === 0) {
      console.warn(
        "Could not find DOM elements for event cluster at",
        cluster.leftPx
      );
      return;
    }

    // Create a bounding box that encompasses ALL events in the cluster using actual DOM positions
    const virtualTrigger = {
      getBoundingClientRect: () => {
        const rects = clusterEventElements.map((e) => e.rect);
        const minLeft = Math.min(...rects.map((r) => r.left));
        const minTop = Math.min(...rects.map((r) => r.top));
        const maxRight = Math.max(...rects.map((r) => r.right));
        const maxBottom = Math.max(...rects.map((r) => r.bottom));

        return {
          left: minLeft,
          top: minTop,
          right: maxRight,
          bottom: maxBottom,
          width: maxRight - minLeft,
          height: maxBottom - minTop,
        };
      },
    };

    const eventConfig = {
      events: cluster.events,
      clickTriggered: false,
    };

    // Use unified placement algorithm
    const placement = calculateTooltipPlacement(virtualTrigger, eventConfig);

    // Update reactive state (only if placement succeeded)
    if (placement) {
      activeEventTooltip = {
        ...eventConfig,
        ...placement,
        year: cluster.events[0].event.year,
      };
    }
  }

  function showHistoricalTooltip(hEvent, clickEvent) {
    if (indicatorHoverTimeout) {
      clearTimeout(indicatorHoverTimeout);
      indicatorHoverTimeout = null;
    }

    const eventConfig = {
      events: [
        {
          personId: null,
          eventIndex: null,
          event: {
            title: hEvent.title,
            year: hEvent.year,
            event_index: undefined,
          },
          personName: null,
          colors: {
            primary: "#94a3b8",
            primaryRgb: "148, 163, 184",
            secondary: "#94a3b8",
            secondaryRgb: "148, 163, 184",
          },
          isHistorical: true,
          description: hEvent.description,
          wikipediaUrl: hEvent.wikipedia_url,
          dateRange: hEvent.endYear
            ? `${hEvent.year}–${hEvent.endYear}`
            : `${hEvent.year}`,
        },
      ],
      clickTriggered: true,
    };

    // Historical events: always place below, clamped to viewport edges
    const triggerRect = clickEvent.target.getBoundingClientRect();
    const CLEARANCE = 12;
    const EDGE_MARGIN = 10;

    // Position below the trigger element
    const y = triggerRect.bottom + CLEARANCE;

    // Use the actual CSS-computed tooltip width for clamping
    // (CSS sets width: min(540px, calc(90vw - 80px)), not max-width)
    const tooltipWidth = Math.min(540, window.innerWidth * 0.9 - 80);
    const halfWidth = tooltipWidth / 2;
    const triggerCenterX = triggerRect.left + triggerRect.width / 2;
    const minX = EDGE_MARGIN + halfWidth;
    const maxX = window.innerWidth - EDGE_MARGIN - halfWidth;
    const x = Math.max(minX, Math.min(triggerCenterX, maxX));

    activeEventTooltip = {
      ...eventConfig,
      name: "historical-bottom",
      x,
      y,
      anchor: { x: 0.5, y: 0.0 },
      year: hEvent.year,
    };
  }

  function handleEventClick(personId, event) {
    // Remember where the reader left the meta story so returning restores it
    saveMetaStoryScroll(metaStoryId);
    window.location.hash = personStoryHref({
      language: currentLanguage,
      personId,
      eventIndex: event.event_index !== undefined ? event.event_index : 0,
      metaStoryId,
      fromLanding: $queryParams.from_landing,
    }).slice(1);
  }

  // Handle person click - navigate to their story
  function handlePersonClick(personId) {
    // Remember where the reader left the meta story so returning restores it
    saveMetaStoryScroll(metaStoryId);
    window.location.hash = personStoryHref({
      language: currentLanguage,
      personId,
      metaStoryId,
      fromLanding: $queryParams.from_landing,
    }).slice(1);
  }

  // Click-outside handler to close tooltip
  onMount(() => {
    function handleClickOutside(event) {
      if (
        activeEventTooltip &&
        tooltipElement &&
        !tooltipElement.contains(event.target)
      ) {
        hideEventTooltip();
      }
    }

    // Close tooltip on scroll
    function handleScroll() {
      if (activeEventTooltip) {
        hideEventTooltip();
      }

      // Invalidate density map cache on significant scroll
      const timelineContainer = document.querySelector(
        ".meta-timeline-container"
      );
      if (timelineContainer) {
        placementEngine.noteScroll(timelineContainer.scrollLeft);
      }
    }

    function handleResize() {
      // Update viewport height for density recalculation
      viewportHeight = window.innerHeight;

      // Invalidate density map on viewport change
      placementEngine.invalidateDensityCache();

      // Close tooltips on resize (position may be invalid)
      if (activeEventTooltip) {
        hideEventTooltip();
      }
    }

    const timelineContainer = document.querySelector(
      ".meta-timeline-container"
    );

    document.addEventListener("click", handleClickOutside);
    window.addEventListener("resize", handleResize);
    if (timelineContainer) {
      timelineContainer.addEventListener("scroll", handleScroll);
    }

    return () => {
      document.removeEventListener("click", handleClickOutside);
      window.removeEventListener("resize", handleResize);
      if (timelineContainer) {
        timelineContainer.removeEventListener("scroll", handleScroll);
      }

      // Clear timeout on unmount
      if (indicatorHoverTimeout) {
        clearTimeout(indicatorHoverTimeout);
      }

      // Clear cache
      placementEngine.invalidateDensityCache();
    };
  });
</script>

<div
  class="meta-timeline-container"
  style="--density-factor: {densityFactor}; --header-reserve: {headerReserve}px;"
>
  <!-- Fixed chapter header display - only shown when timeline is sticky -->
  {#if isSticky && currentChapterByIndicator}
    {#key currentChapterByIndicator.id}
      <div
        class="fixed-chapter-header"
        in:fade={{ duration: 300, delay: 240 }}
        out:fade={{ duration: 220 }}
        style={chapterHeaderStyle}
      >
        <div
          class="chapter-title-display ms-frame"
          bind:clientWidth={chapterHeaderWidth}
          bind:clientHeight={chapterHeaderHeight}
        >
          <div class="chapter-header-main">
            <h3 class="chapter-title-text" class:marked={storyMarked}>
              {currentChapterByIndicator.title}
            </h3>
            <span class="chapter-year-range">
              {getYear(currentChapterByIndicator.date_start)}–{getYear(
                currentChapterByIndicator.date_end
              )}
            </span>
          </div>
          {#if currentChapterByIndicator.lead_in}
            <p class="chapter-lead-in">{currentChapterByIndicator.lead_in}</p>
          {/if}
        </div>
      </div>
    {/key}
  {/if}

  <div class="timeline-wrapper" style="width: {timelineWidthPx}px;">
    <!-- Chapter backgrounds -->
    <div class="chapters-layer">
      {#each chaptersWithPositions as chapter, i}
        <div
          class="chapter-box"
          class:light={i % 2 === 0}
          class:dark={i % 2 !== 0}
          class:active={currentChapterByIndicator &&
            currentChapterByIndicator.id === chapter.id}
          style="left: {chapter.leftPx}px; width: {chapter.widthPx}px;"
        ></div>
      {/each}
    </div>

    <!-- Gap indicators layer -->
    {#if timelineSegments}
      <div class="gaps-layer">
        {#each timelineSegments.filter((seg) => seg.type === "gap") as gapSegment}
          <div
            class="gap-indicator"
            style="left: {gapSegment.pixelStart}px; width: {gapSegment.pixelEnd -
              gapSegment.pixelStart}px;"
            title="{gapSegment.yearStart}–{gapSegment.yearEnd} ({gapSegment.yearEnd -
              gapSegment.yearStart} years)"
          >
            <div class="gap-label">
              {gapSegment.yearEnd - gapSegment.yearStart}y
            </div>
          </div>
        {/each}
      </div>
    {/if}

    <!-- Year axis -->
    <div class="year-axis">
      {#each yearMarkers as marker}
        <div class="year-marker" style="left: {marker.leftPx}px;">
          <div class="year-tick"></div>
          <div class="year-label">{marker.year}</div>
        </div>
      {/each}

      <!-- Historical context event markers (stacked per chapter) -->
      {#each historicalContextEvents as hEvent}
        {#if hEvent.widthPx > 0}
          <div
            class="historical-event-marker range"
            style="left: {hEvent.leftPx}px; width: {hEvent.widthPx}px; margin-bottom: {hEvent.stackIndex *
              18}px;"
            on:click={(e) => {
              e.stopPropagation();
              showHistoricalTooltip(hEvent, e);
            }}
            on:keydown={(e) => {
              if (e.key === "Enter") {
                e.stopPropagation();
                showHistoricalTooltip(hEvent, e);
              }
            }}
            role="button"
            tabindex="0"
            aria-label="{hEvent.title} ({hEvent.year}–{hEvent.endYear})"
          >
            {#if hEvent.showLabel}
              <span class="historical-event-label">{hEvent.title}</span>
            {/if}
            <div class="historical-event-bar"></div>
          </div>
        {:else}
          <div
            class="historical-event-marker point"
            style="left: {hEvent.leftPx}px; margin-bottom: {hEvent.stackIndex *
              18}px;"
            on:click={(e) => {
              e.stopPropagation();
              showHistoricalTooltip(hEvent, e);
            }}
            on:keydown={(e) => {
              if (e.key === "Enter") {
                e.stopPropagation();
                showHistoricalTooltip(hEvent, e);
              }
            }}
            role="button"
            tabindex="0"
            aria-label="{hEvent.title} ({hEvent.year})"
          >
            {#if hEvent.showLabel}
              <span class="historical-event-label">{hEvent.title}</span>
            {/if}
            <div class="historical-event-diamond"></div>
          </div>
        {/if}
      {/each}
    </div>

    <!-- Person lifespans grouped by theme -->
    <div class="persons-layer">
      {#each themesWithPersons as theme, themeIndex}
        <!-- Theme title row (only if title exists) -->
        {#if theme.title}
          <div
            class="theme-title-row"
            style="left: {theme.leftPx}px; width: {theme.widthPx}px; top: {calculateThemeTop(
              themeIndex,
              visiblePersonIds
            )}px; height: {effectiveThemeTitleHeight}px;"
          >
            <h4 class="theme-title" class:marked={storyMarked}>
              {theme.title}
            </h4>
          </div>
        {/if}

        <!-- Persons in this theme -->
        {#each theme.persons as personData, personIndex (personData.personId)}
          {@const colors = getPersonColors(personData.personId)}
          {@const isCollapsed = !visiblePersonIds.includes(personData.personId)}
          <div
            class="person-lifespan"
            class:alive={personData.isAlive}
            class:collapsed={isCollapsed}
            style="
              left: {personData.leftPx}px;
              width: {personData.widthPx}px;
              top: {calculatePersonTop(
              themeIndex,
              personIndex,
              visiblePersonIds
            )}px;
              height: {isCollapsed
              ? effectivePersonRowHeightCollapsed
              : effectivePersonRowHeight}px;
              --person-primary: {colors.primary};
              --person-secondary: {colors.secondary};
              --person-primary-rgb: {colors.primaryRgb};
              --person-secondary-rgb: {colors.secondaryRgb};
            "
            title="{displayName(
              personData.person.name
            )} ({personData.birthYear}–{personData.deathYear || 'present'})"
          >
            <div class="person-name-wrapper">
              <div class="person-name-label">
                {displayName(personData.person.name)}
              </div>
            </div>
            {#if personData.portrait}
              <div
                class="person-portrait"
                on:click={() => handlePersonClick(personData.personId)}
                on:keydown={(e) =>
                  e.key === "Enter" && handlePersonClick(personData.personId)}
                role="button"
                tabindex="0"
              >
                <img
                  src={personData.portrait}
                  alt={displayName(personData.person.name)}
                  class="portrait-image"
                />
              </div>
            {/if}
            <div class="person-line"></div>
            <div class="person-dates">
              <span class="person-birth">{personData.birthYear}</span>
              <span class="person-death">{personData.deathYear || "..."}</span>
            </div>

            <!-- Event markers -->
            {#if personEventsData.has(personData.personId)}
              {@const events = personEventsData.get(personData.personId)}
              {#each events as event, eventIndex}
                {@const relativeLeftPx = event.leftPx - personData.leftPx}
                {@const eventKey = `${personData.personId}-${eventIndex}`}
                {@const isHoveredByIndicator =
                  hoveredEventsByIndicator.has(eventKey)}
                {@const isActive =
                  activeEventTooltip &&
                  ((activeEventTooltip.personId === personData.personId &&
                    activeEventTooltip.eventIndex === eventIndex) ||
                    (activeEventTooltip.events &&
                      activeEventTooltip.events.some(
                        (evt) =>
                          evt.personId === personData.personId &&
                          evt.eventIndex === eventIndex
                      )))}
                <div
                  class="event-marker essential"
                  class:indicator-hover={isHoveredByIndicator}
                  class:active={isActive}
                  style="left: {relativeLeftPx}px;"
                  on:click={(e) => {
                    e.stopPropagation();
                    showEventTooltip(personData.personId, eventIndex, event, e);
                  }}
                  on:keydown={(e) => {
                    if (e.key === "Enter") {
                      e.stopPropagation();
                      showEventTooltip(
                        personData.personId,
                        eventIndex,
                        event,
                        e
                      );
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
    <div
      class="scroll-indicator"
      style="left: {scrollIndicatorLeftPx}px; top: {headerReserve -
        10}px; height: calc(100% - {headerReserve + 42}px);"
    >
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
      --tooltip-max-width: {activeEventTooltip.maxWidth
      ? `${activeEventTooltip.maxWidth}px`
      : 'min(540px, calc(90vw - 80px))'};
      --tooltip-max-height: {activeEventTooltip.maxHeight
      ? `${activeEventTooltip.maxHeight}px`
      : 'none'};
      --tooltip-overflow: {activeEventTooltip.enableInternalScroll
      ? 'auto'
      : 'visible'};
    "
    on:click={(e) => e.stopPropagation()}
    on:keydown={(e) => e.key === "Escape" && hideEventTooltip()}
    role="dialog"
    aria-label={$_("story.event_details")}
    tabindex="-1"
  >
    <!-- Event list (always scrollable) -->
    <div class="tooltip-events">
      {#each activeEventTooltip.events as evt}
        <div
          class="event-item"
          class:historical={evt.isHistorical}
          style="
            --item-primary: {evt.colors.primary};
            --item-primary-rgb: {evt.colors.primaryRgb};
          "
        >
          <div class="event-item-header">
            <div class="event-item-header-content">
              {#if evt.isHistorical}
                <div class="event-item-title">{evt.event.title}</div>
                {#if evt.dateRange}
                  <div class="event-date-range">{evt.dateRange}</div>
                {/if}
              {:else}
                <div class="event-person-name">{evt.personName}</div>
                <div class="event-item-title">{evt.event.title}</div>
              {/if}
            </div>
            {#if evt.isHistorical && evt.wikipediaUrl}
              <a
                class="tooltip-action-compact"
                href={evt.wikipediaUrl}
                target="_blank"
                rel="noopener noreferrer"
                title="Wikipedia">W</a
              >
            {:else if !evt.isHistorical}
              <button
                class="tooltip-action-compact"
                on:click={() => handleEventClick(evt.personId, evt.event)}
                title="Jump to event in person's story"
              >
                →
              </button>
            {/if}
          </div>

          {#if evt.isHistorical && evt.description}
            <p class="event-item-description">{evt.description}</p>
          {:else if evt.event.theme_connection}
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
    background: rgba(var(--ms-page-bg-rgb, 4, 10, 24), 0.95);
    border-top: 1px solid
      color-mix(in srgb, var(--ms-accent, #38bdf8) 30%, transparent);
    border-bottom: 1px solid
      color-mix(in srgb, var(--ms-accent, #38bdf8) 30%, transparent);
    box-shadow: 0 0 40px rgba(0, 0, 0, 0.5);
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
    padding-top: var(
      --header-reserve,
      60px
    ); /* Reserve space for fixed chapter header */
    /* Animate reserve changes so the year axis and rows glide when the
       chapter header changes height, instead of jumping. */
    transition: padding-top 0.35s cubic-bezier(0.22, 1, 0.36, 1);
  }

  /* Fixed chapter header - positioned at top, doesn't scroll */
  .fixed-chapter-header {
    position: fixed;
    /* top is set dynamically via inline style to account for sticky header */
    left: 0;
    z-index: 100;
    pointer-events: none;
    transition: transform 0.1s ease-out;
  }

  .chapter-title-display {
    background: rgba(var(--ms-page-bg-rgb, 15, 23, 42), 0.95);
    backdrop-filter: blur(12px);
    border: var(--ms-frame-border-width, 1px)
      var(--ms-frame-border-style, solid)
      color-mix(in srgb, var(--ms-accent, #38bdf8) 70%, transparent);
    border-radius: var(--ms-frame-radius, 0.5rem);
    /* Fixed padding: the header floats over the timeline and its space is
       reserved dynamically from its measured height, so it does not shrink
       with timeline density. Vertical padding keeps the year badge off the border. */
    padding: 0.55rem 0.85rem;
    box-shadow:
      0 8px 24px rgba(0, 0, 0, 0.5),
      0 0 20px color-mix(in srgb, var(--ms-accent, #38bdf8) 20%, transparent);
    max-width: 700px;

    /* Smooth transitions */
    transition: all 0.3s cubic-bezier(0.22, 1, 0.36, 1);
  }

  .chapter-title-display:hover {
    border-color: color-mix(
      in srgb,
      var(--ms-accent, #38bdf8) 70%,
      transparent
    );
    box-shadow: 0 6px 16px rgba(var(--ms-page-bg-rgb, 15, 23, 42), 0.5);
  }

  .chapter-header-main {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    /* No margin-bottom for true vertical centering */
  }

  .chapter-title-text {
    font-family: var(--heading-font, "Space Grotesk", sans-serif);
    font-size: 1.05rem;
    font-weight: 600;
    color: var(--ms-accent, #38bdf8);
    margin: 0;
    line-height: 1.2;
  }

  .chapter-year-range {
    font-family: var(--body-font, "IBM Plex Sans", sans-serif);
    font-size: 0.75rem;
    font-weight: 500;
    color: rgba(148, 163, 184, 0.9);
    background: color-mix(in srgb, var(--ms-accent, #38bdf8) 10%, transparent);
    padding: 0.2rem 0.4rem;
    border-radius: var(--ms-frame-radius-sm, 0.25rem);
    /* line-height: 1 keeps the badge shorter than the title's line box so it
       stays vertically centered inside the header instead of overlapping the border. */
    line-height: 1;
    white-space: nowrap;
  }

  /* Composed chapter lead-in (compose_meta_story.py), shown below the headline */
  .chapter-lead-in {
    margin: 0.35rem 0 0;
    font-family: var(--body-font, "IBM Plex Sans", sans-serif);
    font-size: 0.85rem;
    line-height: 1.45;
    color: rgba(203, 213, 225, 0.88);
    text-align: center;
    max-width: 34rem;
  }

  /* Gaps layer - visual indicators for compressed timeline gaps */
  .gaps-layer {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    z-index: 3;
    pointer-events: none;
  }

  .gap-indicator {
    position: absolute;
    top: 0;
    height: 100%;
    background: repeating-linear-gradient(
      -45deg,
      transparent,
      transparent 6px,
      rgba(148, 163, 184, 0.06) 6px,
      rgba(148, 163, 184, 0.06) 12px
    );
    border-left: 1px dashed rgba(148, 163, 184, 0.3);
    border-right: 1px dashed rgba(148, 163, 184, 0.3);
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .gap-label {
    position: sticky;
    top: 50%;
    background: rgba(var(--ms-page-bg-rgb, 15, 23, 42), 0.85);
    backdrop-filter: blur(4px);
    padding: 0.2rem 0.4rem;
    border-radius: 0.25rem;
    font-size: 0.6rem;
    color: rgba(148, 163, 184, 0.8);
    font-weight: 500;
    white-space: nowrap;
    border: 1px solid rgba(148, 163, 184, 0.25);
    pointer-events: auto;
    cursor: help;
    letter-spacing: 0.02em;
  }

  .gap-label:hover {
    color: #94a3b8;
    border-color: rgba(148, 163, 184, 0.5);
  }

  /* Chapters layer */
  .chapters-layer {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    z-index: 1;
    pointer-events: none;
  }

  .chapter-box {
    position: absolute;
    top: 0;
    height: 100%;
    transition: background 0.3s ease;
  }

  .chapter-box.light {
    background: rgba(255, 255, 255, 0.04);
  }

  .chapter-box.dark {
    background: rgba(255, 255, 255, 0.01);
  }

  .chapter-box.active {
    background: color-mix(in srgb, var(--ms-accent, #38bdf8) 8%, transparent);
    border: 1px solid
      color-mix(in srgb, var(--ms-accent, #38bdf8) 40%, transparent);
    box-shadow: inset 0 0 25px
      color-mix(in srgb, var(--ms-accent, #38bdf8) 15%, transparent);
    z-index: 2;
    animation: chapter-glow 5s ease-in-out infinite;
  }

  @keyframes chapter-glow {
    0%,
    100% {
      background: color-mix(in srgb, var(--ms-accent, #38bdf8) 8%, transparent);
      box-shadow: inset 0 0 25px
        color-mix(in srgb, var(--ms-accent, #38bdf8) 15%, transparent);
      border-color: color-mix(
        in srgb,
        var(--ms-accent, #38bdf8) 30%,
        transparent
      );
    }
    50% {
      background: color-mix(
        in srgb,
        var(--ms-accent, #38bdf8) 11%,
        transparent
      );
      box-shadow: inset 0 0 35px
        color-mix(in srgb, var(--ms-accent, #38bdf8) 20%, transparent);
      border-color: color-mix(
        in srgb,
        var(--ms-accent, #38bdf8) 50%,
        transparent
      );
    }
  }

  /* Year axis */
  .year-axis {
    position: relative;
    height: 28px;
    margin-top: 40px; /* Extra space above for stacked historical context labels */
    border-top: 2px solid
      color-mix(in srgb, var(--ms-accent, #38bdf8) 40%, transparent);
    z-index: 5;
  }

  .year-marker {
    position: absolute;
    top: 0;
  }

  .year-tick {
    width: 2px;
    height: 8px;
    background: color-mix(in srgb, var(--ms-accent, #38bdf8) 60%, transparent);
    margin: 0 auto;
  }

  .year-label {
    margin-top: 2px;
    font-size: 0.7rem;
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
    /* height is set inline via effectiveThemeTitleHeight */
    display: flex;
    align-items: center;
    /* Shift left by portrait radius (22px scaled by density) */
    margin-left: calc(-22px * max(0.7, var(--density-factor, 1)));
    z-index: 5;
    transition:
      top 0.3s ease-out,
      height 0.3s ease-out;
  }

  .theme-title {
    position: sticky;
    left: 0;
    font-family: var(--heading-font, "Space Grotesk", sans-serif);
    /* Scale font size based on density factor (min 70% of original) */
    font-size: calc(0.85rem * max(0.7, var(--density-factor, 1)));
    font-weight: 600;
    color: var(--ms-accent, #38bdf8);
    margin: 0;
    padding: 0;
    white-space: nowrap;
    line-height: 1;
  }

  /* The story's mark opens the timeline's headings too, exactly as it opens
     the article's subheads and the narration cards over the graph and the map.
     Only drawn when the story has a glyph. */
  .chapter-title-text.marked,
  .theme-title.marked {
    display: flex;
    align-items: center;
    gap: 0.45em;
  }

  .chapter-title-text.marked::before,
  .theme-title.marked::before {
    content: "";
    flex: 0 0 auto;
    width: 0.85em;
    height: 0.85em;
    background-image: var(--ms-glyph, none);
    background-position: center;
    background-size: contain;
    background-repeat: no-repeat;
  }

  /* Individual person lifespan */
  .person-lifespan {
    position: absolute;
    /* height is set inline via effectivePersonRowHeight */
    transition:
      height 0.3s ease-out,
      top 0.3s ease-out;
  }

  /* Collapsed state - reduced height when not in viewport */
  .person-lifespan.collapsed {
    /* Height is controlled inline via effectivePersonRowHeightCollapsed */
  }

  /* Hide portraits when collapsed */
  .person-lifespan.collapsed .person-portrait {
    opacity: 0;
    transform: translate(-50%, -50%) scale(0.6);
    transition:
      opacity 0.3s ease-out,
      transform 0.3s ease-out;
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

  /* Restore height on hover for better UX - use CSS variable for effective height */
  .person-lifespan.collapsed:hover {
    /* Height expansion on hover is handled by the component's inline style */
  }

  /* Person name wrapper - bottom anchored to the lifespan line */
  .person-name-wrapper {
    position: absolute;
    /* Offset by half portrait width (portrait radius) + small gap to clear the portrait */
    left: calc(22px * max(0.7, var(--density-factor, 1)) + 4px);
    right: 0;
    /* Bottom of name sits just above the line (which is at 50%) with small margin */
    top: calc(50% - 2px);
    transform: translateY(-100%);
    height: auto;
    overflow: visible;
    pointer-events: none;
    z-index: 5; /* In front of the lifespan line */
  }

  /* Person name label - sticky horizontal positioning */
  .person-name-label {
    position: sticky;
    left: 0;
    font-weight: 600;
    /* Scale font size based on density factor (min 70% of original) */
    font-size: calc(0.9rem * max(0.7, var(--density-factor, 1)));
    color: #e2e8f0;
    white-space: nowrap;
    padding: 0;
    background: transparent;
    width: fit-content;
    pointer-events: none;
    line-height: 1;
  }

  /* Portrait thumbnail container - centered on birth year (left edge), scales with density */
  .person-portrait {
    position: absolute;
    left: 0;
    top: 50%;
    transform: translate(-50%, -50%);
    /* Scale portrait size based on density (min 70% of original) */
    width: calc(44px * max(0.7, var(--density-factor, 1)));
    height: calc(44px * max(0.7, var(--density-factor, 1)));
    border-radius: 50%;
    border: 2px solid rgba(var(--person-primary-rgb), 0.8);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.4);
    background: rgba(var(--ms-page-bg-rgb, 15, 23, 42), 0.9);
    transition: all 0.2s;
    z-index: 10;
    overflow: hidden;
    cursor: pointer;
    outline: none;
  }

  .person-portrait:focus-visible {
    outline: 2px solid var(--ms-accent, #38bdf8);
    outline-offset: 2px;
  }

  /* Portrait image inside container */
  .portrait-image {
    width: 100%;
    height: 100%;
    object-fit: cover;
    object-position: center 35%;
    scale: 1.25;
  }

  .person-portrait:hover {
    border-color: rgba(var(--person-primary-rgb), 1);
    box-shadow: 0 4px 12px rgba(var(--person-primary-rgb), 0.6);
    transform: translate(-50%, -50%) scale(1.1);
  }

  .person-lifespan.alive .person-portrait {
    border-color: rgba(var(--person-secondary-rgb), 0.8);
  }

  .person-lifespan.alive .person-portrait:hover {
    border-color: rgba(var(--person-secondary-rgb), 1);
  }

  /* Person lifespan line - starts at left edge (birth year position) */
  .person-line {
    position: absolute;
    left: 0;
    right: 0;
    top: 50%;
    transform: translateY(-50%);
    height: 3px;
    background: linear-gradient(
      90deg,
      rgba(var(--person-primary-rgb), 0.6),
      rgba(var(--person-secondary-rgb), 0.6)
    );
    border-radius: 2px;
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.3);
    transition: all 0.2s;
    pointer-events: none;
  }

  .person-lifespan.alive .person-line {
    background: linear-gradient(
      90deg,
      rgba(var(--person-secondary-rgb), 0.6),
      rgba(var(--person-primary-rgb), 0.6)
    );
  }

  /* Person dates container - offset to clear portrait */
  .person-dates {
    position: absolute;
    /* Offset by half portrait width (portrait radius) + small gap to clear the portrait */
    left: calc(22px * max(0.7, var(--density-factor, 1)) + 4px);
    right: 0;
    top: calc(50% + 2px);
    display: flex;
    justify-content: space-between;
    pointer-events: none;
  }

  .person-birth,
  .person-death {
    /* Scale font size based on density factor (min 70% of original) */
    font-size: calc(0.65rem * max(0.7, var(--density-factor, 1)));
    color: #94a3b8;
    font-weight: 500;
    white-space: nowrap;
    background: transparent;
    padding: 1px 3px;
    border-radius: 2px;
    line-height: 1;
  }

  .person-birth {
    position: sticky;
    left: 0;
  }

  /* Scroll position indicator - full height */
  .scroll-indicator {
    position: absolute;
    /* top and height are set inline, derived from the dynamic header reserve */
    width: 2px;
    background: none;
    border-left: 2px dashed
      color-mix(in srgb, var(--ms-accent, #38bdf8) 40%, transparent);
    pointer-events: none;
    z-index: 15;
    /* left tracks the scroll position quickly; top/height follow the
       animated header reserve so the year pill glides with the axis. */
    transition:
      left 0.1s ease-out,
      top 0.35s cubic-bezier(0.22, 1, 0.36, 1),
      height 0.35s cubic-bezier(0.22, 1, 0.36, 1);
    display: flex;
    flex-direction: column;
    justify-content: flex-start;
  }

  /* Scroll indicator year label - vertically centered on timeline axis */
  .scroll-indicator-label {
    position: sticky;
    top: -20px;
    transform: translateX(-50%);
    background: rgba(var(--ms-page-bg-rgb, 15, 23, 42), 0.65);
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
      /* top and transform are set dynamically via inline style */
      /* Don't override transform here - let JavaScript positioning work */
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
      width: 36px;
      height: 36px;
      /* Keep left: 0 and transform from desktop - portrait centered on birth year */
      border-width: 2px;
    }

    .person-line {
      /* No override needed - inherits desktop positioning */
      height: 3px;
    }

    .person-lifespan:hover .person-line {
      height: 5px;
    }

    .portrait-image {
      scale: 1.25;
      object-position: center 35%;
    }

    .person-name-label {
      font-size: 0.8rem;
    }

    .person-birth,
    .person-death {
      font-size: 0.6rem;
    }

    .theme-title-row {
      height: 24px;
    }

    .theme-title {
      font-size: 0.8rem;
    }
  }

  /* Very small screens */
  @media (max-width: 480px) {
    .fixed-chapter-header {
      /* top is set dynamically via inline style */
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
    outline: 2px solid var(--ms-accent, #38bdf8);
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
    transition:
      background 0.2s,
      border 0.2s;
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
    background: var(--ms-accent, #38bdf8);
    border: 3px solid #ffffff;
    transition: none; /* Disable transitions for animation to work */
    animation: pulse-active 1.5s ease-in-out infinite;
  }

  @keyframes pulse-active {
    0%,
    100% {
      box-shadow:
        0 0 0 3px color-mix(in srgb, var(--ms-accent, #38bdf8) 50%, transparent),
        0 0 20px color-mix(in srgb, var(--ms-accent, #38bdf8) 90%, transparent),
        0 0 40px color-mix(in srgb, var(--ms-accent, #38bdf8) 60%, transparent);
      transform: translate(-50%, -50%) scale(1);
    }
    50% {
      box-shadow:
        0 0 0 6px color-mix(in srgb, var(--ms-accent, #38bdf8) 70%, transparent),
        0 0 35px var(--ms-accent, #38bdf8),
        0 0 70px color-mix(in srgb, var(--ms-accent, #38bdf8) 80%, transparent);
      transform: translate(-50%, -50%) scale(1.15);
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

  /* Event tooltip - now supports multiple placement modes */
  .event-tooltip {
    position: fixed;
    width: min(540px, calc(90vw - 80px));
    background: rgb(var(--ms-page-bg-rgb, 15, 23, 42));
    border: var(--ms-frame-border-width, 2px)
      var(--ms-frame-border-style, solid)
      color-mix(in srgb, var(--ms-accent, #38bdf8) 50%, transparent);
    border-radius: var(--ms-frame-radius, 0.5rem);
    padding: 0.75rem;
    box-shadow: 0 8px 20px rgba(0, 0, 0, 0.6);
    z-index: 10000;
    font-family: var(--body-font, "IBM Plex Sans", sans-serif);

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
    font-family: var(--heading-font, "Space Grotesk", sans-serif);
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
    font-family: var(--heading-font, "Space Grotesk", sans-serif);
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
    background: rgba(var(--ms-page-bg-rgb, 15, 23, 42), 0.5);
    border-radius: 3px;
  }

  .tooltip-events::-webkit-scrollbar-thumb {
    background: color-mix(in srgb, var(--ms-accent, #38bdf8) 40%, transparent);
    border-radius: 3px;
  }

  .tooltip-events::-webkit-scrollbar-thumb:hover {
    background: color-mix(in srgb, var(--ms-accent, #38bdf8) 60%, transparent);
  }

  /* Mobile landscape - adjust chapter header positioning */
  @media (max-height: 450px) {
    /* Keep header reserve for chapter header, but override the top position
       since the main sticky header is on the right, not the top */
    .fixed-chapter-header {
      top: 0.5rem !important;
      /* Ensure chapter header doesn't extend into right 40% where main header sits */
      right: 42% !important;
      left: 0.5rem !important;
      transform: none !important;
    }

    /* Compact chapter header for landscape - reduced padding and fonts */
    .chapter-title-display {
      max-width: 100%;
      padding: 0.3rem 0.6rem;
    }

    .chapter-header-main {
      gap: 0.4rem;
    }

    .chapter-title-text {
      font-size: 0.8rem;
    }

    .chapter-year-range {
      font-size: 0.6rem;
      padding: 0.1rem 0.3rem;
    }

    /* No room for the lead-in next to the compact landscape header */
    .chapter-lead-in {
      display: none;
    }
  }

  /* Historical context markers — positioned above the blue year-axis line */
  .historical-event-marker {
    position: absolute;
    z-index: 6;
    cursor: pointer;
  }

  /* Point event: diamond + label above the axis line */
  .historical-event-marker.point {
    transform: translateX(-50%);
    bottom: 100%;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding-bottom: 6px;
  }

  .historical-event-diamond {
    width: 7px;
    height: 7px;
    background: rgba(148, 163, 184, 0.7);
    border: 1px solid rgba(255, 255, 255, 0.4);
    transform: rotate(45deg);
    transition: all 0.2s;
    flex-shrink: 0;
  }

  .historical-event-marker.point:hover .historical-event-diamond {
    background: rgba(148, 163, 184, 1);
    border-color: rgba(255, 255, 255, 0.9);
    box-shadow: 0 0 6px rgba(148, 163, 184, 0.6);
    transform: rotate(45deg) scale(1.3);
  }

  /* Range event: bar + label above the axis line */
  .historical-event-marker.range {
    bottom: 100%;
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    padding-bottom: 6px;
  }

  .historical-event-bar {
    width: 100%;
    height: 3px;
    background: rgba(148, 163, 184, 0.35);
    border-radius: 1.5px;
    transition: all 0.2s;
  }

  .historical-event-marker.range:hover .historical-event-bar {
    background: rgba(148, 163, 184, 0.7);
    height: 4px;
  }

  /* Keyword label — always visible, above the marker */
  .historical-event-label {
    font-size: 0.7rem;
    font-weight: 500;
    color: rgba(148, 163, 184, 0.8);
    white-space: nowrap;
    pointer-events: none;
    line-height: 1;
    margin-bottom: 2px;
  }

  .historical-event-marker:hover .historical-event-label {
    color: rgba(148, 163, 184, 1);
  }

  /* Historical event tooltip styles */
  .event-date-range {
    font-size: 0.7rem;
    color: #94a3b8;
    margin-top: 0.15rem;
  }

  /* Wikipedia link styled as tooltip action */
  a.tooltip-action-compact {
    text-decoration: none;
    font-weight: 700;
    font-size: 0.85rem;
  }

  a.tooltip-action-compact:hover {
    transform: none;
    background: rgba(var(--item-primary-rgb), 0.4);
  }
</style>
