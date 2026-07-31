# Development Reference

> Detailed reference for coding agents. Keep the root `AGENTS.md` concise and update this document when the related project behavior changes.

## Development Workflow

### Common Commands

```bash
npm install          # Install dependencies
npm run dev          # Start dev server (localhost:5173/life-ds/)
npm run build        # Production build to dist/
npm run preview      # Preview production build
npm run test:core    # Minimal UI, logic, and Python regression safeguards
```

See [Testing strategy](../testing-strategy.md) for the boundary between the
small deterministic suite and the repository's AI exploratory testing skill.

**Note**: The dev server is always running in this environment. No need to start it manually.

### Claude Code on the web

Web sessions run in a fresh container that has the repository cloned and
nothing installed, so `.claude/hooks/session-start.sh` runs before the session
starts and prepares it. The hook is a no-op anywhere else—it exits immediately
unless `CLAUDE_CODE_REMOTE` is set—so local machines keep using their own
`.venv`. It does three things:

- `npm install`.
- Installs `requirements.txt` and `requirements-dev.txt` into the container's
  Python, and puts that interpreter's scripts first on `PATH`. The image also
  ships `black`, `flake8`, `mypy` and `pytest` as standalone tools that cannot
  see the project's packages; without the `PATH` change `mypy scripts/` fails
  on the pydantic plugin.
- Points the Playwright browser revision the installed client expects at the
  Chromium build the image actually carries. Browser downloads are blocked in
  the container, and without the link `npm run test:interface` cannot launch.

### Deployment

Hosted on **GitHub Pages** as a project page under
`https://<owner>.github.io/life-ds/`, published **on demand only**—pushing or
merging to `main` does not publish. `.github/workflows/deploy-pages.yml` has a
single `workflow_dispatch` trigger; a maintainer runs it from the Actions tab.
Pages' repository source must be set to "GitHub Actions".

Because the site lives in a subdirectory, `vite.config.js` sets
`base: "/life-ds/"` in dev and build alike, and the build writes a `404.html`
copy of `index.html` so path-style entry URLs survive on a host without
rewrite rules.

`technicalReportPlugin` publishes the generated technical report alongside the
app: the build copies `docs/report/index.html` to `dist/report/index.html`, and
the dev server answers `/life-ds/report/` with the same file ahead of the SPA
fallback. The landing page and the AI-generated modal link there through
`assetUrl("/report/")`, and `tests/interface.spec.js` follows that link.

**Consequence for application code**: every site-absolute path that becomes a
URL—portrait paths from the generated data, assets in `public/`—must go through
`assetUrl()` in `src/utils/assetUrl.js`. A raw `"/portraits/…"` string in
markup works at a domain root and 404s on Pages. The data files and the Python
generators keep writing site-absolute paths; the prefixing happens at render
time only.

`VITE_BASE_PATH=/` builds for a host that serves from the domain root.

See README "Deployment" for the setup steps and the platform limits.

### Adding a New Person

1. Run `python scripts/generate_person.py "Person Name"`
2. Review generated files in `data/people/person_id/`
3. Check `data/persons.json` and `data/person_styles.json` were updated
4. Test in browser at `/life-ds/#/en/story/person_id`
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

### Person Name Highlighting

