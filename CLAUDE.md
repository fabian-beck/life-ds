# Claude Code Context: Life Data Stories

> **Important**: Update this file whenever there are major changes to project structure, features, data schemas, or development workflow. This ensures AI assistants have accurate context.

## Project Overview

A biographical visualization application that presents famous figures' life stories as full-screen, scroll-snapped slides with interactive timelines, maps, and social networks. Built with Svelte + Vite, designed mobile-first.

**Tech Stack**: Svelte 5, Vite 8, MapLibre GL, Protomaps, svelte-spa-router 5

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
     "styles": {
       "alan_turing": {
         "primary": "#5ED0FF",
         "secondary": "#9A7BFF",
         "background": "#040A18",
         "background_pattern_svg": "<svg>...</svg>",
         "heading_font": "Space Grotesk",
         "body_font": "IBM Plex Sans"
       }
     }
   }
   ```

   Note the top-level `styles` wrapper — entries are nested under it, not at the root.

3. **`data/people/{person_id}/`** - Person-specific data folder:
   - `life_events.json` - Chronological life events with locations, images, categories, and optional chapter groupings
   - `ego_network.json` - Social network connections with relationship metadata
   - `_cache/` - Wikipedia cache (articles, images, related content)

### Life Events Schema

Events are the core narrative units displayed as slides. Events can optionally be grouped into chapters representing distinct life phases, with a conclusion statement summarizing the person's legacy:

```json
{
  "person_id": "alan_turing",
  "chapters": [
    {
      "id": "early_years",
      "headline": "The Making of a Mind",
      "date_start": "1912",
      "date_start_precision": "year",
      "date_end": "1938",
      "date_end_precision": "year",
      "age_start": 0,
      "age_end": 26
    }
  ],
  "conclusion": "Turing's mind bridged abstract mathematics and wartime necessity, inventing the computer age before a cruel society silenced him.",
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

**Chapter Structure**:
- `headline`: Catchy, story-like title (2-5 words, varied lengths) - ONE unified concept, NOT a list. Vivid and evocative like a book chapter. Avoid commas, "and", or punctuation that creates lists.
- Each chapter should have thematic coherence - events share a common thread or life phase
- Aim for 3-6 chapters total that flow together to create narrative momentum
- `conclusion`: Crisp statement (1-2 sentences) capturing the person's legacy or life essence

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

### Meta Story Social Network

Each meta story JSON carries a `social_network` block, rendered as a d3-force
graph in `MetaStoryView.svelte` (component: `MetaStoryNetwork.svelte`, lazily
imported so `d3-force` stays out of the entry bundle). It follows the timeline
section and visualizes how the story's people connected:

```json
"social_network": {
  "nodes": [
    { "id": "alan_turing", "name": "Alan Turing", "type": "main",
      "portrait": "/portraits/alan_turing_thumbnail.webp",
      "roles": ["mathematician", "computer scientist"] },
    { "id": "sec:max_newman", "name": "Max Newman", "type": "secondary",
      "portrait": null, "roles": [] }
  ],
  "links": [
    { "source": "alan_turing", "target": "john_von_neumann",
      "relationship_type": "academic/colleague",
      "relationship_description": "…", "strength": "moderate", "kind": "main",
      "endpoints": {
        "alan_turing": { "relationship_type": "…", "relationship_description": "…", "strength": "…" },
        "john_von_neumann": { "relationship_type": "…", "relationship_description": "…", "strength": "…" }
      } }
  ]
}
```

Each link's `endpoints` map holds **each person's own ego-network view of the
other** (a bridge link has only the main person's entry). Top-level
`relationship_type`/`strength` (the richest direction) drive stroke width and
the tie explanations shown in the narration cards. A weak
`forceX` pulls each node toward an x derived from its `birth_year`, so the graph
reads left→right chronologically; secondary nodes (no birth year) sit at the
mean x of the main people they bridge. The final layout is **fully static** —
it is computed **in the background** by advancing the simulation to full
convergence in per-frame batches (via `requestAnimationFrame`, so the main
thread never blocks and the layout isn't rushed) behind a "Building the
network…" placeholder, then revealed once settled (~0.5s); nodes are not
draggable, so the graph never moves after that.

The network is presented as a **scrollytelling section**: the graph pins
(`position: sticky`, below the app's sticky header) while blurred,
slightly-transparent narration cards scroll up over it. The section's opening
text (under the "Connections" heading, rendered by `MetaStoryView.svelte`) is
the AI-written `social_network.narration.intro` paragraph (falling back to the
static `meta_story.network_subtitle` label only when a story has no narration);
there is no separate intro card and no legend. Each scroll card highlights one
**cluster ("circle")** of the network — its members stay lit while everything
else darkens (kept opaque so links never shine through) — under an AI-written
**headline** (`title`) and a short story text in which each circle member's name
is emphasized in place (the same `.person-mention` treatment used in the story
slides: main people glow in their own story color, bridging people get a neutral
emphasis; the names are not links). Each card maps 1:1 to a cluster (step index
`i` ⇒ `clusters[i]`). Clusters are derived client-side in
`src/utils/networkClusters.js` by deterministic greedy-modularity community
detection (tie strength weighted, main↔main links boosted ×3 so e.g. spouses
sharing a court are not split), ordered roughly by the mean birth year of
their main members. Unconnected nodes simply don't appear in any card. The
active card is tracked with an `IntersectionObserver` whose callback recomputes
the active step from card geometry (so jump-scrolls can't leave a stale
highlight). Hovering/tapping a node still transiently highlights that node's
ties (overriding the cluster highlight; there is no details panel anymore),
and the graph area uses `touch-action: pan-y` so vertical page scrolling stays
smooth on touch. The component takes a `currentLanguage` prop (used to localize
`relationship_type` and the fallback name list).

**Narration texts** live in the data as `social_network.narration`:

```json
"narration": {
  "intro": "2-3 sentence story-specific paragraph shown as the section's opening text",
  "circles": [
    { "key": "charles_babbage+ada_lovelace+konrad_zuse",
      "title": "The Engine Foretold",
      "text": "2-4 sentence story text…" }
  ]
}
```

A circle's `key` is its cluster key — the cluster's main person ids in cluster
order joined with `+` — computed identically by `derive_clusters()` in
`scripts/meta_story_network.py` and `computeClusters()` in the UI, which
matches narration to clusters by that key. Each circle's `title` is a short
evocative headline (not a list of names), shown as the card's heading; when a
circle has no `title` (older data) the card falls back to a joined list of the
members' names. Narration is written by AI as **Phase 6** of
`generate_meta_story.py` (non-fatal on failure) and then rewritten in the
story's unified voice by the Phase 7 composer (see "Meta Story Composition"
below); when a cluster has no matching
`text` (e.g. the network changed and narration wasn't regenerated), the card
falls back to listing the cluster's ties. Unlike the rest of `social_network`,
narration texts (both `title` and `text`) ARE part of the translation payload
(`network_narration` in `extract_meta_story_translatables`), so they are
translated and fingerprinted like other meta story prose.

- **Main nodes** (`type: "main"`) are the meta story's own people, drawn with
  portraits ringed in each person's `person_styles.json` primary color. A
  **main link** joins two main people when one appears in the other's
  `ego_network.json`.
- **Secondary nodes** (`type: "secondary"`, id prefixed `sec:`) are bridging
  people — not in the story, but present in the ego networks of **two or more**
  main people. They are drawn clearly smaller and capped at
  `MAX_SECONDARY_NODES` (14) so the graph stays readable.
- Graph derivation is **deterministic, no AI** (`scripts/meta_story_network.py`),
  run as Phase 5 of `generate_meta_story.py`. Nodes/links are **not** part of
  the translation payload, so the same graph is copied verbatim into translated
  files: node labels are person names (kept in the original language) and
  `relationship_type` is localized by the UI; `relationship_description` (used
  by the tie-list fallback and link tooltips) falls back to English. Only the
  `narration` texts are translated (see above).
- **Phase 5b — AI network review** (`scripts/meta_story_network_review.py`, one
  AI call, runs after derivation and **before** clustering/narration; non-fatal,
  opt out with `--skip-network-review`). The ego networks were each generated
  per person without seeing the meta story's people as a group, so the derived
  union misses direct ties, over-states vague ones, or carries stale wording.
  Given the derived graph plus **focused Wikipedia excerpts** for the main people
  (each article's lead plus the sentences that mention another main person — kept
  small so the prompt stays affordable), the model may **add** links between
  existing nodes, **modify** a link's type/description/strength, and **delete**
  rather indirect ties (e.g. a vague "influence" with no documented contact). How
  aggressively it enriches vs. prunes is scaled by the **density of the
  main↔main subgraph**: a sparse graph invites generous, well-supported additions
  and keeps documented influence (only truly unsupported ties are cut); a dense
  graph invites strict pruning of indirect ties. Application is deterministic and
  defensive — node ids are validated, unordered pairs matched regardless of
  orientation, self-loops skipped, and secondary nodes that no longer bridge ≥2
  main people are pruned — so a bad response can only edit links between existing
  nodes, never invent people. Added/modified links carry an `origin`
  (`review_added` / `reviewed`) marker; like the rest of the graph they are not
  translated (copied verbatim into translated files).
- Adding/removing people or regenerating ego networks changes the derived
  network. Rebuild every meta story (including translated copies) with
  `python scripts/backfill_meta_story_networks.py` (no API key needed), then
  `npx prettier --write "data/meta_stories/**/*.json"`. The backfill carries
  each file's existing narration over, dropping circles whose cluster key no
  longer exists — it warns when that happens, and the dropped circles need
  re-narration (Phase 6) or hand-written texts. **Note:** the backfill is a pure
  re-derivation, so it discards Phase 5b review edits (added/modified/deleted
  ties) just as it can orphan narration — re-run the full pipeline (or Phase
  5b + 6) when you need the reviewed graph back.

### Meta Story Map ("Places" section)

Each meta story JSON can carry a `geo_map` block, rendered as a scrollytelling
map section in `MetaStoryView.svelte` (component: `MetaStoryMap.svelte`, lazily
imported so MapLibre stays out of the entry bundle). It follows the network
section and usually comes last before the conclusion: a **non-interactive** map
(all pan/zoom handlers disabled — the story drives the camera) pins **full
screen** (full-bleed out of the story column, under the translucent sticky
header) while narration cards scroll up over it, one card per geographic
"stop". When a card enters the viewport band, the camera automatically flies to
that stop (single place → `flyTo` city zoom; spread cluster → `fitBounds`),
the stop's event markers (person-colored dots) light up, and the others dim.
Before the first card, the map shows an overview of all stops. The basemap
keeps place labels (rendered in the current UI language, unlike the label-free
story map) and the map area uses `touch-action: pan-y` so page scrolling stays
smooth on touch. Person names in the card texts get the same `.person-mention`
emphasis as the network cards; each card also lists up to 4 member events
(date, title, person) with a "+n more" overflow line.

```json
"geo_map": {
  "clusters": [
    { "key": "bletchley", "label": "Bletchley", "score": 3.0,
      "centroid": [-0.741, 51.997], "bbox": [-0.741, 51.997, -0.741, 51.997],
      "year_start": 1940, "year_end": 1940,
      "events": [
        { "person_id": "alan_turing", "person_name": "Alan Turing",
          "event_index": 9, "event_title": "Led Hut 8 naval cryptanalysis",
          "event_date": "1940", "place": "Bletchley",
          "coordinates": [-0.741, 51.997], "weight": 3.0 }
      ] }
  ],
  "narration": {
    "intro": "2-3 sentence opening paragraph shown under the section heading",
    "stops": [ { "key": "bletchley", "title": "The Codebreakers' Room",
                 "text": "2-4 sentence story text…" } ]
  },
  "discarded": [ { "key": "…", "label": "…", "reason": "…" } ],
  "generation": { "model": "…", "generated_at": "…", "located_events": 32, "rated_events": 32 }
}
```

The block is built by **Phase 8** of `generate_meta_story.py` (opt out with
`--skip-map`), a small multi-agent pipeline that runs **after** Phase 7 so
composer exclusions never reach the map (non-fatal throughout):

1. **Event rating agent** (`scripts/meta_story_map_narration.py`,
   `rate_map_events`, batched AI calls) — every located story event (the
   chapters' `person_events` resolved against each person's
   `life_events.json`; events without coordinates are skipped) is rated 0–3
   for how strongly it anchors the story *geographically*: 3 = the place is
   inseparable from the contribution (Bletchley Park), 0 = the location is
   incidental (a publication venue's city) and drops off the map entirely.
2. **Deterministic clustering** (`scripts/meta_story_map.py`, no AI) —
   complete-linkage agglomerative clustering on great-circle distance
   (`MERGE_DISTANCE_KM` = 50, so Cambridge and Bletchley stay distinct while
   same-city events merge). A cluster's score is the sum of its events'
   rating weights, so a single landmark event can carry a stop just like
   several weaker but co-located events. Top clusters are selected
   (score ≥ `MIN_CLUSTER_SCORE`, landmark-bearing clusters get
   `LANDMARK_BONUS` so an iconic single-event place isn't crowded out, cap
   `MAX_MAP_CLUSTERS` = 8, minimum top-up to 3) and ordered chronologically
   so the camera travels through the story in time. Debug CLI:
   `python scripts/meta_story_map.py <story_id>` (no API key).
3. **Narration agent** (`narrate_map_clusters`, 1 AI call) — writes the
   section intro plus a headline (`title`) and 2-4 sentence story text per
   stop, and may **discard** a stop whose geographic grouping is accidental
   rather than meaningful (events merely sharing a city that adds nothing to
   the story). Application is defensive: unknown keys are ignored, stops
   without narration are kept (the card falls back to its event list), and
   discards are honored only while ≥ 3 stops survive (re-kept by score).
   Discards are recorded under `geo_map.discarded` with reasons.

Narration stops are matched to clusters by `key` (slugified cluster label,
unique per document). Like the social network, the cluster data is technical
and copied **verbatim** into translated files; only `geo_map.narration`
(intro + stop titles/texts) is part of the translation payload
(`map_narration` in `extract_meta_story_translatables`), added only when
present so stories without a map keep their fingerprints. The composer's
exclusion cascade also prunes `geo_map` (excluded people's events are removed,
emptied clusters and their stops dropped).

Rebuild the map section for existing stories standalone (saves the English
file and re-translates, default `de`, `--skip-translate` to opt out):

```bash
python scripts/meta_story_map_narration.py computing_pioneers --verbose
python scripts/meta_story_map_narration.py --all
python scripts/meta_story_map_narration.py computing_pioneers --dry-run     # preview only
python scripts/meta_story_map_narration.py computing_pioneers --skip-rating # all events weigh 1.0
```

The UI section heading falls back to the localized `meta_story.map_heading`
("Places"/"Schauplätze") and the intro to `meta_story.map_subtitle` when a
story has no narration; a composed `section_headings.map` wins when present.

### Meta Story Composition (Phase 7 — Story Composer)

Every text in a meta story is originally written bottom-up by a phase that only
sees its own slice (description/conclusion before events exist, theme
connections per batch, network narration from the graph alone). **Phase 7**
(`scripts/compose_meta_story.py`, run automatically at the end of
`generate_meta_story.py`, opt out with `--skip-compose`) is a story composer
agent that reads the *assembled* story top-down and writes one coherent
narrative in two AI calls:

1. **Curation** — decides a *throughline* (the arc that anchors all prose) and,
   exceptionally, which clearly disconnected people to drop. Exclusions are
   applied deterministically with hard guardrails (at most ~25% of the cast,
   never below 3 people, unknown ids ignored) and cascade through
   `person_ids`, subtopics (emptied subtopics are dropped), chapter
   `person_events`, and the social network. The network is **pruned, not
   re-derived**, so Phase 5b review edits on surviving ties are kept;
   secondary nodes that no longer bridge ≥2 main people are removed.
2. **Composition** — rewrites all display prose in one voice: title, tagline,
   a top-level **`opening`** (a cold-open scene anchored in one specific
   event or person — rendered with a drop cap between the date range and the
   description, optionally with an image floated beside it), the description,
   story-specific **`section_headings`** (`{timeline, network, conclusion}`,
   replacing the generic "Timeline"/"Connections"/"Legacy" labels — the UI
   falls back to the localized labels when absent), a top-level
   **`timeline_intro`** (paragraph shown under the timeline heading), chapter
   headlines (date range re-appended automatically) plus a per-chapter
   **`lead_in`** (1-2 sentences shown inside the floating chapter header
   while scrolling; hidden in the landscape-mobile compact header), subtopic
   titles/descriptions, *sparse* refinements of event `theme_connection`s,
   the network narration (intro + circles, replacing the Phase 6 baseline in
   the story's unified voice), the conclusion, and optional
   **`section_images`** (`{timeline?, network?, conclusion?}`).

**Images** come exclusively from the people's own story slides: the composer
is shown a candidate list built from the story's `person_events` (each event's
`images` from the person's `life_events.json`) and may only *select by key*
(`person_id:event_index:image_index`, at most 4 per story, no reuse). The
url/caption/source are copied deterministically, so a hallucinated URL can
never enter the data. Each stored image keeps its provenance
(`person_id`/`event_index`/`image_index`); `MetaStoryFigure.svelte` renders it
with caption and source link.

Application is structural and defensive: chapters/subtopics/circles are
matched by id/key, unknown entries are ignored with warnings, missing entries
keep their existing texts, and dates/IDs/coordinates/graph data are never
model-editable. Provenance (model, throughline, exclusions with reasons) is
stamped into a top-level `composition` block. The whole phase is non-fatal —
on any failure the bottom-up texts are kept unchanged.

`timeline_intro`, `lead_in`, `opening`, `section_headings`, and the image
captions are part of the translation payload, but only when present, so
uncomposed stories keep their old fingerprints (and their translations stay
"current"). Image captions prefer the caption from the person's *translated*
life events (matched by provenance, like event titles), falling back to the
model-translated payload; URLs and sources are never touched. Composing a
story changes its English prose, so its translations go stale by fingerprint;
the standalone CLI re-translates right away (default `de`, `--skip-translate`
to opt out).

Recompose existing stories standalone (updates the registry entry and
translations too):

```bash
python scripts/compose_meta_story.py computing_pioneers --verbose
python scripts/compose_meta_story.py --all
python scripts/compose_meta_story.py computing_pioneers --dry-run       # preview only
python scripts/compose_meta_story.py computing_pioneers --no-exclusions # text-only
```

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
│   ├── generate_person_portrait.py  # Stylized portrait generation
│   ├── generate_all_portraits.py    # Batch portrait generation
│   ├── icon_categories.py           # MDI icon mappings + icon normalization
│   ├── fix_event_icons.py           # Repair invalid event_type_icon values
│   ├── translate_person.py          # Translation core + translate single person
│   ├── translate_all_persons.py     # Batch translate persons + meta stories, --check
│   ├── translate_meta_story.py      # Translate meta stories
│   ├── generate_meta_story.py       # Meta story workflow (phases 1-4, 5 network, 5b review, 6 narration, 7 composer, 8 map)
│   ├── meta_story_network.py        # Derive meta story social network from ego networks (no AI)
│   ├── meta_story_network_review.py # Phase 5b: AI review/enrich/prune of the derived network
│   ├── compose_meta_story.py        # Phase 7: story composer — top-down narrative composition
│   ├── meta_story_map.py            # Geographic clustering of meta story events (no AI)
│   ├── meta_story_map_narration.py  # Phase 8: map pipeline — event rating + stop narration agents, standalone CLI
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

## Development Workflow

### Common Commands

```bash
npm install          # Install dependencies
npm run dev          # Start dev server (localhost:5173)
npm run build        # Production build to dist/
npm run preview      # Preview production build
```

**Note**: The dev server is always running in this environment. No need to start it manually.

### Deployment

Hosted on **Netlify**, deployed **on demand only** — pushing/merging to `main`
does not publish. Auto-builds are stopped in the Netlify dashboard, and
`netlify.toml`'s `ignore = "exit 0"` skips git-triggered builds. Publish by
uploading the pre-built `dist/` with the CLI (not Netlify's build-from-git,
which is disabled; the Netlify MCP `deploy-site`/zip-and-build path returns
`400` for this project):

```powershell
npx netlify-cli login   # once per machine (browser auth)
npm run build
npx netlify-cli deploy --prod --dir=dist --site 12d3d478-2a11-4020-b56c-4580fa57e108
```

Use the `netlify-cli` package (its bin is `netlify`), **not** `npx netlify`
(that is the unrelated `netlify` API-client package). See README "Deployment"
for the full rationale.

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
- Interaction frequency: `rare`, `occasional`, `monthly`, `weekly`, `daily`, `yearly`
- Influence direction: `alter_to_ego`, `ego_to_alter`, `bidirectional`, `unknown`

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

**Components run in legacy (non-runes) mode.** The project is on Svelte 5, but
`export let`, `$:` and `on:click` all still work there and no component has been
converted. Adopting runes is a deliberate, separate decision — do not introduce
`$state`/`$derived`/`$props` into a component piecemeal, because a component
that uses any rune switches to runes mode wholesale and its `export let` and
`$:` statements stop compiling.

- Prefer reactive declarations (`$:`) over manual updates
- Keep component files focused (< 500 lines)
- Extract complex logic to functions outside component script
- Use stores sparingly (most state is local)
- `main.js` mounts with `mount(App, { target })`; `new App()` is not a thing in
  Svelte 5.
- Import `location` / `querystring` from `src/stores/router.js`, not from
  `svelte-spa-router`. Version 5 exposes them as runes-backed getters on its
  `router` object; that module bridges them back to stores with `toStore()` so
  non-runes components (and the plain-JS `queryParams.js`) can subscribe with
  `$location`. `push`/`replace` still come from `svelte-spa-router` directly.
- ESLint's `svelte/prefer-svelte-reactivity` is off because it presumes runes;
  plain `Map`/`Set` plus reassignment is correct in legacy mode.

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

- Entry chunk is ~425 kB (~115 kB gzipped), plus ~135 kB of CSS, as reported by
  `npm run build`. Person data and the map components are separate chunks
  fetched on demand.
- **Never `import * as` from `@mdi/js`.** The package holds ~7,400 icons
  (6.3 MB) and a wildcard import defeats tree-shaking — this once put 2.5 MB
  of icon paths in the bundle. Use named imports, or `virtual:mdi-icon-map`
  (see below) when the icon name is only known at runtime.
- **Keep MapLibre out of the initial bundle.** MapLibre, pmtiles and
  `@protomaps/basemaps` total ~1.1 MB. `LandingMap.svelte`, `StoryMap.svelte`
  and `MetaStoryMap.svelte` are the only modules that may import them, and all
  are themselves imported dynamically (`{#await import("./StoryMap.svelte")}`).
  A static import of either component from anywhere pulls all of it back into
  the entry chunk. Each map component must import `maplibre-gl.css` itself
  rather than relying on the other having been loaded.
- PMTiles uses HTTP range requests (efficient tile loading)
- CSS custom properties avoid style duplication
- SVG patterns are inline (no external requests)
- Images are lazy-loaded by browser

### Event Icons

`event_type_icon` values must name a real MDI icon or they render nothing.
Two mechanisms keep that true, because the model reliably gets it wrong:

- `normalize_icon()` (`scripts/icon_categories.py`) runs during generation and
  rewrites names that are provably wrong. The model is shown category keywords
  next to their icons and often returns the keyword prefixed with `mdi-`
  (`mdi-lecture` instead of `mdi-school-outline`). Unrecognised `mdi-` names
  are passed through, not defaulted: MDI has ~7,400 icons and
  `ICON_CATEGORIES` names 68, so an unknown name is usually a real icon
  outside the vocabulary (`mdi-airplane`), and defaulting it would replace a
  working icon with a generic calendar.
- The `virtual:mdi-icon-map` plugin (`vite.config.js`) builds the runtime
  lookup from the union of `icon_categories.py` and the icons actually present
  in `data/people`, since generated data drifts from the vocabulary. It
  validates every name against real `@mdi/js` exports and **warns at build
  time** about any that do not exist — that warning is the signal that data
  needs repair.

Repair existing data with `python scripts/fix_event_icons.py --dry-run` (then
without the flag). It rewrites icon values in place and touches nothing else.
`data/people/**/*.json` is prettier-ignored and formatted as it was generated,
so never rewrite these files with `json.dump` — it would reflow every line of
all 47 of them to change a handful of strings. Open them with `newline=""` when
writing, or Python turns each `\n` into `\r\n` on Windows and does the same
damage by a different route.

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
