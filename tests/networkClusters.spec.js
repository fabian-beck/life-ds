import { test, expect } from "@playwright/test";
import { computeClusters } from "../src/utils/networkClusters.js";

// The circles of a meta story network come from the pipeline, stored as
// member_ids per narration circle. The client resolves them against the graph
// and never detects communities itself, so a narration without member_ids
// yields no circles at all.

const main = (id, birthYear) => ({
  id,
  name: id.replace("_", " "),
  type: "main",
  birth_year: birthYear,
});
const secondary = (id) => ({
  id,
  name: id.replace("_", " "),
  type: "secondary",
});
const link = (source, target, kind, strength) => ({
  source,
  target,
  kind,
  strength,
});

const network = {
  nodes: [
    main("ada_lovelace", 1815),
    main("charles_babbage", 1791),
    main("alan_turing", 1912),
    main("john_von_neumann", 1903),
    secondary("mary_somerville"),
    secondary("max_newman"),
  ],
  links: [
    link("ada_lovelace", "charles_babbage", "main", "strong"),
    link("alan_turing", "john_von_neumann", "main", "moderate"),
    link("ada_lovelace", "mary_somerville", "secondary", "moderate"),
    link("charles_babbage", "mary_somerville", "secondary", "weak"),
    link("alan_turing", "max_newman", "secondary", "strong"),
    link("john_von_neumann", "max_newman", "secondary", "weak"),
    link("charles_babbage", "alan_turing", "main", "weak"),
  ],
};

const withCircles = (circles) => ({ ...network, narration: { circles } });

test("a narration without member_ids yields no circles", () => {
  expect(computeClusters(network)).toEqual([]);
  expect(
    computeClusters(withCircles([{ key: "charles_babbage+ada_lovelace" }]))
  ).toEqual([]);
});

test("circles follow the stored order and members", () => {
  const clusters = computeClusters(
    withCircles([
      {
        key: "john_von_neumann+alan_turing",
        member_ids: ["alan_turing", "john_von_neumann"],
      },
      {
        key: "charles_babbage+ada_lovelace",
        member_ids: ["ada_lovelace", "charles_babbage"],
      },
    ])
  );
  expect(clusters.map((c) => c.key)).toEqual([
    "john_von_neumann+alan_turing",
    "charles_babbage+ada_lovelace",
  ]);
  // Main members sort by birth year, whatever order the ids were stored in.
  expect(clusters[1].mains.map((n) => n.id)).toEqual([
    "charles_babbage",
    "ada_lovelace",
  ]);
});

test("bridging people join the circle holding most of their main neighbors", () => {
  const clusters = computeClusters(
    withCircles([
      { member_ids: ["ada_lovelace", "charles_babbage"] },
      { member_ids: ["alan_turing", "john_von_neumann"] },
    ])
  );
  expect(clusters[0].secondaries.map((n) => n.id)).toEqual(["mary_somerville"]);
  expect(clusters[1].secondaries.map((n) => n.id)).toEqual(["max_newman"]);
  // A missing key is rebuilt from the sorted main ids.
  expect(clusters[0].key).toBe("charles_babbage+ada_lovelace");
  // Internal ties: main bonds first, then bridging ties strongest-first; the
  // cross-circle Babbage–Turing tie belongs to neither.
  expect(clusters[0].links.map((l) => `${l.source}-${l.target}`)).toEqual([
    "ada_lovelace-charles_babbage",
    "ada_lovelace-mary_somerville",
    "charles_babbage-mary_somerville",
  ]);
});

test("circles with fewer than two resolvable main members are skipped", () => {
  const clusters = computeClusters(
    withCircles([
      { member_ids: ["ada_lovelace", "unknown_person"] },
      { member_ids: ["alan_turing", "max_newman"] },
      { member_ids: ["alan_turing", "john_von_neumann"] },
    ])
  );
  expect(clusters.map((c) => c.key)).toEqual(["john_von_neumann+alan_turing"]);
});
