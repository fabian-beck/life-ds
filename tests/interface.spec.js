import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";
// The story titles are data, and a re-translation is free to word one
// differently; what this file checks is that the page shows the reader's
// language, so it asks the registries which title that is.
import metaStories from "../data/meta_stories.json" with { type: "json" };
import metaStoriesDe from "../data/meta_stories_de.json" with { type: "json" };
// Which event carries a picture is data too, and the one test that needs a
// picture on screen asks rather than assumes.
import turingEvents from "../data/people/alan_turing/life_events.json" with { type: "json" };

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

/* Chromium is driven twice, at a desktop and at a phone viewport, so that the
   journey and the layout it moves through are seen at both sizes. Not every
   test in this file earns the second pass, and one that does not costs the run
   its slowest part twice over for a single answer. The two below say which pass
   a test keeps; the projects are given roughly half of them each, because they
   run side by side and the run is as long as the fuller one. */

// Decided by the document rather than by its layout: a route, a title, the
// served meta tags, a page that boots or does not. Either project answers for
// both.
function viewportDoesNotDecideThis() {
  test.skip(
    test.info().project.name !== "desktop-chromium",
    "no viewport decides this; checked under desktop-chromium"
  );
}

// Sets a phone viewport of its own, so the project's size is moot — but its
// touch and device-scale emulation is not, and a phone is what these were
// written for.
function setsItsOwnPhoneViewport() {
  test.skip(
    test.info().project.name !== "mobile-chromium",
    "pinned to its own viewport; checked under mobile-chromium"
  );
}

// Nothing on a page laid out for the reader's own screen may reach past its
// right edge: a sideways scrollbar on a phone is how a mobile reader loses half
// a caption. Named after the page it measures, so a failure says where.
async function expectNoSidewaysScroll(page, where) {
  const width = await page.evaluate(() => ({
    document: document.documentElement.scrollWidth,
    viewport: window.innerWidth,
  }));
  expect(width.document, `${where} scrolls sideways`).toBeLessThanOrEqual(
    width.viewport + 1
  );
}

// The event pictures come from Wikimedia, and a test that waits on a foreign
// host is a test that fails for reasons of its own. This serves a local file in
// their place, so the layout the picture drives is measured offline and always.
const LOCAL_IMAGE = readFileSync("public/preview.png");

async function serveImagesLocally(page) {
  await page.route(/upload\.wikimedia\.org/, (route) =>
    route.fulfill({ status: 200, contentType: "image/png", body: LOCAL_IMAGE })
  );
}

// A slide is one screen and one screen only. Its own picture is the thing most
// likely to argue: it is laid out from the viewport and then shifted outward so
// its faded corner clears the edge, which paints past the slide's right side.
// The slide scrolls vertically, and a browser hands any box that scrolls one way
// a scrollbar on the other as soon as something reaches past it — so the bleed
// used to become a sideways drag that pulled the event off center. Measured on
// the slide rather than on the document, because the document never overflowed:
// the slide absorbed it, which is exactly why the check above missed this.
test("an event slide with a picture is exactly as wide as the screen", async ({
  page,
}) => {
  const withImage = turingEvents.events.findIndex(
    (event) => (event.images ?? []).length > 0
  );
  expect(withImage, "no Turing event carries a picture").toBeGreaterThanOrEqual(
    0
  );

  await serveImagesLocally(page);
  await page.goto(`en#/en/story/alan_turing?event=${withImage}`);
  const slide = page.locator("section.slide:not([inert])");
  await expect(slide.locator(".image-thumbnail.image-visible")).toBeVisible();

  const measured = await slide.evaluate((section) => {
    // Asked for, not merely read: `scrollWidth` alone would pass on a box that
    // hides its overflow while still letting focus or a script scroll into it.
    section.scrollLeft = section.clientWidth;
    const reached = section.scrollLeft;
    section.scrollLeft = 0;
    return {
      reached,
      scrollWidth: section.scrollWidth,
      clientWidth: section.clientWidth,
      picture: section.querySelector(".image-thumbnail").getBoundingClientRect()
        .width,
    };
  });

  // The picture is really there and really wide, so a pass means the bleed was
  // cropped rather than that there was nothing to crop.
  expect(measured.picture).toBeGreaterThan(0);
  expect(
    measured.scrollWidth,
    "the event slide reaches past its own right edge"
  ).toBeLessThanOrEqual(measured.clientWidth + 1);
  expect(measured.reached, "the event slide scrolls sideways").toBe(0);
});

