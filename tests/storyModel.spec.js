import { test, expect } from "@playwright/test";
import {
  buildSlides,
  eventToSlideIndex,
  rawEventToSlideIndex,
  slideToEventIndex,
} from "../src/utils/story/storyModel.js";
import { relatedPersonsByRole } from "../src/utils/story/personMatching.js";

// The slide list decides what StoryView's `activeIndex` is an index into, and
// three maps translate between that index, the event a slide shows, and the
// position that event has in the stored dataset. Deep links, timeline jumps
// and meta-story links each rely on a different one of the three, so they are
// pinned separately.

const event = (id, chapter) => ({ id, ...(chapter ? { chapter } : {}) });
const types = (slides) => slides.map((slide) => slide.type);

test("a story is an overview and its events", () => {
  expect(types(buildSlides({ events: [event("a"), event("b")] }))).toEqual([
    "overview",
    "event",
    "event",
  ]);
});

test("a chapter slide precedes the first event of its chapter", () => {
  const slides = buildSlides({
    events: [event("a", "early"), event("b", "early"), event("c", "late")],
    chapters: [{ id: "early" }, { id: "late" }],
  });
  expect(types(slides)).toEqual([
    "overview",
    "chapter",
    "event",
    "event",
    "chapter",
    "event",
  ]);
  expect(slides[1].chapterIndex).toBe(0);
  expect(slides[1].eventIndex).toBe(0);
  expect(slides[4].eventIndex).toBe(2);
});

test("an event naming a chapter that does not exist gets no chapter slide", () => {
  const slides = buildSlides({
    events: [event("a", "ghost")],
    chapters: [{ id: "early" }],
  });
  expect(types(slides)).toEqual(["overview", "event"]);
});

test("a conclusion closes the story, and so does a list of related people", () => {
  expect(
    types(buildSlides({ events: [event("a")], conclusion: "He endured." }))
  ).toEqual(["overview", "event", "conclusion"]);
  expect(
    types(buildSlides({ events: [event("a")], relatedPersons: [{ id: "x" }] }))
  ).toEqual(["overview", "event", "conclusion"]);
  expect(types(buildSlides({ events: [event("a")] }))).toEqual([
    "overview",
    "event",
  ]);
});

test("a story with no events is still a story when it has a conclusion", () => {
  expect(types(buildSlides({ events: [], conclusion: "A life." }))).toEqual([
    "overview",
    "conclusion",
  ]);
  expect(types(buildSlides({ events: [] }))).toEqual(["overview"]);
  expect(types(buildSlides())).toEqual(["overview"]);
});

test("the overview sits before the first event, at event index -1", () => {
  // Not `null`: the timeline has to be able to point at the overview, which a
  // slide showing no event (a chapter, the conclusion) is not.
  const slides = buildSlides({
    events: [event("a", "early")],
    chapters: [{ id: "early" }],
    conclusion: "Done.",
  });
  const map = slideToEventIndex(slides);
  expect([...map.values()]).toEqual([-1, null, 0, null]);
});

test("event indices skip the slides that show no event", () => {
  const slides = buildSlides({
    events: [event("a", "early"), event("b", "late")],
    chapters: [{ id: "early" }, { id: "late" }],
  });
  expect([...slideToEventIndex(slides).values()]).toEqual([
    -1,
    null,
    0,
    null,
    1,
  ]);
  expect([...eventToSlideIndex(slides).entries()]).toEqual([
    [0, 2],
    [1, 4],
  ]);
});

test("the raw index is the one external links address events by", () => {
  // A LandingMap marker and a meta story's `event_index` are generated from
  // the stored events array, which the story's chronological sort reorders —
  // so the map is keyed by where the event *was*, not where it now shows.
  const slides = buildSlides({
    events: [
      { id: "later-in-file-but-earlier", rawIndex: 2 },
      { id: "first-in-file", rawIndex: 0 },
    ],
  });
  expect([...rawEventToSlideIndex(slides).entries()]).toEqual([
    [2, 1],
    [0, 2],
  ]);
});

test("an event without a raw index is simply not addressable that way", () => {
  const slides = buildSlides({ events: [{ id: "a" }] });
  expect(rawEventToSlideIndex(slides).size).toBe(0);
});

// --- related people ------------------------------------------------------

const registry = {
  people: [
    { id: "subject", name: "Ada Lovelace", primaryRoles: ["mathematician"] },
    { id: "peer", name: "Charles Babbage", primaryRoles: ["mathematician"] },
    { id: "two", name: "Emmy Noether", primaryRoles: ["mathematician"] },
    { id: "other", name: "Zaha Hadid", primaryRoles: ["architect"] },
  ],
};
const subject = { name: "Ada Lovelace", primary_roles: ["Mathematician"] };

test("only people who share a role are offered", () => {
  const related = relatedPersonsByRole({ person: subject, registry });
  expect(related.map((r) => r.person.id)).toEqual(["peer", "two"]);
});

test("being in the story's network is worth one shared role", () => {
  const related = relatedPersonsByRole({
    person: subject,
    registry,
    egoNetwork: { connections: [{ person_name: "Charles Babbage" }] },
  });
  expect(related[0].person.id).toBe("peer");
  expect(related[0].score).toBeGreaterThan(related[1].score);
});

test("the subject is never related to itself", () => {
  const related = relatedPersonsByRole({ person: subject, registry });
  expect(related.map((r) => r.person.id)).not.toContain("subject");
});

test("a subject the registry does not know produces nothing", () => {
  expect(
    relatedPersonsByRole({
      person: { name: "Nobody", primary_roles: ["mathematician"] },
      registry,
    })
  ).toEqual([]);
  expect(relatedPersonsByRole({ person: subject, registry: null })).toEqual([]);
  expect(relatedPersonsByRole()).toEqual([]);
});

test("a subject with no roles matches nobody", () => {
  expect(
    relatedPersonsByRole({
      person: { name: "Ada Lovelace", primary_roles: [] },
      registry,
    })
  ).toEqual([]);
});
