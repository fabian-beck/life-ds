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

Life Data Stories makes that structure explicit and explorable. It derives from the source prose [[registry|a profile of the subject]], [[events|a set of discrete events]]—each with a resolved date, a place located on a modern map, the persons involved, and the illustrations available for it—and [[ego-network|the documented relationships that recur across them]]. It groups those events into the phases of a life and presents the result simultaneously as [[prose|narrative text]], as [[timeline|a chronology]], as [[map|a geography]], and as [[graph|a social network]]. The same derivation applied across several biographies yields [[meta-story|a theme]]: an idea traced through the lives that share it. A theme is presented as [[sections|a meta story]], one continuous document that carries the same encodings across all of its subjects at once—one timeline with a lane per life, one map, and one network merged from theirs.

Segel and Heer [@segel2010narrative], surveying how data is used to tell stories, place such a presentation on a spectrum between the author-driven, in which a fixed order carries the message, and the reader-driven, in which the audience decides what to look at. A story in Life Data Stories is author-driven at first glance and reader-driven in its depth. The sequence is fixed when the story is generated and can simply be followed to the end; the timeline that doubles as a control, the network opened on demand, the images as a gallery, and the cards leading into other lives are all available and none of them is required. A meta story is linear in the same way, and at any point along it the lives it draws on are open to be entered. The same three encodings appear at the reader-driven end of that spectrum in VisKonnect [@latif2021viskonnect], which connects historical figures through the events they have in common: a reader's prompt retrieves the matching events from an event knowledge graph, and an event timeline, an event map, and a relationship graph are shown beside a short answer.

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

