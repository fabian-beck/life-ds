/**
 * What the evaluation logs say, computed once and read by both reports.
 *
 * The logger records a flat stream of small events per session (see
 * src/evaluation/logger.js); this module turns that stream into the measures
 * a study asks about — how long a reader stayed, what they opened, how far
 * they got, which controls they used, and how they moved — first per
 * participant and then across participants. Everything here is a pure
 * function of the batches the API returns, so the analysis page renders
 * exactly what these functions say and the logic tests pin their rules.
 *
 * Vocabulary. A *session* is one browser tab. A *view segment* is a stretch
 * of a session spent on one route target (the landing, one person story, one
 * meta story), reconstructed from the route events. A *visit* is a view
 * segment of a story, with everything the reader did inside it attached.
 */

import { parseRoute, viewKey } from "./routes.js";

/**
 * An event as the logger wrote it: a moment, a type, the route it happened
 * on, and whatever small details that type carries.
 * @typedef {{ t: number, type: string, route?: string, [detail: string]: any }} LogEvent
 */

/**
 * @typedef {Object} LogBatch
 * @property {string} participant
 * @property {string} session
 * @property {number} seq
 * @property {LogEvent[]} events
 * @property {string|null} [receivedAt]
 */

/**
 * @typedef {Object} Session
 * @property {string} id
 * @property {string} participant
 * @property {LogEvent[]} events - Enriched and in time order
 * @property {number} batches
 */

// ---------------------------------------------------------------- numbers

/** @param {number[]} values */
export function median(values) {
  return quantile(values, 0.5);
}

/**
 * @param {number[]} values
 * @param {number} p - 0..1
 * @returns {number|null}
 */
export function quantile(values, p) {
  const sorted = values.filter((v) => Number.isFinite(v)).sort((a, b) => a - b);
  if (sorted.length === 0) return null;
  const position = (sorted.length - 1) * p;
  const lower = Math.floor(position);
  const upper = Math.ceil(position);
  const weight = position - lower;
  return sorted[lower] * (1 - weight) + sorted[upper] * weight;
}

/** @param {number[]} values */
export function mean(values) {
  const finite = values.filter((v) => Number.isFinite(v));
  if (finite.length === 0) return null;
  return finite.reduce((a, b) => a + b, 0) / finite.length;
}

function count(map, key, by = 1) {
  map.set(key, (map.get(key) ?? 0) + by);
}

function sortedEntries(map) {
  return [...map.entries()].sort(
    (a, b) => b[1] - a[1] || String(a[0]).localeCompare(String(b[0]))
  );
}

// ---------------------------------------------------------------- sessions

/**
 * Group the batches of one participant into sessions, each with its events in
 * time order, and add the two events the log only implies: the network modal
 * and the expanded timeline are query parameters of the route, so opening
 * either shows up as a route change rather than as an event of its own.
 *
 * @param {LogBatch[]} batches
 * @returns {Session[]}
 */
export function assembleSessions(batches) {
  const bySession = new Map();
  for (const batch of batches) {
    if (!batch || !Array.isArray(batch.events)) continue;
    const list = bySession.get(batch.session) ?? [];
    list.push(batch);
    bySession.set(batch.session, list);
  }
  const sessions = [];
  for (const [id, list] of bySession) {
    list.sort((a, b) => (a.seq ?? 0) - (b.seq ?? 0));
    const events = list
      .flatMap((batch) => batch.events)
      .filter((event) => event && Number.isFinite(event.t) && event.type)
      .sort((a, b) => a.t - b.t);
    sessions.push({
      id,
      participant: list[0].participant,
      events: enrichEvents(events),
      batches: list.length,
    });
  }
  sessions.sort((a, b) => (a.events[0]?.t ?? 0) - (b.events[0]?.t ?? 0));
  return sessions;
}

/**
 * Derive `story.network` and `story.timeline` events from route transitions.
 * @param {LogEvent[]} events
 * @returns {LogEvent[]}
 */
