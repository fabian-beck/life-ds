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

test("landing, search, story navigation, and network modal", async ({
  page,
}, testInfo) => {
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.goto("/en");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByRole("status")).toContainText(/stories shown/i);
  await capture(page, testInfo, "01-landing");
  await attachAudit(testInfo, "landing", await viewportAudit(page));

  const search = page.getByRole("textbox", {
    name: "Search people by name, role, or keywords",
  });
  await search.fill("Ada Lovelace");
  const adaCard = page.getByRole("button", {
    name: "Open life story for Ada Lovelace",
  });
  await expect(adaCard).toBeVisible();
  await expect(page.getByRole("status")).toContainText("1");

  if (testInfo.project.name === "mobile-chromium") {
    await expect(page.locator(".header-container")).toBeHidden();
    await expect(page.locator(".filters-right")).toBeHidden();

    const resultIsInViewport = await adaCard.evaluate((element) => {
      const rect = element.getBoundingClientRect();
      return rect.top >= 0 && rect.top < window.innerHeight;
    });
    expect(resultIsInViewport).toBe(true);
  } else {
    await expect(page.locator(".header-container")).toBeVisible();
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

  await page.keyboard.press("ArrowRight");
  await expect(page).toHaveURL(/[?&]slide=1(?:&|$)/);
  await capture(page, testInfo, "04-story-chapter");

  await page.keyboard.press("ArrowRight");
  await expect(page).toHaveURL(/[?&]slide=2(?:&|$)/);
  await capture(page, testInfo, "05-story-event");
  await attachAudit(testInfo, "story-event", await viewportAudit(page));

  await page.getByRole("button", { name: "Show full network" }).click();
  await expect(page.locator(".network-modal")).toBeVisible();
  await capture(page, testInfo, "06-network-modal");
  await page.getByRole("button", { name: "Close modal" }).click();
  await expect(page.locator(".network-modal")).toBeHidden();

  await page
    .getByRole("button", {
      name: "Close story and return to the landing page",
    })
    .click();
  await expect(page).toHaveURL(/\/en$/);

  expect(pageErrors).toEqual([]);
});
