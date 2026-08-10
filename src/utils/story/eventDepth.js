/**
 * Event weighting and the depth layer: how much of a life an event turns on,
 * and which events carry enough material for a fold beneath the slide.
 */
import { getBackgroundImages, getValidImages } from "./images.js";
import { getRelevantPeople } from "./personMatching.js";

// Icons that name a kind of event a life is remembered for — a work, a
// discovery, an honor. The datasets classify only five kinds of event in
// `event_class`, and a landmark often falls outside all of them (Turing's two
// famous papers carry no classification at all), so the icon is the one
// vocabulary that separates "published the paper" from "took up a post". Kinds
// that recur in every academic life — schooling, degrees, appointments — are
// deliberately absent: they say what happened, not that it mattered.
const MILESTONE_ICONS = new Set([
  "mdi-book",
  "mdi-book-open-variant",
  "mdi-file-document",
  "mdi-file-document-edit",
  "mdi-newspaper",
  "mdi-lightbulb-on-outline",
  "mdi-microscope",
  "mdi-test-tube",
  "mdi-palette",
  "mdi-drawing",
  "mdi-cube",
  "mdi-music-note",
  "mdi-medal",
  "mdi-trophy",
  "mdi-crown",
  "mdi-shield-crown",
  "mdi-star",
  "mdi-seal",
  "mdi-gavel",
  "mdi-office-building",
  "mdi-castle",
]);
// The classifications, by how much of a life they turn on.
const CLASS_WEIGHTS = {
  birth: 0.3,
  death: 0.3,
  invention: 0.3,
  publication: 0.3,
  marriage_partnership: 0.25,
  migration: 0.15,
};
/**
 * How much of a life an event turns on, on a 0–1 scale.
 *
 * The datasets carry the number: Phase 1 proposes a life's events and weighs
 * them against each other in the same call, which is the only place in the
 * pipeline that sees them all at once. That is what makes the judgment
 * possible at all — weight here is comparative, not absolute.
 *
 * What follows is the fallback for a dataset generated before the field
 * existed, and it is a weaker thing: it reads the traces an important event
 * leaves behind — a classification, a milestone icon, a picture, annotations,
 * people, length — which is to say it reads the documentation rather than the
 * life. It ranks a well-attended ceremony above a quiet paper that founded a
 * field. Backfilling the weights is what fixes that; see
 * `scripts/backfill_event_weights.py`.
 * @param {Object} event - Event object
 * @returns {number} Weight between 0 and 1
 */
export function getEventWeight(event) {
  if (!event) return 0;

  if (Number.isFinite(event.weight)) {
    return Math.min(Math.max(event.weight, 0), 1);
  }

  let weight = 0;

  const classWeight = CLASS_WEIGHTS[event.event_class?.type];
  if (classWeight) {
    weight += classWeight;
  } else if (MILESTONE_ICONS.has(event.event_type_icon)) {
    // A classification already says the event is one of the recognized kinds;
    // the icon is what is left to go on when it does not.
    weight += 0.2;
  }

  const annotationCount = Object.keys(event.annotations ?? {}).length;
  weight += Math.min(annotationCount, 3) * 0.08;

  if (getValidImages(event.images).length > 0) weight += 0.12;

  const peopleCount = Array.isArray(event.involved_people)
    ? event.involved_people.length
    : 0;
  weight += Math.min(peopleCount, 3) * 0.05;

  const sourceCount = Array.isArray(event.sources) ? event.sources.length : 0;
  weight += Math.min(Math.max(sourceCount - 1, 0), 2) * 0.05;

  const length =
    typeof event.description === "string" ? event.description.length : 0;
  if (length >= 380) weight += 0.1;
  else if (length >= 300) weight += 0.05;

  // An event the sources place across a span, rather than on a day, tends to
  // be one they treat as an episode.
  if (event.date_end) weight += 0.05;

  return Math.min(weight, 1);
}
/**
 * The material a depth layer would have to show for one event: the place under
 * both its names, the terms its description leans on, the pictures with their
 * credits, the people who were there, and where all of it was read.
 *
 * Every part of this is already in the dataset. What the fold shows of it is a
 * tap away at most — an annotation behind its term, a credit behind the
 * lightbox — and the place and the sources are not on the slide at all.
 * @param {Object} event - Event object
 * @param {Object} egoNetwork - Ego network with connections array
 * @returns {Object} {background, places, terms, images, people, sources, itemCount, sectionCount}
 */
