import { toStore } from "svelte/store";
import { router } from "svelte-spa-router";

/**
 * Store views of svelte-spa-router's current location.
 *
 * Version 5 replaced the `location` and `querystring` stores with runes-backed
 * getters on a shared `router` object. Runes can only be declared in components
 * and .svelte.js modules, and `$querystring` is consumed here by a plain
 * `derived()` store, so bridge them back to the store contract rather than
 * spread runes through components that do not otherwise use them.
 *
 * `toStore` subscribes to the underlying signal and establishes its own effect
 * root, so these stay live outside a component. `push`, `pop` and `replace` are
 * unchanged in v5 and should still be imported from svelte-spa-router directly.
 */
export const location = toStore(() => router.location);

export const querystring = toStore(() => router.querystring);
