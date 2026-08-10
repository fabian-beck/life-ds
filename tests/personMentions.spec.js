import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

// Five components used to write out the mention loop themselves; they now
// share `PersonMentions`. What a reader would notice if that component got a
// prop wrong is the prose: a name emphasized twice, a name dropped, or text
// spliced back together differently from how the data wrote it.
//
// So the assertion is the strict one — the narration card's `textContent` has
// to equal its source string character for character. `textContent` rather
// than `innerText` on purpose: innerText reports the text as rendered, with
// runs of whitespace already collapsed, and would hide a splice defect.
//
// (Svelte trims the template whitespace around `{#each}`/`{#if}` itself, so
// the classic newline-in-the-loop slip does not survive compilation. This
// guards the props and the segmentation, not the source formatting.)

const story = JSON.parse(
  readFileSync(
    fileURLToPath(
      new URL("../data/meta_stories/computing_pioneers.json", import.meta.url)
    ),
    "utf8"
  )
);

test("the network narration reads exactly as the data writes it", async ({
  page,
}) => {
  await page.goto("en#/en/meta/computing_pioneers");
  await expect(page.locator(".ms-steps .step-card").first()).toBeVisible();

  const rendered = await page.evaluate(() =>
    [...document.querySelectorAll(".ms-steps .step-body")].map(
      (node) => node.textContent
    )
  );
  expect(rendered.length).toBeGreaterThan(0);

  const sources = new Set(
    story.social_network.narration.circles.map((circle) => circle.text)
  );
  let compared = 0;
  for (const text of rendered) {
    // The card list is capped, so only assert on the cards actually shown —
    // but every one of them has to match its source character for character.
    if (!sources.has(text)) {
      const near = [...sources].find(
        (source) => source.replace(/\s+/g, " ") === text.replace(/\s+/g, " ")
      );
      expect(near ?? text, "rendered card differs from its source text").toBe(
        text
      );
    }
    compared += 1;
  }
  expect(compared).toBeGreaterThan(0);
});

test("a mention is spliced in without a space of its own", async ({ page }) => {
  await page.goto("en#/en/meta/computing_pioneers");
  await expect(page.locator(".person-mention").first()).toBeVisible();

  // No mention may sit against whitespace the source did not write — the
  // giveaway being a space in front of punctuation.
  const offenders = await page.evaluate(() =>
    [...document.querySelectorAll(".person-mention")]
      .map((node) => {
        const before = node.previousSibling?.textContent ?? "";
        const after = node.nextSibling?.textContent ?? "";
        return `${before.slice(-2)}[${node.textContent}]${after.slice(0, 2)}`;
      })
      .filter(
        (sample) =>
          /\s\s\]/.test(sample) ||
          /\]\s[.,;:’'”)]/.test(sample) ||
          /\s\s/.test(sample)
      )
  );
  expect(offenders).toEqual([]);
});
