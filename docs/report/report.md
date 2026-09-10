---
title: Life Data Stories
subtitle: Generating and presenting biographical data stories
authors:
  Fabian Beck | University of Bamberg | https://www.uni-bamberg.de/en/vis/team/prof-dr-fabian-beck/ | 0000-0003-4042-3043
  Leah Mühlöder | University of Bamberg | https://www.uni-bamberg.de/en/vis/team/leah-muehloeder/ | 0009-0000-3510-1686
  Till Nagel | Mannheim University of Applied Sciences | https://services.informatik.hs-mannheim.de/~nagel/ | 0000-0001-5400-091X
description:
  Technical report on the Life Data Stories system: its data model, its two
  generation pipelines and its interface.
disclaimer:
  This report was co-written with AI. Its prose was drafted and revised with language models under the authors' direction, and every figure, table, and count in it is computed from the repository at build time. The system it describes was implemented by AI through agentic engineering: coding agents wrote the code, and the authors specified, reviewed, and directed the work.
abstract:
  Life Data Stories transforms encyclopedic biographical prose into structured data stories. The stories are shown as sequences of slides in which a life is presented as a multi-faceted representation that combines narrative text, timelines, maps, and social networks. A second story type, the meta story, traces a theme across several lives and presents it as one continuous document in which the same three visual encodings are read by scrolling. The system separates two concerns. First, generation is performed offline by staged pipelines that combine intelligent language-model inference with deterministic transformation. Second, the presentation is rendered deterministically by an interactive web application. This report documents the implemented solution and provides a basic scientific contextualization.
---

::: teaser
:::

::: toc
:::

## Introduction

[[sources|Encyclopedic biography]] is a rich and well-sourced account of a life, written as continuous prose in long-form articles. Reading a life in that order is natural, but it keeps other points of access in the background and does not support more casual browsing. Such browsing would be supported by the biography's temporal, geographic, and relational structure: the phases of a life, its movements, the people who recur in it. That structure runs through the whole text without being tangible for the reader.

Life Data Stories makes that structure explicit and explorable. It derives from the source prose a set of discrete [[events|events]] and the documented [[ego-network|relationships]] that recur across them. Each event has a resolved date, a [[geography|place]], the people involved, and the [[imagery|illustrations]] available for it. It groups those events into the phases of a life and presents the result simultaneously as narrative text, as a chronology, as a geography, and as a social network. The [[narrative|text]] that describes those events and the [[identity|visual identity]] the story is presented in are generated with them. The same derivation applied across several biographies yields a [[sections|meta story]], one continuous document that integrates a timeline with a lane per life, a map, and a social network merged from the biographies.

Segel and Heer [@segel2010narrative], surveying how data and visualization are used to tell stories, place such a presentation on a spectrum between the author-driven, in which a fixed order carries the message, and the reader-driven, in which the audience decides what to look at. A story in Life Data Stories is author-driven at first glance and reader-driven in its depth. The sequence is fixed when the story is generated and can be followed to the end. Alternative exploration affordances are available throughout, in timelines, image galleries, maps, and social network views. A meta story is linear in the same way, and at any point along it one of the lives can be entered.

BiographySampo [@hyvonen2019biographysampo] is one of the closest precedents from the digital humanities. It extracts events, places, and relationships from national biographical dictionaries with language technology and pattern rules, links them to external registers, and offers them through faceted search, maps, timelines, and ego networks. Its tools serve biographical research, and the text of a biography stays what it was, read beside the data. VisKonnect [@latif2021viskonnect] uses encodings similar to those of Life Data Stories and connects historical figures through the events they have in common. There, only a reader's prompt retrieves the matching events from an event knowledge graph, and an event timeline, an event map, and a relationship graph are shown beside a short answer. Textual answers are generated but are only partial and stay disconnected from the visual representation. In contrast, Life Data Stories integrates text and visual representation and proposes an order through both, with exploration options alongside.

To achieve this, we heavily rely on [[inference|large language models (LLMs)]] for interpreting the data. A biography is at first unstructured text, and giving it structure means deciding which episodes are important, which places they relate to, and which relationships matter. However, this only needs to be done once, not as part of the user interface. The system is accordingly built in two parts that connect through the [[artifacts|data]]. Generation runs offline as preprocessing and interleaves model calls with deterministic transformation, so a step that researches or reviews material is surrounded by steps that resolve, cluster, merge, and validate what the model returned. It produces a set of documents, data, and images describing one life or one theme. The interface loads those files and renders them as a matter of presentation alone in a single-page web application.

## Data model

