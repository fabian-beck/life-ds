import { test, expect } from "@playwright/test";
import {
  makeLocalizedLoader,
  mergeLocalized,
} from "../src/utils/localizedData.js";

// The rule every localized document in data/ follows: ask for the reader's
// language, fall back to English when that translation does not exist yet.
// App.svelte wrote it three times, and each copy is a chance for one document
// to stop falling back and take a half-translated corpus down with it.

const modules = {
  "en/ada": async () => ({ language: "en" }),
  "de/ada": async () => ({ language: "de" }),
  "en/only-english": async () => ({ language: "en" }),
  "en/broken": async () => {
    throw new Error("bad json");
  },
};
const pathFor = (id, language) => `${language}/${id}`;
const loader = (options = {}) =>
  makeLocalizedLoader({ modules, pathFor, label: "Doc", ...options });

test("the reader's language wins when it exists", async () => {
  expect(await loader()("ada", "de")).toEqual({ language: "de" });
});

test("a missing translation falls back to English", async () => {
  expect(await loader()("only-english", "de")).toEqual({ language: "en" });
});

test("English is the default and never falls back to itself", async () => {
  expect(await loader()("ada")).toEqual({ language: "en" });
  expect(await loader()("nothing", "en")).toBe(null);
});

test("a document in no language at all is null, not a throw", async () => {
  expect(await loader()("nothing", "de")).toBe(null);
});

test("a document that exists but fails to parse is null too", async () => {
  // The view can render an empty state; it cannot render a rejected promise.
  expect(await loader()("broken", "en")).toBe(null);
});

test("only the documents that promised to exist warn about being missing", async () => {
  const said = [];
  const warn = console.warn;
  console.warn = (...args) => said.push(args.join(" "));
  try {
    await loader()("nothing", "en");
    expect(said.filter((line) => line.includes("not found:"))).toHaveLength(0);
    await loader({ warnWhenMissing: true })("nothing", "en");
    expect(said.filter((line) => line.includes("not found:"))).toHaveLength(1);
  } finally {
    console.warn = warn;
  }
});

// --- registry merging ----------------------------------------------------

test("a localized entry replaces its English one, in place", () => {
  const merged = mergeLocalized(
    [
      { id: "a", name: "A" },
      { id: "b", name: "B" },
      { id: "c", name: "C" },
    ],
    [{ id: "b", name: "Bee" }]
  );
  expect(merged.map((entry) => entry.name)).toEqual(["A", "Bee", "C"]);
});

test("a person with no translation still appears", () => {
  // This is the whole point: the list is the same length in every language,
  // so switching language never makes someone disappear from the landing page.
  const base = [{ id: "a" }, { id: "b" }];
  expect(mergeLocalized(base, [{ id: "a", name: "Ä" }])).toHaveLength(2);
  expect(mergeLocalized(base, [])).toEqual(base);
  expect(mergeLocalized(base, undefined)).toEqual(base);
});

test("the English list decides who exists, not the translation", () => {
  // An entry only the translation knows about is not smuggled in — the
  // English registry is the reference.
  const merged = mergeLocalized([{ id: "a" }], [{ id: "a" }, { id: "ghost" }]);
  expect(merged.map((entry) => entry.id)).toEqual(["a"]);
});

test("no base is an empty list, not a crash", () => {
  expect(mergeLocalized(undefined, [{ id: "a" }])).toEqual([]);
  expect(mergeLocalized(null, null)).toEqual([]);
});
