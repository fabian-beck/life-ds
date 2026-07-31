import { expect, test } from "@playwright/test";
import { writeFile } from "node:fs/promises";

async function capture(page, testInfo, name) {
  const path = testInfo.outputPath(`${name}.png`);
  await page.screenshot({ path, animations: "disabled" });
  await testInfo.attach(name, { path, contentType: "image/png" });
}

function viewportAudit(page) {
  return page.evaluate(() => {
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    const interactive = [
      ...document.querySelectorAll(
        'a[href], button, input, select, textarea, [role="button"]'
      ),
    ];

    const visible = interactive.filter((element) => {
      const style = getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      return (
        style.visibility !== "hidden" &&
        style.display !== "none" &&
        rect.width > 0 &&
        rect.height > 0 &&
        rect.bottom > 0 &&
        rect.top < viewportHeight &&
        rect.right > 0 &&
        rect.left < viewportWidth
      );
    });

    const summarize = (element) => {
      const rect = element.getBoundingClientRect();
      return {
        label:
          element.getAttribute("aria-label") ||
          element.textContent?.trim().replace(/\s+/g, " ").slice(0, 100) ||
          element.tagName.toLowerCase(),
        width: Math.round(rect.width),
        height: Math.round(rect.height),
        left: Math.round(rect.left),
        right: Math.round(rect.right),
      };
    };

    return {
      viewport: { width: viewportWidth, height: viewportHeight },
      documentWidth: document.documentElement.scrollWidth,
      clippedControls: visible
        .filter((element) => {
          const rect = element.getBoundingClientRect();
          return rect.left < -1 || rect.right > viewportWidth + 1;
        })
        .map(summarize),
      smallControls: visible
        .filter((element) => {
          const rect = element.getBoundingClientRect();
          return rect.width < 44 || rect.height < 44;
        })
        .map(summarize),
    };
  });
}

async function attachAudit(testInfo, name, audit) {
  const path = testInfo.outputPath(`${name}-audit.json`);
  await writeFile(path, JSON.stringify(audit, null, 2), "utf8");
  await testInfo.attach(`${name}-audit`, {
    path,
    contentType: "application/json",
  });
  expect(audit.documentWidth).toBeLessThanOrEqual(audit.viewport.width + 1);
}

// The report is a separate page published next to the app, so a broken link
// here fails silently in the application itself: nothing imports it, and no
// other test would notice that the route stopped resolving.
test("technical report is reachable from the landing page", async ({
  page,
}) => {
  await page.goto("en");

  const reportLink = page
    .getByRole("link", { name: /Read the technical report/ })
    .first();
  await expect(reportLink).toHaveAttribute("href", /\/report\/$/);

  await reportLink.click();
  await expect(page).toHaveURL(/\/report\/$/);
  await expect(
    page.getByRole("heading", { level: 1, name: "Life Data Stories" })
  ).toBeVisible();
});

