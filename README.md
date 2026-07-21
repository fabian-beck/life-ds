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

The Playwright smoke test covers the landing page, search, a representative
story overview, chapter and event navigation, and the network modal in desktop
and mobile Chromium profiles.

```powershell
# Required once per machine
npx playwright install chromium

npm run test:interface
npm run test:interface:report
```

The HTML report includes screenshots and viewport audits. Generated reports and
test artifacts are ignored by Git.

## Deployment

The site is hosted on **Netlify** (project `famous-marigold-49244d`, site id
`12d3d478-2a11-4020-b56c-4580fa57e108`) and is deployed **on demand only** —
pushing/merging to `main` does **not** publish the site.

> Two things enforce "on demand only":
>
> 1. `netlify.toml` sets `ignore = "exit 0"`, so Netlify skips the build for any
>    git-triggered event.
> 2. Automatic builds are additionally turned off in the Netlify dashboard
>    (Site configuration → Build & deploy → Continuous deployment → **Stop
>    builds**), so a push doesn't even spin up a build container.
>
> To restore automatic deploys, re-enable builds in the dashboard and delete the
> `ignore` line in `netlify.toml`.

### Publishing a new version

Deploy the **pre-built** `dist/` folder with the Netlify CLI (a direct file
upload — it does not use Netlify's build system):

```powershell
# once per machine: authenticate (opens a browser)
npx netlify-cli login

npm run build   # refresh dist/ from the current checkout
npx netlify-cli deploy --prod --dir=dist --site 12d3d478-2a11-4020-b56c-4580fa57e108
```

Notes:

- The CLI package is **`netlify-cli`** — do **not** run `npx netlify`, which
  pulls the unrelated `netlify` JS API-client package.
- `--prod` publishes to the live site; without it you get a draft preview URL
  and production stays unchanged.
- Prefer this `--dir=dist` upload over Netlify's "build from git" paths: with
  builds stopped, the dashboard "Trigger deploy" and build hooks are disabled,
  and the Netlify MCP `deploy-site` (zip-and-build) path returns `400` for this
  project.
- To install the CLI globally instead: `npm install -g netlify-cli`, then use
  `netlify deploy --prod --dir=dist --site …` directly.

## Routing

The application supports URL-based routing, allowing you to:

- **Navigate with browser back/forward buttons**: The browser history is maintained, so you can use the back and forward buttons to navigate between views.
- **Share specific stories via URL**: Each person's story has a unique URL that can be shared directly:
  - Landing page: `http://localhost:5173/`
  - Person story (overview): `http://localhost:5173/story/ada_lovelace`
  - Specific event slide: `http://localhost:5173/story/ada_lovelace/3` (shows slide 3)

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

The story view uses a Protomaps vector basemap served directly from a PMTiles archive. By default it points at the public demo bucket for the v4 basemap:

```
https://demo-bucket.protomaps.com/v4.pmtiles
```

If that source ever fails or you prefer a different build, you can override both the primary and fallback URLs via Vite environment variables. The built-in fallback (used when the primary 404s) remains the archived public dataset:

```
https://protomaps.github.io/tiles/v3/20240820.pmtiles
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
