#!/usr/bin/env node
/**
 * Print the technical report to PDF.
 *
 *     node scripts/report_pdf.js                    # docs/report/report.pdf
 *     node scripts/report_pdf.js --doi 10.5281/…    # stamp a DOI in the footer
 *
 * The HTML report is the primary artifact—it is interactive, and the PDF is
 * not. What the PDF is for is the things a single self-contained page cannot
 * be: a fixed rendition that a repository can preview on its landing page, that
 * cites cleanly with page numbers, and that will still open in fifty years.
 * Each published version gets one, alongside the HTML.
 *
 * The page is printed as it stands. Everything the report shows on load is on
 * paper; what needs a click—the step drawer, the chart's own filters—is not,
 * and the captions already read as descriptions of a static figure. The
 * collapsed schema blocks are the exception: `app.js` opens them on
 * `beforeprint`, which this script dispatches before printing.
 *
 * Chromium comes from Playwright, already a dev dependency for the interface
 * tests. Run `npx playwright install chromium` once per machine.
 */

import { chromium } from "@playwright/test";
import { mkdir, readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const DEFAULT_IN = resolve(REPO_ROOT, "docs/report/index.html");
const DEFAULT_OUT = resolve(REPO_ROOT, "docs/report/report.pdf");

// A hydrated page draws its charts from the payload; an un-hydrated one would
// print a page of empty mounts. Waiting on the mounts themselves rather than on
// a timeout keeps the output the same on a slow machine as on a fast one.
const HYDRATION_TIMEOUT = 60000;

// The viewport is the A4 content box of the `@page` rule in `style.css`—178mm
// by 261mm at 96dpi. Chromium lays the document out at the paper width when it
// prints, but not before, and the report measures its tables in `beforeprint`
// to decide which of them need a landscape page. Rendering at the paper width
// throughout is what makes that measurement describe the paper.
const PAPER = { width: 673, height: 986 };

function parseArgs(argv) {
  const options = {
    in: DEFAULT_IN,
    out: DEFAULT_OUT,
    doi: process.env.LDS_REPORT_DOI || "",
  };
  for (let i = 0; i < argv.length; i += 1) {
    const flag = argv[i];
    const value = argv[i + 1];
    if (flag === "--in" || flag === "--out" || flag === "--doi") {
      if (value === undefined) throw new Error(`${flag} needs a value.`);
      options[flag.slice(2)] = flag === "--doi" ? value : resolve(value);
      i += 1;
    } else if (flag === "--help" || flag === "-h") {
      options.help = true;
    } else {
      throw new Error(`Unknown argument: ${flag}`);
    }
  }
  return options;
}

/** Build stamp from the report's own payload, so the PDF cannot claim a
    different provenance than the page it was printed from. */
async function buildStamp(path) {
  const html = await readFile(path, "utf8");
  const match = html.match(
    /<script id="payload" type="application\/json">([\s\S]*?)<\/script>/
  );
  if (!match) return {};
  try {
    const payload = JSON.parse(match[1].replace(/<\\\//g, "</"));
    return { built: payload.generated_at, commit: payload.commit };
  } catch {
    return {};
  }
}

function footerTemplate(stamp, doi) {
  const left = [
    stamp.built ? `Built ${stamp.built}` : "",
    stamp.commit ? `Commit ${stamp.commit}` : "",
    doi,
  ]
    .filter(Boolean)
    .join(" &middot; ");
  // Chromium renders header and footer templates in their own document, with
  // no access to the page's stylesheet—hence the inline styles.
  return `<div style="width:100%;margin:0 16mm;font-family:Georgia,serif;
      font-size:7.5pt;color:#666;display:flex;justify-content:space-between;
      border-top:0.5px solid #ccc;padding-top:3mm;">
      <span>${left}</span>
      <span><span class="pageNumber"></span> / <span class="totalPages"></span></span>
    </div>`;
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  if (options.help) {
    console.log(
      "Usage: node scripts/report_pdf.js [--in index.html] " +
        "[--out report.pdf] [--doi DOI]"
    );
    return 0;
  }

  const stamp = await buildStamp(options.in);
  await mkdir(dirname(options.out), { recursive: true });

  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({ viewport: PAPER });
    const failures = [];
    page.on("pageerror", (error) => failures.push(error.message));
    await page.goto(pathToFileURL(options.in).href, { waitUntil: "load" });

    await page.waitForFunction(
      () => {
        const mounts = document.querySelectorAll(".widget[data-component]");
        if (!mounts.length) return false;
        return Array.prototype.every.call(
          mounts,
          (widget) => widget.querySelector(".widget-mount")?.childElementCount
        );
      },
      undefined,
      { timeout: HYDRATION_TIMEOUT }
    );
    await page.evaluate(() => document.fonts.ready);

    if (failures.length) {
      console.error("The report raised errors while rendering:");
      failures.forEach((message) => console.error(`  ${message}`));
      return 1;
    }

    // `page.pdf` prints without a print dialog, so nothing else dispatches the
    // event the report listens for to open its collapsed schema blocks and
    // pick out the tables that need a landscape page. Print media has to be in
    // force first: that handler measures, and screen widths are not print
    // widths.
    await page.emulateMedia({ media: "print" });
    await page.evaluate(() => window.dispatchEvent(new Event("beforeprint")));

    await page.pdf({
      path: options.out,
      // Paper size and margins come from the report's own `@page` rules, so
      // this file and the browser's print dialog produce the same document.
      preferCSSPageSize: true,
      printBackground: true,
      displayHeaderFooter: true,
      headerTemplate: "<span></span>",
      footerTemplate: footerTemplate(stamp, options.doi),
    });
  } finally {
    await browser.close();
  }

  console.log(`Wrote ${options.out}`);
  return 0;
}

main().then(
  (code) => process.exit(code),
  (error) => {
    console.error(error.message || error);
    if (/Executable doesn't exist|browserType.launch/.test(String(error))) {
      console.error(
        "\nRun `npx playwright install chromium` once per machine."
      );
    }
    process.exit(1);
  }
);
