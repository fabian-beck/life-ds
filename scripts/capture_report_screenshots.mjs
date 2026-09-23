#!/usr/bin/env node
/**
 * Take the screenshots the technical report declares.
 *
 *   python scripts/generate_report.py --shots        # the usual way in
 *   node scripts/capture_report_screenshots.mjs --manifest shots.json
 *
 * This script knows nothing about the report. It is handed a manifest of
 * pictures to take—a route into the application, a viewport, optionally a
 * selector to wait for and a region to clip—and it writes one image per entry
 * plus a results file saying what it wrote. Everything about where those
 * descriptions come from, and what a taken picture means for the report, is
 * `scripts/pipeline_docs/screenshots.py`.
 *
 * The manifest is the whole contract:
 *
 *   { "outDir": "docs/report/screenshots",
 *     "shots": [{ "id": "person-story", "file": "person-story.png",
 *                 "route": "#/en/story/ada_lovelace", "width": 390,
 *                 "height": 844, "scale": 2, "clip": null, "wait": ".story-view",
 *                 "settle": 400, "scroll": 0, "format": "png" }] }
 *
 * A shot that fails is recorded as a failure and the run continues, so one
 * broken selector costs one figure rather than the whole set.
 */

import { spawn } from "node:child_process";
import {
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");

/* The preview server serves the app under the deployment base path, as Pages
   does, so a route resolves against that rather than the domain root. A port
   of its own, so a capture run and an interface run—or the dev server someone
   is already looking at—never fight over one. */
const BASE_PATH = process.env.VITE_BASE_PATH ?? "/life-ds/";
const PORT = Number(process.env.REPORT_SHOTS_PORT ?? 4177);
const ORIGIN = `http://127.0.0.1:${PORT}`;

const USAGE = `Take the screenshots the technical report declares.

  node scripts/capture_report_screenshots.mjs --manifest <path> [options]

  --manifest <path>   Shots to take (written by generate_report.py --shots).
  --results <path>    Where to write the result record (default: none).
  --base-url <url>    Serve from here instead of building and previewing.
  --timeout <ms>      Per-shot budget (default: 30000).
  --help              Show this message.
`;

function parseArgs(argv) {
  const options = {
    manifest: null,
    results: null,
    baseUrl: null,
    timeout: 30000,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const value = () => {
      const next = argv[index + 1];
      if (next === undefined) throw new Error(`${arg} needs a value.`);
      index += 1;
      return next;
    };
    if (arg === "--help" || arg === "-h") {
      process.stdout.write(USAGE);
      process.exit(0);
    } else if (arg === "--manifest") options.manifest = resolve(value());
    else if (arg === "--results") options.results = resolve(value());
    else if (arg === "--base-url") options.baseUrl = value();
    else if (arg === "--timeout") options.timeout = Number(value());
    else throw new Error(`Unknown option: ${arg}\n\n${USAGE}`);
  }
  if (!options.manifest) throw new Error(`--manifest is required.\n\n${USAGE}`);
  return options;
}

async function reachable(url) {
  try {
    const response = await fetch(url, { redirect: "follow" });
    return response.ok;
  } catch {
    return false;
  }
}

const delay = (ms) =>
  new Promise((done) => {
    setTimeout(done, ms);
  });

async function waitForServer(url, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    // Polling: each probe has to finish before the next one is worth making.
    // eslint-disable-next-line no-await-in-loop
    if (await reachable(url)) return true;
    // eslint-disable-next-line no-await-in-loop
    await delay(500);
  }
  return false;
}

const VITE = resolve(REPO_ROOT, "node_modules/vite/bin/vite.js");

/* Run Vite to completion, keeping its output for the case it fails. */
function runVite(args) {
  return new Promise((done, fail) => {
    const child = spawn(process.execPath, [VITE, ...args], {
      cwd: REPO_ROOT,
      stdio: ["ignore", "pipe", "pipe"],
    });
    const log = [];
    child.stdout.on("data", (chunk) => log.push(String(chunk)));
    child.stderr.on("data", (chunk) => log.push(String(chunk)));
    child.on("error", fail);
    child.on("exit", (code) => {
      if (code === 0) done();
      else {
        process.stderr.write(log.join(""));
        fail(new Error(`vite ${args[0]} exited with ${code}.`));
      }
    });
  });
}

