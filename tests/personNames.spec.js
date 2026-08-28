import { test, expect } from "@playwright/test";
import { segmentPersonMentions } from "../src/utils/personNames.js";

// The matcher's rules are mostly about what it refuses to match, and every
// rule here is anchored in a real case from data/: a diacritic that broke
// `\b`, a German genitive, a relative who shares the subject's surname.
// Expectations are written as the rendered prose with matches in ⟦…⟧ so a
// failure reads like the sentence the reader would see.
function render(text, people) {
  return segmentPersonMentions(text, people)
    .map((segment) =>
      segment.type === "person"
        ? `⟦${segment.content}|${segment.person.id}⟧`
        : segment.content
    )
    .join("");
}

const person = (id, name, aliases) => ({
  id,
  name,
  ...(aliases ? { aliases } : {}),
});

const architects = [
  person("gaudi", "Antoni Gaudí"),
  person("mackintosh", "Charles Rennie Mackintosh"),
  person("wright", "Frank Lloyd Wright"),
  person("frei_otto", "Frei Otto"),
  person("hundertwasser", "Friedensreich Hundertwasser"),
  person("wagner", "Otto Wagner"),
];

const revolutionaries = [
  person("abigail_adams", "Abigail Adams"),
  person("washington", "George Washington"),
];

const pioneers = [
  person("von_neumann", "John von Neumann"),
  person("turing", "Alan Turing"),
  person("lovelace", "Ada Lovelace"),
  person("zuse", "Konrad Zuse"),
  person("nixdorf", "Heinz Nixdorf"),
  person("bush", "Vannevar Bush"),
];

const bamberg = [
  person("henry_ii", "Henry II", ["Heinrich II."]),
  person("cunigunde", "Cunigunde of Luxembourg", ["Kunigunde von Luxemburg"]),
  person("hoffmann", "E. T. A. Hoffmann"),
];

test("matches names carrying diacritics", () => {
  expect(render("Hundertwasser found in Gaudí a precedent.", architects)).toBe(
    "⟦Hundertwasser|hundertwasser⟧ found in ⟦Gaudí|gaudi⟧ a precedent."
  );
});

test("matches every mention, not only the first", () => {
  expect(
    render(
      "Wagner taught in Vienna. Later Wagner joined the Secession, and Wagner left.",
      architects
    )
  ).toBe(
    "⟦Wagner|wagner⟧ taught in Vienna. Later ⟦Wagner|wagner⟧ joined the Secession, and ⟦Wagner|wagner⟧ left."
  );
});

test("keeps an English possessive outside the highlight", () => {
  expect(render("Wright’s work shaped him.", architects)).toBe(
    "⟦Wright|wright⟧’s work shaped him."
  );
});

test("takes a German genitive into the highlight", () => {
  expect(render("Wrights Ideen organischer Architektur.", architects)).toBe(
    "⟦Wrights|wright⟧ Ideen organischer Architektur."
  );
  expect(render("Ada Lovelaces Notes von 1843.", pioneers)).toBe(
    "⟦Ada Lovelaces|lovelace⟧ Notes von 1843."
  );
});

test("a capitalized German noun after a surname does not block the match", () => {
  expect(render("Alan Turings Aufsatz von 1936.", pioneers)).toBe(
    "⟦Alan Turings|turing⟧ Aufsatz von 1936."
  );
});

test("splits hyphenated German compounds at the name", () => {
  expect(
    render(
      "Sie erwogen, Zuse-Software auf Nixdorf-Computer zu übertragen.",
      pioneers
    )
  ).toBe(
    "Sie erwogen, ⟦Zuse|zuse⟧-Software auf ⟦Nixdorf|nixdorf⟧-Computer zu übertragen."
  );
});

test("prefers the person whose full name is spelled out", () => {
  // "Otto" is Frei Otto's surname and Otto Wagner's given name.
  expect(render("Otto Wagner designed the station.", architects)).toBe(
    "⟦Otto Wagner|wagner⟧ designed the station."
  );
  expect(render("That encounter exposed Otto to new ideas.", architects)).toBe(
    "That encounter exposed ⟦Otto|frei_otto⟧ to new ideas."
  );
});