export function enrichEvents(events) {
  const result = [];
  let previous = null;
  for (const event of events) {
    result.push(event);
    if (event.type !== "route") continue;
    const route = parseRoute(event.path, event.query);
    if (
      previous &&
      previous.kind === "story" &&
      route.kind === "story" &&
      previous.id === route.id
    ) {
      if (route.network !== previous.network) {
        result.push({
          t: event.t,
          type: "story.network",
          route: event.route,
          open: route.network,
        });
      }
      if (route.timeline !== previous.timeline) {
        result.push({
          t: event.t,
          type: "story.timeline",
          route: event.route,
          expanded: route.timeline,
        });
      }
    }
    previous = route;
  }
  return result;
}

/**
 * The stretches of a session spent on one view.
 * @param {Session} session
 * @returns {Array<{kind: string, id: string|null, key: string, lang: string|null, start: number, end: number, duration: number, fromMeta: string|null}>}
 */
export function viewSegments(session) {
  const { events } = session;
  if (events.length === 0) return [];
  const end = events[events.length - 1].t;
  const segments = [];
  let current = null;
  for (const event of events) {
    if (event.type !== "route") continue;
    const route = parseRoute(event.path, event.query);
    const key = viewKey(route);
    if (current && current.key === key) continue;
    if (current) {
      current.end = event.t;
      current.duration = current.end - current.start;
    }
    current = {
      kind: route.kind,
      id: route.id,
      key,
      lang: route.lang,
      start: event.t,
      end,
      duration: end - event.t,
      fromMeta: route.fromMeta,
    };
    segments.push(current);
  }
  return segments;
}

function eventsWithin(events, start, end) {
  return events.filter((event) => event.t >= start && event.t <= end);
}

/**
 * The spans a session spent hidden — another tab, a locked phone — so that
 * active time can be told from elapsed time.
 * @param {LogEvent[]} events
 * @returns {number} milliseconds hidden
 */
export function hiddenDuration(events) {
  let hidden = 0;
  let hiddenSince = null;
  for (const event of events) {
    if (event.type !== "session.visibility") continue;
    if (event.hidden && hiddenSince === null) hiddenSince = event.t;
    if (!event.hidden && hiddenSince !== null) {
      hidden += event.t - hiddenSince;
      hiddenSince = null;
    }
  }
  if (hiddenSince !== null && events.length > 0) {
    hidden += events[events.length - 1].t - hiddenSince;
  }
  return hidden;
}

/**
 * @param {Session} session
 */
export function sessionSummary(session) {
  const { events } = session;
  const start = events[0]?.t ?? 0;
  const end = events[events.length - 1]?.t ?? start;
  /** @type {any} */
  const startEvent =
    events.find((event) => event.type === "session.start") ?? {};
  const segments = viewSegments(session);
  const stories = new Set(
    segments.filter((s) => s.kind === "story").map((s) => s.id)
  );
  const metas = new Set(
    segments.filter((s) => s.kind === "meta").map((s) => s.id)
  );
  const languages = new Set(segments.map((s) => s.lang).filter(Boolean));
  return {
    id: session.id,
    participant: session.participant,
    start,
    end,
    duration: end - start,
    activeDuration: end - start - hiddenDuration(events),
    eventCount: events.length,
    batchCount: session.batches,
    resumed: Boolean(startEvent.resumed),
    environment: {
      ua: startEvent.ua ?? null,
      w: startEvent.w ?? null,
      h: startEvent.h ?? null,
      dpr: startEvent.dpr ?? null,
      touch: startEvent.touch ?? null,
      coarse: startEvent.coarse ?? null,
      reducedMotion: startEvent.reducedMotion ?? null,
      lang: startEvent.lang ?? null,
      browserLang: startEvent.browserLang ?? null,
      contrast: startEvent.contrast ?? null,
    },
    languages: [...languages],
    stories: stories.size,
    metas: metas.size,
    errors: events
      .filter((event) => event.type === "error")
      .map((event) => ({
        t: event.t,
        message: event.message ?? "",
        source: event.source ?? null,
      })),
  };
}

// ------------------------------------------------------------ navigation

/**
 * The mechanism behind a slide change, in the handful of classes the report
 * distinguishes. The component names the control that asked; a swipe and a
 * scroll are the same gesture to a reader.
 * @param {string|null|undefined} source
 * @returns {"swipe"|"keyboard"|"arrows"|"timeline"|"image"|"initial"|"link"|"other"}
 */
