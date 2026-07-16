import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";
import { readdirSync, readFileSync } from "fs";
import { resolve } from "path";
import * as mdiExports from "@mdi/js";

/**
 * Vite plugin: virtual:mdi-icon-map
 *
 * Generates a virtual module holding only the MDI icons this app can actually
 * render, as named imports from @mdi/js plus a lookup map. Timeline.svelte once
 * did `import * as mdiIcons from "@mdi/js"`, which defeated tree-shaking and
 * pulled all ~7,400 icons (~2.5 MB) into the bundle.
 *
 * The icon set is the union of two sources, because neither alone is complete:
 *   - scripts/icon_categories.py — the vocabulary offered to the generator
 *   - data/people/**\/life_events.json — what the generator actually emitted,
 *     which drifts from that vocabulary and includes icons it never listed
 *
 * Names that are not real @mdi/js exports are dropped rather than imported:
 * generated data contains category keys mistaken for icon names (e.g.
 * "mdi-lecture"), and emitting `import { mdiLecture }` would break the build.
 * Dropped names resolve to null at runtime, exactly as they did before.
 */
function mdiIconMapPlugin() {
  const virtualId = "virtual:mdi-icon-map";
  const resolvedId = "\0" + virtualId;
  const pyPath = resolve("scripts/icon_categories.py");
  const dataDir = resolve("data/people");

  /** "mdi-some-icon" → "mdiSomeIcon" */
  function toExportKey(mdiName) {
    const parts = mdiName.replace(/^mdi-/, "").split("-");
    return (
      "mdi" +
      parts.map((p) => (p ? p[0].toUpperCase() + p.slice(1) : "")).join("")
    );
  }

  /** Every life_events.json under data/people, translations included. */
  function findEventFiles(dir, out = []) {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const path = resolve(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name !== "_cache") findEventFiles(path, out);
      } else if (entry.name === "life_events.json") {
        out.push(path);
      }
    }
    return out;
  }

  function collectIcons(eventFiles) {
    const icons = new Set();
    // Values in ICON_CATEGORIES, e.g.: "birth": "mdi-candle"
    const py = readFileSync(pyPath, "utf-8");
    for (const m of py.matchAll(/:\s*"(mdi-[\w-]+)"/g)) icons.add(m[1]);

    for (const file of eventFiles) {
      const json = JSON.parse(readFileSync(file, "utf-8"));
      for (const event of json.events ?? []) {
        if (event.event_type_icon) icons.add(event.event_type_icon);
      }
    }
    return icons;
  }

  function generateModule(eventFiles) {
    const valid = [];
    const unknown = [];
    for (const icon of [...collectIcons(eventFiles)].sort()) {
      (toExportKey(icon) in mdiExports ? valid : unknown).push(icon);
    }
    if (unknown.length > 0) {
      this.warn(
        `${unknown.length} icon name(s) in icon_categories.py or life_events.json ` +
          `are not @mdi/js exports and will render no icon: ${unknown.join(", ")}`
      );
    }
    const keys = valid.map(toExportKey);
    return [
      `import { ${keys.join(", ")} } from "@mdi/js";`,
      `export const mdiIconMap = {`,
      ...valid.map((icon, i) => `  "${icon}": ${keys[i]},`),
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
      const eventFiles = findEventFiles(dataDir);
      // HMR: regenerate when the vocabulary or the generated data changes.
      this.addWatchFile(pyPath);
      for (const file of eventFiles) this.addWatchFile(file);
      return generateModule.call(this, eventFiles);
    },
  };
}

export default defineConfig({
  plugins: [mdiIconMapPlugin(), svelte()],
});
