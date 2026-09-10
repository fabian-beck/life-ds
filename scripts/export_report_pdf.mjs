#!/usr/bin/env node
/**
 * Print the technical report to PDF.
 *
 *   npm run report:pdf                      # docs/report/index.html -> PDF
 *   npm run report:pdf -- --no-appendix     # without the step appendix
 *   npm run report:pdf -- --out report.pdf  # somewhere else
 *
 * The layout is not this script's: it is the `@media print` half of
 * `scripts/pipeline_docs/assets/style.css`, the same rules a reader gets from
 * Ctrl+P -> Save as PDF. What the script adds is only what a person clicking
 * Print does by hand—wait for the page to finish building itself, open every
 * disclosure so nothing prints as a collapsed summary, and ask for the paper
 * size the stylesheet declares.
 *
 * The report is a generated file, so this reads whatever `generate_report.py`
 * last wrote. Rebuild first if the pipeline or the prose has changed.
 */

import { existsSync, statSync, readFileSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { chromium } from "playwright";

const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const DEFAULT_INPUT = resolve(REPO_ROOT, "docs/report/index.html");
const DEFAULT_OUTPUT = resolve(
  REPO_ROOT,
  "docs/report/life-data-stories-technical-report.pdf"
);

const USAGE = `Print docs/report/index.html to PDF.

  node scripts/export_report_pdf.mjs [options]

  --input <path>    Report page to print (default: docs/report/index.html).
  --out <path>      PDF to write (default: docs/report/<report>.pdf).
  --format <name>   Paper size when the page declares none (default: A4).
  --no-appendix     Leave out the per-step appendix.
  --timeout <ms>    How long to wait for the page to build (default: 30000).
  --help            Show this message.
`;

function parseArgs(argv) {
  const options = {
    input: DEFAULT_INPUT,
    out: DEFAULT_OUTPUT,
    format: "A4",
    appendix: true,
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
    } else if (arg === "--input") options.input = resolve(value());
    else if (arg === "--out") options.out = resolve(value());
    else if (arg === "--format") options.format = value();
    else if (arg === "--no-appendix") options.appendix = false;
    else if (arg === "--timeout") options.timeout = Number(value());
    else throw new Error(`Unknown option: ${arg}\n\n${USAGE}`);
  }
  return options;
}

/* Chromium prints headers and footers into the page margins from their own
   miniature document, which inherits nothing from the report. Hence the inline
   styles, and hence the margin repeated here: without it the running feet sit
   flush against the paper's edge. */
function footerTemplate(title) {
  return `<div style="width:100%;margin:0 17mm;font-family:system-ui,-apple-system,'Segoe UI',helvetica,arial,sans-serif;font-size:8px;color:#6b6b66;display:flex;justify-content:space-between;align-items:center;">
  <span>${title}</span>
  <span><span class="pageNumber"></span> / <span class="totalPages"></span></span>
</div>`;
}

/* Skia writes the page tree uncompressed, so the count is readable without a
   PDF library. It is a log line, not a contract: if the shape ever changes the
   export still succeeded. */
function pageCount(path) {
  const text = readFileSync(path).toString("latin1");
  const counts = [...text.matchAll(/\/Count\s+(\d+)/g)].map((match) =>
    Number(match[1])
  );
  return counts.length ? Math.max(...counts) : null;
}

async function main() {
  const options = parseArgs(process.argv.slice(2));

  if (!existsSync(options.input)) {
    console.error(
      `No report at ${options.input}.\n` +
        "Build it first: python scripts/generate_report.py"
    );
    return 1;
  }

  const url = new URL(pathToFileURL(options.input));
  if (!options.appendix) url.searchParams.set("appendix", "0");

  const browser = await chromium.launch();
  const failures = [];
  try {
    const page = await browser.newPage({
      viewport: { width: 1280, height: 1600 },
    });
    page.on("pageerror", (error) => failures.push(String(error)));

    console.log(`Loading ${options.input} ...`);
    await page.goto(url.href, { waitUntil: "load" });

    // `app.js` sets this once every computed block is mounted. Printing before
    // that would catch the report as an outline of empty figures.
    await page.waitForFunction(
      () =>
        document.documentElement.getAttribute("data-report-ready") === "1",
      undefined,
      { timeout: options.timeout }
    );

    await page.emulateMedia({ media: "print" });

    // The stylesheet cannot open a disclosure and the print events the page
    // listens for are never dispatched through the DevTools protocol, so the
    // script does here what `beforeprint` does in a browser.
    const opened = await page.evaluate(() => {
      const closed = [...document.querySelectorAll("details")].filter(
        (node) => !node.open
      );
      closed.forEach((node) => {
        node.open = true;
      });
      return closed.length;
    });

    const measured = await page.evaluate(() => ({
      steps: document.querySelectorAll(".steps-table .step-row").length,
      figures: document.querySelectorAll("figure.figure").length,
      tables: document.querySelectorAll(".report table.data").length,
    }));
    console.log(
      `  ${measured.figures} figures, ${measured.tables} tables, ` +
        `${measured.steps} appendix entries, ${opened} disclosures opened.`
    );

    const title = await page.title();
    mkdirSync(dirname(options.out), { recursive: true });
    await page.pdf({
      path: options.out,
      format: options.format,
      // The paper size and margins are declared by `@page` in the report's own
      // stylesheet, so printing from a browser gives the same document.
      preferCSSPageSize: true,
      printBackground: true,
      displayHeaderFooter: true,
      headerTemplate: "<span></span>",
      footerTemplate: footerTemplate(title),
    });
  } finally {
    await browser.close();
  }

  if (failures.length) {
    console.error("\nThe page raised errors while it was building:");
    failures.forEach((failure) => console.error(`  ${failure}`));
    return 1;
  }

  const pages = pageCount(options.out);
  const sizeKb = statSync(options.out).size / 1024;
  console.log(
    `\nWrote ${options.out} (${sizeKb.toFixed(0)} KB` +
      (pages ? `, ${pages} pages).` : ").")
  );
  return 0;
}

main().then(
  (code) => process.exit(code),
  (error) => {
    console.error(error instanceof Error ? error.message : error);
    process.exit(1);
  }
);
