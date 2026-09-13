import { test, expect } from "@playwright/test";
import {
  coverSourceWidth,
  getThumbnailUrl,
} from "../src/utils/story/images.js";

/* An event slide draws its picture into a box the layout computes from the
   room the slide leaves free, and fills that box with `object-fit: cover`. How
   many source pixels the picture needs therefore follows the box and the
   screen, not a constant: the same photograph that is a corner accent on a
   phone runs across most of a desktop slide, and a source chosen for the phone
   arrives there as an enlarged thumbnail. */

test("a wide picture in a tall box needs more than the box's width", () => {
  // Scaled to the box height of 500, a 2:1 photograph is 1000 wide and the
  // surplus is cropped; asking for the box width alone would enlarge it.
  expect(coverSourceWidth(700, 500, 2)).toBe(1000);
  // A portrait in the same box is limited by the width instead.
  expect(coverSourceWidth(700, 500, 0.6)).toBe(700);
});

test("a dense screen doubles the request, and no screen more than doubles it", () => {
  expect(coverSourceWidth(600, 400, 1.5, 2)).toBe(1200);
  expect(coverSourceWidth(600, 400, 1.5, 3)).toBe(1200);
  expect(coverSourceWidth(600, 400, 1.5, 0)).toBe(600);
});

test("the request stops at the largest source worth fetching", () => {
  expect(coverSourceWidth(3600, 2400, 1.5, 2)).toBe(1920);
});

test("a box that does not exist yet asks for nothing", () => {
  expect(coverSourceWidth(0, 400, 1.5)).toBe(0);
  expect(coverSourceWidth(600, 0, 1.5)).toBe(0);
  expect(coverSourceWidth(600, 400, Number.NaN)).toBe(0);
});

/* The width only matters through the address it produces: Wikimedia serves
   fixed steps, so a desktop-sized box has to land on a larger step than the
   400px request every slide used to make. */
test("a desktop-sized box lands on a larger Wikimedia step", () => {
  const file =
    "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d0/Aquatics.jpg/960px-Aquatics.jpg";
  const phone = getThumbnailUrl(file, coverSourceWidth(360, 240, 1.5, 2));
  const desktop = getThumbnailUrl(file, coverSourceWidth(1100, 730, 1.5, 1));

  expect(phone).toContain("/960px-");
  expect(desktop).toContain("/1280px-");
});
