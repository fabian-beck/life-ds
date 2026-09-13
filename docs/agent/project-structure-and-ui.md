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
│       ├── DeploymentPreviewToggle.svelte # Dev only: preview the deployed view without hidden entries
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
│   └── evaluation/          # The user-evaluation deployment: participant gate, logger, analysis page
│   └── utils/
│       ├── story/           # One module per cluster of story helpers: dates,
│       │                    # geo, color, eventIcons, images, personMatching,
│       │                    # prose, eventDepth. Import the module, not a barrel.
│       ├── metaStoryStyles.js # Resolves a meta story's style to CSS variables
│       ├── metaStorySections.js # Resolves the composed order of a meta story's sections
│       ├── personNames.js    # Finds person names in prose (highlighting)
│       └── visibility.js     # Entries marked hidden: filter, and carry the English flag over
│   └── stores/
│       └── visibility.js     # Whether hidden entries show: never in a build, dev toggle otherwise
├── data/
│   ├── persons.json         # Master person registry (entries may carry hidden: true)
│   ├── person_styles.json   # Visual styles registry
│   ├── meta_story_styles.json # Per-meta-story colors, fonts, SVG marks
│   └── people/
│       └── {person_id}/
│           ├── life_events.json
│           ├── ego_network.json
│           └── _cache/       # Wikipedia materials
├── scripts/                 # Python data generators
│   ├── generate_person.py           # Full person workflow
│   ├── generate_person_events.py    # Life events: the command line over events/pipeline.py
│   ├── events/                      # The life event pipeline: pipeline, schemas, event_classes, normalize, images/, prompts/
│   ├── generate_person_style.py     # Visual style only
│   ├── generate_person_network.py   # Ego network only
│   ├── generate_person_portrait.py  # Stylized portrait generation
│   ├── generate_all_portraits.py    # Batch portrait generation
│   ├── generate_chapter_illustrations.py # Abstract chapter slide art (concepts + images)
│   ├── icon_categories.py           # MDI icon mappings + icon normalization
│   ├── generate_event_backgrounds.py # Depth-layer background reports for the deep events, their citations and illustrations
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
│   ├── cache_wikipedia_materials.py # Cache Wikipedia data
│   ├── clear_caches.py              # Clear old cached data
│   ├── remove_person.py             # Delete person
│   ├── set_hidden.py                # Hide a person or meta story from the deployed site, or show it again
│   └── config.py                    # Shared config
└── public/                  # Static assets
```

## Svelte 5 Modes

The application runs on Svelte 5 and 29 of its 30 components are in legacy mode: props are `export let` and derived values are `$:`. The exception is `PrivacyModal.svelte`, written with runes under the displacement rule below. That is a supported configuration rather than an oversight, and it is deliberately not a migration waiting to be scheduled. The components carrying most of the reactivity are the ones a conversion would have to start with—`StoryView.svelte` holds 47 reactive blocks and `MetaStoryTimeline.svelte` 31—and converting them means rewriting the hand-guarded state machines inside them, which is where the deterministic suite is thinnest: reactivity races here have historically surfaced as flaky interface tests rather than as reproducible failures.

The rule that follows is to migrate by displacement rather than by project. A new component is written with runes, and so is a component extracted out of an existing one, because the extraction is already a rewrite and a fresh component carries no legacy state machine to preserve. A component that is merely edited stays as it is. Mixing the two modes across the application is supported; mixing them inside one component is not, so a file is converted whole or not at all.

Three legacy APIs are marked deprecated in the installed Svelte and must not gain new uses: `createEventDispatcher` (use callback props), `beforeUpdate` (use `$effect.pre`), and `afterUpdate` (use `$effect`). Two of them survive, once each—`createEventDispatcher` in `Timeline.svelte` and `afterUpdate` in `NetworkModal.svelte`. The second is the harder constraint rather than the smaller one: `afterUpdate` throws `lifecycle_legacy_only` outside legacy mode, so `NetworkModal.svelte` cannot move to runes at all while it is there. Removing it is the one piece of migration worth doing on its own, instead of waiting for the component to be opened for some other reason.

`eslint.config.js` turns off `svelte/prefer-svelte-reactivity` and `svelte/infinite-reactive-loop` for exactly this reason, and its comments name the guarded state machines the second rule would otherwise report. Both belong back on once the components they cover are on runes; until then a report from either is noise rather than a finding.

## Routing

Uses `svelte-spa-router` with URL-based navigation:

- `/` - Landing page (person grid)
- `/story/{person_id}` - Person's story (starts at event 0)
- `/story/{person_id}/{event_index}` - Specific event slide

**Routing behavior**: Slide changes use `history.replaceState` (no history spam), but navigating between people uses `push` (back button works as expected).

## Chapter Slides

A chapter slide is a rest between phases of a life: a headline, a date and age range, a place, and the people the chapter belongs to. That is little for a full screen, and the slide read as a gap rather than as a pause. It now opens with an abstract illustration of what the chapter is about — generated by `scripts/generate_chapter_illustrations.py`, stored per chapter as `illustration`, and drawn in the same light-on-black style the portraits are transferred toward.

It is printed the way the portrait on the overview slide is printed, and for the same reason: masked to nothing at its edges with a radial gradient and taken down in opacity, so the story's background and pattern read through it and no rectangle is left standing on the slide. Two details are load-bearing. The mask must reach zero before 70.7% of its radius — where a `farthest-corner` circle meets the edge of a square image — or the black ground shows as four straight lines. And the image is decorative: `alt=""`, `aria-hidden`, no caption. It depicts a metaphor rather than an event, so announcing it to a screen reader would describe something that never happened, and a caption would make the slide look like it is exhibiting a picture. A chapter with no illustration keeps the layout it always had, including the taller run-up above the headline.

## Slides Off Screen

The whole story is in the DOM at once: one scroll-snapped strip, one section per slide, nothing mounted or unmounted as the reader moves. That is what leaves the sideways gesture to the browser, and it is also what made the transition stutter. A slide is not cheap to paint — two full-screen pattern layers of its own, blended, over a background of its own, under whatever the event brings — and a life's worth of them sat in the compositor's layer list for every frame of a swipe. Measured on a throttled phone, a third of the frames during a slide change ran over 32 ms, and the time was going to the layer list rather than to script.

`content-visibility: auto` on `.slide` is the obvious answer and does not work here. It was shipped and reverted: on a slide carrying an event panel, Chromium painted the top of the slide and left everything below it transparent, so the family tree ended mid-portrait and the description was simply gone, with the story map showing through where it belonged. Layout was correct and byte-identical either way — the content box measured the same with the property on and off — so nothing in the application, and no measurement in a test, could see it. Only a screenshot could. `contain-intrinsic-size` did not help; restricting the property to `.slide[inert]`, so the slide the reader is on never carries it, did paint correctly, and is where a second attempt should start.

The other cost a slide change carries is a synchronous layout, taken in the frame the change has just dirtied the strip in: reading the active slide's `scrollHeight` to see how far into its depth layer the reader is. Only a slide that has a depth layer has anything to report, and four slides in five have none, so `slideHasDepth` decides whether the measurement is taken at all. It is the one place the markup and the measurement have to agree on which slides go deeper, so both ask it.

## The Depth Layer

A person's story moves sideways: one slide per event, horizontally scroll-snapped. On a life's landmarks the slide also moves downward, and the two axes mean different things — sideways is *later*, downward is *further into the same event*.

A deep slide is built as two screens inside the one scroll container:

- `.slide-fold` holds the event exactly as a slide without depth holds it, and is declared exactly one screen tall (`height: calc(100% + var(--slide-bottom-base))`), so the layer below starts out of sight. The definite height is what lets `.slide-reserve` shrink here the way it does on every other slide. When an event's own text cannot fit a screen, `watchContentFit` marks the slide `fold-overrun` and the fold grows instead of spilling over the layer below.
- `EventDepth.svelte` renders the layer: the written background report under its own section headings, its illustrations dealt out between the paragraphs with their captions and credits, and under the last paragraph a row of chips for the people the report names. Nothing that has an affordance of its own is repeated here. The annotated terms are marked in the description, where a tap opens the same explanation and the same link. The event's `sources` stay data: they are re-decided when the report is written, but the layer does not print them, since a line of links to encyclopedia articles is a footnote where the reader wanted a page. The people are the one thing the layer adds an affordance for. `parseBackgroundBlocks` runs the same matcher the description runs, against the whole ego network rather than the event's own cast, and marks every name the network knows as a `.person-mention`; `mentionedPeople` gathers the people it marked, once each in order of first mention, and the layer sets them as the same `PersonChip` the slide uses, with its tooltip, its strength border, and its way into the network. The slide's chips are the event's own cast; a report ranging over a decade names people the event itself never did, and those are the ones a reader can only open here. The chips share `visiblePersonInfo` and `togglePersonInfo` with the slide, keyed `<eventIndex>-depth-<n>`, so opening one closes whatever popup is open above.

  The register is prose, deliberately: no card, no rules, no icons, a narrower measure than the slide's, and no line per record. Once everything with an affordance of its own had been taken out of the layer, the composed text that remained was one sentence naming the place — which read as an oddity under a report — so nothing is composed here any more. The text is the report and only the report, and `getBackgroundImages` in `src/utils/story/images.js` returns only the pictures searched for the report. The event's own picture is deliberately not a fallback: it is a screen up, the reader has just scrolled past it, and reprinting it under the report is what made the layer look like a second copy of the slide. The rule is held in the application as well as at generation, and on the file rather than the URL, because Commons serves one photograph at any width and `640px-Hut_8.jpg` beside `960px-Hut_8.jpg` is the same picture printed twice.

  Those pictures are part of the story's gallery rather than a lightbox of their own: `collectStoryImages` puts each event's illustrations directly after the event's own picture, so a reader who enlarges one from under the fold pages through the same sequence as one who enlarged it from a slide, and lands on the right event when they jump.

  What leads the layer is not composed at all. `scripts/generate_event_backgrounds.py` writes a `background` report per deep event — the situation it sat in, why it mattered, what followed — and `EventDepth` renders its blocks: a `## ` line becomes a section heading, everything else a paragraph, with the illustrations spaced across them rather than banked under the first few. One or two headings in a report of this length is the instruction, never above the opening paragraph, and a report that runs as a single argument takes none — a heading over every paragraph turns a page of prose into a form. The prompt's operative rules are negative, because a summarizer pointed at an event it has just been shown will otherwise say it again in other words: the description is handed over as the thing to go beyond, and `build_background_avoidance` adds everything else the reader already has — the annotations, verbatim, as the popups under that same description; the people, as the chips that introduce them; the whole rest of the story as an outline, every other slide the reader can swipe to; the person's summary; and what the event cites today, to be kept or dropped on its merits. A passage written without being shown the annotations repeats them, which is the one repetition a reader is guaranteed to notice, since the popup is directly above. The outline is the whole story and not just the two neighbouring events, because a report shown only its neighbours wanders into whatever is a slide or two further along: Turing's death opened on the Manchester laboratory and spent two paragraphs on the morphogenesis paper, which is its own slide two events back. The report is 350-550 words in 3-5 paragraphs, built like a report — the situation, the specifics, one thing at length, what came of it — and told that a sentence which could be written about any event of its kind is a wasted sentence, and that a reader who scrolled down here has asked for depth. It is only as good as its material: `RELATED_ARTICLE_CHARS` and `RELATED_ARTICLE_COUNT` are what the call gets to read, and the reports written before the Wikipedia cache existed for a person were written from the model's own memory, which is why they were thin.

  The step runs inside `generate_person.py` after review — so the report is grounded in the reviewed text — and before translation, so the translator sees it; standalone, `python scripts/generate_event_backgrounds.py <person_id>` fills exactly the same events. It computes the story's own deep-event selection rather than taking a list, presents a classified event's panel fields as ground the report must not repeat, and re-decides the event's `sources` in the same call, because several were wrong: the old prompt said to pick from the related articles supplied, so an event none of them documented got the nearest one anyway — Morcom's death, in 1930, cited the article on Turing's 1936 proof. Only URLs the call was shown are accepted, so a plausible invented citation cannot land, and the URLs are synced to the translated copies since a URL is not prose. The translated copies get their reports from `translate_person.py`, which sends the report taken apart — paragraphs as one array, headings as another — and reassembles it on merge.

  The illustrations are searched and then read. A Commons keyword search is a keyword search: "On Computable Numbers manuscript" returned a 16th-century Mexican codex, "Christopher Morcom" returned a steam engine built by Belliss & Morcom, and "Banbury sheets" returned an ordnance map of the town of Banbury. So `fetch_background_images` shows every candidate to a critic on the larger model — filename as well as caption, because a Commons caption is often the uploader's paperwork — which keeps at most three, each of a different thing, and is told that three is a ceiling and not a target. One picture per query is enforced in code. It lives in `generate_event_backgrounds.py` and runs in the same pass as the report, once the event's own picture is already in the dataset and can therefore be excluded: an illustration the reader scrolled past a screen ago illustrates nothing.

