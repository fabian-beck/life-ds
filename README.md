# Life Data Stories Viewer

A mobile-first Svelte + Vite experience that presents biographical life events as full-height, scroll-snapped slides with URL-based routing support.

## Getting Started

```powershell
npm ci
npm run dev -- --open
```

- `npm run build` generates a production bundle in `dist/`.
- `npm run preview` serves the production build locally.

## Interface Tests

The Playwright smoke test covers the landing page, search, a representative story overview, chapter and event navigation, and the network modal in desktop and mobile Chromium profiles.

```powershell
# Required once per machine
npx playwright install chromium

npm run test:interface
npm run test:interface:report
```

The HTML report includes screenshots and viewport audits. Generated reports and test artifacts are ignored by Git.

## Deployment

The site is published by **GitHub Pages** at https://fabian-beck.github.io/life-ds/, and the `deploy` branch is the deployment. A push onto that branch runs `.github/workflows/deploy-pages.yml`, which builds the tree it carries and publishes it; nothing else publishes. `main` is integrated continuously and stays unpublished until someone advances `deploy`, which is what keeps releasing a deliberate act.

`.github/workflows/checks.yml` lints, builds, and tests every push except the one onto `deploy`, whose tree `main` has already been checked, so the deployment workflow publishes without repeating them.

### Publishing a new version

```powershell
git fetch origin
git push origin origin/main:deploy
```

That push is the entire release: the workflow starts on its own, and its run under **Actions → Deploy to GitHub Pages** is where it is followed. Publishing an earlier or a partial state is the same command with a different source — `git push origin <commit>:deploy`.

Check what `deploy` currently points at before pushing (`git log origin/deploy --oneline -1`). The branch is a pointer at whatever was published last rather than a line of development, so a push that is not a fast-forward is normal and needs `--force`; nothing is lost, because every commit it ever pointed at is on `main`.

### The build

A plain `npm run build`, and the workflow reads it from the branch it is building — a change to the workflow publishes only once it reaches `deploy`. Nothing has to be configured for the address: `vite.config.js` defaults `base` to `/life-ds/`, which is the path Pages serves a repository of this name from, and derives the link-preview address from it. `VITE_BASE_PATH` and `VITE_SITE_URL` are for a deployment that lives somewhere else — a custom domain, or a host that serves from a domain root.

Notes:

- The build produces a `404.html` copy of `index.html` (see `notFoundFallbackPlugin` in `vite.config.js`). Shared deep links are hash-based and never reach the server, but a static host has no rewrite rules, and serving the application as the 404 document keeps path-style entry URLs such as `/en` working.
- The technical report is published with the site: the build copies `docs/report/index.html` to `dist/report/index.html`, served at `/report/` and linked from the landing page and the "AI-generated" modal. The report is committed, so a deployment publishes whatever `docs/report/index.html` holds on the published commit — regenerate it (`python scripts/generate_report.py`) before publishing if a generation script changed.
- The site is served from a subdirectory (`base: "/life-ds/"`), on Pages and locally alike, so anything that turns a site-absolute path — a portrait path from the generated data, an asset in `public/` — into a URL must go through `assetUrl()` in `src/utils/assetUrl.js`. A raw `"/portraits/…"` string in markup 404s everywhere except on a deployment that serves from a domain root.
- The published site is currently ~177 MB in ~1,170 files, most of it generated portraits, and all of it is served. Pages caps a site at 1 GB and a single file at 100 MB — the basemap, at 15 MB, is the largest — and applies a soft bandwidth limit of 100 GB per month.
- The basemap is served from the site's own origin and relies on HTTP range requests, which Pages has been reported to answer inconsistently for `.pmtiles` archives. If the map fails to load with a byte-serving error, point `VITE_PROTOMAPS_PM_TILES_URL` at an external host (see "Basemap" below); the map degrades to a message rather than breaking the page.

### The user-evaluation deployment

A second deployment of the same site, built from the `deploy-evaluation` branch in Vite's `evaluation` mode, asks each reader for a participant ID, logs their interactions to Netlify Blobs through a Netlify Function, and serves an analysis page at `/analysis/` with a report per participant and one across all of them. Publishing it is `git push origin origin/main:deploy-evaluation`, once the branch is enabled under the site's branch deploys; nothing of it is in the ordinary `deploy` build. See [User evaluation](docs/agent/user-evaluation.md).

This deployment stays on **Netlify** and cannot move to Pages: its log endpoint is a function and its store is a Netlify service, neither of which a static host provides. `netlify.toml` is therefore still part of the repository, and the Netlify site still exists — for the evaluation branch alone. Its production branch is what needs to be disconnected, under **Site configuration → Build & deploy → Continuous deployment**: while it still watches `deploy`, one push publishes the site twice, to Pages at `/life-ds/` and to Netlify at its own root.

## Routing

The application supports URL-based routing, allowing you to:

- **Navigate with browser back/forward buttons**: The browser history is maintained, so you can use the back and forward buttons to navigate between views.
- **Share specific stories via URL**: Each person's story has a unique URL that can be shared directly. Routes live in the URL hash, so they resolve entirely in the browser and need no server-side rewrite:
  - Landing page: `http://localhost:5173/life-ds/#/en`
  - Person story (overview): `http://localhost:5173/life-ds/#/en/story/ada_lovelace`
  - Specific event slide: `http://localhost:5173/life-ds/#/en/story/ada_lovelace?slide=3`

