---
title: Life Data Stories
subtitle: Generating and presenting biographical data stories
description:
  Technical report on the Life Data Stories system—its artifact schemas, its two
  generation pipelines and its interface.
abstract:
  Life Data Stories transforms encyclopedic biographical prose into structured
  data stories: sequences of full-screen slides in which a life is presented at
  once as narrative text, an event timeline, a geographic map and a social
  network. A second story type, the meta story, traces a theme across several
  lives and presents it as one continuous document in which the same three
  encodings are read by scrolling. The system separates two concerns:
  generation is performed offline by staged Python pipelines that combine
  language-model inference with deterministic transformation; presentation is
  performed by a client-side application that reads static files and performs
  no inference of its own.
---

::: toc
:::

## Introduction

Encyclopedic biography is a rich and well-sourced account of a life, written as
continuous prose. Its temporal, geographic and relational structure is present
throughout the text and largely implicit in it: dates are given at whatever
precision the record supports, places under the names they carried at the time,
and relationships in subordinate clauses distributed across sections. A reader
who wants the shape of the life—its phases, its movements, the people who
recur in it—reconstructs that shape while reading.

Life Data Stories makes the shape explicit and presentable. It derives from the
source prose a set of discrete events, each with a resolved date, the modern
coordinates of its place, the persons involved, an illustration and the sources
that support it; it groups those events into the phases of a life; and it
presents the result simultaneously as narrative text, as a chronology, as a
geography and as a social network. The same derivation applied across several
biographies yields a meta story, in which a theme is traced through the lives
that share it.

The operations this requires are interpretive. Selecting the episodes that
constitute a life, identifying the modern place a historical toponym denotes,
and judging which relationships are constitutive of a career are decisions
about meaning, and at the scale of a corpus they are made by a language model.

The system is accordingly built in two parts that meet only at the data.
Generation runs offline as a dependency graph of individually addressable
steps, in which model inference is interleaved with deterministic
transformation: a step proposes, researches or reviews material, and the steps
around it resolve, cluster, merge and validate what the model returned. What
the graph produces is a set of documents describing one life or one theme. The
interface loads those documents and renders them, so that reading a story is a
matter of presentation alone.

::: decision
**One record, several encodings.** The event is the unit of both the narrative
and the data. Prose, timeline, map and network encode one derived record, and
therefore agree by construction.

**Derive bottom-up, then revise top-down.** Each step observes its own slice,
which is locally sound and globally repetitive. A closing pass reads the
assembled story and distinguishes the text that describes a component from the
text that surrounds it.

**Themes are second-order.** A meta story is derived from finished biographies.
The corpus is a graph: every life is reachable from each theme it joins.

**Every story looks like itself.** Palette, typography and pattern are
generated per subject and carried in the data, so visual identity travels with
the artifact.
:::

## Architecture

The two halves of the system communicate exclusively through the file system,
and each is decomposed along a different axis. Generation is decomposed into
*steps*: individually addressable units of work, {{ pipeline.steps }} in total,
of which {{ pipeline.ai_steps }} issue a prompt to a model and
{{ pipeline.code_steps }} consist of deterministic code or plain HTTP
retrieval. Presentation is decomposed into the units through which a reader
advances: slides in a person's story, sections in a meta story. The two axes
answer different questions. A step is the granularity at which work is cached,
re-run, priced and tested; a slide or section is the granularity at which the
reader's attention is directed and at which a position in a story becomes an
address.

### A taxonomy of steps

Each step belongs to one of four kinds. The classification partitions the
pipeline by failure mode and by cost, and thus determines what may be re-run
freely, what must be paid for, what depends on the availability and stability
of an external service, and what can be verified by assertion.

::: kindlegend
:::

The ratio between the kinds is the principal design variable. Inference steps
are what make the task possible; deterministic steps are what make the result
testable. The system therefore confines non-determinism to the steps that
genuinely require judgment and keeps the remainder—clustering, geocoding,
chapter fitting, network merging, translation bookkeeping—deterministic, so
that everything downstream of an inference is reproducible and assertable.

## Data model

Four artifact families carry everything the application reads, distributed over
{{ pipeline.artifacts }} declared files and directories. Each is a denormalized
document rather than a row in a normalized schema, because the document is the
unit at which generated material is inspected, corrected and regenerated.

The **person registry** holds the identity and portrait of each subject, and
stands in one-to-one correspondence with the per-person directories that hold
everything else: a directory without a registry entry is invisible to the
interface, and an entry without a directory is a broken reference.

The **life events** document is the narrative spine of a biography: dated
events with locations, involved persons, sources, images and a typed icon,
optionally grouped into chapters that name the phases of a life, together with
a concluding statement. It is also the reference document from which all
localized copies derive.

