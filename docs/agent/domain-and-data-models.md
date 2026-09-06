# Domain and Data Models

> Detailed reference for coding agents. Keep the root `AGENTS.md` concise and update this document when the related project behavior changes.

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

   An entry may also carry `"hidden": true`, and so may an entry of the meta story registry `data/meta_stories.json`. The person or collection then stays in the data but is kept off the deployed site: a production build lists it nowhere—not on the landing page, not among the related-people or collection cards, not as a person mention—and sends its route to the landing page as it does an unknown id. The development server shows hidden entries by default, marked with a badge, and offers a toggle next to the high-contrast one that previews the deployed view (`src/stores/visibility.js`, `src/utils/visibility.js`). The English registries are the reference the application reads the flag from; the localized registries mirror it because their entries are derived from the English ones whole. Set or clear it with `python scripts/set_hidden.py --person <id> --meta-story <id> [--show]`, which writes every registry, and `--list` prints what is hidden. The registry writers keep the flag through a regeneration. A visible entry carries no flag at all; `false` is never written.

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
      "locations": [
        {
          "name_historic": "Cambridge",
          "name_modern": "Cambridge, England, United Kingdom",
          "primary": true,
          "centroid": [0.1218, 52.2053]
        }
      ],
      "involved_people": ["Max Newman", "Alonzo Church"],
      "sources": ["https://en.wikipedia.org/wiki/..."],
      "event_type_icon": "mdi-file-document",
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

**New Fields (Two-Phase System)**:
- `locations`: every place the event touches, each with the name at the time (`name_historic`), the name to geocode against today (`name_modern`, e.g. "Kaliningrad, Russia" for historic "Königsberg"), a `centroid` as `[lon, lat]`, and a `primary` flag marking the one the maps pin. This is the only location field anything reads — the person story, the collection map, and the meta-story planner alike. An older `location_coordinates` list (`label`/`name`/`source`) still sits on ten English events and their German derivations, listed in `data/outdated.md`; nothing reads it, so those events show no place until their datasets are regenerated.
- `involved_people`: List of people directly involved in this event (excludes the main subject)
- `event_type_icon`: MDI icon identifier for visual categorization (e.g., "mdi-crown", "mdi-book", "mdi-school")

**Annotations**: an event may carry an `annotations` map of `term → {explanation, wikipedia_url?}`, rendered on the slide as a tappable term with a popup. A term is placed in the description in one of two ways, both handled by `parseDescriptionSegments` in `src/utils/story/prose.js`:

- **Markup** — `[[term|display]]` in the description. Use it when the sentence words the term differently from the key (`[[Modernisme|the modernista style]]`); the term before the `|` is the id the map is keyed by, and it stays in English through translation.
- **By name** — no markup at all. The term is then looked for in the prose, the way person names are, matching whole words case-insensitively and accepting a slugged key (`Greek_War_of_Independence`) or one qualified by its region (`Portland, Oregon` for a sentence that only says "Portland"). This exists because Phase 2 writes the explanation and omits the markup often enough to matter — the terms it stranded were mostly institutions, so the names most in need of a gloss were the ones without one.

Markup wins where both could apply, and a name that is already emphasized as a person wins over an unmarked term, since the person's card says more than a gloss would. A term that appears nowhere in the description simply renders nothing. A term is explained once per story: the normalize step drops an annotation whose term an earlier event already annotated or carried in its title, so a reader is not offered a definition of what the previous slides were about.

**Event Classification (`event_class`)**: an optional structured block Phase 1 writes for the recognized kinds of event — `birth`, `marriage_partnership`, `migration`, `invention`, and `publication` — which `EventSlide.svelte` renders as an info box instead of the plain event badge. A publication carries `title`, `publication_type`, and optionally `publisher`, `significance`, and `impact`:

```json
"event_class": {
  "type": "publication",
  "title": "On the Constitution of Atoms and Molecules",
  "publication_type": "paper",
  "publisher": "Philosophical Magazine"
}
```

The slide names the work and does not link it. The event's own `sources` are about the event, and no step resolves the work itself.

**Chapter Structure**:
- `headline`: Catchy, story-like title (2-5 words, varied lengths) - ONE unified concept, NOT a list. Vivid and evocative like a book chapter. Avoid commas, "and", or punctuation that creates lists.
- `illustration` (optional): the chapter's abstract opening image, written by `scripts/generate_chapter_illustrations.py`:

  ```json
  "illustration": {
    "image": "/chapter_art/alan_turing/split_sunrise_medium.webp",
    "medium": "/chapter_art/alan_turing/split_sunrise_medium.webp",
    "full": "/chapter_art/alan_turing/split_sunrise_full.webp",
    "concept": "A pale gold disc hovers at the center of deep blue darkness, cleanly divided by a narrow vertical seam…",
    "creator": "AI generated artwork",
    "generated_on": "2026-08-09"
  }
  ```

  It depicts nothing that happened: no people, no places, no text, only a metaphor for what the chapter is about. That is why it carries no caption and no alt text — `ChapterSlide.svelte` prints it translucent above the headline and hides it from assistive technology, which also means none of these fields are translated. Every language copy carries the same paths and the same `concept`, the way portrait metadata does; `concept` is kept so the picture can be redrawn without a second text call.
- Each chapter should have thematic coherence - events share a common thread or life phase
- Aim for 3-6 chapters total that flow together to create narrative momentum
- `conclusion`: Crisp statement (1-2 sentences) capturing the person's legacy or life essence

