# Life Data Stories Viewer

A mobile-first Svelte + Vite experience that presents biographical life events as full-height, scroll-snapped slides with URL-based routing support.

## Getting Started

```powershell
npm install
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

The site is hosted on **GitHub Pages** as a project page under `https://<owner>.github.io/life-ds/` and is published **on demand only** — pushing or merging to `main` does **not** publish the site.

"On demand only" is enforced by the workflow itself: `.github/workflows/deploy-pages.yml` has a single `workflow_dispatch` trigger and no `push` trigger, so nothing publishes until a maintainer starts it.

### Publishing a new version

Open the repository's **Actions** tab, select **Deploy to GitHub Pages**, and run the workflow on `main`. It installs dependencies, runs `npm run build`, and uploads `dist/` to Pages.

One-time repository setup: **Settings → Pages → Build and deployment → Source** must be set to **GitHub Actions**.

Notes:

- The build produces a `404.html` copy of `index.html` (see `githubPages404Plugin` in `vite.config.js`). Pages has no rewrite rules; shared links are hash-based and never hit the server, but this keeps path-style entry URLs such as `/life-ds/en` working.
- The technical report is published with the site: the build copies `docs/report/index.html` to `dist/report/index.html`, served at `https://<owner>.github.io/life-ds/report/` and linked from the landing page and the "AI-generated" modal. The report is committed, so a deployment publishes whatever `docs/report/index.html` holds on `main` — regenerate it (`python scripts/generate_report.py`) before publishing if a generation script changed.
- The site is served from a subdirectory, so the build sets `base: "/life-ds/"`. Anything that turns a site-absolute path — a portrait path from the generated data, an asset in `public/` — into a URL must go through `assetUrl()` in `src/utils/assetUrl.js`. Adding a raw `"/portraits/…"` string to markup works locally at the domain root and 404s on Pages.
- Building for a host that serves from the domain root (a custom domain, or a different static host) needs no code change: `VITE_BASE_PATH=/ npm run build`.
- Limits worth knowing: Pages caps a published site at 1 GB and a single file at 100 MB, with a soft bandwidth limit of 100 GB per month. `public/` is currently ~134 MB, most of it generated portraits.
- The basemap is served from this same origin and relies on HTTP range requests, which GitHub Pages has been reported to handle inconsistently for `.pmtiles` files. If the map fails to load with a byte-serving error, point `VITE_PROTOMAPS_PM_TILES_URL` at an external host (see "Basemap" below); the map degrades to a message rather than breaking the page.

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

Attribution for Protomaps and OpenStreetMap is included in the vector source definition and displayed according to the license terms.