Whether an event opens a layer at all is two conditions. `selectDeepEventIndexes` (`src/utils/story/eventDepth.js`) names the events a report is worth writing for — `scripts/utils/event_depth.py` is the generation side's port of it, and the two must be kept in sync; `hasBackgroundReport` then requires that the report actually exist, because the layer is the report and nothing else. A life whose reports are not written yet simply offers no way down, rather than an invitation to an empty screen — the corpus fills in one life at a time. The first condition is derived from `getEventWeight`. The weight is generated: Phase 1 proposes a life's events and weighs them against each other in the same call, which is the only step that sees a life whole — and how much of a life an event turns on is a comparison, not a property of the event. A dataset written before the field existed is outdated data — flagged in `data/outdated.md` and regenerated, never repaired — and until then `getEventWeight` still derives a fallback score from the traces an important event leaves behind — a classification, a milestone icon, images, annotations, people, length — which is a weaker thing: it reads the documentation rather than the life, and it ranked Turing's Princeton doctorate above the paper that founded computer science. Selection is per chapter — each chapter offers its heaviest event and no more — which spreads the deep slides across the story instead of clustering them where a life happens to be best documented. An event whose depth layer would be nearly empty is passed over however heavy it scores. Across the current corpus this marks roughly a quarter to a third of a life's events. `tests/eventWeight.spec.js` covers the rules; the reading behavior is reviewed by exploration rather than by a script.

