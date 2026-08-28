/**
 * The list of slides a person's story is made of, and the index maps that
 * translate between a slide's position and the event it shows.
 *
 * All of it is a pure function of the dataset — events, chapters, conclusion —
 * which is why it lives here rather than among StoryView's scroll state. The
 * component is a state machine over `activeIndex`; this is the thing that
 * decides what `activeIndex` is an index *into*, and it is worth being able to
 * test that without a browser.
 */

/**
 * Build the slide list: an overview, the events, a chapter slide in front of
 * each chapter's first event, and a conclusion when there is one.
 *
 * @param {Object} [model] - The story's parts
 * @param {Array<Object>} [model.events] - Events, already sorted and indexed
 * @param {Array<Object>} [model.chapters] - Chapter definitions
 * @param {string|null} [model.conclusion] - Closing statement
 * @param {Array<Object>} [model.relatedPersons] - People for the closing slide
 * @param {Array<string>} [model.allSources] - Sources for the closing slide
 * @returns {Array<Object>} Slides, each carrying a `type`
 */
export function buildSlides({
  events = [],
  chapters = [],
  conclusion = null,
  relatedPersons = [],
  allSources = [],
} = {}) {
  // A story with neither a closing statement nor anyone to point at afterwards
  // simply ends on its last event.
  const hasConclusion = Boolean(conclusion) || relatedPersons.length > 0;
  const conclusionSlide = {
    type: "conclusion",
    conclusion,
    relatedPersons,
    allSources,
  };

  if (events.length === 0) {
    // A dataset can arrive with a conclusion and no events — the overview and
    // the closing statement are still a story, just a short one.
    return hasConclusion
      ? [{ type: "overview" }, conclusionSlide]
      : [{ type: "overview" }];
  }

  const slides = [{ type: "overview" }];

  if (chapters.length === 0) {
    slides.push(...events.map((event) => ({ ...event, type: "event" })));
  } else {
    let lastChapterId = null;
    events.forEach((event, index) => {
      // A chapter slide is inserted the first time its chapter is entered, so
      // an event whose chapter is unknown to `chapters` simply gets none.
      if (event.chapter && event.chapter !== lastChapterId) {
        const chapter = chapters.find((ch) => ch.id === event.chapter);
        if (chapter) {
          slides.push({
            type: "chapter",
            chapter,
            chapterIndex: chapters.indexOf(chapter),
            eventIndex: index,
          });
        }
        lastChapterId = event.chapter;
      }
      slides.push({ ...event, type: "event" });
    });
  }

  if (hasConclusion) slides.push(conclusionSlide);
  return slides;
}

/**
 * Slide position → event position.
 *
 * The overview maps to -1 rather than to nothing, because it is a real place
 * in the story that the timeline has to be able to sit before. Chapter and
 * conclusion slides map to `null`: they are slides that show no event.
 *
 * @param {Array<Object>} slides - Slides from {@link buildSlides}
 * @returns {Map<number, number|null>} Slide index to event index
 */
export function slideToEventIndex(slides = []) {
  const map = new Map();
  let eventIndex = 0;
  slides.forEach((slide, slideIndex) => {
    if (slide.type === "overview") {
      map.set(slideIndex, -1);
    } else if (slide.type === "chapter" || slide.type === "conclusion") {
      map.set(slideIndex, null);
    } else {
      map.set(slideIndex, eventIndex);
      eventIndex += 1;
    }
  });
  return map;
}

/**
 * Event position → slide position, for timeline navigation.
 * @param {Array<Object>} slides - Slides from {@link buildSlides}
 * @returns {Map<number, number>} Event index to slide index
 */
export function eventToSlideIndex(slides = []) {
  const map = new Map();
  const bySlide = slideToEventIndex(slides);
  slides.forEach((slide, slideIndex) => {
    if (slide.type === "overview" || slide.type === "chapter") return;
    const eventIndex = bySlide.get(slideIndex);
    if (eventIndex !== null && eventIndex !== undefined && eventIndex !== -1) {
      map.set(eventIndex, slideIndex);
    }
  });
  return map;
}

/**
 * Source-array position → slide position.
 *
 * This is the identity external links use: a LandingMap marker and a
 * meta-story `event_index` are both generated from the person's events array
 * in its stored order, which is not where the story's chronological sort puts
 * them whenever the dates were not already in order.
 *
 * @param {Array<Object>} slides - Slides from {@link buildSlides}
 * @returns {Map<number, number>} Raw event index to slide index
 */
export function rawEventToSlideIndex(slides = []) {
  const map = new Map();
  slides.forEach((slide, slideIndex) => {
    if (slide.type === "event" && typeof slide.rawIndex === "number") {
      map.set(slide.rawIndex, slideIndex);
    }
  });
  return map;
}
