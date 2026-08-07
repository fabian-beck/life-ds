import { test, expect } from "@playwright/test";
import { composeDepthParagraphs } from "../src/utils/storyHelpers.js";
import en from "../src/locales/en.json" with { type: "json" };

// The real translate function, so the templates under test are the ones the
// application ships rather than a paraphrase of them.
function t(key, params = {}) {
  return Object.entries(params).reduce(
    (text, [name, value]) => text.replaceAll(`{${name}}`, value),
    en[key] ?? key
  );
}

const flatten = (paragraphs) =>
  paragraphs.map((p) => p.map((segment) => segment.text).join("")).join(" ");

const depth = {
  places: [{ historic: "Bletchley", modern: "Milton Keynes" }],
  terms: [
    {
      term: "Hut 8",
      explanation: "A section at Bletchley Park",
      wikipediaUrl: "https://en.wikipedia.org/wiki/Hut_8",
    },
  ],
  people: [
    {
      person_name: "Joan Clarke",
      relationship_description: "A cryptanalyst in the same section",
    },
  ],
  images: [],
  sources: [],
};

test("the place is named under both of the names it has had", () => {
  expect(flatten(composeDepthParagraphs(depth, t))).toBe(
    "It happened at Bletchley, a place today's maps name Milton Keynes."
  );
});

test("a place with one name gets the shorter sentence", () => {
  expect(
    flatten(
      composeDepthParagraphs(
        { places: [{ historic: "Wilmslow", modern: "Wilmslow" }] },
        t
      )
    )
  ).toBe("It happened at Wilmslow.");
});

test("everything with an affordance of its own is left to it", () => {
  // The terms are marked in the description, where a tap opens the
  // explanation. The people are chips on the slide, and a chip is how this
  // application gives a person's context everywhere else. Writing either into
  // the layer would make it a second copy of the slide a screen below.
  const said = flatten(composeDepthParagraphs(depth, t));
  expect(said).not.toContain("Hut 8");
  expect(said).not.toContain("A section at Bletchley Park");
  expect(said).not.toContain("Joan Clarke");
  expect(said).not.toContain("cryptanalyst in the same section");
  expect(said).not.toContain(en["story.read_more"]);
});

test("nothing to say, nothing said", () => {
  expect(composeDepthParagraphs(null, t)).toEqual([]);
  expect(composeDepthParagraphs({}, t)).toEqual([]);
  expect(
    composeDepthParagraphs({ terms: depth.terms, people: depth.people }, t)
  ).toEqual([]);
});
