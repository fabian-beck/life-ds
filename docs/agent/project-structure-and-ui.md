# Project Structure and UI

> Detailed reference for coding agents. Keep the root `AGENTS.md` concise and update this document when the related project behavior changes.

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
│       ├── MetaStoryNetwork.svelte # d3-force network for meta stories
│       ├── MetaStoryMap.svelte # Scrollytelling map for meta stories
│       ├── PersonChip.svelte # Inline person chip (slides, tooltips)
│       ├── PersonCard.svelte # Portrait card linking to a person's story
│       └── ImageViewer.svelte # Lightbox for event images
│   └── utils/
│       ├── storyHelpers.js   # Dates, images, event/person helpers
│       └── personNames.js    # Finds person names in prose (highlighting)
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
│   ├── generate_person_portrait.py  # Stylized portrait generation
│   ├── generate_all_portraits.py    # Batch portrait generation
│   ├── icon_categories.py           # MDI icon mappings + icon normalization
│   ├── fix_event_icons.py           # Repair invalid event_type_icon values
│   ├── translate_person.py          # Translation core + translate single person
│   ├── translate_all_persons.py     # Batch translate persons + meta stories, --check
│   ├── translate_meta_story.py      # Translate meta stories
│   ├── generate_meta_story.py       # Meta story workflow (1 plan, 2 collect, 3 curate, 3b fit chapters, 4 context, 5 network, 5b review, 6 narration, 7 map, 8 composer)
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

### Background Patterns

Each person has a custom SVG pattern (stored inline in `person_styles.json`). These are converted to data URLs and applied as CSS background images.

### Font Loading

Fonts are loaded dynamically from Google Fonts when a person's story is viewed. The app normalizes font names (strips weights, handles special cases).
