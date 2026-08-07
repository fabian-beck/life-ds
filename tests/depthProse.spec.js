import { test, expect } from "@playwright/test";
import {
  asDepthSentence,
  composeDepthParagraphs,
} from "../src/utils/storyHelpers.js";
import en from "../src/locales/en.json" with { type: "json" };

// The real translate function, so the templates under test are the ones the
// application ships rather than a paraphrase of them.
function t(key, params = {}) {
  return Object.entries(params).reduce(
    (text, [name, value]) => text.replaceAll(`{${name}}`, value),
    en[key] ?? key
  );
}

const flatten = (paragraph) =>
  paragraph.map((segment) => segment.text).join("");

test("a definition becomes a statement about its subject", () => {
  const sentence = asDepthSentence(
    "Hut 8",
    "A section at Bletchley Park responsible for naval Enigma",
    t
  );
  expect(sentence.subject).toBe("Hut 8");
  expect(sentence.tail).toBe(
    " was a section at Bletchley Park responsible for naval Enigma."
  );
});

test("an explanation that already names its subject is not made to say it twice", () => {
  const sentence = asDepthSentence(
    "Braintree",
    "Braintree was the Massachusetts town where the Adams family farmed.",
    t
  );
  expect(sentence.subject).toBe("Braintree");
  expect(sentence.tail).toBe(
    " was the Massachusetts town where the Adams family farmed."
  );
  expect(flatten([{ text: sentence.subject }, { text: sentence.tail }])).toBe(
    "Braintree was the Massachusetts town where the Adams family farmed."
  );
});

test("a capital that is not an article is left alone", () => {
  // Lowering "Britain's" or "German" would be an error the reader sees, so
  // these stay as an apposition rather than being forced into a sentence.
  for (const [subject, explanation] of [
    ["Bletchley Park", "Britain's Government Code and Cypher School's site"],
    ["Enigma traffic", "German naval signals enciphered on the machine"],
    ["the imitation game", "Turing's proposed conversational test"],
  ]) {
    const sentence = asDepthSentence(subject, explanation, t);
    expect(sentence.tail).toBe(` — ${explanation}.`);
  }
});

test("every sentence is end-stopped, however the dataset left it", () => {
  expect(asDepthSentence("A", "A thing", t).tail).toMatch(/\.$/);
  expect(asDepthSentence("A", "A thing.", t).tail).toMatch(/[^.]\.$/);
  expect(asDepthSentence("A", "Is it a thing?", t).tail).toMatch(/\?$/);
  expect(asDepthSentence("A", "   ", t)).toBeNull();
});

const depth = {
  places: [{ historic: "Bletchley", modern: "Milton Keynes" }],
  terms: [
    {
      term: "Hut 8",
      explanation: "A section at Bletchley Park",
      wikipediaUrl: "https://en.wikipedia.org/wiki/Hut_8",
    },
    { term: "Enigma", explanation: "A family of cipher machines" },
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

test("the terms of one event are a single passage, not a line each", () => {
  const paragraphs = composeDepthParagraphs(depth, t);
  expect(paragraphs).toHaveLength(3);

  expect(flatten(paragraphs[0])).toBe(
    "It happened at Bletchley, a place today's maps name Milton Keynes."
  );
  expect(flatten(paragraphs[1])).toBe(
    "Hut 8 was a section at Bletchley Park. Enigma was a family of cipher machines."
  );
  expect(flatten(paragraphs[2])).toBe(
    "Joan Clarke was a cryptanalyst in the same section."
  );
});

test("the way out to an article rides on the subject, not on a marker after it", () => {
  const [, background] = composeDepthParagraphs(depth, t);
  const linked = background.filter((segment) => segment.href);
  expect(linked).toHaveLength(1);
  expect(linked[0]).toMatchObject({
    text: "Hut 8",
    href: "https://en.wikipedia.org/wiki/Hut_8",
  });
  expect(flatten(background)).not.toContain(en["story.read_more"]);
});

test("a place with one name gets the shorter sentence, and nothing gets an empty one", () => {
  const paragraphs = composeDepthParagraphs(
    {
      places: [{ historic: "Wilmslow", modern: "Wilmslow" }],
      terms: [{ term: "Unexplained", explanation: "" }],
      people: [{ person_name: "Nobody", relationship_description: null }],
    },
    t
  );
  expect(paragraphs).toHaveLength(1);
  expect(flatten(paragraphs[0])).toBe("It happened at Wilmslow.");
});

test("nothing to say, nothing said", () => {
  expect(composeDepthParagraphs(null, t)).toEqual([]);
  expect(composeDepthParagraphs({}, t)).toEqual([]);
});
