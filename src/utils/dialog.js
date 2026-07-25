const FOCUSABLE_SELECTOR = [
  "a[href]",
  "area[href]",
  "button:not([disabled])",
  "input:not([disabled]):not([type='hidden'])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "iframe",
  "object",
  "embed",
  "summary",
  "[contenteditable='true']",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

function getFocusableElements(node) {
  return Array.from(node.querySelectorAll(FOCUSABLE_SELECTOR)).filter(
    (element) =>
      element.getClientRects().length > 0 &&
      getComputedStyle(element).visibility !== "hidden" &&
      element.getAttribute("aria-hidden") !== "true"
  );
}

/**
 * Give a modal dialog predictable keyboard and focus behaviour.
 *
 * The action focuses the dialog, keeps Tab navigation inside it, handles
 * Escape, makes the page behind it inert, and restores focus when it closes.
 */
export function dialog(node, initialOptions = {}) {
  let options = initialOptions;
  const previouslyFocused = document.activeElement;
  const overlay = node.closest("[data-dialog-overlay]") || node;
  const siblings = Array.from(overlay.parentElement?.children || [])
    .filter((element) => element !== overlay)
    .map((element) => ({ element, wasInert: element.inert }));

  siblings.forEach(({ element }) => {
    element.inert = true;
  });

  function focusInitialElement() {
    const requestedTarget = options.initialFocus
      ? node.querySelector(options.initialFocus)
      : null;
    const target = requestedTarget || getFocusableElements(node)[0] || node;
    target.focus({ preventScroll: true });
  }

  function handleKeydown(event) {
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      options.onClose?.();
      return;
    }

    if (event.key !== "Tab") return;

    const focusableElements = getFocusableElements(node);
    if (focusableElements.length === 0) {
      event.preventDefault();
      node.focus({ preventScroll: true });
      return;
    }

    const first = focusableElements[0];
    const last = focusableElements[focusableElements.length - 1];
    const focusIsInside = node.contains(document.activeElement);

    if (
      !focusIsInside ||
      (event.shiftKey && document.activeElement === first)
    ) {
      event.preventDefault();
      (event.shiftKey ? last : first).focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  document.addEventListener("keydown", handleKeydown, true);
  queueMicrotask(focusInitialElement);

  return {
    update(nextOptions) {
      options = nextOptions;
    },
    destroy() {
      document.removeEventListener("keydown", handleKeydown, true);
      siblings.forEach(({ element, wasInert }) => {
        element.inert = wasInert;
      });

      queueMicrotask(() => {
        if (
          previouslyFocused instanceof HTMLElement &&
          previouslyFocused.isConnected
        ) {
          previouslyFocused.focus({ preventScroll: true });
        }
      });
    },
  };
}
