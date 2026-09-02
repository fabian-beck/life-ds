import { expect, test } from "@playwright/test";
import {
  aggregateReport,
  assembleSessions,
  dropOffCurve,
  enrichEvents,
  featureCounts,
  formatDuration,
  hiddenDuration,
  median,
  navigationClass,
  participantReport,
  sessionSummary,
  storyVisits,
  viewSegments,
} from "../src/utils/evaluation/analysis.js";

/* A session as the logger would have written it, in two batches that arrive
   out of order: a landing, a search, a story read part way with the network
   opened, a spell in another tab, and a meta story scrolled half way. Times
   are seconds from an arbitrary start, so the durations below are legible. */
const T0 = 1_700_000_000_000;
const at = (seconds) => T0 + seconds * 1000;

function event(seconds, type, data = {}) {
  return { ...data, t: at(seconds), type };
}

const sessionEvents = [
  event(0, "session.start", {
    participant: "P1",
    session: "s-1",
    ua: "Mozilla/5.0 Chrome/1",
    w: 390,
    h: 844,
    touch: true,
    lang: "en",
  }),
  event(0, "route", { path: "/en", query: "" }),
  event(5, "landing.search", { query: "ada" }),
  event(8, "click", {
    tag: "button",
    label: "Open the life story of Ada Lovelace",
  }),
  event(8, "landing.select_person", { id: "ada_lovelace", via: "card" }),
  event(8, "route", {
    path: "/en/story/ada_lovelace",
    query: "from_landing=q%3Dada",
  }),
  event(9, "story.open", {
    name: "Ada Lovelace",
    slides: 10,
    events: 7,
    deep: 2,
  }),
  event(9, "story.navigate", {
    index: 0,
    slideType: "overview",
    event: -1,
    source: "initial",
    total: 10,
  }),
  event(20, "story.navigate", {
    index: 1,
    slideType: "chapter",
    event: null,
    source: "touch",
    total: 10,
  }),
  event(25, "route", {
    path: "/en/story/ada_lovelace",
    query: "slide=1&from_landing=q%3Dada",
  }),
  event(30, "story.navigate", {
    index: 2,
    slideType: "event",
    event: 0,
    source: "user-scroll",
    total: 10,
  }),
  event(30, "route", {
    path: "/en/story/ada_lovelace",
    query: "slide=2&from_landing=q%3Dada",
  }),
  event(40, "route", {
    path: "/en/story/ada_lovelace",
    query: "slide=2&network=1&from_landing=q%3Dada",
  }),
  event(41, "story.person_info", { key: "x", open: true, where: "network" }),
  event(50, "route", {
    path: "/en/story/ada_lovelace",
    query: "slide=2&from_landing=q%3Dada",
  }),
  event(60, "story.depth", { action: "enter", index: 2, event: 0 }),
  event(70, "session.visibility", { hidden: true }),
  event(100, "session.visibility", { hidden: false }),
  event(110, "story.navigate", {
    index: 5,
    slideType: "event",
    event: 3,
    source: "timeline_event",
    total: 10,
  }),
  event(110, "story.depth", {
    action: "leave",
    index: 2,
    event: 0,
    progress: 0.8,
  }),
  event(120, "story.close", { via: "button" }),
  event(120, "route", { path: "/en", query: "q=ada" }),
  event(130, "route", { path: "/en/meta/computing_pioneers", query: "" }),
  event(131, "meta.open", {
    id: "computing_pioneers",
    title: "Beyond the Box",
  }),
  event(140, "meta.scroll", { progress: 0.2, section: "chapters" }),
  event(150, "meta.scroll", { progress: 0.5, section: "network" }),
  event(155, "meta.network", { action: "select", id: "alan_turing" }),
  event(160, "session.end"),
];

const batches = [
  {
    participant: "P1",
    session: "s-1",
    seq: 1,
    events: sessionEvents.slice(12),
  },
  {
    participant: "P1",
    session: "s-1",
    seq: 0,
    events: sessionEvents.slice(0, 12),
  },
];

test("batches assemble into one session in time order", () => {
  const sessions = assembleSessions(batches);
  expect(sessions).toHaveLength(1);
  const times = sessions[0].events.map((e) => e.t);
  expect([...times].sort((a, b) => a - b)).toEqual(times);
  expect(sessions[0].batches).toBe(2);
});

test("opening the network is read out of the route", () => {
  const enriched = enrichEvents(sessionEvents);
  const network = enriched.filter((e) => e.type === "story.network");
  expect(network.map((e) => e.open)).toEqual([true, false]);
  expect(network[0].t).toBe(at(40));
});

test("a session's elapsed time leaves hidden spells out of active time", () => {
  const [session] = assembleSessions(batches);
  expect(hiddenDuration(session.events)).toBe(30_000);
  const summary = sessionSummary(session);
  expect(summary.duration).toBe(160_000);
  expect(summary.activeDuration).toBe(130_000);
  expect(summary.environment.touch).toBe(true);
  expect(summary.stories).toBe(1);
  expect(summary.metas).toBe(1);
});

test("view segments follow the route, merging a story's own slide changes", () => {
  const [session] = assembleSessions(batches);
  const segments = viewSegments(session);
  expect(segments.map((s) => s.key)).toEqual([
    "landing",
    "story:ada_lovelace",
    "landing",
    "meta:computing_pioneers",
  ]);
  expect(segments[1].duration).toBe(112_000);
  expect(segments[3].end).toBe(at(160));
});

