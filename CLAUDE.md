# Claude Code Context: Life Data Stories

> **Important**: Update this file whenever there are major changes to project structure, features, data schemas, or development workflow. This ensures AI assistants have accurate context.

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
   - `life_events.json` - Chronological life events with locations, images, categories, and optional chapter groupings
   - `ego_network.json` - Social network connections with relationship metadata
   - `_cache/` - Wikipedia cache (articles, images, related content)

### Life Events Schema

Events are the core narrative units displayed as slides. Events can optionally be grouped into chapters representing distinct life phases:

```json
{
  "person_id": "alan_turing",
  "chapters": [
    {
      "id": "early_years",
      "headline": "Early Years and Education",
      "description": "Turing's formative years and academic development.",
      "date_start": "1912",
      "date_start_precision": "year",
      "date_end": "1938",
      "date_end_precision": "year",
      "age_start": 0,
      "age_end": 26
    }
  ],
  "events": [
    {
      "date": "1936",
      "title": "Publishes 'On Computable Numbers'",
      "description": "Long-form markdown description...",
      "chapter": "early_years",
      "locations": ["Cambridge, England"],
      "location_modern": "Cambridge, United Kingdom",
      "involved_people": ["Max Newman", "Alonzo Church"],
      "sources": ["https://en.wikipedia.org/wiki/..."],
      "event_type_icon": "mdi-file-document",
      "images": [
        {
          "url": "https://...",
          "caption": "...",
          "source": "https://commons.wikimedia.org/..."
        }
      ],
      "location_coordinates": [
        {
          "label": "Cambridge, England, United Kingdom",
          "name": "Cambridge, England",
          "primary": true,
          "centroid": [0.1218, 52.2053],
          "source": "nominatim"
        }
      ]
    }
  ]
}
```

**New Fields (Two-Phase System)**:
- `location_modern`: Modern geographic name for geocoding (e.g., "Kaliningrad, Russia" for historic "Königsberg")
- `involved_people`: List of people directly involved in this event (excludes the main subject)
- `event_type_icon`: MDI icon identifier for visual categorization (e.g., "mdi-crown", "mdi-book", "mdi-school")