The invitation down is `.depth-affordance`, a small chip held to the right edge in the gap the slide already keeps clear of the timeline, with two chevrons that beckon (and hold still under `prefers-reduced-motion`). It is on the right and not centered because centered it stood in the middle of the map. It yields to an open popup — an annotation, a date note, a person — which is drawn from the foot of the description and would otherwise be covered by it; `popupOpen` in `StoryView` takes it to zero opacity and out of the tab order for as long as one is showing. Otherwise it sits directly under the event's last line — anywhere lower and it stands over the map, which is the one thing on the slide that has to stay legible under it. That means it is a flex item in the fold rather than an absolutely placed one, and the event's auto margins are set so the event and the chip are centered as one block (`margin: auto auto 0` on `.content`, `margin-top: auto` on the reserve) with nothing opening up between them — the same flexible placement an event without depth gets from its own auto margins, centered when short and rising toward the top as the text grows. It fades as the reader descends. So does everything else that belongs to the event rather than to the page of running text that replaces it: `StoryView` tracks the active deep slide's scroll as `depthProgress`, passes it to `StoryMap`, which drives `--map-depth-opacity`, and past a third of the way down marks itself `reading-depth`, which takes the timeline, its arrows and the chapter pill out. They are hidden rather than merely faded, because the timeline's container passes clicks through but its buttons take them back, and a transparent arrow answering a tap in the middle of a paragraph is worse than a visible one. Scrolling back up brings all of it with the event. Down and up arrows drive the second axis on a deep slide before carrying the reader on to the next one, and a wheel flick that opens the depth layer is not allowed to continue into the next slide in the same gesture.

