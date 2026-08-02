#!/usr/bin/env node
/**
 * Take the picture a shared link unfurls to.
 *
 *   npm run preview:card
 *
 * Every story in this project has a URL, and sharing one is a headline feature,
 * so the card a chat client draws for that URL is part of the interface. It is
 * taken from the running application rather than drawn by hand, for the same
 * reason the report's figures are: a picture deposited once ages silently, and
 * nobody can tell when.
 *
 * The landing page at 1200x630 — the size every unfurler crops toward — is the
 * subject, because a static host serves one `index.html` for every route, so
 * one card stands for the whole site.
 */

import { spawn } from "node:child_process";
import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");

/* Mirrors capture_report_screenshots.mjs: the dev server serves the app under
   the deployment base path, and a port of its own keeps this run from fighting
   over one with a capture run or a server someone is already looking at. */
const BASE_PATH = process.env.VITE_BASE_PATH ?? "/life-ds/";
const PORT = Number(process.env.PREVIEW_CARD_PORT ?? 4178);
const ORIGIN = `http://127.0.0.1:${PORT}`;
const OUTPUT = resolve(REPO_ROOT, "public/preview.png");

// The Open Graph card: 1.91:1, the aspect every major unfurler crops toward.
const WIDTH = 1200;
const HEIGHT = 630;

const delay = (ms) =>
  new Promise((resolve_) => {
    setTimeout(resolve_, ms);
  });

async function reachable(url) {
  try {
    const response = await fetch(url, { method: "HEAD" });
    return response.ok || response.status === 404;
  } catch {
    return false;
  }
}

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

/* An already-running server is reused when one answers at the same address.
   Vite is started directly rather than through `npm run dev`, so that killing
   it here does not leave an orphan holding the port. */
async function startServer(url) {
  if (await reachable(url)) {
    console.log(`Using the server already answering at ${url}`);
    return null;
  }
  console.log(`Starting the dev server on ${ORIGIN} ...`);
  const child = spawn(
    process.execPath,
    [
      resolve(REPO_ROOT, "node_modules/vite/bin/vite.js"),
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
  if (!(await waitForServer(url, 120000))) {
    child.kill();
    process.stderr.write(log.join(""));
    throw new Error(`The dev server did not come up at ${url}.`);
  }
  child.stderr.removeAllListeners("data");
  child.stderr.resume();
  return child;
}

async function main() {
  const baseUrl = `${ORIGIN}${BASE_PATH}`;
  const server = await startServer(baseUrl);
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({
      viewport: { width: WIDTH, height: HEIGHT },
      deviceScaleFactor: 1,
    });
    await page.goto(`${baseUrl}#/en`, { waitUntil: "load", timeout: 30000 });
    // The card must show the gallery, not the moment before it arrives.
    await page.waitForSelector(".landing .person-card", {
      state: "visible",
      timeout: 30000,
    });
    await page.waitForTimeout(1200);
    mkdirSync(dirname(OUTPUT), { recursive: true });
    await page.screenshot({ path: OUTPUT, type: "png" });
    console.log(`Wrote ${OUTPUT}`);
  } finally {
    await browser.close();
    if (server) server.kill();
  }
}

main().catch((error) => {
  console.error(error.message ?? error);
  process.exitCode = 1;
});