export function navigationClass(source) {
  switch (source) {
    case "touch":
    case "user-scroll":
      return "swipe";
    case "keyboard":
      return "keyboard";
    case "button":
      return "arrows";
    case "timeline_event":
    case "timeline_chapter":
    case "timeline_scrub":
    case "timeline_scrubber":
      return "timeline";
    case "image-viewer-jump":
      return "image";
    case "initial":
      return "initial";
    case "prop-change":
    case "programmatic":
      return "link";
    default:
      return "other";
  }
}

export const NAVIGATION_CLASSES = [
  { key: "swipe", label: "Swipe or scroll" },
  { key: "arrows", label: "Arrow buttons" },
  { key: "keyboard", label: "Keyboard" },
  { key: "timeline", label: "Timeline" },
  { key: "image", label: "Image gallery" },
  { key: "link", label: "Link or history" },
  { key: "other", label: "Other" },
];

// -------------------------------------------------------------- features

/**
 * The controls the study asks about, each with the event that means it was
 * used. Order is the order the report lists them in.
 */
export const FEATURES = [
  {
    key: "search",
    label: "Search",
    group: "Landing",
    test: (e) => e.type === "landing.search" && Boolean(e.query),
  },
  {
    key: "role_filter",
    label: "Role filter",
    group: "Landing",
    test: (e) => e.type === "landing.filter" && e.active,
  },
  {
    key: "collection_filter",
    label: "Collection filter",
    group: "Landing",
    test: (e) => e.type === "landing.collection_filter" && e.active,
  },
  {
    key: "landing_map",
    label: "Landing map",
    group: "Landing",
    test: (e) => e.type === "landing.map" && e.shown,
  },
  {
    key: "map_marker",
    label: "Map marker to event",
    group: "Landing",
    test: (e) => e.type === "landing.map_select",
  },
  {
    key: "carousel",
    label: "Carousel controls",
    group: "Landing",
    test: (e) => e.type === "landing.carousel",
  },
  {
    key: "language",
    label: "Language switch",
    group: "Landing",
    test: (e) => e.type === "app.language",
  },
  {
    key: "contrast",
    label: "High contrast",
    group: "Landing",
    test: (e) => e.type === "app.contrast" && e.enabled,
  },
  {
    key: "ai_modal",
    label: "AI-generated notice",
    group: "Landing",
    test: (e) => /\.ai_modal$/.test(e.type) && e.open,
  },
  {
    key: "network",
    label: "Network modal",
    group: "Person story",
    test: (e) => e.type === "story.network" && e.open,
  },
  {
    key: "network_person",
    label: "Person in network",
    group: "Person story",
    test: (e) =>
      e.type === "story.person_info" && e.open && e.where === "network",
  },
  {
    key: "timeline_expand",
    label: "Timeline expanded",
    group: "Person story",
    test: (e) => e.type === "story.timeline" && e.expanded,
  },
  {
    key: "timeline_jump",
    label: "Timeline navigation",
    group: "Person story",
    test: (e) =>
      e.type === "story.navigate" && navigationClass(e.source) === "timeline",
  },
  {
    key: "keyboard",
    label: "Keyboard navigation",
    group: "Person story",
    test: (e) =>
      e.type === "story.navigate" && navigationClass(e.source) === "keyboard",
  },
  {
    key: "image",
    label: "Image lightbox",
    group: "Person story",
    test: (e) => e.type === "story.image" && e.action === "open",
  },
  {
    key: "annotation",
    label: "Annotation popup",
    group: "Person story",
    test: (e) => e.type === "story.annotation" && e.open,
  },
  {
    key: "date_note",
    label: "Date note",
    group: "Person story",
    test: (e) => e.type === "story.date_note" && e.open,
  },
  {
    key: "person_chip",
    label: "Person chip",
    group: "Person story",
    test: (e) =>
      e.type === "story.person_info" && e.open && e.where === "slide",
  },
  {
    key: "depth",
    label: "Depth layer",
    group: "Person story",
    test: (e) => e.type === "story.depth" && e.action === "enter",
  },
  {
    key: "meta_timeline",
    label: "Timeline tooltips and years",
    group: "Meta story",
    test: (e) => e.type === "meta.timeline",
  },
  {
    key: "meta_network",
    label: "Network selection",
    group: "Meta story",
    test: (e) => e.type === "meta.network" && e.action === "select",
  },
  {
    key: "meta_map",
    label: "Map narration",
    group: "Meta story",
    test: (e) =>
      e.type === "meta.map" && e.step !== null && e.step !== undefined,
  },
  {
    key: "meta_image",
    label: "Figure lightbox",
    group: "Meta story",
    test: (e) => e.type === "meta.image" && e.action === "open",
  },
  {
    key: "meta_to_story",
    label: "Into a person story",
    group: "Meta story",
    test: (e) => e.type === "meta.open_story",
  },
];

