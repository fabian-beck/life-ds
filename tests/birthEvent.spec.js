import { test, expect } from "@playwright/test";
import {
  getBirthParents,
  isBirthEvent,
  normalizeFamilyRole,
} from "../src/utils/story/personMatching.js";

const father = {
  person_name: "Christian Bohr",
  relationship_type: "family/father",
  relationship_description: "Physiologist and first teacher",
  strength: "strong",
};
const mother = {
  person_name: "Ellen Adler Bohr",
  relationship_type: "family/mother",
  relationship_description: "From a Danish banking family",
  strength: "strong",
};
const sibling = {
  person_name: "Harald Bohr",
  relationship_type: "family/sibling",
  relationship_description: "Mathematician brother",
  strength: "strong",
};
const network = { connections: [father, mother, sibling] };

const birthEvent = {
  title: "Birth in Copenhagen",
  event_class: {
    type: "birth",
    father: "Christian Bohr",
    mother: "Ellen Adler Bohr",
  },
};

test("recognizes the birth event by its classification", () => {
  expect(isBirthEvent(birthEvent)).toBe(true);
  expect(isBirthEvent({ event_class: { type: "migration" } })).toBe(false);
  expect(isBirthEvent({ title: "Birth in Copenhagen" })).toBe(false);
});

test("resolves the named parents against the ego network", () => {
  const parents = getBirthParents(birthEvent, network);
  // Father first, and each one carries the network's own metadata so the chip
  // behaves exactly as it does in the network view.
  expect(parents.map((p) => p.person_name)).toEqual([
    "Christian Bohr",
    "Ellen Adler Bohr",
  ]);
  expect(parents[0].relationship_description).toBe(
    "Physiologist and first teacher"
  );
});

test("still shows a parent the network does not know", () => {
  const parents = getBirthParents(birthEvent, { connections: [] });
  expect(parents.map((p) => p.relationship_type)).toEqual([
    "family/father",
    "family/mother",
  ]);
  // An undefined description would reach the tooltip as the text "undefined".
  expect(parents[0].relationship_description).toBe("");
});

test("falls back to the network when the classification names nobody", () => {
  const parents = getBirthParents({ event_class: { type: "birth" } }, network);
  expect(parents).toEqual([father, mother]);
});

test("takes no parents from an event that is not a birth", () => {
  expect(
    getBirthParents({ event_class: { type: "publication" } }, network)
  ).toEqual([]);
});

test("leaves out a parent the sources never named", () => {
  const placeholder = {
    person_name: "Unnamed mother of Frances E. Allen",
    relationship_type: "family/mother",
  };
  expect(
    getBirthParents(
      { event_class: { type: "birth" } },
      { connections: [placeholder] }
    )
  ).toEqual([]);
  expect(
    getBirthParents(
      { event_class: { type: "birth", father: "Unknown father" } },
      { connections: [] }
    )
  ).toEqual([]);
});

test("reads a qualified family role as the plain one", () => {
  expect(normalizeFamilyRole("family/step_father")).toBe("father");
  expect(normalizeFamilyRole("family/adoptive-mother")).toBe("mother");
  expect(normalizeFamilyRole("family/aunt-by-marriage")).toBe("aunt");
  expect(normalizeFamilyRole("family")).toBe(null);
});

test("finds an adoptive parent through the fallback", () => {
  const adoptive = {
    person_name: "Paul Jobs",
    relationship_type: "family/adoptive-father",
  };
  const parents = getBirthParents(
    { event_class: { type: "birth" } },
    { connections: [adoptive] }
  );
  expect(parents).toEqual([adoptive]);
});