The **ego network** document records the subject's relationships as typed and
weighted edges, each with a period, a strength and a supporting description. It
is generated independently of the narrative, so a biography may exist before
its network does.

The **meta story** document is a second-order artifact. It describes a theme
across several biographies and is the only family whose inputs are other
artifacts of this system rather than an external source, which makes the
coupling between the two pipelines a coupling of files rather than of code.

::: artifacts lane=person
:::

::: artifacts lane=meta
:::

## Generation

Both pipelines are directed acyclic graphs rather than sequences, and the
figures below draw them as such. A step's vertical position is the length of
the longest chain of data dependencies reaching it, so steps drawn side by side
are genuinely independent and may execute in either order. The two graphs
together declare {{ pipeline.edges }} dependency edges, each labeled with the
data that travels along it, and {{ pipeline.groups }} named concerns that the
layout aligns into vertical strands.

The pipelines instantiate a common pattern: material is first derived bottom-up
by steps that each observe only their own slice of the subject, and is then
revised top-down by a step that observes the assembled artifact. The pattern
exists because locally optimal generation is globally redundant. A phase that
sees only the social graph will describe the social graph, and so will the
phase that later writes the surrounding prose, unless some step is given the
whole document and the explicit task of distinguishing the two registers.

The two subsections that follow present the same class of figure at the same
scale, so that the pipelines may be compared directly. The personal pipeline is
deeper than its width suggests and the meta pipeline is wider than its depth
suggests, and that asymmetry is the substance of the architecture.

### Personal story pipeline

One biography, end to end: {{ pipeline.person_steps }} steps distributed over
{{ pipeline.person_layers }} dependency layers, beginning at an encyclopedia
article and terminating in a translated, illustrated and individually styled
story.

The salient structural feature is the fork that follows source acquisition.
Once the material is cached and narrowed, the narrative branch, the imagery
branch, the network branch and the visual-identity branch cease to depend on
one another, and they reconverge only at review and translation. Branch
independence bounds the consequences of a failure to a single concern and makes
partial regeneration—new imagery for an unchanged narrative, a revised palette
for an unchanged network—an ordinary operation rather than a full rebuild.

::: pipeline lane=person
:::

::: note
Events are researched individually rather than in a single call. This is the
most consequential granularity decision in the pipeline: latency and token
consumption scale linearly with the number of events, and the recorded timings
below show the effect directly. It is retained because a per-event call
receives a focused prompt and a small output schema, and because a failed or
malformed response is then confined to a single event.
:::

::: steptable lane=person
:::

### Meta story pipeline

A theme across many lives: {{ pipeline.meta_steps }} steps distributed over
{{ pipeline.meta_layers }} layers. The pipeline consumes the output of the
personal pipeline rather than external sources, which is why its figure begins
with unattributed file nodes that no step of its own graph produces.

Where the personal pipeline forks once, this one maintains two long independent
branches—the social network and the geographic map—each of which runs to
completion on its own. Each branch follows the same internal progression: a
deterministic derivation from existing data, an inference pass that reviews or
weights the derived structure, and a narration pass that writes the text bound
to it. The branches meet only in the composition step, which re-reads the
assembled story and separates its two registers of text: captions bound
one-to-one to something the reader is looking at, and article prose that
supplies the context surrounding what the components encode.

::: pipeline lane=meta
:::

::: steptable lane=meta
:::

### Models, prompts and structured output

The generation side uses {{ pipeline.models }} across
{{ pipeline.call_sites }} call sites. Models are selected per call site rather
than globally, so that a phase whose cost is dominated by volume and a phase
whose quality determines the whole artifact need not share one setting.

::: modeltable
:::

Reasoning effort is configured per call site, because the calls differ in kind.
Proposing the significant events of a life is an
inference problem and receives a reasoning budget; researching an event that
has already been selected is a retrieval and writing problem and deliberately
receives none.

Prompt text is constructed in Python functions rather than stored as templates
or configuration—{{ pipeline.prompt_builders }} such functions across the
scripts—since prompts require conditionals and injected data far more often
than they require editing outside a code review. Structured output is declared
as Pydantic models, {{ pipeline.schemas }} classes in total, which converts
open-ended text generation into slot filling: the required shape of a response
is a type rather than a paragraph of instructions, and validation occurs before
any value reaches an artifact. Model output is then applied deterministically.
Identifiers are matched against existing entities, unknown references are
discarded with a warning, and coordinates, URLs and graph structure are copied
rather than accepted, so that a defective response stays confined to the field
it fills.

