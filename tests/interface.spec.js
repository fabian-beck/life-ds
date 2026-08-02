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

  // The carousel portraits sit early in the tab order, and their slanted
  // clip-path used to swallow the focus ring along with the corners, leaving a
  // keyboard reader with nothing to follow on the entry page. This has to come
  // before the first click of the journey: `:focus-visible` follows the last
  // interaction, and a pointer one suppresses it.
  // Focused without scrolling too — on the mobile viewport, letting the browser
  // bring the portrait into view would move the page under the rest of the
  // journey.
  const portraitOutline = await page
    .locator(".carousel-slide.active .portrait-column")
    .first()
    .evaluate((element) => {
      element.focus({ preventScroll: true });
      const width = parseFloat(getComputedStyle(element).outlineWidth);
      element.blur();
      return width;
    });
  expect(portraitOutline).toBeGreaterThanOrEqual(2);

  // The carousel's play/pause glyph used to be a decorative div: it looked
  // like a media control and was not one.
  await page
    .getByRole("button", { name: "Stop the collections from advancing" })
    .click();
  await expect(
    page.getByRole("button", { name: "Let the collections advance again" })
  ).toHaveAttribute("aria-pressed", "true");

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
    // Polled rather than sampled once: filtering scrolls the results into view
    // with `behavior: "smooth"`, so reading the position the instant the count
    // updates catches the page mid-scroll and fails at random.
    await expect
      .poll(() =>
        adaCard.evaluate((element) => {
          const rect = element.getBoundingClientRect();
          return rect.top >= 0 && rect.top < window.innerHeight;
        })
      )
      .toBe(true);
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

  // The whole story is in the DOM at once. Only the slide on screen may be
  // reachable: Tab used to walk into controls belonging to later slides, and
  // the browser scrolling each one into view carried the reader forward
  // through slides they never opened.
  const slideGuard = await page.evaluate(() => {
    const slides = [
      ...document.querySelectorAll("main.slides > section.slide"),
    ];
    const reachable = [
      ...document.querySelectorAll("main.slides a[href], main.slides button"),
    ].filter((element) => !element.closest("[inert]"));
    return {
      total: slides.length,
      exposed: slides.filter((slide) => !slide.hasAttribute("inert")).length,
      offscreenReachable: reachable.filter((element) => {
        const rect = element.getBoundingClientRect();
        return rect.right < 0 || rect.left > window.innerWidth;
      }).length,
    };
  });
  expect(slideGuard.total).toBeGreaterThan(3);
  expect(slideGuard.exposed).toBe(1);
  expect(slideGuard.offscreenReachable).toBe(0);

  for (let press = 0; press < 8; press += 1) {
    // eslint-disable-next-line no-await-in-loop
    await page.keyboard.press("Tab");
  }
  await expect(page).toHaveURL(/[?&]slide=2(?:&|$)/);

  // Navigating scrolls the container; it inserts nothing. The slide container
  // used to be the live region itself, which announced the entire biography as
  // one insertion on load and then said nothing at all about slide changes.
  await expect(page.locator("main.slides")).not.toHaveAttribute("aria-live");
  await expect(page.locator(".slide-status")).toHaveText(/Slide \d+ of \d+: /);

  // The compact timeline is a scrollbar as much as a set of targets: dragging
  // along it runs through the story under the finger, which is the only way to
  // cross a long life on a phone without tapping once per slide.
  const compactTimeline = page.locator(".dots-container:not(.expanded)");
  const lastSlide = (await compactTimeline.locator(".dot").count()) - 1;
  expect(lastSlide).toBeGreaterThan(3);
  const track = await compactTimeline.boundingBox();
  const trackY = track.y + track.height / 2;
  await page.mouse.move(track.x + 4, trackY);
  await page.mouse.down();
  await page.mouse.move(track.x + track.width - 4, trackY, { steps: 12 });
  await expect(
    compactTimeline.locator(`[data-slide-index="${lastSlide}"]`)
  ).toHaveAttribute("aria-current", "true");
  // The route stays where it was until the finger lifts. A drag passes over
  // every slide between its ends, and rewriting the URL for each one records
  // slides nobody stopped on, and spends the browser's budget for rewrites.
  await expect(page).toHaveURL(/[?&]slide=2(?:&|$)/);
  await page.mouse.up();
  await expect(page).toHaveURL(new RegExp(`[?&]slide=${lastSlide}(?:&|$)`));

  // A tap is still a tap: only travel along the track turns a press into a drag.
  await compactTimeline.locator(".home-dot .dot").click();
  await expect(page).not.toHaveURL(/[?&]slide=/);

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
  // The language churn above leaves the slide container relaying out. Opening
  // the modal has to survive that: a stale sample of the moving scroll position
  // used to rewrite the slide behind this click, which closed the modal again
  // and dropped the parameter that opened it.
  await expect(page).toHaveURL(/\?slide=2&network=1$/);
  await capture(page, testInfo, "06-network-modal");
  await page.getByRole("button", { name: "Close modal" }).click();
  await expect(page.locator(".network-modal")).toBeHidden();

  await page.goBack();
  await expect(page).toHaveURL(/\/en\?q=Ada(?:\+|%20)Lovelace$/);
  await expect(search).toHaveValue("Ada Lovelace");

  // The two ways out of a story have to agree. Back already restored the
  // search; the close button used to rebuild a bare landing route and drop it,
  // so the reader watched their filter vanish.
  await page.getByRole("button", { name: "Open life story for Ada" }).click();
  await expect(page).toHaveURL(/\/en\/story\/ada_lovelace/);
  await page
    .getByRole("button", {
      name: "Close story and return to the landing page",
    })
    .click();
  await expect(page).toHaveURL(/\/en\?q=Ada(?:\+|%20)Lovelace$/);
  await expect(search).toHaveValue("Ada Lovelace");

  // Closing used to drop focus to <body>, so a keyboard reader who opened the
  // thirtieth card had to tab the whole page again to get back to it.
  await expect(adaCard).toBeFocused();

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

