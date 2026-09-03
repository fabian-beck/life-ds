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

[[sources|Encyclopedic biography]] is a rich and well-sourced account of a life, written as continuous prose in long-form articles. Reading a life in that order is natural, but it keeps every other point of access in the background. The biography's temporal, geographic, and relational structure runs through the whole text without ever being stated as such, and a reader who wants to explore that structure—the phases of a life, its movements, the people who recur in it—reconstructs it while reading.

Life Data Stories makes that structure explicit and explorable. It derives from the source prose [[registry|a profile of the subject]], [[events|a set of discrete events]]—each with a resolved date, a place located on a modern map, the people involved, and the illustrations available for it—and [[ego-network|the documented relationships that recur across them]]. It groups those events into the phases of a life and presents the result simultaneously as [[prose|narrative text]], as [[timeline|a chronology]], as [[map|a geography]], and as [[graph|a social network]] ((one-record)). The same derivation applied across several biographies yields [[meta-story|a theme]]: an idea traced through the lives that share it. A theme is presented as [[sections|a meta story]], one continuous document that carries the same encodings across all of its subjects at once—one timeline with a lane per life, one map, and one network merged from all of them.

Segel and Heer [@segel2010narrative], surveying how data is used to tell stories, place such a presentation on a spectrum between the author-driven, in which a fixed order carries the message, and the reader-driven, in which the audience decides what to look at. A story in Life Data Stories is author-driven at first glance and reader-driven in its depth. The sequence is fixed when the story is generated and can be followed to the end; the timeline that doubles as a control, the network opened on demand, the images as a gallery, and the cards leading into other lives are available throughout, and none of them is required. A meta story is linear in the same way, and at any point along it one of the lives it draws on can be entered. The same three encodings appear at the reader-driven end of that spectrum in VisKonnect [@latif2021viskonnect], which connects historical figures through the events they have in common. There, a reader's prompt retrieves the matching events from an event knowledge graph, and an event timeline, an event map, and a relationship graph are shown beside a short answer.

As in VisKonnect, the operations this requires are interpretive. A biography is unstructured text, and giving it structure means deciding what the article never states outright—which episodes constitute a life, which place a historical name refers to, which relationships matter—so those decisions are left to [[inference|large language models (LLMs)]]. The system is accordingly built in two parts that [[artifacts|connect through the data]]. Generation runs offline as preprocessing and interleaves model calls with deterministic transformation, so a step that researches or reviews material is surrounded by steps that resolve, cluster, merge, and validate what the model returned. It produces a set of documents describing one life or one theme. The interface loads those documents and renders them, which leaves reading a story a matter of presentation alone, carried by a single-page web application that performs no inference of its own.

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

The data that connects generation and interface is the central abstraction of the system. For a single life it holds several structured perspectives on one encyclopedic source: the <<profile|subject>> a story is about, the <<events|events>> that mark the turning points of a life, the <<narrative|text>> that describes them, the <<imagery|pictures>> that illustrate them, and the <<places|geography>> a life traces. Two further perspectives are more interpretive, stated by no article as such—the <<network|social network>> around the subject, and the <<identity|visual identity>> the story is presented in.

::: conceptlegend
:::

A meta story refers to the data of the lives it draws on and adds perspectives of its own ((second-order)). It is built on a <<theme|theme>>, which names its cast of subjects and groups them into subtopics. Its chapters cut across those lives into shared periods, and each chapter references <<events|events>> that stay in the subject's own data rather than being copied into the theme, annotated with what each one contributes to it. The subjects' ego networks are merged into one <<network|social network>>, in which people who recur in several of them bridge subjects who never met directly, and the <<places|geography>> of all of those lives is clustered into the few places the theme turns on. The <<narrative|text>> is written for the theme rather than assembled from its lives, and the <<imagery|pictures>> that illustrate it are selected from the events of the individual stories. Like a life, a theme is presented in an <<identity|visual identity>> of its own ((own-look)).

## Generation

The generation process is split into stages. The first stage reads an encyclopedia article and writes the data of an individual biography; a second reads the individuals data and writes a meta story connecting multiple individuals. Both pipelines run offline as Python command-line scripts, one entry point per story type, invoked for one life or one theme at a time. Each step reads the documents earlier steps wrote and writes its own back to disk, so a run is resumable, a single concern can be regenerated without touching the rest, and a failing step is recorded and skipped rather than aborting the run; a run leaves behind the directory of JSON documents the previous section described. Every step is one of [[kinds|four kinds]], a classification that partitions both pipelines by failure mode and by cost—what may be re-run freely, what must be paid for, what depends on an external service, and what can be verified by assertion—and non-determinism is confined to the steps that genuinely require judgment, which leaves clustering, geocoding, chapter fitting, network merging, and translation bookkeeping deterministic. 

