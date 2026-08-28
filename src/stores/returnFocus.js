/**
 * Puts keyboard focus back where the reader left it after a route change.
 *
 * A modal can hold on to the element that opened it (`src/utils/dialog.js`
 * does exactly that), because the page behind it is still there. A route
 * change cannot: opening a story unmounts the landing entirely, so by the time
 * the reader closes it the card they pressed no longer exists. What survives
 * is its identity — every trigger carries a `data-focus-id`, and that is what
 * is remembered. The id names the control, not the thing it leads to: a person
 * is reachable both from a grid card and from a carousel portrait, and coming
 * back to the wrong one of the two is its own small betrayal.
 *
 * Without this the browser drops focus to `<body>` on each transition, and a
 * reader who opened the thirtieth card has to tab through the whole page again
 * to get back to it.
 */

// How long to keep looking for the trigger after the route changes, and how
// often. The destination mounts and then loads its data asynchronously, so the
// element usually appears almost at once — but not always, and a budget
// counted in frames silently becomes a speed test.
//
// Timers rather than `requestAnimationFrame`: rAF is tied to rendering, and a
// tab that is not painting (backgrounded, or a browser under load) can stall
// it indefinitely. Restoring focus is not an animation and must not wait on
// one.
const MAX_WAIT_MS = 2000;
const RETRY_MS = 16;

let pendingFocusId = null;

/**
 * Remember the control that is about to navigate. Call before pushing a route.
 * @param {EventTarget|null} [element] - defaults to whatever has focus
 */
export function rememberFocusTrigger(element) {
  const trigger = element ?? document.activeElement;
  const holder =
    trigger instanceof Element ? trigger.closest("[data-focus-id]") : null;
  pendingFocusId =
    holder instanceof HTMLElement ? (holder.dataset.focusId ?? null) : null;
}

/**
 * Focus the remembered trigger once it exists again. Call after replacing the
 * route. The pending id is consumed either way, so a second return does not
 * reuse a stale one.
 * @param {string} [fallbackSelector] - focused when the trigger never appears,
 *   so that focus lands on a landmark rather than on `<body>`
 */
export function restoreFocusTrigger(fallbackSelector) {
  const focusId = pendingFocusId;
  pendingFocusId = null;
  if (typeof document === "undefined") return;

  const deadline = performance.now() + MAX_WAIT_MS;
  // Usually the close control that is about to be unmounted. Comparing against
  // it is what distinguishes "focus has not moved yet" from "the reader has
  // since chosen something", which must not be taken away from them.
  const startedWith = document.activeElement;

  const attempt = () => {
    const held = document.activeElement;
    if (
      held &&
      held !== startedWith &&
      held !== document.body &&
      held !== document.documentElement &&
      held.isConnected
    ) {
      return;
    }
    if (focusId) {
      const target = document.querySelector(
        `[data-focus-id="${CSS.escape(focusId)}"]`
      );
      // The trigger can come back unreachable — a carousel that advanced while
      // the reader was away leaves its slide `inert`. Verifying the focus took
      // is what keeps that case falling through to the landmark below rather
      // than leaving focus on `<body>`.
      if (target instanceof HTMLElement && !target.closest("[inert]")) {
        target.focus();
        if (document.activeElement === target) return;
      }
    }
    // Only the trigger is worth waiting for; the landmark is always there.
    if (focusId && performance.now() < deadline) {
      setTimeout(attempt, RETRY_MS);
      return;
    }
    const fallback = fallbackSelector
      ? document.querySelector(fallbackSelector)
      : null;
    if (fallback instanceof HTMLElement)
      fallback.focus({ preventScroll: true });
  };
  setTimeout(attempt, 0);
}
