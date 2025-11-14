# Life Data Stories Viewer

A mobile-first Svelte + Vite experience that presents biographical life events as full-height, scroll-snapped slides with URL-based routing support.

## Getting Started

```powershell
npm install
npm run dev -- --open
```

- `npm run build` generates a production bundle in `dist/`.
- `npm run preview` serves the production build locally.

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
python scripts/generate_person_dataset.py "Ada Lovelace"
python scripts/generate_person_style.py "Ada Lovelace"
```

The dataset generator uses `gpt-4o-mini` by default. To use a different model:

```powershell
python scripts/generate_person_dataset.py "Ada Lovelace" --model gpt-4o-2024-08-06
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
