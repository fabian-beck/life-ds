/**
 * Vendor the Protomaps sprite and glyph assets the basemap needs.
 *
 * The basemap tiles are served from `public/basemap.pmtiles`, but the style
 * that renders them used to point its `sprite` and `glyphs` at
 * protomaps.github.io. Every map view therefore disclosed the visitor's IP to
 * a US CDN, and rendered badly whenever that host was slow or unreachable —
 * missing icons and locally drawn fallback letterforms.
 *
 * Downloading every range the upstream publishes would cost 10.6 MB, half of
 * it letterforms this basemap never sets. So the ranges are derived from the
 * tiles instead: every `name…` property of every feature in every tile is
 * read, and only the ranges those codepoints fall into are fetched. Rerun this
 * after replacing `public/basemap.pmtiles` — a different extract labels
 * different places, in different scripts.
 *
 *   node scripts/vendor_basemap_assets.mjs           # download what is missing
 *   node scripts/vendor_basemap_assets.mjs --check   # report, write nothing
 *   node scripts/vendor_basemap_assets.mjs --force   # redownload everything
 */

import { mkdir, readFile, writeFile, stat } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { PMTiles } from "pmtiles";
import { VectorTile } from "@mapbox/vector-tile";
import { PbfReader } from "pbf";
import { layers, namedFlavor } from "@protomaps/basemaps";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const PMTILES = join(ROOT, "public", "basemap.pmtiles");
const OUT = join(ROOT, "public", "basemap-assets");
const UPSTREAM = "https://protomaps.github.io/basemaps-assets";

// MapLibre asks for glyphs 256 codepoints at a time, which is also how the
// upstream files are cut.
const RANGE_SIZE = 256;

// The sprite sheet the dark flavor names, in both pixel ratios MapLibre may
// ask for.
const SPRITE_FILES = [
  "dark.json",
  "dark.png",
  "dark@2x.json",
  "dark@2x.png",
];

/**
 * The font stacks the built style actually sets text in.
 *
 * Read from the style rather than listed here: a flavor may reach for another
 * weight, and a stack nobody sets text in is a directory of letterforms no
 * visitor ever loads.
 * @returns {Array<string>} Font stack names, e.g. "Noto Sans Regular"
 */
function fontStacksInStyle() {
  const found = new Set();
  const walk = (value) => {
    if (Array.isArray(value)) {
      value.forEach(walk);
      return;
    }
    if (typeof value === "string") found.add(value);
  };
  for (const layer of layers("protomaps", namedFlavor("dark"), { lang: "en" })) {
    const fonts = layer?.layout?.["text-font"];
    if (fonts) walk(fonts);
  }
  // The `case` expression that picks a weight by zoom contributes its operator
  // and its property name alongside the font names; a font stack is the only
  // string that names a face this basemap ships.
  return [...found].filter((name) => name.startsWith("Noto Sans "));
}

/** Serve the local pmtiles file to the reader as if it were a range source. */
class FileSource {
  /** @param {Buffer} buffer - The whole pmtiles file */
  constructor(buffer) {
    this.buffer = buffer;
  }

  /** @returns {string} Cache key for the reader */
  getKey() {
    return PMTILES;
  }

  /**
   * @param {number} offset - Byte offset
   * @param {number} length - Byte count
   * @returns {Promise<{data: ArrayBuffer}>} The requested slice
   */
  async getBytes(offset, length) {
    const { buffer, byteOffset } = this.buffer;
    return { data: buffer.slice(byteOffset + offset, byteOffset + offset + length) };
  }
}

/**
 * Every glyph range the basemap's own labels reach into.
 * @returns {Promise<{ranges: Array<number>, codepoints: number, tiles: number}>}
 *   Range indices in ascending order, with what they were read from
 */
