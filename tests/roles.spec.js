import { test, expect } from "@playwright/test";
import { roleKey, roleLabel } from "../src/utils/roles.js";

test("a role is keyed trimmed, lowercased, and with its spacing collapsed", () => {
  expect(roleKey("  Mathematician ")).toBe("mathematician");
  expect(roleKey("political  advisor")).toBe("political advisor");
  expect(roleKey(null)).toBe("");
  expect(roleKey(42)).toBe("");
});

test("a language without gendered role names keys the role as written", () => {
  expect(roleKey("Mathematician", "en")).toBe("mathematician");
  // The reduction is German, so it must not shorten an English role name.
  expect(roleKey("writer", "en")).toBe("writer");
  expect(roleKey("designer", "en")).toBe("designer");
  expect(roleKey("Mathematikerin", "en")).not.toBe(
    roleKey("Mathematiker", "en")
  );
});

test("the German forms of one role share a key", () => {
  for (const [feminine, masculine] of [
    // The regular suffix, on its own and with an umlaut.
    ["Mathematikerin", "Mathematiker"],
    ["Schriftstellerin", "Schriftsteller"],
    ["Architektin", "Architekt"],
    ["Professorin", "Professor"],
    ["Präsidentin", "Präsident"],
    ["Journalistin", "Journalist"],
    ["Ingenieurin", "Ingenieur"],
    ["Ärztin", "Arzt"],
    ["Köchin", "Koch"],
    ["Gräfin", "Graf"],
    ["Bäuerin", "Bauer"],
    // The weak and adjectival nouns, whose masculine form ends in "e" or "er".
    ["Pathologin", "Pathologe"],
    ["Pädagogin", "Pädagoge"],
    ["Beamtin", "Beamter"],
    ["Industrielle", "Industrieller"],
    // The irregular feminine, and the compound that pairs "-mann" with "-frau".
    ["Prinzessin", "Prinz"],
    ["Geschäftsfrau", "Geschäftsmann"],
    ["Kauffrau", "Kaufmann"],
  ]) {
    expect(roleKey(feminine, "de"), `${feminine} / ${masculine}`).toBe(
      roleKey(masculine, "de")
    );
  }
});

test("different German roles keep different keys", () => {
  // One name per profession, across the shapes the reduction cuts into:
  // "-er", "-e", "-or", "-ent", "-ist", "-eur", and the compounds.
  const distinct = [
    "Mathematiker",
    "Informatiker",
    "Physiker",
    "Chemiker",
    "Architekt",
    "Philosoph",
    "Dichter",
    "Designer",
    "Erfinder",
    "Kaiser",
    "Monarch",
    "Lehrer",
    "Hochschullehrer",
    "Pathologe",
    "Pädagoge",
    "Professor",
    "Präsident",
    "Publizist",
    "Redakteur",
    "Offizier",
    "Marineoffizier",
    "Geschäftsmann",
    "Staatsmann",
    "Widerstandskämpfer",
  ];
  const keys = new Set(distinct.map((role) => roleKey(role, "de")));
  expect(keys.size).toBe(distinct.length);
});

test("a short role keeps the ending that would leave no stem", () => {
  expect(roleKey("Abt", "de")).toBe("abt");
  expect(roleKey("Erbin", "de")).toBe(roleKey("Erbe", "de"));
  expect(roleKey("Patin", "de")).toBe(roleKey("Pate", "de"));
});

test("a role the data carries in both forms is labeled inclusively", () => {
  expect(roleLabel(["Mathematiker", "Mathematikerin"])).toBe("Mathematiker:in");
  expect(roleLabel(["Mathematikerin", "Mathematiker"])).toBe("Mathematiker:in");
  // The inclusive form is built on the feminine name's stem, which is what the
  // irregular pairs need.
  expect(roleLabel(["Pathologe", "Pathologin"])).toBe("Patholog:in");
  expect(roleLabel(["Arzt", "Ärztin"])).toBe("Ärzt:in");
});

test("a role the data carries in one form is labeled as written", () => {
  expect(roleLabel(["Physikerin"])).toBe("Physikerin");
  expect(roleLabel([" Mathematician "])).toBe("Mathematician");
  expect(roleLabel([])).toBe("");
  expect(roleLabel(null)).toBe("");
});
