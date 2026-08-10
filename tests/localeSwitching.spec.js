import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

// App.svelte loads a story's documents through one shared loader now, and the
// generation counters that decide whose answer may be written stayed in the
// component. They guard a race that is invisible on a fast machine, where
// every load resolves in the order it was asked for — so this test makes the
// slow one actually slow, and checks that its late answer is discarded.

const dataset = (path) =>
  JSON.parse(
    readFileSync(
      fileURLToPath(new URL(`../data/people/${path}`, import.meta.url)),
      "utf8"
    )
  );

const GERMAN = dataset("konrad_zuse/de/life_events.json");
const ENGLISH = dataset("konrad_zuse/life_events.json");

test("a slow load that lands late does not overwrite the story on screen", async ({
  page,
}) => {
  // The German dataset takes two seconds; the English one is immediate. So the
  // reader asks for German, changes their mind, and German arrives afterwards.
  await page.route("**/konrad_zuse/de/life_events.json*", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 2000));
    await route.continue();
  });

  await page.goto("en#/de/story/konrad_zuse?slide=1");
  await page.evaluate(() => {
    window.location.replace("#/en/story/konrad_zuse?slide=1");
  });

  await expect(page).toHaveURL(/\/en\/story\/konrad_zuse/);
  await expect(page.locator(".slides")).toContainText(ENGLISH.events[0].title, {
    timeout: 15000,
  });

  // Long enough for the German answer to have arrived and been refused.
  await page.waitForTimeout(3000);
  await expect(page.locator(".slides")).toContainText(ENGLISH.events[0].title);
  await expect(page.locator(".slides")).not.toContainText(
    GERMAN.events[0].title
  );
});

test("rapid language switching leaves the story in the language it lands on", async ({
  page,
}) => {
  await page.goto("en#/en/story/konrad_zuse?slide=1");
  await expect(page.locator(".slide").first()).toBeVisible();

  await page.evaluate(async () => {
    const languages = ["de", "en", "de", "en", "de"];
    languages.forEach((language, index) => {
      setTimeout(() => {
        window.location.replace(`#/${language}/story/konrad_zuse?slide=1`);
      }, index * 60);
    });
    await new Promise((resolve) => setTimeout(resolve, 600));
  });

  await expect(page).toHaveURL(/\/de\/story\/konrad_zuse/);
  await expect(page.locator(".slides")).toContainText(GERMAN.events[0].title, {
    timeout: 15000,
  });
});