The salient structural feature is the fork that follows source acquisition. Once the material is cached and narrowed, the narrative branch, the imagery branch, the network branch, and the visual-identity branch cease to depend on one another, and they reconverge only at review and translation. The one crossing is the imagery branch's, and it is deliberate: alongside the twenty searches written for the life as a whole, the searches the event research wrote for each event while it still had that event's material in front of it are run too. A search written from one researched event names the machine, the building, the document; a search written from twenty titles at once knows little beyond the person and the city, and asking Wikimedia Commons for a person and a city returns what a later century built to remember them. Branch independence bounds the consequences of a failure to a single concern and makes partial regeneration—new imagery for an unchanged narrative, a revised palette for an unchanged network—an ordinary operation rather than a full rebuild.^[Three of the branches are addressable from the command line as they are drawn here: `--dataset-only`, `--style-only`, and `--network-only` each run one of them against the subject's existing data.]

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

Life Data Stories' reading side is a mobile-first Svelte and Vite application: it loads the data the generation pipelines produced and renders it directly. The landing page offers access to two story types, which organize the data differently: [[slides|a person's story]] follows one life in order, a [[sections|meta story]] follows [[meta-story|a theme]] across several lives. On the landing page, the meta stories are displayed in [[landing.carousel|a carousel]] at the top. Below them, [[landing.grid|a person's stories]] can be reached four ways: via their generated portrait, by filtering on role, by search, or by viewing a map that plots every place mentioned across the corpus. Clicking a marker there opens directly onto the event it belongs to inside a person's story. In the following, we walk through both story types in more detail. Throughout, we use the meta story *Beyond the Box* and the person's story of *Antoni Gaudí* as running examples.


::: screenshot id=landing route="#/en" width=1280 height=1300 settle=2500 caption="The landing page: a carousel of meta stories above, person's life stories in a filterable grid below."
@carousel 471,101,769,400 Meta story carousel
Cycles through the meta stories, each with title, subtitle, and a "Story" or "Filter" shortcut.
@grid 48,705,1169,595 Filterable story grid
One tile per person's story, with generated portrait, lifespan, roles, and a one-line description.
:::


### The meta story
A meta story is structured as an [[prose|opening scene]], up to three component sections — [[timeline|a timeline]], [[graph|a network]], [[map|a map]] — and a [[prose|closing conclusion]], followed by a grid linking to the people it draws on. The whole read from top to bottom by scrolling. Not every theme carries all three sections, and which ones appear, is decided once when the story is composed based on the data that is available. Our exemplary meta-story, *Beyond the Box*, illustrates nine architects who lived and worked across more than a century. <!--Each of these architects pushed past what their time considered to be the limits of architecture. -->The meta story investigates their commonalities, what shaped their work, and how they might have influenced each other.


::: screenshot id=meta-timeline-environment route="#/en/meta/organic_shapes_in_architecture" width=1280 height=820 wait=".timeline-horizontal-container" anchor=".timeline-horizontal-container" scroll=500 settle=3000 caption="The timeline: one lane per architect, with a guiding story card in front naming the span currently in focus"
@whole 0,0,1280,820 Timeline visualization
The timeline: one lane per architect, with a guiding story card in front naming the span currently in focus
@card 170,55,570,110 Guiding story card
Names the span of years currently in focus and describes what happened across the lives within it.
@lanes 0,230,1280,530 Nine architect lanes
One lane per architect, grouped into thematic clusters, with events marked as dots along each line.
:::

*Timeline.* After the text-only introduction, the vertical scrolling turns horizontal, as the reader reaches the [[meta-timeline-environment.whole|timeline visualization]]. This visualization carries the reader sideways through time instead of further down the page. In *Beyond the Box*, what comes into view is [[meta-timeline-environment.lanes|a timeline of nine lanes]], one per architect. Events are marked as dots along each lane. [[meta-timeline-environment.card|A sequence of guiding story cards]] is pinned near the top and leads the reader through the timeline. Each card names a span of years and describes what happened during that period. The first card, "The Complete Environment", remains visible as long as the reader scrolls through the years it covers.

::: screenshot id=meta-network route="#/en/meta/organic_shapes_in_architecture" width=390 height=844 wait=".network-section" anchor=".network-section" scroll=800 settle=3000 caption="The network: architects as nodes, one card in front naming the cluster currently lit"
@whole 0,0,390,844 The network view
The full graph of architects, with one card in front naming the cluster currently lit.
@cluster 15,315,280,185 Otto, Wright, and Gaudí, lit
Ringed and connected while the rest of the graph darkens into the background.
@card 8,604,364,240 Lines of Transmission
Describes the one connection currently lit: Otto's 1950 visit to Wright, and his later use of Gaudí's forms.
:::

Tapping on a dot representing an event opens a brief description of it. Tapping the surrounding card instead leads into that architect's personal story. Above the lanes is a second layer of annotations that marks historical events affecting several lives at once, such as World War II. While the guiding story card offers one path through the theme, the lanes and their events are for readers who want to explore further.

::: screenshot id=meta-map route="#/en/meta/organic_shapes_in_architecture" width=390 height=874 wait=".map-section" anchor=".map-section" scroll=800 settle=3000 caption="A location card, with the map flown in above and its linked events listed below"
@map 0,43,390,527 The background map
Flies to a new location as each card scrolls into view.
@events 20,758,350,106 Linked events
Each relevant event listed here links directly to the person's story slide where that event is introduced.
:::

*Network.* [[meta-network.whole|The graph]] displays the architects and the documented connections between them. Its layout is calculated in the background and finalized before it is displayed. The data groups people into clusters, tying their members more closely to each other than to the rest. As the reader scrolls, [[meta-network.card|cards move over the graph]], one per cluster: the people involved are highlighted and the connection between them lit, while the rest of the graph darkens — [[meta-network.cluster|as here, for Frei Otto, Frank Lloyd Wright, and Antoni Gaudí]]. The graph itself does not move or rearrange as the reader scrolls, only the part in the foreground changes.

*Map.* The third section shifts the focus from the architects themselves and their connections to the locations where their work took place. [[meta-map.map|A non-interactive map]] fills the background behind the scrollable story cards, flying to a new location as each one scrolls into view — zooming to a point or fitting a bounding box depending on how spread out that events are — as here, for Barcelona. Each [[meta-map.events|event listed on a card]] links directly to the person's story slide where that event is introduced. The map section is not a separate account of the theme; it is the same events that the timeline already showed. Instead of *when,* the focus is on *where.*



The meta story concludes with a brief summary that ties the nine lives together. Below that is a grid of tiles, one for each architect. The grid links out to the architects' individual stories. The walkthrough follows one thread further from there, into Gaudí's own story.

### A person's story

::: screenshot id=gaudi-relationship-card route="#/en/story/antoni_gaud?slide=10" width=390 height=844 wait=".story-view" settle=3500 caption="The classic format of the slide includes text in the middle, a map beneath, and an outline consisting of icons at the bottom."
@whole 0,0,390,844 The event slide
The classic slide format: running text in the middle, an accumulating map beneath, and an icon outline at the bottom.
@tag 24,538,172,34 Eusebi Güell, tagged as patron
Tapping it opens a card describing the relationship in detail.
@map 0,580,390,180 The accumulating map
Gains a new marker — here Barcelona — each time the running text names a place.
@icons 0,798,390,46 Event icon row
There is one icon per event, shaped according to its type, and a plain marker for each chapter.
:::
There are two ways to access a person's story: directly from the landing page, through search, filter, or the overview map, or by following a link out of a meta story — its closing grid, a name in its running text, a marker on its map, a point on its timeline. Following that grid into Gaudí's story, as we just did, lands at its beginning.

*Timeline*. The story unfolds as a horizontal [[gaudi-relationship-card.whole|sequence of slides]] — an overview, a few chapters that mark the phases of life, the events themselves, and a closing slide — which are moved through by swiping sideways rather than scrolling down. [[gaudi-relationship-card.icons|A row along the bottom]] serves as both a progress marker and an outline. Each event is represented by an icon that reflects its type. Each chapter is represented by a plain marker. Tapping on the event count expands the entire row into a dated outline of the life. <!--Gaudí's story contains sixteen events across four chapters. Its second chapter, "A Genius Enters Barcelona," covers the period from 1878 to 1899. During this decade, his earliest commissions evolved into the Barcelona work for which he is known.--> For events with supporting data, a vertical axis opens further. A chevron reveals a longer background passage about the context of the event. 

The same three encodings a meta story spreads across sections — time, place, relation — are attached to this sequence too, just differently: the slide-based representation of events already stands in for the [[timeline|timeline]]; [[graph|a network overview]] exists from the start, reachable on demand from a button at the top of the screen; and [[map|a map]] is visible beneath the text of every slide.

*Map* Fixed in the same position on the screen, it receives a marker each time an event mentions a place. By the end of the story, the map shows everywhere the subject worked and lived. [[gaudi-relationship-card.map|This chapter's marker is on Barcelona]], where Gaudí's projects, such as Palau Güell took shape.

*Network.* When an event slide mentions another person, that person's name appears beside the text with their role — as here, for [[gaudi-relationship-card.tag|Eusebi Güell]], tagged patron. Tapping the tag opens a card describing the relationship on its own terms. From this card, or the button at the top of the screen, readers can access Gaudí's full network, organized by relationship type — family, professional, social — each group introduced by a short passage.

## Discussion and conclusion

Life Data Stories uses offline generation to derive events, locations, relationships, translations, and visual styles from encyclopedic biographies. A second pipeline recombines completed biographies into thematic stories. Both produce structured artifacts that a static client presents as life-story slides or thematic articles with timelines, maps, and networks.

Events connect narrative, chronology, and geography through one record, which improves consistency across views and allows corrections to propagate. The map includes only events with resolved coordinates, while the social network is generated separately. Structured model outputs and deterministic transformations limit individual failures and support partial regeneration, but factual quality remains dependent on the source material and model-based interpretation.

Meta stories reuse existing biographies and preserve links between themes and their subjects, while also inheriting gaps and errors from the corpus. Name-based network merging is particularly sensitive to inconsistent entity naming. Evaluation should therefore combine source-based checks of dates, places, relationships, and event selection with reader studies of comprehension, orientation, exploration, and trust. Stable entity identifiers, claim-level provenance, accessibility testing, and native-speaker review would strengthen the approach.

Overall, the project provides a reusable architecture for presenting individual and thematic biographies through coordinated narrative, temporal, geographic, and relational views. The main next steps are source-level verification and empirical evaluation with readers.

## References

::: references
:::
