# Testing Strategy

This prototype uses a deliberately small deterministic core and AI-led exploratory testing. The goal is fast feedback while the product changes, not exhaustive scripted regression coverage.

## Deterministic core

Run the complete core with:

```bash
npm run test:core
```

It contains only safeguards for high-value failures:

- one Playwright visitor journey in desktop and mobile Chromium, covering the landing page, search, opening and navigating a person story, the network modal, returning home, and entering and leaving a collection;
- a handful of further interface tests for layout and interaction that the journey cannot assert in passing — the slide fold, the depth layer, the timeline morph — plus two boot checks for a browser that refuses site data, where an unguarded storage access takes the whole application down with no error on screen;
- the browser-independent pure functions — the person-name matcher, the date and label helpers, the description and depth-prose builders — in a `logic` project with no browser at all; and
- focused Python regression checks for the generation scripts and for the data they write: portrait file validation, keeping curated meta-story references synchronized with person events, holding the person registries, per-person directories, and style registry to the same set of people, and the technical report's own build.

Do not add a deterministic test merely to increase coverage. Add one only for a costly, repeatable regression that is difficult to notice through exploration, or for a silent data-integrity failure. Prefer extending the one core journey over adding another UI scenario. Remove obsolete regression tests when their risk is no longer material.

### Each test earns the passes it costs

The browser projects are the slow part of the run, so nothing is checked twice for one answer. A pure function belongs in the `logic` project rather than in a browser. An interface test that pins its own viewport, or that reads something no viewport decides — a route, a document title, the served meta tags — declares which project keeps it; `tests/interface.spec.js` has the two helpers and says how they are shared out. Only what the two screen sizes can genuinely disagree about runs in both.

Two habits are worth avoiding, because both read as coverage and neither is:

- **Restating the source.** A test that greps a file for a string it should not contain, asserts the words of a prompt constant, or re-parses a module the test file already imported fails only when someone edits the line it copies. Assert the behavior the line produces, or let it go.
- **Sampling a value that is still moving.** Opacities, scroll positions, and anything mid-transition need `expect.poll` or a web-first assertion. A single sample of an animating value passes locally and fails on a loaded runner.

`npm run validate` and `npm run build` remain separate static and production build checks; they are not duplicated by the core suite.

## AI exploratory testing

AI exploration is the primary product review. Invoke the repository skill in Codex or Claude Code by asking it to use `exploratory-user-test`, optionally with a mode and focus, for example:

```text
Use exploratory-user-test in focused mode for the timeline changes.
```

The modes are:

- **smoke** (5–10 minutes): a quick first-time visitor tour;
- **focused** (10–20 minutes): inspect the current diff and explore the changed feature plus an adjacent journey; and
- **release** (30–45 minutes): rotate through major features, viewports, languages, resilience, and accessibility heuristics.

The agent uses charters rather than a fixed script, samples stories that fit the risk, and saves evidence under `test-results/exploratory/<timestamp>/`. It reports confirmed bugs separately from usability and improvement ideas and does not change application code unless asked in a later step.

## Choosing the right check

| Change | Required feedback |
| --- | --- |
| Documentation or agent workflow | formatting plus a dry review of instructions |
| UI behavior or styling | validation, build, core suite, and focused AI exploration |
| Person-name matching | core suite |
| Portrait or meta-story synchronization scripts | focused Python tests, then core suite |
| Broad release candidate | validation, build, core suite, and release AI exploration |

Real Mobile Safari and physical touch hardware remain manual checks when a change depends on browser- or device-specific behavior; Chromium emulation is not evidence that those environments work.