The data that connects generation and interface is a semi-structured representation of a biography and the central abstraction of the system. For a single life it holds several structured perspectives: the <<events|events>> that mark the turning points of a life, the <<narrative|text>> that describes them, the <<imagery|pictures>> that illustrate them, and the <<places|geography>> connected to them. While these parts are relatively straightforward derivatives of the textual biographical source, two further perspectives are more interpretive: the <<network|social network>> around the subject, which the text rarely describes explicitly, and the <<identity|visual identity>> the story is presented in, which gives it a recognizable look.

::: conceptlegend
:::

A meta story refers to the data of the lives it connects and adds perspectives of its own. It names its cast of subjects and groups them into subtopics. Its chapters cut across those lives into shared periods, and each chapter references <<events|events>> that stay in the subjects' own data, annotated with what each one contributes to it. The subjects' ego networks are merged into one <<network|social network>>, and the <<places|geography>> of all of those lives is clustered into the places important to the theme. The <<narrative|text>> is written for the theme, and the <<imagery|pictures>> that illustrate it are selected from the events of the individual stories. Like a life, a theme is presented in an <<identity|visual identity>> of its own.

## Generation

We split the generation of this data into two stages. The first stage, the [[person-pipeline|personal story pipeline]], reads an encyclopedia article and writes the data of an individual biography. The second stage, the [[meta-pipeline|meta story pipeline]], reads the data of several individuals and writes a meta story connecting them. Both pipelines run offline as Python command-line scripts, invoked for one life or one theme at a time. A run writes the data the previous section described as JSON documents. Each step within a run reads the documents earlier steps wrote, writes its own back to disk, and is one of four kinds.

::: kindlegend
:::

Both pipelines follow the same pattern: material is derived bottom-up and revised top-down. Both end in translation, where the English document is written first and each document is then translated into every other supported language (currently: German).

### Personal story pipeline

The [[person-pipeline|personal pipeline]] derives data for one biography, from an [[sources|encyclopedia article]] to the data needed for an illustrated and individually styled story. The chart bands its steps into seven phases: the sources are gathered; the events are proposed, researched, and geocoded; their pictures are found; the assembled document is then presented, with a registry entry, a style, and generated pictures; the social network is derived and both datasets are reviewed; a depth layer of background reports is written; and localization closes the run.

::: pipeline lane=person
:::

First, an [[step:p_wiki_fetch|acquisition step]] loads the subject's Wikipedia article, the articles it links to, and the Commons image metadata around it, and caches all of it, so that every later step and every rerun reads the same material. An AI-based [[step:p_wiki_select|selection call]] ranks the linked articles by how much each would help tell this particular life. Meanwhile, a [[step:p_db|second biographical source]] is consulted for German and European figures.

The events and the main narrative are derived from that material in two calls of different types. The [[step:p_events_p1|first call]] proposes 12 to 16 events with titles, dates, descriptions, a classification, and a weight, and groups them into three to six chapters. A [[step:p_events_p2|second call per event]] then researches each event in detail against the relevant articles: the historic and modern name of its place, the people involved, a semantic icon, and image searches that would illustrate it.

We then resolve places and pictures. [[step:p_geocode|Geocoding]] looks up exact coordinates for the places by their modern names. For image search, [[step:p_img_search|a planning step]] generates queries for images relating to the person's name and the subjects of the events, while the per-event searches name specific objects such as a building or a document. [[step:p_img_fetch|All queries]] are then executed against Wikimedia Commons and Openverse, and the candidates are scored in code on resolution, file size, and filename before [[step:p_img_match|an AI-based matching call]] assigns pictures to events, writes captions with attribution, and picks a reference portrait. Since the matching call judges by metadata only, [[step:p_img_verify|a vision call]] checks whether the chosen portrait, which we consider the most central visual representation, actually depicts the subject.

The three strands meet in the life events document, which the chart draws as a node: every later step reads the written document rather than the memory of the run, which makes a run resumable and a single concern regenerable. [[step:p_register|The registry]] adds the subject to the index of the landing page. Two descriptions of the whole life are then derived independently: [[step:p_style|a color and type system]] from the subject's era and field, and [[step:p_network|the ego network]] as typed, weighted, and described relationships the article implies. Generated illustrations come last: [[step:p_portrait|the reference portrait is style-transferred]] toward one master style shared by all subjects, [[step:p_chapter_concepts|each chapter is turned into an abstract visual concept]] in one call over all chapters, and [[step:p_chapter_art|each concept is drawn]] in the same style.

[[step:p_review|A review pass]] over the events and the network applies only high-confidence changes. Reading the slides in order, it rewrites descriptions that rely on names not yet introduced or repeat the previous slide. The style is checked in code instead: its rules on tile, font, and contrast are arithmetic, and [[step:p_style|the generator]] asks the model again with the reason when a check fails. For localization, [[step:p_name_evidence|a deterministic pass]] collects the target language's names of the subject, the people, and the places from the linked articles. [[step:p_glossary|A glossary call]] fixes once per subject how every name is rendered, since the interface matches cross-references on exact names. [[step:p_translate|The translation]] merges the translated fields over a copy of the English document, so that dates, coordinates, URLs, and identifiers stay unchanged.

