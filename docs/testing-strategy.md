# Testing Strategy

This prototype uses a smoke test, a set of pure-function checks, and AI-led exploratory testing. The goal is fast feedback while the product changes, not exhaustive scripted regression coverage. The interface is reviewed by an agent that looks at it, not by a script that asserts selectors, so the automated suite is held to a few seconds and the product review is the exploratory run.

## Deterministic core

Run the complete core with:

```bash
npm run test:core
```

The whole run finishes in about ten seconds and contains three things:

- one Playwright smoke test at a phone viewport, `tests/smoke.spec.js`: the landing page, the search, opening a person story, moving from the chapter slide to the first event, and returning to the filtered landing page, with any script error or same-origin 404 along the way failing the run;
- the browser-independent pure functions — the person-name matcher, the date and label helpers, the description and depth-prose builders — in a `logic` project with no browser at all; and
- focused Python regression checks for the generation scripts and for the data they write: portrait file validation, keeping curated meta-story references synchronized with person events, holding the person registries, per-person directories, and style registry to the same set of people, and the technical report's own build.

The smoke test answers one question: does the application still run. Everything a screen decides — layout, gestures, animation, localization, accessibility — is reviewed by AI exploration, which sees the page instead of a selector and finds what no assertion was written for.

### What not to add

Do not add a browser test to increase coverage. A second scripted scenario costs every future run its seconds and pins the markup it reads, and this interface changes faster than such a test pays for itself — explore the change instead. A pure function belongs in the `logic` project, where it costs milliseconds and no browser.

Add a browser assertion only when a regression is costly, silent, and repeatable — something exploration would plausibly walk past twice — and then extend the smoke journey rather than starting a second file. Anything that needs its own viewport, a map, a timed race, or seconds of waiting does not go in it. Remove a check when its risk is no longer material.

Two habits are worth avoiding wherever a test does land, because both read as coverage and neither is:

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

## Fact-checking evaluation

Tests and exploration ask whether the application works. Whether its stories are *true* is a separate question, and it is answered by measurement rather than by assertion: an AI stage extracts every claim a person story makes, a second stage samples those claims and searches the sources the story was generated from for verbatim supporting or contradicting quotes, evaluators judge the sampled claims against that evidence in a standalone page, and a merge script reports the verdicts, the defect rate, and the agreement between evaluators. It is internal, deployed nowhere, and run when a number for the corpus is wanted, not on every change. See [evaluation/README.md](../evaluation/README.md).

## Choosing the right check

| Change | Required feedback |
| --- | --- |
| Documentation or agent workflow | formatting plus a dry review of instructions |
| UI behavior or styling | validation, build, core suite, and focused AI exploration |
| Person-name matching | core suite |
| Portrait or meta-story synchronization scripts | focused Python tests, then core suite |
| Broad release candidate | validation, build, core suite, and release AI exploration |
| Generation prompts or data quality | a fact-checking round on the affected people |

The core suite is cheap enough to run on every change; it is never the evidence that an interface change works. That evidence is an exploratory run.

Real Mobile Safari and physical touch hardware remain manual checks when a change depends on browser- or device-specific behavior; Chromium emulation is not evidence that those environments work.