async function rangesTheBasemapLabels() {
  const reader = new PMTiles(new FileSource(await readFile(PMTILES)));
  const header = await reader.getHeader();
  const codepoints = new Set();
  let tiles = 0;

  for (let z = header.minZoom; z <= header.maxZoom; z += 1) {
    const side = 2 ** z;
    for (let x = 0; x < side; x += 1) {
      for (let y = 0; y < side; y += 1) {
        /* eslint-disable no-await-in-loop */
        const tile = await reader.getZxy(z, x, y);
        /* eslint-enable no-await-in-loop */
        if (!tile) continue;
        tiles += 1;
        const decoded = new VectorTile(new PbfReader(new Uint8Array(tile.data)));
        for (const name of Object.keys(decoded.layers)) {
          const layer = decoded.layers[name];
          for (let i = 0; i < layer.length; i += 1) {
            const properties = layer.feature(i).properties;
            for (const [key, value] of Object.entries(properties)) {
              // "name", "name:en", "name:de", … — the only properties the
              // style ever sets as text.
              if (!key.startsWith("name") || typeof value !== "string") continue;
              for (const character of value) {
                codepoints.add(character.codePointAt(0));
              }
            }
          }
        }
      }
    }
  }

  const ranges = new Set(
    [...codepoints].map((point) => Math.floor(point / RANGE_SIZE))
  );
  return {
    ranges: [...ranges].sort((a, b) => a - b),
    codepoints: codepoints.size,
    tiles,
  };
}

/**
 * Fetch one upstream asset into the vendored tree.
 * @param {string} relative - Path below the assets root, e.g. "sprites/v4/dark.png"
 * @param {{check: boolean, force: boolean}} mode - What the caller asked for
 * @returns {Promise<"present"|"written"|"missing">} What happened to the file
 */
async function vendorOne(relative, mode) {
  const destination = join(OUT, relative);
  if (!mode.force) {
    const present = await stat(destination).then(
      () => true,
      () => false
    );
    if (present) return "present";
  }
  if (mode.check) return "missing";

  const response = await fetch(`${UPSTREAM}/${encodeURI(relative)}`);
  if (!response.ok) {
    throw new Error(`${response.status} for ${relative}`);
  }
  await mkdir(dirname(destination), { recursive: true });
  await writeFile(destination, Buffer.from(await response.arrayBuffer()));
  return "written";
}

const mode = {
  check: process.argv.includes("--check"),
  force: process.argv.includes("--force"),
};

const stacks = fontStacksInStyle();
const { ranges, codepoints, tiles } = await rangesTheBasemapLabels();
console.log(
  `${tiles} tiles label ${codepoints} codepoints in ${ranges.length} ranges; ` +
    `${stacks.length} font stacks: ${stacks.join(", ")}`
);

const wanted = [
  ...SPRITE_FILES.map((file) => `sprites/v4/${file}`),
  ...stacks.flatMap((stack) =>
    ranges.map(
      (range) =>
        `fonts/${stack}/${range * RANGE_SIZE}-${range * RANGE_SIZE + RANGE_SIZE - 1}.pbf`
    )
  ),
];

const tally = { present: 0, written: 0, missing: 0 };
const missing = [];
// Sequential on purpose: this runs rarely, and a burst of a few hundred
// requests at a public CDN is not a good way to be a guest.
for (const relative of wanted) {
  /* eslint-disable no-await-in-loop */
  const outcome = await vendorOne(relative, mode);
  /* eslint-enable no-await-in-loop */
  tally[outcome] += 1;
  if (outcome === "missing") missing.push(relative);
}

console.log(
  `${wanted.length} assets: ${tally.present} already vendored, ` +
    `${tally.written} downloaded, ${tally.missing} missing.`
);

if (mode.check && tally.missing > 0) {
  for (const relative of missing.slice(0, 10)) console.log(`  missing ${relative}`);
  if (missing.length > 10) console.log(`  … and ${missing.length - 10} more`);
  console.log("Run: node scripts/vendor_basemap_assets.mjs");
  process.exit(1);
}