test("a story visit knows its coverage, its depth, and how it was navigated", () => {
  const [session] = assembleSessions(batches);
  const [visit] = storyVisits(session);
  expect(visit.id).toBe("ada_lovelace");
  expect(visit.slidesTotal).toBe(10);
  expect(visit.slidesVisited).toEqual([0, 1, 2, 5]);
  expect(visit.coverage).toBeCloseTo(0.4);
  expect(visit.reachedEnd).toBe(false);
  expect(visit.networkOpens).toBe(1);
  expect(visit.depthEntered).toEqual([0]);
  expect(visit.depthProgress.get(0)).toBe(0.8);
  expect(Object.fromEntries(visit.navigation)).toEqual({
    swipe: 2,
    timeline: 1,
  });
  // Slide 2 held the reader from second 30 to second 110.
  const slideTwo = visit.slideDwell.find((d) => d.index === 2);
  expect(slideTwo.ms).toBe(80_000);
  expect(visit.closedVia).toBe("button");
});

test("navigation sources fold into the classes a reader would name", () => {
  expect(navigationClass("touch")).toBe("swipe");
  expect(navigationClass("user-scroll")).toBe("swipe");
  expect(navigationClass("timeline_scrub")).toBe("timeline");
  expect(navigationClass("button")).toBe("arrows");
  expect(navigationClass("prop-change")).toBe("link");
  expect(navigationClass(undefined)).toBe("other");
});

test("feature counts see the search, the network, the depth layer, and the meta network", () => {
  const [session] = assembleSessions(batches);
  const counts = featureCounts(session.events);
  expect(counts.get("search")).toBe(1);
  expect(counts.get("network")).toBe(1);
  expect(counts.get("network_person")).toBe(1);
  expect(counts.get("depth")).toBe(1);
  expect(counts.get("timeline_jump")).toBe(1);
  expect(counts.get("meta_network")).toBe(1);
  expect(counts.get("image")).toBe(0);
});

test("the participant report sums the session and names what was read", () => {
  const report = participantReport(batches);
  expect(report.id).toBe("P1");
  expect(report.totals.sessions).toBe(1);
  expect(report.totals.duration).toBe(160_000);
  expect(report.stories[0]).toMatchObject({
    id: "ada_lovelace",
    name: "Ada Lovelace",
    visits: 1,
    coverage: 0.4,
  });
  expect(report.metas[0]).toMatchObject({
    id: "computing_pioneers",
    title: "Beyond the Box",
    maxProgress: 0.5,
  });
  expect(report.metas[0].sections).toEqual(["chapters", "network"]);
  expect(report.landing.searches).toEqual(["ada"]);
  expect(report.landing.timeToFirstStory).toBe(8_000);
  expect(report.landing.selections.get("card")).toBe(1);
});

test("the aggregate reads adoption and drop-off across participants", () => {
  const second = [
    {
      participant: "P2",
      session: "s-2",
      seq: 0,
      events: [
        event(0, "session.start", {
          participant: "P2",
          session: "s-2",
          touch: false,
          w: 1440,
        }),
        event(0, "route", { path: "/de", query: "" }),
        event(10, "route", { path: "/de/story/ada_lovelace", query: "" }),
        event(11, "story.open", {
          name: "Ada Lovelace",
          slides: 10,
          events: 7,
          deep: 2,
        }),
        event(11, "story.navigate", {
          index: 0,
          slideType: "overview",
          source: "initial",
          total: 10,
        }),
        event(20, "story.navigate", {
          index: 9,
          slideType: "conclusion",
          source: "keyboard",
          total: 10,
        }),
        event(30, "session.end"),
      ],
    },
  ];
  const reports = [participantReport(batches), participantReport(second)];
  const aggregate = aggregateReport(reports);
  expect(aggregate.participants).toBe(2);
  expect(aggregate.touch).toBe(1);
  expect(aggregate.pointer).toBe(1);
  expect(aggregate.stories[0]).toMatchObject({
    id: "ada_lovelace",
    readers: 2,
    completions: 1,
  });
  expect(aggregate.completionRate).toBe(0.5);
  const search = aggregate.features.find((f) => f.key === "search");
  expect(search.users).toBe(1);
  expect(search.share).toBe(0.5);
  expect(aggregate.navigation.map((n) => n.key)).toEqual([
    "swipe",
    "keyboard",
    "timeline",
  ]);
  // One visit stopped at slide 5 of 10, the other reached the end.
  const curve = dropOffCurve(
    aggregate.stories.length ? reports.flatMap((r) => r.visits) : []
  );
  expect(curve[0].share).toBe(1);
  expect(curve[5].share).toBe(1);
  expect(curve[6].share).toBe(0.5);
  expect(curve[10].share).toBe(0.5);
  expect(aggregate.languages).toEqual([
    ["de", 1],
    ["en", 1],
  ]);
});

test("numbers read as durations, and a median of nothing is nothing", () => {
  expect(formatDuration(850)).toBe("850 ms");
  expect(formatDuration(59_000)).toBe("59 s");
  expect(formatDuration(252_000)).toBe("4 min 12 s");
  expect(formatDuration(3_780_000)).toBe("1 h 03 min");
  expect(formatDuration(null)).toBe("—");
  expect(median([])).toBe(null);
  expect(median([3, 1, 2])).toBe(2);
  expect(median([1, 2, 3, 4])).toBe(2.5);
});
