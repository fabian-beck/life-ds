import { test, expect } from "@playwright/test";
import {
  computeYearsLabel,
  createDateFormatters,
  extractYear,
  formatSingleDate,
  toIsoInstant,
  toTimestamp,
} from "../src/utils/storyHelpers.js";

// The registry writes pre-1000 years both ways — "0975-01-01" for Cunigunde,
// "0973-05-06" for Henry II — and nothing stops a B.C. date from arriving.
// Every expectation here is a shape the data does or plausibly could hold.

test("expands the year to a form the date parser accepts", () => {
  expect(toIsoInstant("1955-04-18")).toBe("1955-04-18T00:00:00Z");
  expect(toIsoInstant("0975-01-01")).toBe("0975-01-01T00:00:00Z");
  expect(toIsoInstant("973-05-06")).toBe("0973-05-06T00:00:00Z");
  expect(toIsoInstant("-000500-03-15")).toBe("-000500-03-15T00:00:00Z");
  expect(toIsoInstant("-500")).toBe("-000500-01-01T00:00:00Z");
});

test("fills in the parts a coarser precision leaves out", () => {
  expect(toIsoInstant("1938")).toBe("1938-01-01T00:00:00Z");
  expect(toIsoInstant("1938-05")).toBe("1938-05-01T00:00:00Z");
});

test("rejects what is not a date", () => {
  expect(toIsoInstant("")).toBeNull();
  expect(toIsoInstant("circa 1500")).toBeNull();
  expect(toIsoInstant("1955-04-18T09:00:00Z")).toBeNull();
  expect(toIsoInstant(null)).toBeNull();
});

test("writes 1 B.C. as year zero, the only form the parser takes", () => {
  // "-000000" is not a legal expanded year, so the sign has to be dropped.
  expect(toIsoInstant("-0000")).toBe("0000-01-01T00:00:00Z");
  expect(extractYear("0000-01-01")).toBe(0);
});

test("reads the year regardless of padding or era", () => {
  expect(extractYear("973-05-06")).toBe(973);
  expect(extractYear("0975-01-01")).toBe(975);
  expect(extractYear("1024-07-13")).toBe(1024);
  // ISO 8601 counts astronomically: "-000500" is 501 B.C.
  expect(extractYear("-000500-01-01")).toBe(-500);
  expect(Number.isNaN(extractYear(undefined))).toBe(true);
});

test("orders events across the millennium boundary", () => {
  const at = (date) => toTimestamp({ date });
  expect(at("973-05-06")).toBeLessThan(at("0975-01-01"));
  expect(at("0975-01-01")).toBeLessThan(at("1024-07-13"));
  expect(at("-000500-01-01")).toBeLessThan(at("0973-05-06"));
  expect(toTimestamp({})).toBe(Number.POSITIVE_INFINITY);
});

test("labels a pre-1000 lifespan the same on every surface", () => {
  // Issue #61: the landing card showed "973-–1024" and "0975–1040".
  expect(
    computeYearsLabel({ birthDate: "0973-05-06", deathDate: "1024-07-13" })
  ).toBe("973 - 1024");
  expect(
    computeYearsLabel({ birthDate: "973-05-06", deathDate: "1024-07-13" })
  ).toBe("973 - 1024");
  expect(
    computeYearsLabel({ birthDate: "0975-01-01", deathDate: "1040-03-03" })
  ).toBe("975 - 1040");
});

test("accepts either field naming and a missing death date", () => {
  expect(
    computeYearsLabel({ birth_date: "1912-06-23", death_date: "1954-06-07" })
  ).toBe("1912 - 1954");
  expect(computeYearsLabel({ birthDate: "1879-03-14" })).toBe("1879");
  expect(computeYearsLabel({ deathDate: "1955-04-18" })).toBe("");
  expect(computeYearsLabel(null)).toBe("");
});

test("names the era for a lifespan before the common era", () => {
  // Astronomical numbering again: -000469 is 470 B.C., -000398 is 399 B.C.
  const person = { birthDate: "-000469-01-01", deathDate: "-000398-01-01" };
  expect(computeYearsLabel(person, "en")).toBe("470 BC - 399 BC");
  expect(computeYearsLabel(person, "de")).toBe("470 v. Chr. - 399 v. Chr.");
});

test("formats a single date without losing the day to the time zone", () => {
  const formatters = createDateFormatters("en");
  expect(formatSingleDate("973-05-06", "day", formatters)).toBe("May 6, 973");
  expect(formatSingleDate("1938-05", "month", formatters)).toBe("May 1938");
  expect(formatSingleDate("1938", "year", formatters)).toBe("1938");
  expect(formatSingleDate("", "day", formatters)).toBeNull();
  expect(formatSingleDate("circa 1500", "day", formatters)).toBeNull();
});

test("formats a date before the common era with its era", () => {
  const formatters = createDateFormatters("en");
  expect(formatSingleDate("-000399-01-01", "day", formatters)).toBe(
    "January 1, 400 BC"
  );
  expect(formatSingleDate("-000399", "year", formatters)).toBe("400 BC");
});
