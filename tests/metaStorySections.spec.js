import { expect, test } from "@playwright/test";
import { resolveSectionOrder } from "../src/utils/metaStorySections.js";

/* A story with all three components present. The order the composer wrote is
   the only thing that varies between the cases below. */
function story(sectionOrder) {
  return {
    chapters: [{ id: "c1" }],
    social_network: { links: [{ source: "a", target: "b" }] },
    geo_map: { clusters: [{ key: "bamberg" }] },
    ...(sectionOrder ? { section_order: sectionOrder } : {}),
  };
}

test("a story keeps the historical sequence until one is composed", () => {
  expect(resolveSectionOrder(story())).toEqual(["timeline", "network", "map"]);
});

test("the composed order decides which component opens the page", () => {
  expect(resolveSectionOrder(story(["map", "network", "timeline"]))).toEqual([
    "map",
    "network",
    "timeline",
  ]);
});

/* The order is written by a model, so it can name a section twice, name one
   the story has no data for, or forget one. None of those may cost the reader
   a component or render an empty section. */
test("a careless order still renders every section exactly once", () => {
  expect(
    resolveSectionOrder(story(["network", "network", "conclusion"]))
  ).toEqual(["network", "timeline", "map"]);
});

test("a section the story has no data for is never rendered", () => {
  const withoutMap = {
    ...story(["map", "network"]),
    geo_map: { clusters: [] },
  };
  expect(resolveSectionOrder(withoutMap)).toEqual(["network", "timeline"]);
});
