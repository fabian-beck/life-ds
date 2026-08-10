import { test, expect } from "@playwright/test";
import { parseDescriptionSegments } from "../src/utils/story/prose.js";

// An annotation is placed either by the `[[term|display]]` markup the
// generator is asked to write, or — when it wrote the explanation and forgot
// the markup — by finding the term in the prose. Every case here is a real one
// from data/: the institutions that arrived unmarked are what a reader notices,
// because the names most in need of a gloss were the ones without one.
// Expectations are written as the rendered prose with annotations in ⟦…⟧ and
// person mentions in «…» so a failure reads like the sentence on the slide.
function render(description, annotations, people = [], subjectName = null) {
  return parseDescriptionSegments(description, annotations, people, subjectName)
    .map((segment) => {
      if (segment.type === "annotation") {
        return `⟦${segment.displayText}|${segment.termKey}⟧`;
      }
      if (segment.type === "person") return `«${segment.content}»`;
      return segment.content;
    })
    .join("");
}

const gloss = (term, explanation = "An explanation.") => ({
  [term]: { explanation },
});

test("marked-up terms are annotated where the markup sits", () => {
  expect(
    render(
      "He led [[Tube Alloys|the British programme]] from London.",
      gloss("Tube Alloys")
    )
  ).toBe("He led ⟦the British programme|Tube Alloys⟧ from London.");
});

test("an unmarked institution is found in the prose", () => {
  expect(
    render(
      "He was involved in establishing CERN and Denmark's Atomic Energy " +
        "Commission, including its Risø research establishment.",
      gloss("Risø")
    )
  ).toBe(
    "He was involved in establishing CERN and Denmark's Atomic Energy " +
      "Commission, including its ⟦Risø|Risø⟧ research establishment."
  );
});

test("a slug key matches the words it stands for", () => {
  expect(
    render(
      "Byron died in Greece while supporting the Greek War of Independence.",
      gloss("Greek_War_of_Independence")
    )
  ).toBe(
    "Byron died in Greece while supporting the " +
      "⟦Greek War of Independence|Greek_War_of_Independence⟧."
  );
});

test("a key qualified by its region matches the plain name", () => {
  expect(
    render("After the family moved from Portland to the countryside.", {
      ...gloss("Portland, Oregon"),
    })
  ).toBe(
    "After the family moved from ⟦Portland|Portland, Oregon⟧ to the countryside."
  );
});

test("a term absent from the prose annotates nothing", () => {
  const description =
    "In 1913, after returning to Copenhagen, Bohr published three papers.";
  expect(render(description, gloss("Manchester"))).toBe(description);
});

test("a term is annotated once, at its first free occurrence", () => {
  expect(
    render(
      "Zuse KG expanded fast, and Zuse KG was over-indebted by 1964.",
      gloss("Zuse KG")
    )
  ).toBe(
    "⟦Zuse KG|Zuse KG⟧ expanded fast, and Zuse KG was over-indebted by 1964."
  );
});

test("a term only matches whole words", () => {
  const description = "The Institute's reactors ran at Risøhalvøen for years.";
  expect(render(description, gloss("Risø"))).toBe(description);
});

test("an unmarked term yields to the person it names", () => {
  expect(
    render(
      "She was the only child of the poet Lord Byron and his wife.",
      gloss("Lord Byron"),
      [{ person_name: "Lord Byron" }]
    )
  ).toBe("She was the only child of the poet «Lord Byron» and his wife.");
});

test("markup still wins over a person sharing the span", () => {
  expect(
    render(
      "She was the only child of the poet [[Lord Byron]] and his wife.",
      gloss("Lord Byron"),
      [{ person_name: "Lord Byron" }]
    )
  ).toBe(
    "She was the only child of the poet ⟦Lord Byron|Lord Byron⟧ and his wife."
  );
});

test("a term containing the subject's own name is still annotated", () => {
  // "Zuse" is the story's subject, so it renders as plain text and holds
  // nothing — the company named after him is free to carry its gloss.
  expect(
    render(
      "Rapid expansion left Zuse KG over-indebted, and Konrad Zuse gave up his share.",
      gloss("Zuse KG"),
      [],
      "Konrad Zuse"
    )
  ).toBe(
    "Rapid expansion left ⟦Zuse KG|Zuse KG⟧ over-indebted, and Konrad Zuse gave up his share."
  );
});

test("an unmarked term never lands inside another annotation's markup", () => {
  expect(
    render(
      "The [[Sonderforschungsbereich|SFB]] 64 programme ran at Stuttgart.",
      { ...gloss("Sonderforschungsbereich"), ...gloss("SFB") }
    )
  ).toBe("The ⟦SFB|Sonderforschungsbereich⟧ 64 programme ran at Stuttgart.");
});