::: schemalist names=LifePlan,EventDetails,EgoNetwork,MetaStoryPlan
The four schemas central to the two pipelines—the plan of a life, a single
researched event, a person's ego network and a meta story's plan—expanded field
by field from the Pydantic models the API is asked to populate.
:::

## Cost and latency

Timings and token counts are obtained by instrumentation rather than
estimation. A recording wrapper around either pipeline captures every model
call—prompt, response, wall-clock duration and reported token usage—and the
aggregates below are computed per step from those records. The recorded corpus
presently comprises {{ runs.count }} runs, {{ runs.calls }} model calls,
{{ runs.minutes }} minutes of API time and {{ runs.tokens }} tokens.

::: limitation
Recording is opt-in and rewrites the subject's data files, so the recorded set
is small. It supports statements about the distribution of time and tokens
across the steps of an observed generation; statements about the expected cost
of an arbitrary subject would require a sample.
:::

::: runfigures lane=person
:::

::: runtable lane=person
:::

::: runfigures lane=meta
:::

::: runtable lane=meta
:::

## Interface

The reading side is a mobile-first Svelte and Vite application that loads the
generated documents as static assets and renders them directly. It presents the
same three encodings of a life—time, space and relation—in two reading modes,
corresponding to the two story types. A person's story is a bounded sequence
advanced one unit at a time, which suits material that has a canonical order
and a natural unit, the event. A meta story is a continuous document advanced
by scrolling, which lets its order follow the argument the composition makes
across several lives.

Application state is carried in the URL throughout: language, story, position
within it, and the open or closed condition of the network view. Every position
in a story is therefore a citable address, movement within a story replaces the
history entry while movement between stories pushes one, and a reader arriving
at a meta story from a person's story is returned to the position from which
they left.

### Person stories

A person's story is a horizontal sequence of full-screen, scroll-snapped
slides of four kinds. An overview slide opens with the generated portrait, the
lifespan, the principal roles and a summary. Chapter slides mark the phases of
the life, so that the transition between phases is itself an event in the
reading. Event slides are the substance: a title, a date, a long-form
description, the images attached to that event, the persons involved rendered
as inline chips, and the sources from which the event was researched. A
concluding slide closes the life and offers cards for related subjects, which
makes the corpus traversable from within any one story rather than only from
the landing page.

The three encodings are attached to this sequence rather than displayed beside
it. A persistent timeline maps every event to its position in the life, bands
the chapters, and doubles as the navigation control. A map built on MapLibre
and Protomaps locates the events whose places could be resolved, with the
camera following the reader rather than the reader panning the map; the
basemap is deliberately label-free, since the story supplies the toponyms. The
ego network is presented on demand as a force-directed graph of the subject's
documented relationships, typed and weighted as the artifact records them.
Images open in a lightbox that pages through the story's illustrations as a
single gallery.

Each story additionally carries a generated visual identity—palette,
typography and background pattern—injected as CSS custom properties, so that
the design system is data rather than code and each subject is presented in a
visual register of its own.

### Meta stories

A meta story presents a theme across several biographies, and its structure is
the one the composition step imposes: an opening scene, a timeline
section, a network section, a map section, a conclusion, and a closing grid of
the people the story is built from. Each of the three middle sections pairs
running prose with one interactive component, and each carries the article
layer's context rather than a recapitulation of what the component already
shows.

The two visual sections are scrollytelling constructions, in which the
component is pinned while narration cards scroll over it and select what it
displays. In the network section, the force-directed graph is laid out once and
then frozen—the simulation is advanced to convergence in the background before
the graph is revealed—so that the narration directs the reader's attention
while the graph holds still. Each card corresponds to one
detected circle of the graph: its members remain lit while the remainder of the
graph darkens. In the map section, a non-interactive map is pinned full-bleed
and the camera flies to each geographic stop as its card enters the viewport,
zooming to a place or fitting a bounding box according to how dispersed the
stop's events are. Here the basemap keeps its labels, since the section is
about where the theme was located.

The closing card grid links to the individual stories of every person the
theme is built from, and each person's story links back. The two story types
are thus two views of one corpus: a meta story is navigable into the
biographies it draws on, and a biography is reachable from every theme in which
it participates.

## Localization

Every generated document exists in {{ app.locales }} languages
({{ app.languages }}). Translation is a generation step rather than an
interface concern: the English document is produced first, a glossary pass then
fixes the rendering of names and recurring terminology once, and only
afterwards is each document translated, so that a subject carries one
designation throughout a story.

Translated payloads carry a fingerprint of the source fields they cover, which
makes staleness computable rather than assumed: a translation is current if and
only if its fingerprint matches the English text it was derived from. The
consequence for development is direct. A new translatable field must be added
to the payload conditionally, since including it unconditionally invalidates
every existing translation in the corpus at once.

