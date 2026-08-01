# Project Structure and UI

> Detailed reference for coding agents. Keep the root `AGENTS.md` concise and update this document when the related project behavior changes.

## Project Structure

```
life-ds/
├── src/
│   ├── App.svelte           # Main app with routing & lazy loading
│   ├── main.js              # Entry point
│   ├── meta-frames.css      # Meta story frame vocabulary (global, by data-ms-frame)
│   └── components/
│       ├── Landing.svelte    # Person grid landing page
│       ├── StoryView.svelte  # Main story viewer (timeline/map)
│       ├── Timeline.svelte   # Event timeline component
│       ├── NetworkModal.svelte # Social network visualization
│       ├── MetaStoryNetwork.svelte # d3-force network for meta stories
│       ├── MetaStoryMap.svelte # Scrollytelling map for meta stories
│       ├── PersonChip.svelte # Inline person chip (slides, tooltips)
│       ├── PersonCard.svelte # Portrait card linking to a person's story
│       ├── MetaStoryOrnament.svelte # Meta story rule/divider/end mark (SVG)
│       └── ImageViewer.svelte # Lightbox for event images
│   └── utils/
│       ├── storyHelpers.js   # Dates, images, event/person helpers
│       ├── metaStoryStyles.js # Resolves a meta story's style to CSS variables
│       └── personNames.js    # Finds person names in prose (highlighting)
├── data/
│   ├── persons.json         # Master person registry
│   ├── person_styles.json   # Visual styles registry
│   ├── meta_story_styles.json # Per-meta-story colors, fonts, SVG marks
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
│   ├── generate_person_portrait.py  # Stylized portrait generation
│   ├── generate_all_portraits.py    # Batch portrait generation
│   ├── icon_categories.py           # MDI icon mappings + icon normalization
│   ├── fix_event_icons.py           # Repair invalid event_type_icon values
│   ├── translate_person.py          # Translation core + translate single person
│   ├── translate_all_persons.py     # Batch translate persons + meta stories, --check
│   ├── translate_meta_story.py      # Translate meta stories
│   ├── generate_meta_story.py       # Meta story workflow (1 plan, 2 collect, 3 curate, 3b fit chapters, 4 context, 5 network, 5b review, 6 narration, 7 map, 8 composer, 9 style)
│   ├── generate_meta_story_style.py # Phase 9: a meta story's colors, fonts and SVG marks
│   ├── meta_story_network.py        # Derive meta story social network from ego networks (no AI)
│   ├── meta_story_network_review.py # Phase 5b: AI review/enrich/prune of the derived network
│   ├── compose_meta_story.py        # Phase 8: story composer — caption layer + article layer
│   ├── meta_story_map.py            # Geographic clustering of meta story events (no AI)
│   ├── meta_story_map_narration.py  # Phase 7: map pipeline — event rating + stop narration agents, standalone CLI
│   ├── backfill_meta_story_networks.py # Inject social_network into existing meta stories (no AI)
│   ├── migrate_translations.py      # Rebase legacy translations onto English structure
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

Meta stories carry their own identity in `meta_story_styles.json`, resolved by `src/utils/metaStoryStyles.js` into `--ms-*` variables (plus `--heading-font` and `--body-font`) on the article container. Beyond colors and fonts it holds two SVG marks that punctuate the prose — a separator glyph and an ornamental rule — rendered by `MetaStoryOrnament.svelte`. See [Domain and data models](domain-and-data-models.md) for the schema and where each mark appears.

### Background Patterns

Each person has a custom SVG pattern (stored inline in `person_styles.json`). These are converted to data URLs and applied as CSS background images. A meta story's pattern works the same way, but is printed far more faintly: it sits behind a page of running text rather than behind full-screen slides.

### Font Loading

Fonts are self-hosted. `src/fonts.css` imports the eleven families from `@fontsource` packages and is pulled in by `src/main.js`, so the faces are bundled, fingerprinted, and served from our own origin. Nothing is fetched from a third party at runtime.

They used to come from `fonts.googleapis.com` through a render-blocking `<link>` in `index.html`. That gated the first paint on an external host: with the host reachable-but-hanging, first contentful paint measured 12,848 ms instead of 112 ms. `index.html` must stay free of third-party stylesheet links.

Two constraints when editing `src/fonts.css`:

- Import `latin` **and** `latin-ext` for every cut. The content needs Latin Extended (`ł` alone appears 110 times, e.g. Skłodowska).
- Keep the family list in step with `HEADING_FONT_CHOICES` / `BODY_FONT_CHOICES` in `scripts/generate_person_style.py`. A family the generator can pick but that is not imported renders in the fallback font.

`tests/test_font_coverage.py` enforces both, in both directions.

Because two heading faces ship a single weight by design (Archivo Black, DM Serif Display) while headings ask for 600-700, `app.css` sets `font-synthesis-weight: none` so the browser uses the real face instead of smearing a synthetic bold over it. `font-synthesis-style` is deliberately left alone — the sans body faces have no true italic and rely on synthetic oblique.
