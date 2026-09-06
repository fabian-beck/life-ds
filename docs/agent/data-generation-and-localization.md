# Data Generation and Localization

> Detailed reference for coding agents. Keep the root `AGENTS.md` concise and update this document when the related project behavior changes.

## Data Generation

Generated data is never repaired in place. When a generator or schema change leaves shipped datasets behind, flag them in `data/outdated.md` with the reason and regenerate them with the current pipeline (see the no-repair rule in `AGENTS.md`). Hidden persons and collections (`"hidden": true` in the registries) are not tracked there: they are off the deployed site, and a session that shows one again first regenerates it or audits it against the entries in that file.

### Python Environment

The generation scripts run from a project-local virtual environment. The `openai` dependency must be >= 2.0.0 — the pre-1.0 SDK exposes a different client and the scripts will fail to import against it.

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt   # Windows
# source .venv/bin/activate && pip install -r requirements.txt  # macOS/Linux
```

Run scripts with the venv interpreter, e.g. `.venv/Scripts/python.exe scripts/generate_person.py "..."`.

**Model configuration** (see `scripts/config.py`):

- `OPENAI_MODEL` — text/reasoning model for the phases that decide what a life or a theme is, read a whole document, or criticize another phase's output (default: `gpt-5.6-terra`)
- `OPENAI_COMPOSER_MODEL` — Phase 8 meta-story composer model (default: `gpt-5.6-sol`)
- `OPENAI_BULK_MODEL` — small model for the phases whose output is checkable or replaceable (default: `gpt-5.6-luna`)
- `OPENAI_REASONING_EFFORT` / `OPENAI_BULK_REASONING_EFFORT` / `OPENAI_LOW_REASONING_EFFORT` — reasoning effort levels (`medium` / `low` / `none`)
- Portrait scripts take `--model` separately (default: `gpt-image-2`)

A phase runs on `OPENAI_BULK_MODEL` when a wrong answer cannot quietly become part of the corpus — its output is validated against existing entities afterwards, rewritten by a later phase, or backed by a deterministic fallback. That covers related-article selection, Phase 2 event research, image search and matching, both style generators, meta-story event curation, circle narration, the map branch, and translation. Everything else keeps `OPENAI_MODEL`: Phase 1, the ego network, story planning, historical context, the depth-layer background reports and their illustration critic, both review passes, and the name glossary, whose decisions every other document then matches on by exact name. The report's step drawer shows the model and effort each call site actually resolves to; it is generated from the source, so consult it rather than this list when they disagree.

`generate_meta_story.py` exposes the tier as `--bulk-model`, alongside `--model` and `--composer-model`. `cache_wikipedia_materials.py`, `generate_person_style.py`, `generate_meta_story_style.py`, and `meta_story_map_narration.py` do all their AI work at this tier, so their own `--model` flag defaults to it.

**Making the call** (see `scripts/utils/model_calls.py`): every phase that fills a schema calls `parse_structured()`, which wraps the Responses API. Reasoning effort is a required argument there, so no phase can silently inherit the model's default. The call retries only failures a second identical request could survive — dropped connections, timeouts, 408/409/429/5xx, and a response that parsed to nothing — and returns `None` for everything else, having logged the phase's name and the reason. What a `None` means belongs to the phase: article selection falls back to the first N candidates, historical context is skipped, translation is left stale for `--check` to report, and curation stops the run rather than let a story keep every event of every life.

**Running the independent calls side by side** (see `scripts/utils/concurrency.py`): the research of the events, the image searches, the chapter illustrations, and the background reports read nothing of each other, so each of those steps sends its calls through a small thread pool and gathers the results in the original order. `LIFE_DS_WORKERS` sets the pool size (default 4); `1` restores the serial order call for call and is the first thing to try when the provider answers 429, since every Phase 2 call carries the subject's article and a handful of them at once reach the tokens-per-minute limit. The geocoder stays serial because Nominatim allows one request a second, and the phases that read each other's output stay in sequence. The usage ledger counts calls from every worker; a `usage.step` block belongs on the main thread, because it attributes every worker's calls while it is open.

Image models that support the dual-image editing path are allowlisted in `generate_person_portrait.py`; a model outside that list silently falls back to text-only generation and will not preserve facial likeness.

### Python Scripts (require `OPENAI_API_KEY`)

**Add a new person**:

```bash
python scripts/generate_person.py "Albert Einstein"
```

This runs the whole pipeline: the three generators, the portrait and chapter art, review, the depth-layer background reports, and translation.

1. `generate_person_events.py` - Life events via two-phase AI (the command line over `events/pipeline.py`)
2. `generate_person_style.py` - Visual design
3. `generate_person_network.py` - Ego network
4. `generate_event_backgrounds.py` - Background reports for the deep events (after review, before translation)

**The images wait for the style**: both image steps draw in the story's own primary and secondary color, which `generate_person_style.py` writes to `data/person_styles.json`, so they run after it and only for a person who has an entry there. `scripts/utils/person_style.py` is the one reader of those colors, and it raises rather than substituting a default palette: a portrait or a chapter illustration in colors no story uses would be cached under the person's name, and every later run would find it and leave it alone. A run whose style step failed reports the portrait and the chapter art as skipped for the missing style; a person whose style an earlier run wrote is drawn in that one.

**What the run consumed**:

Every model call the pipeline makes is recorded by `scripts/utils/usage.py` and attributed to the step that was open when it was made, and a run ends by printing one row per step: calls, input tokens, input tokens served from the provider's prefix cache, input tokens written to it, output tokens, reasoning tokens, and images. `--usage-json PATH` writes the same ledger, plus one entry per individual call, as JSON. The ledger counts tokens and images only. Rates for the configured models are not part of this repository, so a run states what it consumed and not what it cost.

The prompts of the repeated steps are ordered for that cache: the subject's article, the second biographical source, and the task description lead, and the event being researched follows them, because a repeated prefix is discounted only while nothing that varies per call precedes it. A step whose prompt changes shape should keep that order.

**How the prose reads** (see `scripts/utils/prose_style.py`): every phase that writes text a reader sees — Phase 1 and Phase 2, the background reports, the review pass, the meta-story composer, and the circle and stop cards — appends the one `PROSE_STYLE_INSTRUCTIONS` block to its prompt, and the German translator carries the same rules in its language note. The block names the habits of model prose by the shape they take on the slide, each with the sentence to write instead: one statement per sentence and no colon, semicolon, or dash carrying an aside; the fact stated and never contrasted against an alternative nobody proposed ("rather than", "not X but Y"); no verdict sentence on what an event "marked" or "reflected"; no opening announcement or closing generalization; plain words. A generic "be concise" moved nothing, and the composer, the one prompt that had named the constructions it did not want, was for a time the only phase whose prose had none of them. A rule about how sentences read belongs in that block, not in one phase's prompt.

A call made outside any step appears under `Unattributed`, which is how a generator invoked on its own reports, and how a missing `usage.begin_step` in the orchestrator would show up.

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

This script acts as an AI-powered constructive critic to review and improve the quality of generated person data. It reviews life events and the ego network, proposing improvements for readability, accuracy, and storytelling quality.

**What it reviews**:
- **Life events**: Event descriptions, titles, chronological accuracy, historical context
- **Story continuity**: the review is the one pass that sees the finished sequence. Phase 2 refined each description with only its own event in view, so a slide can lean on a name the story never introduced ("Hut 8") or tell again what the slide before it told ("Joins the National Physical Laboratory" followed by a slide that prepares the same plans again). The reviewer walks the events in order and states, per event, what the slide adds, which terms it leans on unexplained, and which facts it restates, and rewrites the description so it names the thing where the story first meets it and carries what changed at this moment. A slide that adds nothing and whose sources supply nothing more is beyond its powers, since the review cannot remove an event; the run prints such a slide under "Story continuity", in the dry run and the real run alike, so a human can decide.
- **Ego network**: Relationship descriptions, connection strength

The interface style is not reviewed. Its rules — a two-color tile over an opaque ground, a self-hosted font, a WCAG contrast floor for the two text colors against the background — are checked in code by `generate_person_style.py`, which asks the model once more with the reason when an answer fails; a style worth replacing is regenerated with that script.

**Features**:
- Confidence-based changes (only applies high-confidence improvements by default)
- Dry-run mode for previewing changes without applying them
- Aspect-specific review (events, network, or all)
- Uses Wikipedia cache for contextual understanding

**Options**:
- `--aspect {all,events,network}` - Which aspect to review (default: all)
- `--dry-run` - Show proposed changes without applying them
- `--min-confidence {1,2,3,4,5}` - Lowest confidence a change may have to be applied (default: 4)
- `--model MODEL` - Override OpenAI model
- `--reasoning-effort {low,medium,high}` - Override reasoning effort levels
- `--verbose` - Enable detailed logging

**Write the depth-layer background reports**:

```bash
python scripts/generate_event_backgrounds.py alan_turing
python scripts/generate_event_backgrounds.py                # every person
python scripts/generate_event_backgrounds.py --dry-run
python scripts/generate_event_backgrounds.py --overwrite    # rewrite existing reports
```

The story offers a depth layer on roughly one event per chapter, and the layer is a written background report plus the pictures that illustrate it. This step computes the story's own deep-event selection (`scripts/utils/event_depth.py`, a port of `src/utils/story/eventDepth.js` — keep the two in sync) and writes a 350-550 word report exactly for the events the story will offer one on; it re-decides the event's citations in the same call and illustrates the report from Commons through a critic on the default model. Inside `generate_person.py` it runs after review and before translation; standalone it fills the same events for the persons named. A dataset whose events carry no `weight` predates Phase 1 weighting — the step refuses it and points to `data/outdated.md`.

**Remove a person**:

```bash
python scripts/remove_person.py "Ada Lovelace"
```

**Check the source links** (no API key, no model):

```bash
python scripts/validate_source_links.py            # report
python scripts/validate_source_links.py --check    # exit 1 on any dead link
python scripts/validate_source_links.py --fix      # repair what search resolves
```

Phase 2 asks a model for the sources behind each event, and the annotations it writes carry article links of their own; both are rendered as links the reader can follow. This asks the MediaWiki API — 50 titles per request, redirects followed — whether each one is a real article. `--fix` rewrites a link only when search returns the same title respelled ("Kunst Haus Wien" → "KunstHausWien", "Austrian Postal Savings Bank Building" → "Austrian Postal Savings Bank"); a result that names a different subject is reported for a human, because search answers every query with something.

**Check the people who lived the same events** (no API key, no model):

```bash
python scripts/validate_cross_person_events.py            # scan list
python scripts/validate_cross_person_events.py --check    # exit 1 on a contradiction
```

Person generation is per-person by construction: the generator reads one subject's cached articles and never looks at the datasets already in `data/people/`, so two records of one wedding, battle, or coronation are written independently and never compared. Two events become candidates for the same occasion when they name a participant in common — or name each other's subject — and fall within a year. The default output lists those candidates for a human to scan, because nothing deterministic can tell whether "Makes the Case for Constitution" and "Presides Over Constitutional Convention" are one occasion or two. `--check` reports only the shape that is a contradiction rather than a judgment: same primary place, and dates that cannot both be true once each is read at its own precision. That is what a coronation recorded on two different days looks like.

**Check the event dates against their own descriptions** (no API key, no model):

```bash
python scripts/validate_event_dates.py            # exit 1 on any finding
python scripts/validate_event_dates.py alvar_aalto
```

Phase 1 decides the date, the precision, and the description in one call, and the Phase 2 schema carries no date field — so when Phase 2's research disagrees, the disagreement lands in the prose and the reader sees the date on the slide contradicted by the sentence beneath it. The generator's chronological check only compares an event to its neighbors, so a wrong year that preserves the ordering passes. This reads the description's *first* sentence, the one that states the event, and reports a year there that falls outside the event's own span. Decades ("the 1950s"), life spans in parentheses, and ranges ("the winter of 1779–1780", which covers both years) are read the way a reader reads them. A context year in an opening sentence that is nonetheless right belongs in the script's `ACCEPTED` list with the reason.

**Check the years given to other people against their sources** (no API key, no model):

```bash
python scripts/validate_life_spans.py            # exit 1 on any finding
python scripts/validate_life_spans.py max_planck
```

The cached articles write life spans in parentheses ("Karl (1888–1916)"), and the generator read them yet still shipped "killed at Verdun in 1917" — a wrong year attached to a *different* person, which neither the chronological check nor `validate_event_dates.py` can see. This collects every such span from the person's `_cache` and holds two things to them: a network connection must not end after that person's death or start before their birth, and a prose sentence that says a named person died must name a year the sources give as that person's death year. Family names resolve through bare first names the way the articles write relatives; everyone else matches on the full name only. A person without a cache produces no findings, so run it right after generating, while the cache that fed the prompts is still on disk; a finding that is right despite the sources belongs in the script's `ACCEPTED` list with the reason.

**Check that events spell people the way the network spells them** (no API key, no model):

```bash
python scripts/validate_involved_names.py            # exit 1 on any finding
python scripts/validate_involved_names.py max_planck
```

The story matches `involved_people` against `ego_network.json` by name to draw the person chips, without folding diacritics or ß/ss — so "Marga von Hößlin Planck" against "Marga von Hösslin" silently lost its chip, and nothing reported it because a failed match is also the correct outcome for people who are not in the network. This flags the near miss: a pair that folds to one person (diacritics collapsed, particles dropped, token subsets allowed) and that the interface's scoring — ported from `src/utils/story/personMatching.js`, keep the two in sync — nonetheless rejects. Its first corpus run surfaced seven shipped misses, from "Leó Szilárd"/"Leo Szilard" to a control-character corruption of "Lazović". The fix is to spell both sides identically; a pair that is genuinely two people belongs in the script's `ACCEPTED` list with the reason.

**Check the words for mixed writing systems** (no API key, no model):

```bash
python scripts/validate_scripts.py            # exit 1 on any finding
```

The translator has twice spliced another alphabet into a German word — "Zwillინგstöchter" with three Georgian letters, "лекtionierte" opening in Cyrillic — and the defect is invisible in a diff of correct-looking JSON. This scans every data file for a word mixing Latin letters with another script's. A pure Cyrillic name in an image credit passes, one Greek letter beside Latin passes (that is how physics writes "hν"), and sub-/superscript digits are not letters; there is no `ACCEPTED` list because no legitimate word has this shape. `translate_person.py` runs the same scan on every document it saves and prints the corrupt words while the run is still on screen.

**Check the prose for stray Markdown** (no API key, no model):

```bash
python scripts/validate_markdown.py            # exit 1 on any finding
```

The interface renders every text field verbatim; its only markup is the `[[term|display]]` annotation marker and the `## ` heading line inside a `background` report. A model that writes Markdown anyway — the generator setting a work's title as `*Childe Harold's Pilgrimage*`, the translator adding `*Philosophical Magazine*` where the English was plain — ships literal asterisks onto the slide. This flags asterisks, backticks, `__bold__` pairs, `[text](url)` links, and a heading line outside a `background` field; single-underscore emphasis is not checked, because Commons file names are full of underscores and models write emphasis with asterisks. There is no `ACCEPTED` list because no field legitimately carries these characters. `translate_person.py` runs the same scan on every document it saves.

