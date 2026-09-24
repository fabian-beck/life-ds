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
  Life Data Stories is an approach that transforms encyclopedic biographical prose into structured data stories. The stories are shown as sequences of slides that combine narrative text, timelines, maps, and social networks. A second story type, the meta story, traces a theme across several lives and presents it as one continuous scrolling document with similar visual encodings. The system separates two concerns. First, generation is performed offline by staged pipelines that combine large language-model inference with deterministic transformation. Second, the presentation is rendered by an interactive web application without further use of artificial intelligence. This technical report documents the approach and its implementation and provides a basic scientific contextualization. The source code is available at [github.com/fabian-beck/life-ds](https://github.com/fabian-beck/life-ds) and the deployed application at [fabian-beck.github.io/life-ds](https://fabian-beck.github.io/life-ds/).
---

::: teaser
:::

::: toc
:::

## Introduction

[[sources|Encyclopedic biography]] is a rich and well-sourced account of a life, written as continuous prose in long-form articles. Reading a life in that order is natural, but it hardly supports other forms of access, such as casual browsing. Such browsing would be supported by the biography's temporal, geographic, and relational structure: the phases of a life, its places, and the people involved. However, the reader cannot access this structure directly.

Life Data Stories makes this structure explicit and explorable through specific data representations. It derives from the source prose a set of discrete [[events|events]] and the documented [[ego-network|relationships]] between people. Each event has a date and, where known or available, a [[geography|place]], the people involved, and [[imagery|illustrations]]. Our approach groups those events into the phases of a life and presents the result as narrative text, as a chronology, as a geography, and as a social network. Further, a [[identity|visual identity]] is generated for each story. A similar derivation applied across several biographies yields a [[sections|meta story]], one continuous document that integrates a timeline with a lane per life, a map, and a social network merged from the individual biographies.

Segel and Heer [@segel2010narrative], surveying how data and visualization are used to tell stories, place such a presentation on a spectrum between the author-driven, in which a fixed order carries the message, and the reader-driven, in which the audience decides what to look at. A story in Life Data Stories is author-driven at first glance and reader-driven in its depth. The sequence is fixed when the story is generated and can be followed to the end. Alternative exploration affordances are available throughout, in timelines, image galleries, maps, and social network views. A meta story is linear in the same way and links to the personal stories throughout.

BiographySampo [@hyvonen2019biographysampo] is one of the closest precedents with a digital humanities focus. It extracts events, places, and relationships from national biographical dictionaries with language technology and pattern rules, links them to external registers, and offers them through faceted search, maps, timelines, and ego networks. Its tools serve biographical research and show the unchanged biography text next to the data. VisKonnect [@latif2021viskonnect] uses encodings similar to those of Life Data Stories and connects historical figures through the events they have in common. There, a reader's prompt retrieves the matching events from an event knowledge graph, and an event timeline, an event map, and a relationship graph are shown beside a short answer. Textual answers are generated but refer to intersections of lives and stay disconnected from the visual representation. In contrast, Life Data Stories integrates text and visual representation and proposes a reading order while offering exploration options.

To achieve this, we rely on [[inference|large language models]] (LLMs) for interpreting the data. A biography is at first unstructured text, and giving it structure implies deciding which episodes are important, which places they relate to, and which relationships matter. However, this needs to be done only once, before the stories are presented. The system is accordingly built in two parts that connect through the [[artifacts|data]][[figure:teaser]]. Generation runs offline as preprocessing and interleaves model calls with deterministic transformation, so steps that research or review material alternate with steps that resolve, cluster, merge, and validate the data. The processing produces a set of documents, data, and images describing one life or one theme. The interface loads those files and renders them in a single-page web application.

## Data model

The data that connects generation and interface is a semi-structured representation of a biography and the central abstraction of the system. For a single life, it holds several structured perspectives: the <<events|events>> of the life with their <<narrative|text>>, <<imagery|pictures>>, and <<places|geography>>. While these parts are relatively straightforward derivatives of the textual biographical source, two further perspectives are more interpretive: the <<network|social network>> of the subject, which the text rarely describes explicitly, and the story's <<identity|visual identity>>.

::: conceptlegend
:::

A meta story refers to the data of its subjects and adds further perspectives. It lists the subjects and groups them into subtopics. Its chapters divide the covered time span into periods, and each chapter references <<events|events>> from the subjects' data, annotated with their relevance to the theme. The subjects' ego networks are merged into one <<network|social network>>, and the <<places|locations>> of their events are clustered into places relevant to the theme. The <<narrative|text>> is written for the theme, and the <<imagery|pictures>> are selected from the events of the individual stories. Like a personal story, a meta story is presented in a generated <<identity|visual identity>>.

## Generation

We split the generation of this data into two pipelines. The first, the [[person-pipeline|personal story pipeline]], reads an encyclopedia article and writes the data of an individual biography. The second, the [[meta-pipeline|meta story pipeline]], reads the data of several individuals and writes a meta story connecting them. Both pipelines run offline as Python command-line scripts, invoked for one life or one theme at a time. A run stores the data described in the previous section as JSON documents. Each step reads the documents of earlier steps, writes its own, and belongs to one of four kinds.

::: kindlegend
:::

Both pipelines follow the same pattern: material is derived bottom-up and revised top-down. Both end in translation: each English document is translated into every other supported language (currently: German).

### Personal story pipeline

The [[person-pipeline|personal story pipeline]] derives data for one biography, from an [[sources|encyclopedia article]] to the data needed for an illustrated and individually styled story. The chart[[figure:pipeline-person]] groups its steps into seven stages. Once the sources are loaded, the events of the life are proposed from them, researched, geocoded, and matched with pictures. The story is then styled individually, and the generated pictures adopt that style. Independently of the style, the social network is derived, and a review pass revises it together with the events. Background reports then add depth to selected events, and localization closes the run.

::: pipeline lane=person
:::

*Sources*. An [[step:p_wiki_fetch|acquisition]] step loads the subject's Wikipedia article and linked article titles. An AI-based [[step:p_wiki_select|selection]] call chooses the most relevant titles before their full texts are fetched. The fetched articles are cached for reuse by later steps and reruns, together with Commons image metadata.

*Events*. The events and the main narrative are derived from this material. The first AI-based call [[step:p_events_p1|proposes]] twelve to sixteen events with titles, dates, descriptions, an optional classification, and a weight. It also groups them into three to six chapters. An AI call per event then [[step:p_events_p2|researches]] each event in detail against the relevant articles: the historic and modern name of its place, the people involved, a semantic icon, and image search queries. [[step:p_geocode|Geocoding]] looks up exact coordinates for each place by its modern name, if available.

*Images*. A [[step:p_img_search|planning]] step generates image queries for the person and the subjects of the events, which complement the per-event queries for specific objects such as a building or a document. The [[step:p_img_fetch|search queries]] are then executed against Wikimedia Commons, the life-wide ones also against Openverse, and the candidates are [[step:p_img_filter|scored]] in code on resolution, bytes per pixel, filename, and a penalty for certain subjects (e.g., a plaque only remembering an event). An AI-based [[step:p_img_match|matching]] call then assigns pictures to events, writes captions, keeps each picture's attribution, and picks a reference portrait. Because we consider the portrait the central visual element and the matching call judges by metadata only, a [[step:p_img_verify|vision]] call checks whether it depicts the subject.

*Presentation*. A [[step:p_style|color and type]] system is generated, inspired by the subject's own work. The step returns a color palette with a sentence justifying it, a tileable background pattern, a separator glyph, and a heading and a body font. The style is checked through rule-based heuristics regarding tile, font, and contrasts, and regenerated if necessary. Based on the style, especially its color palette, illustrations are generated. The reference portrait is [[step:p_portrait|style-transferred]] toward one master style shared by all subjects. Each chapter is turned into an abstract [[step:p_chapter_concepts|visual concept]] in one call over all chapters, and each concept is [[step:p_chapter_art|illustrated]] in the same style.

*Network and review*. The [[step:p_network|ego network]] is derived independently of the style, as typed, weighted, and described relationships. To increase coherence and avoid redundancies, a top-down [[step:p_review|review pass]] over the events and the network refines descriptions and applies high-confidence changes. Reading the slides in order, it potentially rewrites descriptions that rely on terms not yet introduced or repeat the previous slide.

*Depth*. A [[step:p_backgrounds|background report]] of a few paragraphs---explaining details of an event or the background of a key concept relevant to the event (e.g., an invention)---is written after the review for the most important events, roughly one event per chapter, and only where the sources provide enough material on the event. An [[step:p_illustrations|image critic]] call compares the illustrations found for each report with its text and removes images that do not match its topic.

*Localization*. To support multiple languages, a [[step:p_name_evidence|lookup]] collects the target language's names of the subject, the people, and the places from Wikipedia's language links. Based on these names, a [[step:p_glossary|glossary]] call decides once per subject which person names have an established form in the target language, and this mapping is applied to the events, the network, and the person registry alike. A person thus carries the same name in every translated document, which the interface requires because it links the documents by exact names. The [[step:p_translate|translation]] merges the translated fields over a copy of the English document, so that dates, coordinates, URLs, and identifiers stay unchanged.

### Meta story pipeline

The [[meta-pipeline|meta story generation]][[figure:pipeline-meta]] concerns a theme that connects multiple lives (e.g., an area of science, art, or political development) and builds upon the output of the personal pipelines. The story is planned and its events collected and curated against the theme. Moreover, the social network and the map are derived independently of each other. Then, a composition step joins the branches into one story and gives it a visual identity. Again, localization closes the run.

::: pipeline lane=meta
:::

*Planning*. An AI [[step:m_p1|planning]] call reads a summary of every available personal story and selects the subjects for the theme. It groups the selected people into two to four subtopics, proposes three to six chapters as named eras with estimated date ranges, and drafts a description and a conclusion. [[step:m_p2|Event collection]] then gathers every dated event of the selected people in code.

*Events*. A [[step:m_p3|curation]] call per batch of events judges each event against the theme and records why it belongs. The proposed chapters are then fitted to the surviving events. Each event is assigned to the chapter containing its year or to the nearest one, and each chapter's date range is adjusted to its events. A [[step:m_p4|context]] call adds up to two historical events per chapter that directly affected the story's people.

*Network*. The network construction starts from the subjects' ego networks. An initial [[step:m_p5|merge]] joins them by normalized name into one graph of the subjects and the related people who appear in two or more of their ego networks. Since each ego network was generated for one person, a [[step:m_p5b|review]] call reads the merged graph against excerpts of the subjects' articles and adds missing ties, rewords existing ones, and deletes indirect ones, adapting how much it changes to the density of the graph. [[step:m_clusters|Community detection]] by greedy modularity [@clauset2004finding] yields the story's circles (i.e., clusters of people), which the composition may later regroup.^[The detection merges the two connected communities whose union adds the most modularity until no merge adds any, the greedy optimization of Clauset et al. (without the heaps that make their version fast, as the examples here are small).] A [[step:m_p6|narration]] call writes a title and a short description per circle.

*Map*. The map branch starts from the chapters' events that have a location. A [[step:m_p7b|rating]] call scores each of them by the importance of its place for the story. The scores weight the [[step:m_p7a|clustering]], which merges events only while all of them lie close together and keeps the clusters with sufficient total weight, ordered by date. A [[step:m_p7c|narration]] call writes a title and a short description per cluster and decides which clusters the map keeps as stops, discarding clusters whose events have nothing in common beyond their city and places of little relevance to the theme.

*Composition*. The [[step:m_p8|composition]] call assembles the story from the generated material: it revises and connects the descriptions into a coherent story and decides the order of the sections and the final grouping of the circles. A [[step:m_style|style]] call derives from the story's framing a color palette, background pattern, fonts, and ornamental elements.

*Localization*. Each subject's name is taken from their own translated registry entry, so that a meta story uses the same name as the person's own story. The [[step:m_translate|translation]] proceeds as for personal stories and copies event titles verbatim from the translated personal stories, so that both use identical titles. Its prompt asks the model to read the whole story before translating the metaphors the theme relies on, to keep a metaphor only where the target language uses it and otherwise to state its meaning plainly, and to apply that decision consistently, including in the title.

### AI models and prompting

The generation uses OpenAI's API models ({{ pipeline.models }}). We configure the models per [[inference|call site]] to only spend frontier intelligence and reasoning effort where needed and keep generation costs manageable (below 1 EUR per generated story). We assign the largest model to composition, the one step that rewrites a whole assembled story, the image models to the portrait and chapter illustration steps, and divide the remaining steps between a reasoning tier and a small one by whether an error could remain undetected in the final data. A step uses the small model when its output is validated against existing entities, rewritten by a later step, or backed by a deterministic fallback. More advanced tasks use the reasoning tier, among them proposing the events of a life, selecting the people of a theme, reviewing another step's output, the glossary, and the translation, whose wording no later step checks or rewrites. Reasoning effort is likewise set per call.

For prompt design and context engineering, we tried to anticipate which materials a call needs and to limit the prompt to those, while still providing sufficient background. In the steps that make one call per event, the material shared by all calls is placed at the start of the prompt and the event-specific part at the end, and the request marks where the shared part ends, so that the API caches this prefix and reuses it for the later calls of the step. The steps that write the story's prose share one instruction block on writing style. It discourages typical patterns of AI-generated prose, for instance, contrasting a fact with an alternative nobody proposed. Most text responses are requested as structured output against a [Pydantic](https://docs.pydantic.dev/) schema; the style generators request JSON objects and validate them in code.

## Interface

Life Data Stories' frontend is a mobile-first Svelte application that loads and renders the generated data. The layout is designed for the phone and adapts responsively to larger screens; the screenshots in this report are deliberately captured at both phone and desktop width. The landing page offers access to the two story types, which organize the data differently: a [[slides|personal story]] follows one life in order, and a [[sections|meta story]] follows a theme across several lives. On the landing page[[figure:landing]], the meta stories are displayed in a [[landing.carousel|carousel]] at the top. Below them, the [[landing.grid|personal stories]] can be reached via their generated portrait, by filtering on role, by search, or by viewing a map that plots the place of every event across the corpus. Clicking a marker there shows the event, and one more tap opens the personal story on its slide. In the following, we walk through both story types in more detail. Throughout, we use the meta story *Architecture as Living Form* and the personal story of *Antoni Gaudí* as running examples.

::: screenshot id=landing route="#/en" width=1280 height=1000 settle=2500 caption="The landing page: a carousel of meta stories above, the personal stories in a filterable grid below."
@carousel 471,101,769,400 Meta story carousel
Cycles through the meta stories, each with title, subtitle, and "Story" and "Filter" shortcuts.
@grid 48,735,1184,260 Filterable story grid
One tile per personal story, with generated portrait, lifespan, roles, and a one-line description.
:::

### The meta story

A meta story is structured as an opening scene, up to three sections (a timeline, a map, and a social network), and a closing conclusion, followed by a grid linking to the personal stories of its subjects. The whole is read from top to bottom by scrolling. *Architecture as Living Form* follows nine architects who explored organic shapes in architecture and worked across more than a century.

*Timeline.* After a short textual introduction, the vertical scrolling turns horizontal as the reader reaches the [[meta-timeline-environment.whole|timeline visualization]][[figure:meta-timeline-environment]]. In *Architecture as Living Form*, a timeline of [[meta-timeline-environment.lanes|nine lanes]], one per architect, shows events as dots along each lane. A sequence of guiding [[meta-timeline-environment.card|story cards]], marking chapters in the development, is pinned near the top and leads the reader through the timeline. Tapping or clicking a dot opens a brief description of the event. The surrounding card links to that architect's personal story. A second layer above the lanes marks historical events affecting several lives at once, such as World War II.

::: screenshot id=meta-timeline-environment route="#/en/meta/organic_shapes_in_architecture" width=1280 height=820 wait=".timeline-horizontal-container" anchor=".timeline-horizontal-container" scroll=500 settle=3000 caption="The timeline: one lane per architect, with a guiding story card in front naming the span currently in focus."
@whole 0,0,1280,820 Timeline visualization
The timeline: one lane per architect, with a guiding story card in front naming the span currently in focus.
@card 170,58,580,90 Guiding story card
Names the span of years currently in focus and summarizes the events of that period across the lives.
@lanes 0,230,1280,530 Nine architect lanes
One lane per architect, grouped into thematic clusters, with events marked as dots along each line.
:::

*Map.* The second section shifts the focus to the locations where the architects' work took place. A non-interactive [[meta-map.map|map]][[figure:meta-map]] fills the background behind the scrollable story cards, flying to a new location as each one scrolls into view. It zooms to a point or fits a bounding box depending on how spread out the events are. Each [[meta-map.events|event]] listed on a card links directly to the respective personal story.

::: screenshot id=meta-map route="#/en/meta/organic_shapes_in_architecture" width=390 height=874 wait=".map-section" anchor=".map-section" scroll=1100 settle=3000 caption="A location card, with the map above and its linked events below."
@map 0,43,390,420 The background map
Flies to a new location as each card scrolls into view.
@events 20,775,350,99 Linked events
Each listed event links to its slide in the personal story.
:::

*Network.* The third section is a [[meta-network.whole|graph]][[figure:meta-network]] that displays the architects and the documented connections between them. Its force-directed layout is calculated in the background and finalized before it is displayed. The precomputed data groups people into clusters. As the reader scrolls, one [[meta-network.card|card]] per cluster moves over the graph and describes it, and the people and connections involved are [[meta-network.cluster|highlighted]], while the rest of the graph darkens.

::: screenshot id=meta-network route="#/en/meta/organic_shapes_in_architecture" width=390 height=844 wait=".network-section" anchor=".network-section" scroll=800 settle=3000 caption="The network: architects as nodes, one card in front naming the cluster currently highlighted."
@whole 0,0,390,844 The network view
The full graph of architects, with one card in front naming the cluster currently highlighted.
@cluster 15,285,275,300 Gaudí, Hundertwasser, Aalto, Wright, and Otto, highlighted
Outlined while the rest of the graph is dimmed.
@card 8,557,364,287 A Chain of Influence
Describes the chain of connections currently highlighted: Gaudí's forms taken up by Hundertwasser and Otto, Otto's acquaintance with Wright, and Wright's praise for Aalto.
:::

The meta story ends with a brief summary of the nine lives, followed by a grid of tiles linking to the architects' personal stories.

### Personal story

Gaudí's personal story begins with the stylized portrait and a short biographical summary. The encodings of time, place, and relation that a meta story shows in separate sections also accompany this sequence. The story is a horizontal sequence of slides, navigated by swiping sideways. Chapter slides, showing a headline and an illustration, structure the [[gaudi-relationship-card.whole|event slides]][[figure:gaudi-relationship-card]] that provide the main information. Beside the details of the event, an image may be shown. For events with supporting material, the slide extends vertically: a chevron reveals a longer background passage about the context of the event. Special events such as birth, death, publication, or migration contain further structuring elements and specialized representations.

::: screenshot id=gaudi-relationship-card route="#/en/story/antoni_gaud?slide=12" width=390 height=844 wait=".story-view" settle=3500 caption="The standard event slide: text in the middle, a map beneath, and an icon outline at the bottom."
@whole 0,0,390,844 The event slide
The standard slide format: running text in the middle, an accumulating map beneath, and an icon outline at the bottom.
@tag 44,430,138,36 Eusebi Güell, tagged as patron
Tapping it opens a card describing the relationship in detail.
@map 0,540,390,220 The accumulating map
Gains a new marker at each event's main place, here Barcelona.
@icons 0,798,390,46 Event icon row
One icon per event, shaped by its type, and a plain marker per chapter.
:::

*Timeline.* As an explicit representation of time, a [[gaudi-relationship-card.icons|row]] along the bottom serves as both a progress marker and an outline. Each event is shown as an icon reflecting its type and each chapter as a plain marker. Tapping the chapter label above the row unfolds it into a full-screen [[gaudi-timeline.whole|outline]] of the life[[figure:gaudi-timeline]], the icons traveling from their places in the row to their entries in the list. The outline runs from the overview to the conclusion, with each chapter as a [[gaudi-timeline.chapter|heading]] that names its main location and each [[gaudi-timeline.event|event]] beneath its chapter with year, the subject's age, and title. Each [[gaudi-timeline.offset|entry]] is set in from the left in proportion to the subject's age at that point, so the pace of the life stays visible where the list is dense. Tapping an entry moves the story to that slide.

::: screenshot id=gaudi-timeline route="#/en/story/antoni_gaud?slide=12&timeline=1" width=390 height=844 wait=".expanded-timeline-container" settle=3500 caption="The expanded timeline: the life as a vertical outline of chapters and events, each entry indented in proportion to the subject's age."
@whole 0,0,390,844 The expanded outline
The row of icons unfolded into a full-screen list of chapters and events, from the overview to the conclusion.
@chapter 54,160,300,53 A chapter heading
Names the chapter and its main location; tapping it moves the story to the chapter slide.
@event 88,440,220,40 The current event
Icon, year, the subject's age, and title, highlighted as the slide the reader came from.
@offset 20,75,120,700 The age offset
Every entry is set in from the left in proportion to the subject's age, a faint line marking the offset.
:::

*Map.* The map stays in place across slides and adds a marker at each event's main place, so that by the end of the story it shows everywhere the subject worked and lived. In the example, the event's [[gaudi-relationship-card.map|main marker]] is in Barcelona, while faded smaller markers show the places of earlier events, in Paris and near Barcelona.

*Network.* When an event slide mentions another person, that person's name appears beside the text with their role, as here for [[gaudi-relationship-card.tag|Eusebi Güell]], tagged as patron. Tapping the tag opens a card describing the relationship. From this card, or the button at the top of the screen, readers can access [[gaudi-network.whole|Gaudí's full network]][[figure:gaudi-network]]. It is organized by relationship category, family first and then the others in alphabetical order, academic, business, professional, and religious in Gaudí's case. Each category shows a count and a short introductory [[gaudi-network.summary|passage]] with the mentioned names and roles highlighted. Its people appear as chips grouped by role: the family as [[gaudi-network.generations|generations]] around the subject, joined by lines, and the other categories as chips labeled by role, gathered into [[gaudi-network.boxes|boxes]] where a role repeats, such as client or collaborator. Tapping a chip opens the description and strength of that relationship.