::: kindlegend
:::

Both pipelines follow the same pattern ((bottom-up)): material is derived bottom-up by steps that each observe only their own slice of the subject, and revised top-down by a step that observes the assembled story. Both end in translation, where the English document is written first, a glossary pass fixes the rendering of names and recurring terminology once per subject, and each document is then translated into every supported language ({{ app.languages }}).



### Personal story pipeline

[[person-pipeline|The personal pipeline]] carries one biography end to end, from [[sources|an encyclopedia article]] to a translated, illustrated, and individually styled story. It runs the derivation in a fixed order, and the order follows what each step can be shown: the source material is acquired first, because everything else is a reading of it; the events are proposed before they are researched, because research is per event; places, pictures, and published works are resolved once the events name them; and the descriptions of a life as a whole—its chapters, its social network, its look—are settled last, when there is a whole life to describe. Imagery, the social network, and the visual identity each read the written life and nothing else the run produces, which bounds a failure to a single concern and makes partial regeneration—new imagery for an unchanged narrative, a revised palette for an unchanged network—an ordinary operation rather than a full rebuild.^[Three of those concerns are addressable from the command line as they are derived here: `--dataset-only`, `--style-only`, and `--network-only` each run one of them against the subject's existing data.]

::: pipeline lane=person
:::

[[step:p_wiki_fetch|Acquisition]] pulls the subject's article, the articles it links to, and the Commons image metadata around it, and caches all of it, so that every later step and every rerun reads the same material at no further cost. Which of the linked articles to keep is a budget question rather than a coverage question—an article on a mid-career architect links to hundreds of others, and the context a later call can be given is finite—so [[step:p_wiki_select|a selection call]] ranks the candidates by how much each would help tell this particular life. [[step:p_db|A second biographical source]] is consulted for German and European figures, under a license check applied per record: the older ADB text may be used and the newer NDB text may not, and the distinction belongs to the record rather than to the database it came from.

The narrative is derived from that material in two calls of very different shape. [[step:p_events_p1|The first proposes the events]]—12 to 16 of them, with titles, dates, descriptions, a classification, and a weight—and it is the one call in the pipeline that sees a life whole, which is what the weight requires: how much of a life an event turns on is a comparison between events rather than a property of one. What it returns is a skeleton, with no places, sources, or pictures in it. [[step:p_events_p2|Each skeleton is then researched on its own]], against the articles relevant to that event, into the historic and the modern name of its place, the people involved, the sources behind it, a semantic icon, and the Commons searches that would illustrate that event, written while its material is still in front of the call. [[step:p_chapters|A third call]] groups the researched events into three to five chapters whose headlines read as an arc rather than as date ranges ((bottom-up)).

::: note
Events are researched individually rather than in a single call. This is the most consequential granularity decision in the pipeline, since the number of model calls it makes scales linearly with the number of events. It is retained because a per-event call receives a focused prompt and a small output schema, and because a failed or malformed response is then confined to a single event.
:::

What the events name is then resolved against registers outside the article. [[step:p_geocode|Geocoding]] places each location on a modern map, preferring the modern name the event research supplied, which is what lets a historic place with a renamed successor land where a reader can find it. [[step:p_pub_links|The published works]] a life event names are resolved against Wikidata, and against Wikipedia where that finds nothing, and an answer is kept only when both the title and the authorship check out, so that a slide naming a work also offers the place it can be read. The imagery is searched twice over. [[step:p_img_search|Searches written for the life as a whole]] name the person and the things the events name, and are forbidden to name a commemoration, because asking Wikimedia Commons for a person and a city returns what a later century built to remember them; the searches the event research wrote run alongside them, and they name the machine, the building, the document, which is what a search written from a list of event titles cannot do. [[step:p_img_fetch|Every query is run]] against Commons and Openverse and the hits are deduplicated by URL, the per-event searches first, so that the tag recording which event a picture was found for survives deduplication. [[step:p_img_filter|A deterministic pass]] scores the candidates on resolution, file efficiency, and how informative a filename is, and drops everything under a permissive threshold, so that [[step:p_img_match|the matching call]] sees candidates rather than noise. That call assigns pictures to events, writes their captions, carries the attribution each license requires, and picks the subject's reference portrait, under no quota: an event with no picture is a correct answer. It judges by filename and caption alone, and a photograph of a spouse carries the subject's name in its caption, so [[step:p_img_verify|the portrait is shown to a model as an image]] and asked whether it depicts the subject. A no drops the pick and a failed call keeps it, so the check can lose a wrong portrait but never a right one.

[[step:p_write|Writing the dataset]] is where the run stops being memory: everything after it reads the written documents rather than the payload that produced them, which is what makes a run resumable and a single concern regenerable. [[step:p_register|The registry]] folds the subject into the index the landing page reads. Three descriptions of the whole life are then derived from it, none of them reading the others. [[step:p_style|A color and type system]] is derived from the subject's era and field, so that the story carries an identity of its own rather than the application's ((own-look)). [[step:p_network|The ego network]] states the relationships the article implies but never lists, as typed, weighted, and described ties, and it is what the meta pipeline later merges across lives ((second-order)). The illustrations that are drawn rather than found come last: [[step:p_portrait|the licensed reference portrait is style-transferred]] toward one master style, so that every subject in the collection belongs to a single illustration set, and [[step:p_chapter_concepts|each chapter is turned into an abstract visual concept]]—a metaphor with concrete forms in it, never a person or a place—in one call over all chapters, so that the metaphors differ from one another, before [[step:p_chapter_art|each concept is drawn]] in that same master style. Both drawing steps take their two colors from the style, which is why they wait on it rather than merely following it: an image drawn in a palette no story uses is cached under the subject's name and outlives the run that drew it, so a subject whose style is missing is left undrawn and the run says so.

Two critics read what the derivation produced: [[step:p_review|one over the events and the network]], which applies only high-confidence changes, and [[step:p_review_style|one over the style]], which checks color harmony and font pairing against the mood of the story. Localization closes the run in three steps, because a translator working from its own memory of a name invents one. [[step:p_name_evidence|A deterministic pass reads the target language's own names]]—the subject's article in that language, and one language link per person and per place in the data—and hands that evidence to the two calls that follow. [[step:p_glossary|A glossary call]] then decides once per subject how every name is rendered, since the interface matches its cross-references on exact names and drift between documents would break them, and [[step:p_translate|the translation]] extracts the translatable fields, translates them, and merges the result over a copy of the English document, so that dates, coordinates, URLs, and identifiers cannot drift.

One piece of writing follows the review rather than preceding it. The story opens a depth layer on roughly one event per chapter, and the layer is a written report; [[step:p_backgrounds|the report step]] computes that selection with a port of the interface's own rule and writes a report of a few hundred words exactly for the events the story will offer one on—grounded in the reviewed text, shown everything the slide already tells the reader so it writes around it, and re-deciding the event's citations. Its illustrations are searched and then read: [[step:p_illustrations|a critic reads what the searches returned against the report itself]], because half of what a keyword search returns merely shares a word with it. A dataset that predates a model field—a weight, a classification, this report—is not repaired: it is flagged as outdated and regenerated by the current pipeline.

### Meta story pipeline

[[meta-pipeline|The meta pipeline]] traces a theme across many lives, and it consumes the output of the personal pipeline rather than external sources, so its figure begins with nodes that no step of its own produces. Where the personal pipeline forks once, this one maintains two long independent branches—the social network and the geographic map—each of which runs to completion on its own. Each branch follows the same internal progression: a deterministic derivation from existing data, an inference pass that reviews or weights the derived structure, and a narration pass that writes the text bound to it. The branches meet only in the composition step, which re-reads the assembled story and separates captions, bound one-to-one to something the reader is looking at, from the article prose that supplies the context around what the components encode ((bottom-up)).

::: pipeline lane=meta
:::

### Models, prompts, and structured output

The generation side uses {{ pipeline.models }}. The model is resolved per [[inference|call site]] rather than fixed globally, so that a phase whose cost is dominated by volume and a phase whose quality determines the whole story need not share one setting. Three text tiers are in use. Composition—the one step that reads a whole assembled story—takes the largest through its own variable; the portrait step takes the image model; and the remaining steps are divided between a reasoning tier and a small one by a single question: whether a wrong answer can quietly become part of the corpus. A step qualifies for the small model when it cannot—when what it returns is validated against entities that already exist, rewritten by a later step, or backed by a deterministic fallback. Selecting which articles to read, researching an event the pipeline has already chosen, matching images to events, curating a theme's event pool, narrating what composition will rewrite, and translating a payload whose structure the merge enforces are all of that kind. Deciding which episodes constitute a life, which people constitute a theme, and whether another step's output is any good are not, and neither is the glossary that fixes how a name is written, because every other document is then matched against its answer by exact name. The division is a claim about verifiability rather than about difficulty, and it is worth stating in those terms: a step is cheap to run precisely when the system can tell that it went wrong.

Reasoning effort is configured the same way, and varies more, because the calls differ in kind. Proposing the significant events of a life is an inference problem and receives a reasoning budget; writing the search strings for an image query is slot filling and receives none. Between them sits the work the small model is asked to do, which mostly consists of holding a threshold or choosing one option out of many—is this event essential to the theme, which of these images is a portrait, which German sentence carries this English one—and receives a small budget for it. The two settings are chosen together: moving a step to the small model is not the same decision as deciding how much it should deliberate, and a step can be moved down one axis while moving up the other.

Both settings are arguments of one call. Every step that fills a schema reaches the API through a single function, which takes the model and the effort and returns either the parsed object or nothing—and this is worth reporting because for a time it was not so. Six steps used a second API that had no effort parameter, and therefore ran at whatever the model does by default while the configuration described effort as a per-step setting; the divergence was invisible in the code, since each call read as a reasonable call. Beyond consistency, a shared entry point lets a policy be stated once. The policy that matters here is which failures are worth repeating: a dropped connection or a rate limit is a statement about the moment, and the same request a few seconds later usually succeeds, whereas a malformed request or a refusal is a statement about the request, and asking again spends money to hear it twice. Only the first kind is retried. What a failure *means*, though, stays with the step, because only it knows: article selection falls back to the first candidates in order, an optional section is skipped, a translation is left stale for the parity check to report, and curation stops the run rather than let a theme keep every event of every life it draws on.

Prompt text is constructed in Python functions rather than stored as templates or configuration, since prompts require conditionals and injected data far more often than they require editing outside a code review. Structured output is declared as Pydantic models, which converts open-ended text generation into slot filling: the required shape of a response is a type rather than a paragraph of instructions, and validation occurs before any value is kept. Model output is then applied deterministically. Identifiers are matched against existing entities, unknown references are discarded with a warning, and coordinates, URLs, and graph structure are copied rather than accepted, so that a defective response stays confined to the field it fills.

::: schemalist names=LifePlan,EventDetails,EgoNetwork,MetaStoryPlan
The four schemas central to the two pipelines—the plan of a life, a single researched event, a person's ego network, and a meta story's plan—are expanded field by field from the Pydantic models the API is asked to populate.
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

Three properties of the approach hold independently of how well any single model call performed. An event is one record, so the narrative, the chronology, and the geography of a life cannot disagree about when it happened or where ((one-record)), and a correction made once is a correction in every view. Non-determinism is confined to the steps that genuinely require judgment, which leaves everything downstream of a model call reproducible and assertable, and makes partial regeneration an ordinary operation. Themes are derived from finished biographies rather than from sources of their own ((second-order)), so a theme names the lives it is made of and each of them can be entered from it.

The architecture cannot establish that the content is true. Every statement in the corpus is a model's reading of an encyclopedia article, and most of what the pipelines check is structural—identifiers resolve, schemas fill, coordinates parse. Separate scripts do hold generated dates and life spans against the cached articles, but nothing checks whether a description says what its sources say. Where an interpretation fails, it also fails quietly: a place name that does not resolve leaves its event off the map without leaving a gap the reader can see.

The social network is the encoding least protected by any of this. It is derived on its own branch and joined to the events by name, so an inconsistently written name, rather than a disagreement about the facts, is what most often makes two views of the same person diverge—and a meta story, built from finished biographies, merges those names across lives and inherits every error already in them. Replacing name matching with stable identifiers is the change the system's own failures argue for most directly.

Two kinds of evaluation would settle what the report so far only claims. Source-based checking would hold dates, places, relationships, and event selection against the articles they were derived from, extending the checks that already exist into the parts of a document that resolve to an entity. Reader studies would have to answer the question the architecture assumes an answer to: whether four coordinated encodings of one life are read as one story, and whether a reader can tell what the system took from a source from what it inferred.

## References

::: references
:::