Wherever a person is named in running text—story slide descriptions, meta
story prose, the network and map narration cards—the name is emphasized
(`.person-mention`, and a link into that person's story in meta story prose).
**One matcher does this for all of them**: `findPersonMentions()` /
`segmentPersonMentions()` in `src/utils/personNames.js`. Do not write a second
one; the four call sites previously each had their own copy and each was wrong
in its own way.

It works on **name runs**—stretches of capitalized tokens joined across
spaces, hyphens, particles ("von", "of") and the dots of initials—rather than
on `\bName\b` regexes, which cannot handle any of the things this data is full
of: `\b` is ASCII-only (so it never matched "Gaudí"), German genitives glue an
"s" to the name ("Zuses Software"), and a bare surname regex cannot tell
"Adams’s letters" from "John Adams". Matching a whole run makes the surrounding
tokens available as evidence, which is what lets short forms be matched safely.
Every occurrence is highlighted, not just the first.

Precision comes from refusing the ambiguous cases (a wrong link is worse than a
missing highlight): a bare surname behind another capitalized token is rejected
unless that token opens a sentence or is a title ("General Washington" yes,
"John Adams" no); a given name alone only counts for one-name figures or
distinctive long names, never "Alan" or "John"; regnal numerals must match
("Otto III" is not Otto Wagner); and when two people fit a span equally well it
is left plain. `tests/personNames.spec.js` pins these rules with cases drawn
from the real stories—run it when touching the matcher.

Two things feed the matcher besides the text:

- **Aliases.** Registry names are translated but graph/map data is not, so a
  German story prints "Heinrich II." while its network node still says
  "Henry II". `MetaStoryView` passes both (`storyPeople[].aliases`, and
  `personAliases` down to `MetaStoryNetwork`/`MetaStoryMap`). Without this a
  translated story highlights nothing.
- **The story subject.** `parseDescriptionSegments()` takes the ego's name so
  a bare "Hamilton" in Alexander Hamilton's story comes out ambiguous—and
  therefore plain—instead of being handed to his father, while
  "James Hamilton" still resolves to the father.

`getRelevantPeople()` uses the same matcher to decide which people an event
mentions, so the chips offered and the names emphasized cannot disagree.

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
converted. Adopting runes is a deliberate, separate decision—do not introduce
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
  (6.3 MB) and a wildcard import defeats tree-shaking—this once put 2.5 MB
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
  (`mdi-lecture` instead of `mdi-school-outline`). Unrecognized `mdi-` names
  are passed through, not defaulted: MDI has ~7,400 icons and
  `ICON_CATEGORIES` names 68, so an unknown name is usually a real icon
  outside the vocabulary (`mdi-airplane`), and defaulting it would replace a
  working icon with a generic calendar.
- The `virtual:mdi-icon-map` plugin (`vite.config.js`) builds the runtime
  lookup from the union of `icon_categories.py` and the icons actually present
  in `data/people`, since generated data drifts from the vocabulary. It
  validates every name against real `@mdi/js` exports and **warns at build
  time** about any that do not exist—that warning is the signal that data
  needs repair.

Repair existing data with `python scripts/fix_event_icons.py --dry-run` (then
without the flag). It rewrites icon values in place and touches nothing else.
`data/people/**/*.json` is prettier-ignored and formatted as it was generated,
so never rewrite these files with `json.dump`—it would reflow every line of
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

## Technical Report

`docs/report/index.html` is a standalone, interactive technical report on the
whole system: what it is for, how the data is modeled, both generation pipelines
step by step—the model and reasoning effort each uses, the prompt it sends, the
structured output it asks for, and, when a run has been recorded, the real
prompts, responses, timings and token counts—plus the application, localization
and testing.

It has two halves that never mix. The prose is authored by hand in
`docs/report/report.md`; everything factual is computed at build time. See
[Authoring the Report](#authoring-the-report) below before editing either.

The page is styled as an academic report: black on white, square corners, and
color reserved for the step kind alone. Both pipelines are drawn, as sections
4.1 and 4.2 rather than as tabs, each with its own filters, search and selection;
the step drawer is shared between them.

The chart is a **layered DAG, not a sequence**. An arrow means one step consumes
what another produced (`Step.depends_on` in `spec.py`, with a label for the data
that travels along it); a step's layer is the longest such chain reaching it, so
steps drawn side by side are genuinely independent—the meta story's map branch
and network branch really do run without seeing each other. Files a step writes
are printed inside its node; a file the pipeline only reads becomes a source
node, which is how the meta chart shows that it consumes person-pipeline output.
Orchestrator `main()` functions are deliberately not steps: they impose an order
without creating a dependency, and drawing them made a fork look like a chain.

The vertical axis is the dependency graph; the horizontal axis carries no graph
meaning, so `spec.GROUPS` spends it on concerns. A group names steps that do one
job across several layers—planning the image searches, running them, matching
the results—and the layout aligns them and draws a labeled band behind them,
so the strand can be read straight down instead of being tracked as it drifts
sideways. Grouping is presentation only: it never moves a layer.

Alignment holds only where a group is **continuous**. The layers a group occupies
are cut into runs of consecutive layers, and each run is aligned and banded on
its own, so the portrait—four layers below the last image step, with unrelated
work in between—is placed by the graph rather than dragged into the imagery
strand under a band stretched over the gap. A run of one step is not banded at
all, which is also what happens to a group most of whose steps a filter has
hidden.

Horizontal placement runs in two stages and uses **continuous positions, not a
column grid**:

1. Blocks—one per group run, one per ungrouped node—are placed as rigid
   rectangles with a single x across every layer they cross. A leftmost packing
   gives a feasible start; blocks are then relaxed toward the mean position of
   their graph neighbors, each clamped to the room its neighbors in every layer
   it occupies actually leave. Feasibility is therefore invariant, and sparse
   layers center themselves under the layers they feed.
2. Nodes are centered inside their block, which is what lines a group up: a run
   with one step per layer puts every step at the same x.

Adding a group is a `spec.py` edit; `--check` rejects one that names an unknown
step, claims a step twice, or mixes the two pipelines.

```bash
python scripts/generate_report.py            # rebuild the page
python scripts/generate_report.py --check    # drift check only, no API key needed
python scripts/generate_report.py --skip-ai  # rebuild without calling the API
```

It is built from these layers, in `scripts/pipeline_docs/`:

| Layer | File | What it contributes |
| --- | --- | --- |
| Static analysis | `introspect.py` | Parses `scripts/*.py` with `ast`: model call sites, resolved models and reasoning efforts, Pydantic output schemas, prompt templates, CLI flags. Never imports the generators, so it needs no API key. |
| Pipeline shape | `spec.py` | Which steps exist, what data flows between them (`depends_on`), which files they read and write, and which steps form one concern (`GROUPS`). Each step points at a real function. |
| Measurements | `facts.py` | Repository-scale numbers the prose cites—corpus size, component counts, test counts—each with the place it was measured. |
| Authored prose | `report.py` | Compiles `docs/report/report.md`: sections and numbering, `{{ fact }}` citations, `[[part]]` figure references, `::: component` mount points, callouts. |
| Teaser figure | `teaser.py` | The scene of Figure 1—its parts, their boxes, labels, sentences and arrows—declared once and drawn by `app.js`. Part ids are what the prose points at. |
| Explanations | `summarize.py` | AI-written per-step documentation, cached in `docs/report/summaries.json` against a fingerprint of that step's source, prompt and schema. Only changed steps are re-summarized. |
| Recorded runs | `capture.py` | Patches the OpenAI SDK during a real run and records each call. Optional. |
| Screenshots | `screenshots.py` | Reads the `::: screenshot` blocks, pairs each with the picture on disk, embeds it as a data URI and decides whether it is stale. Capture itself is `scripts/capture_report_screenshots.mjs` (Playwright). |

`spec.py` and `report.md` are the only hand-maintained inputs.

### Keeping It Honest

`--check` fails when `spec.py` no longer matches the source: a documented step
whose function was renamed, a dead prompt symbol, a dependency edge pointing at
a step that does not exist, a cycle in the graph, or—most importantly—a
model call site that **no step claims**. Adding a phase without documenting it
is therefore an error rather than a silent omission.

It also fails when the authored report no longer resolves: an unknown
`{{ fact }}` citation, an unknown `[[part]]` reference into the teaser figure, a
figure whose geometry is inconsistent, an unknown or misconfigured
`::: component`, a lane or script that no longer exists, a pipeline that no
chart draws, or a declared screenshot with no picture on disk. A fact that is
measured but never cited, a figure part no phrase references, and a screenshot
whose declaration moved since it was taken are warnings rather than errors.

The check needs no API key, so it is safe to run anywhere. It is deliberately
**not** part of `npm run validate`; run it after changing any generation script
or the report source.

### Recording a Run

```bash
python scripts/record_pipeline_run.py person "Ada Lovelace"
python scripts/record_pipeline_run.py meta "Computing Pioneers"
```

This performs a **real generation run**—it calls the API and rewrites that
subject's data files exactly as a normal regeneration would. Records land in
`docs/report/runs/*.json` and are picked up by the next report build. Prompts
and responses are truncated to 4000 characters by default (`--truncate 0` keeps
everything, but a Phase 1 prompt carries whole Wikipedia articles).

Figure and table numbering follows what actually renders: with no run recorded,
the run blocks consume no caption numbers, so the sequence has no gaps.

### Authoring the Report

`docs/report/report.md` holds the prose and nothing else. **No number, model
name or file count belongs in it**—those are cited, so they cannot go stale.

| Syntax | Meaning |
| --- | --- |
| `## Heading`, `### Heading` | Section and subsection. Numbers, ids, the contents and the sidebar are all derived from document order. Skipping a level is a build error. |
| `{{ some.fact }}` | A measurement from `facts.py`, rendered with its source as a tooltip. An unknown key fails the build. |
| `[[part\|phrase]]`, `[[part]]` | A phrase that names a part of the teaser figure (`teaser.PARTS`). An unknown id fails the build; a part no phrase names is a warning. |
| `::: component key=value` … `:::` | A computed block. The block's body is authored prose kept above the computed part. |
| `::: note` / `aside` / `decision` / `limitation` | An authored callout. Holds prose only. |
| `^[an explanation]` | An inline note. Brackets nest, `\^[` escapes the syntax, and the body is collapsed to one line, so a note is inline-level by construction. |
| `::: toc` | The table of contents. |

**Notes are authored once and read two ways.** The compiler emits the printed
form—a numbered list closing the section that raised the note, with every marker
a real link into it—and `app.js` then withdraws that list on screen and shows
the same text in a popover on the marker. The popover copies the list item it
points at rather than carrying its own copy, so the two renderings cannot
disagree, and with JavaScript off or on paper the notes are still there. A note
belongs to a `##` section, decided from its position in the rendered page rather
than from the order the compiler collected it in.

Use a note for something a specialist reader may want and the sentence cannot
carry—a mechanism named in passing, a consequence of a decision, the reason a
number means what it does. Anything the argument depends on belongs in the
prose or in a callout.

Adding a new *kind* of computed block means two edits: a `ComponentSpec` in
`report.py` (its required arguments and how many captions it emits) and a
renderer of the same name in `assets/app.js`. The two rosters are checked against
each other, so a block with no renderer fails the build.

**Captions complement the figure, they do not describe it.** A caption names
what the block is and then adds only what a reader cannot get from the drawing
itself: what an unlabelled mark means, what the block does when it is touched,
what a bar aggregates. Anything a legend, an axis, a node label or the prose
above already states is left out—the pipeline figure does not re-explain the
layer semantics of section 4, and the token figure does not restate its own
legend. Captions are written as sentences; the terminating full stop is added
by `caption()` in `assets/app.js`, so call sites need not repeat it.

Adding a new citable number means one `Fact` in `facts.py`, measured from the
repository rather than typed in.

### Screenshots of the Application

A figure showing the interface is **described in `report.md`, not pasted in**.
The block says where in the application the picture is taken; a browser takes it
when asked, so a changed interface is one command away from changed figures.

```markdown
::: screenshot id=person-story route="#/en/story/alan_turing?event=13" width=390 height=844 wait=".story-view" settle=3500 caption="One event slide on a phone"
Optional authored prose, kept above the figure.
:::
```

| Argument | Meaning |
| --- | --- |
| `id` | Stable name. Names the file (`docs/report/screenshots/<id>.jpg`) and is what `--shots <id>` selects. |
| `route` | Where in the application, written as it appears in the address bar: `#/en/story/<person>?event=13`. Application state—language, story, position, open network view—is all in the URL, so the position is a string. |
| `caption` | The figure's caption. Required, and outside the fingerprint: rewording it does not make the picture stale. |
| `width`, `height` | Viewport in CSS pixels (default 1280×820). A phone shot is 390×844. |
| `wait` | A selector that must be visible before the shot—the honest way to wait for a story to have loaded. |
| `anchor`, `scroll` | Where in the document. `anchor` is a selector scrolled to the top of the viewport (`.network-section`, `.chapters-section`); `scroll` adjusts relative to it, or is an absolute offset when there is no anchor. Prefer an anchor: a meta story grows as its components load, so a bare pixel offset lands somewhere else on a slower machine. |
| `settle` | Milliseconds to wait after that, for a simulation to converge or a camera to arrive. |
| `clip` | `x,y,width,height` in CSS pixels, when the figure is one region rather than the screen. |
| `scale` | Device pixel ratio (default 2, for print). |
| `format`, `quality` | `jpeg` (default, quality 88) or `png`. The pictures are inlined into the single-file report, and a lossless capture of the landing page is 2.3 MB against 0.5 MB as a JPEG nobody can tell apart. Use `png` when the subject is a hairline or a screenful of small type. |
| `alt` | Alternative text, when the caption does not serve. |

```bash
npm run report:shots                                     # missing and stale ones
python scripts/generate_report.py --shots all            # every declared shot
python scripts/generate_report.py --shots person-story   # one of them
python scripts/generate_report.py --shots --shots-base-url http://127.0.0.1:5173/life-ds/
```

Capture starts a dev server of its own on port 4177 unless one already answers
there or `--shots-base-url` names another. It is **not** part of an ordinary
build: a build embeds what is on disk, so `--check` stays runnable without a
browser. `docs/report/screenshots/captures.json` records, per shot, the
fingerprint of the declaration the picture was taken from. A declaration that
has moved since makes the figure *stale*—a warning naming the command that
retakes it—and a declaration with no picture at all is a build error.

Staleness is a property of the description, not of the application: nothing here
can tell that the interface changed under an unchanged declaration. Retake
everything with `--shots all` after a visible change to the application, and
commit the pictures along with `captures.json`.

### The Teaser Figure

Figure 1 is the whole system on one canvas, and it is the only figure the prose
points *into*. Its parts are declared in `pipeline_docs/teaser.py`—id, label,
one sentence, a box in scene coordinates, a `decor` routine and, where a part
prints a number, a `metric` template over `facts.py` keys. `app.js` draws the
scene; the closed `decor` vocabulary is checked against the page the same way
the component roster is.

Reading a phrase in the text and finding the part it names are the same act, so
a reference is resolved against where the reader actually is:

- the figure on screen and large enough to read: the part lights in place;
- the figure on screen but scaled down: the part is enlarged in place;
- the figure off screen: the part is shown in a panel beside the passage—a
  card at wide widths, a sheet along the bottom edge on a phone.

There are no breakpoints in that rule. The scene is one coordinate system, a
part is a sub-rectangle of it, and all three behaviors are a `viewBox`. Two
consequences are load-bearing for anything added here: the drawing's box must
keep a fixed aspect ratio (so zooming never reflows the page), and the status
strip under the figure reserves the height of its tallest state where the
pointer hovers (so lighting a phrase cannot move the phrase).

Moving a part is a coordinate edit; `--check` rejects a box outside the canvas,
two siblings overlapping, a child escaping its parent, an arrow to a part that
does not exist, or a metric citing a fact that was removed.

### Printing the Report

The page carries its own print layout, so **Ctrl+P → Save as PDF** in any
browser produces the full report. `npm run report:pdf` does the same thing
headlessly, through Playwright, and writes
`docs/report/life-data-stories-technical-report.pdf` (untracked—regenerate it
rather than committing it).

```bash
npm run report:pdf                     # docs/report/index.html -> PDF
npm run report:pdf -- --no-appendix    # body only, no step appendix
npm run report:pdf -- --out some.pdf   # somewhere else
```

The script prints whatever `generate_report.py` last wrote, so rebuild the page
first if the pipeline or the prose has changed.

Both routes render the same `@media print` rules at the foot of
`assets/style.css`, whose job is that nothing on paper is missing:

- **Nothing clipped.** The wide figures and tables scroll inside their own boxes
  on screen, which on paper is a silent truncation. Print opens every scroll
  container, drops the screen-only table minimum, and fits each pipeline graph
  to the sheet by overriding the pixel size `app.js` measured it at.
- **Nothing behind an interaction.** Every `<details>` is opened before printing
  (`bindPrintDisclosure` in `app.js` for the browser, the export script itself
  for headless runs, since the DevTools protocol never fires `beforeprint`), and
  the drawer's material is laid out as an appendix.
- **Nothing straddling a break** that costs the reader what it describes:
  figures stay with captions, rows stay whole, headings stay with their text.

**Appendix A is the drawer on paper.** `renderStepAppendix` in `app.js` builds
one entry per documented step from `stepDetail`—the same function that fills the
drawer—with the prompt tabs expanded into every prompt in sequence. It is in the
DOM but hidden on screen, where the drawer already answers the question in
place; `?appendix=0` skips building it. Anything added to the drawer therefore
reaches the PDF for free, and anything printed outside `stepDetail` will drift.

### When the Pipeline Changes

1. Add or update the step in `scripts/pipeline_docs/spec.py`, including the
   `depends_on` edges into it *and* any existing step that now reads its output.
   An edge is a real data dependency, not "runs after".
2. Run `python scripts/generate_report.py`—the summary cache refreshes only
   the steps whose source changed.
3. Commit the regenerated `docs/report/index.html` and `summaries.json`.

Everything except `spec.py`, `report.md` and the page's own styling is derived,
so never hand-edit `docs/report/index.html`.

## Key Files for Context

When working on specific features, read these files first:

**Routing**: `src/App.svelte` (lines 1-150)
**Event display**: `src/components/StoryView.svelte`
**Timeline**: `src/components/Timeline.svelte`
**Network viz**: `src/components/NetworkModal.svelte`
**Name highlighting**: `src/utils/personNames.js`
**Person data**: `data/persons.json`, `data/people/{person_id}/`
**Styles**: `data/person_styles.json`
**System overview**: `docs/report/index.html` (open it), `docs/report/report.md`, `scripts/pipeline_docs/spec.py`