export function getEventDepth(event, egoNetwork) {
  const places = Array.isArray(event?.locations)
    ? event.locations
        .filter((location) => location?.name_historic || location?.name_modern)
        .map((location) => ({
          historic: location.name_historic ?? null,
          modern: location.name_modern ?? null,
          primary: location.primary === true,
        }))
    : [];

  const terms = Object.entries(event?.annotations ?? {})
    .filter(([, annotation]) => !!annotation?.explanation)
    .map(([term, annotation]) => ({
      term,
      explanation: annotation.explanation,
      wikipediaUrl: annotation.wikipedia_url ?? null,
    }));

  const images = getValidImages(event?.images)
    .map((imageData) =>
      typeof imageData === "string" ? { url: imageData } : imageData
    )
    .filter((image) => image.caption || image.creator || image.source);

  const people = getRelevantPeople(event, egoNetwork);

  const sources = Array.isArray(event?.sources)
    ? event.sources.filter((url) => typeof url === "string" && url.length > 0)
    : [];

  // The passage Phase 2 wrote for this event, where there is one. It is
  // deliberately left out of the counts below: those decide which events offer
  // a depth layer at all, the passages are generated for the events that do,
  // and letting one feed the other would make the selection drift as the
  // corpus fills in.
  const background =
    typeof event?.background === "string" ? event.background : null;
  const illustrations = getBackgroundImages(event);

  const sections = [places, terms, images, people, sources];
  return {
    background,
    illustrations,
    places,
    terms,
    images,
    people,
    sources,
    itemCount: sections.reduce((total, section) => total + section.length, 0),
    sectionCount: sections.filter((section) => section.length > 0).length,
  };
}
// A weight below this is not a highlight in any life, however its neighbors
// score. Without a floor a thin chapter would still nominate its best event.
export const DEEP_EVENT_FLOOR = 0.35;
// Below this there is not enough behind the fold to be worth the trip down.
const MIN_DEPTH_SECTIONS = 2;
const MIN_DEPTH_ITEMS = 3;
/**
 * Which events of one life open a depth layer.
 *
 * Weight alone would cluster the highlights wherever a life is best
 * documented, so the selection is made per chapter: each chapter offers its
 * heaviest event and no more, which spreads the deep slides across the story
 * the way a comic spreads its big panels across a chapter. An event that has
 * too little behind the fold is passed over for the next one down, and a
 * chapter whose best event never clears the floor simply offers none.
 * @param {Array} events - Event objects in story order
 * @param {Object} egoNetwork - Ego network with connections array
 * @returns {Set<number>} Indexes into `events`
 */
export function selectDeepEventIndexes(events, egoNetwork) {
  if (!Array.isArray(events) || events.length === 0) return new Set();

  const candidates = events
    .map((event, index) => ({
      index,
      chapter: event?.chapter ?? "",
      weight: getEventWeight(event),
      depth: getEventDepth(event, egoNetwork),
    }))
    .filter(
      (candidate) =>
        candidate.weight >= DEEP_EVENT_FLOOR &&
        candidate.depth.sectionCount >= MIN_DEPTH_SECTIONS &&
        candidate.depth.itemCount >= MIN_DEPTH_ITEMS
    );

  const best = new Map();
  for (const candidate of candidates) {
    const held = best.get(candidate.chapter);
    // Ties go to the earlier event: a chapter's first landmark is the one the
    // reader meets while the chapter is still being established.
    if (!held || candidate.weight > held.weight) {
      best.set(candidate.chapter, candidate);
    }
  }

  return new Set([...best.values()].map((candidate) => candidate.index));
}
/**
 * Whether an event actually has a layer to open.
 *
 * `selectDeepEventIndexes` picks the events a layer is *worth* writing for,
 * which is what the backfill script asks it for. The reader's question is a
 * different one: the layer is the generated report and nothing else, so an
 * event whose report has not been written yet must not advertise a second
 * screen and then show an empty one. A corpus fills in one life at a time, and
 * the invitation down appears exactly where there is something down there.
 * @param {Object} event - Event object
 * @returns {boolean}
 */
export function hasBackgroundReport(event) {
  return (
    typeof event?.background === "string" && event.background.trim() !== ""
  );
}
