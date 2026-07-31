# Agent Instructions

These instructions are the shared source of truth for Codex, Claude Code, and
other coding agents working in this repository.

## Project

Life Data Stories is a mobile-first Svelte 5 and Vite application for
biographical stories presented as full-screen, scroll-snapped slides. It uses
MapLibre GL, Protomaps, and `svelte-spa-router`.

Important locations:

- `src/`: Svelte application code
- `data/`: person registries, life events, networks, and meta stories
- `scripts/`: Python data-generation and maintenance tools
- `tests/`: Python and Playwright tests
- `public/`: static assets and generated portraits

Detailed project information is intentionally kept out of this always-loaded
file. Read only the references relevant to the current task:

- [Domain and data models](docs/agent/domain-and-data-models.md)
- [Project structure and UI](docs/agent/project-structure-and-ui.md)
- [Data generation and localization](docs/agent/data-generation-and-localization.md)
- [Development reference](docs/agent/development-reference.md)

`docs/report/index.html` is a generated, interactive technical report on the
system—data model, both generation pipelines with their steps, prompts, output
schemas and recorded timings, the application, localization and testing. Open it
to orient yourself before changing a generation script.

Its prose is authored in `docs/report/report.md`; everything factual is computed
at build time, so never hand-edit `index.html`. Run
`python scripts/generate_report.py --check` after changing a generation script or
the report source.

`npm run report:pdf` prints the built page to `docs/report/report.pdf`, the
fixed rendition a published version is uploaded as. It is generated on demand
and not committed.

## Common Commands

```powershell
npm install
npm run dev
npm run validate
npm run build
npm run test:core
npm run test:interface
```

Python tooling uses the repository `.venv`. Run focused Python tests and
type-checking when changing Python code:

```powershell
python -m pytest
npm run type-check:py
```

The intentionally small automated suite and the Codex/Claude exploratory user
testing skill are documented in [Testing strategy](docs/testing-strategy.md).

The development server is normally already running in this environment.

## Git Workflow

Every new agent session must use a unique `agent/<session>` branch in a
separate Git worktree created from `origin/main`. Agents must not edit in the
primary `main` worktree and must not share a branch or worktree with another
session.

### Start a Session

From the primary repository:

```powershell
git fetch origin
git worktree add "..\life-ds-<session>" -b "agent/<session>" origin/main
Set-Location "..\life-ds-<session>"
```

Use a descriptive session name such as `2026-07-26-fix-import`.

### Work and Validate

- Change only files within the current task's scope.
- Preserve unrelated and pre-existing working-tree changes.
- Stage specific files instead of using `git add .`.
- Commit completed work on the session branch.
- Before integration, require a clean `git status --short`.

Rebase and run checks appropriate to the change:

```powershell
git fetch origin
git rebase origin/main
npm run validate
npm run build
```

Run `npm run test:interface`, Python tests, and other focused checks when the
affected area requires them.

### Integrate Directly into Main

Integration is part of the task, not an optional extra. A session is only
finished when its commits are on `origin/main`, or when the agent has reported
that they are not and why. Leaving work on the session branch without saying so
is the failure mode this section exists to prevent.

After successful validation:

```powershell
git push origin HEAD:main
```

Do not create a pull request and never force-push to `main`.

The push is the concurrency check. If it is rejected because `main` advanced,
fetch, rebase onto the new `origin/main`, rerun the relevant checks, and retry:

```powershell
git fetch origin
git rebase origin/main
# Rerun relevant validation.
git push origin HEAD:main
```

Retry this loop until the push succeeds. A rejected push is a normal race, not
a reason to stop.

Stop and report instead of pushing when any of these hold:

- The rebase produces conflicts that cannot be resolved with confidence.
- Validation fails after the rebase, and the failure is not clearly unrelated
  to the change.
- The push keeps being rejected after several rebase-and-retry rounds.
- The remote rejects the push for a reason other than `main` having advanced,
  such as missing permissions or a protected branch.

In those cases leave the commits on the session branch, do not delete the
worktree, and say exactly what blocked the merge so a human can finish it.

Verify the merge rather than assuming it. After the push reports success:

```powershell
git fetch origin
git log origin/main --oneline -1
git status --short --branch
```

The session's last commit must appear on `origin/main`. Treat this check, not
the absence of an error message, as the proof that integration happened.

### Clean Up

Only after the verification above shows the session's commit on `origin/main`:

```powershell
Set-Location "<primary-repository-path>"
git fetch origin
git switch main
git pull --ff-only origin main
git worktree remove "..\life-ds-<session>"
git branch -d "agent/<session>"
```

If the primary worktree contains uncommitted changes, do not switch branches,
pull, delete, or modify those changes. Leave primary-worktree cleanup to its
owner.

## Code and Data Conventions

- Use camelCase for JavaScript variables and functions.
- Use PascalCase for Svelte component filenames.
- Use snake_case for person IDs and Python variables and functions.
- Use kebab-case for CSS classes.
- Write English prose in American English—the report, documentation, comments,
  code identifiers and generated English text alike (color, artifact, labeled).
- Follow existing Svelte 5 patterns and shared stores.
- Keep person data synchronized across its registries and localized files.
- Do not edit generated output when the source data or generator is the proper
  place for a change.
- Preserve source attribution for biographical data and images.

Consult the relevant reference document before changing schemas, translation
generation, maps, networks, timelines, or meta-story composition.

## Definition of Done

Before reporting completion:

1. Review the diff for scope and accidental generated or unrelated changes.
2. Run validation proportional to the change.
3. Confirm new behavior has tests when practical.
4. Report checks run and any checks not run.
5. End every summary with an explicit merge status line, described below.
6. Do not deploy unless the user explicitly requests deployment. Pushing or
   merging to `main` does not deploy this project automatically.

### Report the Merge Status

The last line of every summary must state whether the work reached
`origin/main`. Never leave this implicit, and never let a description of the
code changes stand in for it. Use one of these forms:

- `Merge status: merged into main` — the push succeeded and the verification
  above confirmed the commit on `origin/main`.
- `Merge status: NOT merged — <reason>` — the work is committed on
  `agent/<session>` but not on `main`. Name the blocker (conflict, failing
  validation, rejected push, task incomplete) and what a human needs to do
  next.
- `Merge status: nothing to merge` — the task produced no commits, such as a
  question answered or an investigation with no code change.

A session that stops early, runs out of scope, or hands back for review still
reports its merge status. "NOT merged" is an acceptable outcome; silence about
it is not.
