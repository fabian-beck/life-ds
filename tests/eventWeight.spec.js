import { test, expect } from "@playwright/test";
import {
  DEEP_EVENT_FLOOR,
  getEventDepth,
  getEventWeight,
  selectDeepEventIndexes,
} from "../src/utils/story/eventDepth.js";

const network = {
  connections: [
    {
      person_name: "Joan Clarke",
      relationship_type: "professional/colleague",
      relationship_description: "Cryptanalyst in the same section",
      strength: "strong",
    },
  ],
};

function event(overrides = {}) {
  return {
    title: "An event",
    description: "Something happened.",
    chapter: "one",
    ...overrides,
  };
}

test("a weight the pipeline wrote is the weight, not a hint", () => {
  // Phase 1 sees a life whole and weighs its events against each other. The
  // derived score below never overrides that, however the event is documented.
  const weighed = event({ weight: 0.92, event_type_icon: "mdi-briefcase" });
  expect(getEventWeight(weighed)).toBeCloseTo(0.92, 5);
  // A ceremony the sources dwell on still ranks where the biographer put it.
  const decorated = event({
    weight: 0.1,
    event_class: { type: "publication" },
    images: [{ url: "https://example.org/a.jpg" }],
    involved_people: ["A", "B", "C"],
    sources: ["https://example.org/a", "https://example.org/b"],
    description: "x".repeat(400),
  });
  expect(getEventWeight(decorated)).toBeCloseTo(0.1, 5);
});

test("a weight out of range is brought back into it", () => {
  expect(getEventWeight(event({ weight: 4 }))).toBe(1);
  expect(getEventWeight(event({ weight: -1 }))).toBe(0);
  // Not a number: the derived fallback answers instead of NaN.
  expect(getEventWeight(event({ weight: null }))).toBe(0);
  expect(getEventWeight(event({ weight: "high" }))).toBe(0);
});

test("a bare event carries almost no weight", () => {
  expect(getEventWeight(event())).toBeLessThan(DEEP_EVENT_FLOOR);
  expect(getEventWeight(null)).toBe(0);
});

test("a classification outweighs a milestone icon, and they do not stack", () => {
  const classified = getEventWeight(
    event({ event_class: { type: "publication" }, event_type_icon: "mdi-book" })
  );
  const iconOnly = getEventWeight(event({ event_type_icon: "mdi-book" }));
  expect(classified).toBeGreaterThan(iconOnly);
  // The icon's own contribution is not added on top of the classification's.
  expect(classified).toBeCloseTo(0.3, 5);
  expect(iconOnly).toBeCloseTo(0.2, 5);
});

test("an icon for an ordinary step of a career counts for nothing", () => {
  expect(getEventWeight(event({ event_type_icon: "mdi-briefcase" }))).toBe(0);
  expect(getEventWeight(event({ event_type_icon: "mdi-school" }))).toBe(0);
});

test("the traces of a documented event add up", () => {
  const documented = event({
    event_type_icon: "mdi-file-document",
    annotations: {
      "Hut 8": { explanation: "A section at Bletchley Park." },
      Enigma: { explanation: "A family of cipher machines." },
    },
    images: [{ url: "https://example.org/hut8.jpg", caption: "Hut 8" }],
    involved_people: ["Joan Clarke"],
    sources: ["https://example.org/a", "https://example.org/b"],
    description: "x".repeat(400),
  });
  expect(getEventWeight(documented)).toBeGreaterThan(DEEP_EVENT_FLOOR);
  expect(getEventWeight(documented)).toBeLessThanOrEqual(1);
});

test("the depth material is what the fold keeps a tap away or leaves out", () => {
  const depth = getEventDepth(
    event({
      locations: [
        {
          name_historic: "Bletchley",
          name_modern: "Bletchley, Milton Keynes, UK",
          primary: true,
        },
      ],
      annotations: {
        Enigma: {
          explanation: "A family of cipher machines.",
          wikipedia_url: "https://en.wikipedia.org/wiki/Enigma_machine",
        },
        Undocumented: {},
      },
      images: [
        { url: "https://example.org/a.jpg", caption: "A caption" },
        { url: "https://example.org/b.jpg" },
      ],
      involved_people: ["Joan Clarke"],
      sources: ["https://example.org/a"],
    }),
    network
  );

  expect(depth.places).toEqual([
    {
      historic: "Bletchley",
      modern: "Bletchley, Milton Keynes, UK",
      primary: true,
    },
  ]);
  // An annotation the generator left without an explanation carries nothing.
  expect(depth.terms.map((term) => term.term)).toEqual(["Enigma"]);
  // Neither does a picture with no caption and no credit to print.
  expect(depth.images).toHaveLength(1);
  expect(depth.people.map((person) => person.person_name)).toEqual([
    "Joan Clarke",
  ]);
  expect(depth.sectionCount).toBe(5);
  expect(depth.itemCount).toBe(5);
});

test("an event with nothing behind it offers no depth", () => {
  const depth = getEventDepth(event({ sources: ["https://example.org/a"] }), {
    connections: [],
  });
  expect(depth.sectionCount).toBe(1);
  expect(depth.itemCount).toBe(1);
});

const heavy = (chapter, title, extra = {}) =>
  event({
    chapter,
    title,
    event_type_icon: "mdi-file-document",
    annotations: {
      One: { explanation: "First." },
      Two: { explanation: "Second." },
    },
    images: [{ url: "https://example.org/i.jpg", caption: "A picture" }],
    sources: ["https://example.org/a", "https://example.org/b"],
    description: "x".repeat(400),
    locations: [{ name_historic: "Here", name_modern: "There" }],
    ...extra,
  });

test("each chapter offers its heaviest event and no more", () => {
  const events = [
    heavy("one", "Lighter", { description: "x".repeat(100) }),
    heavy("one", "Heaviest", { involved_people: ["Joan Clarke"] }),
    heavy("two", "Only one here"),
    event({ chapter: "three", title: "Nothing to show" }),
  ];

  const deep = selectDeepEventIndexes(events, network);
  expect([...deep].sort()).toEqual([1, 2]);
});

test("a chapter whose best event stays under the floor offers none", () => {
  const events = [
    event({
      chapter: "one",
      title: "Thin",
      sources: ["https://example.org/a"],
    }),
    event({ chapter: "one", title: "Also thin" }),
  ];
  expect(selectDeepEventIndexes(events, network).size).toBe(0);
});

test("an event without the material to fill a depth layer is passed over", () => {
  // Weight enough to clear the floor twice over, but a bare place and one
  // source is not a page worth scrolling to.
  const events = [
    event({
      chapter: "one",
      title: "Weighty but bare",
      event_class: { type: "publication" },
      description: "x".repeat(400),
      date_end: "1950",
      sources: ["https://example.org/a"],
    }),
  ];
  expect(getEventWeight(events[0])).toBeGreaterThan(DEEP_EVENT_FLOOR);
  expect(selectDeepEventIndexes(events, network).size).toBe(0);
});

test("no events, no deep events", () => {
  expect(selectDeepEventIndexes([], network).size).toBe(0);
  expect(selectDeepEventIndexes(null, network).size).toBe(0);
});
