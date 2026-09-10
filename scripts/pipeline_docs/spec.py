#!/usr/bin/env python3
"""The hand-maintained shape of the generation pipeline.

This is the only file in `pipeline_docs` that a human edits when the pipeline
changes, and it deliberately holds just the things a parser cannot infer:
which processing steps exist, which data actually flows between them, and
which artifacts they read and write. Everything factual about a step—its model,
reasoning effort, output schema, prompt text, CLI flags—is pulled from the
source by `introspect.py` and must not be duplicated here.

The pipeline is a DAG, not a sequence. `Step.depends_on` names the steps whose
*output this step consumes*, with a label for the data that travels along the
edge; the drawing derives the layers from that graph, so two steps only share a
layer when neither can see the other's result. Orchestrator functions are
deliberately absent: `generate_person.main` and `generate_meta_story.main` only
call the steps in an order, and drawing them as nodes made the chart look like
a chain when it is a fork.

Only *direct* edges are declared. An edge that another chain of edges already
implies—the image matching reads the event skeletons, but it is reached from
them through the search planning and the search itself—says nothing the reader
cannot follow along the strand, and drawing it doubled the lines crossing the
chart. Such an edge is left out; the step's `summary` and `inputs` still record
what it reads. Leaving one in changes no layer, since the longest path is
unaffected, so `validate.py` reports it as a warning rather than an error, and
naming the implying path lets a maintainer judge it. The chart re-derives the
skipped connection whenever a filter hides the steps in between, so a strand
never breaks.

`Step.inputs` and `Step.outputs` name the artifacts a step consumes and
produces. The chart does not draw them; the step note and the appendix list
them. Each artifact declares the concept it carries, and the report names that
concept—its name and its glyph—rather than the path it is stored at.

Writing a document is not a step—every step writes something—so the point
where a pipeline's strands become the document every later step reads is not
drawn as a node. The steps that read the finished life events depend on the
last call of the run that produces them, the portrait check, and the geocoder
is a leaf: its coordinates go into the document and are read by the
application and by the meta pipeline's map branch, never by a later step of
this pipeline. The same holds for the meta story, whose style and translation
depend on the composition that finishes it.

`GROUPS` are the phases of each pipeline. Every step belongs to exactly one,
and a phase names a concern that spans several layers—planning image searches,
running them and matching the results are three layers of one job—so the chart
aligns each phase's steps to read as one strand under a banded label. The chart
aligns only the parts of a phase that are continuous, so a member separated
from the rest by layers the phase has no step in is placed on its own.
Grouping is presentation only: it never changes a layer, and the layer is
still the longest dependency path.

Each step names a `script` and a `function`. `validate.py` checks that both
still exist, that the dependency graph is acyclic, that every step is in one
phase, and that no AI call site in the codebase is left unclaimed, so a step
added to the pipeline without a spec entry fails the docs build instead of
quietly going undocumented.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

PERSON = "person"
META = "meta"
SHARED = "shared"

LANES: Dict[str, Dict[str, str]] = {
    PERSON: {
        "label": "Personal story",
        "entry": "scripts/generate_person.py",
        "blurb": (
            "One biography, from a Wikipedia article to a scroll-snapped story: "
            "life events, ego network, interface style, portrait, chapter art, "
            "review, translation."
        ),
    },
    META: {
        "label": "Meta story",
        "entry": "scripts/generate_meta_story.py",
        "blurb": (
            "A theme across many biographies: person selection, event curation, "
            "a derived social network, a geographic map, and a final pass that "
            "rewrites every text in one voice."
        ),
    },
    SHARED: {
        "label": "Shared subsystems",
        "entry": "",
        "blurb": (
            "Sourcing, geocoding, review and localization—used by both "
            "pipelines and run as their own scripts too."
        ),
    },
}

# Step kinds drive both color and the "AI only" filter in the chart.
AI = "ai"
CODE = "deterministic"
EXTERNAL = "external"
IMAGE = "image"


@dataclass
class Artifact:
    """Something the pipeline produces or consumes, and where it happens to live.

    `path` is the ground truth for a maintainer and stops there: the report
    speaks about the *concept* an artifact carries—source material, life
    events, the social network—and never about the file that holds it. A path
    is an implementation detail of storage, and naming it in a figure invites
    the reader to reason about a directory instead of about the system.
    """

    id: str
    label: str
    path: str
    kind: str  # cache | dataset | registry | asset
    note: str = ""
    concept: str = ""
    """Which entry of `concepts.CONCEPTS` this artifact carries, and thus which
    glyph stands for it wherever the report draws it."""


@dataclass
class Dep:
    """One edge of the DAG: `on` produces data that the declaring step reads."""

    on: str
    data: str
    """What travels along the edge, in the vocabulary of the pipeline."""


@dataclass
class Step:
    """One processing step, anchored to a real function in the source."""

    id: str
    label: str
    lane: str
    kind: str
    script: str
    function: str
    summary: str
    depends_on: List[Dep] = field(default_factory=list)
    prompts: List[str] = field(default_factory=list)
    inputs: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    calls_per_run: str = "1"
    skip_flag: Optional[str] = None
    model_note: Optional[str] = None
    byline: Optional[str] = None
    """The one line the figure prints under the step's name in place of its
    kind: what a step that calls no model actually does—the service it asks,
    the rule it applies. A model step prints its kind and its model instead,
    which already say as much. Required for deterministic and external steps,
    and kept to about thirty characters, the width of a node."""
    model_from: Optional[str] = None
    """Script whose `--model` default supplies this step's model.

    Needed for steps that are library modules with no CLI of their own, or that
    delegate the actual API call to a helper: the call site knows only the
    `model` its caller handed it, so the value has to come from the entry point.
    """


@dataclass
class Group:
    """One phase of a pipeline: steps of one concern, aligned into one strand.

    A phase is a reading aid, not a dependency: its members usually form a
    chain, but they may also sit in the same layer (two sourcing calls that do
    not see each other), in which case they are simply placed side by side
    inside the phase. Members separated by layers the phase has no step in are
    aligned and banded separately. Every member must be drawn in the same
    pipeline column, and every step of a pipeline belongs to exactly one phase.
    """

    id: str
    label: str
    steps: List[str]
    note: str = ""
    """Why these steps belong together—shown as the band's tooltip."""