[[step:p_backgrounds|A background report]] of a few hundred words is written after the review for roughly one event per chapter, selected by the interface's own rule and grounded in the reviewed text. [[step:p_illustrations|A critic call]] reads the illustrations found for it against the report, since keyword search returns much that merely shares a word with it. Datasets that predate a model field are flagged as outdated and regenerated.

### Meta story pipeline

The [[meta-pipeline|meta pipeline]] traces a theme across many lives and consumes the output of the personal pipeline instead of external sources. It runs two independent branches, the social network and the geographic map. Each derives its structure deterministically from existing data, reviews or weights it in an inference pass, and writes the text bound to it in a narration pass. The branches meet in the composition step, which re-reads the assembled story and separates captions bound to what the reader sees from the article prose that supplies context.

::: pipeline lane=meta
:::

### AI models and prompting

The generation side uses {{ pipeline.models }}. We configure the model per [[inference|call site]] to only spend frontier intelligence and reasoning effort where needed and keep generation costs manageable (below 1 EUR per generated story). We assign the largest model to composition, the one step that reads a whole assembled story, the image model to the portrait step, and divide the remaining steps between a reasoning tier and a small one by whether a wrong answer can quietly become part of the corpus. A step uses the small model when its output is validated against existing entities, rewritten by a later step, or backed by a deterministic fallback. More advanced tasks such as proposing the events of a life, selecting the people of a theme, reviewing another step's output, and the glossary use the reasoning tier. Analogously, reasoning effort is differentiated between different calls.

For prompt design and context engineering, we tried to anticipate which materials a call needs and to limit the prompt to those, while still providing sufficient background. The material shared by all calls of a step is placed at the start of the prompt and the event-specific part at the end, so that the API's prefix caching covers the repeated part. All steps that produce text a reader sees share one instruction block on writing style. It discourages typical patterns of AI-generated prose, for instance, contrasting a fact with an alternative nobody proposed. Every response is requested as structured output against a [Pydantic](https://docs.pydantic.dev/) schema, so that it is parsed and validated.

## Interface

