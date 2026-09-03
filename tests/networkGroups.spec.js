import { test, expect } from "@playwright/test";
import { groupBySubcategory } from "../src/utils/story/networkGroups.js";

// The role boxes inside one circle of the network view. A box subdivides a
// circle, so a circle that resolves to a single group is rendered without
// one: the Einstein network drew a frame around four academic chips that
// shared no role, which framed nothing.

const labelRole = (role, count) => (count === 1 ? role : `${role}s`);

const tie = (name, type, strength = "moderate") => ({
  person_name: name,
  relationship_type: type,
  strength,
});

const names = (group) => group.people.map((p) => p.person_name);

test("a circle whose roles never repeat is one unboxed group", () => {
  const groups = groupBySubcategory(
    [
      tie("Marcel Grossmann", "academic/friend"),
      tie("Michele Besso", "academic/collaborator"),
      tie("Max Planck", "academic/mentor", "strong"),
      tie("J. Robert Oppenheimer", "academic/colleague", "weak"),
    ],
    labelRole
  );
  expect(groups).toHaveLength(1);
  expect(groups[0].subcategory).toBeNull();
  expect(groups[0].label).toBeNull();
  expect(groups[0].isOther).toBeUndefined();
  // Strongest first within the group.
  expect(names(groups[0])).toEqual([
    "Max Planck",
    "Marcel Grossmann",
    "Michele Besso",
    "J. Robert Oppenheimer",
  ]);
});

test("a circle where everyone shares one role is unboxed too", () => {
  // One box holding the whole circle would subdivide nothing; the chips
  // keep their role labels instead.
  const groups = groupBySubcategory(
    [
      tie("Ernst Straus", "academic/student"),
      tie("Leopold Infeld", "academic/student"),
      tie("Nathan Rosen", "academic/student"),
    ],
    labelRole
  );
  expect(groups).toHaveLength(1);
  expect(groups[0].subcategory).toBeNull();
  expect(groups[0].label).toBeNull();
});

test("a repeated role earns a labeled box, and the leftovers an Other box", () => {
  const groups = groupBySubcategory(
    [
      tie("A", "professional/colleague", "weak"),
      tie("B", "professional/colleague", "strong"),
      tie("C", "professional/employer"),
      tie("D", "professional/publisher"),
    ],
    labelRole
  );
  expect(groups.map((g) => g.subcategory)).toEqual(["colleague", null]);
  expect(groups[0].label).toBe("colleagues");
  expect(names(groups[0])).toEqual(["B", "A"]);
  expect(groups[1].isOther).toBe(true);
  expect(groups[1].label).toBeNull();
  expect(names(groups[1])).toEqual(["C", "D"]);
});

test("a single leftover names its box after its own role", () => {
  const groups = groupBySubcategory(
    [
      tie("A", "academic/student"),
      tie("B", "academic/student"),
      tie("C", "academic/mentor"),
    ],
    labelRole
  );
  expect(groups.map((g) => g.subcategory)).toEqual(["student", "mentor"]);
  expect(groups[1].label).toBe("mentor");
  expect(groups[1].isOther).toBe(false);
});

test("boxes are ordered strongest first, with the leftovers always last", () => {
  const groups = groupBySubcategory(
    [
      tie("A", "academic/student", "weak"),
      tie("B", "academic/student", "weak"),
      tie("C", "academic/mentor", "strong"),
      tie("D", "academic/mentor", "strong"),
      tie("E", "academic/rival", "strong"),
      tie("F", "academic/patron", "strong"),
    ],
    labelRole
  );
  expect(groups.map((g) => g.subcategory)).toEqual(["mentor", "student", null]);
  expect(groups[2].isOther).toBe(true);
});
