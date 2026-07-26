# Data Generation and Localization

> Detailed reference for coding agents. Keep the root `AGENTS.md` concise and update this document when the related project behavior changes.

## Data Generation

### Python Environment

The generation scripts run from a project-local virtual environment. The `openai`
dependency must be >= 2.0.0 — the pre-1.0 SDK exposes a different client and the
scripts will fail to import against it.

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt   # Windows
# source .venv/bin/activate && pip install -r requirements.txt  # macOS/Linux
```

Run scripts with the venv interpreter, e.g. `.venv/Scripts/python.exe scripts/generate_person.py "..."`.

**Model configuration** (see `scripts/config.py`):

- `OPENAI_MODEL` — text/reasoning model for all generation (default: `gpt-5.6-terra`)
- `OPENAI_REASONING_EFFORT` / `OPENAI_LOW_REASONING_EFFORT` — reasoning effort levels
- Portrait scripts take `--model` separately (default: `gpt-image-2`)

Image models that support the dual-image editing path are allowlisted in
`generate_person_portrait.py`; a model outside that list silently falls back to
text-only generation and will not preserve facial likeness.

### Python Scripts (require `OPENAI_API_KEY`)

**Add a new person**:

```bash
python scripts/generate_person.py "Albert Einstein"
```

This runs all three generators:

1. `generate_person_events.py` - Life events via two-phase AI
2. `generate_person_style.py` - Visual design
3. `generate_person_network.py` - Ego network

**Disambiguate with Wikipedia URL** (for ambiguous names):

When a person's name is ambiguous (e.g., "Henry II"), you can specify the exact Wikipedia article using the `--url` argument. The URL will be used to fetch the correct Wikipedia article, while the subject parameter determines the `person_id` (directory name):

```bash
python scripts/generate_person.py "henry_II" --url https://en.wikipedia.org/wiki/Henry_II,_Holy_Roman_Emperor
```

This creates a person with ID `henry_ii` (from the subject "henry_II") but fetches data from the specified Wikipedia article. The data will be stored in `data/people/henry_ii/`.

The `--url` argument works with all generation scripts:

```bash
python scripts/generate_person_events.py "henry_II" --url https://en.wikipedia.org/wiki/Henry_II,_Holy_Roman_Emperor
python scripts/generate_person_style.py "henry_II" --url https://en.wikipedia.org/wiki/Henry_II,_Holy_Roman_Emperor
python scripts/generate_person_network.py "henry_II" --url https://en.wikipedia.org/wiki/Henry_II,_Holy_Roman_Emperor
python scripts/cache_wikipedia_materials.py "henry_II" --url https://en.wikipedia.org/wiki/Henry_II,_Holy_Roman_Emperor
```

**Important**: When using `--url`, the subject parameter controls the person_id, not the URL. This allows you to use clean, simple IDs (like "henry_II") even when the Wikipedia article has a long, disambiguated title.

**Individual generators**:

```bash
python scripts/generate_person_events.py "Ada Lovelace"
python scripts/generate_person_style.py "Ada Lovelace"
python scripts/generate_person_network.py "Ada Lovelace"
```

**Review and improve person data**:

```bash
python scripts/review_person.py "Alan Turing"
python scripts/review_person.py "alan_turing" --aspect events
python scripts/review_person.py "ada_lovelace" --dry-run
```

This script acts as an AI-powered constructive critic to review and improve the quality of generated person data. It can review life events, ego network, and visual styles, proposing improvements for readability, accuracy, and storytelling quality.

**What it reviews**:
- **Life events**: Event descriptions, titles, chronological accuracy, historical context
- **Ego network**: Relationship descriptions, connection strength, interaction frequency
- **Visual styles**: Color harmony, font pairings, design coherence

**Features**:
- Confidence-based changes (only applies high-confidence improvements by default)
- Dry-run mode for previewing changes without applying them
- Aspect-specific review (events, network, style, or all)
- Uses Wikipedia cache for contextual understanding

**Options**:
- `--aspect {all,events,network,style}` - Which aspect to review (default: all)
- `--dry-run` - Show proposed changes without applying them
- `--skip-low-confidence` - Only apply high-confidence changes (default: True)
- `--model MODEL` - Override OpenAI model
- `--reasoning-effort {low,medium,high}` - Override reasoning effort levels
- `--verbose` - Enable detailed logging

**Remove a person**:

```bash
python scripts/remove_person.py "Ada Lovelace"
```

**Generate stylized portrait** (optional):

```bash
python scripts/generate_person_portrait.py "Alan Turing"
```

This uses OpenAI image generation to transform the existing Wikimedia Commons portrait into a stylized illustration with consistent artistic treatment. Requires a master style reference portrait at `public/master_style_portrait.png`.

**Features**:
- Uses master style image for consistent artistic treatment across all persons
- Preserves facial likeness from Wikimedia portraits
- Saves to `public/portraits/{person_id}.png`
- Automatically updates `data/persons.json` with generated portrait path
- Automatically syncs portrait data to `data/people/{person_id}/life_events.json` (main and all translations)
- Cost: varies by model and image size; check current OpenAI image pricing

**Prerequisites**:
1. Create master style reference portrait at `public/master_style_portrait.png` (1024x1024 PNG)
2. Ensure person has existing Wikimedia portrait (from `generate_person_events.py`)

**Options**:
- `--force`: Regenerate even if portrait already exists
- `--dry-run`: Test without API calls or file writes
- `--master-style PATH`: Use custom master style image
- `--model MODEL`: Specify OpenAI model (default: gpt-image-2)

**Master Style Portrait**:
The master style portrait defines the artistic style applied to all generated portraits. Create it once (manually or using AI tools), then all generated portraits will match its style through AI-powered style transfer.

**Portrait Data Syncing**:
The portrait generation script automatically ensures portrait data consistency across all files:
1. Updates `data/persons.json` with the generated portrait path and metadata
2. Syncs the same portrait data to `data/people/{person_id}/life_events.json`
3. Updates all language translations (e.g., `data/people/{person_id}/de/life_events.json`)

This ensures the generated portraits appear consistently on both the landing page (which reads from `persons.json`) and the story overview slide (which reads from `life_events.json`).

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

**Performance**: ~60 seconds per person. Cost varies by model — check current OpenAI pricing for the configured `OPENAI_MODEL`.

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

### Deutsche Biographie Integration

The generation pipeline automatically fetches supplementary biographical data from [Deutsche Biographie](https://www.deutsche-biographie.de/) (deutsche-biographie.de) via their open Solr API. This provides additional context for the AI generation, especially for German/European historical figures.

**How it works**:
1. After Wikipedia caching, searches Deutsche Biographie by person name (with birth/death year disambiguation)
2. Checks article licensing per record:
   - **CC0 metadata** (dates, places, professions, relationships): Always included
   - **ADB article text** (Allgemeine Deutsche Biographie, pre-1900): CC-BY-NC-SA — included as AI context
   - **NDB article text** (Neue Deutsche Biographie): CC-BY-NC-ND — **excluded** (no derivatives allowed)
3. Cached to `data/people/{person_id}/_cache/deutsche_biographie.json`
4. Formatted and included in Phase 1 and Phase 2 AI prompts

**CLI flag**: Use `--skip-db` to disable Deutsche Biographie fetching:
```bash
python scripts/generate_person.py "Albert Einstein" --skip-db
```

**Key files**:
- `scripts/utils/deutsche_biographie.py` — API client, caching, license checking, prompt formatting
- Integration in `scripts/generate_person_events.py` (Phase 1 & 2 prompts)
- Integration in `scripts/cache_wikipedia_materials.py` (caching step)

**Limitations**:
- Name matching works best for names that are similar in English and German
- For translated names (Henry → Heinrich, Charles → Karl), the search may not find the correct record
- Providing birth/death years improves disambiguation accuracy

## Translation System

### Overview

English ("en") is always the **reference version**. Translations are *derived* from the English data with an extract–translate–merge architecture (see `scripts/translate_person.py`):

1. **Extract**: only translatable text fields are pulled from the English document into a compact payload.
2. **Translate**: the payload (never the whole document) goes to the model via structured outputs, so dates, coordinates, URLs, IDs, icons, `event_index` references, and structure can never drift.
3. **Merge**: the translated payload is overlaid onto a deep copy of the English document. List lengths are validated, so a translated file is guaranteed to have the same events, chapters, images, and connections — in the same order — as the English source.

Every translated file carries a `translation` provenance block with a **fingerprint of the English source text** it was derived from. When the English text changes, the fingerprint no longer matches and the translation is reported (and re-translated) as **stale**. Person names are localized via a per-person **name glossary** applied identically across life events, ego network, and registry, because UI cross-references match on exact names. `relationship_type` values stay untouched — the UI localizes them from locale files.

### Directory Structure for Translations

**Person data (e.g., German)**:
```
data/people/{person_id}/
├── life_events.json        # English (reference)
├── ego_network.json        # English (reference)
├── de/                     # German, derived from English
│   ├── life_events.json
│   └── ego_network.json
└── _cache/
```

**Meta stories**:
- `data/meta_stories/{id}.json` - English detail (reference)
- `data/meta_stories/de/{id}.json` - German detail
- `data/meta_stories.json` / `data/meta_stories_de.json` - registries

**Language-Specific Registries**:
- `data/persons.json` - English (reference)
- `data/persons_de.json` - German (all persons, same ids/order/fields; entries carry a `translation` block)

### Translation Scripts (require `OPENAI_API_KEY`, except `--check`)

**Check parity (no API key needed)**:

```bash
python scripts/translate_all_persons.py --target-lang de --check
```

Prints per-person and per-meta-story status (✓ current, ↻ stale, ✗ missing) and exits non-zero if anything is stale or missing.

**Translate a single person**:

```bash
python scripts/translate_person.py "Alan Turing" --target-lang de
```

**Translate everything (persons + meta stories)**:

```bash
python scripts/translate_all_persons.py --target-lang de          # only missing/stale
python scripts/translate_all_persons.py --target-lang de --force  # re-translate all
```

**Translate meta stories only**:

```bash
python scripts/translate_meta_story.py computing_pioneers --target-lang de
python scripts/translate_meta_story.py --all --target-lang de
```

Meta story `event_title`s are copied verbatim from the person's translated life events (matched by `event_index`) whenever that translation exists, so meta story chapters and story slides always show identical titles.

**Migrate legacy translation files** (deterministic, no API):

```bash
python scripts/migrate_translations.py --lang de [--dry-run]
```

Rebases old-schema translated files onto the current English structure, carries over matched translated text, and flags them as stale for retranslation.

**CLI Options**:

`translate_person.py`:
- `person_name_or_id` (positional): Person name or ID
- `--target-lang` (required): ISO language code (e.g., 'de', 'fr', 'es')
- `--force`: Re-translate even if the translation is current
- `--model`: Override default OpenAI model
- `--verbose`: Enable detailed logging

`translate_all_persons.py`:
- `--target-lang` (required): ISO language code
- `--check`: Report status only (no API calls, no changes)
- `--force`: Re-translate even current translations
- `--model`: Override default OpenAI model
- `--persons`: Comma-separated list to translate only specific persons
- `--skip-meta`: Skip meta stories
- `--verbose`: Enable verbose output

### German Is Generated Alongside English

`generate_person.py` and `generate_meta_story.py` automatically translate to German as their final step (after review, so translations reflect the reviewed English text). Control this with `--translate-langs de,fr,...` or `--skip-translate`. Translation failures are non-fatal — the English reference stays complete and `--check` reports the gap. If you edit or re-review English data outside the pipeline, run `translate_all_persons.py --target-lang de` afterwards; fingerprint-based staleness detection ensures only affected documents are re-translated.

### Translation Rules

**What gets translated**:
- Person summaries and roles
- Event titles and descriptions
- Chapter headlines
- Image captions
- Relationship descriptions
- Social network notes and summaries

**What is preserved** (guaranteed by the merge — the model never sees these fields):
- All dates (dates, timestamps)
- All coordinates (locations, centroid, bbox)
- All URLs (sources, wikipedia, images, annotation wikipedia_urls)
- All IDs (person_id, chapter IDs, annotation term keys, event_index)
- `event_type_icon`, `event_class`, `involved_people` list structure
- Relationship types (e.g., `professional/mentor`) — entirely; the UI localizes them from locale files
- Strength values (`weak`, `moderate`, `strong`)
- Technical classifications

**Annotation markers**: descriptions may contain `[[term|display]]` markers. The term (before the `|`) is an ID and stays in English; only the display text and the annotation's `explanation` are translated.

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

1. A name glossary is built once per person (single AI call) and applied deterministically everywhere a name appears
2. Each document's translatable payload is translated with structured outputs (Pydantic models)
3. The payload is merged onto a deep copy of the English document; misaligned outputs (wrong list lengths) are rejected
4. A `translation` block (`source_lang`, `target_lang`, `source_fingerprint`, `translated_on`, `translator`) is stamped into the file
5. Language-specific registries (`persons_{lang}.json`, `meta_stories_{lang}.json`) are created/updated automatically, kept in English registry order

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

4. **Registry merging**: `data/persons_{lang}.json` entries are merged **per person over the English registry**, so the person list is identical in every language and untranslated people fall back to English text individually (never a shorter list).

5. **Language-aware meta stories**: the meta story registry (`meta_stories_{lang}.json`) is merged over the English one the same way; detail files load from `data/meta_stories/{lang}/{id}.json` with English fallback, and reload on language switch.

6. **Basemap labels**: the landing map renders place labels in the current UI language and swaps label layers in place on switch.

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
   - Add `../data/people/*/{lang}/life_events.json` (and the matching `ego_network.json` pattern) to the globs in App.svelte and LandingMap.svelte
   - Add `../data/meta_stories/{lang}/*.json` to the meta story glob in App.svelte

4. **Translate person data and meta stories**:
   - Run `python scripts/translate_all_persons.py --target-lang {lang}`
   - Verify with `python scripts/translate_all_persons.py --target-lang {lang} --check`

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
