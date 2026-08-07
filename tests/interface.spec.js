import { expect, test } from "@playwright/test";
import { writeFile } from "node:fs/promises";
// The story titles are data, and a re-translation is free to word one
// differently; what this file checks is that the page shows the reader's
// language, so it asks the registries which title that is.
import metaStories from "../data/meta_stories.json" with { type: "json" };
import metaStoriesDe from "../data/meta_stories_de.json" with { type: "json" };

function metaStoryTitle(registry, id) {
  const entry = (registry.meta_stories ?? []).find((story) => story.id === id);
  if (!entry?.title) throw new Error(`no title for meta story '${id}'`);
  return entry.title;
}

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

/* Each slide keeps room free at its foot, for the story map and for the
   timeline controls that float over it. The room used to be bottom padding,
   which an `overflow-y: auto` box scrolls through, so slides whose every word
   was already on screen scrolled over empty margin. The room can only be given
   up when giving it up spares the slide a scroll: on a slide the content
   overruns, it is what the reader scrolls the last line into. Both halves are
   checked here, because a fix for either one alone breaks the other. */
test("a slide scrolls only when there is something below to reach", async ({
  page,
}) => {
  await page.goto("en#/en/story/ada_lovelace");
  await expect(
    page.locator('section[aria-label^="Overview: Ada Lovelace"]')
  ).toBeVisible();
  await expect(page.locator(".slides-wrapper.map-enabled")).toBeAttached();
  await expect(page.locator(".indicator")).toBeVisible();

  // Neither half shows itself on a screen with room to spare, so the sizes are
  // named here rather than left to the project.
  const roomy = await expectSlidesReachTheirContent(page, {
    width: 390,
    height: 760,
  });
  const cramped = await expectSlidesReachTheirContent(page, {
    width: 360,
    height: 640,
  });

  // Neither half is vacuous: the roomy screen has slides that fit, the cramped
  // one has event slides that do not, and both have slides that go deeper.
  expect(roomy.fitting).toBeGreaterThan(0);
  expect(cramped.overrunning).toBeGreaterThan(0);
  expect(roomy.deep).toBeGreaterThan(0);
  expect(cramped.deep).toBeGreaterThan(0);
});

async function expectSlidesReachTheirContent(page, viewport) {
  await page.setViewportSize(viewport);
  const audit = await page.evaluate(() => {
    // The previous and next buttons and the timeline bar float over the foot of
    // every slide. Text under them is text the reader cannot read.
    const controls = document.querySelector(".indicator");
    // A slide with a depth layer scrolls by design: what is below its fold is
    // the second screen, not empty margin. It is audited on its own terms
    // further down.
    const isDeep = (slide) => slide.classList.contains("has-depth");
    // The slide keeps its content a round 10rem clear of the foot, a little
    // more than the controls actually take. A last line landing inside that
    // difference is flush against them, and a slide may scroll to lift it, so
    // the check for scrolling over nothing starts above the difference.
    const FLUSH = 16;
    const result = {
      fitting: 0,
      overrunning: 0,
      deep: 0,
      phantom: [],
      buried: [],
      shallow: [],
    };

    for (const slide of document.querySelectorAll("section.slide")) {
      const content = slide.querySelector(".content");
      if (!content) continue;
      const foot = slide.getBoundingClientRect().bottom;
      const controlsReach = foot - controls.getBoundingClientRect().top;
      const label = slide.getAttribute("aria-label");
      const scrollable = slide.scrollHeight - slide.clientHeight;

      // A pixel of slack throughout: the measurements round differently.
      const atRest = foot - content.getBoundingClientRect().bottom;

      if (isDeep(slide)) {
        result.deep += 1;
        const depth = slide.querySelector(".event-depth");
        // The fold is one screen and the depth layer begins under it, so the
        // slide has to scroll, and by at least a screen's worth.
        if (!depth || scrollable < slide.clientHeight - 1) {
          result.shallow.push({
            label,
            scrollable: Math.round(scrollable),
            screen: slide.clientHeight,
            hasDepthLayer: !!depth,
          });
        }
        continue;
      }

      if (atRest >= controlsReach - 1) {
        result.fitting += 1;
        // Everything is already readable, so there is nothing to scroll to.
        if (scrollable > 1 && atRest >= controlsReach + FLUSH) {
          result.phantom.push({
            label,
            scrollable: Math.round(scrollable),
            clearAtRest: Math.round(atRest),
          });
        }
        continue;
      }

      result.overrunning += 1;
      // The event slides are the ones carrying the map's reserve; the overview
      // and conclusion keep a smaller one of their own.
      if (/^Slide \d+ of/.test(label ?? "")) {
        slide.scrollTop = slide.scrollHeight;
        const scrolled = foot - content.getBoundingClientRect().bottom;
        slide.scrollTop = 0;
        if (scrolled < controlsReach - 1) {
          result.buried.push({
            label,
            clearsBy: Math.round(scrolled),
            needs: Math.round(controlsReach),
          });
        }
      }
    }
    return result;
  });

  const where = `at ${viewport.width}x${viewport.height}`;
  expect(audit.phantom, `scrolls over nothing ${where}`).toEqual([]);
  expect(audit.buried, `cannot be scrolled clear ${where}`).toEqual([]);
  expect(audit.shallow, `deep slide has no second screen ${where}`).toEqual([]);
  return audit;
}

