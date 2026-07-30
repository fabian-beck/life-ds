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
system — data model, both generation pipelines with their steps, prompts, output
schemas and recorded timings, the application, localization and testing. Open it
to orient yourself before changing a generation script.

Its prose is authored in `docs/report/report.md`; everything factual is computed
at build time, so never hand-edit `index.html`. Run
`python scripts/generate_report.py --check` after changing a generation script or
the report source.

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

### Clean Up

Only after confirming that the push succeeded:

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
5. Do not deploy unless the user explicitly requests deployment. Pushing or
   merging to `main` does not deploy this project automatically.