// The report is a separate page published next to the app, so a broken link
// here fails silently in the application itself: nothing imports it, and no
// other test would notice that the route stopped resolving.
test("technical report is reachable from the landing page", async ({
  page,
}) => {
  viewportDoesNotDecideThis();
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
  await expectNoSidewaysScroll(page, "the landing page");

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
  await expectNoSidewaysScroll(page, "the filtered landing page");

  await adaCard.click();
  await expect(page).toHaveURL(/\/en\/story\/ada_lovelace/);
  await expect(
    page.locator('section[aria-label^="Overview: Ada Lovelace"]')
  ).toBeVisible();
  await capture(page, testInfo, "03-story-overview");
  await expectNoSidewaysScroll(page, "the story overview");

  await page.keyboard.press("ArrowDown");
  await expect(page).toHaveURL(/[?&]slide=1(?:&|$)/);
  await capture(page, testInfo, "04-story-chapter");

  await page.keyboard.press("PageDown");
  await expect(page).toHaveURL(/[?&]slide=2(?:&|$)/);
  await capture(page, testInfo, "05-story-event");
  await expectNoSidewaysScroll(page, "an event slide");

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
    viewportDoesNotDecideThis();
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
  setsItsOwnPhoneViewport();
  // Alan Turing, because the deep half of this audit needs a life whose
  // landmark events carry a background report — the layer is that report, and
  // the corpus is filled one life at a time.
  await page.goto("en#/en/story/alan_turing");
  await expect(
    page.locator('section[aria-label^="Overview: Alan Turing"]')
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

  // Polled, like every other reading of this value below. The overlay starts
  // out `hidden` and fades in over 0.6s once the route settles on the event, so
  // a single sample taken the moment it attaches catches it part-way up the
  // ramp and fails for no reason the test is about.
  await expect
    .poll(async () => (await geometry()).mapOpacity)
    .toBeGreaterThan(0.9);
  const atRest = await geometry();
  expect(atRest.scrollTop).toBe(0);
  expect(atRest.below).toBeGreaterThanOrEqual(0);

  const affordance = slide.locator(".depth-affordance");
  await expect(affordance).toBeVisible();

  // An annotation opens its popup from the foot of the description, which is
  // where the invitation down sits. The one the reader just asked for wins.
  const term = slide.locator(".annotated-term").first();
  await term.click();
  await expect(slide.locator(".annotation-popup")).toBeVisible();
  await expect(affordance).toHaveCSS("opacity", "0");
  await expect(affordance).toHaveCSS("pointer-events", "none");
  await term.click();
  await expect(slide.locator(".annotation-popup")).toHaveCount(0);
  await expect(affordance).toHaveCSS("opacity", "1");

  await affordance.click();

  // A chapter of background, not a reference card: several paragraphs of
  // generated report, with the pictures chosen for it dealt out between them.
  await expect(slide.locator(".event-depth")).toBeInViewport();
  const paragraphs = slide.locator(".event-depth .depth-paragraph");
  await expect(paragraphs.first()).toBeVisible();
  expect(await paragraphs.count()).toBeGreaterThan(1);
  // Background rather than a retelling. The prompt's whole job is this
  // difference, and the cheapest check of it is that the passage is not the
  // description over again.
  const eventText = await slide.locator(".content").innerText();
  const report = (await paragraphs.allInnerTexts()).join("\n\n");
  expect(report.length).toBeGreaterThan(600);
  for (const paragraph of await paragraphs.allInnerTexts()) {
    expect(eventText).not.toContain(paragraph);
  }
  // A figure sits under the opening paragraph, where a chapter would put it,
  // rather than all of them banked above the text.
  const figures = slide.locator(".event-depth .depth-figure");
  expect(await figures.count()).toBeGreaterThan(0);
  await expect(figures.first()).toBeVisible();
  // The layer does not reprint the popups: every annotated term on this slide
  // is explained a tap away, and saying it twice is what made the layer read
  // as a second copy of the fold.
  const explanations = await slide.evaluate((node) =>
    [...node.querySelectorAll(".annotation-popup")].map((p) => p.textContent)
  );
  const layer = await slide.locator(".event-depth").innerText();
  for (const explanation of explanations) {
    expect(layer).not.toContain(explanation);
  }
  // Prose, not a card: no definition list, no line per record. What headings
  // there are divide the prose rather than label its parts, so they are the
  // report's own `## ` lines and never stand above its opening paragraph.
  expect(await slide.locator(".event-depth dt").count()).toBe(0);
  const sections = slide.locator(".event-depth .depth-section");
  expect(await sections.count()).toBeLessThanOrEqual(3);
  const first = await slide.evaluate((node) => {
    const prose = node.querySelector(".depth-prose");
    const blocks = [...prose.children].filter((child) =>
      child.matches(".depth-paragraph, .depth-section")
    );
    return blocks[0]?.className ?? "";
  });
  expect(first).toContain("depth-paragraph");
  // A person the ego network knows is emphasized where the report names them,
  // exactly as the description emphasizes them — and stays emphasis, since the
  // chip a screen above is where a person opens.
  const mentions = slide.locator(".event-depth .person-mention");
  expect(await mentions.count()).toBeGreaterThan(0);
  expect(await slide.locator(".event-depth .person-chip").count()).toBe(0);
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

/* Neither a thumb on glass nor two fingers on a trackpad send a gesture that
   is only vertical. The story read the sideways part of a drag down as a swipe
   along the story, so a reader opening an event was carried off it — the two
   tests below are that same wandering gesture, once as touch and once as a
   wheel, and a deliberate swipe after it to show the story still answers one.
   The deep slide is where it mattered most: down the screen is where the rest
   of the event is. */
// `dx` and `dy` are fractions of the slide, so that the same numbers describe
// the same gesture on a phone and on a desktop screen — the story reads a
// swipe against the width it has, and a drag named in pixels is a different
// gesture on each.
async function dragSlides(page, { dx, dy, steps = 8 }) {
  await page.evaluate(
    async ({ dx, dy, steps }) => {
      const active = document.querySelector("section.slide:not([inert])");
      const box = active.getBoundingClientRect();
      const travelX = dx * box.width;
      const travelY = dy * box.height;
      const startX = box.left + box.width / 2;
      const startY = box.top + box.height / 2;
      const fire = (type, x, y) => {
        const touch = new Touch({
          identifier: 1,
          target: active,
          clientX: x,
          clientY: y,
        });
        const points = type === "touchend" ? [] : [touch];
        active.dispatchEvent(
          new TouchEvent(type, {
            bubbles: true,
            cancelable: true,
            touches: points,
            targetTouches: points,
            changedTouches: [touch],
          })
        );
      };
      fire("touchstart", startX, startY);
      // A finger arrives as a run of points spread over time, and both halves
      // of that matter: where it has been says which way it is going, and how
      // long it took says whether it was a flick. A drag delivered in one jump
      // would be neither.
      for (let step = 1; step <= steps; step += 1) {
        fire(
          "touchmove",
          startX + (travelX * step) / steps,
          startY + (travelY * step) / steps
        );
        // eslint-disable-next-line no-await-in-loop -- a drag is a sequence
        await new Promise((resolve) => {
          requestAnimationFrame(resolve);
        });
      }
      fire("touchend", startX + travelX, startY + travelY);
    },
    { dx, dy, steps }
  );
}

function activeSlideLabel(page) {
  return page
    .locator("section.slide:not([inert])")
    .getAttribute("aria-label", { timeout: 10_000 });
}

test("a swipe down the screen stays on the event it opens", async ({
  page,
}) => {
  await page.goto("en#/en/story/alan_turing?event=9");
  const slide = page.locator("section.slide:not([inert])");
  await expect(slide).toHaveClass(/has-depth/);
  const opened = await activeSlideLabel(page);
  const restedAt = await page.evaluate(
    () => document.querySelector("main.slides").scrollLeft
  );

  // Up the screen, because that is the way a finger moves to bring the page
  // below into view, and a good way sideways with it — a sloppy drag, but the
  // drag of someone reading further into the event, not of someone leaving it.
  // Far enough sideways that the story used to count it as a swipe.
  await dragSlides(page, { dx: -0.35, dy: -0.6 });
  await expect(slide).toHaveAttribute("aria-label", opened);
  await expect
    .poll(() =>
      page.evaluate(() => document.querySelector("main.slides").scrollLeft)
    )
    .toBe(restedAt);

  // The same drag leaning the other way is a swipe, and still moves the story.
  await dragSlides(page, { dx: -0.5, dy: -0.15 });
  await expect.poll(() => activeSlideLabel(page)).not.toBe(opened);
});

test("a wheel that wanders sideways scrolls into the event, not past it", async ({
  page,
}) => {
  await page.goto("en#/en/story/alan_turing?event=9");
  const slide = page.locator("section.slide:not([inert])");
  await expect(slide).toHaveClass(/has-depth/);
  const opened = await activeSlideLabel(page);

  // The story is one strip of slides, and it snaps back to the nearest one
  // when it is let go, so where the strip ends up says nothing about whether
  // it moved. What it did while the gesture ran is the whole question.
  await page.evaluate(() => {
    const slides = document.querySelector("main.slides");
    const restedAt = slides.scrollLeft;
    window.__slideDrift = 0;
    slides.addEventListener("scroll", () => {
      window.__slideDrift = Math.max(
        window.__slideDrift,
        Math.abs(slides.scrollLeft - restedAt)
      );
    });
  });

  const box = await slide.boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  // A moment of a scroll down a trackpad, and one whose sideways half is the
  // larger — which is all it used to take: the story took the whole event for
  // a swipe, and a strip that snaps carried the reader a slide along on 16px
  // of drift. (That a whole run of such moments still leans down is decided in
  // `gestureAxis.spec.js`: a driven wheel arrives too slowly to make one run
  // of here.)
  await page.mouse.wheel(16, 12);

  await expect
    .poll(() =>
      page.evaluate(
        () => document.querySelector("section.slide:not([inert])").scrollTop
      )
    )
    .toBeGreaterThan(0);
  await expect(slide).toHaveAttribute("aria-label", opened);
  expect(await page.evaluate(() => window.__slideDrift)).toBe(0);
});

/* A person's context is given by their chip, on every slide, including the ones
   that carry a depth layer. The layer briefly took the people for itself — the
   chips were suppressed to avoid saying a name twice — which made the one slide
   with more to say the one slide where a person could not be opened. */
test("a person on a deep slide keeps their chip, and the layer does not retell them", async ({
  page,
}) => {
  await page.goto("en#/en/story/alan_turing?event=2");
  const slide = page.locator("section.slide:not([inert])");
  await expect(slide).toHaveClass(/has-depth/);

  const chip = slide.locator(".content .person-chip").first();
  await expect(chip).toBeVisible();
  const name = (await chip.innerText()).trim();
  expect(name.length).toBeGreaterThan(0);

  // Opening the chip is where who they were to the subject is told.
  await chip.click();
  // The tooltip is portalled to the body, not nested in the slide.
  const told = page.locator(".person-info-tooltip").first();
  await expect(told).toBeVisible();
  const relationship = await told
    .locator(".tooltip-relationship")
    .first()
    .innerText();

  await slide.locator(".depth-affordance").click();
  const layer = slide.locator(".event-depth");
  await expect(layer).toBeInViewport();
  const said = await layer.innerText();
  expect(said).not.toContain(relationship.trim());
  expect(await layer.locator(".person-chip").count()).toBe(0);
});

/* A title is what a bookmark, a tab, and a search result show. The generic one
   was kept for collections, and stayed English on the German site. */
test("the document title names the open story, in the reader's language", async ({
  page,
}) => {
  viewportDoesNotDecideThis();
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
  viewportDoesNotDecideThis();
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
  setsItsOwnPhoneViewport();
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
  setsItsOwnPhoneViewport();
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

/* A chapter slide carries an abstract illustration of what the chapter is
   about, printed the way the portrait is: translucent, edges dissolved, no
   caption. It is decoration and must stay out of the reading order — an alt
   text here would announce a metaphor to a screen reader as if it were a
   picture of something that happened. Which chapters have one is data, so the
   test asks the dataset rather than assuming. */
test("a chapter slide prints its illustration as decoration", async ({
  page,
}) => {
  viewportDoesNotDecideThis();
  const illustrated = (turingEvents.chapters ?? []).find(
    (chapter) => chapter.illustration?.medium
  );
  test.skip(!illustrated, "no chapter of this life has an illustration yet");

  await page.goto("en#/en/story/alan_turing?slide=1");
  const slide = page.locator("section.slide.chapter").first();
  const illustration = slide.locator(".chapter-illustration");

  await expect(illustration).toBeVisible();
  await expect(illustration).toHaveAttribute("aria-hidden", "true");
  await expect(illustration).toHaveAttribute("alt", "");
  await expect(illustration).toHaveJSProperty("naturalWidth", 512);

  // Translucent, so the story's own background reads through it.
  const opacity = await illustration.evaluate((element) =>
    Number(getComputedStyle(element).opacity)
  );
  expect(opacity).toBeGreaterThan(0);
  expect(opacity).toBeLessThan(1);

  // The headline is what the slide is for; the picture stays above it. Their
  // boxes are allowed to touch — the illustration's faded edge is pulled up
  // under the headline on purpose — but the headline is never printed over it.
  const [picture, headline] = await Promise.all([
    illustration.boundingBox(),
    slide.locator(".chapter-headline").boundingBox(),
  ]);
  expect(picture.y).toBeLessThan(headline.y);
  expect(picture.y + picture.height).toBeLessThan(headline.y + headline.height);
});