GROUPS: List[Group] = [
    # ---------------------------------------------------------------- person
    Group(
        "sources",
        "Sources",
        ["p_wiki_fetch", "p_wiki_select", "p_db"],
        note=(
            "Everything the pipeline learns about the person before any writing "
            "happens: fetch, then narrow, plus the second biographical source."
        ),
    ),
    Group(
        "events",
        "Events",
        ["p_events_p1", "p_events_p2", "p_geocode"],
        note=(
            "The narrative spine: propose the events and the chapters they fall "
            "into, research each event, and put its places on the map."
        ),
    ),
    Group(
        "images",
        "Images",
        [
            "p_img_search",
            "p_img_fetch",
            "p_img_filter",
            "p_img_match",
            "p_img_verify",
        ],
        note=(
            "One job: plan the searches, run them, rank what comes back, match "
            "the survivors to events, and check the portrait the match picked."
        ),
    ),
    Group(
        "presentation",
        "Presentation",
        ["p_style", "p_chapter_concepts", "p_portrait", "p_chapter_art"],
        note=(
            "How the story looks: the color and type system, and the pictures "
            "drawn in it—the portrait and one abstract image per chapter."
        ),
    ),
    Group(
        "network",
        "Network and review",
        ["p_network", "p_review"],
        note=(
            "The second derived dataset, then the critic pass that reads both: "
            "the relationships the article implies, and a review of events and "
            "network together."
        ),
    ),
    Group(
        "depth",
        "Depth",
        ["p_backgrounds", "p_illustrations"],
        note=(
            "The layer beneath the slides: a background report for roughly one "
            "event per chapter, and the pictures a critic keeps for it."
        ),
    ),
    Group(
        "localization",
        "Localization",
        ["p_name_evidence", "p_glossary", "p_translate"],
        note=(
            "Read what the target language calls things, decide each name once, "
            "then apply that decision to every document."
        ),
    ),
    # ------------------------------------------------------------------ meta
    Group(
        "planning",
        "Planning",
        ["m_p1", "m_p2"],
        note=(
            "Decide whom the theme is about, then gather every event of those "
            "people."
        ),
    ),
    Group(
        "event_curation",
        "Events",
        ["m_p3", "m_p4"],
        note=(
            "Judge the events against the theme, refit the chapters to the "
            "survivors, then give each chapter its period."
        ),
    ),
    Group(
        "social_network",
        "Network",
        ["m_p5", "m_p5b", "m_clusters", "m_p6"],
        note=(
            "The network branch end to end: merge the ego networks, review the "
            "graph, detect the circles, write their cards."
        ),
    ),
    Group(
        "map_branch",
        "Map",
        ["m_p7b", "m_p7a", "m_p7c"],
        note=(
            "The map branch end to end: rate the located events, cluster them "
            "into stops, narrate the stops that survive."
        ),
    ),
    Group(
        "composition",
        "Composition",
        ["m_p8", "m_style"],
        note=(
            "Where the branches become one story: rewrite every text in one "
            "voice, then give the story its visual identity."
        ),
    ),
    Group(
        "meta_localization",
        "Localization",
        ["m_images", "m_translate"],
        note=(
            "Settle how the story's recurring images read in the target "
            "language, then translate every passage against that decision."
        ),
    ),
]


