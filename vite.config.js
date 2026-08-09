import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";
import { copyFileSync, mkdirSync, readdirSync, readFileSync } from "fs";
import { resolve } from "path";
import * as mdiExports from "@mdi/js";

/**
 * Deployment base path.
 *
 * The dev server and the interface tests serve the application from
 * /life-ds/, so every asset URL has to carry that prefix, and the code that
 * builds those URLs is exercised by every local run rather than only by a
 * production build.
 *
 * The published site is served from the domain root instead, so the Netlify
 * build sets `VITE_BASE_PATH=/` (see netlify.toml). Any other host that serves
 * from a root or from a subdirectory is the same one variable.
 *
 * Code that turns a site-absolute path into a URL must go through
 * `src/utils/assetUrl.js`, which reads this value back as
 * `import.meta.env.BASE_URL`.
 */
const basePath = process.env.VITE_BASE_PATH ?? "/life-ds/";

/**
 * Absolute address of the deployed site.
 *
 * The link-preview tags in index.html need it: an unfurler resolves `og:image`
 * against nothing, so a site-absolute path there is a broken picture. The
 * public address belongs to the deployment rather than to this repository, so
 * the published build reads it from `VITE_SITE_URL` in the Netlify site's
 * environment variables; the fallback below is only a placeholder.
 */
const siteUrl = (
  process.env.VITE_SITE_URL ?? `https://fabian-beck.github.io${basePath}`
).replace(/\/*$/, "/");

/**
 * Vite plugin: social-card
 *
 * Substitutes `%SITE_URL%` in index.html. It runs before Vite's own `%KEY%`
 * env replacement, which only knows `VITE_`-prefixed names and would leave the
 * token standing in the served document.
 */
function socialCardPlugin() {
  return {
    name: "social-card",
    transformIndexHtml: {
      order: "pre",
      handler(html) {
        return html.replaceAll("%SITE_URL%", siteUrl);
      },
    },
  };
}

/**
 * Vite plugin: not-found-fallback
 *
 * The site is published to a static host with no rewrite rules. Shared deep
 * links are hash-based (`/#/en/story/ada_lovelace`) and never reach the
 * server, but path-style entry URLs such as `/en` — which the dev server
 * answers through its SPA fallback, and which the interface tests use — would
 * return the host's 404 page.
 *
 * Publishing index.html as 404.html makes the host serve the application for
 * those paths too, at the cost of a 404 status code that no visitor sees.
 */
function notFoundFallbackPlugin() {
  let outDir;
  return {
    name: "not-found-fallback",
    apply: "build",
    configResolved(config) {
      outDir = config.build.outDir;
    },
    closeBundle() {
      copyFileSync(resolve(outDir, "index.html"), resolve(outDir, "404.html"));
    },
  };
}

/**
 * Vite plugin: technical-report
 *
 * Publishes `docs/report/index.html` — the generated technical report — as
 * `<base>report/` next to the application, so the links in the landing page
 * and the AI-generated modal point at a page on the same deployment instead of
 * at a file that only exists in the repository.
 *
 * The report is a single self-contained HTML file with no external assets, so
 * publishing it is one copy. It is served in dev as well: the dev server's SPA
 * fallback would otherwise answer `/life-ds/report/` with the application, and
 * a link that only resolves in production is a link nothing ever exercises.
 */
function technicalReportPlugin() {
  const reportPath = resolve("docs/report/index.html");
  const reportRoute = `${basePath}report`;
  let outDir;

  return {
    name: "technical-report",
    configResolved(config) {
      outDir = config.build.outDir;
    },
    configureServer(server) {
      // Ahead of the SPA fallback, which claims every extensionless path.
      server.middlewares.use((req, res, next) => {
        const path = req.url.split("?")[0];
        if (path !== reportRoute && path !== `${reportRoute}/`) return next();
        res.setHeader("Content-Type", "text/html; charset=utf-8");
        res.end(readFileSync(reportPath));
      });
    },
    closeBundle() {
      const reportDir = resolve(outDir, "report");
      mkdirSync(reportDir, { recursive: true });
      copyFileSync(reportPath, resolve(reportDir, "index.html"));
    },
  };
}

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
  base: basePath,
  plugins: [
    mdiIconMapPlugin(),
    svelte(),
    socialCardPlugin(),
    technicalReportPlugin(),
    notFoundFallbackPlugin(),
  ],
});