**Check the English event titles** (no API key, no model):

```bash
python scripts/validate_event_titles.py            # exit 1 on any finding
python scripts/validate_event_titles.py emmy_noether
```

A title is written once, in Phase 1, and nothing downstream revisits it — the Phase 2 schema carries no title field. A title that came back half in German therefore stays that way in the English data, while the translation step renders it into idiomatic German, so the defect survives only in the language nobody re-reads. This flags a German function word left standing in an English title and a city written the German way where English has its own name (Warschau, Zürich). Quoted work titles and name particles ("Nina von Lerchenfeld") are exempt; a title that trips a rule and is still right belongs in the script's `ACCEPTED` list with the reason. It is a lexical check and claims nothing beyond that: a German noun that looks like a place name ("Wölfen" against "Göttingen") is indistinguishable to it.

**Check the event prose against the description contract** (no API key, no model):

```bash
python scripts/validate_event_prose.py            # report
python scripts/validate_event_prose.py --check    # exit 1 on any finding
python scripts/validate_event_prose.py charles_babbage
```

Every phase that writes a description — Phase 1, Phase 2's refinement, the review — reads one definition of what a description is, `description_contract_prompt()` in `scripts/utils/prose_style.py`: one moment of a life, narrated in its own present, asserted rather than weighed against sources, at the slide's granularity. Before the contract each phase carried its own partial copy of the rules and the copies disagreed, and a description that was accurate, sourced, and written in an encyclopedia's source-critical register passed every validator (issue #141). This reads for the shapes that shipped: a year later than the event's own span anywhere in the prose, the language of weighing sources ("most likely", "is disputed", "according to"), a street address or house number where the slide is at city level, a description under twenty words, a conclusion of one sentence, and a sentence that restates a sentence of one of the three slides before it in its content words ("He prepares plans for the Automatic Computing Engine, a stored-program electronic computer" followed by "The design sets out a stored-program electronic computer"), the event's own place and people not counting as shared words. The last is the shape a per-event rewrite produces, since Phase 2 sees one event at a time; the contract says a description is read in sequence, and the review is asked to read it that way. The two length floors came from the datasets generated on 2026-09-05, whose median description had fallen to 23 words from the 60 of the first datasets: the prose block said its range was "not a length target", Phase 2 was told to refine a skeleton "shorter, never longer" although it holds more of the article than Phase 1, the class guidance forbade the partner's name in the prose because the card carries it, and a marriage came out as "In 1930, she married a New York University professor." The prompts now state the floor, let Phase 2 extend a thin skeleton, and keep the people and the place in the sentence; the card holds only the structured detail. It reports by default, because the corpus still carries prose written before the contract, and its count is how a prompt change is judged; `--check` makes it a gate. A sentence that trips a rule and is right belongs in the script's `ACCEPTED` list with the reason.