/* Sideways is the story's axis, one event after another. Downward is the other
   one: on a life's landmarks the slide carries a second screen of context under
   the fold. The fold has to be exactly a screen — a peek of the layer below
   gives the ending away and clutters the event — the invitation down has to be
   there to be seen and taken, and the map, which belongs to the event, has to
   get out of the way of the page that replaces it. */
test("an important event opens downward, and the map gives way to it", async ({
  page,
}) => {
  await page.goto("en#/en/story/alan_turing?event=9");
  const slide = page.locator("section.slide:not([inert])");
  await expect(slide).toHaveClass(/has-depth/);
  await expect(page.locator(".map-overlay")).toBeAttached();

  // Rare by design: the depth layer is offered on a life's landmarks, not on
  // every event it happens to know a lot about.
  const deep = await page.locator("section.slide.has-depth").count();
  const events = await page
    .locator('section.slide[aria-label^="Slide "]')
    .count();
  expect(deep).toBeGreaterThan(0);
  expect(deep).toBeLessThan(events / 2);

  const geometry = () =>
    page.evaluate(() => {
      const active = document.querySelector("section.slide:not([inert])");
      const depth = active.querySelector(".event-depth");
      return {
        scrollTop: Math.round(active.scrollTop),
        // How far the depth layer's top sits below the foot of the window.
        below: Math.round(
          depth.getBoundingClientRect().top - window.innerHeight
        ),
        mapOpacity: Number(
          getComputedStyle(document.querySelector(".map-overlay")).opacity
        ),
      };
    });

  const atRest = await geometry();
  expect(atRest.scrollTop).toBe(0);
  expect(atRest.below).toBeGreaterThanOrEqual(0);
  expect(atRest.mapOpacity).toBeGreaterThan(0.9);

  const affordance = slide.locator(".depth-affordance");
  await expect(affordance).toBeVisible();
  await affordance.click();

  // A passage of what the fold keeps a tap away or leaves out, and prose
  // rather than a reference card: the written background leads, the place is
  // named in a sentence, and what each paragraph is about runs into the
  // sentence instead of sitting above it as a heading.
  await expect(slide.locator(".event-depth")).toBeInViewport();
  const written = slide.locator(".event-depth .depth-written").first();
  await expect(written).toBeVisible();
  // Background rather than a retelling. The prompt's whole job is this
  // difference, and the cheapest check of it is that the passage is not the
  // description over again.
  const eventText = await slide.locator(".content").innerText();
  const passage = await written.innerText();
  expect(passage.length).toBeGreaterThan(80);
  expect(eventText).not.toContain(passage);
  await expect(slide.locator(".event-depth")).toContainText(
    "Bletchley, Milton Keynes"
  );
  await expect(
    slide.locator(".event-depth .depth-paragraph .depth-subject").first()
  ).toBeVisible();
  expect(await slide.locator(".event-depth h3, .event-depth dt").count()).toBe(
    0
  );
  await expect
    .poll(async () => (await geometry()).mapOpacity)
    .toBeLessThan(0.1);

  await slide.locator(".depth-return").click();
  await expect.poll(async () => (await geometry()).scrollTop).toBe(0);
  await expect
    .poll(async () => (await geometry()).mapOpacity)
    .toBeGreaterThan(0.9);
  await expect(affordance).toBeVisible();
});

/* A title is what a bookmark, a tab, and a search result show. The generic one
   was kept for collections, and stayed English on the German site. */
