import { expect, test } from "@playwright/test";

/* The one browser test the repository keeps. It walks the shortest path that
   touches every part of the application a reader cannot avoid — the landing
   page, the search, a story, a slide change, and the way back — and asserts
   only that each one arrives. Layout, gestures, localization, and everything
   else a screen decides are checked by AI exploration, which sees the page
   rather than a selector; see docs/testing-strategy.md.

   It is deliberately cheap. A scenario that needs its own viewport, a map, a
   timed race, or several seconds of waiting does not belong here. */

test("a reader reaches a story and comes back", async ({ page }, testInfo) => {
  // A thrown script error and a missing asset are the two failures that break
  // the application without breaking any single assertion below: the first
  // leaves an empty screen, the second a portrait that never appears.
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  const siteOrigin = new URL(testInfo.project.use.baseURL).origin;
  const missingAssets = [];
  page.on("response", (response) => {
    const url = new URL(response.url());
    if (response.status() === 404 && url.origin === siteOrigin) {
      missingAssets.push(url.pathname);
    }
  });

  await page.goto("en");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByRole("status")).toContainText(/stories shown/i);

  const search = page.getByRole("textbox", {
    name: "Search people by name, role, or keywords",
  });
  await search.fill("Ada Lovelace");
  await expect(page).toHaveURL(/\/en\?q=Ada(?:\+|%20)Lovelace$/);

  // The collections carousel announces its portraits with the same string, so
  // the accessible name alone does not single out a result card.
  const adaCard = page
    .getByRole("button", { name: "Open the life story of Ada Lovelace" })
    .and(page.locator(".person-card"));
  await adaCard.click();
  await expect(page).toHaveURL(/\/en\/story\/ada_lovelace/);
  await expect(
    page.locator('section[aria-label^="Overview: Ada Lovelace"]')
  ).toBeVisible();

  await page.keyboard.press("ArrowDown");
  await expect(page).toHaveURL(/[?&]slide=1(?:&|$)/);
  // One more, because slide 1 is the chapter title and slide 2 is the first
  // event: the reader has now seen the two kinds of slide a story is made of.
  await page.keyboard.press("ArrowDown");
  await expect(page).toHaveURL(/[?&]slide=2(?:&|$)/);
  await expect(page.locator(".slide-status")).toHaveText(/Slide \d+ of \d+: /);

  await page
    .getByRole("button", {
      name: "Close story and return to the landing page",
    })
    .click();
  await expect(page).toHaveURL(/\/en\?q=Ada(?:\+|%20)Lovelace$/);
  await expect(search).toHaveValue("Ada Lovelace");

  expect(pageErrors).toEqual([]);
  expect(missingAssets).toEqual([]);
});
