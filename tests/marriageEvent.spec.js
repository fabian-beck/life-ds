import { test, expect } from "@playwright/test";
import { getMarriagePartner } from "../src/utils/story/personMatching.js";

const marriageEvent = {
  event_class: {
    type: "marriage_partnership",
    subtype: "marriage",
    partner: "Alexander Rowan, 4th Baron Rowan",
  },
};

test("resolves a differently labeled spouse through a unique partner role", () => {
  const spouse = {
    person_name: "Lord Rowan",
    relationship_type: "family/spouse",
    relationship_description: "Shared a household",
  };

  expect(getMarriagePartner(marriageEvent, { connections: [spouse] })).toBe(
    spouse
  );
});

test("keeps the classified partner when relationship evidence is ambiguous", () => {
  const network = {
    connections: [
      { person_name: "Lord Rowan", relationship_type: "family/spouse" },
      { person_name: "Morgan Vale", relationship_type: "family/spouse" },
    ],
  };

  expect(getMarriagePartner(marriageEvent, network)).toEqual({
    person_name: "Alexander Rowan, 4th Baron Rowan",
    relationship_type: "family/spouse",
    relationship_description: "",
  });
});

test("does not create a partner for another event class", () => {
  expect(
    getMarriagePartner(
      { event_class: { type: "publication", partner: "Alexander Rowan" } },
      { connections: [] }
    )
  ).toBe(null);
});
