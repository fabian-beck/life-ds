import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";
import { readFileSync } from "fs";
import { resolve } from "path";

/**
 * Vite plugin: virtual:mdi-icon-map
 *
 * Reads scripts/icon_categories.py at build time, extracts the unique set of
 * MDI icon strings (e.g. "mdi-crown"), and generates a virtual JS module with
 * named imports from @mdi/js plus a lookup map.
 *
 * This keeps icon_categories.py as the single source of truth — no generated
 * file, no manual sync step.  In dev mode, editing icon_categories.py triggers
 * an HMR reload automatically.
 */
function mdiIconMapPlugin() {
  const virtualId = "virtual:mdi-icon-map";
  const resolvedId = "\0" + virtualId;
  const pyPath = resolve("scripts/icon_categories.py");

  /** "mdi-some-icon" → "mdiSomeIcon" */
  function toExportKey(mdiName) {
    const parts = mdiName.replace(/^mdi-/, "").split("-");
    return "mdi" + parts.map((p) => p[0].toUpperCase() + p.slice(1)).join("");
  }

  function generateModule() {
    const src = readFileSync(pyPath, "utf-8");
    // Match the string values in ICON_CATEGORIES, e.g.: "birth": "mdi-candle"
    const icons = new Set();
    for (const m of src.matchAll(/:\s*"(mdi-[\w-]+)"/g)) {
      icons.add(m[1]);
    }
    const sorted = [...icons].sort();
    const keys = sorted.map(toExportKey);
    return [
      `import { ${keys.join(", ")} } from "@mdi/js";`,
      `export const mdiIconMap = {`,
      ...sorted.map((icon, i) => `  "${icon}": ${keys[i]},`),
      `};`,
    ].join("\n");
  }

  return {
    name: "mdi-icon-map",
    resolveId(id) {
      if (id === virtualId) return resolvedId;
    },
    load(id) {
      if (id !== resolvedId) return;
      this.addWatchFile(pyPath); // HMR: rebuild when .py changes
      return generateModule();
    },
  };
}

export default defineConfig({
  plugins: [mdiIconMapPlugin(), svelte()],
});
