// A gesture leans one way or the other, and the reader means the way it leans
// — not the way any one moment of it happens to point. A thumb on glass and
// two fingers on a trackpad both wander sideways while travelling down, so a
// scroll judged moment by moment keeps changing its mind about which axis it
// is on, and a story laid out sideways slides out from under a reader who was
// only reading further down the slide.
//
// A lock answers from where the gesture has been rather than from where it
// last was: it says nothing until enough of the gesture has arrived to say
// anything, then holds that answer until the gesture is over.

// How far one axis has to lead the other before the gesture counts as leaning
// that way. Ties, and anything close to one, go to the vertical: down the
// screen is the reading direction, and the cost of getting it wrong there is a
// slide the reader never asked to leave.
export const AXIS_DOMINANCE = 1.4;

/**
 * @param {object} options
 * @param {number} options.threshold px of travel before the axis is decided.
 * @param {number} [options.dominance] how far one axis must lead the other.
 * @param {number} [options.gapMs] a quiet spell longer than this ends the
 *   gesture. Wheels have no equivalent of a finger lifting, so a pause is the
 *   only end they have; a finger calls `reset` instead.
 */
export function createAxisLock({
  threshold,
  dominance = AXIS_DOMINANCE,
  gapMs = Infinity,
}) {
  let axis = null;
  let travelX = 0;
  let travelY = 0;
  let lastAt = null;

  function reset() {
    axis = null;
    travelX = 0;
    travelY = 0;
    lastAt = null;
  }

  return {
    get axis() {
      return axis;
    },
    reset,
    /**
     * Adds one step of the gesture: the deltas of a wheel event, or how far a
     * finger has come since the point before. Returns the axis the gesture is
     * locked to, or null while it is still too short to tell.
     *
     * @param {number} deltaX
     * @param {number} deltaY
     * @param {number} [at] timestamp in ms, for the pause that ends a gesture.
     */
    move(deltaX, deltaY, at = 0) {
      if (lastAt !== null && at - lastAt > gapMs) reset();
      lastAt = at;
      travelX += Math.abs(deltaX);
      travelY += Math.abs(deltaY);
      if (axis === null && Math.max(travelX, travelY) >= threshold) {
        axis = travelX > travelY * dominance ? "x" : "y";
      }
      return axis;
    },
  };
}
