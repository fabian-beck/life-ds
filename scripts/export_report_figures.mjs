#!/usr/bin/env node
/**
 * Print the drawn figures of the technical report to vector PDFs.
 *
 *   python scripts/generate_report.py --figures    # the usual way in
 *   node scripts/export_report_figures.mjs --manifest figures.json
 *
 * The teaser and the pipeline charts are drawn by `app.js` in the browser, so
 * the LaTeX rendering of the report cannot draw them itself. This script opens
 * the built page, waits for it to finish drawing, and prints each declared
 * figure's SVG to a PDF of exactly its own size—text kept as text, so the
 * drawing stays sharp at any scale and its type embeds like the rest of the
 * document. `latex.py` then includes the file where the figure belongs.
 *
 * Like `capture_report_screenshots.mjs`, this script knows nothing about the
 * report. The manifest says which element to print and where to write it:
 *
 *   { "input": "docs/report/index.html",
 *     "outDir": "docs/report/latex/figures",
 *     "figures": [{ "id": "pipeline-person", "file": "pipeline-person.pdf",
 *                   "selector": ".widget[data-lane=\"person\"] svg" }] }
 *
 * A figure that fails is recorded as a failure and the run continues.
 */

import { mkdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { chromium } from "playwright";

const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");

const USAGE = `Print the report's drawn figures to vector PDFs.

  node scripts/export_report_figures.mjs --manifest <path> [options]

  --manifest <path>   Figures to print (written by generate_report.py --figures).
  --results <path>    Where to write the result record (default: none).
  --timeout <ms>      How long to wait for the page to build (default: 30000).
  --help              Show this message.
`;

function parseArgs(argv) {
  const options = { manifest: null, results: null, timeout: 30000 };
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
    else if (arg === "--timeout") options.timeout = Number(value());
    else throw new Error(`Unknown option: ${arg}\n\n${USAGE}`);
  }
  if (!options.manifest) throw new Error(`--manifest is required.\n\n${USAGE}`);
  return options;
}

/* The drawing, lifted out of the page with the wrappers its stylesheet
   addresses it through. A chart is styled by rules such as
   `.chart-scroll > svg` and `figure.figure .node`, so the SVG alone would
   print unstyled; the chain of ancestors up to the computed block is rebuilt
   around it, each with its classes and none of its siblings. */
function liftFigure(selector) {
  const svg = document.querySelector(selector);
  if (!svg) return { error: `nothing matches ${selector}` };
  const box = (svg.getAttribute("viewBox") || "").trim().split(/[\s,]+/);
  if (box.length !== 4) return { error: `${selector} has no viewBox` };
  const width = Number(box[2]);
  const height = Number(box[3]);
  if (!(width > 0 && height > 0)) {
    return { error: `${selector} has an empty viewBox` };
  }
  const chain = [];
  let node = svg.parentElement;
  while (node && node !== document.body) {
    chain.unshift({
      tag: node.tagName.toLowerCase(),
      className: node.getAttribute("class") || "",
    });
    if (node.classList.contains("widget")) break;
    node = node.parentElement;
  }
  const css = Array.from(document.querySelectorAll("style"))
    .map((style) => style.textContent)
    .join("\n");
  return { width, height, chain, css, svg: svg.outerHTML };
}

/* A page of exactly the drawing's size, so the PDF is the figure and nothing
   else: the sheet is fitted to the drawing, not the drawing to a sheet.
   The SVG is pinned to its scene size in CSS pixels, one per viewBox unit, and
   the stylesheet's own sizing of it is overridden with `!important`, since
   `app.js` writes a measured width onto the element. */
