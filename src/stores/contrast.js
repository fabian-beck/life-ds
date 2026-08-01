import { writable } from "svelte/store";
import { localStore } from "../utils/safeStorage.js";

// High-contrast accessibility mode. When enabled, a global overlay boosts the
// contrast of everything rendered on the page (see `html.high-contrast` in
// app.css). The preference is remembered across visits.
const STORAGE_KEY = "highContrast";

const stored = localStore.get(STORAGE_KEY);
const initial = stored === "true";

export const highContrast = writable(initial);

// Persist the preference and reflect it on the document root so the global
// stylesheet can react. Mirrors the pattern used by the language store.
highContrast.subscribe((enabled) => {
  localStore.set(STORAGE_KEY, enabled ? "true" : "false");
  if (typeof document !== "undefined") {
    document.documentElement.classList.toggle("high-contrast", enabled);
  }
});

export function toggleHighContrast() {
  highContrast.update((value) => !value);
}
