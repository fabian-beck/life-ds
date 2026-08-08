import { test, expect } from "@playwright/test";
import {
  getBackgroundImages,
  getEventDepth,
  hasBackgroundReport,
} from "../src/utils/storyHelpers.js";

/* What the layer under the fold is made of. Everything it says is written by
   the generation pipeline — the report and the pictures chosen for it — so all
   the application decides is which events have a layer to open, and that the
   report never feeds back into which events are worth writing one for. */

const commons = (name) =>
  `https://upload.wikimedia.org/wikipedia/commons/${name}`;

test("the pictures chosen for the report are the ones it is illustrated with", () => {
  const event = {
    background_images: [
      { url: commons("bombe.jpg"), caption: "A rebuilt bombe" },
      { url: commons("hut8.jpg"), caption: "Hut 8" },
    ],
    images: [{ url: commons("portrait.jpg"), caption: "The event's own" }],
  };
  expect(getBackgroundImages(event).map((image) => image.caption)).toEqual([
    "A rebuilt bombe",
    "Hut 8",
  ]);
});

/* The event's own picture is a screen up, and the reader scrolled past it to
   get here. Reprinting it under the report is what made the layer read as a
   second copy of the slide, so a report with no illustrations of its own is
   set as plain prose. */
test("the event's own picture is not printed again under the report", () => {
  const event = {
    images: [{ url: commons("portrait.jpg"), caption: "On the slide" }],
  };
  expect(getBackgroundImages(event)).toEqual([]);
});

test("nothing to show, nothing shown", () => {
  expect(getBackgroundImages(null)).toEqual([]);
  expect(getBackgroundImages({})).toEqual([]);
  expect(
    getBackgroundImages({ background_images: [{ caption: "no url" }] })
  ).toEqual([]);
});

/* The counts below decide which events are offered a layer. The report is
   generated for the events that already are, so counting it would make the
   selection drift every time the corpus fills in a passage. */
test("the report and its pictures are carried, and left out of the counts", () => {
  const bare = {
    locations: [{ name_historic: "Bletchley", name_modern: "Milton Keynes" }],
    sources: ["https://en.wikipedia.org/wiki/Hut_8"],
  };
  const withReport = {
    ...bare,
    background: "Two paragraphs of it.\n\nAnd the second.",
    background_images: [{ url: commons("bombe.jpg") }],
  };

  const plain = getEventDepth(bare, null);
  const reported = getEventDepth(withReport, null);

  expect(plain.background).toBeNull();
  expect(reported.background).toContain("And the second.");
  expect(reported.illustrations).toHaveLength(1);
  expect(reported.itemCount).toBe(plain.itemCount);
  expect(reported.sectionCount).toBe(plain.sectionCount);
});

/* The layer is the report and nothing else, so a landmark whose report has not
   been written yet must not advertise a second screen and then show an empty
   one. The corpus fills in one life at a time. */
test("only an event with a report has a layer to open", () => {
  expect(hasBackgroundReport({ background: "A chapter of it." })).toBe(true);
  expect(hasBackgroundReport({ background: "   " })).toBe(false);
  expect(hasBackgroundReport({ background: null })).toBe(false);
  expect(hasBackgroundReport({ images: [{ url: commons("a.jpg") }] })).toBe(
    false
  );
  expect(hasBackgroundReport(null)).toBe(false);
});