/* The pictures show the application as it is deployed, so they are taken from
   a production build rather than the dev server. The dev server is a
   different application for this purpose: it shows the stories marked hidden
   in the registries and the switch that previews the deployed view, neither
   of which a reader ever sees. The build goes to a directory of its own so
   that `dist/` is left as it was.

   An already-running server is reused when one answers at the same address,
   which is what makes a re-capture cheap while working on the interface.

   Vite is started directly rather than through `npm run preview`: npm is a
   wrapper process, and killing it at the end of the run leaves the server it
   spawned holding the port—which the next run then mistakes for a server it
   may reuse, moments before the orphan notices its parent is gone and exits
   under it. */
async function startServer(url) {
  if (await reachable(url)) {
    console.log(`Using the server already answering at ${url}`);
    return null;
  }
  const outDir = mkdtempSync(join(tmpdir(), "life-ds-report-shots-"));
  const cleanUp = () => rmSync(outDir, { recursive: true, force: true });
  console.log("Building the application for capture ...");
  try {
    await runVite(["build", "--outDir", outDir, "--emptyOutDir"]);
  } catch (error) {
    cleanUp();
    throw error;
  }
  console.log(`Starting the preview server on ${ORIGIN} ...`);
  const child = spawn(
    process.execPath,
    [
      VITE,
      "preview",
      "--outDir",
      outDir,
      "--host",
      "127.0.0.1",
      "--port",
      String(PORT),
      "--strictPort",
    ],
    { cwd: REPO_ROOT, stdio: ["ignore", "ignore", "pipe"] }
  );
  const log = [];
  child.stderr.on("data", (chunk) => log.push(String(chunk)));
  const stop = () => {
    child.kill();
    cleanUp();
  };
  if (!(await waitForServer(url, 120000))) {
    stop();
    process.stderr.write(log.join(""));
    throw new Error(`The preview server did not come up at ${url}.`);
  }
  // Up: stop keeping the log, but keep reading the pipe—a full one would block
  // the server mid-run.
  child.stderr.removeAllListeners("data");
  child.stderr.resume();
  return { stop };
}