test("does not hand another person's full name to a shared surname", () => {
  expect(
    render("She corresponded with John Adams for years.", revolutionaries)
  ).toBe("She corresponded with John Adams for years.");
  expect(
    render("Adams’s letters mixed household and politics.", revolutionaries)
  ).toBe("⟦Adams|abigail_adams⟧’s letters mixed household and politics.");
});

test("two names in a row are two people, not one blocking the other", () => {
  // German word order puts the object straight behind the subject, so the
  // capitalized word in front of "Wright" is Frei Otto rather than a stranger's
  // given name — the case the guard above exists for.
  expect(render("Später besuchte Otto Wright in Taliesin.", architects)).toBe(
    "Später besuchte ⟦Otto|frei_otto⟧ ⟦Wright|wright⟧ in Taliesin."
  );
  // The guard still holds when nothing in front of the surname is a mention.
  expect(render("Später besuchte Ernst Wright in Taliesin.", architects)).toBe(
    "Später besuchte Ernst Wright in Taliesin."
  );
});

test("reads through an apposition and a title", () => {
  expect(
    render("Die Politikerin Abigail Adams schrieb Briefe.", revolutionaries)
  ).toBe("Die Politikerin ⟦Abigail Adams|abigail_adams⟧ schrieb Briefe.");
  expect(render("General Washington took command.", revolutionaries)).toBe(
    "General ⟦Washington|washington⟧ took command."
  );
  expect(render("Präsident Washington handelte.", revolutionaries)).toBe(
    "Präsident ⟦Washington|washington⟧ handelte."
  );
});

test("a title plus a given name stays with the monarch it names", () => {
  expect(render("King George refused the petition.", revolutionaries)).toBe(
    "King George refused the petition."
  );
  expect(render("Kaiser Heinrich gründete das Bistum.", bamberg)).toBe(
    "Kaiser ⟦Heinrich|henry_ii⟧ gründete das Bistum."
  );
});

// German capitalizes every noun, so an everyday word walks into a name run the
// way "King" does in English — and it does so far more often, since the
// capitalization carries no signal at all. Both people here are real German
// surnames; only one of them is also a word.
const germans = [person("wolf", "Christa Wolf"), person("zuse", "Konrad Zuse")];

test("an everyday German word needs its given name beside it", () => {
  expect(render("Der Wolf lief durch den Wald.", germans)).toBe(
    "Der Wolf lief durch den Wald."
  );
  expect(render("Christa Wolf las aus dem Manuskript.", germans)).toBe(
    "⟦Christa Wolf|wolf⟧ las aus dem Manuskript."
  );
  // A surname that is nobody's everyday word still stands on its own.
  expect(render("Zuse baute die Z3 in Berlin.", germans)).toBe(
    "⟦Zuse|zuse⟧ baute die Z3 in Berlin."
  );
});

test("short given names are not evidence on their own", () => {
  expect(render("He met John Mauchly around ENIAC.", pioneers)).toBe(
    "He met John Mauchly around ENIAC."
  );
  expect(render("Vannevar sketched the memex.", pioneers)).toBe(
    "⟦Vannevar|bush⟧ sketched the memex."
  );
});

// "he and his son Aage advised Allied researchers": the apposition names one
// person, so the given name no longer has to carry the identification alone.
const bohrs = [
  {
    id: "aage",
    name: "Aage Bohr",
    relationship_type: "family/child",
  },
  {
    id: "margrethe",
    name: "Margrethe Nørlund Bohr",
    relationship_type: "family/spouse",
  },
];

test("a kinship apposition names a relative by their given name", () => {
  expect(render("He and his son Aage advised the researchers.", bohrs)).toBe(
    "He and his son ⟦Aage|aage⟧ advised the researchers."
  );
  expect(render("Their second daughter, Aage, followed.", bohrs)).toBe(
    "Their second daughter, ⟦Aage|aage⟧, followed."
  );
});

test("a German kinship noun is not a stranger's given name", () => {
  // "Frau" and "Sohn" are capitalized, which otherwise reads as another
  // person standing in front of a shared surname.
  expect(
    render("Er floh mit seiner Frau Margrethe nach Schweden.", bohrs)
  ).toBe("Er floh mit seiner Frau ⟦Margrethe|margrethe⟧ nach Schweden.");
  expect(render("Er und sein Sohn Aage berieten die Forscher.", bohrs)).toBe(
    "Er und sein Sohn ⟦Aage|aage⟧ berieten die Forscher."
  );
});