The routing is implemented using `svelte-spa-router` and works seamlessly with the application's existing navigation. Slide numbers are updated in the URL as you navigate through events, but use `history.replaceState` to avoid cluttering browser history, so the back button returns to the previous person/landing page rather than the previous slide.

## Generating Data Assets

Both dataset and styling generators rely on the OpenAI API. Set `OPENAI_API_KEY` before running the scripts.

### Python Dependencies

Install the required Python packages:

```powershell
pip install -r requirements.txt
```

The scripts require:

- `openai` - OpenAI API client with structured outputs support
- `requests` - HTTP library for Wikipedia API
- `pydantic` - Data validation for structured outputs

### Running the Generators

```powershell
python scripts/generate_person_events.py "Ada Lovelace"
python scripts/generate_person_style.py "Ada Lovelace"
```

The event generator uses a **two-phase AI approach** for improved accuracy and richer metadata. The model is configurable via the `OPENAI_MODEL` environment variable or the `--model` flag:

```powershell
python scripts/generate_person_events.py "Ada Lovelace" --model <model_name>
```

Phases whose output is validated, rewritten, or replaceable afterwards run on a smaller model instead, set by `OPENAI_BULK_MODEL`.

By default the scripts write to `data/people/` and `data/person_styles.json`, updating the shared registry files as needed.

### Event Images

The dataset generator now automatically includes relevant images for events when meaningful images are available from Wikipedia. Each image includes metadata such as a caption and source link. Images are stored in an optional `images` array within each event:

```json
{
  "date": "1842",
  "title": "Translates Menabrea's paper on the Analytical Engine",
  "images": [
    {
      "url": "https://upload.wikimedia.org/wikipedia/commons/c/cf/Diagram_for_the_computation_of_Bernoulli_numbers.jpg",
      "caption": "Diagram of an algorithm for the Analytical Engine for computing Bernoulli numbers",
      "source": "https://commons.wikimedia.org/wiki/File:Diagram_for_the_computation_of_Bernoulli_numbers.jpg"
    }
  ]
}
```

The UI displays these images as small thumbnails in the top-right corner of each event slide. Click on any thumbnail to view the enlarged image with its caption and a direct link to the Wikimedia Commons source page.

## Basemap (Protomaps PMTiles)

The maps use a Protomaps vector basemap served directly from a PMTiles archive. By default this is the copy shipped with the site, a zoom 0–5 world extract of the Protomaps v4 basemap:

```
public/basemap.pmtiles   →   served as <base>/basemap.pmtiles
```

Both the primary and the fallback URL can be overridden via Vite environment variables — to follow a daily build, or to move the archive to a host with better range-request support than the site's own:

```
https://build.protomaps.com/<YYYYMMDD>.pmtiles?download=1
https://demo-bucket.protomaps.com/v4.pmtiles
```

Environment variables:

| Variable                               | Purpose                                                     |
| -------------------------------------- | ----------------------------------------------------------- |
| `VITE_PROTOMAPS_PM_TILES_URL`          | Primary PMTiles archive (daily build or custom hosted file) |
| `VITE_PROTOMAPS_PM_TILES_FALLBACK_URL` | Optional explicit fallback if the primary 404s              |

Create a `.env` file in the project root (or `.env.local`) to force a specific daily build and set a custom fallback:

```env
VITE_PROTOMAPS_PM_TILES_URL=https://build.protomaps.com/20251114.pmtiles?download=1
VITE_PROTOMAPS_PM_TILES_FALLBACK_URL=https://protomaps.github.io/tiles/v3/20240820.pmtiles
```

If neither resolves (network error or 404), the map quietly disables itself and shows a small message. This prevents runtime errors from the PMTiles protocol while attempting to read headers.

### Notes on Hosting Your Own

If you host a custom PMTiles file:

1. Serve it with HTTP range request support (`Accept-Ranges: bytes`).
2. Add `Access-Control-Allow-Origin: *` (or specific origin) so browsers can fetch segments cross-origin.
3. Prefer CDN or static object storage (S3, Cloudflare R2, etc.) for latency & caching.
4. Keep filenames stable; if you rotate archives, update the env var.

### Forcing a Specific Daily Build (Optional)

Daily builds live at `https://build.protomaps.com/<YYYYMMDD>.pmtiles?download=1`.

1. Visit the build site and copy the desired dated URL.
2. Set `VITE_PROTOMAPS_PM_TILES_URL` in `.env`.
3. (Optional) Point `VITE_PROTOMAPS_PM_TILES_FALLBACK_URL` at a second source (or leave the default archived dataset).
4. Restart the dev server (`npm run dev`). The component issues a `HEAD`; if reachable it uses your custom archive.

### Attribution

Attribution for Protomaps and OpenStreetMap is included in the vector source definition and displayed according to the license terms. The basemap archive and its vendored glyphs are third-party material; see [License](#license).

## License

The code is MIT-licensed (see `LICENSE`): the application, the generation and evaluation scripts, the build configuration, the tests, and the documentation.

The repository also carries material it did not author, and that material keeps the terms of its source rather than taking on the MIT license — the basemap extract is derived from OpenStreetMap under ODbL, the vendored glyphs are Noto Sans under the SIL Open Font License, and the generated stories under `data/` are derived from Wikipedia under CC BY-SA. `NOTICE` names each one, where it sits, and which terms apply, and is the file to read before reusing anything from here beyond the code.