test("core visitor journey", async ({ page }, testInfo) => {
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  // Every asset the app asks for has to exist under the deployment base path.
  // A site-absolute path from the data files that never passed through
  // `assetUrl` requests the domain root instead and answers 404, which shows up
  // as a broken portrait rather than as a script error — invisible to the
  // checks above. Collecting the misses makes that failure loud.
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
  await capture(page, testInfo, "01-landing");
  await attachAudit(testInfo, "landing", await viewportAudit(page));

  const search = page.getByRole("textbox", {
    name: "Search people by name, role, or keywords",
  });
  const skipToSearch = page.getByRole("button", { name: "Skip to search" });
  await expect(page.locator(".indicator.active")).toHaveAttribute(
    "aria-current",
    "true"
  );
  await page.keyboard.press("Tab");
  await expect(skipToSearch).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(search).toBeFocused();

  const roleChip = page.locator(".tag-chip").first();
  await roleChip.click();
  await expect(page).toHaveURL(/[?&]roles=/);
  await roleChip.click();
  await expect(page).not.toHaveURL(/[?&]roles=/);

  await search.fill("Ada Lovelace");
  await expect(page).toHaveURL(/\/en\?q=Ada(?:\+|%20)Lovelace$/);
  const adaCard = page.getByRole("button", {
    name: "Open life story for Ada Lovelace",
  });
  await expect(adaCard).toBeVisible();
  await expect(page.getByRole("status")).toContainText("1");
  await expect(page.locator(".header-container")).toBeVisible();
  await expect(page.locator(".filters-right")).toBeVisible();

  if (testInfo.project.name === "mobile-chromium") {
    const resultIsInViewport = await adaCard.evaluate((element) => {
      const rect = element.getBoundingClientRect();
      return rect.top >= 0 && rect.top < window.innerHeight;
    });
    expect(resultIsInViewport).toBe(true);
  }

  await capture(page, testInfo, "02-filtered-landing");
  await attachAudit(testInfo, "filtered-landing", await viewportAudit(page));

  await adaCard.click();
  await expect(page).toHaveURL(/\/en\/story\/ada_lovelace/);
  await expect(
    page.locator('section[aria-label^="Overview: Ada Lovelace"]')
  ).toBeVisible();
  await capture(page, testInfo, "03-story-overview");
  await attachAudit(testInfo, "story-overview", await viewportAudit(page));

  await page.keyboard.press("ArrowDown");
  await expect(page).toHaveURL(/[?&]slide=1(?:&|$)/);
  await capture(page, testInfo, "04-story-chapter");

  await page.keyboard.press("PageDown");
  await expect(page).toHaveURL(/[?&]slide=2(?:&|$)/);
  await capture(page, testInfo, "05-story-event");
  await attachAudit(testInfo, "story-event", await viewportAudit(page));

  await page.evaluate(async () => {
    const languages = ["de", "en", "de", "en", "de", "en", "de", "en", "de"];
    languages.forEach((language, index) => {
      setTimeout(() => {
        window.location.replace(`#/${language}/story/ada_lovelace?slide=2`);
      }, index * 75);
    });
    await new Promise((resolve) => {
      setTimeout(resolve, languages.length * 75);
    });
  });
  await expect(page).toHaveURL(/\/de\/story\/ada_lovelace\?slide=2$/);

  await page.evaluate(() => {
    window.location.replace("#/en/story/ada_lovelace?slide=2");
  });
  await expect(page).toHaveURL(/\/en\/story\/ada_lovelace\?slide=2$/);
  await expect(
    page.getByRole("button", { name: "Show full network" })
  ).toBeVisible();

  await page.getByRole("button", { name: "Show full network" }).click();
  await expect(page.locator(".network-modal")).toBeVisible();
  await capture(page, testInfo, "06-network-modal");
  await page.getByRole("button", { name: "Close modal" }).click();
  await expect(page.locator(".network-modal")).toBeHidden();

  await page.goBack();
  await expect(page).toHaveURL(/\/en\?q=Ada(?:\+|%20)Lovelace$/);
  await expect(search).toHaveValue("Ada Lovelace");
  await page.getByRole("button", { name: "Clear search" }).click();
  await expect(page).toHaveURL(/\/en$/);

  await page
    .getByRole("button", { name: "Explore collection" })
    .first()
    .click();
  await expect(page).toHaveURL(/\/en\/meta\//);
  await expect(
    page.getByRole("button", { name: "Back to Stories" }).first()
  ).toBeVisible();

  // The article wears the story's own identity: colors and fonts from
  // meta_story_styles.json, plus the ornamental rule under the dateline.
  await expect(page.locator(".meta-story-view.styled")).toBeVisible();

  // The social network graph draws each main person as an SVG <image>, the one
  // portrait in the app that is not an <img>. Scrolling it into view makes the
  // response listener see those requests.
  const networkSection = page.locator(".network-section .mnet");
  await networkSection.scrollIntoViewIfNeeded();
  await expect(networkSection.locator("image").first()).toBeVisible();
  await capture(page, testInfo, "07-meta-story-network");

  await page.getByRole("button", { name: "Back to Stories" }).first().click();
  await expect(page).toHaveURL(/\/en$/);
  await page.goto("en#/en/exhibition/ada_lovelace");
  await expect(page).toHaveURL(/\/en\/story\/ada_lovelace$/);
  await expect(
    page.locator('section[aria-label^="Overview: Ada Lovelace"]')
  ).toBeVisible();

  expect(pageErrors).toEqual([]);
  expect(missingAssets).toEqual([]);
});