/**
 * @param {LogEvent[]} events
 * @returns {Map<string, number>} feature key → uses
 */
export function featureCounts(events) {
  const counts = new Map();
  for (const feature of FEATURES) counts.set(feature.key, 0);
  for (const event of events) {
    for (const feature of FEATURES) {
      if (feature.test(event)) count(counts, feature.key);
    }
  }
  return counts;
}

// ---------------------------------------------------------------- stories

/**
 * Every visit to a person story in a session, with what happened inside it.
 * @param {Session} session
 */
export function storyVisits(session) {
  const segments = viewSegments(session).filter(
    (segment) => segment.kind === "story"
  );
  return segments.map((segment) => {
    const events = eventsWithin(session.events, segment.start, segment.end);
    const open = events.find((event) => event.type === "story.open");
    const total = open?.slides ?? null;
    const navigations = events.filter(
      (event) => event.type === "story.navigate"
    );
    const slideDwell = [];
    for (let i = 0; i < navigations.length; i += 1) {
      const current = navigations[i];
      const next = navigations[i + 1];
      slideDwell.push({
        index: current.index,
        type: current.slideType ?? null,
        event: current.event ?? null,
        ms: (next ? next.t : segment.end) - current.t,
        source: navigationClass(current.source),
      });
    }
    const visited = new Set(navigations.map((event) => event.index));
    const maxIndex = navigations.length
      ? Math.max(...navigations.map((event) => event.index))
      : null;
    // The first slide of a visit is where the story opened, not a move the
    // reader made, whatever the component called it.
    const navigation = new Map();
    for (const nav of navigations.slice(1)) {
      if (navigationClass(nav.source) === "initial") continue;
      count(navigation, navigationClass(nav.source));
    }
    const depthEntered = events
      .filter(
        (event) => event.type === "story.depth" && event.action === "enter"
      )
      .map((event) => event.event);
    const depthProgress = new Map();
    for (const event of events) {
      if (event.type === "story.depth" && event.action === "leave") {
        depthProgress.set(
          event.event,
          Math.max(depthProgress.get(event.event) ?? 0, event.progress ?? 0)
        );
      }
    }
    const reachedEnd =
      navigations.some((event) => event.slideType === "conclusion") ||
      (total !== null && maxIndex !== null && maxIndex >= total - 1);
    return {
      id: segment.id,
      name: open?.name ?? null,
      start: segment.start,
      end: segment.end,
      duration: segment.duration,
      fromMeta: segment.fromMeta,
      slidesTotal: total,
      slidesVisited: [...visited].sort((a, b) => a - b),
      maxIndex,
      coverage: total ? visited.size / total : null,
      reachedEnd,
      navigation,
      slideDwell,
      depthEntered: [...new Set(depthEntered)],
      depthProgress,
      networkOpens: events.filter(
        (event) => event.type === "story.network" && event.open
      ).length,
      timelineExpands: events.filter(
        (event) => event.type === "story.timeline" && event.expanded
      ).length,
      images: events.filter(
        (event) => event.type === "story.image" && event.action === "open"
      ).length,
      annotations: events.filter(
        (event) => event.type === "story.annotation" && event.open
      ).length,
      dateNotes: events.filter(
        (event) => event.type === "story.date_note" && event.open
      ).length,
      personInfos: events.filter(
        (event) => event.type === "story.person_info" && event.open
      ).length,
      closedVia: events.some((event) => event.type === "story.close")
        ? "button"
        : null,
    };
  });
}

/**
 * Every visit to a meta story in a session.
 * @param {Session} session
 */
