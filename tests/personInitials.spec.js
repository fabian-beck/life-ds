import { test, expect } from "@playwright/test";
import { initialsFromName } from "../src/utils/helpers.js";

// The monogram a card falls back to when a person has no portrait. Three
// surfaces used to compute it — the landing card, the person card and the
// story's conclusion — and the two that read "the first letter of the first
// two words" got ten of the 52 shipped people wrong. Every expectation below
// that names a real person is one of those ten, or the reason one of them
// broke.

test("takes the first word and the last, not the first two", () => {
  // A particle, a middle name and a spelled-out initial each stand where the
  // discarded rule assumed a surname: it read CO, JV, GW and ET.
  expect(initialsFromName("Cunigunde of Luxembourg")).toBe("CL");
  expect(initialsFromName("John von Neumann")).toBe("JN");
  expect(initialsFromName("Georg Wilhelm Friedrich Hegel")).toBe("GH");
  expect(initialsFromName("E. T. A. Hoffmann")).toBe("EH");
});

test("a two-word name is the case both rules always agreed on", () => {
  expect(initialsFromName("Abigail Adams")).toBe("AA");
  expect(initialsFromName("Henry II")).toBe("HI");
});

test("a single-word name still yields a monogram, not one letter", () => {
  expect(initialsFromName("Sappho")).toBe("SA");
  // Two letters of the word, not the word twice.
  expect(initialsFromName("Hypatia")).toBe("HY");
});

test("reads the registry's underscored names as written", () => {
  // `data/persons.json` stores names with underscores; the card renders them
  // spaced, and the monogram is taken from the same reading.
  expect(initialsFromName("Charles_Rennie_Mackintosh")).toBe("CM");
  expect(initialsFromName("Claus_von_Stauffenberg")).toBe("CS");
});

test("collapses stray whitespace before counting words", () => {
  expect(initialsFromName("  Ada   Lovelace  ")).toBe("AL");
});

test("a nameless person gets a question mark rather than an empty box", () => {
  expect(initialsFromName("")).toBe("?");
  expect(initialsFromName()).toBe("?");
  expect(initialsFromName(null)).toBe("?");
  expect(initialsFromName("   ")).toBe("?");
});