test("the document title names the open story, in the reader's language", async ({
  page,
}) => {
  await page.goto("en");
  await expect(page).toHaveTitle("Life Data Stories");

  await page.goto("en#/en/story/ada_lovelace");
  await expect(page).toHaveTitle("Life Data Stories · Ada Lovelace");

  const english = metaStoryTitle(metaStories, "computing_pioneers");
  const german = metaStoryTitle(metaStoriesDe, "computing_pioneers");
  expect(german).not.toBe(english);

  await page.goto("en#/en/meta/computing_pioneers");
  await expect(page).toHaveTitle(`Life Data Stories · ${english}`);

  await page.goto("en#/de/meta/computing_pioneers");
  await expect(page).toHaveTitle(`Life Data Stories · ${german}`);
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

/* Opening the timeline rearranges icons the reader is already looking at. They
   used to be thrown away and a list faded in over the gap, which read as two
   unrelated widgets swapping places; each icon now travels from where it stood
   in the bar to where it stands in the list. */
test("opening the timeline carries its icons into their new places", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("en#/en/story/alan_turing");

  const eventDots = page.locator('.dots-container [data-morph-key^="event-"]');
  await expect.poll(() => eventDots.count()).toBeGreaterThan(8);
  // A life long enough that its expanded list overruns the screen, opened
  // halfway along, so that the list has to be scrolled for the icon to have
  // anywhere sensible to land.
  const middle = Math.floor((await eventDots.count()) / 2);
  await eventDots.nth(middle).click();
  const key = `event-${middle}`;
  await expect(page.locator(`[data-morph-key="${key}"]`)).toHaveAttribute(
    "aria-current",
    "true"
  );

  const centerOf = (morphKey) =>
    page.evaluate((selectorKey) => {
      const rect = document
        .querySelector(`[data-morph-key="${selectorKey}"]`)
        .getBoundingClientRect();
      return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
    }, morphKey);

  const inTheBar = await centerOf(key);

  // Every animation started from here on is held at its first frame, so that the
  // start of the move can be read off without racing it.
  await page.evaluate(() => {
    const animate = Element.prototype.animate;
    Element.prototype.animate = function holdAtStart(...args) {
      const animation = animate.apply(this, args);
      animation.pause();
      animation.currentTime = 0;
      return animation;
    };
  });

  await page.locator(".chapter-indicator-box").click();
  await expect(page.locator(".dots-container.expanded")).toBeVisible();

  // The icon in the list is the icon that was in the bar: at the first frame of
  // the move it has not left the place the reader last saw it.
  const atTheStart = await centerOf(key);
  expect(Math.abs(atTheStart.x - inTheBar.x)).toBeLessThan(2);
  expect(Math.abs(atTheStart.y - inTheBar.y)).toBeLessThan(2);

  await page.evaluate(() => {
    for (const animation of document.getAnimations()) {
      // Endless ones — the page has a few — cannot be sent to an end they do
      // not have.
      if (animation.effect?.getComputedTiming().iterations === Infinity)
        continue;
      animation.finish();
    }
  });

  // The list was already sitting on the reader's event before the icons set
  // off, so the icon makes one journey and lands where it stays, rather than
  // arriving and then being scrolled somewhere else.
  const atTheEnd = await centerOf(key);
  expect(atTheEnd.y).toBeLessThan(inTheBar.y - 100);
  expect(atTheEnd.y).toBeGreaterThan(844 * 0.2);
  expect(atTheEnd.y).toBeLessThan(844 * 0.8);

  // The stand-ins for the chapter dots, which the list has no icon for, clear
  // up after themselves.
  await expect
    .poll(() => page.locator(".morph-ghost-layer > *").count())
    .toBe(0);
});

/* A chapter change swaps one title for the next inside a single pill. The pill
   used to hold the outgoing and incoming titles at once—two headings side by
   side, the pill stretched to fit both—whenever the fades overlapped, which a
   busy main thread makes certain rather than unlikely. */
test("the chapter pill carries one title at a time", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("en#/en/story/alan_turing");

  const dots = page.locator('.dots-container [data-morph-key^="event-"]');
  await expect.poll(() => dots.count()).toBeGreaterThan(8);
  await expect(page.locator(".chapter-indicator-label")).toHaveCount(1);

  // A second title in the pill is a second label element, so watching the pill
  // for one catches the overlap however short it is: the observer runs on the
  // insertion itself, not on a frame that may never be painted.
  await page.evaluate(() => {
    window.__mostTitlesAtOnce = 0;
    const count = () => {
      window.__mostTitlesAtOnce = Math.max(
        window.__mostTitlesAtOnce,
        document.querySelectorAll(".chapter-indicator-label").length
      );
    };
    new MutationObserver(count).observe(document.body, {
      subtree: true,
      childList: true,
      characterData: true,
    });
    setInterval(count, 16);
    count();
  });

  // Jump the length of the life, so the pill is asked to change chapter
  // several times over.
  const total = await dots.count();
  const titles = new Set();
  for (const index of [0, Math.floor(total / 2), total - 1, 1]) {
    // The jumps are a sequence, not a batch: each one has to land before the
    // next is asked for.
    /* eslint-disable no-await-in-loop */
    await dots.nth(index).click();
    await expect(
      page.locator(`[data-morph-key="event-${index}"]`)
    ).toHaveAttribute("aria-current", "true");
    // Long enough for the fade out, the swap, and the fade back in.
    await page.waitForTimeout(600);
    titles.add(await page.locator(".chapter-indicator-label").innerText());
    /* eslint-enable no-await-in-loop */
  }

  // The pill really did change hands; otherwise the count below proves nothing.
  expect(titles.size).toBeGreaterThan(2);
  expect(await page.evaluate(() => window.__mostTitlesAtOnce)).toBe(1);
});
