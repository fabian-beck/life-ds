---
title: Life Data Stories
subtitle: Generating and presenting biographical data stories
authors:
  Fabian Beck | University of Bamberg | https://www.uni-bamberg.de/en/vis/team/prof-dr-fabian-beck/ | 0000-0003-4042-3043
  Leah Mühlöder | University of Bamberg | https://www.uni-bamberg.de/en/vis/team/leah-muehloeder/ | 0009-0000-3510-1686
  Till Nagel | Mannheim University of Applied Sciences | https://services.informatik.hs-mannheim.de/~nagel/ | 0000-0001-5400-091X
description:
  Technical report on the Life Data Stories system—its data model, its two
  generation pipelines and its interface.
abstract:
  Life Data Stories transforms encyclopedic biographical prose into structured
  data stories: sequences of full-screen slides in which a life is presented at
  once as narrative text, an event timeline, a geographic map, and a social
  network. A second story type, the meta story, traces a theme across several
  lives and presents it as one continuous document in which the same three
  encodings are read by scrolling. The system separates two concerns:
  generation is performed offline by staged Python pipelines that combine
  language-model inference with deterministic transformation; presentation is
  performed by a client-side application that reads what those pipelines
  produced and performs no inference of its own.
---

::: teaser
:::

::: toc
:::

## Introduction

[[sources|Encyclopedic biography]] is a rich and well-sourced account of a life, written as continuous prose in long-form articles. Reading a life in that order is natural, but it keeps every other point of access in the background. The biography's temporal, geographic, and relational structure is present throughout the text, yet rather implicit, available only in the order the article takes. A reader who wants to explore that structure—the phases of a life, its movements, the people who recur in it—reconstructs it while reading.

Life Data Stories makes that structure explicit and explorable. It derives from the source prose [[events|a set of discrete events]], each with a resolved date, a place located on a modern map, the persons involved, and the illustrations available for it. It groups those events into the phases of a life and presents the result simultaneously as [[prose|narrative text]], as [[timeline|a chronology]], as [[map|a geography]], and as [[graph|a social network]]. The same derivation applied across several biographies yields [[meta-story|a theme]]: an idea traced through the lives that share it. A theme is presented as [[sections|a meta story]], one continuous document that carries the same encodings across all of its subjects at once—one timeline with a lane per life, one map, and one network merged from theirs.

Segel and Heer, surveying how data is used to tell stories, place such a presentation on a spectrum between the author-driven, in which a fixed order carries the message, and the reader-driven, in which the audience decides what to look at [@segel2010narrative]. A story in Life Data Stories is author-driven at first glance and reader-driven in its depth. The sequence is fixed when the story is generated and can simply be followed to the end; the timeline that doubles as a control, the network opened on demand, the images as a gallery, and the cards leading into other lives are all available and none of them is required. A meta story is linear in the same way, and at any point along it the lives it draws on are open to be entered. The same three encodings appear at the reader-driven end of that spectrum in VisKonnect, which connects historical figures through the events they have in common [@latif2021viskonnect]: a reader's prompt retrieves the matching events from an event knowledge graph, and an event timeline, an event map, and a relationship graph are shown beside a short answer.

As in VisKonnect, the operations this requires are interpretive. Selecting the episodes that constitute a life, identifying the modern place a historical toponym denotes, and judging which relationships are constitutive of a career are decisions about meaning, and at the scale of a corpus they are made by [[inference|a language model]]. The system is accordingly built in two parts that [[artifacts|connect through the data]]. Generation runs offline as a dependency graph of individually addressable steps, in which model inference is interleaved with deterministic transformation: a step proposes, researches, or reviews material, and the steps around it resolve, cluster, merge, and validate what the model returned. What the graph produces is a set of documents describing one life or one theme. The interface loads those documents and renders them, so that reading a story is a matter of presentation alone.

::: principles
@one-record One record, several encodings
The event is the unit of both the narrative and the data. Prose, timeline, map, and network encode one derived record, and therefore agree by construction.