export function metaVisits(session) {
  const segments = viewSegments(session).filter(
    (segment) => segment.kind === "meta"
  );
  return segments.map((segment) => {
    const events = eventsWithin(session.events, segment.start, segment.end);
    const scrolls = events.filter((event) => event.type === "meta.scroll");
    const sections = new Set(
      scrolls.map((event) => event.section).filter(Boolean)
    );
    const mapSteps = new Set(
      events
        .filter(
          (event) =>
            event.type === "meta.map" &&
            event.step !== null &&
            event.step !== undefined
        )
        .map((event) => event.step)
    );
    const open = events.find((event) => event.type === "meta.open");
    return {
      id: segment.id,
      title: open?.title ?? null,
      start: segment.start,
      end: segment.end,
      duration: segment.duration,
      maxProgress: scrolls.length
        ? Math.max(...scrolls.map((event) => event.progress ?? 0))
        : 0,
      sections: [...sections],
      timelineActions: events.filter((event) => event.type === "meta.timeline")
        .length,
      networkSelections: events.filter(
        (event) => event.type === "meta.network" && event.action === "select"
      ).length,
      mapSteps: mapSteps.size,
      images: events.filter(
        (event) => event.type === "meta.image" && event.action === "open"
      ).length,
      storiesOpened: events.filter((event) => event.type === "meta.open_story")
        .length,
      closedVia: events.some((event) => event.type === "meta.back")
        ? "button"
        : null,
    };
  });
}

/**
 * What a session did on the landing page.
 * @param {Session} session
 */
export function landingSummary(session) {
  const segments = viewSegments(session);
  const landing = segments.filter((segment) => segment.kind === "landing");
  const events = landing.flatMap((segment) =>
    eventsWithin(session.events, segment.start, segment.end)
  );
  const selections = new Map();
  for (const event of events) {
    if (event.type === "landing.select_person")
      count(selections, event.via ?? "card");
    if (event.type === "landing.map_select") count(selections, "map");
  }
  const firstStory = segments.find(
    (segment) => segment.kind === "story" || segment.kind === "meta"
  );
  const sessionStart = session.events[0]?.t ?? null;
  return {
    duration: landing.reduce((sum, segment) => sum + segment.duration, 0),
    searches: [
      ...new Set(
        events
          .filter((event) => event.type === "landing.search" && event.query)
          .map((event) => event.query)
      ),
    ],
    filterToggles: events.filter(
      (event) => event.type === "landing.filter" && event.active
    ).length,
    collectionFilters: events.filter(
      (event) => event.type === "landing.collection_filter" && event.active
    ).length,
    mapShown: events.filter(
      (event) => event.type === "landing.map" && event.shown
    ).length,
    carouselActions: events.filter((event) => event.type === "landing.carousel")
      .length,
    exploreCollections: events.filter(
      (event) => event.type === "landing.explore_collection"
    ).length,
    selections,
    timeToFirstStory:
      firstStory && sessionStart !== null
        ? firstStory.start - sessionStart
        : null,
  };
}

// ---------------------------------------------------------- participant

function mergeCounts(target, source) {
  for (const [key, value] of source) count(target, key, value);
  return target;
}

/**
 * Everything the per-participant report shows.
 * @param {LogBatch[]} batches
 */
