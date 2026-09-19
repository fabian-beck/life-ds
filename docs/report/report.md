---
title: Life Data Stories
subtitle: Generating and presenting biographical data stories
authors:
  Fabian Beck | University of Bamberg | https://www.uni-bamberg.de/en/vis/team/prof-dr-fabian-beck/ | 0000-0003-4042-3043
  Leah Mühlöder | University of Bamberg | https://www.uni-bamberg.de/en/vis/team/leah-muehloeder/ | 0009-0000-3510-1686
  Till Nagel | Mannheim University of Applied Sciences | https://services.informatik.hs-mannheim.de/~nagel/ | 0000-0001-5400-091X
description:
  Technical report on the Life Data Stories system: its data model, its two
  generation pipelines, and its interface.
disclaimer:
  This report was co-written with AI. Its text and figures were drafted and revised with language models under the authors' direction, alongside manual edits. The system the report describes was implemented through AI using agentic engineering.
abstract:
  Life Data Stories transforms encyclopedic biographical prose into structured data stories. The stories are shown as sequences of slides in which a life is presented as a multi-faceted representation that combines narrative text, timelines, maps, and social networks. A second story type, the meta story, traces a theme across several lives and presents it as one continuous document in which similar visual encodings are read by scrolling. The system separates two concerns. First, generation is performed offline by staged pipelines that combine intelligent language-model inference with deterministic transformation. Second, the presentation is rendered deterministically by an interactive web application. This technical report documents the implemented solution and provides a basic scientific contextualization. The source code is available at [github.com/fabian-beck/life-ds](https://github.com/fabian-beck/life-ds) and the deployed application at [fabian-beck.github.io/life-ds](https://fabian-beck.github.io/life-ds/).
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

To achieve this, we heavily rely on [[inference|large language models]] (LLMs) for interpreting the data. A biography is at first unstructured text, and giving it structure means deciding which episodes are important, which places they relate to, and which relationships matter. However, this only needs to be done once, not as part of the user interface. The system is accordingly built in two parts that connect through the [[artifacts|data]][[figure:teaser]]. Generation runs offline as preprocessing and interleaves model calls with deterministic transformation, so a step that researches or reviews material is surrounded by steps that resolve, cluster, merge, and validate what the model returned. It produces a set of documents, data, and images describing one life or one theme. The interface loads those files and renders them as a matter of presentation alone in a single-page web application.

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

The [[person-pipeline|personal story pipeline]] derives data for one biography, from an [[sources|encyclopedia article]] to the data needed for an illustrated and individually styled story. The chart[[figure:pipeline-person]] bands its steps into seven phases: the sources are gathered; the events are proposed, researched, and geocoded; their pictures are found; the story is given a style and generated pictures; the social network is derived and both datasets are reviewed; a depth layer of background reports is written; and localization closes the run.

::: pipeline lane=person
:::

*Sources*. An [[step:p_wiki_fetch|acquisition]] step loads the subject's Wikipedia article and linked article titles. An AI-based [[step:p_wiki_select|selection]] call selects the most relevant titles before their full texts are fetched. The fetched articles are cached for reuse by later steps and reruns, together with Commons image metadata.

*Events*. The events and the main narrative are derived from that material. The first AI-based call [[step:p_events_p1|proposes]] twelve to sixteen events with titles, dates, descriptions, an optional classification, and a weight, and groups them into three to six chapters. A second call per event then [[step:p_events_p2|researches]] each event in detail against the relevant articles: the historic and modern name of its place, the people involved, a semantic icon, and image searches that would illustrate it. [[step:p_geocode|Geocoding]] looks up exact coordinates for the places by their modern names where the research supplied one.

*Images*. A [[step:p_img_search|planning]] step generates queries for images relating to the person's name and the subjects of the events, while the per-event searches name specific objects such as a building or a document. The [[step:p_img_fetch|search queries]] are then executed against Wikimedia Commons, the life-wide ones also against Openverse, and the candidates are [[step:p_img_filter|scored]] in code on resolution, bytes per pixel, filename, and a penalty for commemorative subjects before an AI-based [[step:p_img_match|matching]] call assigns pictures to events, writes captions, keeps each picture's attribution, and picks a reference portrait. Since the matching call judges by metadata only, a [[step:p_img_verify|vision]] call checks whether the chosen portrait, which we consider the most central visual representation, actually depicts the subject.

*Presentation*. A [[step:p_style|color and type]] system is derived from the subject's own work. The step is shown the events of the life that depict something—a building, a first edition, a manuscript, an instrument—together with the captions of the pictures the story carries, and it returns the palette with a sentence naming what that palette was read off. Selecting the events for what they show rather than for their place in the chronology is what makes the derivation possible: an opening run of births and schooldays is the same for every subject and supports no palette at all. The style is checked through rule-based heuristics regarding tile, font, and contrasts, and regenerated if necessary. Considering the style (especially the color palette), illustrations are generated: the reference portrait is [[step:p_portrait|style-transferred]] toward one master style shared by all subjects, each chapter is turned into an abstract [[step:p_chapter_concepts|visual concept]] in one call over all chapters, and each concept is [[step:p_chapter_art|drawn]] in the same style.

*Network and review*. The [[step:p_network|ego network]] is derived independently of the style, as typed, weighted, and described relationships. A [[step:p_review|review]] pass over the events and the network refines descriptions but applies only high-confidence changes. Reading the slides in order, it potentially rewrites descriptions that rely on terms not yet introduced or repeat the previous slide.

*Depth*. A [[step:p_backgrounds|background report]] of a few paragraphs---explaining details of an event or the background of a key concept relevant to the event (e.g., an invention)---is written after the review for the most important events, roughly one event per chapter, and only where the sources say something around the event itself---an event they record in half a sentence gets no report, and the story then offers no way down there. A [[step:p_illustrations|critic]] call reads the illustrations found for it against the report, filtering out images that do not fully match the scope of the respective topic.

*Localization*. To be able to provide multiple language options, a [[step:p_name_evidence|lookup]] collects the target language's names of the subject, the people, and the places from Wikipedia's language links. A [[step:p_glossary|glossary]] call fixes once per subject how every person's name is rendered, since cross-references between the translated documents are matched on exact names. The [[step:p_translate|translation]] merges the translated fields over a copy of the English document, so that dates, coordinates, URLs, and identifiers stay unchanged.

### Meta story pipeline

The [[meta-pipeline|meta story generation]][[figure:pipeline-meta]] concerns a theme that connects multiple lives (e.g., an area of science, art, or political development) and builds upon the output of the personal pipelines. The story is planned and its events collected and curated against the theme. Moreover, the social network and the map are derived independently of each other. Then, a composition step joins the branches into one story and gives it a visual identity. Again, localization closes the run.

::: pipeline lane=meta
:::

*Planning*. An AI [[step:m_p1|planning]] call reads a summary of every subject and decides whom to involve from the list of available personal stories. It groups the selected people into two to four subtopics, proposes three to six chapters as named eras with estimated date ranges, and drafts a description and a conclusion. [[step:m_p2|Event collection]] then gathers every dated event of the selected people in code.

*Events*. A [[step:m_p3|curation]] call per batch of events judges each event against the theme and records why it belongs. The proposed chapters are then fitted to the surviving events. Each event goes to the chapter containing its year or to the nearest one, and each span snaps to its events. A [[step:m_p4|context]] call adds up to two historical events per chapter that affected the story's people or are important historic reference points.

*Network*. The network construction starts from the subjects' ego networks. An initial [[step:m_p5|merge]] joins them by normalized name into one graph of the subjects and the related people who appear in two or more of their ego networks. Since each ego network was generated for one person, a [[step:m_p5b|review]] call reads the merged graph against excerpts of the subjects' articles and adds ties the ego networks missed, rewords them, or deletes indirect ones, generously on a sparse graph and strictly on a dense one. [[step:m_clusters|Community detection]] by greedy modularity [@clauset2004finding] yields the story's circles (i.e., clusters of people), which the composition may later regroup.^[The detection merges the two connected communities whose union adds the most modularity until no merge adds any, the greedy optimization of Clauset et al. (without the heaps that make their version fast, as the examples here are small).] A [[step:m_p6|narration]] call writes a title and a short description per circle.

*Map*. The map branch starts from the located events the chapters reference. A [[step:m_p7b|rating]] call scores each of them by how important the place appears to be for the story. The scores weight the [[step:m_p7a|clustering]], which merges events only while all of them lie close together and keeps the clusters whose weights add up, ordered by date. A [[step:m_p7c|narration]] call writes a title and a short description per cluster and decides which clusters the map keeps as stops, discarding groupings that merely share a city and places that would only pad the map.

*Composition*. The [[step:m_p8|composition]] call assembles the story based on the previously generated materials. In one call it revises and connects the descriptions into a coherent and consistent story and decides the order of the sections and the final grouping of the circles. A [[step:m_style|style]] call derives from its framing a color palette, background pattern, fonts, and ornamental elements.

*Localization*. Each subject's name is taken from their own translated registry entry, so that a meta story calls a person what their own story calls them. The [[step:m_translate|translation]] follows the same contract as a person's data and copies event titles verbatim from the translated person data, so that chapter and slide never disagree. Its prompt asks the translator to read the whole story before rendering the images its theme rides on, to keep a picture only where the target language uses it and otherwise to say plainly what it meant, and to hold to that decision in every passage, the title included.

### AI models and prompting

The generation uses OpenAI's API models ({{ pipeline.models }}). We configure the models per [[inference|call site]] to only spend frontier intelligence and reasoning effort where needed and keep generation costs manageable (below 1 EUR per generated story). We assign the largest model to composition, the one step that reads a whole assembled story, the image models to the portrait and chapter illustration steps, and divide the remaining steps between a reasoning tier and a small one by whether a wrong answer can quietly become part of the corpus. A step uses the small model when its output is validated against existing entities, rewritten by a later step, or backed by a deterministic fallback. More advanced tasks use the reasoning tier: proposing the events of a life, selecting the people of a theme, reviewing another step's output, the glossary, and the translation, whose wording no later step checks or rewrites. Analogously, reasoning effort is differentiated between different calls.

For prompt design and context engineering, we tried to anticipate which materials a call needs and to limit the prompt to those, while still providing sufficient background. The material shared by all calls of a step is placed at the start of the prompt and the event-specific part at the end, and the request marks where the shared part ends, so that the API caches that prefix and the later calls of the step read it instead of sending it again. Without such a marker the API caches each prompt whole, and a prompt ending in its own event is one no other call can reuse. All steps that produce text a reader sees share one instruction block on writing style. It discourages typical patterns of AI-generated prose, for instance, contrasting a fact with an alternative nobody proposed. Most text responses are requested as structured output against a [Pydantic](https://docs.pydantic.dev/) schema; the style generators request JSON objects and validate them in code.

## Interface

Life Data Stories' frontend is a mobile-first Svelte application that loads the data the generation pipelines produced and renders it. The layout is designed for the phone and adapts responsively to larger screens; the screenshots in this report are deliberately captured at both phone and desktop width. The landing page offers access to the two story types, which organize the data differently: a [[slides|personal story]] follows one life in order, and a [[sections|meta story]] follows a theme across several lives. On the landing page[[figure:landing]], the meta stories are displayed in a [[landing.carousel|carousel]] at the top. Below them, the [[landing.grid|personal stories]] can be reached via their generated portrait, by filtering on role, by search, or by viewing a map that plots every place mentioned across the corpus. Clicking a marker there opens directly onto the event it belongs to inside a personal story. In the following, we walk through both story types in more detail. Throughout, we use the meta story *Architecture as Living Form* and the personal story of *Antoni Gaudí* as running examples.

::: screenshot id=landing route="#/en" width=1280 height=1000 settle=2500 caption="The landing page: a carousel of meta stories above, the personal stories in a filterable grid below."
@carousel 471,101,769,400 Meta story carousel
Cycles through the meta stories, each with title, subtitle, and a "Story" or "Filter" shortcut.
@grid 48,735,1184,260 Filterable story grid
One tile per personal story, with generated portrait, lifespan, roles, and a one-line description.
:::

### The meta story

A meta story is structured as an opening scene, up to three sections---relating to components such as timeline, social network, and map---and a closing conclusion, followed by a grid linking to the people it covers. The whole is read from top to bottom by scrolling. *Architecture as Living Form* follows nine architects who explored organic shapes in architecture and worked across more than a century.

*Timeline.* After a short textual introduction, the vertical scrolling turns horizontal as the reader reaches the [[meta-timeline-environment.whole|timeline visualization]][[figure:meta-timeline-environment]]. In *Architecture as Living Form*, a timeline of [[meta-timeline-environment.lanes|nine lanes]], one per architect, shows events that are marked as dots along each lane. A sequence of guiding [[meta-timeline-environment.card|story cards]], marking chapters in the development, is pinned near the top and leads the reader through the timeline. Tapping or clicking on a dot representing an event opens a brief description of it. The surrounding card instead leads into that architect's personal story. Above the lanes is a second layer of annotations that marks the historical events affecting several lives at once, such as World War II.

::: screenshot id=meta-timeline-environment route="#/en/meta/organic_shapes_in_architecture" width=1280 height=820 wait=".timeline-horizontal-container" anchor=".timeline-horizontal-container" scroll=500 settle=3000 caption="The timeline: one lane per architect, with a guiding story card in front naming the span currently in focus."
@whole 0,0,1280,820 Timeline visualization
The timeline: one lane per architect, with a guiding story card in front naming the span currently in focus.
@card 170,58,580,90 Guiding story card
Names the span of years currently in focus and describes what happened across the lives within it.
@lanes 0,230,1280,530 Nine architect lanes
One lane per architect, grouped into thematic clusters, with events marked as dots along each line.
:::

*Map.* The second section shifts the focus to the locations where the architects' work took place. A non-interactive [[meta-map.map|map]][[figure:meta-map]] fills the background behind the scrollable story cards, flying to a new location as each one scrolls into view. It zooms to a point or fits a bounding box depending on how spread out the events are. Each [[meta-map.events|event]] listed on a card links directly to the respective personal story.

::: screenshot id=meta-map route="#/en/meta/organic_shapes_in_architecture" width=390 height=874 wait=".map-section" anchor=".map-section" scroll=1100 settle=3000 caption="A location card, with the map flown in above and its linked events listed below."
@map 0,43,390,420 The background map
Flies to a new location as each card scrolls into view.
@events 20,775,350,99 Linked events
Each relevant event listed here links directly to the personal story slide where that event is introduced.
:::

*Network.* The third section is a [[meta-network.whole|graph]][[figure:meta-network]] that displays the architects and the documented connections between them. Its force-directed layout is calculated in the background and finalized before it is displayed. As precomputed, the data groups people into clusters. As the reader scrolls, [[meta-network.card|cards]] move over the graph, one per cluster, describing it, and the people and connections involved are [[meta-network.cluster|highlighted]], while the rest of the graph darkens.

::: screenshot id=meta-network route="#/en/meta/organic_shapes_in_architecture" width=390 height=844 wait=".network-section" anchor=".network-section" scroll=800 settle=3000 caption="The network: architects as nodes, one card in front naming the cluster currently lit."
@whole 0,0,390,844 The network view
The full graph of architects, with one card in front naming the cluster currently lit.
@cluster 15,285,275,300 Gaudí, Hundertwasser, Aalto, Wright, and Otto, lit
Ringed and connected while the rest of the graph darkens into the background.
@card 8,557,364,287 A Chain of Influence
Describes the chain of connections currently lit: Gaudí's forms taken up by Hundertwasser and Otto, Otto's acquaintance with Wright, and Wright's praise for Aalto.
:::

The meta story concludes with a brief summary that ties the nine lives together. Below that is a grid of tiles, one for each architect, that links out to the architects' personal stories.

### Personal story

Following that grid into Gaudí's personal story opens it at its beginning, showing the stylized portrait image and a short biographical summary. The same three encodings of time, place, and relation that a meta story spreads across sections are attached to this sequence too, just differently. The story unfolds as a horizontal sequence of slides, moved through by swiping sideways. Chapter slides, showing a headline and an illustration, structure the [[gaudi-relationship-card.whole|event slides]][[figure:gaudi-relationship-card]] that provide the main information. Aside details of the event, an image might be blended in. For events with supporting data, a vertical axis opens further. A chevron reveals a longer background passage about the context of the event. Special events such as birth, death, publication, or migration contain further structuring elements and specialized representations.

::: screenshot id=gaudi-relationship-card route="#/en/story/antoni_gaud?slide=12" width=390 height=844 wait=".story-view" settle=3500 caption="The classic format of the slide includes text in the middle, a map beneath, and an outline consisting of icons at the bottom."
@whole 0,0,390,844 The event slide
The classic slide format: running text in the middle, an accumulating map beneath, and an icon outline at the bottom.
@tag 44,430,138,36 Eusebi Güell, tagged as patron
Tapping it opens a card describing the relationship in detail.
@map 0,540,390,220 The accumulating map
Gains a new marker each time the running text names a place, here Barcelona.
@icons 0,798,390,46 Event icon row
There is one icon per event, shaped according to its type, and a plain marker for each chapter.
:::

*Timeline.* As an explicit representation of time, a [[gaudi-relationship-card.icons|row]] along the bottom serves as both a progress marker and an outline. Each event is represented by an icon that reflects its type, while each chapter is represented by a plain marker. Tapping the row unfolds it into a full-screen [[gaudi-timeline.whole|outline]] of the life[[figure:gaudi-timeline]], the icons traveling from their places in the row to their entries in the list. The outline runs from the overview to the conclusion, with each chapter as a [[gaudi-timeline.chapter|heading]] that names its main location and each [[gaudi-timeline.event|event]] beneath its chapter with year, the subject's age, and title. Each [[gaudi-timeline.offset|entry]] is set in from the left in proportion to the subject's age at that point, so the pace of the life stays visible where the list is dense. Tapping an entry closes the outline and moves the story to that slide.

::: screenshot id=gaudi-timeline route="#/en/story/antoni_gaud?slide=12&timeline=1" width=390 height=844 wait=".expanded-timeline-container" settle=3500 caption="The expanded timeline: the life as a vertical outline of chapters and events, each entry led in by a line that grows with the subject's age."
@whole 0,0,390,844 The expanded outline
The row of icons unfolded into a full-screen list of chapters and events, from the overview to the conclusion.
@chapter 54,160,300,53 A chapter heading
Names the chapter and its main location; tapping it moves the story to the chapter slide.
@event 88,440,220,40 The current event
Icon, year, the subject's age, and title, lit because it is the slide the reader came from.
@offset 20,75,120,700 The age offset
Every entry is set in from the left in proportion to the subject's age, a faint line marking the offset.
:::

*Map.* Fixed in the same position on the screen, the map receives a marker each time an event mentions a place. Hence, by the end of the story, the map shows everywhere the subject worked and lived. In the example, the event's [[gaudi-relationship-card.map|main marker]] is on Barcelona, while a secondary marker is visible on Paris and a faded smaller one close to Barcelona.

*Network.* When an event slide mentions another person, that person's name appears beside the text with their role, as here for [[gaudi-relationship-card.tag|Eusebi Güell]], tagged as patron. Tapping the tag opens a card describing the relationship on its own terms. From this card, or the button at the top of the screen, readers can access [[gaudi-network.whole|Gaudí's full network]][[figure:gaudi-network]]. It is organized by relationship category, family first and then the others in alphabetical order, academic, business, professional, and religious in Gaudí's case. Each category has a count and a short [[gaudi-network.summary|passage]] that introduces its people, with the names and roles it mentions highlighted, and lays them out as chips grouped by role: the family as [[gaudi-network.generations|generations]] around the subject, joined by lines, and the other categories in [[gaudi-network.boxes|boxes]] labeled by role, such as collaborator or patron. Tapping a chip opens the description and strength of that relationship.

