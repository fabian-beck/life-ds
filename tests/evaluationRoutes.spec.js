import { expect, test } from "@playwright/test";
import { parseRoute, viewKey } from "../src/utils/evaluation/routes.js";

/* The analysis reads the application's routes back out of the log. These
   pin the shapes App.svelte produces, including the ones a reader arrives
   on from a bookmark. */

test("a person story route names the story and its query", () => {
  const route = parseRoute(
    "/en/story/ada_lovelace",
    "slide=3&network=1&from_meta=computing_pioneers&from_landing=q%3DAda"
  );
  expect(route.kind).toBe("story");
  expect(route.id).toBe("ada_lovelace");
  expect(route.lang).toBe("en");
  expect(route.slide).toBe(3);
  expect(route.network).toBe(true);
  expect(route.timeline).toBe(false);
  expect(route.fromMeta).toBe("computing_pioneers");
  expect(route.fromLanding).toBe("q=Ada");
  expect(viewKey(route)).toBe("story:ada_lovelace");
});

test("the landing is the landing with or without a language", () => {
  expect(parseRoute("/").kind).toBe("landing");
  expect(parseRoute("/de").kind).toBe("landing");
  expect(parseRoute("/de/", "q=Ada&roles=poet,mathematician").roles).toEqual([
    "poet",
    "mathematician",
  ]);
  expect(viewKey(parseRoute("/en"))).toBe("landing");
});

test("a meta story and the retired exhibition route resolve", () => {
  expect(parseRoute("/de/meta/computing_pioneers")).toMatchObject({
    kind: "meta",
    id: "computing_pioneers",
    lang: "de",
  });
  expect(parseRoute("/en/exhibition/alan_turing").kind).toBe("story");
});

test("a malformed query never yields NaN", () => {
  const route = parseRoute("/en/story/x", "slide=abc&event=");
  expect(route.slide).toBe(null);
  expect(route.event).toBe(null);
  expect(parseRoute("/nothing/here").kind).toBe("other");
});
