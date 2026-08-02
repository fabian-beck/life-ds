/**
 * Svelte action that moves an element to a different parent, by default
 * `document.body`.
 *
 * Use it for overlays positioned against the viewport. A `position: fixed`
 * element resolves against its nearest ancestor that establishes a containing
 * block, and `transform`, `filter`, `backdrop-filter`, and `will-change` on an
 * ancestor all create one. The sticky headers use `backdrop-filter`, so an
 * overlay rendered inside one would be trapped in the header's box instead of
 * spanning the viewport.
 *
 * @param {HTMLElement} node
 * @param {HTMLElement} [target]
 */
export function portal(node, target = document.body) {
  let currentTarget;

  function mount(nextTarget) {
    currentTarget = nextTarget ?? document.body;
    currentTarget.appendChild(node);
  }

  mount(target);

  return {
    update(nextTarget) {
      if ((nextTarget ?? document.body) !== currentTarget) {
        mount(nextTarget);
      }
    },
    destroy() {
      if (node.parentNode) {
        node.parentNode.removeChild(node);
      }
    },
  };
}
