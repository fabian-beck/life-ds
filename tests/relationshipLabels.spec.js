import { test, expect } from "@playwright/test";
import {
  relationshipCategoryLabel,
  relationshipMetaValueLabel,
  relationshipRoleLabel,
  relationshipTypeLabel,
} from "../src/utils/relationshipLabels.js";
// Node requires the import attribute for JSON modules; the locales are read
// here rather than restated so the test cannot drift from what ships.
import en from "../src/locales/en.json" with { type: "json" };
import de from "../src/locales/de.json" with { type: "json" };

// The real translate function: it answers with the key when there is no entry,
// which is exactly the case the fallback has to survive.
const translator = (locale) => (key) => locale[key] ?? key;
const t = translator(en);
const tDe = translator(de);

test("names a role in the reader's language", () => {
  expect(relationshipRoleLabel(t, "father")).toBe("Father");
  expect(relationshipRoleLabel(tDe, "father")).toBe("Vater");
  expect(relationshipRoleLabel(tDe, "collaborator")).toBe(
    "Kooperationspartner"
  );
});

test("pluralizes from the locale rather than by rule", () => {
  // The old naive pluralizer turned two children into "Childs".
  expect(relationshipRoleLabel(t, "child", 2)).toBe("Children");
  expect(relationshipRoleLabel(tDe, "child", 2)).toBe("Kinder");
  expect(relationshipRoleLabel(tDe, "mentor", 3)).toBe("Mentoren");
});

test("collapses the spellings the datasets disagree on", () => {
  // data/ carries both `family/mother_in_law` and `family/mother-in-law`.
  for (const token of ["mother_in_law", "mother-in-law", "Mother In Law"]) {
    expect(relationshipRoleLabel(tDe, token)).toBe("Schwiegermutter");
  }
});

test("takes the role from a full relationship type", () => {
  expect(relationshipRoleLabel(tDe, "family/father")).toBe("Vater");
});

test("names a category, and a bare token that is also a role", () => {
  expect(relationshipCategoryLabel(t, "professional", 6)).toBe("Professional");
  expect(relationshipCategoryLabel(tDe, "professional", 6)).toBe("Beruflich");
  // `colleague` appears as a whole relationship_type, so it heads a group.
  expect(relationshipCategoryLabel(tDe, "colleague", 4)).toBe("Kollegen");
  expect(relationshipCategoryLabel(tDe, "colleague", 1)).toBe("Kollege");
});

test("falls back to a visibly generic label for values with no mapping", () => {
  // The vocabulary is closed, so a token without a locale entry is a gap.
  // The old fallback title-cased the raw token — fake-English-precise in
  // every language; now the reader gets an honestly generic label instead.
  expect(relationshipRoleLabel(t, "authorship attester")).toBe("Connection");
  expect(relationshipRoleLabel(tDe, "poetic subject")).toBe("Verbindung");
  expect(relationshipRoleLabel(tDe, "poetic subject", 3)).toBe("Verbindungen");
  expect(relationshipCategoryLabel(t, "cosmic", 1)).toBe("Other");
  expect(relationshipCategoryLabel(tDe, "cosmic", 1)).toBe("Weitere");
  // Known tokens are untouched.
  expect(relationshipRoleLabel(t, "adversary", 2)).toBe("Adversaries");
  expect(relationshipCategoryLabel(t, "innovation", 1)).toBe("Innovation");
});

test("names the new directional conflict roles in both languages", () => {
  // Issue #119: the tag itself states that the regime acted against the
  // subject — Goebbels reads "Censor"/"Zensor", never a neutral role word.
  expect(relationshipRoleLabel(t, "political/censor")).toBe("Censor");
  expect(relationshipRoleLabel(tDe, "political/censor")).toBe("Zensor");
  expect(relationshipRoleLabel(tDe, "persecutor")).toBe("Verfolger");
  expect(relationshipRoleLabel(t, "banned_by")).toBe("Banned by");
  expect(relationshipTypeLabel(tDe, "political/banned_by")).toBe(
    "Politisch · Verboten durch"
  );
});

test("joins both segments for the meta story network", () => {
  expect(relationshipTypeLabel(t, "professional/mentor")).toBe(
    "Professional · Mentor"
  );
  expect(relationshipTypeLabel(tDe, "professional/mentor")).toBe(
    "Beruflich · Mentor"
  );
});

test("is empty for an absent relationship", () => {
  expect(relationshipRoleLabel(t, null)).toBe("");
  expect(relationshipCategoryLabel(t, "")).toBe("");
  expect(relationshipTypeLabel(t, undefined)).toBe("");
});

test("names the relationship metadata values in the reader's language", () => {
  // The datasets carry these as English tokens in every language; the chip
  // used to print them raw, so a German reader got "Stärke: strong".
  expect(relationshipMetaValueLabel(t, "strength", "strong")).toBe("strong");
  expect(relationshipMetaValueLabel(tDe, "strength", "strong")).toBe("stark");
  expect(relationshipMetaValueLabel(tDe, "frequency", "occasional")).toBe(
    "gelegentlich"
  );
  // An unmapped token still falls back to its humanized form.
  expect(relationshipMetaValueLabel(t, "strength", "overwhelming")).toBe(
    "Overwhelming"
  );
  expect(relationshipMetaValueLabel(t, "strength", null)).toBe("");
});

test("every relationship metadata token in the corpus has both locale entries", () => {
  // The closed vocabulary, verified across all ego networks.
  const families = {
    strength: ["strong", "moderate", "weak"],
    frequency: ["daily", "weekly", "monthly", "yearly", "occasional", "rare"],
  };
  for (const [family, tokens] of Object.entries(families)) {
    for (const token of tokens) {
      const key = `person.${family}_value.${token}`;
      expect(en[key], key).toBeTruthy();
      expect(de[key], key).toBeTruthy();
    }
  }
});

test("the two locales define the same vocabulary", () => {
  const vocabulary = (locale) =>
    Object.keys(locale)
      .filter(
        (key) =>
          key.startsWith("network.role.") || key.startsWith("network.category.")
      )
      .sort();
  expect(vocabulary(de)).toEqual(vocabulary(en));
});