Life Data Stories' reading side is a mobile-first Svelte and Vite application: it loads the data the generation pipelines produced and renders it directly. The landing page offers access to two story types, which organize the data differently: [[slides|a person's story]] follows one life in order, a [[sections|meta story]] follows a theme across several lives. On the landing page, the meta stories are displayed in [[landing.carousel|a carousel]] at the top. Below them, [[landing.grid|a person's stories]] can be reached four ways: via their generated portrait, by filtering on role, by search, or by viewing a map that plots every place mentioned across the corpus. Clicking a marker there opens directly onto the event it belongs to inside a person's story. In the following, we walk through both story types in more detail. Throughout, we use the meta story *Beyond the Box* and the person's story of *Antoni Gaudí* as running examples.


::: screenshot id=landing route="#/en" width=1280 height=1300 settle=2500 caption="The landing page: a carousel of meta stories above, person's life stories in a filterable grid below."
@carousel 471,101,769,400 Meta story carousel
Cycles through the meta stories, each with title, subtitle, and a "Story" or "Filter" shortcut.
@grid 48,705,1169,595 Filterable story grid
One tile per person's story, with generated portrait, lifespan, roles, and a one-line description.
:::


### The meta story
A meta story is structured as an opening scene, up to three component sections, and a closing conclusion, followed by a grid linking to the people it draws on; the sections are a timeline, a network, and a map. The whole is read from top to bottom by scrolling. Not every theme carries all three sections, and which ones appear, is decided once when the story is composed based on the data that is available. Our exemplary meta-story, *Beyond the Box*, illustrates nine architects who lived and worked across more than a century. <!--Each of these architects pushed past what their time considered to be the limits of architecture. -->The meta story investigates their commonalities, what shaped their work, and how they might have influenced each other.


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

*Network.* [[meta-network.whole|The graph]] displays the architects and the documented connections between them. Its layout is calculated in the background and finalized before it is displayed. The data groups people into clusters, tying their members more closely to each other than to the rest. As the reader scrolls, [[meta-network.card|cards move over the graph]], one per cluster: the people involved are highlighted and the connection between them lit, while the rest of the graph darkens, [[meta-network.cluster|as here for Frei Otto, Frank Lloyd Wright, and Antoni Gaudí]]. The graph itself does not move or rearrange as the reader scrolls, only the part in the foreground changes.

*Map.* The third section shifts the focus from the architects themselves and their connections to the locations where their work took place. [[meta-map.map|A non-interactive map]] fills the background behind the scrollable story cards, flying to a new location as each one scrolls into view, as here for Barcelona. It zooms to a point or fits a bounding box depending on how spread out the events are. Each [[meta-map.events|event listed on a card]] links directly to the person's story slide where that event is introduced. The map section is not a separate account of the theme; it is the same events that the timeline already showed. Instead of *when,* the focus is on *where.*



The meta story concludes with a brief summary that ties the nine lives together. Below that is a grid of tiles, one for each architect. The grid links out to the architects' individual stories. The walkthrough follows one thread further from there, into Gaudí's own story.

### A person's story

::: screenshot id=gaudi-relationship-card route="#/en/story/antoni_gaud?slide=10" width=390 height=844 wait=".story-view" settle=3500 caption="The classic format of the slide includes text in the middle, a map beneath, and an outline consisting of icons at the bottom."
@whole 0,0,390,844 The event slide
The classic slide format: running text in the middle, an accumulating map beneath, and an icon outline at the bottom.
@tag 24,538,172,34 Eusebi Güell, tagged as patron
Tapping it opens a card describing the relationship in detail.
@map 0,580,390,180 The accumulating map
Gains a new marker each time the running text names a place, here Barcelona.
@icons 0,798,390,46 Event icon row
There is one icon per event, shaped according to its type, and a plain marker for each chapter.
:::
There are two ways to access a person's story: directly from the landing page, through search, filter, or the overview map, or by following a link out of a meta story: its closing grid, a name in its running text, a marker on its map, a point on its timeline. Following that grid into Gaudí's story, as we just did, lands at its beginning.

*Timeline*. The story unfolds as a horizontal [[gaudi-relationship-card.whole|sequence of slides]], moved through by swiping sideways rather than scrolling down: an overview, a few chapters that mark the phases of life, the events themselves, and a closing slide. [[gaudi-relationship-card.icons|A row along the bottom]] serves as both a progress marker and an outline. Each event is represented by an icon that reflects its type. Each chapter is represented by a plain marker. Tapping on the event count expands the entire row into a dated outline of the life. <!--Gaudí's story contains sixteen events across four chapters. Its second chapter, "A Genius Enters Barcelona," covers the period from 1878 to 1899. During this decade, his earliest commissions evolved into the Barcelona work for which he is known.--> For events with supporting data, a vertical axis opens further. A chevron reveals a longer background passage about the context of the event. 

The same three encodings of time, place, and relation that a meta story spreads across sections are attached to this sequence too, just differently: the slide-based representation of events already stands in for the timeline; a network overview exists from the start, reachable on demand from a button at the top of the screen; and a map is visible beneath the text of every slide.

*Map* Fixed in the same position on the screen, it receives a marker each time an event mentions a place. By the end of the story, the map shows everywhere the subject worked and lived. [[gaudi-relationship-card.map|This chapter's marker is on Barcelona]], where Gaudí's projects, such as Palau Güell took shape.

*Network.* When an event slide mentions another person, that person's name appears beside the text with their role, as here for [[gaudi-relationship-card.tag|Eusebi Güell]], tagged patron. Tapping the tag opens a card describing the relationship on its own terms. From this card, or the button at the top of the screen, readers can access Gaudí's full network, organized by relationship type into family, professional, and social, each group introduced by a short passage.

## Discussion and conclusion

Three properties of the approach hold independently of how well any single model call performed. An event is one record, so the narrative, the chronology, and the geography of a life agree by construction about when it happened and where, and a correction made once is a correction in every view. Non-determinism is confined to the steps that genuinely require judgment, which leaves everything downstream of a model call reproducible and assertable, and makes partial regeneration an ordinary operation. Themes are derived from finished biographies rather than from sources of their own, so a theme names the lives it is made of and each of them can be entered from it.

The architecture cannot establish that the content is true. Every statement in the corpus is a model's reading of an encyclopedia article, and most of what the pipelines check is structural: identifiers resolve, schemas fill, coordinates parse. Separate scripts do hold generated dates and life spans against the cached articles, but nothing checks whether a description says what its sources say. Where an interpretation fails, it also fails quietly: a place name that does not resolve leaves its event off the map without leaving a gap the reader can see.

The social network is the encoding least protected by any of this. It is derived on its own branch and joined to the events by name, so an inconsistently written name, rather than a disagreement about the facts, is what most often makes two views of the same person diverge. A meta story, built from finished biographies, merges those names across lives and inherits every error already in them. We consider replacing name matching with stable identifiers the most direct improvement.

Two kinds of evaluation would settle what we so far only claim. Source-based checking would hold dates, places, relationships, and event selection against the articles they were derived from, extending the checks that already exist into the parts of a document that resolve to an entity. Reader studies would have to answer the question the architecture assumes an answer to: whether four coordinated encodings of one life are read as one story, and whether a reader can tell what the system took from a source from what it inferred.

## References

::: references
:::
