import { expect, test } from "@playwright/test";
import { createAxisLock } from "../src/utils/gestureAxis.js";

/* The run of events a real gesture arrives as, sampled from a trackpad pushed
   straight down: mostly vertical, with moments whose larger half is sideways.
   Judging those moments one at a time is what used to carry a reader off the
   slide they were scrolling into. */
const wanderingScrollDown = [
  [0, 4],
  [3, 2],
  [-1, 6],
  [5, 3],
  [0, 8],
  [-4, 2],
];

test("a run that leans down is vertical, moment by moment or not", () => {
  const lock = createAxisLock({ threshold: 12 });
  const answers = wanderingScrollDown.map(([dx, dy]) => lock.move(dx, dy));

  expect(answers.at(-1)).toBe("y");
  // Never anything else along the way: an axis, once given, is the same axis
  // for the rest of the gesture.
  expect(answers.filter((axis) => axis === "x")).toEqual([]);
});

test("a lock says nothing until there is enough gesture to answer from", () => {
  const lock = createAxisLock({ threshold: 12 });

  expect(lock.move(3, 1)).toBe(null);
  expect(lock.move(3, 1)).toBe(null);
  expect(lock.axis).toBe(null);
  expect(lock.move(8, 2)).toBe("x");
});

test("a gesture that leads sideways is horizontal", () => {
  const lock = createAxisLock({ threshold: 12 });

  expect(lock.move(20, 6)).toBe("x");
  // And stays horizontal: a swipe that curls down at the end is still a swipe.
  expect(lock.move(4, 40)).toBe("x");
});

test("a gesture that leads sideways by too little is left to the reading axis", () => {
  const lock = createAxisLock({ threshold: 12, dominance: 1.4 });

  // Sideways leads, but not by enough to be sure the reader meant it, and the
  // cost of being wrong is a slide they never asked to leave.
  expect(lock.move(14, 12)).toBe("y");
});

test("a pause ends a wheel gesture, and a finger lifting ends a drag", () => {
  const paused = createAxisLock({ threshold: 12, gapMs: 150 });
  expect(paused.move(0, 14, 1000)).toBe("y");
  expect(paused.move(20, 6, 1080)).toBe("y");
  // Quiet for longer than a run of wheel events ever goes: whatever comes next
  // is a new gesture, and gets to lean whichever way it likes.
  expect(paused.move(20, 6, 1400)).toBe("x");

  const lifted = createAxisLock({ threshold: 12 });
  expect(lifted.move(0, 14)).toBe("y");
  // Without a gap the same lock holds forever, however long the wait...
  expect(lifted.move(20, 6, 99_000)).toBe("y");
  // ...until the gesture it belongs to is over.
  lifted.reset();
  expect(lifted.axis).toBe(null);
  expect(lifted.move(20, 6)).toBe("x");
});
