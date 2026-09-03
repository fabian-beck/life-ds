import { derived, writable } from "svelte/store";
import { localStore } from "../utils/safeStorage.js";

// Whether the entries marked hidden in the registries are on screen.
//
// A production build never shows them: the condition below folds to a constant
// there. The development server shows them by default, so a story can be
// worked on before it is published, and remembers a switch to the deployed
// view so the landing page can be checked as a reader will see it.

/** True under `npm run dev`; false in every build, including the preview. */
export const developmentMode = Boolean(import.meta.env?.DEV);

const STORAGE_KEY = "previewDeployment";

/** The development-only switch: true while previewing the deployed view. */
export const previewDeployment = writable(
  developmentMode && localStore.get(STORAGE_KEY) === "true"
);

previewDeployment.subscribe((enabled) => {
  if (!developmentMode) return;
  localStore.set(STORAGE_KEY, enabled ? "true" : "false");
});

/** Whether hidden entries are shown: only in development, and only while the
 * deployment preview is off. */
export const showHidden = derived(
  previewDeployment,
  (preview) => developmentMode && !preview
);

export function togglePreviewDeployment() {
  if (!developmentMode) return;
  previewDeployment.update((value) => !value);
}