**Check the chapter sizes** (no API key, no model):

```bash
python scripts/validate_chapter_sizes.py            # report
python scripts/validate_chapter_sizes.py --check    # exit 1 on any finding
python scripts/validate_chapter_sizes.py alan_turing
```

A chapter slide announces a phase of the life and the event slides after it tell that phase, so a chapter with one event announces the event and then tells it once more, with the same year and place on both slides; a chapter with no event never renders, because the interface inserts a chapter slide only where an event names it. Phase 1 now refuses such a plan (`MIN_CHAPTER_EVENTS` in `scripts/events/pipeline.py`), and this reads the corpus for the datasets written before the floor. It reports by default and gates under `--check` once the count reads zero.

**Restyle a meta story** (Phase 9 of `generate_meta_story.py`, standalone):

```bash
python scripts/generate_meta_story_style.py computing_pioneers --verbose
python scripts/generate_meta_story_style.py computing_pioneers --dry-run
```

Writes one entry in `data/meta_story_styles.json`: the article's colors and fonts plus the SVG marks that punctuate its prose — a separator glyph and an ornamental rule. See [Domain and data models](domain-and-data-models.md) for the schema. Skip the phase inside the full workflow with `--skip-style`; it is non-fatal, and a story without an entry falls back to the neutral editorial palette.

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
3. Generate the person's style first (`generate_person_style.py`): the transfer prompt names the story's primary and secondary color, and a person without an entry in `data/person_styles.json` is reported as an unmet prerequisite before anything is requested

