# Claude Code Context: Life Data Stories

## Project Overview

A biographical visualization application that presents famous figures' life stories as full-screen, scroll-snapped slides with interactive timelines, maps, and social networks. Built with Svelte + Vite, designed mobile-first.

**Tech Stack**: Svelte 4, Vite 5, MapLibre GL, Protomaps, svelte-spa-router

## Core Concepts

### Person Data Model

Each person has a unique `id` (snake_case, e.g., `alan_turing`) and exists in three registries:

1. **`data/persons.json`** - Master registry with metadata:

   ```json
   {
     "id": "alan_turing",
     "name": "Alan_Turing",
     "summary": "...",
     "portrait": { "image": "url", "source": "url" },
     "primaryRoles": ["Mathematician", "Computer Scientist"],
     "birthDate": "1912-06-23",
     "deathDate": "1954-06-07",
     "created": "ISO8601",
     "lastUpdated": "ISO8601"
   }
   ```

2. **`data/person_styles.json`** - Visual styling per person:

   ```json
   {
     "alan_turing": {
       "primary": "#5ED0FF",
       "secondary": "#9A7BFF",
       "background": "#040A18",
       "background_pattern_svg": "<svg>...</svg>",
       "heading_font": "Space Grotesk",
       "body_font": "IBM Plex Sans"
     }
   }
   ```

3. **`data/people/{person_id}/`** - Person-specific data folder:
   - `life_events.json` - Chronological life events with locations, images, categories
   - `ego_network.json` - Social network connections with relationship metadata
   - `_cache/` - Wikipedia cache (articles, images, related content)

### Life Events Schema

Events are the core narrative units displayed as slides:

```json
{
  "person_id": "alan_turing",
  "events": [
    {
      "date": "1936",
      "title": "Publishes 'On Computable Numbers'",
      "description": "Long-form markdown description...",
      "location": {
        "name": "Cambridge, England",
        "latitude": 52.2053,
        "longitude": 0.1218
      },
      "categories": ["Academic Achievement"],
      "images": [
        {
          "url": "https://...",
          "caption": "...",
          "source": "https://commons.wikimedia.org/..."
        }
      ]
    }
  ]
}
```

**Important**: Events may not have locations (non-geographic events) or images.

### Ego Network Schema

Social connections with rich relationship metadata:

```json
{
  "ego": {
    "name": "Alan Turing",
    "birth_year": 1912,
    "death_year": 1954,
    "primary_roles": ["mathematician", "computer scientist"],
    "summary": "...",
    "wikipedia": "https://en.wikipedia.org/wiki/Alan_Turing"
  },
  "connections": [
    {
      "person_name": "Max Newman",
      "relationship_type": "professional/mentor",
      "relationship_description": "PhD supervisor and collaborator",
      "start_year": 1935,
      "end_year": 1954,
      "strength": "strong",
      "interaction_frequency": "regular",
      "influence_direction": "bidirectional",
      "shared_activities": ["mathematics", "computer design"],
      "sources": ["https://..."],
      "notes": "..."
    }
  ]
}
```

**Relationship categories**:

- `family/{relation}` (e.g., `family/father`, `family/mother`)
- `professional/{type}` (e.g., `professional/mentor`, `professional/colleague`)
- `friendship/{type}` (e.g., `friendship/close-friend`)
- `intellectual/{type}` (e.g., `intellectual/influence`, `intellectual/correspondent`)
- `romantic/{type}` (e.g., `romantic/fiancé`)
- `adversarial/{type}` (e.g., `adversarial/legal-opponent`)

## Project Structure

```
life-ds/
├── src/
│   ├── App.svelte           # Main app with routing & lazy loading
│   ├── main.js              # Entry point
│   └── components/
│       ├── Landing.svelte    # Person grid landing page
│       ├── StoryView.svelte  # Main story viewer (timeline/map)
│       ├── Timeline.svelte   # Event timeline component
│       ├── NetworkModal.svelte # Social network visualization
│       ├── PersonChip.svelte # Person card component
│       └── ImageViewer.svelte # Lightbox for event images
├── data/
│   ├── persons.json         # Master person registry
│   ├── person_styles.json   # Visual styles registry
│   └── people/
│       └── {person_id}/
│           ├── life_events.json
│           ├── ego_network.json
│           └── _cache/       # Wikipedia materials
├── scripts/                 # Python data generators
│   ├── generate_person.py           # Full person workflow
│   ├── generate_person_dataset.py   # Life events only
│   ├── generate_person_style.py     # Visual style only
│   ├── generate_person_network.py   # Ego network only
│   ├── cache_wikipedia_materials.py # Cache Wikipedia data
│   ├── remove_person.py             # Delete person
│   └── config.py                    # Shared config
└── public/                  # Static assets
```