export function participantReport(batches) {
  const sessions = assembleSessions(batches);
  const id = sessions[0]?.participant ?? batches[0]?.participant ?? "";
  const summaries = sessions.map(sessionSummary);
  const events = sessions.flatMap((session) => session.events);
  const segments = sessions.flatMap((session) =>
    viewSegments(session).map((segment) => ({
      ...segment,
      session: session.id,
    }))
  );

  const visits = sessions.flatMap(storyVisits);
  const stories = new Map();
  for (const visit of visits) {
    const story = stories.get(visit.id) ?? {
      id: visit.id,
      name: visit.name,
      visits: 0,
      duration: 0,
      slidesTotal: visit.slidesTotal,
      slidesVisited: new Set(),
      reachedEnd: false,
      depthEntered: new Set(),
      networkOpens: 0,
      timelineExpands: 0,
      images: 0,
      annotations: 0,
      dateNotes: 0,
      personInfos: 0,
      navigation: new Map(),
      slideDwell: new Map(),
      fromMeta: false,
    };
    story.name = story.name ?? visit.name;
    story.visits += 1;
    story.duration += visit.duration;
    story.slidesTotal = story.slidesTotal ?? visit.slidesTotal;
    for (const index of visit.slidesVisited) story.slidesVisited.add(index);
    story.reachedEnd = story.reachedEnd || visit.reachedEnd;
    for (const index of visit.depthEntered) story.depthEntered.add(index);
    story.networkOpens += visit.networkOpens;
    story.timelineExpands += visit.timelineExpands;
    story.images += visit.images;
    story.annotations += visit.annotations;
    story.dateNotes += visit.dateNotes;
    story.personInfos += visit.personInfos;
    mergeCounts(story.navigation, visit.navigation);
    for (const dwell of visit.slideDwell) {
      const entry = story.slideDwell.get(dwell.index) ?? {
        index: dwell.index,
        type: dwell.type,
        event: dwell.event,
        ms: 0,
        visits: 0,
      };
      entry.ms += dwell.ms;
      entry.visits += 1;
      story.slideDwell.set(dwell.index, entry);
    }
    story.fromMeta = story.fromMeta || Boolean(visit.fromMeta);
    stories.set(visit.id, story);
  }
  const storyList = [...stories.values()]
    .map((story) => ({
      ...story,
      slidesVisited: [...story.slidesVisited].sort((a, b) => a - b),
      coverage: story.slidesTotal
        ? story.slidesVisited.size / story.slidesTotal
        : null,
      depthEntered: [...story.depthEntered],
      slideDwell: [...story.slideDwell.values()].sort(
        (a, b) => a.index - b.index
      ),
    }))
    .sort((a, b) => b.duration - a.duration);

  const metaVisitList = sessions.flatMap(metaVisits);
  const metas = new Map();
  for (const visit of metaVisitList) {
    const meta = metas.get(visit.id) ?? {
      id: visit.id,
      title: visit.title,
      visits: 0,
      duration: 0,
      maxProgress: 0,
      sections: new Set(),
      timelineActions: 0,
      networkSelections: 0,
      mapSteps: 0,
      images: 0,
      storiesOpened: 0,
    };
    meta.title = meta.title ?? visit.title;
    meta.visits += 1;
    meta.duration += visit.duration;
    meta.maxProgress = Math.max(meta.maxProgress, visit.maxProgress);
    for (const section of visit.sections) meta.sections.add(section);
    meta.timelineActions += visit.timelineActions;
    meta.networkSelections += visit.networkSelections;
    meta.mapSteps = Math.max(meta.mapSteps, visit.mapSteps);
    meta.images += visit.images;
    meta.storiesOpened += visit.storiesOpened;
    metas.set(visit.id, meta);
  }
  const metaList = [...metas.values()]
    .map((meta) => ({ ...meta, sections: [...meta.sections] }))
    .sort((a, b) => b.duration - a.duration);

  const landings = sessions.map(landingSummary);
  const landing = {
    duration: landings.reduce((sum, item) => sum + item.duration, 0),
    searches: [...new Set(landings.flatMap((item) => item.searches))],
    filterToggles: landings.reduce((sum, item) => sum + item.filterToggles, 0),
    collectionFilters: landings.reduce(
      (sum, item) => sum + item.collectionFilters,
      0
    ),
    mapShown: landings.reduce((sum, item) => sum + item.mapShown, 0),
    carouselActions: landings.reduce(
      (sum, item) => sum + item.carouselActions,
      0
    ),
    exploreCollections: landings.reduce(
      (sum, item) => sum + item.exploreCollections,
      0
    ),
    selections: landings.reduce(
      (map, item) => mergeCounts(map, item.selections),
      new Map()
    ),
    timeToFirstStory: landings[0]?.timeToFirstStory ?? null,
  };

  const navigation = new Map();
  for (const visit of visits) mergeCounts(navigation, visit.navigation);

  const duration = summaries.reduce((sum, s) => sum + s.duration, 0);
  const activeDuration = summaries.reduce(
    (sum, s) => sum + s.activeDuration,
    0
  );
  const clicks = events.filter((event) => event.type === "click").length;
  const keys = events.filter((event) => event.type === "key").length;

  return {
    id,
    sessions: summaries,
    events,
    segments,
    totals: {
      sessions: summaries.length,
      duration,
      activeDuration,
      events: events.length,
      clicks,
      keys,
      stories: storyList.length,
      metas: metaList.length,
      storyDuration: storyList.reduce((sum, story) => sum + story.duration, 0),
      metaDuration: metaList.reduce((sum, meta) => sum + meta.duration, 0),
      landingDuration: landing.duration,
    },
    environment: summaries[0]?.environment ?? {},
    languages: [...new Set(summaries.flatMap((s) => s.languages))],
    stories: storyList,
    visits,
    metas: metaList,
    landing,
    features: featureCounts(events),
    navigation,
    errors: summaries.flatMap((s) => s.errors),
  };
}

