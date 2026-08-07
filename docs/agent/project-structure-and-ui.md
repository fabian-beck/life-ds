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
│       ├── EventDepth.svelte # Context layer below the fold of a landmark event
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
│   ├── backfill_birth_events.py     # Classify the birth event of existing person datasets (no AI)
│   ├── backfill_death_events.py     # Classify the death event of existing person datasets, cause read from the event text
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

## The Depth Layer

A person's story moves sideways: one slide per event, horizontally scroll-snapped. On a life's landmarks the slide also moves downward, and the two axes mean different things — sideways is *later*, downward is *further into the same event*.

A deep slide is built as two screens inside the one scroll container:

- `.slide-fold` holds the event exactly as a slide without depth holds it, and is declared exactly one screen tall (`height: calc(100% + var(--slide-bottom-base))`), so the layer below starts out of sight. The definite height is what lets `.slide-reserve` shrink here the way it does on every other slide. When an event's own text cannot fit a screen, `watchContentFit` marks the slide `fold-overrun` and the fold grows instead of spilling over the layer below.
- `EventDepth.svelte` renders the passage: the written background, a sentence placing the event under the name it happened under and the name a map carries today, figures with their captions and credits, a paragraph for the people, and a quiet line of sources. The annotated terms are deliberately not among them — each is marked in the description itself, where a tap opens a popup carrying the same explanation and the same link, and a depth layer that reprints the popups adds nothing. All of it is already in the dataset — the fold keeps it a tap away at most, and the place and the sources are not on the slide at all. The people move out of the fold on a deep slide (`peopleInDepth` on `EventSlide`) so the same names are not listed twice.

  The register is prose, deliberately: no card, no rules, no icons, no section headings, a narrower measure than the slide's, and no line per record. `composeDepthParagraphs` in `storyHelpers.js` writes each record out as a sentence and runs the sentences together into paragraphs — the terms an event leans on become one passage, the people another — so the layer reads as a short chapter rather than a filing card. `asDepthSentence` decides the shape of each: an explanation that already names its subject ("Braintree was the Massachusetts town where…") is left to stand, one opening with an article becomes a statement ("Hut 8 was a section at…"), and anything else is kept as an apposition after a dash, because the words that open the rest are proper nouns and adjectives of nationality that must not be lowercased. About three quarters of the corpus takes the second path. The link out rides on the subject, so no "read more" marker breaks the line. `tests/depthProse.spec.js` covers the three shapes.

  What leads the layer is not composed at all. Phase 2 writes a `background` passage per event — the situation it sat in, why it mattered, what followed — and `EventDepth` renders it above the composed sentences. The prompt's operative rules are negative, because a summarizer pointed at an event it has just been shown will otherwise say it again in other words: the description is handed over as the thing to go beyond, and `build_background_avoidance` adds everything else the reader already has — the annotations, verbatim, as the popups under that same description; the events either side, which are a swipe away; the person's summary. A passage written without being shown the annotations repeats them, which is the one repetition a reader is guaranteed to notice, since the popup is directly above. `scripts/backfill_event_backgrounds.py` fills the field for existing datasets, sending Phase 2's own prompt rather than a copy of it, and takes a `--selection` file so only the events that actually open a depth layer cost a call. An event without a passage falls back to the composed sentences alone.

Which events offer it is decided in `selectDeepEventIndexes` (`src/utils/storyHelpers.js`), from `getEventWeight`. The weight is generated: Phase 1 proposes a life's events and weighs them against each other in the same call, which is the only step that sees a life whole — and how much of a life an event turns on is a comparison, not a property of the event. `scripts/backfill_event_weights.py` fills the number for datasets written before the field existed, one call per person, writing to the translated copies as well since a number does not translate and a reader in another language must not arrive at different events. `getEventWeight` still derives a score from the traces an important event leaves behind — a classification, a milestone icon, images, annotations, people, length — but only as a fallback for an unweighed dataset, and it is a weaker thing: it reads the documentation rather than the life, and it ranked Turing's Princeton doctorate above the paper that founded computer science. Selection is per chapter — each chapter offers its heaviest event and no more — which spreads the deep slides across the story instead of clustering them where a life happens to be best documented. An event whose depth layer would be nearly empty is passed over however heavy it scores. Across the current corpus this marks roughly a quarter to a third of a life's events. `tests/eventWeight.spec.js` covers the rules; the reading behavior is covered in `tests/interface.spec.js`.

The invitation down is `.depth-affordance`, a small chip held to the right edge in the gap the slide already keeps clear of the timeline, with two chevrons that beckon (and hold still under `prefers-reduced-motion`). It is on the right and not centered because centered it stood in the middle of the map. It yields to an open popup — an annotation, a date note, a person — which is drawn from the foot of the description and would otherwise be covered by it; `popupOpen` in `StoryView` takes it to zero opacity and out of the tab order for as long as one is showing. Otherwise it sits directly under the event's last line — anywhere lower and it stands over the map, which is the one thing on the slide that has to stay legible under it. That means it is a flex item in the fold rather than an absolutely placed one, and the event's auto margins are set so the event and the chip are centered as one block (`margin: auto auto 0` on `.content`, `margin-top: auto` on the reserve) with nothing opening up between them. It fades as the reader descends. The story map fades with it: `StoryView` tracks the active slide's scroll as `depthProgress` and passes it to `StoryMap`, which drives `--map-depth-opacity` — the map belongs to the event, not to the page of running text that replaces it. Down and up arrows drive the second axis on a deep slide before carrying the reader on to the next one, and a wheel flick that opens the depth layer is not allowed to continue into the next slide in the same gesture.

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
