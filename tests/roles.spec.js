import { test, expect } from "@playwright/test";
import { normalizeRole, roleVocabulary } from "../src/utils/roles.js";
// The shipped German registry, so the pairs the test claims are merged are the
// ones a reader actually meets.
import personsDe from "../data/persons_de.json" with { type: "json" };

const germanRoles = personsDe.people.flatMap(
  (person) => person.primaryRoles ?? []
);

test("a role is compared trimmed and lowercased", () => {
  expect(normalizeRole("  Mathematician ")).toBe("mathematician");
  expect(normalizeRole(null)).toBe("");
  expect(normalizeRole(42)).toBe("");
});

test("English roles are compared as written", () => {
  const roles = roleVocabulary(["Mathematician", "writer"], "en");
  expect(roles.key("mathematician")).toBe("mathematician");
  expect(roles.label("mathematician")).toBe("Mathematician");
  expect(roles.key("writer")).toBe("writer");
});

test("the two German forms of one role share a key", () => {
  const roles = roleVocabulary(
    ["Mathematikerin", "Mathematiker", "Architektin", "Architekt"],
    "de"
  );
  expect(roles.key("Mathematikerin")).toBe(roles.key("Mathematiker"));
  expect(roles.key("Architektin")).toBe(roles.key("Architekt"));
  expect(roles.key("Mathematikerin")).not.toBe(roles.key("Architekt"));
});

test("an irregular German pair shares a key too", () => {
  // "Pathologin" drops the masculine "-e", "Beamtin" the masculine "-er", and
  // "Ärztin" carries an umlaut its masculine form does not.
  const roles = roleVocabulary(
    ["Pathologe", "Pathologin", "Beamter", "Beamtin", "Arzt", "Ärztin"],
    "de"
  );
  expect(roles.key("Pathologin")).toBe(roles.key("Pathologe"));
  expect(roles.key("Beamtin")).toBe(roles.key("Beamter"));
  expect(roles.key("Ärztin")).toBe(roles.key("Arzt"));
});

test("a merged pair is labeled inclusively, from the stem both forms share", () => {
  const roles = roleVocabulary(
    ["Mathematikerin", "Mathematiker", "Pathologe", "Pathologin", "Physikerin"],
    "de"
  );
  expect(roles.label("Mathematiker")).toBe("Mathematiker:in");
  expect(roles.label("Mathematikerin")).toBe("Mathematiker:in");
  expect(roles.label("Pathologe")).toBe("Patholog:in");
  // Without a masculine counterpart in the data there is no pair to label.
  expect(roles.label("Physikerin")).toBe("Physikerin");
});

test("only a pair the data carries is merged", () => {
  // A word ending in "in" is not read as a feminine role name on its own: the
  // masculine form has to occur in the data as well.
  const german = roleVocabulary(["Kapitänin", "Mathematiker"], "de");
  expect(german.key("Kapitänin")).toBe("kapitänin");
  expect(german.label("Kapitänin")).toBe("Kapitänin");
});

test("only German merges its gendered forms", () => {
  const english = roleVocabulary(["Mathematikerin", "Mathematiker"], "en");
  expect(english.key("Mathematikerin")).not.toBe(english.key("Mathematiker"));
});

test("a role the vocabulary never saw is still keyed and labeled", () => {
  const roles = roleVocabulary(["Mathematiker"], "de");
  expect(roles.key(" Physikerin ")).toBe("physikerin");
  expect(roles.label(" Physikerin ")).toBe("Physikerin");
  expect(roles.key(null)).toBe("");
  expect(roles.label(undefined)).toBe("");
});

test("the German registry's gendered pairs all merge", () => {
  const roles = roleVocabulary(germanRoles, "de");
  for (const [feminine, masculine] of [
    ["Mathematikerin", "Mathematiker"],
    ["Physikerin", "Physiker"],
    ["Informatikerin", "Informatiker"],
    ["Schriftstellerin", "Schriftsteller"],
    ["Architektin", "Architekt"],
    ["Designerin", "Designer"],
    ["Dichterin", "Dichter"],
    ["Erfinderin", "Erfinder"],
    ["Künstlerin", "Künstler"],
    ["Hochschullehrerin", "Hochschullehrer"],
  ]) {
    expect(germanRoles).toContain(feminine);
    expect(germanRoles).toContain(masculine);
    expect(roles.key(feminine)).toBe(roles.key(masculine));
  }
});