**Important**:
- Events may not have locations (non-geographic events) or images
- Chapters are optional but recommended for organizing life narratives
- Each event can reference a chapter via the `chapter` field (using the chapter's `id`)
- Chapters should be chronological and non-overlapping
- The new fields are optional and backward-compatible with existing data

### Event Classifications

A few kinds of event carry more than prose, and an optional `event_class` block holds that structure so the slide can render it instead of burying it in the description. The vocabulary lives in one place — `EVENT_CLASS_CONFIG` in `scripts/events/event_classes.py`, which drives the Phase 1 detection guidelines, the Phase 2 research focus ("do not repeat what the classification already holds"), and the logging. Adding a kind means a Pydantic model in `scripts/events/schemas.py`, an entry in the `EventClassification` union there, a config entry, and the matching branch in `EventSlide.svelte` and `Timeline.svelte`. Phase 1 classifies; Phase 2 never adds or edits a classification.

| type | fields |
| --- | --- |
| `birth` | `father`, `mother`, `birth_name`, `characterization` |
| `death` | `cause`, `characterization`, `place_of_rest` |
| `marriage_partnership` | `subtype`, `partner`, `duration`, `children`, `characterization` |
| `migration` | `from_location`, `to_location`, `characterization` |
| `invention` | `title`, `description`, `impact` |
| `publication` | `title`, `publication_type`, `publisher`, `significance`, `impact` |

The block splits in two for localization. Its **prose** — a cause, a characterization, an invention's description — is translated with the rest of the document (`EVENT_CLASS_TEXT_FIELDS` in `scripts/translate_person.py`; a new prose field has to be added there or it stays English in every translated copy). Its **tokens** — `type`, `subtype`, `publication_type` — are machine values the datasets keep in every language, named by the interface through `src/utils/eventClassLabels.js`. A change that adds prose to the block therefore leaves the translations stale by fingerprint; `python scripts/translate_all_persons.py --target-lang de` is what closes that.

The two life boundaries are the classifications a run does not leave to the model. `ensure_birth_classification()` and `ensure_death_classification()` run right after Phase 1 and decide from the dates which events they are; each classifies that event when the model didn't and strips its class from any other event (a child's birth, a spouse's death). The model's own classification is consulted only when no event is dated at the boundary at all — which is how a medieval life whose events carry no ages still finds one.

- **Birth**: dated at age 0 or on the person's birth date, and either opening the story or reading as a birth. A child's birth carries the subject's own age, never zero.
- **Death**: dated on the person's death date, or closing the story within the death year — a duel or a tram accident opens the event days before the death it caused. The search runs backwards, so a day that holds three events (Stauffenberg's bomb, the failed coup, the execution) resolves to the last of them. With no death date on record, only a closing event whose *title* names a death qualifies.

The prose of both boundary events has a definition of its own, `BIRTH_DESCRIPTION_GUIDANCE` and `DEATH_DESCRIPTION_GUIDANCE` in `scripts/events/event_classes.py`, which Phase 1 writes the skeleton from, Phase 2 rewrites a skeleton to when it fell short, and the review holds the shipped description to. The slide already shows the birth and the death themselves, so a birth description tells the household the child enters and grows up in, what the parents did, where the family stood, and the circumstances of the moment, and a death description tells what led to the death and the conditions of the end. Phase 2 is otherwise told to refine a description only shorter, and these two events are the exception.

The birth slide shows the parents in the same generational representation the network view uses for a family: a labeled parents box of `PersonChip`s over a link line down to the person's portrait (`getBirthParents()` in `src/utils/story/personMatching.js`). The names come from the classification and are resolved against `ego_network.json`, so each chip carries the network's own relationship metadata; when the classification names nobody the parents are read from the network directly (`family/father`, `family/mother`, qualifiers like `step-`/`adoptive-` stripped). Placeholder names ("Unnamed mother of …") are dropped rather than shown, and a birth with no parents, birth name, or characterization keeps the plain class badge instead of an empty box. The parents are removed from the slide's other people so they appear once.

A dataset generated before the classification existed carries none; flag it in `data/outdated.md` and regenerate it — there is no repair path.

The death slide is the birth's mirror: the same frame and label, boxing the **cause of death** where the birth boxes the parents, with the circumstances beside the "Died" label and the resting place beneath. A death whose sources give none of the three keeps the plain class badge.

### Ego Network Schema

