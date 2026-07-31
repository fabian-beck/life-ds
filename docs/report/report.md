---
title: Life Data Stories
subtitle: A technical report on generating and presenting biographical data stories
description:
  Technical report on the Life Data Stories system—its data model, its two
  generation pipelines, the reader-facing application, and how this document
  keeps itself honest.
abstract:
  Life Data Stories turns encyclopedia articles into biographical data stories:
  full-screen, scroll-snapped slides carrying an event timeline, a map and a
  social network. The system has two halves. A set of Python pipelines does the
  writing—sourcing material, proposing and researching life events, deriving
  networks, clustering places, generating a portrait and a visual identity, then
  translating everything—and a mobile-first Svelte application does the
  reading.

  This report describes both, and is itself generated. Every count, model name,
  prompt, output schema, dependency graph and timing on this page was measured
  at build time from the repository; only the prose was written by hand. That
  split is the point: the parts of a system that change weekly are the parts
  documentation gets wrong, so they are not written down here at all.
---

::: toc
:::

## Introduction

A biography is not a dataset, and that is the problem this system exists to
work on. Encyclopedia prose is continuous, hedged and unevenly detailed; a data
story needs discrete units with dates, places, people and images attached to
them, each one confident enough to fill a screen on its own. Turning the first
into the second is the whole job, and it cannot be done by parsing—it needs
judgement about what mattered in a life, and that judgement has to be auditable
afterwards.

The system currently holds {{ data.people }} biographies carrying
{{ data.events }} life events between them—about {{ data.events_per_person }}
per person—and {{ data.meta_stories }} meta stories, which are themes traced
across several lives at once. The generation side is a set of command-line
Python pipelines that reach a language model at {{ pipeline.call_sites }}
distinct places; the reading side is a Svelte application that never runs
them.

::: decision
The pipelines write plain JSON files into `data/`, and the application reads
them as static assets. There is no database, no server and no build-time
transform between the two.

**Why:** it makes every generated artefact reviewable in a diff. A questionable
event, a wrong date or an unflattering network edge shows up in `git diff` as
text, gets fixed by hand or by regeneration, and is committed like code. A
database would have hidden all of that behind a migration.
:::

## System overview

The two halves meet only at the file system, and each half is organised around a
different unit. The generation side is organised around *steps*: discrete,
individually addressable units of work, {{ pipeline.steps }} of them documented,
of which {{ pipeline.ai_steps }} send a prompt to a model and
{{ pipeline.code_steps }} are ordinary deterministic code or plain HTTP fetches.
The reading side is organised around *slides*.

### The four kinds of step

Every step is one of four kinds, and the distinction is load-bearing rather than
decorative: it says what can be re-run cheaply, what costs money, what needs a
network, and what can be tested with an assertion.

::: kindlegend
:::

The mix matters more than the totals. A pipeline that is nothing but model calls
cannot be tested; one with no model calls could not do this job at all. Keeping
the deterministic steps deterministic—clustering, geocoding, chapter fitting,
network merging—is what makes the expensive steps small enough to reason
about.

## Data model

Four artefact families carry everything the application reads, spread over
{{ pipeline.artifacts }} declared files and folders.

A **person registry** entry in `data/persons.json` holds the identity and
portrait of one subject; there are {{ data.registry_entries }} of them, and the
count is expected to match the {{ data.people }} folders under `data/people/`,
because a folder with no registry entry is invisible to the application and an
entry with no folder is a broken link.

A **life events** file is the narrative spine: dated events with locations,
involved people, sources, images and an icon, optionally grouped into chapters
that name the phases of a life, plus a conclusion.

An **ego network** file records who a person was connected to and how. Across
the corpus these hold {{ data.connections }} connections over
{{ data.networked_people }} biographies—the small shortfall against
{{ data.people }} is what a network step that has not been run yet looks like.

A **meta story** file is a theme across several biographies, and is the only
artefact that reads from other artefacts rather than from an external source.

::: artifacts lane=person
Every file the personal pipeline touches, with the steps that write and read it.
:::

::: artifacts lane=meta
The meta pipeline reads what the personal pipeline wrote. Files with no writer
in this table are produced by the other pipeline, which is where the two are
coupled—on disk, not in code.
:::

## Generation

Both pipelines are directed acyclic graphs, not sequences, and the charts below
draw them as such. A step's vertical position is the longest chain of real data
dependencies reaching it, so two steps drawn side by side are genuinely
independent and could run in either order. Across both pipelines there are
{{ pipeline.edges }} declared dependency edges, each labelled with the data that
travels along it, and {{ pipeline.groups }} named concerns that the layout
aligns into vertical strands.

The two subsections that follow are the same kind of figure at the same scale,
which is deliberate: the pipelines are meant to be compared. The personal
pipeline is deeper than it looks and the meta pipeline is wider than it looks,
and that difference is the architecture.

### Personal story pipeline

One biography, end to end: {{ pipeline.person_steps }} steps in
{{ pipeline.person_layers }} dependency layers. It starts at a Wikipedia article
and ends at a translated, styled, illustrated story.

The shape worth noticing is the fork after sourcing. Once the source material is
cached and narrowed, the narrative branch, the imagery branch, the network
branch and the visual-identity branch stop depending on each other entirely.
Everything reconverges only at review and translation.

::: pipeline lane=person
:::