// Blocking site data used to be fatal: both preference stores read
// `localStorage` at module scope, and in a browser that refuses storage the
// property exists and accessing it throws. The exception aborted the bootstrap,
// so every route rendered a blank page with nothing to interact with.
for (const [name, script] of [
  [
    "reads throw",
    () => {
      const boom = () => {
        throw new DOMException("Access is denied", "SecurityError");
      };
      Object.defineProperty(window, "localStorage", { get: boom });
    },
  ],
  [
    "writes throw",
    () => {
      Object.defineProperty(window, "localStorage", {
        value: {
          getItem: () => null,
          removeItem: () => {},
          setItem: () => {
            throw new DOMException("Quota exceeded", "QuotaExceededError");
          },
        },
      });
    },
  ],
]) {
  test(`the app boots when localStorage ${name}`, async ({ page }) => {
    const pageErrors = [];
    page.on("pageerror", (error) => pageErrors.push(error.message));
    await page.addInitScript(script);

    await page.goto("en");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.getByRole("status")).toContainText(/stories shown/i);

    await page.goto("en#/en/story/ada_lovelace");
    await expect(
      page.locator('section[aria-label^="Overview: Ada Lovelace"]')
    ).toBeVisible();

    expect(pageErrors).toEqual([]);
  });
}

/* A title is what a bookmark, a tab, and a search result show. The generic one
   was kept for collections, and stayed English on the German site. */
test("the document title names the open story, in the reader's language", async ({
  page,
}) => {
  await page.goto("en");
  await expect(page).toHaveTitle("Life Data Stories");

  await page.goto("en#/en/story/ada_lovelace");
  await expect(page).toHaveTitle("Life Data Stories · Ada Lovelace");

  await page.goto("en#/en/meta/computing_pioneers");
  await expect(page).toHaveTitle(
    "Life Data Stories · From Procedure to Presence"
  );

  await page.goto("en#/de/meta/computing_pioneers");
  await expect(page).toHaveTitle(
    "Life Data Stories · Vom Verfahren zur Allgegenwart"
  );
});

/* An unfurler never runs the router, so these tags live in the served
   document — and they are the whole preview a shared link gets. */
test("a shared link carries a preview card", async ({ page }) => {
  await page.goto("en");

  const content = (property) =>
    page
      .locator(`meta[property="${property}"], meta[name="${property}"]`)
      .getAttribute("content");

  await expect.poll(() => content("og:title")).toBe("Life Data Stories");
  await expect.poll(() => content("og:type")).toBe("website");
  await expect.poll(() => content("twitter:card")).toBe("summary_large_image");
  await expect.poll(() => content("description")).toContain("data stories");

  const image = await content("og:image");
  expect(image).toMatch(/^https?:\/\/.+\/preview\.png$/);

  const response = await page.request.get(image.replace(/^.*\/life-ds\//, ""));
  expect(response.status()).toBe(200);
});

/* The sticky header paints a backdrop-filter, which makes it the containing
   block for any fixed-position descendant. The confirmation toast lived inside
   it, so toggling contrast while scrolled pinned the toast under the header
   instead of the bottom of the viewport. */
test("the contrast toast sits at the bottom of the viewport, scrolled or not", async ({
  page,
}) => {
  await page.goto("en");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();

  const viewportHeight = page.viewportSize().height;
  const toast = page.locator(".contrast-toast");

  const expectToastNearBottom = async () => {
    await expect(toast).toBeVisible();
    const box = await toast.boundingBox();
    expect(box.y).toBeGreaterThan(viewportHeight / 2);
    expect(box.y + box.height).toBeLessThanOrEqual(viewportHeight);
    await expect(toast).toHaveCount(1);
  };

  await page.locator(".top-controls-right .contrast-toggle").click();
  await expectToastNearBottom();
  await expect(toast).toBeHidden({ timeout: 5000 });

  await page.mouse.wheel(0, 600);
  const stickyHeader = page.locator(".landing-sticky-header");
  await expect(stickyHeader).toBeVisible();

  await stickyHeader.locator(".contrast-toggle").click();
  await expectToastNearBottom();
});
