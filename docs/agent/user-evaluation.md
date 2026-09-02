# User Evaluation

> Detailed reference for coding agents. Keep the root `AGENTS.md` concise and update this document when the related project behavior changes.

The user-evaluation deployment is the same application built in Vite's `evaluation` mode: a participant identifies themselves before the first view, every interaction is logged under that ID, and an analysis page on the same deployment reads the logs back as reports. None of it is part of the ordinary site, and the normal `deploy` branch carries none of it.

## The mode

`vite --mode evaluation` reads `.env.evaluation`, whose one variable, `VITE_EVALUATION_MODE=1`, is the switch. `src/evaluation/log.js` exports it as `evaluationMode`, and `App.svelte` compares the literal `import.meta.env.VITE_EVALUATION_MODE` so that the ordinary build folds the branch away and emits neither chunk behind it. In every other mode the switch is unset, `logEvent()` is a null check, and the analysis entry is not built.

```powershell
npm run dev:evaluation      # the dev server in evaluation mode, with the log API emulated
npm run build:evaluation    # the production build of the evaluation deployment
```

The dev server emulates the log API (`evaluationApiPlugin` in `vite.config.js`) over a directory of JSON files, `.evaluation-logs/`, which Git ignores. It runs the same module the Netlify Function runs, so the whole loop—gate, logger, flush, analysis page—works without a Netlify account. Wipe the directory to start a study over locally.

## Deployment

The evaluation deployment is a branch deploy of the same Netlify site: `netlify.toml` carries a `[context.deploy-evaluation]` whose build command runs `npm run build:evaluation`, and whose environment sets `EVALUATION_MODE=1` for the function. Publishing is the same act as for the ordinary site, with a different target branch:

```powershell
git fetch origin
git push origin origin/main:deploy-evaluation
```

Two things happen once, in the Netlify dashboard. Under **Site configuration → Build & deploy → Branches and deploy contexts**, `deploy-evaluation` is added to the branches Netlify builds; the deployment then lives at `deploy-evaluation--<site>.netlify.app`. Optionally, `EVALUATION_ANALYSIS_KEY` is set as an environment variable (scoped to Functions) to protect the reports: the analysis page then asks for the key once per tab, and the read endpoints refuse without it. Writing needs no key—a participant's browser posts its own log.

A separate Netlify site works the same way when the evaluation should have its own domain or its own log store: connect it to the repository with `deploy-evaluation` as its production branch, and set `VITE_EVALUATION_MODE=1` in that site's environment, scoped to builds and functions, since the branch-context section of `netlify.toml` does not apply to a production build. Everything else is unchanged.

Storage is **Netlify Blobs**, the site-wide key-value store every Netlify site has without provisioning. `netlify/functions/evaluation.mjs` opens the store named `evaluation-logs`; every deploy of the site shares it, and only the evaluation deployment reads or writes it, because the function answers 404 unless `EVALUATION_MODE` or `VITE_EVALUATION_MODE` is set in its environment. A branch deploy shares the production site's store, which is what makes redeploying the evaluation branch safe for the logs already collected.

## What is logged

`src/evaluation/logger.js` starts once a participant ID is known and records a flat stream of events, each with the moment it happened (`t`, the reader's clock), its `type`, and the hash route it happened on. Three sources feed it:

- **The router.** Every route, as path and query. The analysis reconstructs from these alone which view was open when, and derives the network modal and the expanded timeline from the query.
- **The application**, through `logEvent(type, data)` from `src/evaluation/log.js`, at the points where a component knows what a reader meant: `story.open` with the story's size, `story.navigate` with the slide and the mechanism that reached it (`source`, as `StoryView` names its scroll requests), `story.depth` on entering a depth layer and how far down the reader got, `story.image`, `story.annotation`, `story.date_note`, `story.person_info`, `story.close`; `meta.open`, `meta.timeline`, `meta.network`, `meta.map`, `meta.image`, `meta.open_story`, `meta.back`; `landing.search` once typing pauses, `landing.filter`, `landing.collection_filter`, `landing.map`, `landing.map_select`, `landing.select_person`, `landing.explore_collection`, `landing.carousel`, `landing.ai_modal`, `landing.privacy`; `app.language` and `app.contrast` from the stores.
- **The document.** Every click with a description of the control under it (`describeTarget`: element, role, accessible name, a few classes, a link's destination—never an input's value), the navigation keys outside text fields, scroll depth and the section under the viewport's middle on a meta story (the sections announce themselves with `data-section`), visibility changes, resizes, and script errors. `session.start` carries the environment: user agent, viewport, pixel ratio, touch and pointer, language, reduced motion, contrast.

Nothing a reader types is recorded except the search query, which the gate says. The privacy notice gains a paragraph in evaluation mode saying the same.

A session is one browser tab: the session ID lives in session storage, so a reload continues it (`resumed: true` on the second `session.start`) and a new tab starts another. Changing the participant ID on the landing page ends the session and starts a new one under the new name.

Events are batched—every five seconds, at forty events, and on the way out of the page by beacon—and posted to `/api/evaluation/log`. A batch that cannot be sent is kept in local storage and retried on the next flush or the next visit. The server stores each batch as one immutable object under `logs/<participant>/<session>/<seq>`, so overlapping flushes cannot lose each other and a re-sent batch overwrites itself.

## The analysis page

`analysis/index.html` is the second entry of the evaluation build, published at `/analysis/` and served by the dev server at `/life-ds/analysis/`. It is its own small runes application under `src/evaluation/analysis/`, styled after the technical report—black on white, one serif measure, sans-serif tables, hairline rules, numbered figures and tables, a print stylesheet—and it draws its charts as inline SVG in the report's palette: the first three categorical slots for the three kinds of view, slot one alone for a single series.

The page loads every participant's batches through `/api/evaluation/participants` and `/api/evaluation/logs?participant=<id>`, computes the reports in the browser, and shows the aggregate report at `#/` or one participant's at `#/participant/<id>`. The computation is `src/utils/evaluation/analysis.js`, pure functions from batches to measures—sessions and active time, view segments, story visits with coverage and slide dwell, meta story visits with scroll depth, landing behavior, feature counts against the `FEATURES` roster, navigation classes, and the aggregate's medians, adoption shares, and drop-off curve—covered by `tests/evaluationAnalysis.spec.js` in the `logic` project. The participant report ends with the log itself and a JSON download for analysis elsewhere.

Adding a control to the study is two edits: a `logEvent` call where the control acts, and an entry in `FEATURES` that recognizes the event. Adding a measure is a function in `analysis.js` with a test, and a block in one of the two report components.