Two axes in one container means every gesture has to be assigned to one of them, and no real gesture is only vertical: a thumb and a trackpad both wander sideways while travelling down, and the story used to read that drift as a swipe and carry the reader off the event they were opening. `createAxisLock` (`src/utils/gestureAxis.js`) decides the axis from where the whole gesture has been rather than from its latest moment, says nothing until 12px of it has arrived, and holds the answer until the gesture ends — a pause for a wheel, a finger lifting for a drag. Ties and near-ties go to the vertical (`AXIS_DOMINANCE`), because leaving a slide the reader meant to stay on costs more than a swipe that has to be repeated. `.slides` takes `touch-action: pan-y pinch-zoom` and `.slide` takes `overscroll-behavior: contain`, so the sideways part of a drag or a wheel down cannot reach the story behind the slide on its own; a mandatory-snap strip turns even a few pixels of that into a whole slide. `tests/gestureAxis.spec.js` covers the rule; the gestures themselves are checked by exploration on a real page.

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

Fonts are self-hosted. `src/fonts.css` imports the seventeen families from `@fontsource` packages and is pulled in by `src/main.js`, so the faces are bundled, fingerprinted, and served from our own origin. Nothing is fetched from a third party at runtime.

They used to come from `fonts.googleapis.com` through a render-blocking `<link>` in `index.html`. That gated the first paint on an external host: with the host reachable-but-hanging, first contentful paint measured 12,848 ms instead of 112 ms. `index.html` must stay free of third-party stylesheet links.

Two constraints when editing `src/fonts.css`:

- Import `latin` **and** `latin-ext` for every cut. The content needs Latin Extended (`ł` alone appears 110 times, e.g. Skłodowska).
- Keep the family list in step with `HEADING_FONT_CHOICES` / `BODY_FONT_CHOICES` in `scripts/generate_person_style.py`. A family the generator can pick but that is not imported renders in the fallback font.

`tests/test_font_coverage.py` enforces both, in both directions.

Because two heading faces ship a single weight by design (Archivo Black, DM Serif Display) while headings ask for 600-700, `app.css` sets `font-synthesis-weight: none` so the browser uses the real face instead of smearing a synthetic bold over it. `font-synthesis-style` is deliberately left alone — the sans body faces have no true italic and rely on synthetic oblique.