::: screenshot id=gaudi-network route="#/en/story/antoni_gaud?slide=12&network=1" width=390 height=844 wait=".network-modal" settle=3500 caption="The network view of a personal story: relationships by category, the family laid out as generations around the subject and the other categories as chips labeled by role."
@whole 0,0,390,844 The network view
The subject's relationships by category, each introduced by a short passage and laid out as chips grouped by role.
@summary 20,125,350,125 The family passage
Introduces the group, with the mentioned names and roles highlighted.
@generations 45,255,300,365 The family as generations
Parents and siblings above the subject's portrait, the niece below, joined by lines.
@boxes 20,635,350,170 The academic category
A single chip with the role teacher; where a role repeats, the chips are gathered into a box labeled by the role.
:::

## Discussion and conclusion

This report has introduced the implementation of Life Data Stories, an approach for transforming unstructured biographical text into structured stories about individual lives and the themes that connect them. It defines the main structuring elements of these stories: [[events|life events]], [[narrative|narrative text]], [[imagery|imagery]], [[geography|geography]], and [[ego-network|social network]] views, which together provide affordances for interactive exploration. The stories share a consistent design, while their [[identity|visual identity]] adapts to the specific person. The approach relies on [[inference|AI-based extraction]] to derive the underlying structured data. This step runs as preprocessing, so the presentation layer stays independent of further AI calls. At the same time, the resulting stories remain highly interactive through the extracted data layers and the connections between them.

While this report provides implementation details and a basic scientific contextualization, a broader scientific discussion is beyond its scope. Such a discussion would examine related research and its empirical results in more detail. Likewise, an evaluation of the approach remains future work. As the approach targets a broad audience, feedback from this audience will be an important part of such an evaluation. Beyond usability and the perceived value of the approach, it should investigate to what extent users accept AI-based transformations of biographical sources and what expectations they have regarding such transformations.

## References

::: references
:::