ARTIFACTS: List[Artifact] = [
    Artifact(
        "wiki_cache",
        "Wikipedia material",
        "data/people/{id}/_cache/wikipedia_page.json, related_articles.json, commons_images.json",
        "cache",
        "Main article, up to 15 related articles, and Commons image metadata.",
        concept="sources",
    ),
    Artifact(
        "db_cache",
        "Deutsche Biographie material",
        "data/people/{id}/_cache/deutsche_biographie.json",
        "cache",
        "ADB text (CC-BY-NC-SA) and CC0 metadata only; NDB text is excluded by license.",
        concept="sources",
    ),
    Artifact(
        "life_events",
        "Life events",
        "data/people/{id}/life_events.json",
        "dataset",
        "The English reference document: person metadata, chapters, events, images, sources.",
        concept="events",
    ),
    Artifact(
        "ego_network",
        "Ego network",
        "data/people/{id}/ego_network.json",
        "dataset",
        "The person's relationships, typed and weighted.",
        concept="network",
    ),
    Artifact(
        "person_styles",
        "Interface style",
        "data/person_styles.json",
        "registry",
        "Per-person colors and fonts for the story UI.",
        concept="identity",
    ),
    Artifact(
        "persons",
        "Person registry",
        "data/persons.json",
        "registry",
        "Landing-page index of every person.",
        concept="profile",
    ),
    Artifact(
        "portrait",
        "Portrait",
        "public/portraits/{id}.webp",
        "asset",
        "Style-transferred from a licensed reference image.",
        concept="imagery",
    ),
    Artifact(
        "chapter_art",
        "Chapter illustrations",
        "public/chapter_art/{id}/{chapter}.webp",
        "asset",
        "One abstract, style-transferred image per chapter of a life.",
        concept="imagery",
    ),
    Artifact(
        "person_de",
        "Localized person data",
        "data/people/{id}/de/*.json, data/persons_de.json",
        "dataset",
        "Derived from English; carries a fingerprint of its source text.",
        concept="languages",
    ),
    Artifact(
        "meta_story",
        "Meta story",
        "data/meta_stories/{id}.json, data/meta_stories.json",
        "dataset",
        "Chapters, social network, geo map and composed prose for one theme, "
        "and the landing-page index entry written with it.",
        concept="theme",
    ),
    Artifact(
        "meta_story_styles",
        "Meta story style",
        "data/meta_story_styles.json",
        "registry",
        "Per-story colors, fonts and the SVG marks that punctuate its prose.",
        concept="identity",
    ),
    Artifact(
        "meta_de",
        "Localized meta story",
        "data/meta_stories/de/{id}.json, data/meta_stories_de.json",
        "dataset",
        "Event titles are copied verbatim from translated person data.",
        concept="languages",
    ),
]


