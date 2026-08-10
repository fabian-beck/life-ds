import { test, expect } from "@playwright/test";
import { getPublicationSource } from "../src/utils/story/images.js";

// A publication slide names a work and has to offer somewhere to follow it.
// The link in the data was verified by `scripts/enrich_publication_links.py`;
// the search is what the interface owes a work that has no record anywhere,
// and it is built here so it follows the reader's language.

test("a resolved link is offered as itself", () => {
  const source = getPublicationSource(
    {
      type: "publication",
      title: "On the Constitution of Atoms and Molecules",
      source_link: {
        url: "https://en.wikisource.org/wiki/On_the_Constitution_of_Atoms_and_Molecules",
        kind: "wikisource",
        site: "Wikisource",
      },
    },
    "Niels Bohr",
    "en"
  );

  expect(source).toMatchObject({
    url: "https://en.wikisource.org/wiki/On_the_Constitution_of_Atoms_and_Molecules",
    site: "Wikisource",
    kind: "wikisource",
    isSearch: false,
  });
});

test("a link without a site name falls back to the host", () => {
  const source = getPublicationSource(
    {
      type: "publication",
      title: "Über das Element 93",
      source_link: { url: "https://doi.org/10.1002/ange.19340472004" },
    },
    "Ida Noddack",
    "de"
  );

  expect(source.site).toBe("doi.org");
  expect(source.isSearch).toBe(false);
});

test("a work with no record becomes a search for it, by its author", () => {
  const source = getPublicationSource(
    { type: "publication", title: "Das Rhenium" },
    "Ida Noddack",
    "en"
  );

  expect(source.isSearch).toBe(true);
  expect(source.url).toBe(
    "https://en.wikipedia.org/w/index.php?search=Das%20Rhenium%20Ida%20Noddack"
  );
});

test("the search follows the reader's language", () => {
  const source = getPublicationSource(
    { type: "publication", title: "Das Rhenium" },
    "Ida Noddack",
    "de"
  );

  expect(source.url).toBe(
    "https://de.wikipedia.org/w/index.php?search=Das%20Rhenium%20Ida%20Noddack"
  );
});

test("an unexpected language code does not build a broken host", () => {
  const source = getPublicationSource(
    { type: "publication", title: "Das Rhenium" },
    "Ida Noddack",
    "en-US"
  );

  expect(source.url.startsWith("https://en.wikipedia.org/")).toBe(true);
});

test("nothing is offered for events that are not publications", () => {
  expect(getPublicationSource(null, "Ida Noddack", "en")).toBeNull();
  expect(
    getPublicationSource({ type: "invention", title: "Rhenium" }, "x", "en")
  ).toBeNull();
  expect(
    getPublicationSource({ type: "publication", title: "  " }, "x", "en")
  ).toBeNull();
});