@bottom-up Derive bottom-up, then revise top-down
Each step observes its own slice, which is locally sound and globally repetitive. A closing pass reads the assembled story and distinguishes the text that describes a component from the text that surrounds it.

@second-order Themes are second-order
A meta story is derived from finished biographies. The corpus is a graph: every life is reachable from each theme it joins.

@own-look Every story looks like itself
Palette, typography, and pattern are generated per story—for a life and for a theme alike—and carried in the data, so visual identity travels with the story rather than with the application.
:::

## Data model

At the core of the approach is the data that connects story generation and the interface, and it is the central abstraction of the system. What goes in is narrow: textual biographies, and nothing else. What comes out is multi-faceted—several structured perspectives on the same biography, each of which can be read on its own, and none of which discards the narrative the prose carried. Some of them are derived directly from the article: <<profile|the subject>> a story is about, the <<events|events>> that constitute a life, the <<narrative|text>> that tells them, and the <<imagery|pictures>> that illustrate them. Others are more interpretive, and are stated by no article as such: the <<places|geography>> a life traces, which resolves historical toponyms to modern coordinates, the <<network|social network>> behind it, and the <<identity|visual identity>> in which it is presented.

::: conceptlegend
:::

## Generation

Both pipelines are directed acyclic graphs rather than sequences, and the figures below draw them as such.^[The `main()` that orchestrates each script is deliberately not drawn as a step. It fixes an execution order without creating a data dependency, and drawing it made every fork read as a chain.] A step's vertical position is the length of the longest chain of data dependencies reaching it, so steps drawn side by side are genuinely independent and may execute in either order. Every edge is labeled with the data that travels along it, and the concerns that span several layers are aligned into vertical strands under a name. The edges are the direct ones only: a dependency that a longer chain already implies is omitted rather than drawn beside it.^[Image matching reads the event skeletons, but it is reached from them through the search planning and the search itself, and the second line said nothing the first did not. What such a step reads is still recorded in its own entry.]

Each step in those figures is an address rather than a label. Opening one gives the record behind it: the function and line that implement it, the model and reasoning effort it resolves, the output schema it fills, what it reads and writes, the steps it needs and feeds, and the prompts it sends. On paper the same records are laid out for every step as an appendix.

That record is measured from the code, but the explanation printed above it is not: each step is described by a model, from its own source, prompt, and output schema, and rewritten whenever one of the three changes.^[The explanation is cached against a fingerprint of exactly those inputs, so a rebuild re-describes only the steps that moved. The description is attributed where it appears, and it is the one place in this report where prose is generated rather than authored or measured—which is also why a model name it repeats out of a source comment is a build error rather than an editorial matter.] It is disclosed as such wherever it is shown, on the same principle the system applies to what it publishes about its subjects.

Each step belongs to one of [[kinds|four kinds]], which is what the figures color it by. The classification partitions both pipelines by failure mode and by cost, and thus determines what may be re-run freely, what must be paid for, what depends on the availability and stability of an external service, and what can be verified by assertion.

::: kindlegend
:::

The ratio between the kinds is the principal design variable. Inference steps are what make the task possible; deterministic steps are what make the result testable. The system therefore confines non-determinism to the steps that genuinely require judgment and keeps the remainder—clustering, geocoding, chapter fitting, network merging, translation bookkeeping—deterministic, so that everything downstream of an inference is reproducible and assertable.

The pipelines instantiate a common pattern ((bottom-up)): material is first derived bottom-up by steps that each observe only their own slice of the subject, and is then revised top-down by a step that observes the assembled story. The pattern exists because locally optimal generation is globally redundant. A phase that sees only the social graph will describe the social graph, and so will the phase that later writes the surrounding prose, unless some step is given the whole document and the explicit task of distinguishing the two registers.

Both graphs end in translation, which makes localization a generation concern rather than an interface one: the English document is written first, a glossary pass then fixes the rendering of names and recurring terminology once per subject, and only afterward is each document translated into every supported language ({{ app.languages }}), so that a subject carries one designation across its events, its network, and its prose. A translated payload carries a fingerprint of the source fields it covers, which makes staleness computable rather than assumed—and which is why a new translatable field has to enter the payload conditionally, since including it unconditionally would invalidate every existing translation at once.