test("a kinship apposition only reaches the people the data calls relatives", () => {
  const turings = [
    {
      id: "john_turing",
      name: "John Ferrier Turing",
      relationship_type: "family/sibling",
    },
    {
      id: "von_neumann",
      name: "John von Neumann",
      relationship_type: "academic/colleague",
    },
  ];
  expect(render("He grew up with his older brother John.", turings)).toBe(
    "He grew up with his older brother ⟦John|john_turing⟧."
  );
  // Without the brother in the list the colleague still does not take the
  // apposition, and a kinship cue does not license a bare given name anywhere
  // else in the sentence.
  expect(render("He grew up with his older brother John.", [turings[1]])).toBe(
    "He grew up with his older brother John."
  );
  expect(render("His brother stayed home, and John visited.", turings)).toBe(
    "His brother stayed home, and John visited."
  );
});

test("keeps the particle with the surname", () => {
  expect(render("Einstein and von Neumann met again.", pioneers)).toBe(
    "Einstein and ⟦von Neumann|von_neumann⟧ met again."
  );
});

test("regnal numerals belong to one ruler", () => {
  expect(
    render("The couple Henry II and Cunigunde ruled together.", bamberg)
  ).toBe(
    "The couple ⟦Henry II|henry_ii⟧ and ⟦Cunigunde|cunigunde⟧ ruled together."
  );
  expect(
    render("When Henry died childless, Cunigunde steered on.", bamberg)
  ).toBe(
    "When ⟦Henry|henry_ii⟧ died childless, ⟦Cunigunde|cunigunde⟧ steered on."
  );
  expect(
    render(
      "His predecessor Otto III had died, and Henry III came later.",
      bamberg
    )
  ).toBe("His predecessor Otto III had died, and Henry III came later.");
});

test("recognizes the translated name a story actually prints", () => {
  expect(
    render("Heinrich II. gründete das Bistum; Kunigunde blieb.", bamberg)
  ).toBe(
    "⟦Heinrich II|henry_ii⟧. gründete das Bistum; ⟦Kunigunde|cunigunde⟧ blieb."
  );
});

test("holds initials together and matches the surname alone", () => {
  expect(
    render("E. T. A. Hoffmann lived here; Hoffmann wrote at night.", bamberg)
  ).toBe(
    "⟦E. T. A. Hoffmann|hoffmann⟧ lived here; ⟦Hoffmann|hoffmann⟧ wrote at night."
  );
});

test("a geographic epithet is not a surname", () => {
  expect(render("The county of Luxembourg was distant.", bamberg)).toBe(
    "The county of Luxembourg was distant."
  );
});

test("only the head of a double surname stands for the person", () => {
  const catalans = [person("father", "Francesc Gaudí i Serra")];
  expect(render("Francesc Gaudí i Serra worked copper.", catalans)).toBe(
    "⟦Francesc Gaudí i Serra|father⟧ worked copper."
  );
  expect(render("The Serra workshop stood nearby.", catalans)).toBe(
    "The Serra workshop stood nearby."
  );
});

test("a middle name does not stand for the person", () => {
  const smiths = [person("smith", "Elizabeth Quincy Smith")];
  expect(render("They sailed from Quincy that spring.", smiths)).toBe(
    "They sailed from Quincy that spring."
  );
});

test("leaves an equally good tie unhighlighted", () => {
  const bothAdams = [
    person("abigail", "Abigail Adams"),
    person("john", "John Adams"),
  ];
  expect(render("Adams argued for independence.", bothAdams)).toBe(
    "Adams argued for independence."
  );
});

test("segments always reconstruct the original text", () => {
  const text = "Ada Lovelaces Notes; Gaudí; von Neumann — Zuse-Software.";
  const rebuilt = segmentPersonMentions(text, [...pioneers, ...architects])
    .map((segment) => segment.content)
    .join("");
  expect(rebuilt).toBe(text);
});

test("handles empty input", () => {
  expect(render("", pioneers)).toBe("");
  expect(render("Plain prose.", [])).toBe("Plain prose.");
});
