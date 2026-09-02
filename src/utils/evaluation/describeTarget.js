/**
 * Describe what a click landed on, for the interaction log.
 *
 * The log records every click, and what a click means depends on the control
 * under it — which is usually an ancestor of the node the browser reports,
 * since a tap on a button lands on its label or its icon. The description
 * climbs to the nearest interactive ancestor and reads the little a control
 * says about itself: its element, its role, its accessible name, and a hint
 * of its classes. No text a reader typed is ever read: an input reports its
 * label, never its value.
 *
 * Written against the few DOM properties it needs, so a plain object with the
 * same shape stands in for an element in the logic tests.
 */

const INTERACTIVE_TAGS = new Set([
  "a",
  "button",
  "input",
  "select",
  "textarea",
  "summary",
  "label",
  "option",
]);

const INTERACTIVE_ROLES = new Set([
  "button",
  "link",
  "tab",
  "menuitem",
  "option",
  "checkbox",
  "radio",
  "switch",
  "slider",
]);

const MAX_LABEL = 60;
const MAX_CLASSES = 3;

function attribute(element, name) {
  return typeof element.getAttribute === "function"
    ? element.getAttribute(name)
    : null;
}

function isInteractive(element) {
  const tag = String(element.tagName ?? "").toLowerCase();
  if (INTERACTIVE_TAGS.has(tag)) return true;
  const role = attribute(element, "role");
  if (role && INTERACTIVE_ROLES.has(role)) return true;
  const tabindex = attribute(element, "tabindex");
  return tabindex !== null && tabindex !== "-1";
}

function collapse(text) {
  return String(text ?? "")
    .replace(/\s+/g, " ")
    .trim();
}

function labelOf(element) {
  const explicit =
    attribute(element, "aria-label") ||
    attribute(element, "title") ||
    attribute(element, "alt") ||
    attribute(element, "placeholder");
  const text = collapse(explicit || element.textContent);
  return text.length > MAX_LABEL ? `${text.slice(0, MAX_LABEL - 1)}…` : text;
}

function classesOf(element) {
  const list = element.classList
    ? Array.from(element.classList)
    : collapse(attribute(element, "class")).split(" ").filter(Boolean);
  return list.slice(0, MAX_CLASSES);
}

/**
 * @typedef {Object} TargetDescription
 * @property {string} tag - The element name, lowercase
 * @property {string|null} role - Its explicit ARIA role
 * @property {string} label - Its accessible name or text, shortened
 * @property {string[]} cls - Up to three of its classes
 * @property {string|null} href - A link's destination
 * @property {boolean} interactive - Whether a control was found at all
 */

/**
 * @param {any} node - The event target
 * @param {Object} [options]
 * @param {number} [options.maxDepth] - How many ancestors to consider
 * @returns {TargetDescription|null}
 */
export function describeTarget(node, { maxDepth = 8 } = {}) {
  let element =
    node && node.nodeType === 1 ? node : (node?.parentElement ?? null);
  const origin = element;
  let depth = 0;
  let control = null;
  while (element && depth <= maxDepth) {
    if (isInteractive(element)) {
      control = element;
      break;
    }
    element = element.parentElement ?? null;
    depth += 1;
  }
  const target = control ?? origin;
  if (!target) return null;
  const href = attribute(target, "href");
  return {
    tag: String(target.tagName ?? "").toLowerCase(),
    role: attribute(target, "role"),
    label: labelOf(target),
    cls: classesOf(target),
    href: href || null,
    interactive: control !== null,
  };
}
