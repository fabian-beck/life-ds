import { expect, test } from "@playwright/test";
import { describeTarget } from "../src/utils/evaluation/describeTarget.js";

/* A stand-in for an element: the few properties the descriptor reads. */
function element(
  tag,
  { attrs = {}, text = "", classes = [], parent = null } = {}
) {
  return {
    nodeType: 1,
    tagName: tag.toUpperCase(),
    textContent: text,
    classList: classes,
    parentElement: parent,
    getAttribute: (name) => attrs[name] ?? null,
  };
}

test("a click on an icon inside a button describes the button", () => {
  const button = element("button", {
    attrs: { "aria-label": "Show network" },
    classes: ["header-network-btn", "compact", "extra", "more"],
    text: "   ",
  });
  const svg = element("svg", { parent: button });
  const path = element("path", { parent: svg });

  expect(describeTarget(path)).toEqual({
    tag: "button",
    role: null,
    label: "Show network",
    cls: ["header-network-btn", "compact", "extra"],
    href: null,
    interactive: true,
  });
});

test("a link keeps its destination, and long text is shortened", () => {
  const link = element("a", {
    attrs: { href: "https://commons.wikimedia.org/wiki/File:X.jpg" },
    text: "A caption that runs on for far longer than any label should, and then some more",
  });
  const described = describeTarget(link);
  expect(described.href).toBe("https://commons.wikimedia.org/wiki/File:X.jpg");
  expect(described.label.length).toBeLessThanOrEqual(60);
  expect(described.label.endsWith("…")).toBe(true);
});

test("a click on plain prose describes the element itself as non-interactive", () => {
  const paragraph = element("p", {
    text: "Some running text.",
    classes: ["description"],
  });
  expect(describeTarget(paragraph)).toMatchObject({
    tag: "p",
    label: "Some running text.",
    interactive: false,
  });
});

test("an explicit role counts as a control, and a text node is climbed out of", () => {
  const card = element("div", {
    attrs: { role: "button", title: "Open" },
    classes: ["card"],
  });
  const textNode = { nodeType: 3, parentElement: card };
  expect(describeTarget(textNode)).toMatchObject({
    tag: "div",
    role: "button",
    label: "Open",
    interactive: true,
  });
  expect(describeTarget(null)).toBe(null);
});
