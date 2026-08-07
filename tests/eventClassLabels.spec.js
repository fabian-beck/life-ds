import { test, expect } from "@playwright/test";
import {
  eventClassLabel,
  publicationTypeLabel,
} from "../src/utils/eventClassLabels.js";
// Node requires the import attribute for JSON modules; the locales are read
// here rather than restated so the test cannot drift from what ships.
import en from "../src/locales/en.json" with { type: "json" };
import de from "../src/locales/de.json" with { type: "json" };

// The real translate function: it answers with the key when there is no entry,
// which is exactly the case the fallback has to survive.
const translator = (locale) => (key) => locale[key] ?? key;
const t = translator(en);
const tDe = translator(de);

test("names a union by what it was", () => {
  const marriage = { type: "marriage_partnership", subtype: "marriage" };
  const partnership = { type: "marriage_partnership", subtype: "partnership" };
  expect(eventClassLabel(t, marriage)).toBe("Marriage");
  expect(eventClassLabel(tDe, marriage)).toBe("Ehe");
  expect(eventClassLabel(tDe, partnership)).toBe("Partnerschaft");
});

test("names the other classifications in the reader's language", () => {
  expect(eventClassLabel(tDe, { type: "publication" })).toBe("Publikation");
  expect(eventClassLabel(tDe, { type: "invention" })).toBe("Erfindung");
  expect(eventClassLabel(tDe, { type: "migration" })).toBe("Umzug");
});

test("falls back to the humanized token, never a locale key", () => {
  // A classification the generator grows before the locales catch up.
  const label = eventClassLabel(tDe, { type: "military_service" });
  expect(label).toBe("Military Service");
});

test("names a publication's kind", () => {
  expect(publicationTypeLabel(t, "book")).toBe("Book");
  expect(publicationTypeLabel(tDe, "book")).toBe("Buch");
  expect(publicationTypeLabel(tDe, "thesis")).toBe("Dissertation");
});

test("a publication with no stated kind still reads as one", () => {
  expect(publicationTypeLabel(tDe, null)).toBe("Publikation");
  expect(publicationTypeLabel(tDe, undefined)).toBe("Publikation");
});

test("the two locales define the same vocabulary", () => {
  // The vocabularies are closed, so an entry in one locale and not the other
  // is a bug rather than a fallback. Compared as key sets: a German name is
  // free to be spelled like the English one — "Essay" is — so telling the two
  // apart by their text would both miss that case and misread it as drift.
  const vocabulary = (locale) =>
    Object.keys(locale)
      .filter(
        (key) =>
          key.startsWith("story.event_class.") ||
          key.startsWith("story.publication_type.")
      )
      .sort();
  expect(vocabulary(de)).toEqual(vocabulary(en));
  expect(vocabulary(en).length).toBeGreaterThan(0);
});
