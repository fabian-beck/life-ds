import { test, expect } from "@playwright/test";
import {
  getEventDepth,
  hasBackgroundReport,
} from "../src/utils/story/eventDepth.js";
import {
  collectStoryImages,
  getBackgroundImages,
  getThumbnailUrl,
} from "../src/utils/story/images.js";
import {
  mentionedPeople,
  parseBackgroundBlocks,
} from "../src/utils/story/prose.js";

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

/* The searches are told to leave the slide's picture alone and the candidates
   drop it, but a Commons file is served at any width, so the same photograph
   reaches the two screens as two URLs. Comparing them as URLs would call them
   two pictures and print one of them twice. */
test("the same file at another size is still the slide's picture", () => {
  const event = {
    images: [{ url: commons("thumb/a/a1/Hut_8.jpg/640px-Hut_8.jpg") }],
    background_images: [
      { url: commons("thumb/a/a1/Hut_8.jpg/960px-Hut_8.jpg?utm_source=x") },
      { url: commons("bombe.jpg"), caption: "A rebuilt bombe" },
    ],
  };
  expect(getBackgroundImages(event).map((image) => image.caption)).toEqual([
    "A rebuilt bombe",
  ]);
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

/* The report is the one text in the application long enough to want a shape.
   It carries its headings as `## ` lines and nothing else as markup, so the
   parser reads a page: headings, paragraphs, and inside a paragraph the people
   this life's network knows. */
function render(background, people = [], subjectName = null) {
  return parseBackgroundBlocks(background, people, subjectName).map((block) =>
    block.type === "heading"
      ? `## ${block.text}`
      : block.segments
          .map((segment) =>
            segment.type === "person" ? `«${segment.content}»` : segment.content
          )
          .join("")
  );
}

const connection = (name) => ({ person_name: name });

test("a report divides at its headings and nowhere else", () => {
  expect(
    render(
      "Bletchley ran on shifts.\n\n" +
        "## The bombe on the floor\n\n" +
        "Two hundred of them by 1943.\n\n" +
        "It ended with the war."
    )
  ).toEqual([
    "Bletchley ran on shifts.",
    "## The bombe on the floor",
    "Two hundred of them by 1943.",
    "It ended with the war.",
  ]);
});

test("an undivided report is still a page of paragraphs", () => {
  expect(render("One paragraph.\n\nAnd a second.")).toEqual([
    "One paragraph.",
    "And a second.",
  ]);
  expect(parseBackgroundBlocks("   ")).toEqual([]);
  expect(parseBackgroundBlocks(null)).toEqual([]);
});

/* The same matcher the description uses, so a reader meets a person the same
   way on both screens. */
test("the names the network knows are emphasized in the prose", () => {
  expect(
    render(
      "Christopher Morcom had died four years earlier, and Max Newman " +
        "lectured on it.",
      [connection("Christopher Morcom"), connection("Max Newman")]
    )
  ).toEqual([
    "«Christopher Morcom» had died four years earlier, and «Max Newman» " +
      "lectured on it.",
  ]);
});

/* A description names a person twice at most. A report about Max Brod names
   Brod twelve times, and twelve bold Brods down one page is speckle rather
   than emphasis — the mark says the network knows this person, which needs
   saying the first time and not after. */
test("a person is emphasized once in a report, not at every mention", () => {
  expect(
    render(
      "Max Newman lectured on it.\n\nNewman later hired him, and Max Newman " +
        "signed the letter.",
      [connection("Max Newman")]
    )
  ).toEqual([
    "«Max Newman» lectured on it.",
    "Newman later hired him, and Max Newman signed the letter.",
  ]);
});

test("a name the network does not know is left alone", () => {
  expect(render("Winston Churchill read the decrypts.", [])).toEqual([
    "Winston Churchill read the decrypts.",
  ]);
});

/* The chips under the report are the people it emphasized and nobody else:
   the slide above carries the event's own cast, and a report ranging over a
   decade names people the event never did. Each once, in the order the report
   introduces them, and as the network's own records, so a chip here opens the
   same tooltip a chip on the slide does. */
test("the report's chips are the people it names, once each, in order", () => {
  const morcom = connection("Christopher Morcom");
  const newman = connection("Max Newman");
  const blocks = parseBackgroundBlocks(
    "Max Newman lectured on it.\n\n## Before\n\nChristopher Morcom had " +
      "died four years earlier; Newman had not known him. Max Newman later " +
      "signed the letter.",
    [morcom, newman, connection("Joan Clarke")],
    "Alan Turing"
  );
  expect(mentionedPeople(blocks)).toEqual([newman, morcom]);
  expect(mentionedPeople([])).toEqual([]);
});

/* This is the subject's own story: there is nothing to point them at, and a
   report about them would otherwise be half in bold. They still compete for
   their own name, so a shared surname comes out plain rather than handed to a
   relative. */
test("the subject's own name stays plain", () => {
  expect(
    render(
      "Turing walked to Hut 8.",
      [connection("Sara Turing")],
      "Alan Turing"
    )
  ).toEqual(["Turing walked to Hut 8."]);
});

/* A picture opened from under the fold has to land in the same gallery as one
   opened from the slide above, next to the pictures of its own event — a
   lightbox holding a single image with nowhere to page to is what the reader
   used to get. */
test("the report's pictures join the story's gallery, after the event's own", () => {
  const gallery = collectStoryImages(
    { image: commons("portrait.jpg"), full: commons("portrait_full.jpg") },
    [
      {
        eventIndex: 3,
        title: "Led Hut 8",
        date: "1941-01-01",
        images: [{ url: commons("hut8.jpg") }],
        background_images: [
          { url: commons("bombe.jpg"), caption: "A rebuilt bombe" },
        ],
      },
    ],
    new Map([[3, 7]])
  );

  expect(gallery.map((image) => image.url)).toEqual([
    commons("portrait_full.jpg"),
    commons("hut8.jpg"),
    commons("bombe.jpg"),
  ]);
  expect(gallery[2]).toMatchObject({
    caption: "A rebuilt bombe",
    eventIndex: 3,
    eventTitle: "Led Hut 8",
    slideIndex: 7,
  });
});

/* Every illustration in the corpus comes from the Commons API, which appends
   its own analytics to the address it answers with. A size is appended to the
   path, so a query string left in the middle of the address is a picture that
   never loads — which is how the first illustrated reports shipped with three
   captions and no pictures. */
test("the tracking Commons hangs off a URL never reaches the thumbnail", () => {
  const tracked = (path) =>
    `${commons(path)}?utm_source=commons.wikimedia.org&utm_campaign=imageinfo`;

  expect(
    getThumbnailUrl(tracked("thumb/b/bc/Enigma.JPG/960px-Enigma.JPG"), 800)
  ).toBe(commons("thumb/b/bc/Enigma.JPG/960px-Enigma.JPG"));
  expect(getThumbnailUrl(tracked("6/69/Bombe.jpg"), 800)).toBe(
    commons("thumb/6/69/Bombe.jpg/960px-Bombe.jpg")
  );
});
