# Development Reference

> Detailed reference for coding agents. Keep the root `AGENTS.md` concise and update this document when the related project behavior changes.

## Development Workflow

### Common Commands

```bash
npm install          # Install dependencies
npm run dev          # Start dev server (localhost:5173)
npm run build        # Production build to dist/
npm run preview      # Preview production build
npm run test:core    # Minimal UI, logic, and Python regression safeguards
```

See [Testing strategy](../testing-strategy.md) for the boundary between the
small deterministic suite and the repository's AI exploratory testing skill.

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

### Person Name Highlighting

Wherever a person is named in running text — story slide descriptions, meta
story prose, the network and map narration cards — the name is emphasized
(`.person-mention`, and a link into that person's story in meta story prose).
**One matcher does this for all of them**: `findPersonMentions()` /
`segmentPersonMentions()` in `src/utils/personNames.js`. Do not write a second
one; the four call sites previously each had their own copy and each was wrong
in its own way.

It works on **name runs** — stretches of capitalized tokens joined across
spaces, hyphens, particles ("von", "of") and the dots of initials — rather than
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
from the real stories — run it when touching the matcher.

Two things feed the matcher besides the text:

- **Aliases.** Registry names are translated but graph/map data is not, so a
  German story prints "Heinrich II." while its network node still says
  "Henry II". `MetaStoryView` passes both (`storyPeople[].aliases`, and
  `personAliases` down to `MetaStoryNetwork`/`MetaStoryMap`). Without this a
  translated story highlights nothing.
- **The story subject.** `parseDescriptionSegments()` takes the ego's name so
  a bare "Hamilton" in Alexander Hamilton's story comes out ambiguous — and
  therefore plain — instead of being handed to his father, while
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
**Name highlighting**: `src/utils/personNames.js`
**Person data**: `data/persons.json`, `data/people/{person_id}/`
**Styles**: `data/person_styles.json`