function shotUrl(baseUrl, route) {
  const trimmed = String(route).trim();
  if (/^https?:\/\//.test(trimmed)) return trimmed;
  // A route is written the way it is read in the address bar: "#/en/story/x",
  // or a plain path that is turned into one, since the app routes on the hash.
  const hash = trimmed.startsWith("#")
    ? trimmed
    : `#${trimmed.startsWith("/") ? "" : "/"}${trimmed}`;
  return `${baseUrl.replace(/\/$/, "")}/${hash}`;
}

/* Where in the document the picture is taken.
 *
 * An `anchor` is a selector scrolled to the top of the viewport, and it is the
 * stable way to say where: a meta story grows as its sections load their
 * components, so the same pixel offset lands somewhere else depending on how
 * much had arrived when the scroll happened. A named section does not move.
 * `scroll` then adjusts relative to it—which is how a scrollytelling section is
 * advanced from its first narration card to a later one.
 *
 * Without an anchor, `scroll` is an absolute offset, and the wait for the
 * document to grow past it is what keeps a page that is still loading from
 * quietly clamping the offset to its own short height.
 */
async function scrollTo(page, shot, timeout) {
  if (shot.anchor) {
    await page.waitForSelector(shot.anchor, { state: "attached", timeout });
    await page.evaluate(
      ({ selector, offset }) => {
        const target = document.querySelector(selector);
        if (!target) return;
        const top = target.getBoundingClientRect().top + window.scrollY;
        window.scrollTo({ top: top + offset, behavior: "auto" });
      },
      { selector: shot.anchor, offset: shot.scroll || 0 }
    );
  } else {
    try {
      await page.waitForFunction(
        (wanted) => document.documentElement.scrollHeight > wanted,
        shot.scroll,
        { timeout: Math.min(timeout, 15000) }
      );
    } catch {
      process.stdout.write("(never grew past the scroll offset) ");
    }
    await page.evaluate((wanted) => {
      window.scrollTo({ top: wanted, behavior: "auto" });
    }, shot.scroll);
  }
  // Scroll-driven sections react to the event, not to the offset; the wait is
  // for that reaction to start before `settle` waits for it to finish.
  await page.waitForTimeout(300);
}

async function capture(browser, shot, baseUrl, outDir, timeout) {
  const context = await browser.newContext({
    viewport: { width: shot.width, height: shot.height },
    deviceScaleFactor: shot.scale || 1,
    // A screenshot is one frame of a page that is still moving otherwise:
    // slide transitions, the network simulation, the map's camera. Reduced
    // motion is what the application itself listens to, so asking for it here
    // is asking for the state the picture is supposed to show.
    reducedMotion: "reduce",
    isMobile: shot.width < 700,
    hasTouch: shot.width < 700,
  });
  const page = await context.newPage();
  const failures = [];
  page.on("pageerror", (error) => failures.push(String(error)));
  try {
    const url = shotUrl(baseUrl, shot.route);
    await page.goto(url, { waitUntil: "load", timeout });
    if (shot.wait) {
      await page.waitForSelector(shot.wait, { state: "visible", timeout });
    }
    // Web fonts decide the metrics of every label in the picture; a shot taken
    // before they land is a shot of a different layout.
    await page.evaluate(() => document.fonts && document.fonts.ready);
    if (shot.anchor || shot.scroll) await scrollTo(page, shot, timeout);
    if (shot.settle) await page.waitForTimeout(shot.settle);

    const options = {
      path: resolve(outDir, shot.file),
      type: shot.format === "jpeg" ? "jpeg" : "png",
      animations: "disabled",
      caret: "hide",
    };
    if (shot.format === "jpeg" && shot.quality) options.quality = shot.quality;
    if (shot.clip) {
      const [x, y, width, height] = shot.clip;
      options.clip = { x, y, width, height };
    }
    await page.screenshot(options);
    return { bytes: statSync(options.path).size, failures };
  } finally {
    await context.close();
  }
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const manifest = JSON.parse(readFileSync(options.manifest, "utf-8"));
  const shots = manifest.shots || [];
  const outDir = resolve(
    REPO_ROOT,
    manifest.outDir || "docs/report/screenshots"
  );
  mkdirSync(outDir, { recursive: true });

  const baseUrl = options.baseUrl ?? `${ORIGIN}${BASE_PATH}`;
  const server = options.baseUrl ? null : await startServer(baseUrl);

  const results = [];
  let browser = null;
  try {
    browser = await chromium.launch();
    for (const shot of shots) {
      process.stdout.write(`  ${shot.id} ... `);
      try {
        // One at a time, deliberately: parallel pages share a server and a
        // GPU, and a picture of a page that was starved of both is not the
        // picture the declaration describes.
        // eslint-disable-next-line no-await-in-loop
        const written = await capture(
          browser,
          shot,
          baseUrl,
          outDir,
          options.timeout
        );
        results.push({
          id: shot.id,
          file: shot.file,
          bytes: written.bytes,
          captured: new Date().toISOString().replace(/\.\d+Z$/, "Z"),
        });
        console.log(
          `${(written.bytes / 1024).toFixed(0)} KB` +
            (written.failures.length
              ? ` (the page raised ${written.failures.length} error(s))`
              : "")
        );
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        results.push({ id: shot.id, error: message.split("\n")[0] });
        console.log(`failed: ${message.split("\n")[0]}`);
      }
    }
  } finally {
    if (browser) await browser.close();
    if (server) server.stop();
  }

  if (options.results) {
    writeFileSync(
      options.results,
      JSON.stringify({ baseUrl, shots: results }, null, 2),
      "utf-8"
    );
  }
  return results.some((result) => result.error) ? 1 : 0;
}

main().then(
  (code) => process.exit(code),
  (error) => {
    console.error(error instanceof Error ? error.message : error);
    process.exit(1);
  }
);