function figurePage(lifted) {
  const open = lifted.chain
    .map((node) => `<${node.tag} class="${node.className}">`)
    .join("");
  const close = lifted.chain
    .slice()
    .reverse()
    .map((node) => `</${node.tag}>`)
    .join("");
  return `<!doctype html><html lang="en"><head><meta charset="utf-8">
<style>${lifted.css}</style>
<style>
  @page { size: ${lifted.width}px ${lifted.height}px; margin: 0; }
  html, body { margin: 0; padding: 0; background: #ffffff; }
  * { print-color-adjust: exact; -webkit-print-color-adjust: exact; }
  html, body { overflow: hidden; }
  .figure-export, .figure-export > *, .figure-export svg, [class] .figure-export * {
    max-width: none !important;
  }
  /* The wrappers are here for their selectors only: their own margins, frames
     and padding belong to the page, and a margin above the block would push
     the drawing onto a second sheet. */
  .figure-export, .figure-export div, .figure-export figure {
    display: block !important;
    margin: 0 !important;
    padding: 0 !important;
    border: 0 !important;
    overflow: visible !important;
    width: ${lifted.width}px !important;
    height: ${lifted.height}px !important;
  }
  .figure-export svg {
    display: block;
    width: ${lifted.width}px !important;
    height: ${lifted.height}px !important;
    min-width: 0 !important;
    max-height: none !important;
    aspect-ratio: auto !important;
  }
</style></head><body><div class="report figure-export">${open}${lifted.svg}${close}</div></body></html>`;
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const manifest = JSON.parse(readFileSync(options.manifest, "utf8"));
  const input = resolve(REPO_ROOT, manifest.input || "docs/report/index.html");
  const outDir = resolve(
    REPO_ROOT,
    manifest.outDir || "docs/report/latex/figures"
  );
  mkdirSync(outDir, { recursive: true });

  const browser = await chromium.launch();
  const results = [];
  try {
    const page = await browser.newPage({
      viewport: { width: 1280, height: 1600 },
    });
    console.log(`Loading ${input} ...`);
    await page.goto(pathToFileURL(input).href, { waitUntil: "load" });
    // `app.js` sets this once every computed block is mounted; before that a
    // chart is an empty mount point.
    await page.waitForFunction(
      () => document.documentElement.getAttribute("data-report-ready") === "1",
      undefined,
      { timeout: options.timeout }
    );

    for (const figure of manifest.figures || []) {
      process.stdout.write(`  ${figure.id} ... `);
      const target = resolve(outDir, figure.file);
      try {
        // Sequential on purpose: one page is lifted from, and one PDF written,
        // at a time.
        // eslint-disable-next-line no-await-in-loop
        const lifted = await page.evaluate(liftFigure, figure.selector);
        if (lifted.error) throw new Error(lifted.error);
        // eslint-disable-next-line no-await-in-loop
        const sheet = await browser.newPage();
        try {
          // eslint-disable-next-line no-await-in-loop
          await sheet.setContent(figurePage(lifted), { waitUntil: "load" });
          // eslint-disable-next-line no-await-in-loop
          await sheet.emulateMedia({ media: "screen" });
          // eslint-disable-next-line no-await-in-loop
          await sheet.pdf({
            path: target,
            width: `${lifted.width}px`,
            height: `${lifted.height}px`,
            printBackground: true,
            preferCSSPageSize: true,
          });
        } finally {
          // eslint-disable-next-line no-await-in-loop
          await sheet.close();
        }
        const bytes = statSync(target).size;
        results.push({
          id: figure.id,
          file: figure.file,
          width: lifted.width,
          height: lifted.height,
          bytes,
          exported: new Date().toISOString().replace(/\.\d{3}Z$/, "Z"),
        });
        console.log(
          `${lifted.width}×${lifted.height}, ${(bytes / 1024).toFixed(0)} KB`
        );
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        results.push({ id: figure.id, file: figure.file, error: message });
        console.log(`FAILED: ${message}`);
      }
    }
  } finally {
    await browser.close();
  }

  if (options.results) {
    mkdirSync(dirname(options.results), { recursive: true });
    writeFileSync(
      options.results,
      JSON.stringify({ figures: results }, null, 2)
    );
  }
  const failed = results.filter((result) => result.error).length;
  console.log(
    `\n${results.length - failed} figure(s) written to ${outDir}` +
      (failed ? `, ${failed} failed.` : ".")
  );
  return failed ? 1 : 0;
}

main().then(
  (code) => process.exit(code),
  (error) => {
    console.error(error instanceof Error ? error.message : error);
    process.exit(1);
  }
);