Social connections with relationship metadata. Every connection is a **mutual tie**: two people who dealt with each other directly, documented by the sources. The schema therefore carries no direction of influence, no relationship years, and no activity tags — the type, the description, and the two weights say what the tie was:

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
      "strength": "strong",
      "sources": ["https://..."],
      "notes": "..."
    }
  ]
}
```

**Relationship types**:

`relationship_type` is always `category/role`, both segments drawn from the closed vocabulary in `scripts/utils/relationship_vocabulary.py` — 12 categories (`family`, `professional`, `social`, `academic`, `artistic`, `political`, …) and about a hundred roles. Categories are the circles the network view opens, so they stay coarse: `academic` holds every tie of scholarship, and the `intellectual` category that used to split a scientist's circle in two is retired (`RETIRED_CATEGORIES` in the module); the datasets still carrying it are listed in `data/outdated.md`, and the locales keep its entry only until they are regenerated. Both segments are reader-facing text, resolved through the locale files by `src/utils/relationshipLabels.js` — `network.category.{segment}` for the first and `network.role.{segment}_one`/`_other` for the second. The vocabulary used to be open, which left 155 generated types without a locale entry rendering as title-cased English in every language (issue #117); now the generator prompt is constrained to it, generated and review output is checked against it through `normalize_relationship_type()` (which collapses spelling variants and reports anything outside), and a token that still escapes falls back to a visibly generic label ("Connection"/"Verbindung") and a dev-console warning instead of fake precision. Extending the vocabulary means adding the role to the module **and** its `network.role.*` entries to both locale files; `tests/test_relationship_vocabulary.py` fails on any drift between module, corpus, and locales. There is deliberately no migration map from old tokens to new ones — a dataset that predates a vocabulary change is regenerated, not rewritten.

The conflict roles are directional (issue #119): for a relationship with a state or regime official the role names the action toward the subject — `political/censor`, `political/persecutor`, `political/banned_by` when the official acted against the subject, `political/patron` when they protected or promoted them — never a neutral office word, and never `opponent` or `rival` for one-sided persecution; those, with `adversary`, are reserved for genuinely two-sided conflicts. The other party is the person who acted, never the regime or the police force as such.

**Mutual ties only**: a connection is a relationship both people took part in — they met, corresponded, worked, lived, or fought with one another. Someone the subject only read or admired from afar, or who only later drew on the subject's work, is not a connection; such one-sided influence belongs in the category summary as prose. The generator's prompt states the rule, and the `influence`, `inspiration`, and `legacy` roles of the vocabulary name a documented direct tie under it. The schema used to carry `influence_direction` (`bidirectional` / `ego_to_alter` / `alter_to_ego`), `start_year` / `end_year`, and `shared_activities` tags; a mutual tie has no direction, the description dates the tie where the sources do, and the tags restated the description. The generator no longer writes the four fields, `PersonChip.svelte` no longer shows them, the story no longer filters an event's chips by the tie's years, and the review step no longer edits them. Datasets generated before the change still carry the fields; they are listed in `data/outdated.md` for regeneration, and `translate_person.py` keeps carrying `shared_activities` for a dataset that has the key so its fingerprint holds until then.

**Strength only**: the one weight a connection carries is `strength` (`strong` | `moderate` | `weak`). The schema used to ask for an `interaction_frequency` as well (`daily` through `rare`); how often two people dealt with each other is rarely stated in the sources, so the value was the model's guess and could not be checked. The generator no longer writes the field, `PersonChip.svelte` no longer shows it, the review step no longer edits it, and the locales carry no entry for it. Datasets generated before the change still carry the field, listed in `data/outdated.md`; the interface ignores it.

**Individuals only**: every connection is one named human being. The generator's schema has no field for anything else, its prompt forbids organizations, states, regimes, and unnamed groups as nodes and asks for the individual through whom such a tie ran (the official who dismissed the subject, the director who hired them) or for the tie to stay in the category summary, and `looks_collective()` in `scripts/generate_person_network.py` reports a name that still reads as a collective ("Nazi regime", "IBM", "Students at …") in the run log. Datasets generated before this rule carry such nodes, typed by `entity_kind` (`organization` | `group`) with an optional translatable `qualifier` ("secret police"); they are listed in `data/outdated.md` for regeneration, and until then `PersonChip.svelte` still shows the localized entity label (`network.entity.*`) and the qualifier in the chip tooltip.

### Meta Story Social Network

Each meta story JSON carries a `social_network` block, rendered as a d3-force graph in `MetaStoryView.svelte` (component: `MetaStoryNetwork.svelte`, lazily imported so `d3-force` stays out of the entry bundle). Where it sits among the three component sections is the composer's decision (see `section_order` under "Meta Story Composition"); it visualizes how the story's people connected:

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

Each link's `endpoints` map holds **each person's own ego-network view of the other** (a bridge link has only the main person's entry). Top-level `relationship_type`/`strength` (the richest direction) drive stroke width and the tie explanations shown in the narration cards. A weak `forceX` pulls each node toward an x derived from its `birth_year`, so the graph reads left→right chronologically; secondary nodes (no birth year) sit at the mean x of the main people they bridge. The final layout is **fully static** — it is computed **in the background** by advancing the simulation to full convergence in per-frame batches (via `requestAnimationFrame`, so the main thread never blocks and the layout isn't rushed) behind a "Building the network…" placeholder, then revealed once settled (~0.5s); nodes are not draggable, so the graph never moves after that.

The network is presented as a **scrollytelling section**: the graph pins (`position: sticky`, below the app's sticky header) while blurred, slightly-transparent narration cards scroll up over it. The section carries no standfirst under its heading — the composed `section_bodies.network` prose is the section's only running text (see "Meta Story Composition") — and there is no separate intro card and no legend. Each scroll card highlights one **cluster ("circle")** of the network — its members stay lit while everything else darkens (kept opaque so links never shine through) — under an AI-written **headline** (`title`) and a short story text in which each circle member's name is emphasized in place (the same `.person-mention` treatment used in the story slides: main people glow in their own story color, bridging people get a neutral emphasis; the names are not links). Each card maps 1:1 to a cluster (step index `i` ⇒ `clusters[i]`). Clusters are derived client-side in `src/utils/networkClusters.js` by deterministic greedy-modularity community detection (tie strength weighted, main↔main links boosted ×3 so e.g. spouses sharing a court are not split), ordered roughly by the mean birth year of their main members. Unconnected nodes simply don't appear in any card. The active card is tracked with an `IntersectionObserver` whose callback recomputes the active step from card geometry (so jump-scrolls can't leave a stale highlight). Hovering/tapping a node still transiently highlights that node's ties (overriding the cluster highlight; there is no details panel anymore), and the graph area uses `touch-action: pan-y` so vertical page scrolling stays smooth on touch. The component takes a `currentLanguage` prop (used to localize `relationship_type` and the fallback name list).

**Narration texts** live in the data as `social_network.narration`:

```json
"narration": {
  "circles": [
    { "key": "charles_babbage+ada_lovelace+konrad_zuse",
      "title": "The Engine Foretold",
      "text": "2-4 sentence story text…" }
  ]
}
```

A circle's `key` is its cluster key — the cluster's main person ids in cluster order joined with `+` — computed identically by `derive_clusters()` in `scripts/meta_story_network.py` and `computeClusters()` in the UI, which matches narration to clusters by that key. **Composed stories** additionally carry an explicit `member_ids` list per circle: the Phase 8 composer's caption-layer call may reorganize the circles (merge, split, reorder, or discard clusters), and when `member_ids` are present the UI builds the circles from them directly (in authored order; secondary nodes join the circle holding most of their main neighbors) instead of running community detection. Each circle's `title` is a short evocative headline (not a list of names), shown as the card's heading; when a circle has no `title` (older data) the card falls back to a joined list of the members' names. Narration is written by AI as **Phase 6** of `generate_meta_story.py` (non-fatal on failure) and then rewritten by the Phase 8 composer's caption-layer call — the circle texts belong to the caption layer, so they describe their own members' documented ties and leave the story's argument to the article layer (see "Meta Story Composition" below); when a cluster has no matching `text` (e.g. the network changed and narration wasn't regenerated), the card falls back to listing the cluster's ties. Unlike the rest of `social_network`, narration texts (both `title` and `text`) ARE part of the translation payload (`network_narration` in `extract_meta_story_translatables`), so they are translated and fingerprinted like other meta story prose.

- **Main nodes** (`type: "main"`) are the meta story's own people, drawn with portraits ringed in each person's `person_styles.json` primary color. A **main link** joins two main people when one appears in the other's `ego_network.json`.
- **Secondary nodes** (`type: "secondary"`, id prefixed `sec:`) are bridging people — not in the story, but present in the ego networks of **two or more** main people. They are drawn clearly smaller and capped at `MAX_SECONDARY_NODES` (14) so the graph stays readable.
- Graph derivation is **deterministic, no AI** (`scripts/meta_story_network.py`), run as Phase 5 of `generate_meta_story.py`. Nodes/links are **not** part of the translation payload, so the same graph is copied verbatim into translated files: node labels are person names (kept in the original language) and `relationship_type` is localized by the UI; `relationship_description` (used by the tie-list fallback and link tooltips) falls back to English. Only the `narration` texts are translated (see above).
- **Phase 5b — AI network review** (`scripts/meta_story_network_review.py`, one AI call, runs after derivation and **before** clustering/narration; non-fatal, opt out with `--skip-network-review`). The ego networks were each generated per person without seeing the meta story's people as a group, so the derived union misses direct ties, over-states vague ones, or carries stale wording. Given the derived graph plus **focused Wikipedia excerpts** for the main people (each article's lead plus the sentences that mention another main person — kept small so the prompt stays affordable), the model may **add** links between existing nodes, **modify** a link's type/description/strength, and **delete** rather indirect ties (e.g. a vague "influence" with no documented contact). How aggressively it enriches vs. prunes is scaled by the **density of the main↔main subgraph**: a sparse graph invites generous, well-supported additions and keeps documented influence (only truly unsupported ties are cut); a dense graph invites strict pruning of indirect ties. Application is deterministic and defensive — node ids are validated, unordered pairs matched regardless of orientation, self-loops skipped, and secondary nodes that no longer bridge ≥2 main people are pruned — so a bad response can only edit links between existing nodes, never invent people. Added/modified links carry an `origin` (`review_added` / `reviewed`) marker; like the rest of the graph they are not translated (copied verbatim into translated files).
- Adding/removing people or regenerating ego networks changes the derived network. A meta story whose networks no longer match its people's ego networks is outdated data: flag it in `data/outdated.md` and re-run its pipeline (`generate_meta_story.py`, or Phase 5 + 5b + 6 for the network alone), which re-derives the graph, reviews it, and re-narrates the circles.

### Meta Story Map ("Places" section)

Each meta story JSON can carry a `geo_map` block, rendered as a scrollytelling map section in `MetaStoryView.svelte` (component: `MetaStoryMap.svelte`, lazily imported so MapLibre stays out of the entry bundle). Like the other two component sections its position is composed (see `section_order` under "Meta Story Composition"), and wherever it lands it works the same way: a **non-interactive** map (all pan/zoom handlers disabled — the story drives the camera) pins **full screen** (full-bleed out of the story column, under the translucent sticky header) while narration cards scroll up over it, one card per geographic "stop". When a card enters the viewport band, the camera automatically flies to that stop (single place → `flyTo` city zoom; spread cluster → `fitBounds`), the stop's event markers (person-colored dots) light up, and the others dim. Before the first card, the map shows an overview of all stops. The basemap keeps place labels (rendered in the current UI language, unlike the label-free story map) and the map area uses `touch-action: pan-y` so page scrolling stays smooth on touch. Person names in the card texts get the same `.person-mention` emphasis as the network cards; each card also lists up to 4 member events (date, title, person) with a "+n more" overflow line.

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
    "stops": [ { "key": "bletchley", "title": "The Codebreakers' Room",
                 "text": "2-4 sentence story text…" } ]
  },
  "discarded": [ { "key": "…", "label": "…", "reason": "…" } ],
  "generation": { "model": "…", "generated_at": "…", "located_events": 32, "rated_events": 32 }
}
```

