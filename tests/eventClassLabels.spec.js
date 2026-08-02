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

test("every classification the datasets carry has a German name", () => {
  // The vocabulary is closed, so a missing entry is a bug, not a fallback.
  for (const type of ["marriage_partnership", "migration", "publication"]) {
    expect(eventClassLabel(tDe, { type })).not.toBe(
      eventClassLabel(t, { type })
    );
  }
  for (const kind of ["book", "paper", "article", "manuscript", "thesis"]) {
    expect(de[`story.publication_type.${kind}`]).toBeTruthy();
  }
});