STEPS: List[Step] = [
    # ---------------------------------------------------------------- person
    Step(
        "p_wiki_fetch",
        "Fetch Wikipedia",
        SHARED,
        EXTERNAL,
        "cache_wikipedia_materials.py",
        "main",
        byline="Wikipedia and Commons APIs",
        summary=(
            "Pulls the main article, its candidate related articles and Commons "
            "image metadata, and caches them so later steps and reruns are free."
        ),
        outputs=["wiki_cache"],
    ),
    Step(
        "p_wiki_select",
        "Select articles",
        SHARED,
        AI,
        "cache_wikipedia_materials.py",
        "select_articles_with_ai",
        summary=(
            "Ranks the linked articles by how much they would help tell this "
            "life, keeping the context budget on the ones that matter."
        ),
        depends_on=[Dep("p_wiki_fetch", "article + outgoing link candidates")],
        prompts=["select_articles_with_ai"],
        inputs=["wiki_cache"],
        outputs=["wiki_cache"],
    ),
    Step(
        "p_db",
        "Fetch Deutsche Biographie",
        SHARED,
        EXTERNAL,
        "utils/deutsche_biographie.py",
        "format_for_prompt",
        byline="Deutsche Biographie API",
        summary=(
            "Adds a second biographical source for German and European figures, "
            "with a per-record license check that drops NDB text."
        ),
        depends_on=[
            Dep("p_wiki_fetch", "article title + birth/death years for disambiguation")
        ],
        prompts=["format_for_prompt"],
        inputs=["wiki_cache"],
        outputs=["db_cache"],
        skip_flag="--skip-db",
    ),
    Step(
        "p_events_p1",
        "Propose events",
        PERSON,
        AI,
        "events/pipeline.py",
        "propose_events",
        summary=(
            "Reads the whole article set and proposes 12–16 significant events "
            "with titles, dates and descriptions—the narrative spine, with no "
            "locations, images or sources yet. It also weighs them against each "
            "other and groups them into 3–6 chapters, naming the chapter on "
            "each event, and writes the conclusion. Only this call can do that: "
            "it is the one place in the pipeline that sees a life whole, and "
            "how much of a life an event turns on, or where one period of it "
            "ends, is a comparison, not a property of the event. The chapters "
            "are dated afterwards from the events they hold, so a chapter can "
            "never begin after one of its own events."
        ),
        depends_on=[
            Dep("p_wiki_select", "the selected related articles"),
            Dep("p_db", "ADB biography text"),
        ],
        prompts=[
            "build_proposal_prompt",
            "propose_events",
            "description_contract_prompt",
        ],
        inputs=["wiki_cache", "db_cache"],
        model_from="generate_person_events.py",
    ),
    Step(
        "p_events_p2",
        "Research events",
        PERSON,
        AI,
        "events/pipeline.py",
        "research_event_details",
        summary=(
            "One call per event, given the subject's own article at 30000 "
            "characters as the primary source and the articles relevant to "
            "that event at 6000 characters each: historic and modern place "
            "names, the people involved, sources, a semantic icon, the terms "
            "the description leans on—together with the Commons searches that "
            "would illustrate the event, written while its material is still "
            "in front of the call. Individual failures do not abort the run."
        ),
        depends_on=[Dep("p_events_p1", "one event skeleton per call")],
        prompts=[
            # The section helpers come first: the joined prompt block is cut at
            # MAX_PROMPT_CHARS, and the base builder alone overruns it, so
            # anything listed after the base builder is never seen.
            "_subject_article_prompt_section",
            "_related_articles_prompt_section",
            "description_contract_prompt",
            "build_research_prompt_base",
            "build_research_prompt_classified",
            "research_event_details",
            "format_icon_categories_for_prompt",
        ],
        calls_per_run="12–16 (one per event)",
        inputs=["wiki_cache", "db_cache"],
    ),
    Step(
        "p_img_search",
        "Plan image searches",
        PERSON,
        AI,
        "events/images/assign.py",
        "generate_image_search_strings",
        summary=(
            "Writes twenty Commons search strings for the life as a whole: "
            "five for the person, from which the portrait is chosen, and "
            "fifteen naming the things the events name. It is forbidden to "
            "search for a commemoration, because 'Franz Kafka Prague' answers "
            "with a birthplace plaque, a bronze head, and two statues before "
            "it answers with anything Kafka saw."
        ),
        depends_on=[Dep("p_events_p1", "event skeletons")],
        prompts=["generate_image_search_strings"],
    ),
    Step(
        "p_img_fetch",
        "Search image sources",
        SHARED,
        EXTERNAL,
        "events/images/assign.py",
        "execute_batch_image_search",
        byline="Commons and Openverse APIs",
        summary=(
            "Runs every planned query against Wikimedia Commons and Openverse "
            "and deduplicates the hits by URL, keeping the Commons record when "
            "both services return the same picture. The searches the research "
            "wrote for each event run too, and first, so that the tag saying "
            "which event a picture was found for survives the deduplication—two "
            "per event, Commons only, because a query naming a machine or a "
            "document is a query Commons indexes well."
        ),
        depends_on=[
            Dep("p_img_search", "the planned search strings"),
            Dep("p_events_p2", "the searches each event asked for"),
        ],
    ),
    Step(
        "p_img_filter",
        "Rank candidates",
        SHARED,
        CODE,
        "events/images/scoring.py",
        "filter_images_by_quality",
        byline="Quality and commemoration score",
        summary=(
            "Scores every hit on resolution, file efficiency, how informative "
            "its filename is, and whether it shows a commemoration, then drops "
            "the ones under a permissive threshold and ranks the rest—so the "
            "matching call sees candidates rather than noise. The "
            "commemoration penalty is what keeps a well-lit modern photograph "
            "of a plaque or a grave from outranking a scanned period "
            "photograph, which it beats on every other measure; it reads the "
            "filename and the caption as well as the categories, because "
            "Openverse reports no categories at all. The scores are computed "
            "once for the whole pool, and the pool serves every event at once."
        ),
        depends_on=[Dep("p_img_fetch", "every hit the queries returned")],
    ),
    Step(
        "p_img_match",
        "Match images",
        PERSON,
        AI,
        "events/images/assign.py",
        "match_images_to_events",
        summary=(
            "Matches the retrieved Commons images to events and writes captions, "
            "preserving the attribution each image requires. The same call picks "
            "the person's reference portrait. It is told which event a candidate "
            "was searched for and the year each photograph was taken, and it is "
            "given no quota: an event with no picture is a correct answer, and "
            "the earlier instruction to fill 40–60% of the slides is what put a "
            "gravestone under fifteen deaths. The year is what a filename "
            "cannot say: a 2016 photograph of the Manchester County Court "
            "Offices reached Turing's 1952 conviction as the court where it "
            "happened, and a building found by its kind and its city is now "
            "among the stand-ins the shared rejection list names."
        ),
        depends_on=[Dep("p_img_filter", "the ranked image candidates")],
        prompts=[
            "build_image_match_prompt",
            "STAND_IN_REJECTION_INSTRUCTIONS",
            "match_images_to_events",
        ],
    ),
    Step(
        "p_img_verify",
        "Verify portrait",
        PERSON,
        AI,
        "events/images/assign.py",
        "verify_portrait_depicts_person",
        summary=(
            "Shows the chosen portrait file itself to the model and asks "
            "whether it depicts the subject — the matcher judges by filenames "
            "and captions alone, and a photograph of the subject's spouse "
            "carries the subject's name in its caption. A no drops the pick; "
            "a failed call keeps it, so the check can only catch a wrong "
            "portrait, never lose a right one. It is the last call of the run "
            "that produces the life events: the document is then written, with "
            "the chapters and the conclusion the proposal wrote, the researched "
            "events with their images and coordinates, and the verified "
            "portrait, and the person is folded into the landing-page index "
            "with the portrait reference the matching picked. Every later step "
            "reads the written document rather than the payload that produced "
            "it, which is what makes a run resumable and a single concern "
            "regenerable."
        ),
        depends_on=[Dep("p_img_match", "the portrait pick")],
        prompts=["verify_portrait_depicts_person"],
        calls_per_run="0-1",
        outputs=["life_events", "persons"],
    ),
    Step(
        "p_geocode",
        "Geocode places",
        SHARED,
        EXTERNAL,
        "utils/geocode.py",
        "geocode_location",
        byline="Nominatim geocoder",
        summary=(
            "Resolves each place through Nominatim, preferring the modern name "
            "the research supplied—which is why historic places with renamed "
            "successors still land on the map. The coordinates go into the "
            "written document; no later step of this pipeline reads them, but "
            "the application's map and the meta pipeline's map branch do."
        ),
        depends_on=[Dep("p_events_p2", "historic and modern place names")],
        outputs=["life_events"],
    ),
    Step(
        "p_style",
        "Design interface style",
        PERSON,
        AI,
        "generate_person_style.py",
        "call_openai",
        summary=(
            "Derives a color and type system for the story from the person's "
            "era and field, and rejects a palette whose text colors fall under "
            "a computed contrast floor, asking the model once more with the "
            "reason."
        ),
        depends_on=[Dep("p_img_verify", "the finished life events")],
        prompts=["build_prompt", "build_retry_prompt", "call_openai"],
        inputs=["life_events"],
        outputs=["person_styles"],
        skip_flag="--dataset-only / --network-only",
    ),
    Step(
        "p_network",
        "Build ego network",
        PERSON,
        AI,
        "generate_person_network.py",
        "call_openai",
        summary=(
            "Builds the person's relationship graph with typed, weighted and "
            "described ties—the input the meta story pipeline later merges."
        ),
        depends_on=[Dep("p_img_verify", "the finished life events")],
        prompts=["build_prompt", "call_openai"],
        inputs=["wiki_cache", "life_events"],
        outputs=["ego_network"],
        skip_flag="--dataset-only / --style-only",
    ),
    Step(
        "p_portrait",
        "Draw portrait",
        PERSON,
        IMAGE,
        "generate_person_portrait.py",
        "generate_portrait",
        summary=(
            "Style-transfers a licensed reference portrait toward a shared master "
            "style so every person in the collection looks like one illustration "
            "set. The reference is the licensed image the matching picked, read "
            "from the person's entry in the landing-page index, and the entry "
            "is updated with the finished portrait."
        ),
        depends_on=[Dep("p_style", "primary and secondary color")],
        prompts=["STYLE_TRANSFER_PROMPT", "generate_portrait"],
        inputs=["persons", "person_styles"],
        outputs=["portrait", "persons", "life_events"],
        skip_flag="--skip-portrait",
        model_note="Image model; only allowlisted models keep facial likeness.",
    ),
    Step(
        "p_chapter_concepts",
        "Draft chapter concepts",
        PERSON,
        AI,
        "generate_chapter_illustrations.py",
        "write_chapter_concepts",
        summary=(
            "Turns each chapter of the life into an abstract visual concept — a "
            "metaphor with concrete forms in it, never a person or a place. All "
            "chapters are read in one call so the metaphors differ from one "
            "another."
        ),
        depends_on=[Dep("p_img_verify", "the finished life events")],
        prompts=["CONCEPT_SYSTEM_PROMPT", "build_concept_prompt"],
        inputs=["life_events"],
        skip_flag="--skip-chapter-art",
    ),
    Step(
        "p_chapter_art",
        "Draw chapter art",
        PERSON,
        IMAGE,
        "generate_chapter_illustrations.py",
        "request_illustration",
        summary=(
            "Draws each concept in the same master style the portraits are "
            "transferred toward, so a chapter slide is lit like the rest of the "
            "story. The content comes from the prompt rather than a second "
            "reference image — there is nothing to be faithful to."
        ),
        depends_on=[
            Dep("p_chapter_concepts", "one visual concept per chapter"),
            Dep("p_style", "primary and secondary color"),
        ],
        prompts=["IMAGE_PROMPT", "request_illustration"],
        inputs=["life_events", "person_styles"],
        outputs=["chapter_art", "life_events"],
        calls_per_run="one per chapter",
        skip_flag="--skip-chapter-art",
        model_note="Image model, prompted without a content reference image.",
    ),
    Step(
        "p_review",
        "Review data",
        SHARED,
        AI,
        "review_person.py",
        "review_combined",
        summary=(
            "A critic pass over the generated data. Only high-confidence changes "
            "are applied automatically."
        ),
        depends_on=[Dep("p_network", "the ego network")],
        prompts=[
            "get_combined_review_prompt",
            "review_combined",
            "description_contract_prompt",
        ],
        inputs=["life_events", "ego_network", "wiki_cache"],
        outputs=["life_events", "ego_network"],
        skip_flag="--skip-review",
    ),
    Step(
        "p_name_evidence",
        "Collect name evidence",
        SHARED,
        EXTERNAL,
        "translate_person.py",
        "build_translation_reference",
        byline="Wikipedia language links",
        summary=(
            "Reads the person's article in the language being translated into, "
            "plus one language link per person and place in the data, and hands "
            "both to the two calls that follow. Without it a translator has only "
            "its own memory for what a name is called elsewhere, and memory "
            "invents: a Copenhagen cemetery came back as the 'Assistenzfriedhof'."
        ),
        depends_on=[Dep("p_review", "every name the reviewed documents carry")],
        inputs=["life_events", "ego_network"],
        outputs=["wiki_cache"],
    ),
    Step(
        "p_glossary",
        "Build name glossary",
        SHARED,
        AI,
        "translate_person.py",
        "build_name_glossary",
        summary=(
            "Decides once per person how every name is rendered in the target "
            "language, then applies it everywhere—the UI cross-references match "
            "on exact names, so drift between documents would break them."
        ),
        depends_on=[
            Dep("p_name_evidence", "what the target language writes for each name"),
        ],
        prompts=[
            "build_name_glossary",
            "format_glossary_for_prompt",
            "format_reference_for_prompt",
        ],
        inputs=["life_events", "ego_network", "persons"],
    ),
    Step(
        "p_translate",
        "Translate data",
        SHARED,
        AI,
        "translate_person.py",
        "_call_translation_model",
        summary=(
            "Extract–translate–merge: only translatable fields are sent, and the "
            "result is overlaid on a copy of the English document, so dates, "
            "coordinates, URLs and IDs cannot drift. It is shown the same "
            "target-language naming evidence the glossary saw, which is what "
            "keeps a place name from being invented in prose."
        ),
        depends_on=[
            Dep("p_glossary", "the name mapping to apply"),
            Dep("p_illustrations", "the reports and their illustration captions"),
        ],
        prompts=["_call_translation_model", "format_reference_for_prompt"],
        inputs=["life_events", "ego_network", "persons"],
        outputs=["person_de"],
        skip_flag="--skip-translate",
    ),
    Step(
        "p_backgrounds",
        "Write background reports",
        PERSON,
        AI,
        "generate_event_backgrounds.py",
        "write_report",
        summary=(
            "Computes the story's own deep-event selection — roughly one event "
            "per chapter, ported from the interface and kept in sync with it — "
            "and writes a 350-550 word background report exactly for the "
            "events the story will offer one on; a report for any other event "
            "could never be reached. It runs after review, so the report is "
            "grounded in the reviewed text; its material is the subject's own "
            "article at 30000 characters, the event's related articles, and "
            "what the slide already tells the reader — the popups, the chips, "
            "the rest of the story as an outline — so it writes around them "
            "rather than into them. It re-decides the event's citations in "
            "the same call, accepting only URLs it was shown, and syncs them "
            "to the translated copies since a URL is not prose."
        ),
        depends_on=[
            Dep(
                "p_review",
                "the reviewed events and network, as the dataset holds them",
            ),
        ],
        prompts=[
            "build_report_prompt",
            "_subject_article_prompt_section",
            "REPORT_INSTRUCTIONS",
        ],
        inputs=["life_events", "ego_network", "wiki_cache", "db_cache"],
        outputs=["life_events", "person_de"],
        calls_per_run="one per deep event — roughly one per chapter",
        skip_flag="--skip-backgrounds",
        model_from="generate_event_backgrounds.py",
    ),
    Step(
        "p_illustrations",
        "Illustrate reports",
        PERSON,
        AI,
        "generate_event_backgrounds.py",
        "fetch_background_images",
        summary=(
            "The report says what it would like a picture of; Commons is asked "
            "for each, and this call reads what came back against the report "
            "and keeps at most three. The reading is the step: a keyword "
            "search for 'On Computable Numbers manuscript' returned a "
            "16th-century Mexican codex, one for Christopher Morcom returned a "
            "steam engine built by Belliss & Morcom, and one for the Banbury "
            "sheets returned an ordnance map of Banbury. It runs on the larger "
            "model because it is a critic; it is shown each candidate's "
            "filename as well as its caption, because a Commons caption is "
            "often the uploader's paperwork; and one picture per query is "
            "enforced in code, since two photographs of the same machine are "
            "one illustration printed twice. Three is a ceiling, not a target, "
            "and keeping none is a normal outcome. It runs in the same pass as "
            "the report, once the event's own picture is already in the "
            "dataset and can be excluded: an illustration the reader scrolled "
            "past a screen ago illustrates nothing."
        ),
        depends_on=[
            Dep("p_backgrounds", "the report and the searches it asked for"),
        ],
        prompts=["STAND_IN_REJECTION_INSTRUCTIONS", "fetch_background_images"],
        inputs=["life_events"],
        outputs=["life_events"],
        calls_per_run="1 per report illustrated",
        model_from="generate_event_backgrounds.py",
    ),
    # ------------------------------------------------------------------ meta
    Step(
        "m_p1",
        "Plan story",
        META,
        AI,
        "generate_meta_story.py",
        "phase1_story_planning",
        summary=(
            "Picks which people the theme is actually about, proposes subtopics "
            "and chapters, and names people missing from the dataset that would "
            "strengthen the story."
        ),
        prompts=["phase1_story_planning"],
        inputs=["persons"],
    ),
    Step(
        "m_p2",
        "Collect events",
        META,
        CODE,
        "generate_meta_story.py",
        "phase2_event_collection",
        byline="Read from the life events",
        summary="Gathers every dated event of the selected people, unfiltered.",
        depends_on=[Dep("m_p1", "the selected person ids")],
        inputs=["life_events"],
    ),
    Step(
        "m_p3",
        "Curate events",
        META,
        AI,
        "generate_meta_story.py",
        "_filter_event_batch",
        summary=(
            "Judges each event against the theme in batches and records why it "
            "belongs, so a chapter is a claim rather than a date filter. The "
            "planned chapter boundaries are then re-fitted in code "
            "(`fit_chapters_to_events`) to the events that actually survived."
        ),
        depends_on=[Dep("m_p2", "the unfiltered event pool")],
        prompts=["_filter_event_batch"],
        calls_per_run="one per batch",
        skip_flag="--skip-ai-filtering",
    ),
    Step(
        "m_p4",
        "Add historical context",
        META,
        AI,
        "generate_meta_story.py",
        "phase4_historical_context",
        summary=(
            "Adds the world events a chapter sits inside, so the biography reads "
            "against its period."
        ),
        depends_on=[Dep("m_p3", "the fitted chapters with their surviving events")],
        prompts=["phase4_historical_context"],
        skip_flag="--skip-historical-context",
    ),
    Step(
        "m_p5",
        "Merge networks",
        META,
        CODE,
        "meta_story_network.py",
        "build_social_network",
        byline="Joined by normalized name",
        summary=(
            "Merges the individual ego networks by normalized name into one graph "
            "of main people plus the acquaintances that bridge them. Purely "
            "deterministic—no model sees this step."
        ),
        depends_on=[Dep("m_p1", "the selected person ids")],
        inputs=["ego_network"],
    ),
    Step(
        "m_p5b",
        "Review network",
        META,
        AI,
        "meta_story_network_review.py",
        "review_social_network",
        summary=(
            "Adds direct ties the ego networks missed and prunes vague or indirect "
            "ones, with guidance that adapts to how dense the graph already is. "
            "Runs before clustering so the circles reflect the reviewed graph."
        ),
        depends_on=[Dep("m_p5", "the deterministically merged graph")],
        prompts=["build_review_prompt", "review_social_network"],
        skip_flag="--skip-network-review",
        model_note="Called by generate_meta_story.py with its --model value.",
        model_from="generate_meta_story.py",
    ),
    Step(
        "m_clusters",
        "Detect circles",
        META,
        CODE,
        "meta_story_network.py",
        "derive_clusters",
        byline="Greedy modularity clustering",
        summary=(
            "Community detection over the reviewed graph produces the story's "
            "circles. Called from the narration step, which stores each "
            "circle's members with its text; the client reads the stored "
            "circles and never repeats the detection."
        ),
        depends_on=[Dep("m_p5b", "the reviewed graph")],
    ),
    Step(
        "m_p6",
        "Narrate circles",
        META,
        AI,
        "generate_meta_story.py",
        "phase6_network_narration",
        summary=(
            "Writes the card text for each circle. The composition rewrites "
            "these later; keeping this step means the story still reads when "
            "composition is skipped."
        ),
        depends_on=[Dep("m_clusters", "one circle per card")],
        prompts=["phase6_network_narration"],
    ),
    Step(
        "m_p7b",
        "Rate map events",
        META,
        AI,
        "meta_story_map_narration.py",
        "rate_map_events",
        summary=(
            "Scores how much each located event carries the theme. Runs first in "
            "the map branch because the scores are the weights the clustering uses."
        ),
        depends_on=[Dep("m_p4", "the chapters, whose events carry the coordinates")],
        prompts=["rate_map_events"],
        inputs=["life_events"],
        skip_flag="--skip-map",
    ),
    Step(
        "m_p7a",
        "Cluster places",
        META,
        CODE,
        "meta_story_map.py",
        "cluster_located_events",
        byline="Weighted geographic clustering",
        summary=(
            "Groups the story's located events geographically into candidate map "
            "stops, weighted by the ratings, and keeps only the clusters that qualify."
        ),
        depends_on=[Dep("m_p7b", "per-event weights")],
        skip_flag="--skip-map",
    ),
    Step(
        "m_p7c",
        "Narrate map stops",
        META,
        AI,
        "meta_story_map_narration.py",
        "narrate_map_clusters",
        summary=(
            "Narrates the top clusters as map stops and can discard accidental "
            "groupings, which cascades into pruning the map."
        ),
        depends_on=[Dep("m_p7a", "the qualifying geographic clusters")],
        prompts=["narrate_map_clusters"],
        skip_flag="--skip-map",
    ),
    Step(
        "m_p8",
        "Compose story",
        META,
        AI,
        "compose_meta_story.py",
        "run_composition",
        summary=(
            "Reads the assembled story top-down, the way a reader meets it, and "
            "rewrites every text in one voice: the prose between components, the "
            "captions on them, the circle organization and the map stops. It may "
            "also drop people that do not earn their place. The composed story "
            "is then written, and the landing-page registry updated with it; "
            "the style and the translation read the written document."
        ),
        depends_on=[
            Dep("m_p6", "the circle narration to rewrite"),
            Dep("m_p7c", "the map stops to curate"),
        ],
        prompts=["run_composition"],
        inputs=["wiki_cache", "persons"],
        outputs=["meta_story"],
        skip_flag="--skip-compose",
        model_note="Uses OPENAI_COMPOSER_MODEL, not OPENAI_MODEL.",
    ),
    Step(
        "m_style",
        "Design story style",
        META,
        AI,
        "generate_meta_story_style.py",
        "call_openai",
        summary=(
            "Derives the article's color, type and ornament system from the "
            "theme itself—including the separator glyph and the ornamental "
            "rule its prose is punctuated with."
        ),
        depends_on=[Dep("m_p8", "the composed story's framing and opening")],
        prompts=["build_prompt", "call_openai"],
        inputs=["meta_story"],
        outputs=["meta_story_styles"],
        skip_flag="--skip-style",
    ),
    Step(
        "m_images",
        "Settle recurring images",
        SHARED,
        AI,
        "meta_story_translation.py",
        "build_image_glossary",
        summary=(
            "Decides once, before any prose is written, how the metaphors the "
            "story argues in read in the target language — and whether the "
            "language has them at all. Left to the translation call the "
            "decision is never made: it meets the image in the title, renders "
            "it word for word, and then carries that rendering faithfully "
            "through every passage, so an architecture story about 'the box' "
            "arrived in German as 'Kasten', a crate. Same reason as the name "
            "glossary — what has to read the same in every passage is settled "
            "once rather than re-derived per field."
        ),
        depends_on=[Dep("m_p8", "the composed story's text, as the images to judge")],
        prompts=["build_image_glossary", "format_image_glossary_for_prompt"],
        inputs=["meta_story"],
        skip_flag="--skip-translate",
    ),
    Step(
        "m_translate",
        "Translate meta story",
        SHARED,
        AI,
        "translate_meta_story.py",
        "translate_meta_story_data",
        summary=(
            "Same extract–translate–merge contract as person data. Event titles "
            "are copied verbatim from the translated person data so chapters and "
            "story slides never disagree, and the names in its prose are taken "
            "from the same place: what each person's own translation settled on."
        ),
        depends_on=[Dep("m_images", "the settled wording for each recurring image")],
        inputs=["meta_story", "person_de"],
        outputs=["meta_de"],
        skip_flag="--skip-translate",
        prompts=["_call_translation_model", "format_reference_for_prompt"],
        model_from="translate_meta_story.py",
        model_note="Delegates the API call to translate_person.py's extract–translate–merge helper.",
    ),
]


def group_of(step_id: str) -> Optional[Group]:
    """The phase a step belongs to."""
    for group in GROUPS:
        if step_id in group.steps:
            return group
    return None


def artifact_by_id(artifact_id: str) -> Optional[Artifact]:
    for artifact in ARTIFACTS:
        if artifact.id == artifact_id:
            return artifact
    return None


def step_by_id(step_id: str) -> Optional[Step]:
    for step in STEPS:
        if step.id == step_id:
            return step
    return None


def column_of(step: Step) -> str:
    """Which pipeline column a step is drawn in.

    Lane records *ownership*—several shared subsystems (sourcing, review,
    translation) are their own scripts—but the reader wants to see them at the
    point in the flow where they run, so the drawn column comes from the step id.
    """
    return PERSON if step.id.startswith("p_") else META
