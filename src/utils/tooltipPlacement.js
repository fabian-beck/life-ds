/**
 * Tooltip placement for the meta-story timeline.
 *
 * A 500-line placement engine — candidate generation, density analysis over a
 * grid of the timeline's markers and lifespans, multi-factor scoring, mobile
 * overrides — has no business living inside a 3,500-line component, where it
 * was untestable and read as component state. The component keeps what is
 * genuinely its own: how a tooltip's content is built and measured, and the
 * re-entrancy guard around its reactive hover block. Everything here is
 * geometry over the arguments it is given.
 *
 * The factory holds the density-map cache, which is keyed to the container's
 * horizontal scroll; the component reports scrolls and resizes so the cache
 * can be dropped when it goes stale.
 */

/**
 * @param {Object} options
 * @param {() => Element|null} options.getContainer - The scrolling timeline
 *   container; queried lazily because it mounts after the component's script
 * @param {(config: Object) => {width: number, height: number, safeWidth:
 *   number, safeHeight: number}} options.measureDimensions - Measures the
 *   tooltip the component would render for a config
 */
export function createTooltipPlacementEngine({
  getContainer,
  measureDimensions,
}) {
  // Cache for density map performance
  let cachedDensityMap = null;
  let lastDensityMapScroll = 0;

  // Gather all boundary constraints for placement decisions
  function gatherBoundaryConstraints(triggerElement) {
    const timelineContainer = getContainer();

    return {
      viewport: {
        left: 40, // Padding to avoid prev/next buttons
        top: 0,
        right: window.innerWidth - 40, // Padding to avoid prev/next buttons
        bottom: window.innerHeight,
        width: window.innerWidth - 80, // Account for both side paddings
        height: window.innerHeight,
      },
      container: timelineContainer
        ? timelineContainer.getBoundingClientRect()
        : null,
      trigger: triggerElement.getBoundingClientRect(),
      scrollLeft: timelineContainer?.scrollLeft || 0,
    };
  }

  // Generate 8 placement candidates (not just 2)
  function generatePlacementCandidates(boundaries, dimensions) {
    const { trigger, viewport } = boundaries;
    const CLEARANCE = 12;

    // Calculate trigger center for proximity scoring
    const triggerCenterX = trigger.left + trigger.width / 2;
    const triggerCenterY = trigger.top + trigger.height / 2;

    // Clamp trigger X position to visible viewport bounds
    // This prevents tooltips from being positioned off-screen when timeline is scrolled
    const safeMargin = 10;
    const clampedTriggerLeft = Math.max(
      viewport.left + dimensions.safeWidth * 0.5 + safeMargin,
      Math.min(
        trigger.left,
        viewport.right - dimensions.safeWidth * 0.5 - safeMargin
      )
    );
    const clampedTriggerRight = Math.max(
      viewport.left + dimensions.safeWidth + safeMargin,
      Math.min(trigger.right, viewport.right - safeMargin)
    );
    const clampedTriggerCenterX = Math.max(
      viewport.left + dimensions.safeWidth * 0.5 + safeMargin,
      Math.min(
        triggerCenterX,
        viewport.right - dimensions.safeWidth * 0.5 - safeMargin
      )
    );

    return [
      // Priority 1: Top-center (default preference)
      {
        name: "top-center",
        x: clampedTriggerCenterX,
        y: trigger.top - CLEARANCE,
        anchor: { x: 0.5, y: 1.0 },
        priority: 1,
      },

      // Priority 2: Bottom-center (mobile-friendly)
      {
        name: "bottom-center",
        x: clampedTriggerCenterX,
        y: trigger.bottom + CLEARANCE,
        anchor: { x: 0.5, y: 0.0 },
        priority: 2,
      },

      // Priority 3: Horizontal placements (for vertical constraints)
      {
        name: "left-middle",
        x: clampedTriggerLeft - CLEARANCE,
        y: triggerCenterY,
        anchor: { x: 1.0, y: 0.5 },
        priority: 3,
      },

      {
        name: "right-middle",
        x: clampedTriggerRight + CLEARANCE,
        y: triggerCenterY,
        anchor: { x: 0.0, y: 0.5 },
        priority: 3,
      },

      // Priority 4: Corner placements (last resort)
      {
        name: "top-left",
        x: clampedTriggerLeft,
        y: trigger.top - CLEARANCE,
        anchor: { x: 0.0, y: 1.0 },
        priority: 4,
      },

      {
        name: "top-right",
        x: clampedTriggerRight,
        y: trigger.top - CLEARANCE,
        anchor: { x: 1.0, y: 1.0 },
        priority: 4,
      },

      {
        name: "bottom-left",
        x: clampedTriggerLeft,
        y: trigger.bottom + CLEARANCE,
        anchor: { x: 0.0, y: 0.0 },
        priority: 4,
      },

      {
        name: "bottom-right",
        x: clampedTriggerRight,
        y: trigger.bottom + CLEARANCE,
        anchor: { x: 1.0, y: 0.0 },
        priority: 4,
      },
    ];
  }

  // Analyze timeline density to prefer empty space (with caching for performance)
  function analyzeTimelineDensity(forceRefresh = false) {
    const timelineContainer = getContainer();
    if (!timelineContainer) return null;

    const currentScroll = timelineContainer.scrollLeft;
    const scrollDelta = Math.abs(currentScroll - lastDensityMapScroll);

    // Use cache if scroll movement < 100px
    if (!forceRefresh && cachedDensityMap && scrollDelta < 100) {
      return cachedDensityMap;
    }

    const personsLayer = timelineContainer.querySelector(".persons-layer");
    if (!personsLayer) return null;

    const containerRect = timelineContainer.getBoundingClientRect();

    // Create density grid (50px cells)
    const CELL_SIZE = 50;
    const gridWidth = Math.ceil(containerRect.width / CELL_SIZE);
    const gridHeight = Math.ceil(containerRect.height / CELL_SIZE);

    const densityGrid = Array(gridHeight)
      .fill(0)
      .map(() => Array(gridWidth).fill(0));

    // Mark cells occupied by event markers (high density)
    const allMarkers = Array.from(
      personsLayer.querySelectorAll(".event-marker")
    );
    allMarkers.forEach((marker) => {
      const rect = marker.getBoundingClientRect();
      const cellX = Math.floor(
        (rect.left - containerRect.left + timelineContainer.scrollLeft) /
          CELL_SIZE
      );
      const cellY = Math.floor((rect.top - containerRect.top) / CELL_SIZE);

      if (cellX >= 0 && cellX < gridWidth && cellY >= 0 && cellY < gridHeight) {
        densityGrid[cellY][cellX] += 1.0; // Markers are high priority obstacles
      }
    });

    // Mark cells occupied by person lifespans (lower density)
    const allLifespans = Array.from(
      personsLayer.querySelectorAll(".person-lifespan")
    );
    allLifespans.forEach((lifespan) => {
      const rect = lifespan.getBoundingClientRect();
      const startCell = Math.floor(
        (rect.left - containerRect.left + timelineContainer.scrollLeft) /
          CELL_SIZE
      );
      const endCell = Math.floor(
        (rect.right - containerRect.left + timelineContainer.scrollLeft) /
          CELL_SIZE
      );
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
      containerRect: containerRect,
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
      left: placement.x - dimensions.safeWidth * placement.anchor.x,
      top: placement.y - dimensions.safeHeight * placement.anchor.y,
      width: dimensions.safeWidth,
      height: dimensions.safeHeight,
    };

    // Determine which cells the tooltip would overlap
    const startCellX = Math.floor(
      (tooltipRect.left - containerRect.left) / cellSize
    );
    const endCellX = Math.floor(
      (tooltipRect.left + tooltipRect.width - containerRect.left) / cellSize
    );
    const startCellY = Math.floor(
      (tooltipRect.top - containerRect.top) / cellSize
    );
    const endCellY = Math.floor(
      (tooltipRect.top + tooltipRect.height - containerRect.top) / cellSize
    );

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
      left: placement.x - dimensions.safeWidth * placement.anchor.x,
      top: placement.y - dimensions.safeHeight * placement.anchor.y,
      right: placement.x + dimensions.safeWidth * (1 - placement.anchor.x),
      bottom: placement.y + dimensions.safeHeight * (1 - placement.anchor.y),
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
      clipping, // Total pixels clipped (0 = no clipping)
      violations, // List of boundary violations
      tooltipRect, // Final computed position
    };
  }

  // Multi-factor scoring system to select optimal placement
  function selectOptimalPlacement(
    candidates,
    dimensions,
    boundaries,
    densityMap
  ) {
    const scoredCandidates = candidates.map((candidate) => {
      let score = 0;
      const debugReasons = [];

      // Factor 1: Boundary compliance (CRITICAL - 100 points or disqualified)
      const boundaryScore = calculateBoundaryScore(
        candidate,
        dimensions,
        boundaries
      );
      if (boundaryScore.clipping > 0) {
        score = -1000; // Disqualified
        debugReasons.push(`CLIPPED: ${boundaryScore.violations.join(", ")}`);
      } else {
        score += 100;
        debugReasons.push("✓ No clipping");
      }

      // Factor 2: Empty space preference (50 points max)
      const densityScore = calculateDensityScore(
        candidate,
        dimensions,
        densityMap
      );
      const emptySpacePoints = Math.max(0, 50 - densityScore * 10);
      score += emptySpacePoints;
      debugReasons.push(
        `Density: ${densityScore.toFixed(2)} → ${emptySpacePoints.toFixed(1)}pts`
      );

      // Factor 3: Proximity to trigger (30 points max)
      const triggerCenterX =
        boundaries.trigger.left + boundaries.trigger.width / 2;
      const triggerCenterY =
        boundaries.trigger.top + boundaries.trigger.height / 2;
      const distance = Math.sqrt(
        Math.pow(candidate.x - triggerCenterX, 2) +
          Math.pow(candidate.y - triggerCenterY, 2)
      );
      const proximityPoints = Math.max(0, 30 - distance / 10);
      score += proximityPoints;
      debugReasons.push(
        `Distance: ${distance.toFixed(0)}px → ${proximityPoints.toFixed(1)}pts`
      );

      // Factor 4: Priority bonus (20 points max)
      const priorityPoints = (5 - candidate.priority) * 5;
      score += priorityPoints;
      debugReasons.push(
        `Priority: ${candidate.priority} → ${priorityPoints}pts`
      );

      return {
        ...candidate,
        score,
        debugReasons,
        boundaryScore: boundaryScore,
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
      Math.max(trigger.left + trigger.width / 2, dimensions.safeWidth / 2 + 10),
      viewport.right - dimensions.safeWidth / 2 - 10
    );

    const y = viewport.top + 60; // 60px from top

    return {
      name: "fallback-top",
      x,
      y,
      anchor: { x: 0.5, y: 0.0 },
      priority: 5,
      score: -500, // Negative score indicates fallback
      isFallback: true,
      debugReasons: ["All placements violated boundaries - using fallback"],
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
          name: "mobile-scroll-bottom",
          x: viewport.width / 2,
          y: viewport.top + 60,
          anchor: { x: 0.5, y: 0.0 },
          maxWidth,
          maxHeight: viewport.height * 0.7,
          enableInternalScroll: true,
          mobileOverride: true,
        };
      }

      // Otherwise, prefer bottom placement (thumb-friendly)
      if (!placement.name.includes("bottom")) {
        return {
          ...placement,
          name: "mobile-bottom",
          y: Math.min(
            boundaries.trigger.bottom + 20,
            viewport.bottom - dimensions.safeHeight - 10
          ),
          anchor: { x: 0.5, y: 0.0 },
          maxWidth,
          mobileOverride: true,
        };
      }
    }

    return placement;
  }

  // Main placement orchestrator - unified logic for all tooltips
  function calculate(triggerElement, tooltipConfig) {
    // Phase 1: Gather information
    const dimensions = measureDimensions(tooltipConfig);
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
      boundaries,
    };
  }

  // Invalidate the density map once the container has scrolled far enough
  // that the cached grid no longer describes what is on screen.
  function noteScroll(scrollLeft) {
    if (Math.abs(scrollLeft - lastDensityMapScroll) > 100) {
      cachedDensityMap = null;
    }
  }

  function invalidateDensityCache() {
    cachedDensityMap = null;
  }

  return { calculate, noteScroll, invalidateDensityCache };
}