The personal pipeline is deeper than its width suggests and the meta pipeline is wider than its depth suggests. The two figures are drawn at the same scale, so the asymmetry can be read off them directly.

### Personal story pipeline

[[person-pipeline|One biography, end to end]]: from [[sources|an encyclopedia article]] to a translated, illustrated, and individually styled story.

The salient structural feature is the fork that follows source acquisition. Once the material is cached and narrowed, the narrative branch, the imagery branch, the network branch, and the visual-identity branch cease to depend on one another, and they reconverge only at review and translation. Branch independence bounds the consequences of a failure to a single concern and makes partial regeneration—new imagery for an unchanged narrative, a revised palette for an unchanged network—an ordinary operation rather than a full rebuild.^[Three of the branches are addressable from the command line as they are drawn here: `--dataset-only`, `--style-only`, and `--network-only` each run one of them against the subject's existing data.]

::: pipeline lane=person
:::

::: note
Events are researched individually rather than in a single call. This is the most consequential granularity decision in the pipeline, since the number of model calls it makes scales linearly with the number of events. It is retained because a per-event call receives a focused prompt and a small output schema, and because a failed or malformed response is then confined to a single event.
:::

### Meta story pipeline

[[meta-pipeline|A theme across many lives]]. The pipeline consumes the output of the personal pipeline rather than external sources, which is why its figure begins with unattributed nodes that no step of its own graph produces.

Where the personal pipeline forks once, this one maintains two long independent branches—the social network and the geographic map—each of which runs to completion on its own. Each branch follows the same internal progression: a deterministic derivation from existing data, an inference pass that reviews or weights the derived structure, and a narration pass that writes the text bound to it. The branches meet only in the composition step, which re-reads the assembled story and separates its two registers of text ((bottom-up)): captions bound one-to-one to something the reader is looking at, and article prose that supplies the context surrounding what the components encode.

::: pipeline lane=meta
:::

### Models, prompts, and structured output

The generation side uses {{ pipeline.models }}. The model is resolved per [[inference|call site]] rather than fixed globally, so that a phase whose cost is dominated by volume and a phase whose quality determines the whole story need not share one setting. Three text tiers are in use. Composition—the one step that reads a whole assembled story—takes the largest through its own variable; the portrait step takes the image model; and the remaining steps are divided between a reasoning tier and a small one by a single question: whether a wrong answer can quietly become part of the corpus. A step qualifies for the small model when it cannot—when what it returns is validated against entities that already exist, rewritten by a later step, or backed by a deterministic fallback. Selecting which articles to read, researching an event the pipeline has already chosen, matching images to events, curating a theme's event pool, narrating what composition will rewrite, and translating a payload whose structure the merge enforces are all of that kind. Deciding which episodes constitute a life, which people constitute a theme, and whether another step's output is any good are not, and neither is the glossary that fixes how a name is written, because every other document is then matched against its answer by exact name. The division is a claim about verifiability rather than about difficulty, and it is worth stating in those terms: a step is cheap to run precisely when the system can tell that it went wrong.

Reasoning effort is configured the same way, and varies more, because the calls differ in kind. Proposing the significant events of a life is an inference problem and receives a reasoning budget; writing the search strings for an image query is slot filling and receives none. Between them sits the work the small model is asked to do, which mostly consists of holding a threshold or choosing one option out of many—is this event essential to the theme, which of these images is a portrait, which German sentence carries this English one—and receives a small budget for it. The two settings are chosen together: moving a step to the small model is not the same decision as deciding how much it should deliberate, and a step can be moved down one axis while moving up the other.

Both settings are arguments of one call. Every step that fills a schema reaches the API through a single function, which takes the model and the effort and returns either the parsed object or nothing—and this is worth reporting because for a time it was not so. Six steps used a second API that had no effort parameter, and therefore ran at whatever the model does by default while the configuration described effort as a per-step setting; the divergence was invisible in the code, since each call read as a reasonable call. What a shared entry point buys beyond consistency is that a policy can be stated once. The policy that matters here is which failures are worth repeating: a dropped connection or a rate limit is a statement about the moment, and the same request a few seconds later usually succeeds, whereas a malformed request or a refusal is a statement about the request, and asking again spends money to hear it twice. Only the first kind is retried. What a failure *means*, though, stays with the step, because only it knows: article selection falls back to the first candidates in order, an optional section is skipped, a translation is left stale for the parity check to report, and curation stops the run rather than let a theme keep every event of every life it draws on.

Prompt text is constructed in Python functions rather than stored as templates or configuration, since prompts require conditionals and injected data far more often than they require editing outside a code review. Structured output is declared as Pydantic models, which converts open-ended text generation into slot filling: the required shape of a response is a type rather than a paragraph of instructions, and validation occurs before any value is kept. Model output is then applied deterministically. Identifiers are matched against existing entities, unknown references are discarded with a warning, and coordinates, URLs, and graph structure are copied rather than accepted, so that a defective response stays confined to the field it fills.

::: schemalist names=LifePlan,EventDetails,EgoNetwork,MetaStoryPlan
The four schemas central to the two pipelines—the plan of a life, a single researched event, a person's ego network, and a meta story's plan—expanded field by field from the Pydantic models the API is asked to populate.
:::

## Interface

The reading side is a mobile-first Svelte and Vite application that loads the generated data and renders it directly, with no server of its own. It presents the same three encodings of a life—time, space, and relation—in two reading modes, corresponding to the two story types. A person's story is [[slides|a bounded sequence advanced one unit at a time]], which suits material that has a canonical order and a natural unit, the event. A meta story is [[sections|a continuous document advanced by scrolling]], which lets its order follow the argument the composition makes across several lives.

Application state is carried in the URL throughout: language, story, position within it, and the open or closed condition of the network view. Every position in a story is therefore a citable address, movement within a story replaces the history entry while movement between stories pushes one, and a reader arriving at a meta story from a person's story is returned to the position from which they left. Language is a coordinate of that address rather than a setting applied at render time: every document already exists in each supported language, so switching it exchanges the documents a story is read from and changes nothing about how they are presented.

::: screenshot id=landing route=#/en width=1280 height=820 settle=2500 caption="The entry point: a collection carousel, role filters, and the generated portrait of every subject in the corpus"
:::

### Person stories

::: screenshot id=person-story route="#/en/story/alan_turing?event=13" width=390 height=844 wait=".story-view" settle=3500 caption="One event slide on a phone: the dated narrative above, the map beneath it centered on the event's place, the chapter, and the icon timeline along the bottom edge"
:::

A person's story is a horizontal sequence of full-screen, scroll-snapped slides of four kinds. An overview slide opens with the generated portrait, the lifespan, the principal roles, and a summary. Chapter slides mark the phases of the life, so that the transition between phases is itself an event in the reading. Event slides are the substance: a title, a date, a [[prose|long-form description]], the images attached to that event, the persons involved rendered as inline chips, and the sources from which the event was researched. A concluding slide closes the life and offers cards for related subjects, which makes the corpus traversable from within any one story rather than only from the landing page.

The three encodings are attached to this sequence rather than displayed beside it ((one-record)). [[timeline|A persistent timeline]] maps every event to its position in the life, bands the chapters, and doubles as the navigation control. Brehmer and colleagues, surveying timelines for storytelling, separate the choice of how time is represented from how it is scaled and how it is laid out [@brehmer2017timelines]. This one holds its representation and its layout fixed—a single line, one life on it—and changes only its scale as it opens: collapsed, it spaces the events evenly, so that each is an equally reachable control; expanded, it sets each one at the age it falls at, so that the pace of a life—the crowded decade, the quiet one—becomes visible. [[map|A map built on MapLibre and Protomaps]]^[Protomaps distributes a whole basemap as one PMTiles archive addressed by HTTP range requests, so the map is served by a static file beside the application rather than by a tile service it depends on.] locates the events whose places could be resolved, with the camera following the reader rather than the reader panning the map; the basemap is deliberately label-free, since the story supplies the toponyms. The ego network is presented on demand as [[graph|a force-directed graph]] of the subject's documented relationships, typed and weighted exactly as they were recorded. Images open in a lightbox that pages through the story's illustrations as a single gallery.

Each story additionally carries a generated visual identity—palette, typography, and background pattern—injected as CSS custom properties ((own-look)), so that the design system is data rather than code and each subject is presented in a visual register of its own.

### Meta stories

A meta story presents a theme across several biographies, and its structure is the one the composition step imposes: an opening scene, a timeline section, a network section, a map section, a conclusion, and a closing grid of the people the story is built from. Each of the three middle sections pairs running prose with one interactive component, and each carries the article layer's context rather than a recapitulation of what the component already shows.

The two visual sections are scrollytelling constructions, in which the component is pinned while narration cards scroll over it and select what it displays. In the network section, the force-directed graph is laid out once and then frozen—the simulation is advanced to convergence in the background before the graph is revealed—so that the narration directs the reader's attention while the graph holds still. Each card corresponds to one circle of the graph, which the network step detects by repeatedly merging the two groups whose merger raises modularity most—the greedy method of Clauset, Newman, and Moore [@clauset2004finding]. Its members remain lit while the remainder of the graph darkens. In the map section, a non-interactive map is pinned full-bleed and the camera flies to each geographic stop as its card enters the viewport, zooming to a place or fitting a bounding box according to how dispersed the stop's events are. Here the basemap keeps its labels, since the section is about where the theme was located.

::: screenshot id=meta-timeline route=#/en/meta/computing_pioneers width=1280 height=820 wait=".chapters-section" anchor=".chapters-section" scroll=2000 settle=5000 caption="The timeline section of a meta story, pinned while its narration scrolls: one lane per subject, grouped into the chapters the composition names, with the events of each life marked on it"
:::

A theme is presented in a visual register of its own as well ((own-look)), and because it is read as an article rather than as a sequence of slides, its identity carries something a biography's does not: two generated marks that punctuate prose. A glyph stands between two prose regions and before each subhead; a wider ornamental rule closes the last paragraph. In the masthead the glyph is composed rather than appended: an accent bracket encloses the title block and the mark sits on its corner, so that the opening of an article is itself an object rather than a headline with a rule beneath it. The theme also chooses how its boxes are cut—square, engraved, arched, organic—and that choice reaches every panel the article contains, the narration cards over the pinned components included, so the geometry of a frame is as much a property of the theme as its palette is. The typographic apparatus of a printed feature is thus derived from the theme.

The closing card grid links to the individual stories of every person the theme is built from, and each person's story links back. The two story types are thus two views of one corpus ((second-order)): a meta story is navigable into the biographies it draws on, and a biography is reachable from every theme in which it participates.

## Discussion and conclusion

Life Data Stories uses offline generation to derive events, locations, relationships, translations, and visual styles from encyclopedic biographies. A second pipeline recombines completed biographies into thematic stories. Both produce structured artifacts that a static client presents as life-story slides or thematic articles with timelines, maps, and networks.

Events connect narrative, chronology, and geography through one record, which improves consistency across views and allows corrections to propagate. The map includes only events with resolved coordinates, while the social network is generated separately. Structured model outputs and deterministic transformations limit individual failures and support partial regeneration, but factual quality remains dependent on the source material and model-based interpretation.

Meta stories reuse existing biographies and preserve links between themes and their subjects, while also inheriting gaps and errors from the corpus. Name-based network merging is particularly sensitive to inconsistent entity naming. Evaluation should therefore combine source-based checks of dates, places, relationships, and event selection with reader studies of comprehension, orientation, exploration, and trust. Stable entity identifiers, claim-level provenance, accessibility testing, and native-speaker review would strengthen the approach.

Overall, the project provides a reusable architecture for presenting individual and thematic biographies through coordinated narrative, temporal, geographic, and relational views. The main next steps are source-level verification and empirical evaluation with readers.

## References

::: references
:::
