# Testing Strategy

This prototype uses a deliberately small deterministic core and AI-led exploratory testing. The goal is fast feedback while the product changes, not exhaustive scripted regression coverage.

## Deterministic core

Run the complete core with:

```bash
npm run test:core
```

It contains only safeguards for high-value failures:

- one Playwright visitor journey in desktop and mobile Chromium, covering the landing page, search, opening and navigating a person story, the network modal, returning home, and entering and leaving a collection;
- two boot checks for a browser that refuses site data, where an unguarded storage access takes the whole application down with no error on screen;
- the browser-independent person-name matcher cases, run once rather than in every browser project; and
- focused Python regression checks for portrait file validation, keeping curated meta-story references synchronized with person events, and holding the person registries, per-person directories, and style registry to the same set of people.

Do not add a deterministic test merely to increase coverage. Add one only for a costly, repeatable regression that is difficult to notice through exploration, or for a silent data-integrity failure. Prefer extending the one core journey over adding another UI scenario. Remove obsolete regression tests when their risk is no longer material.

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