**Options**:
- `--force`: Regenerate even if portrait already exists
- `--dry-run`: Test without API calls or file writes
- `--master-style PATH`: Use custom master style image
- `--model MODEL`: Specify OpenAI model (default: gpt-image-2)

**Master Style Portrait**: The master style portrait defines the artistic style applied to all generated portraits. Create it once (manually or using AI tools), then all generated portraits will match its style through AI-powered style transfer.

**Portrait Data Syncing**: The portrait generation script automatically ensures portrait data consistency across all files:
1. Updates `data/persons.json` with the generated portrait path and metadata
2. Syncs the same portrait data to `data/people/{person_id}/life_events.json`
3. Updates all language translations (e.g., `data/people/{person_id}/de/life_events.json`)

This ensures the generated portraits appear consistently on both the landing page (which reads from `persons.json`) and the story overview slide (which reads from `life_events.json`).

**Generate chapter illustrations** (optional):

```bash
python scripts/generate_chapter_illustrations.py "Alan Turing"
```

Each chapter of a story gets one abstract image, printed translucently above its headline. It is style transfer of the same kind as the portrait — the master style at `public/master_style_portrait.png` is the only reference image passed — but the *content* comes from the prompt rather than from a second picture, because there is no photograph of what a chapter is about. Two calls stand behind that:

1. A text call reads the whole chapter list at once, with each chapter's events, and writes one visual concept per chapter: an abstract, metaphorical image described in concrete visual nouns. Its rules are negative and strict — no people, no faces, no recognizable buildings or landmarks, no text — because a model shown a biography draws the biography, and a chapter slide must not make a second claim about what happened. The chapters are shown together so the metaphors differ from one another.
2. One image call per chapter draws that concept in the person's own primary and secondary color, on a pure black ground, as a centered emblem with a wide margin. The margin matters: the interface dissolves the edges with a radial mask, and a form that crowds the frame leaves a visible square. Those colors come from `data/person_styles.json`, so a person without a style there stops the step before the concept call rather than drawing in a default palette.

The result is stored under the chapter as `illustration` in `data/people/{person_id}/life_events.json`, synced to every translated copy (a path and a concept are not prose), and the WebP files are written to `public/chapter_art/{person_id}/`. The concept is stored with it so the picture can be redrawn without paying for the text call again. No PNG master is kept — a corpus-wide set of them would outweigh every other asset in the repository.

**Options**:

- `--force`: Redraw chapters that already have an illustration
- `--chapter ID`: Only this chapter (repeatable)
- `--concepts-only`: Write and print the concepts without generating images — the cheap way to tune the prompt
- `--dry-run`: Print the concept prompt without calling the API
- `--model MODEL` / `--concept-model MODEL`: the image and the text model