The block is built by **Phase 7** of `generate_meta_story.py` (opt out with `--skip-map`), a small multi-agent pipeline that runs **before** the Phase 8 composer — the composer may then reorder/discard the stops, and its exclusion cascade prunes the map deterministically (non-fatal throughout):

1. **Event rating agent** (`scripts/meta_story_map_narration.py`, `rate_map_events`, batched AI calls) — every located story event (the chapters' `person_events` resolved against each person's `life_events.json`; events without coordinates are skipped) is rated 0–3 for how strongly it anchors the story *geographically*: 3 = the place is inseparable from the contribution (Bletchley Park), 0 = the location is incidental (a publication venue's city) and drops off the map entirely.
2. **Deterministic clustering** (`scripts/meta_story_map.py`, no AI) — complete-linkage agglomerative clustering on great-circle distance (`MERGE_DISTANCE_KM` = 50, so Cambridge and Bletchley stay distinct while same-city events merge). A cluster's score is the sum of its events' rating weights, so a single landmark event can carry a stop just like several weaker but co-located events. Top clusters are selected (score ≥ `MIN_CLUSTER_SCORE`, landmark-bearing clusters get `LANDMARK_BONUS` so an iconic single-event place isn't crowded out, cap `MAX_MAP_CLUSTERS` = 8 candidates, minimum top-up to 3) and ordered chronologically so the camera travels through the story in time. Debug CLI: `python scripts/meta_story_map.py <story_id>` (no API key).
3. **Narration agent** (`narrate_map_clusters`, 1 AI call) — writes a headline (`title`) and a 2-4 sentence story text per stop, and **curates how many stops the map has**: from the (up to `MAX_MAP_CLUSTERS`) candidates it keeps only the places that genuinely matter to the story — usually no more than ~5 — **discarding** both accidental groupings (events merely sharing a city that adds nothing) and real-but-secondary places that would only pad the map. The stop count is the agent's decision, not a fixed cap. Application is defensive: unknown keys are ignored, stops without narration are kept (the card falls back to its event list), and discards are honored only while ≥ 3 stops survive (re-kept by score). Discards are recorded under `geo_map.discarded` with reasons.

Narration stops are matched to clusters by `key` (slugified cluster label, unique per document). Like the social network, the cluster data is technical and copied **verbatim** into translated files; only `geo_map.narration` (the stop titles/texts) is part of the translation payload (`map_narration` in `extract_meta_story_translatables`), added only when present so stories without a map keep their fingerprints. The composer's exclusion cascade also prunes `geo_map` (excluded people's events are removed, emptied clusters and their stops dropped).

Rebuild the map section for existing stories standalone (saves the English file and re-translates, default `de`, `--skip-translate` to opt out):

```bash
python scripts/meta_story_map_narration.py computing_pioneers --verbose
python scripts/meta_story_map_narration.py --all
python scripts/meta_story_map_narration.py computing_pioneers --dry-run     # preview only
python scripts/meta_story_map_narration.py computing_pioneers --skip-rating # all events weigh 1.0
```

The UI section heading falls back to the localized `meta_story.map_heading` ("Places"/"Schauplätze") when a story has no composed `section_headings.map`; the section itself carries no standfirst, only its composed body prose.

### Meta Story Composition (Phase 8 — Story Composer)

A meta story page carries **two layers of text**, and keeping them apart is what the composer is for:

- The **caption layer** is bound one-to-one to something the reader is looking at — a chapter band of the timeline, an event on it, a circle in the graph, a stop on the map. It says what *that item* is: concrete, short, factual.
- The **article layer** is the running prose *between* the components — the opening, description, `section_bodies`, conclusion. It says what the components structurally cannot: the world these lives happened inside, the conditions that produced the sequence, what it cost, what followed. **Context, not recap.**

Every text is originally written bottom-up by a phase that only sees its own slice (description/conclusion before events exist, theme connections per batch, network narration from the graph alone). **Phase 8** (`scripts/compose_meta_story.py`, run automatically at the end of `generate_meta_story.py` after the map phase, opt out with `--skip-compose`) reads the *assembled* story top-down — per-event description excerpts from the people's `life_events.json`, the full network tie set, the current circle organization, the map stops, the chapters' `historical_context`, **and focused Wikipedia excerpts for every main person** (article lead + sentences mentioning other main people, via `build_wikipedia_context` shared with Phase 5b) — and rewrites both layers in four AI calls:

1. **Curation** — decides a *throughline* (the arc that anchors all prose) and, exceptionally, which clearly disconnected people to drop. Exclusions are applied deterministically with hard guardrails (at most ~25% of the cast, never below 3 people, unknown ids ignored) and cascade through `person_ids`, subtopics (emptied subtopics are dropped), chapter `person_events`, the social network, and the map. The network is **pruned, not re-derived**, so Phase 5b review edits on surviving ties are kept; secondary nodes that no longer bridge ≥2 main people are removed.
2. **Caption layer** (`run_component_narration`, model `ComponentNarration`) — the item-bound texts: chapter headlines (date range re-appended automatically) plus a per-chapter **`lead_in`**, subtopic titles and descriptions, *sparse* refinements of event `theme_connection`s, its **own circle organization** for the network section (each circle as `member_ids` + title + text — it may merge, split, reorder, or discard the derived clusters; applied with guardrails: only existing main people, each person in at most one circle, ≥2 members per circle, and the organization must cover at least half of the connected cast or it is rejected in favor of the previous narration), and **curated map stops** (kept stops in presentation order with rewritten narration; discards recorded under `geo_map.discarded` with reasons and honored only while ≥3 stops survive, re-kept by score). The prompt's single rule is *describe the item, never the story* — no thesis, no significance, no era-level generalization.
3. **Article layer** (`run_article`, model `StoryArticle`) — title, tagline, a top-level **`opening`** (a cold-open scene anchored in one specific event or person — rendered with a drop cap between the date range and the description, optionally with an image floated beside it), the description, story-specific **`section_headings`** (`{timeline, network, map?, conclusion}`, replacing the generic labels — the UI falls back to the localized labels when absent), free-form **`section_bodies`** (see below — a section's only running text, since no section carries a standfirst under its heading), and the conclusion.

   The call is shown **the finished caption layer verbatim** (`render_component_layer`) under a heading saying it is already on the page, plus `build_context_notes` — the story's span, threads, cast, and `historical_context` entries — as its actual subject matter, deliberately *not* the item list. This is the point of the call split: "do not repeat the components" is unenforceable when the model has only the raw item data and must guess what the captions will say, so it writes the items again in better prose. Measured on the stories composed before the split, article paragraphs matched the caption text directly below them at a Dice overlap of **0.53** — near-verbatim restatement, about twice the paraphrase band seen within the article.

   Two tests govern the article: delete every component and what remains must still read as one continuous essay; and no paragraph may read as a description of the thing below it. The prompt names **both** failure modes with worked examples from real runs — the recap (a list of the map's own stops, one clause each) and the escape into abstraction it invites ("the geography joined centers of coordination to territories subject to changing control"). Context means **different specifics**, not generality: the named law, the institution and what it could not do, the printer who refused the manuscript. An empty section body beats an abstract one.
4. **Redundancy pass** (opt out with `--skip-redundancy-pass`) — a focused editing call that rewrites article slots repeating **one another or the caption layer**. The captions are passed as *fixed reference slots* (`collect_caption_slots`, ids `caption:{chapter|circle|stop}:{i}`): the pass reads them and may rewrite an article slot that retells one, but a revision addressed to a caption is rejected. Article slots are addressed by stable ids — `opening`, `description`, `conclusion`, and `body:{section}:{index}` for body paragraphs — and a revision may only replace the text of a slot that already exists (unknown ids are ignored with a warning), so the pass can rewrite but never add or remove. When two article slots share a point the **later** one is rewritten; the `opening` is exempt from caption overlap, being the one slot allowed to narrate a documented moment in full. The pass is explicitly forbidden to fix a repetition by generalizing — it must swap the repeated specifics for different specifics, or make the slot shorter. Revisions are patched into the composition result *before* `apply_composition`, so they pass through the same defensive path as everything else; the count lands in `composition.prose_revisions`. Non-fatal — on failure the prose is applied unrevised.

Two **diagnostics, not gates**, are printed in `--verbose`, one per failure mode:

- `rank_slot_overlaps()` ranks cross-slot sentence pairs by content-word Dice overlap, before and after the pass. Caption slots are compared against article slots but never against each other. It has deliberately no threshold *within* the article — real paraphrase scores ~0.27 while unrelated sentences sharing two proper names score ~0.26, so the bands overlap and no cutoff separates them; only the before/after change is meaningful. Article↔caption is the one place the numbers separate cleanly: 0.43–0.53 means the article has slipped back into recapping its components.
- `find_abstract_slots()` flags article slots of 25+ words carrying fewer than two *anchors* (`count_anchors()` — proper nouns or numbers, skipping sentence-initial capitals). Overlap scoring rates a contentless sentence as a success, so this is the counterweight: a context paragraph that names nothing is the abstraction failure.

The abstraction failure also gets a **deterministic gate**, because no prompt can fully hold it: reducing overlap by going abstract *always* works, so the redundancy pass has a monotone incentive toward it. In one live run the caption-aware pass rewrote ten of twelve slots into prose like "a workshop could expose constraints that a laboratory could absorb" — repeating nothing, saying nothing. `_revision_loses_substance()` therefore rejects any revision leaving a slot with fewer anchors than it had **and** below the floor of two, in the same spirit as the verbatim-quote rule: the model proposes, the check disposes. Swapping one specific for another passes; only the slide into generality is refused, and a slot that was already abstract can be rewritten freely since the check compares against its own starting point. Rejections are printed and counted alongside the applied revisions.

`find_interface_references()` reports a third defect: an article slot using a part of the page as a grammatical subject ("The map asks how...", "The chronology follows..."). The prompts ban it outright, but it slips through, and unlike a hollowed revision there is no safe deterministic repair — so it is reported as a signal to recompose, not fixed.

`ComponentNarration` and `StoryArticle` are merged into the single `CompositionResult` (`CompositionResult.merge`) that `apply_composition` consumes, so the call split changed no part of the application path.

**`section_order`** is the top-level list deciding which of the three component sections the reader meets first — e.g. `["map", "network", "timeline"]`. Timeline, then network, then map was the *data model's* order applied to every story, but the three components answer different questions (when, who with whom, where) and stories turn on different ones: a cast held together by a city is introduced by that city. The composer therefore names the order in the same call that writes the section bodies, so each body is written for the position it will occupy. Application is defensive (`normalize_section_order`): names the story has no section for are dropped with a warning, duplicates collapse, and a forgotten section is appended in default order, so a careless list can never cost the reader a component. The stored order therefore always names exactly the sections the page renders — `section_bodies` and `section_headings` are stored in that order too, and the shared image budget is spent in it. `MetaStoryView.svelte` renders the sections through `resolveSectionOrder()` (`src/utils/metaStorySections.js`), which repeats the same normalization for the data it is given; a story composed before the field keeps the historical timeline → network → map sequence. Like the graph and the map clusters the order is technical, so it is copied verbatim into translated files and is not part of the translation payload (fingerprints of existing stories are unaffected).

**`section_bodies`** are the article layer's substance — flexible layout for text and images. Each section (`timeline`, `network`, `map`, `conclusion`) may carry an ordered list of blocks rendered between the section's heading and its interactive component (`MetaStoryBody.svelte`). They are the section's whole prose — sections have no standfirst paragraph under the heading, so the first block opens the section itself. They carry **context**, never a retelling of the component below them: the timeline body owns the wars, laws, markets, and institutions that set the terms (never the events); the network body owns what carried the ties — letters, journals, courts, laboratories, patronage (never who knew whom); the map body owns what concentrated or moved people (never a tour of the stops). **An empty list is a valid answer** — a section with no real context to add gets no body, which is better than filler and much better than abstraction. Block types:

- `{ "type": "paragraph", "text": "…" }` — running prose;
- `{ "type": "image", "image": {…}, "layout": "left"|"right"|"full" }` — an image selected by key (left/right float beside the following text on wide screens via `MetaStoryFigure`'s `layout` prop);
- `{ "type": "quote", "text": "…", "attribution": "…" }` — a quotation that is **verified verbatim** (whitespace/typography-normalized) against the material shown to the model (story brief + Wikipedia excerpts) and dropped otherwise, so a fabricated quote can never enter the data.

**Images** come exclusively from the people's own story slides: the article call is shown a candidate list built from the story's `person_events` (each event's `images` from the person's `life_events.json`) and may only *select by key* (`person_id:event_index:image_index`; a shared budget of at most 6 per story covers the opening and all body images, no reuse). Keys are normalized before lookup — the candidate list renders them as `[img=…]` and the model copies that decoration back often enough to lose real selections. The url/caption/source are copied deterministically, so a hallucinated URL can never enter the data. Each stored image keeps its provenance (`person_id`/`event_index`/`image_index`); `MetaStoryFigure.svelte` renders it with caption and source link. Clicking a figure opens it in the shared `ImageViewer.svelte` lightbox (zoom/pan, caption, source): `MetaStoryView` collects every picture the story renders — the opening image, `section_images`, and all body image blocks, in reading order — into one gallery, so the lightbox pages through the whole story with the arrow keys (its keyboard handler for the timeline steps aside while the lightbox is open). The legacy `section_images` slots are no longer written (body image blocks replace them; a recompose removes leftovers) but remain supported by the UI for stories composed before section bodies.

Application is structural and defensive: chapters/subtopics/map stops are matched by id/key, unknown entries are ignored with warnings, missing entries keep their existing texts, and dates/IDs/coordinates/graph data are never model-editable. Provenance (model, throughline, exclusions with reasons) is stamped into a top-level `composition` block. The whole phase is non-fatal — on any failure the bottom-up texts are kept unchanged.

`lead_in`, `opening`, `section_headings`, `section_bodies` (paragraph/quote texts, attributions, image captions), and the image captions are part of the translation payload, but only when present, so uncomposed stories keep their old fingerprints (and their translations stay "current"). Circle `member_ids`, block types, and layouts are technical and copied verbatim. Image captions prefer the caption from the person's *translated* life events (matched by provenance, like event titles), falling back to the model-translated payload; URLs and sources are never touched. Composing a story changes its English prose, so its translations go stale by fingerprint; the standalone CLI re-translates right away (default `de`, `--skip-translate` to opt out).

Recompose existing stories standalone (updates the registry entry and translations too):

```bash
python scripts/compose_meta_story.py computing_pioneers --verbose
python scripts/compose_meta_story.py --all
python scripts/compose_meta_story.py computing_pioneers --dry-run       # preview only
python scripts/compose_meta_story.py computing_pioneers --no-exclusions # text-only
python scripts/compose_meta_story.py computing_pioneers --skip-redundancy-pass
```

The composer defaults to `gpt-5.6-sol`, independently of the other generation phases. Override it with `OPENAI_COMPOSER_MODEL` or the standalone command's `--model` flag; the full pipeline exposes the same override as `--composer-model`.

### Meta Story Style (Phase 9)

Every meta story has a visual identity of its own, held in `data/meta_story_styles.json` — the same shape as `person_styles.json` (entries nested under a top-level `styles` wrapper, keyed by meta story id) plus one field a person's style has no use for:

```json
{
  "styles": {
    "computing_pioneers": {
      "primary": "#5ED0FF",
      "secondary": "#FFB454",
      "background": "#050B16",
      "background_pattern_svg": "<svg>…</svg>",
      "separator_glyph_svg": "<svg>…</svg>",
      "ornament_svg": "<svg>…</svg>",
      "frame": "square",
      "heading_font": "Space Grotesk",
      "body_font": "IBM Plex Sans"
    }
  }
}
```

A meta story is read as an article, not as a stack of slides, so besides colors and fonts the style carries the marks that **punctuate its prose**:

- `separator_glyph_svg` (32×32) is the text separator: on the corner of the masthead bracket, between the cold open and the description, before every subhead, and in place of the interpunct in the sticky header.
- `ornament_svg` (240×24, horizontally symmetric) is the article's end mark: centered under the last paragraph of the conclusion, and nowhere else. It is deliberately **not** placed in the masthead — a symmetric mark left-aligned under left-aligned text reads as a centered ornament that missed its center, and a second mark closing the title block only competes with the bracket that already closes it.
- `background_pattern_svg` (160×160, tileable, black and white only, like the person patterns) is printed faintly behind the whole page, tinted by `primary` through multiply/overlay and faded toward the bottom of the viewport — it sits under running text, so it must stay calm.

`frame` is the story's **box geometry**: how every panel in it is cut. It is a name from a fixed vocabulary — `square`, `engraved`, `soft`, `arched`, `organic` — not CSS. The concrete values behind each name live in `FRAMES` in `src/utils/metaStoryStyles.js`, which resolves them to four variables the components read:

| variable | what it cuts |
| --- | --- |
| `--ms-frame-radius` | panels: narration cards, tooltips, the chapter header, figures, the cast cards |
| `--ms-frame-radius-sm` | chips inside them: the year badge, the gap label, an event row's hover slab |
| `--ms-frame-border-width` / `--ms-frame-border-style` | the frame's rule — `engraved` is a 3px `double`, the rest a 1px `solid` |
| `--ms-frame-rule-width` | hairlines that are rules rather than frames: the subhead underline, the pulled quote's bar (`double` needs 3px before it can draw two lines) |

The geometry is only half of a frame. The line work and the ornament that make it *that* frame live in `src/meta-frames.css`, a global stylesheet keyed on the name the story chose (`<div class="meta-story-view" data-ms-frame="engraved">`), and a panel opts in by carrying the `ms-frame` class: `square` gets register marks at its four corners, `engraved` an inner plate line with the story's glyph on each corner, `arched` an archivolt and a keystone glyph on the crown, `organic` a contour curving wider than the panel, `soft` one faint ring. It is global rather than scoped because one frame reaches panels in four components — the narration cards over the graph and the map, the timeline's chapter header, the closing cast cards (`PersonCard` takes a `class` like `CloseButton` does) — and a copy per component would drift. Components keep what is theirs: surface, border color, padding, shadow.

Two rules for adding a variant, both asserted by `tests/test_meta_story_styles.py`: decorate with `::before`/`::after` only and always `pointer-events: none`, because the panels carry links and a decoration that swallows a click is a bug that looks like a design; and ornament only from what the story already owns — `var(--ms-glyph)` and `var(--ms-accent)` — since a frame that introduces a shape of its own would be a sixth mark nobody chose. Transient popups (the node tooltip, the event tooltip) deliberately keep the plain geometry: cornerwork on something that flickers reads as noise.

A name rather than raw CSS for two reasons: one frame has to work on a full-bleed card, a floating header and a caption badge at once, so the sizes per role are a design decision and not the model's; and nothing generated ever reaches a `style` attribute. Circles and pills that mark a position instead of enclosing content — event dots, the year pill, the pager buttons — keep their own geometry; they are not frames.

Both lists have to agree: the generator's `FRAME_CHOICES` names what may be chosen, `FRAMES` in the app defines what each name looks like, and `tests/test_meta_story_styles.py` fails when one has a name the other lacks.

The two marks are drawn in `primary` only; the generator replaces whatever fill or stroke the model returned, and strips opacity attributes so the stylesheet controls how loud they are.

The masthead is composed rather than decorated: an accent bracket (a hairline along the top fading out to the right, a spine down the left fading out below the dateline) encloses the title block over a panel of the accent at a few percent, and the glyph sits on the bracket's corner. The arms are open, never a closed frame: a box would read as a card lifted off the page. Nothing else is added — the bracket is the whole apparatus. That composition lives in `MetaStoryView.svelte`'s `.masthead` rules; `MetaStoryOrnament.svelte` only carries the marks that punctuate prose further down.

The components inherit the same identity. The timeline, network, and map are full-bleed boxes that overflow the text column, and their chrome — the surface the timeline sits on, the frame of the chapter header, the year axis and its ticks, the active-chapter glow, the narration cards over the graph and the map, the tooltips, the figure frames, and the pager buttons — reads `rgba(var(--ms-page-bg-rgb), …)` and `color-mix(… var(--ms-accent) …)` instead of the slate and sky it used to hard-code. Every heading inside them opens with the story's glyph, the same mark the article's subheads carry: the narration cards over the graph and the map, the chapter header floating over the timeline, and each of the timeline's theme titles. Two rules for editing them:

- Every replacement keeps the old value as the fallback, so a story without a style renders exactly as before.
- Colors that stand for a **person** — `--person-color`, `--mention-color`, `--person-primary-rgb`, `--item-primary-rgb`, the portrait rings, the timeline lanes — are never folded into the story's accent. The story colors its frame; the people inside it keep their own.

The network's focused ties are the one case read in JavaScript (`metaStoryStyle(metaStoryId)?.primary`): the stroke is an SVG presentation attribute, and those do not resolve `var()`.

The style is language-independent — one entry serves every translation — and is resolved in `src/utils/metaStoryStyles.js`, which normalizes the entry (camelCase, SVGs as data URLs) and emits the CSS variables `MetaStoryView.svelte` applies to the whole article. `--heading-font` and `--body-font` are the variables the timeline, network, and map already read, so setting them on the story container styles the components too. From `primary` the view derives the four editorial roles (`--ms-accent`, `--ms-ink`, `--ms-body`, `--ms-muted`) with `color-mix`, and `MetaStoryOrnament.svelte` renders the marks (`variant="rule" | "divider" | "closing"`). A story **without** an entry gets no variables and no ornaments: the article keeps the neutral editorial palette its stylesheet declares as fallbacks.

Generated by Phase 9 of `generate_meta_story.py` (skip with `--skip-style`, non-fatal), or standalone:

```bash
python scripts/generate_meta_story_style.py computing_pioneers --verbose
python scripts/generate_meta_story_style.py computing_pioneers --dry-run
```

`tests/test_meta_story_styles.py` checks the registry against the app: colors are `#RRGGBB`, fonts are among those the `index.html` font link actually loads, the marks are single-color SVG, and the pattern uses only black and white.

### Meta Story People Cards ("The People" section)

A meta story closes with a card grid of **all the people the story is built from** — the mirror of the related-people cards at the end of an individual story (`ConclusionSlide.svelte`). It is the last section of `MetaStoryView.svelte`, after the conclusion, and is derived **purely in the UI**: `meta_story.person_ids` resolved against the persons registry (people missing from the registry are skipped — the card exists to open their story), ordered by birth year. Each card is the shared `PersonCard.svelte` (portrait, name, lifespan, roles, styled in the person's own colors and fonts) and links to `#/{lang}/story/{id}?from_meta={story_id}`, saving the meta story scroll position first so the story's close button returns the reader to the cards.

There is nothing to generate: no data, translation payload, or composer field is involved. The heading is the localized UI label `meta_story.people_heading` — unlike the other sections there is no story-specific `section_headings` counterpart, and like them the section carries no text under its heading.

`PersonCard.svelte` renders the card: it takes `person` (registry entry), `personStyle` (normalized style — camelCase fonts), `href`, an optional localized `ariaLabel`, `onNavigate` (runs before the link is followed, e.g. to remember scroll) and `onClick` (replaces navigation). Its surface tones read from `--card-bg`/`--card-bg-hover`/`--card-border`/ `--card-border-hover`, which the meta story grid overrides because the page background is the same near-black as the card's default. `ConclusionSlide.svelte` still carries its own equivalent copy of the card markup (it predates the component) — keep the two in sync when changing the card's look.