// ------------------------------------------------------------- aggregate

/**
 * The share of story visits that reached at least each tenth of the story,
 * from the slide index each visit got to. A drop-off curve.
 * @param {Array<{maxIndex: number|null, slidesTotal: number|null}>} visits
 * @returns {Array<{position: number, share: number}>}
 */
export function dropOffCurve(visits) {
  const usable = visits.filter(
    (visit) => visit.slidesTotal > 1 && visit.maxIndex !== null
  );
  const steps = [];
  for (let tenth = 0; tenth <= 10; tenth += 1) {
    const position = tenth / 10;
    const reached = usable.filter(
      (visit) => visit.maxIndex / (visit.slidesTotal - 1) >= position - 1e-9
    ).length;
    steps.push({
      position,
      share: usable.length ? reached / usable.length : 0,
    });
  }
  return steps;
}

/**
 * Everything the aggregate report shows, from every participant's report.
 * @param {ReturnType<typeof participantReport>[]} reports
 */
export function aggregateReport(reports) {
  const participants = reports.length;
  const sessions = reports.flatMap((report) => report.sessions);
  const visits = reports.flatMap((report) => report.visits);

  const stories = new Map();
  for (const report of reports) {
    for (const story of report.stories) {
      const entry = stories.get(story.id) ?? {
        id: story.id,
        name: story.name,
        readers: 0,
        visits: 0,
        durations: [],
        coverages: [],
        completions: 0,
        depthReaders: 0,
        networkReaders: 0,
        slidesTotal: story.slidesTotal,
      };
      entry.name = entry.name ?? story.name;
      entry.readers += 1;
      entry.visits += story.visits;
      entry.durations.push(story.duration);
      if (story.coverage !== null) entry.coverages.push(story.coverage);
      if (story.reachedEnd) entry.completions += 1;
      if (story.depthEntered.length > 0) entry.depthReaders += 1;
      if (story.networkOpens > 0) entry.networkReaders += 1;
      stories.set(story.id, entry);
    }
  }
  const storyList = [...stories.values()]
    .map((entry) => ({
      ...entry,
      medianDuration: median(entry.durations),
      medianCoverage: median(entry.coverages),
      completionRate: entry.readers ? entry.completions / entry.readers : 0,
    }))
    .sort(
      (a, b) => b.readers - a.readers || b.medianDuration - a.medianDuration
    );

  const metas = new Map();
  for (const report of reports) {
    for (const meta of report.metas) {
      const entry = metas.get(meta.id) ?? {
        id: meta.id,
        title: meta.title,
        readers: 0,
        visits: 0,
        durations: [],
        progresses: [],
        timelineUsers: 0,
        networkUsers: 0,
        mapUsers: 0,
        storiesOpened: 0,
      };
      entry.title = entry.title ?? meta.title;
      entry.readers += 1;
      entry.visits += meta.visits;
      entry.durations.push(meta.duration);
      entry.progresses.push(meta.maxProgress);
      if (meta.timelineActions > 0) entry.timelineUsers += 1;
      if (meta.networkSelections > 0) entry.networkUsers += 1;
      if (meta.mapSteps > 0) entry.mapUsers += 1;
      entry.storiesOpened += meta.storiesOpened;
      metas.set(meta.id, entry);
    }
  }
  const metaList = [...metas.values()]
    .map((entry) => ({
      ...entry,
      medianDuration: median(entry.durations),
      medianProgress: median(entry.progresses),
    }))
    .sort((a, b) => b.readers - a.readers);

  const features = FEATURES.map((feature) => {
    const users = reports.filter(
      (report) => (report.features.get(feature.key) ?? 0) > 0
    ).length;
    const uses = reports.reduce(
      (sum, report) => sum + (report.features.get(feature.key) ?? 0),
      0
    );
    return {
      ...feature,
      users,
      uses,
      share: participants ? users / participants : 0,
    };
  });

  const navigation = new Map();
  for (const report of reports) mergeCounts(navigation, report.navigation);
  const navigationTotal = [...navigation.values()].reduce((a, b) => a + b, 0);

  const slideTypeDwell = new Map();
  for (const visit of visits) {
    for (const dwell of visit.slideDwell) {
      const list = slideTypeDwell.get(dwell.type ?? "unknown") ?? [];
      list.push(dwell.ms);
      slideTypeDwell.set(dwell.type ?? "unknown", list);
    }
  }

  const durations = reports.map((report) => report.totals.duration);
  const activeDurations = reports.map((report) => report.totals.activeDuration);
  const sessionDurations = sessions.map((session) => session.duration);
  const touch = reports.filter(
    (report) => /** @type {any} */ (report.environment).touch === true
  ).length;
  const widths = reports
    .map((report) => /** @type {any} */ (report.environment).w)
    .filter((w) => Number.isFinite(w));
  const languages = new Map();
  for (const report of reports) {
    for (const lang of report.languages) count(languages, lang);
  }
  const timesToFirstStory = reports
    .map((report) => report.landing.timeToFirstStory)
    .filter((v) => v !== null);

  return {
    participants,
    sessions: sessions.length,
    events: reports.reduce((sum, report) => sum + report.totals.events, 0),
    durations,
    activeDurations,
    sessionDurations,
    medianDuration: median(durations),
    medianActiveDuration: median(activeDurations),
    medianSessionDuration: median(sessionDurations),
    touch,
    pointer: participants - touch,
    widths,
    languages: sortedEntries(languages),
    stories: storyList,
    storyVisits: visits.length,
    dropOff: dropOffCurve(visits),
    completionRate: visits.length
      ? visits.filter((visit) => visit.reachedEnd).length / visits.length
      : 0,
    medianCoverage: median(
      visits.map((visit) => visit.coverage).filter((v) => v !== null)
    ),
    medianVisitDuration: median(visits.map((visit) => visit.duration)),
    metas: metaList,
    features,
    navigation: NAVIGATION_CLASSES.map((cls) => ({
      ...cls,
      count: navigation.get(cls.key) ?? 0,
      share: navigationTotal
        ? (navigation.get(cls.key) ?? 0) / navigationTotal
        : 0,
    })).filter((cls) => cls.count > 0),
    navigationTotal,
    slideTypeDwell: [...slideTypeDwell.entries()]
      .map(([type, values]) => ({
        type,
        count: values.length,
        median: median(values),
      }))
      .sort((a, b) => b.count - a.count),
    landing: {
      searchUsers: reports.filter(
        (report) => report.landing.searches.length > 0
      ).length,
      filterUsers: reports.filter(
        (report) =>
          report.landing.filterToggles + report.landing.collectionFilters > 0
      ).length,
      mapUsers: reports.filter((report) => report.landing.mapShown > 0).length,
      medianTimeToFirstStory: median(timesToFirstStory),
      selections: reports.reduce(
        (map, report) => mergeCounts(map, report.landing.selections),
        new Map()
      ),
    },
    errors: reports.flatMap((report) =>
      report.errors.map((error) => ({ ...error, participant: report.id }))
    ),
  };
}

/**
 * Milliseconds as a short duration: "4 min 12 s", "1 h 03 min", "850 ms".
 * @param {number|null|undefined} ms
 * @returns {string}
 */
export function formatDuration(ms) {
  if (ms === null || ms === undefined || !Number.isFinite(ms)) return "—";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const seconds = Math.round(ms / 1000);
  if (seconds < 60) return `${seconds} s`;
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  if (minutes < 60) return rest ? `${minutes} min ${rest} s` : `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  return `${hours} h ${String(minutes % 60).padStart(2, "0")} min`;
}

/**
 * A share as a percentage with no decimals: 0.437 → "44%".
 * @param {number|null|undefined} share
 * @returns {string}
 */
export function formatPercent(share) {
  if (share === null || share === undefined || !Number.isFinite(share))
    return "—";
  return `${Math.round(share * 100)}%`;
}
