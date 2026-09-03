import { test, expect } from "@playwright/test";
import {
  filterVisible,
  isHidden,
  withHiddenFrom,
} from "../src/utils/visibility.js";

// A registry entry marked `hidden: true` stays out of the deployed site. The
// flag is decided by the English registry, which the localized ones replace
// entry by entry, so the English answer has to be carried back over.

const people = [
  { id: "ada", name: "Ada" },
  { id: "hans", name: "Hans", hidden: true },
  { id: "otto", name: "Otto", hidden: false },
];

test("only the boolean true marks an entry hidden", () => {
  expect(isHidden({ hidden: true })).toBe(true);
  expect(isHidden({ hidden: false })).toBe(false);
  expect(isHidden({ hidden: "true" })).toBe(false);
  expect(isHidden({})).toBe(false);
  expect(isHidden(null)).toBe(false);
});

test("hidden entries are dropped unless asked for", () => {
  expect(filterVisible(people).map((p) => p.id)).toEqual(["ada", "otto"]);
  expect(filterVisible(people, true)).toBe(people);
  expect(filterVisible(undefined)).toEqual([]);
});

test("the reference list decides which entries are hidden", () => {
  const localized = [
    { id: "ada", name: "Ada" },
    { id: "hans", name: "Hans" },
    { id: "otto", name: "Otto", hidden: true },
  ];
  const result = withHiddenFrom(localized, people);
  expect(result.map((p) => isHidden(p))).toEqual([false, true, false]);
  // An entry whose flag already agrees is passed through untouched, and a
  // flag the reference does not carry is removed rather than set to false.
  expect(result[0]).toBe(localized[0]);
  expect("hidden" in result[2]).toBe(false);
});

test("a missing reference hides nothing", () => {
  expect(withHiddenFrom(people, undefined).map((p) => isHidden(p))).toEqual([
    false,
    false,
    false,
  ]);
});