::: screenshot id=gaudi-network route="#/en/story/antoni_gaud?slide=12&network=1" width=390 height=844 wait=".network-modal" settle=3500 caption="The network view of a personal story: relationships by category, the family laid out as generations around the subject and the other categories in boxes labeled by role."
@whole 0,0,390,844 The network view
The subject's relationships by category, each introduced by a short passage and laid out as chips grouped by role.
@summary 20,125,350,125 The family passage
Introduces the group; the names and roles it mentions are highlighted.
@generations 45,255,300,365 The family as generations
Parents and siblings above the subject's portrait, the niece below, joined by lines.
@boxes 20,635,350,170 An academic box
The other categories are boxes labeled by role, here the teacher of the academic category.
:::

## Discussion and conclusion

This report has introduced the implementation of Life Data Stories, an approach for transforming unstructured biographical text into structured stories about individual lives and the themes that connect them. It defines the main structuring elements of these stories: [[events|life events]], [[narrative|narrative text]], [[imagery|imagery]], [[geography|geography]], and [[ego-network|social network]] views, which together provide affordances for interactive exploration. The stories follow one consistently styled theme while their [[identity|visual identity]] adapts to the specific person, which gives each story a recognizable visual profile. The approach relies on [[inference|AI-based extraction]] to derive the underlying structured data. This step runs as preprocessing, so the presentation layer stays independent of further AI calls. At the same time, the resulting stories remain highly interactive through the extracted data layers and the connections between them.

While this report provides implementation details and a basic scientific contextualization, a broader scientific discussion is beyond its scope. Such a discussion would consider related scientific explorations in similar directions and the corresponding empirical work in more detail. Likewise, an evaluation of the approach has not been part of the present focus and remains future work. As the approach targets a broad audience, feedback from users within this audience will be an important part of such an evaluation. Beyond usability and the perceived value of the approach, it should investigate to what extent users accept AI-based transformations of biographical sources and what expectations they have regarding such transformations.

## References

::: references
:::
