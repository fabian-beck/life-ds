import { test, expect } from "@playwright/test";
import { cssUrl, fontStack, styleVars } from "../src/utils/helpers.js";
import { storyStyleVars } from "../src/utils/helpers.js";
import { metaStoryStyleVars } from "../src/utils/metaStoryStyles.js";

// Four surfaces build an inline `style` of CSS custom properties — the person
// story, the meta story, the landing card and the person card. What they share
// is the mechanics, not the variable names, and these pin the mechanics.

test("a variable with no value is left out, not emitted empty", () => {
  // The point of omitting it: the stylesheet's own `var(--x, fallback)` takes
  // over. An empty declaration would win and paint nothing.
  expect(
    styleVars([
      ["--a", "red"],
      ["--b", null],
      ["--c", undefined],
      ["--d", ""],
      ["--e", "blue"],
    ])
  ).toBe("--a: red; --e: blue");
});

test("zero is a value", () => {
  // A frame radius of 0 and a pattern opacity of 0 both mean something.
  expect(
    styleVars([
      ["--radius", "0"],
      ["--opacity", 0],
    ])
  ).toBe("--radius: 0; --opacity: 0");
});

test("nothing at all renders as the empty string", () => {
  expect(styleVars([])).toBe("");
  expect(styleVars([["--a", null]])).toBe("");
});

test("the font stack puts the chosen face in front of the shared fallbacks", () => {
  expect(fontStack("Unbounded")).toBe('"Unbounded", Inter, sans-serif');
});

test("no font means no declaration, unless a fallback is asked for", () => {
  // The story and meta-story containers omit the variable; the person card
  // asks for `inherit`, because it sits inside surfaces with fonts of their own.
  expect(fontStack(null)).toBe(null);
  expect(fontStack("")).toBe(null);
  expect(fontStack(undefined, "inherit")).toBe("inherit");
});

test("a url is wrapped, and an absent one stays absent", () => {
  expect(cssUrl("data:image/svg+xml,%3Csvg%3E")).toBe(
    'url("data:image/svg+xml,%3Csvg%3E")'
  );
  expect(cssUrl(null)).toBe(null);
  expect(cssUrl("")).toBe(null);
});

test("the story builder names its own variables", () => {
  expect(
    storyStyleVars({
      background: "#000",
      primary: "#fff",
      headingFont: "Inter Tight",
    })
  ).toBe(
    "--story-bg: #000; --story-primary: #fff; " +
      '--story-heading-font: "Inter Tight", Inter, sans-serif'
  );
});

test("a pattern brings its size with it, and only then", () => {
  expect(storyStyleVars({ backgroundPatternDataUrl: "data:x" })).toBe(
    '--story-pattern-image: url("data:x"); --story-pattern-size: 500px'
  );
  expect(storyStyleVars({ primary: "#fff" })).not.toContain("pattern-size");
});

test("the meta story leaves its fonts unprefixed on purpose", () => {
  // `meta-frames.css` and the timeline, network and map components all read
  // `--heading-font`, so prefixing these would style nothing.
  const vars = metaStoryStyleVars({
    primary: "#abc",
    headingFont: "DM Serif Display",
    bodyFont: "Source Serif 4",
  });
  expect(vars).toContain('--heading-font: "DM Serif Display"');
  expect(vars).toContain('--body-font: "Source Serif 4"');
  expect(vars).not.toContain("--ms-heading-font");
});

test("an unknown frame contributes no frame variables", () => {
  const vars = metaStoryStyleVars({ primary: "#abc", frame: "no-such-frame" });
  expect(vars).toBe("--ms-primary: #abc");
});

test("a known frame contributes all five", () => {
  const vars = metaStoryStyleVars({ frame: "engraved" });
  expect(vars).toBe(
    "--ms-frame-radius: 2px; --ms-frame-radius-sm: 1px; " +
      "--ms-frame-border-width: 3px; --ms-frame-border-style: double; " +
      "--ms-frame-rule-width: 3px"
  );
});

test("a missing style is the empty string, not a crash", () => {
  expect(storyStyleVars(null)).toBe("");
  expect(storyStyleVars("nonsense")).toBe("");
  expect(metaStoryStyleVars(null)).toBe("");
  expect(metaStoryStyleVars(undefined)).toBe("");
});
