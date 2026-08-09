/**
 * Scrollytelling step tracking, shared by the meta-story map and network.
 *
 * Both sections show a sticky stage behind a column of narration cards and
 * need to know which card the reader is on. The IntersectionObserver only
 * says WHEN to look; the active step is recomputed from card geometry every
 * time, so jump-scrolls (deep links, restored scroll positions) cannot leave
 * a stale state behind.
 */

// A card counts as reached once its top edge is above this share of the
// viewport height — matches the observer's -25% bottom rootMargin.
const BAND_BOTTOM = 0.75;

/**
 * Track which narration card is active.
 * @param {(step: number|null) => void} onActiveStep - Called with the index
 *   of the lowest card whose top is inside the band, or null before the first
 * @returns {{ observe(node: Element, index: number): { destroy(): void },
 *   disconnect(): void }} - `observe` is a Svelte action for each card;
 *   `disconnect` belongs in the component's onDestroy
 */
export function createScrollSteps(onActiveStep) {
  const stepEls = [];
  let observer = null;

  function recompute() {
    const bandBottom = window.innerHeight * BAND_BOTTOM;
    let current = null;
    for (let i = 0; i < stepEls.length; i++) {
      const el = stepEls[i];
      if (el && el.getBoundingClientRect().top < bandBottom) current = i;
    }
    onActiveStep(current);
  }

  function observe(node, index) {
    if (!observer && typeof IntersectionObserver !== "undefined") {
      observer = new IntersectionObserver(recompute, {
        rootMargin: "-55% 0px -25% 0px",
      });
    }
    stepEls[index] = node;
    observer?.observe(node);
    return {
      destroy() {
        observer?.unobserve(node);
        if (stepEls[index] === node) stepEls[index] = null;
      },
    };
  }

  function disconnect() {
    observer?.disconnect();
    observer = null;
  }

  return { observe, disconnect };
}