## Routing

Uses `svelte-spa-router` with URL-based navigation:

- `/` - Landing page (person grid)
- `/story/{person_id}` - Person's story (starts at event 0)
- `/story/{person_id}/{event_index}` - Specific event slide

**Routing behavior**: Slide changes use `history.replaceState` (no history spam), but navigating between people uses `push` (back button works as expected).

## Styling System

### CSS Custom Properties

Person-specific styles are injected as CSS variables:

```css
--primary-rgb: 94, 208, 255
--secondary-rgb: 154, 123, 255
--background-rgb: 4, 10, 24
--heading-font: 'Space Grotesk', sans-serif
--body-font: 'IBM Plex Sans', sans-serif
```

### Background Patterns

Each person has a custom SVG pattern (stored inline in `person_styles.json`). These are converted to data URLs and applied as CSS background images.

### Font Loading

Fonts are loaded dynamically from Google Fonts when a person's story is viewed. The app normalizes font names (strips weights, handles special cases).

## Data Generation

### Python Scripts (require `OPENAI_API_KEY`)

**Add a new person**:

```bash
python scripts/generate_person.py "Albert Einstein"
```

This runs all three generators:

1. `generate_person_dataset.py` - Life events via GPT-4o-mini
2. `generate_person_style.py` - Visual design via GPT-4o
3. `generate_person_network.py` - Ego network via GPT-4o-mini

**Individual generators**:

```bash
python scripts/generate_person_dataset.py "Ada Lovelace"
python scripts/generate_person_style.py "Ada Lovelace"
python scripts/generate_person_network.py "Ada Lovelace"
```

**Remove a person**:

```bash
python scripts/remove_person.py "Ada Lovelace"
```

### Wikipedia Caching

The scripts automatically cache Wikipedia materials in `data/people/{person_id}/_cache/`:

- Main Wikipedia article (HTML, markdown)
- Related articles
- Image metadata

This reduces API calls and provides offline access for analysis.

## Map Integration

Uses Protomaps PMTiles for vector basemaps (MapLibre GL):

- **Primary source**: `https://demo-bucket.protomaps.com/v4.pmtiles`
- **Fallback**: `https://protomaps.github.io/tiles/v3/20240820.pmtiles`

Override via `.env`:

```env
VITE_PROTOMAPS_PM_TILES_URL=https://build.protomaps.com/20251114.pmtiles?download=1
VITE_PROTOMAPS_PM_TILES_FALLBACK_URL=https://...
```

**Important**: Maps only render when events have valid `location` objects. The UI gracefully handles missing location data.

## Development Workflow

### Common Commands

```bash
npm install          # Install dependencies
npm run dev          # Start dev server (localhost:5173)
npm run build        # Production build to dist/
npm run preview      # Preview production build
```

### Adding a New Person

1. Run `python scripts/generate_person.py "Person Name"`
2. Review generated files in `data/people/person_id/`
3. Check `data/persons.json` and `data/person_styles.json` were updated
4. Test in browser at `/story/person_id`
5. Iterate on styles or data as needed

### Modifying Person Data

**Life events**: Edit `data/people/{person_id}/life_events.json`

- Date format: `YYYY`, `YYYY-MM`, or `YYYY-MM-DD`
- Categories are free-form strings
- Images are optional arrays

**Ego network**: Edit `data/people/{person_id}/ego_network.json`

- Follow relationship type conventions (see schema above)
- Strength: `weak`, `moderate`, `strong`
- Interaction frequency: `rare`, `occasional`, `regular`, `frequent`
- Influence direction: `alter_to_ego`, `ego_to_alter`, `bidirectional`

**Visual style**: Edit `data/person_styles.json`

- Colors must be hex format (`#RRGGBB`)
- Background pattern SVG must be valid, self-contained
- Fonts must be available on Google Fonts

## Important Implementation Details

### Lazy Loading

`App.svelte` uses Vite's `import.meta.glob` with dynamic imports:

```javascript
const datasetModules = import.meta.glob("../data/people/*/life_events.json", {
  import: "default",
});
```

Events and networks are only loaded when a person's story is viewed.

### Style Normalization

`App.svelte` includes extensive validation:

- Hex colors → RGB values (for CSS custom properties with alpha)
- SVG strings → data URLs
- Font names → Google Fonts API format
- Missing/invalid styles fall back to defaults

### Event Images

Images appear as thumbnails (top-right of slide). Click to open `ImageViewer.svelte` lightbox with:

- Full-size image
- Caption
- Source link (Wikimedia Commons)

### Timeline Behavior

`Timeline.svelte` features:

- Horizontal scrollable timeline
- Auto-scroll to current event
- Click to jump to specific event
- Visual indicators for event categories
- Year markers (not all events have exact dates)

### Network Visualization

`NetworkModal.svelte` uses a force-directed layout:

- Ego (central person) at the center
- Connection nodes arranged by relationship strength
- Lines styled by relationship type
- Tooltips show relationship details

## Code Conventions

### File Naming

- Components: PascalCase (e.g., `StoryView.svelte`)
- Data files: snake_case (e.g., `life_events.json`)
- Person IDs: snake_case (e.g., `alan_turing`)

### Svelte Patterns

- Prefer reactive declarations (`$:`) over manual updates
- Keep component files focused (< 500 lines)
- Extract complex logic to functions outside component script
- Use stores sparingly (most state is local)

### Python Scripts

- All scripts use OpenAI structured outputs (Pydantic models)
- Model: `gpt-4o-mini` (datasets, networks), `gpt-4o` (styles)
- Wikipedia API via `requests` library
- Shared utilities in `config.py`

## Common Tasks for AI

### Adding/Editing Events

1. Read `data/people/{person_id}/life_events.json`
2. Validate event structure (date, title, description required)
3. If adding locations, verify lat/long coordinates
4. If adding images, ensure URLs are HTTPS and include captions
5. Maintain chronological order by date

### Debugging Styles

1. Check `data/person_styles.json` for the person ID
2. Verify hex color format (`#RRGGBB`)
3. Test SVG pattern in browser (data URL conversion)
4. Confirm fonts exist on Google Fonts
5. Check browser console for CSS custom property errors

### Fixing Routing Issues

1. Verify person ID matches across all registries
2. Check file paths in `import.meta.glob` patterns
3. Test URL patterns in svelte-spa-router routes
4. Confirm person exists in `data/persons.json`

### Network Data Issues

1. Validate relationship types follow category conventions
2. Check year ranges (start_year ≤ end_year)
3. Verify required fields: `person_name`, `relationship_type`, `relationship_description`
4. Ensure connection references are meaningful (not circular)

## Performance Considerations

- Lazy loading keeps initial bundle small (~150KB)
- PMTiles uses HTTP range requests (efficient tile loading)
- CSS custom properties avoid style duplication
- SVG patterns are inline (no external requests)
- Images are lazy-loaded by browser

## Browser Compatibility

- Modern browsers only (ES2020+)
- CSS Grid, Custom Properties, Intersection Observer required
- MapLibre GL requires WebGL support
- Mobile Safari tested (iOS 15+)

## Environment Variables

All variables are prefixed with `VITE_` (exposed to client):

- `VITE_PROTOMAPS_PM_TILES_URL` - Primary PMTiles source
- `VITE_PROTOMAPS_PM_TILES_FALLBACK_URL` - Fallback PMTiles source

Python scripts use:

- `OPENAI_API_KEY` - OpenAI API key (required)

## Useful Debugging Tips

### Data Issues

- Check browser console for JSON parse errors
- Validate JSON files with `python -m json.tool file.json`
- Confirm person IDs match exactly across all files

### Style Issues

- Inspect CSS custom properties in browser DevTools
- Check computed styles for `--primary-rgb`, `--secondary-rgb`, etc.
- Verify font loading in Network tab

### Map Issues

- Check console for PMTiles HTTP errors
- Verify location coordinates (lat: -90 to 90, lng: -180 to 180)
- Test PMTiles URL in browser (should return binary data)

### Routing Issues

- Check URL in browser matches expected pattern
- Verify svelte-spa-router routes in `App.svelte`
- Test with `console.log($location)` in component

## Key Files for Context

When working on specific features, read these files first:

**Routing**: `src/App.svelte` (lines 1-150)
**Event display**: `src/components/StoryView.svelte`
**Timeline**: `src/components/Timeline.svelte`
**Network viz**: `src/components/NetworkModal.svelte`
**Person data**: `data/persons.json`, `data/people/{person_id}/`
**Styles**: `data/person_styles.json`