**Important**:
- Events may not have locations (non-geographic events) or images
- Chapters are optional but recommended for organizing life narratives
- Each event can reference a chapter via the `chapter` field (using the chapter's `id`)
- Chapters should be chronological and non-overlapping
- The new fields are optional and backward-compatible with existing data

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
│   ├── generate_person_events.py    # Life events (two-phase AI)
│   ├── generate_person_style.py     # Visual style only
│   ├── generate_person_network.py   # Ego network only
│   ├── icon_categories.py           # MDI icon mappings
│   ├── translate_person.py          # Translate single person
│   ├── translate_all_persons.py     # Batch translate all persons
│   ├── cache_wikipedia_materials.py # Cache Wikipedia data
│   ├── clear_caches.py              # Clear old cached data
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

1. `generate_person_events.py` - Life events via two-phase AI
2. `generate_person_style.py` - Visual design
3. `generate_person_network.py` - Ego network

**Individual generators**:

```bash
python scripts/generate_person_events.py "Ada Lovelace"
python scripts/generate_person_style.py "Ada Lovelace"
python scripts/generate_person_network.py "Ada Lovelace"
```

**Remove a person**:

```bash
python scripts/remove_person.py "Ada Lovelace"
```

### Two-Phase Event Generation

The life events generation uses a **two-phase AI approach** for improved accuracy and richer metadata:

**Phase 1: Event Skeleton Generation** (1 AI call)
- Identifies 12-16 significant life events (strictly enforced)
- Organizes events into 3-5 coherent chapters
- Creates crisp titles (2-6 words) and rich descriptions
- Uses ALL related articles for broad context

**Phase 2: Event Detail Research** (12-16 AI calls, one per event)
- Researches specific details for each event individually
- Filters 3-5 most relevant related articles per event
- Provides:
  - Historic location name (e.g., "Königsberg")
  - Modern location name (e.g., "Kaliningrad, Russia") for accurate geocoding
  - People directly involved in this event (excludes main subject)
  - Event-specific images and sources
  - Semantic icon from 100+ MDI categories (e.g., "mdi-crown", "mdi-book")

**Benefits**:
- Better accuracy through event-specific context
- Richer metadata (modern locations, involved people, icons)
- More reliable geocoding for historic places with changed names
- Resilient error handling (individual event failures don't abort entire generation)

**Performance**: ~60 seconds per person, ~$0.02 cost (cost may vary by model)

### Wikipedia Caching

The scripts automatically cache Wikipedia materials in `data/people/{person_id}/_cache/`:

- Main Wikipedia article (HTML, markdown)
- Related articles (up to 15 most relevant)
- Image metadata (Commons images)

This reduces API calls and provides offline access for analysis.

**Clear old caches**:

```bash
# Clear all caches older than 1 hour
python scripts/clear_caches.py --max-age 1h

# Clear all caches older than 2 days
python scripts/clear_caches.py --max-age 2d

# Clear specific person caches
python scripts/clear_caches.py alan_turing ada_lovelace

# Clear all caches (force)
python scripts/clear_caches.py --force

# Dry run to see what would be deleted
python scripts/clear_caches.py --max-age 1h --dry-run
```

Supported duration units: `s` (seconds), `m` (minutes), `h` (hours), `d` (days), `w` (weeks)

## Translation System

### Overview

Person data can be translated to different languages using AI-powered translation scripts. English ("en") is always the base language, and translations are stored in language-specific subdirectories.

### Directory Structure for Translations

**Before Translation**:
```
data/people/{person_id}/
├── life_events.json        # English (base)
├── ego_network.json        # English (base)
└── _cache/
```

**After Translation (e.g., German)**:
```
data/people/{person_id}/
├── life_events.json        # English (base)
├── ego_network.json        # English (base)
├── de/                     # German translations
│   ├── life_events.json
│   └── ego_network.json
└── _cache/
```

**Language-Specific Registries**:
- `data/persons.json` - English (base)
- `data/persons_de.json` - German translations
- `data/persons_fr.json` - French translations
- etc.

### Translation Scripts (require `OPENAI_API_KEY`)

**Translate a single person**:

```bash
python scripts/translate_person.py "Alan Turing" --target-lang de
python scripts/translate_person.py "ada_lovelace" --target-lang de
```

**Translate all persons**:

```bash
python scripts/translate_all_persons.py --target-lang de
python scripts/translate_all_persons.py --target-lang de --force  # Re-translate existing
```

**CLI Options**:

`translate_person.py`:
- `person_name_or_id` (positional): Person name or ID
- `--target-lang` (required): ISO language code (e.g., 'de', 'fr', 'es')
- `--force`: Overwrite existing translation
- `--model`: Override default OpenAI model
- `--verbose`: Enable detailed logging

`translate_all_persons.py`:
- `--target-lang` (required): ISO language code
- `--force`: Re-translate even if exists
- `--model`: Override default OpenAI model
- `--persons`: Comma-separated list to translate only specific persons
- `--skip-registry`: Skip updating persons_{lang}.json
- `--verbose`: Enable verbose output

### Translation Rules

**What gets translated**:
- Person summaries and roles
- Event titles and descriptions
- Chapter headlines and descriptions
- Image captions
- Relationship descriptions
- Social network notes and summaries

**What is preserved**:
- All dates (dates, timestamps)
- All coordinates (location_coordinates, centroid, bbox)
- All URLs (sources, wikipedia, images)
- All IDs (person_id, chapter IDs)
- Relationship types (e.g., `professional/mentor`)
- Strength values (`weak`, `moderate`, `strong`)
- Technical classifications

**Proper name handling**:
- Names are kept in original form by default
- Only translate if very well-known with standard localized version
- Examples: Henry II → Heinrich II (German emperor), Queen Elizabeth → Königin Elisabeth (in German)
- Keep modern English names as-is (e.g., Alan Turing, Ada Lovelace, Max Newman)
- **Consistency**: The same person's name is translated the same way throughout all documents

**Place name handling**:
- Use native/localized versions when they exist (e.g., "London" → "Londres" in French, "Munich" → "München" in German)
- Translate geographic descriptors (e.g., "England" → "Inglaterra" in Spanish)
- Keep specific street names mostly intact but translate generic terms (e.g., "Street" → "Straße")

### Supported Languages

Common language codes:
- `de` - German
- `fr` - French
- `es` - Spanish
- `it` - Italian
- `pt` - Portuguese
- `nl` - Dutch
- `pl` - Polish
- `ru` - Russian
- `ja` - Japanese
- `zh` - Chinese
- `ko` - Korean

### Translation Workflow

1. Scripts use OpenAI API with structured outputs (Pydantic models)
2. Each file type (life_events.json, ego_network.json, registry entry) uses specialized translation prompts
3. Translated files maintain exact JSON structure
4. Non-text fields are preserved exactly
5. Language-specific registry (`persons_{lang}.json`) is created/updated automatically

### Language Switching in the Application

**Status**: ✅ Implemented

The application now supports runtime language switching with a two-layer translation system:

**Layer 1: UI Labels** (Static translations in `src/locales/`)
- Button labels, aria-labels, messages, placeholders
- Stored in JSON files: `en.json`, `de.json`, etc.
- Managed via Svelte stores in `src/stores/language.js`

**Layer 2: Person Data** (Dynamic translations from data files)
- Life events, ego networks, person summaries
- Stored in language-specific subdirectories (e.g., `data/people/{person_id}/de/`)
- Loaded dynamically based on selected language

#### Language Store

Location: `src/stores/language.js`

Key exports:
- `currentLanguage` (writable): Current language code ('en', 'de', etc.)
- `translations` (writable): Currently loaded translation strings
- `_` (derived): Reactive translation function with interpolation
- `loadTranslations(lang)`: Load translation JSON file for a language

Features:
- Auto-detects browser language on first visit
- Persists preference in `localStorage`
- Updates `<html lang="...">` attribute automatically
- Supports parameter interpolation (e.g., `$_('key', { count: 5 })`)

#### Implementation Details

**App.svelte** has been updated with:

1. **Language switcher UI**: Fixed-position dropdown in top-right corner
2. **Dynamic glob patterns** for language subdirectories:
   ```javascript
   const datasetModules = import.meta.glob([
     "../data/people/*/life_events.json",
     "../data/people/*/de/life_events.json",
     "../data/people/*/fr/life_events.json",
   ], { import: "default" });
   ```

3. **Language-aware data loading**:
   ```javascript
   async function loadDataset(personId, language = 'en') {
     let path = language === 'en'
       ? `../data/people/${personId}/life_events.json`
       : `../data/people/${personId}/${language}/life_events.json`;
     let loader = datasetModules[path];
     // Fallback to English if translation doesn't exist
     if (!loader && language !== 'en') {
       path = `../data/people/${personId}/life_events.json`;
       loader = datasetModules[path];
     }
     return await loader();
   }
   ```

4. **Dynamic registry loading**: Loads `data/persons_{lang}.json` based on selected language

**All Components** have been updated with translation calls:
- [Landing.svelte](src/components/Landing.svelte): Search, filters, AI disclaimer modal
- [StoryView.svelte](src/components/StoryView.svelte): Loading states, slide content, error messages
- [Timeline.svelte](src/components/Timeline.svelte): Navigation, scrubber, expand/collapse
- [NetworkModal.svelte](src/components/NetworkModal.svelte): Title, close button, group counts
- [PersonChip.svelte](src/components/PersonChip.svelte): Tooltips, year ranges, relationship metadata
- [ImageViewer.svelte](src/components/ImageViewer.svelte): Controls, help text, captions

#### Adding a New Language

1. **Create UI translation file**:
   - Add `src/locales/{lang}.json` with all translation keys
   - Use `src/locales/en.json` as template

2. **Update language selector**:
   - Add option to dropdown in [App.svelte:381-384](src/App.svelte#L381-L384)

3. **Update glob patterns** (if needed):
   - Add `../data/people/*/{lang}/life_events.json` to glob in [App.svelte:50-56](src/App.svelte#L50-L56)

4. **Translate person data**:
   - Run `python scripts/translate_all_persons.py --target-lang {lang}`

#### Translation File Format

Example from `src/locales/de.json`:
```json
{
  "app.title": "Life Data Stories",
  "app.tagline": "Erkunde bemerkenswerte Leben durch Datengeschichten",
  "story.loading_life": "Lade Lebensgeschichte...",
  "story.age": "Alter {age}",
  "story.source_one": "{count} Quelle",
  "story.source_other": "{count} Quellen"
}
```

**Important for German**: Use "Du" form (informal) instead of "Sie" form (formal) for all user-facing text

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

**Note**: The dev server is always running in this environment. No need to start it manually.

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

- Drag scrubber: Click and drag anywhere on timeline track to navigate through slides in real-time
- Snap-to-slide: Releases snap to nearest slide for precise navigation
- Click dots to jump to specific events
- Visual indicators for event categories (icons determined by event text)
- Year markers when expanded (not all events have exact dates)
- Expandable mode: Toggle to see full vertical timeline with labels

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
- Model is configurable via `OPENAI_MODEL` environment variable (see `config.py`)
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
