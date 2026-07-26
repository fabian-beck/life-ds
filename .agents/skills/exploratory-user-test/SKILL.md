---
name: exploratory-user-test
description: Interactively explore the running Life Data Stories app as an intelligent user and produce an evidence-backed bug and improvement report. Use only when explicitly asked to run an exploratory, smoke, focused, or release user test.
---

# Exploratory User Test

Test the application as a user, not as a scripted selector runner. Do not edit
application code during this workflow. Read
[`references/charters.md`](references/charters.md),
[`references/product-risks.md`](references/product-risks.md), and
[`references/report-template.md`](references/report-template.md) before testing.

## Inputs

Infer these from the request when possible:

- mode: `smoke`, `focused`, or `release` (default: `focused`);
- target URL (default to the already-running local development URL, otherwise
  start the documented development server);
- feature or change to emphasize; and
- output directory: `test-results/exploratory/<UTC timestamp>/`.

If a nonessential input is absent, state the assumption and proceed. Ask only
when the target cannot be identified safely.

## Workflow

1. Read `docs/testing-strategy.md` and relevant files under `docs/agent/`.
2. For focused mode, inspect `git status --short` and the current diff. Map the
   changed files to product risks. Do not modify or discard changes.
3. Confirm the target responds. Record commit, mode, target, browser, viewport,
   language, and start time.
4. Choose a persona and charters proportional to the mode. Vary people and
   collections instead of always choosing Ada Lovelace. Include one adjacent
   journey in focused mode.
5. Use the available browser automation interactively through visible text,
   roles, and user-facing controls. Do not turn the charter into source-level
   selectors or simply run the deterministic Playwright suite.
6. Observe navigation, layout, content, feedback, console errors, and failed
   requests. Capture screenshots for suspected visual or interaction findings.
   Store all generated evidence only in the output directory.
7. Reproduce every suspected bug once from a known state. If it cannot be
   reproduced, label it `observation`, not `confirmed`.
8. Write `report.md` using the report template. Separate defects from
   improvements, describe untested scope, and include positive observations.

## Operating rules

- Do not submit forms or follow links that create external side effects.
- Do not expose secrets, personal data, or unrelated local files in artifacts.
- Do not claim support for a browser or device that was only emulated.
- Do not silently fix findings. Offer implementation only after reporting.
- Prefer a small number of well-evidenced findings over speculative lists.
- Stop and report a blocked check if the application cannot be reached or the
  required browser capability is unavailable.

## Completion

Return the report path, tested scope, count by severity, top three next actions,
and any blocked or deliberately omitted checks. A clean session with no bugs is
valid; report what was actually explored and the evidence used.