Inside the full workflow the step runs after the portrait and is skipped with `--skip-chapter-art`, and — like the portrait — with the reason named when the person has no style to draw in. A person whose dataset has no chapters is reported as having nothing to illustrate rather than as a failure.

### Two-Phase Event Generation

The life events generation uses a **two-phase AI approach** for improved accuracy and richer metadata:

**Phase 1: Event Skeleton Generation** (1 AI call)
- Identifies 12-16 significant life events (strictly enforced)
- Groups them into 3-6 coherent chapters by naming the chapter on each event, and writes the conclusion; the chapters are dated afterwards from the events they hold, and `validate_chapter_partition` refuses a plan whose chapters do not form contiguous runs of at least two events (`MIN_CHAPTER_EVENTS`) before Phase 2 pays for any research. A refused plan is asked for once more with the reason (`PHASE1_ATTEMPTS`); a second refusal fails the run
- Creates crisp titles (2-6 words) and writes each description to the shared description contract (`scripts/utils/prose_style.py`), the one definition Phase 2 and the review hold it to as well: 2-4 sentences that name the people and the place and stand without the card beside them
- Uses ALL related articles for broad context

**Phase 2: Event Detail Research** (12-16 AI calls, one per event)
- Researches specific details for each event individually, and rewrites a skeleton that falls short of the description contract from the 30,000 characters of the subject's article it holds, where Phase 1 saw 12,000; a one-sentence skeleton is extended, never returned as it is
- Filters 3-5 most relevant related articles per event
- Provides:
  - Historic location name (e.g., "Königsberg")
  - Modern location name (e.g., "Kaliningrad, Russia") for accurate geocoding
  - People directly involved in this event (excludes main subject)
  - Event-specific images and sources
  - Semantic icon from 100+ MDI categories (e.g., "mdi-crown", "mdi-book")
  - Annotations for the terms an educated general reader would not know from the sentence. Section 5 of the prompt tests reader benefit, not obscurity: the standard terms of a field (`central limit theorem`, `general relativity`) get a gloss, while person names, the classified subject, well-known places and periods, and terms the sentence itself explains do not. An earlier prompt annotated "only truly obscure terms" and defaulted to none, and the persons generated under it (July to September 2026) carry a third of the annotations older ones do; `data/outdated.md` lists them. The review pass (`scripts/utils/review_prompts.py`) applies the same test and adds what Phase 2 missed, merging into the event's existing annotations, and removes via `dropped_annotations` a gloss that only restates the description, the way Turing's Banburismus slide defined the method in the sentence and again in the popup. `validate_event_prose.py` reports the restatements written in the slide's own words; a paraphrase escapes it, which is why the reviewer reads the rest.
- Each call sees only its own event, so it cannot know that a term was the subject of an earlier slide. `drop_repeated_annotations` in `scripts/events/normalize.py` therefore keeps an annotation only where the story first meets its term: once an earlier event annotated a term or named it in its title or classification title, a later annotation of it is removed and its `[[term|display]]` markup unwrapped. The review save path applies the same rule to what the reviewer adds.

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
- Integration in `scripts/events/pipeline.py` (fetched per person) and `scripts/events/prompts/` (Phase 1 & 2 prompts)
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

