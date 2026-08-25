import { test, expect } from "@playwright/test";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
// Node requires the import attribute for JSON modules; the locales are read
// here rather than restated so the test cannot drift from what ships.
import en from "../src/locales/en.json" with { type: "json" };
import de from "../src/locales/de.json" with { type: "json" };

// Keys under these prefixes are built at runtime from data tokens or a
// count, so no source file spells them out. Declaring the prefixes here is
// the documentation of which key families are data-driven; a family removed
// from the code should be removed here so its entries start counting as
// dead again.
const DYNAMIC_PREFIXES = [
  // relationshipLabels.js: `network.role.${token}_${one|other}`
  "network.role.",
  // relationshipLabels.js: `network.category.${token}`
  "network.category.",
  // PersonChip.svelte: `network.entity.${entity_kind}` over the collective
  // entity kinds (organization, group)
  "network.entity.",
  // NetworkModal.svelte: `${box.labelKey}_${one|other}` over the family
  // layer boxes, whose labelKey literals name only the key's stem
  "network.family.",
  // relationshipLabels.js: `person.${family}_value.${token}`
  "person.strength_value.",
  "person.frequency_value.",
  "person.influence_value.",
  // eventClassLabels.js: `story.event_class.${type|subtype}`
  "story.event_class.",
  // eventClassLabels.js: `story.publication_type.${publicationType}`
  "story.publication_type.",
  // Timeline.svelte: `timeline.event_${one|other}`
  "timeline.event_",
];

// Everything a key could be referenced from: application code, tests, and
// the Python tooling. The locale files themselves do not count (they are
// data, not references), and neither does this spec — it names prefixes,
// and must not keep a key alive by asserting on it.
const SCAN_ROOTS = ["src", "tests", "scripts"];
const SCAN_EXTENSIONS = [".js", ".svelte", ".py"];

const projectRoot = fileURLToPath(new URL("..", import.meta.url));

function sourceFiles() {
  const files = [];
  for (const root of SCAN_ROOTS) {
    for (const entry of readdirSync(join(projectRoot, root), {
      recursive: true,
    })) {
      const relative = join(root, entry).replaceAll("\\", "/");
      if (relative === "tests/localeCoverage.spec.js") continue;
      if (SCAN_EXTENSIONS.some((extension) => relative.endsWith(extension))) {
        files.push(relative);
      }
    }
  }
  return files;
}

const sources = sourceFiles().map((file) =>
  readFileSync(join(projectRoot, file), "utf8")
);

test("the two locales carry the same keys", () => {
  expect(Object.keys(de).sort()).toEqual(Object.keys(en).sort());
});

test("every key is referenced by a literal or covered by a dynamic prefix", () => {
  const dead = Object.keys(en).filter(
    (key) =>
      !DYNAMIC_PREFIXES.some((prefix) => key.startsWith(prefix)) &&
      !sources.some((text) => text.includes(key))
  );
  // A key listed here occurs nowhere in src/, tests/, or scripts/ — it was
  // translated and shipped for UI that no longer exists. Remove it from both
  // locale files (or, if it belongs to a data-driven family, declare the
  // family's prefix above).
  expect(dead).toEqual([]);
});

test("every declared dynamic prefix has at least one entry", () => {
  const empty = DYNAMIC_PREFIXES.filter(
    (prefix) => !Object.keys(en).some((key) => key.startsWith(prefix))
  );
  expect(empty).toEqual([]);
});

test("every literal lookup in the application resolves in both locales", () => {
  // A key that does not resolve renders as its own identifier, so a typo or
  // a renamed key ships as literal `story.foo_bar` on screen. This covers
  // the `$_("...")` call sites; keys built at runtime are covered by the
  // prefix declarations above.
  const missing = new Set();
  for (const text of sources) {
    for (const match of text.matchAll(/\$_\(\s*"([^"]+)"/g)) {
      const key = match[1];
      if (!(key in en)) missing.add(`${key} (en)`);
      if (!(key in de)) missing.add(`${key} (de)`);
    }
  }
  expect([...missing]).toEqual([]);
});