::: note
Events are researched one at a time rather than in one large call. That is the
single most expensive decision in this pipeline and the one most often
questioned, so it is worth stating plainly: a per-event call gets a focused
prompt, a small output schema and an error that ruins one event instead of a
whole biography. The cost shows up directly in the recorded timings below.
:::

::: steptable lane=person
:::

### Meta story pipeline

A theme across many lives: {{ pipeline.meta_steps }} steps in
{{ pipeline.meta_layers }} layers. It consumes the personal pipeline's output
rather than external sources, which is why its chart begins with grey file nodes
that nothing on the page produces.

Where the personal pipeline forks once, this one runs two long independent
branches—the social network and the geographic map—that never see each
other's results, and only meet in the composition step that rewrites every text
in one voice.

::: pipeline lane=meta
:::

::: steptable lane=meta
:::

### Models, prompts and structured output

The generation side uses {{ pipeline.models }}. No model name is written down in
this report—the table below is read from the call sites themselves, so a model
swap in the code appears here on the next build and cannot be forgotten.

::: modeltable
:::

Reasoning effort is set per call site rather than globally. Proposing the events
of a life is a reasoning problem and gets a reasoning budget; researching one
already-chosen event is a retrieval-and-writing problem and deliberately gets
none.

Prompt text is not stored in templates or configuration; it is built in Python
functions, {{ pipeline.prompt_builders }} of them, because prompts need
conditionals and injected data far more than they need to be edited without a
code review. Structured output is declared as Pydantic
models—{{ pipeline.schemas }} classes across the scripts—so the shape the model
must return is a type, not a paragraph of instructions.

::: schemalist names=LifePlan,EventDetails,EgoNetwork,MetaStoryPlan
The four schemas at the heart of the two pipelines—the plan of a life, one
researched event, a person's ego network and a meta story's plan—expanded field
by field from the Pydantic models the API is asked to fill in.
:::

## Cost and latency

Timings and token counts on this page come from real generations captured by
`scripts/record_pipeline_run.py`, which wraps the pipelines and writes each
call—prompt, response, duration, usage—to `docs/report/runs/`. There are
currently {{ runs.count }} recorded runs holding {{ runs.calls }} model calls,
{{ runs.minutes }} minutes of API time and {{ runs.tokens }} tokens.

::: limitation
Recording is opt-in and rewrites the subject's data files, so the recorded set
is small and not a benchmark. It answers "where does the time actually go" for
one real generation; it does not answer "how long does a person take on
average".
:::

::: runfigures lane=person
:::

::: runtable lane=person
:::

::: runfigures lane=meta
:::

::: runtable lane=meta
:::

## The application

The reading side is a mobile-first Svelte 5 and Vite application. Stories are
full-screen, scroll-snapped slides; routing is URL-based, so any slide is a
shareable address.

Three visualisations carry the data beyond prose: a timeline of the events, a
MapLibre and Protomaps map of their places, and a force-directed social network.
Each person's story also carries a generated visual identity—colours, fonts
and a background pattern—injected as CSS custom properties, which is why two
stories in this system do not look alike.

::: aside
This section is the thinnest part of the report, and knowingly so. The
application is described here in prose only, because the build measures nothing
about it that is worth stating. Component-level computed content—a route map, a
props graph, a slide-type inventory—would be the natural next extension, and
would slot in as new components without touching this text.
:::

## Localization

Every generated document exists in {{ app.locales }} languages
({{ app.languages }}). Translation is a pipeline step rather than a UI concern:
the English document is generated first, a glossary fixes the translation of
names and recurring terms once, and only then is each document translated, so
the same person is not called two different things in two slides.

Translated payloads are fingerprinted against the fields they cover. Adding a
new translatable field therefore has to be done conditionally, or every existing
document is marked stale at once.

## Validation and testing

The automated suite is intentionally small, and does not try to test generated
content, which is not deterministic. It tests the machinery that makes generated
content trustworthy—that the static extraction really reads the source, that
the dependency graph really is acyclic, that the drift check really fails.

### Drift as a build error

The largest risk to a document like this is not being wrong; it is being
plausibly out of date. So the checks that matter run at build time and fail it.

::: coverage
:::

A step whose function was renamed, a prompt symbol that no longer exists, a
dependency cycle, a group spanning both pipelines, a citation to a measurement
that was deleted, a component the page cannot render—each of these stops the
build rather than degrading the page.

## Operations

Both pipelines are ordinary command-line programs with an option surface read
from their own argument parsers.

::: cliflags script=generate_person.py
:::

::: cliflags script=generate_meta_story.py
:::

## About this document

This report is compiled by `scripts/generate_report.py` from two sources that
never mix: the prose in `docs/report/report.md`, and the repository itself.

The authoring surface is small. Prose is Markdown. A measurement is cited
inline, and the compiler substitutes it along with the place it was measured:

```text
The system currently holds {{ data.people }} biographies.
```

A computed block is mounted by name, with its own authored lead-in kept above
it:

```text
::: pipeline lane=person
Click any step for its prompt and schema.
:::
```

Section numbers, the contents, and every figure and table number are derived
from document order, so moving a section renumbers the report and its captions
together.

::: decision
No number appears literally in the Markdown source, and no prose appears in the
Python.

**Why:** the two rot at different speeds. Counts, models, prompts and timings
change with every commit and are therefore measured, never transcribed. Reasons,
trade-offs and admissions of what is missing do not change with a commit and
cannot be derived from anything—so they are written by hand, and the build
refuses to render a claim it cannot resolve.
:::

::: buildinfo
:::