An entry of either registry, or of the meta story registries, may carry `"hidden": true` to keep the person or collection off the deployed site; see [Person Data Model](domain-and-data-models.md#person-data-model). `scripts/set_hidden.py` sets and clears the flag in the English and every localized registry at once, so the derivations agree the way a translation would leave them.

### Translation Scripts (require `OPENAI_API_KEY`, except `--check`)

**Check parity (no API key needed)**:

```bash
python scripts/translate_all_persons.py --target-lang de --check
```

Prints per-person and per-meta-story status (✓ current, ↻ stale, ✗ missing). It exits non-zero when a translation is missing, and warns without failing when one is stale: a missing document leaves a German reader with nothing, while a stale one still reads, describing English text that has since moved. Staleness is the expected state between regenerating a person and re-translating them, so CI reports it rather than gating on it.

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

`generate_person.py` and `generate_meta_story.py` automatically translate to German as their final step (after review, so translations reflect the reviewed English text). Control this with `--translate-langs de,fr,...` or `--skip-translate`. Translation failures are non-fatal — the English reference stays complete and `--check` reports the gap. If you edit or re-review English data outside the pipeline, run `translate_all_persons.py --target-lang de` afterward; fingerprint-based staleness detection ensures only affected documents are re-translated.

### Translation Rules

**What gets translated**:
- Person summaries and roles
- Event titles and descriptions
- Chapter headlines
- Image captions
- Relationship descriptions
- Social network notes and summaries
- A connection's `qualifier` (the short descriptor of an organization or group in a network that predates the individuals-only rule, see `data/outdated.md`), extracted only when present so documents without one keep their fingerprint
- A connection's `shared_activities` tags, which the network schema no longer carries: extracted only while the source still has the key, so a network that predates the removal keeps its fingerprint until it is regenerated
- The prose inside an `event_class`: `characterization`, `duration`, `from_location`, `to_location`, `title`, `description`, `impact`, and `significance` (see below)

**What is preserved** (guaranteed by the merge — the model never sees these fields):
- All dates (dates, timestamps)
- All coordinates (locations, centroid, bbox)
- All URLs (sources, wikipedia, images, annotation wikipedia_urls)
- All IDs (person_id, chapter IDs, annotation term keys, event_index)
- `event_type_icon`, `involved_people` list structure
- Relationship types (e.g., `professional/mentor`) — entirely; the UI localizes them from locale files (the closed vocabulary in `scripts/utils/relationship_vocabulary.py`), and `entity_kind`, where a pre-rule network still carries it, is copied verbatim the same way
- Strength values (`weak`, `moderate`, `strong`)
- Technical classifications

**Event classifications**: an `event_class` block mixes prose with machine tokens, and the split runs through it rather than around it. Its prose is extracted like any other text, listed under `EVENT_CLASS_TEXT_FIELDS` in `translate_person.py` and carried in the payload only for events that have a classification, so unclassified documents keep their fingerprint. Its tokens — `type`, `subtype`, `publication_type`, `children` — stay verbatim and are named by the interface from `src/locales/` through `src/utils/eventClassLabels.js`, exactly as `relationship_type` is. `partner` is neither: it is a person name that the story matches against the ego network to draw the spouse chip, so it follows the name glossary with every other name. A publisher or journal keeps its own name in every language and is not extracted.

**Annotation markers**: descriptions may contain `[[term|display]]` markers. The term (before the `|`) is an ID and stays in English; only the display text and the annotation's `explanation` are translated.

**Background reports**: a report is the only text in the corpus with structure of its own — paragraphs, and `## ` section headings between them — and it is taken apart for the translator rather than sent as one string. `background_paragraphs` is one entry per paragraph and `background_headings` is the headings as plain phrases; `_rebuild_background` reassembles them on merge, putting each heading above the paragraph it stood above in the source. The depth layer is filled per dataset, so the three report fields — the paragraphs, the headings, and the captions of the report's own pictures — reach the payload per dataset: every event of a life that carries reports offers them, and a life the report step has not reached offers them nowhere, which is what keeps its fingerprint. Carried unconditionally instead, they reported 43 of the 52 German life-event copies stale although no English word had changed. Both routes were tried the obvious way first and neither held: a `## ` line inside a passage reads as formatting to preserve, so two of the first five lives came back with German prose under English headings, and offering the headings a second time as their own fields only taught the model to copy one from the other; sent as one string, the German came back with four paragraphs merged into three and the heading positions counted from the source no longer meant anything. The array-length contract of rule 1 is the one piece of structure this pipeline can actually hold a translator to, and it mostly holds: the small model still merges two paragraphs of a long report about once every dozen events. When it does, the headings have nowhere to stand, and unlike a changed list of images this is not worth discarding the document over — the reader would lose the whole German story to save its section headings. The prose is kept as it came back, the report is set undivided, and the run says so. The merge also measures what came back: German runs a little longer than English, so a report at two-thirds of its source's length was summarized rather than translated, which is what the small model does once a document carries a dozen of them. That prints a warning naming `--model` as the remedy — translating a life whose events all carry reports is one of the few places the bulk tier is now too small, and the larger model returns them at full length.

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

1. The target language's **naming evidence** is read from its own Wikipedia (no AI call, see below)
2. A name glossary is built once per person (single AI call, shown that evidence) and applied deterministically everywhere a name appears
3. Each document's translatable payload is translated with structured outputs (Pydantic models), shown the same evidence
4. The payload is merged onto a deep copy of the English document; misaligned outputs (wrong list lengths) are rejected
5. A `translation` block (`source_lang`, `target_lang`, `source_fingerprint`, `translated_on`, `translator`) is stamped into the file
6. Language-specific registries (`persons_{lang}.json`, `meta_stories_{lang}.json`) are created/updated automatically, kept in English registry order

### Naming Evidence From the Target Language's Wikipedia

A translator working from the English text alone has only its own memory for what a name is called elsewhere, and memory invents: a Copenhagen cemetery came back as the "Assistenzfriedhof", a German compound that reads perfectly and does not exist. So before anything is translated, `build_translation_reference()` in `translate_person.py` reads two things out of the *target language's* Wikipedia and shows both to the glossary call and to every document translation:

- **The person's own article there**, resolved through the language links rather than by searching that edition for the English string — an exonym ("Kunigunde von Luxemburg") is exactly what a string search would miss. Its lead is quoted, which is where the language writes the person's name, their parents' names, and their institutions.
- **One language link per proper name in the data** — every person name the glossary covers plus every place, institution and resting place (`collect_place_names`). This is the encyclopedia's own answer to "what do you call this?": `Assistens Cemetery → Assistens Kirkegård`, `Bamberg Cathedral → Bamberger Dom`, `Pope Benedict VIII → Benedikt VIII.`

Both are best-effort: no network, or a person the other edition does not cover, and the translation runs exactly as it did before.

The lookup is built to be honest about what it found, because a wrong name is worse than no name (`fetch_language_links` in `scripts/utils/wikipedia_cache.py`):

- **Redirects are not followed.** "Ellen Adler Bohr" redirects to her son's article, and following it would offer *Niels Bohr* as the German form of her name. A redirect means that encyclopedia has no article of its own under the name, which is the same as having no evidence.
- **Disambiguation pages and name lists are skipped** — they stand for a string, not for a person.
- **Each link carries the English article's short description**, so a link that landed on the wrong subject is visible in the prompt rather than hidden behind a plausible title.
- **A qualified place falls back to its leading part**, but only when the whole string found nothing, so "Washington, D.C." keeps its own article and never drops to the state. The answer is recorded under that leading part, so "Assistens Cemetery, Copenhagen" becomes "Assistens Kirkegård, Kopenhagen" rather than losing the city with the comma.

The evidence informs the model; it never substitutes automatically. Two things the prompts hold it to, because an article title is not a name: a title that merely spells the same name more fully ("J. J. Thomson" → "Joseph John Thomson") is a title convention, and an epithet the English name carries stays ("Henry II, Holy Roman Emperor" → "Heinrich II., römisch-deutscher Kaiser", not the bare "Heinrich II."). The one error that could not be left to a prompt is enforced in code: `localization_keeps_the_person()` rejects a mapping whose **numerals** differ, because Cunigunde's brother is "Henry V, Count of Luxembourg" here and "Heinrich I. (Luxemburg)" there, and a glossary that adopts that title renumbers him in prose the reader cannot check.

The target-language article is cached beside the English one as `data/people/{person_id}/_cache/wikipedia_page_{lang}.json`.

A **meta story** has no single subject and therefore no article of its own, and its strongest evidence is not Wikipedia's anyway: its people already have translations, and the interface matches a name in its prose against the name their story shows. `build_meta_story_reference()` therefore takes each person's name straight from the translated registry (`persons_{lang}.json`) and asks the encyclopedia only about the map's place labels. That is what keeps a story from calling Cunigunde something her own story does not.

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
- [PersonChip.svelte](src/components/PersonChip.svelte): Tooltips, relationship metadata
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
  "timeline.event_one": "{count} Ereignis",
  "timeline.event_other": "{count} Ereignisse"
}
```

**Important for German**: Use "Du" form (informal) instead of "Sie" form (formal) for all user-facing text

## Map Integration

Uses Protomaps PMTiles for vector basemaps (MapLibre GL):

- **Primary source**: `public/basemap.pmtiles`, a zoom 0-5 world extract shipped with the site and resolved through `assetUrl()` so it follows the deployment base path
- **Fallback**: the same local archive unless an override is set

Override via `.env`:

```env
VITE_PROTOMAPS_PM_TILES_URL=https://build.protomaps.com/20251114.pmtiles?download=1
VITE_PROTOMAPS_PM_TILES_FALLBACK_URL=https://...
```

**Important**: Maps only render when events have valid `location` objects. The UI gracefully handles missing location data.
