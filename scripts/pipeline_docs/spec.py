#!/usr/bin/env python3
"""The hand-maintained shape of the generation pipeline.

This is the only file in `pipeline_docs` that a human edits when the pipeline
changes, and it deliberately holds just the things a parser cannot infer:
which processing steps exist, which data actually flows between them, and which
files they read and write. Everything factual about a step — its model,
reasoning effort, output schema, prompt text, CLI flags — is pulled from the
source by `introspect.py` and must not be duplicated here.

The pipeline is a DAG, not a sequence. `Step.depends_on` names the steps whose
*output this step consumes*, with a label for the data that travels along the
edge; the drawing derives the layers from that graph, so two steps only share a
layer when neither can see the other's result. Orchestrator functions are
deliberately absent: `generate_person.main` and `generate_meta_story.main` only
call the steps in an order, and drawing them as nodes made the chart look like
a chain when it is a fork.

`Step.inputs` and `Step.outputs` are the files on disk. A file written by a step
in the same pipeline is already implied by an edge; a file that arrives from the
*other* pipeline is drawn as a source node, which is how the meta chart shows
that it consumes what the person chart produces.

Each step names a `script` and a `function`. `validate.py` checks that both
still exist, that the dependency graph is acyclic, and that no AI call site in
the codebase is left unclaimed, so a step added to the pipeline without a spec
entry fails the docs build instead of quietly going undocumented.
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
            "life events, ego network, interface style, portrait, review, "
            "translation."
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
            "Sourcing, geocoding, review and localization — used by both "
            "pipelines and run as their own scripts too."
        ),
    },
}

# Step kinds drive both colour and the "AI only" filter in the chart.
AI = "ai"
CODE = "deterministic"
EXTERNAL = "external"
IMAGE = "image"


@dataclass
class Artifact:
    """A file the pipeline reads or writes."""

    id: str
    label: str
    path: str
    kind: str  # cache | dataset | registry | asset
    note: str = ""


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
    phase_label: Optional[str] = None
    model_from: Optional[str] = None
    """Script whose `--model` default supplies this step's model.

    Needed for steps that are library modules with no CLI of their own, or that
    delegate the actual API call to a helper: the call site knows only the
    `model` its caller handed it, so the value has to come from the entry point.
    """


ARTIFACTS: List[Artifact] = [
    Artifact(
        "wiki_cache",
        "Wikipedia cache",
        "data/people/{id}/_cache/wikipedia_page.json, related_articles.json, commons_images.json",
        "cache",
        "Main article, up to 15 related articles, and Commons image metadata.",
    ),
    Artifact(
        "db_cache",
        "Deutsche Biographie cache",
        "data/people/{id}/_cache/deutsche_biographie.json",
        "cache",
        "ADB text (CC-BY-NC-SA) and CC0 metadata only; NDB text is excluded by license.",
    ),
    Artifact(
        "life_events",
        "Life events",
        "data/people/{id}/life_events.json",
        "dataset",
        "The English reference document: person metadata, chapters, events, images, sources.",
    ),
    Artifact(
        "ego_network",
        "Ego network",
        "data/people/{id}/ego_network.json",
        "dataset",
        "The person's relationships, typed and weighted.",
    ),
    Artifact(
        "person_styles",
        "Interface styles",
        "data/person_styles.json",
        "registry",
        "Per-person colours and fonts for the story UI.",
    ),
    Artifact(
        "persons",
        "Persons registry",
        "data/persons.json",
        "registry",
        "Landing-page index of every person.",
    ),
    Artifact(
        "portrait",
        "Portrait",
        "public/portraits/{id}.webp",
        "asset",
        "Style-transferred from a licensed reference image.",
    ),
    Artifact(
        "person_de",
        "Localized person data",
        "data/people/{id}/de/*.json, data/persons_de.json",
        "dataset",
        "Derived from English; carries a fingerprint of its source text.",
    ),
    Artifact(
        "meta_story",
        "Meta story",
        "data/meta_stories/{id}.json",
        "dataset",
        "Chapters, social network, geo map and composed prose for one theme.",
    ),
    Artifact(
        "meta_registry",
        "Meta story registry",
        "data/meta_stories.json",
        "registry",
        "Index of meta stories for the landing page.",
    ),
    Artifact(
        "meta_de",
        "Localized meta story",
        "data/meta_stories/de/{id}.json, data/meta_stories_de.json",
        "dataset",
        "Event titles are copied verbatim from translated person data.",
    ),
]


STEPS: List[Step] = [
    # ---------------------------------------------------------------- person
    Step(
        "p_wiki_fetch",
        "Fetch Wikipedia material",
        SHARED,
        EXTERNAL,
        "cache_wikipedia_materials.py",
        "main",
        summary=(
            "Pulls the main article, its candidate related articles and Commons "
            "image metadata, and caches them so later phases and reruns are free."
        ),
        outputs=["wiki_cache"],
    ),
    Step(
        "p_wiki_select",
        "Select related articles",
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
        "Phase 1 — event skeletons",
        PERSON,
        AI,
        "generate_person_events.py",
        "call_openai_phase1",
        phase_label="Phase 1",
        summary=(
            "Reads the whole article set and proposes 12–16 significant events "
            "with titles, dates and descriptions — the narrative spine, with no "
            "locations, images or sources yet."
        ),
        depends_on=[
            Dep("p_wiki_select", "the selected related articles"),
            Dep("p_db", "ADB biography text"),
        ],
        prompts=["build_phase1_prompt", "call_openai_phase1"],
        inputs=["wiki_cache", "db_cache"],
    ),
    Step(
        "p_events_p2",
        "Phase 2 — research each event",
        PERSON,
        AI,
        "generate_person_events.py",
        "research_event_details",
        phase_label="Phase 2",
        summary=(
            "One call per event, given only the articles relevant to that event: "
            "historic and modern place names, the people involved, sources, and a "
            "semantic icon. Individual failures do not abort the run."
        ),
        depends_on=[
            Dep("p_events_p1", "one event skeleton per call"),
            Dep("p_wiki_select", "the per-event subset of related articles"),
            Dep("p_db", "ADB biography text"),
        ],
        prompts=[
            "build_phase2_prompt_base",
            "build_phase2_prompt_classified",
            "research_event_details",
            "format_icon_categories_for_prompt",
        ],
        calls_per_run="12–16 (one per event)",
        inputs=["wiki_cache", "db_cache"],
    ),
    Step(
        "p_chapters",
        "Group events into chapters",
        PERSON,
        AI,
        "generate_person_events.py",
        "call_openai_chapter_generation",
        summary=(
            "Turns the researched events into 3–5 chapters with headlines that "
            "read as a story arc rather than a date range."
        ),
        depends_on=[
            Dep("p_events_p1", "person metadata + skeletons"),
            Dep("p_events_p2", "the merged, researched events"),
        ],
        prompts=["build_chapter_generation_prompt", "call_openai_chapter_generation"],
    ),
    Step(
        "p_img_search",
        "Plan image searches",
        PERSON,
        AI,
        "generate_person_events.py",
        "generate_image_search_strings",
        summary="Writes the Commons search strings most likely to surface usable imagery.",
        depends_on=[Dep("p_events_p1", "event skeletons")],
        prompts=["generate_image_search_strings"],
    ),
    Step(
        "p_img_fetch",
        "Search image sources",
        SHARED,
        EXTERNAL,
        "generate_person_events.py",
        "execute_batch_image_search",
        summary=(
            "Runs every planned query against Wikimedia Commons and Openverse, "
            "deduplicates the hits and drops the ones that fail a permissive "
            "quality score, so the matching call sees candidates rather than noise."
        ),
        depends_on=[Dep("p_img_search", "the planned search strings")],
    ),
    Step(
        "p_img_match",
        "Assign images to events",
        PERSON,
        AI,
        "generate_person_events.py",
        "match_images_to_events",
        summary=(
            "Matches the retrieved Commons images to events and writes captions, "
            "preserving the attribution each file requires. The same call picks "
            "the person's reference portrait."
        ),
        depends_on=[
            Dep("p_img_fetch", "the filtered image candidates"),
            Dep("p_events_p1", "event skeletons to match against"),
        ],
        prompts=["match_images_to_events"],
    ),
    Step(
        "p_geocode",
        "Geocode locations",
        SHARED,
        EXTERNAL,
        "generate_person_events.py",
        "geocode_location",
        summary=(
            "Resolves each place through Nominatim, preferring the modern name "
            "Phase 2 supplied — which is why historic places with renamed "
            "successors still land on the map."
        ),
        depends_on=[Dep("p_events_p2", "historic and modern place names")],
    ),
    Step(
        "p_write",
        "Write the dataset",
        PERSON,
        CODE,
        "generate_person_events.py",
        "write_dataset",
        summary=(
            "Serializes the document the three branches above assembled. This is "
            "where the run stops being memory: everything downstream reads "
            "life_events.json rather than the payload that produced it."
        ),
        depends_on=[
            Dep("p_chapters", "chapters + conclusion"),
            Dep("p_img_match", "per-event images + portrait pick"),
            Dep("p_geocode", "coordinates"),
        ],
        outputs=["life_events"],
    ),
    Step(
        "p_register",
        "Update the persons registry",
        PERSON,
        CODE,
        "generate_person_events.py",
        "update_register",
        summary=(
            "Folds the person into the landing-page index, carrying over the "
            "portrait reference the image matching picked — which is where the "
            "portrait step later reads it from."
        ),
        depends_on=[Dep("p_write", "the written dataset")],
        inputs=["life_events"],
        outputs=["persons"],
    ),
    Step(
        "p_style",
        "Generate interface style",
        PERSON,
        AI,
        "generate_person_style.py",
        "call_openai",
        summary=(
            "Derives a colour and type system for the story from the person's "
            "era and field."
        ),
        depends_on=[Dep("p_write", "person summary + first five events")],
        prompts=["build_prompt", "call_openai"],
        inputs=["life_events"],
        outputs=["person_styles"],
        skip_flag="--dataset-only / --network-only",
    ),
    Step(
        "p_network",
        "Generate ego network",
        PERSON,
        AI,
        "generate_person_network.py",
        "call_openai",
        summary=(
            "Builds the person's relationship graph with typed, weighted and "
            "described ties — the input the meta story pipeline later merges."
        ),
        depends_on=[
            Dep("p_write", "the finished life events as context"),
            Dep("p_wiki_select", "related articles"),
        ],
        prompts=["build_prompt", "call_openai"],
        inputs=["wiki_cache", "life_events"],
        outputs=["ego_network"],
        skip_flag="--dataset-only / --style-only",
    ),
    Step(
        "p_portrait",
        "Generate portrait",
        PERSON,
        IMAGE,
        "generate_person_portrait.py",
        "generate_portrait",
        summary=(
            "Style-transfers a licensed reference portrait toward a shared master "
            "style so every person in the collection looks like one illustration set."
        ),
        depends_on=[
            Dep("p_register", "the licensed reference image URL"),
            Dep("p_style", "primary and secondary colour"),
        ],
        prompts=["STYLE_TRANSFER_PROMPT", "generate_portrait"],
        inputs=["persons", "person_styles"],
        outputs=["portrait", "persons", "life_events"],
        skip_flag="--skip-portrait",
        model_note="Image model; only allowlisted models keep facial likeness.",
    ),
    Step(
        "p_review",
        "Review events and network",
        SHARED,
        AI,
        "review_person.py",
        "review_combined",
        summary=(
            "A critic pass over the generated data. Only high-confidence changes "
            "are applied automatically."
        ),
        depends_on=[
            Dep("p_write", "the written life events"),
            Dep("p_network", "the ego network"),
        ],
        prompts=["get_combined_review_prompt", "review_combined"],
        inputs=["life_events", "ego_network", "wiki_cache"],
        outputs=["life_events", "ego_network"],
        skip_flag="--skip-review",
    ),
    Step(
        "p_review_style",
        "Review interface style",
        SHARED,
        AI,
        "review_person.py",
        "review_style",
        summary="Checks colour harmony and font pairing against the story's mood.",
        depends_on=[
            Dep("p_style", "the generated style config"),
            Dep("p_write", "events, as the mood to check against"),
        ],
        prompts=["get_style_review_prompt", "review_style"],
        inputs=["person_styles", "life_events"],
        outputs=["person_styles"],
        skip_flag="--skip-review",
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
            "language, then applies it everywhere — the UI cross-references match "
            "on exact names, so drift between documents would break them."
        ),
        depends_on=[
            Dep("p_review", "every person name in the reviewed documents"),
            Dep("p_register", "the registry summary, as context for the call"),
        ],
        prompts=["build_name_glossary", "format_glossary_for_prompt"],
        inputs=["life_events", "ego_network", "persons"],
    ),
    Step(
        "p_translate",
        "Translate person data",
        SHARED,
        AI,
        "translate_person.py",
        "_call_translation_model",
        summary=(
            "Extract–translate–merge: only translatable fields are sent, and the "
            "result is overlaid on a copy of the English document, so dates, "
            "coordinates, URLs and IDs cannot drift."
        ),
        depends_on=[
            Dep("p_glossary", "the name mapping to apply"),
            Dep("p_review", "the reviewed English documents"),
        ],
        prompts=["_call_translation_model"],
        inputs=["life_events", "ego_network"],
        outputs=["person_de"],
        skip_flag="--skip-translate",
    ),
    # ------------------------------------------------------------------ meta
    Step(
        "m_p1",
        "Phase 1 — story planning",
        META,
        AI,
        "generate_meta_story.py",
        "phase1_story_planning",
        phase_label="Phase 1",
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
        "Phase 2 — collect events",
        META,
        CODE,
        "generate_meta_story.py",
        "phase2_event_collection",
        phase_label="Phase 2",
        summary="Gathers every dated event of the selected people, unfiltered.",
        depends_on=[Dep("m_p1", "the selected person ids")],
        inputs=["life_events"],
    ),
    Step(
        "m_p3",
        "Phase 3 — curate events",
        META,
        AI,
        "generate_meta_story.py",
        "_filter_event_batch",
        phase_label="Phase 3",
        summary=(
            "Judges each event against the theme in batches and records why it "
            "belongs, so a chapter is a claim rather than a date filter."
        ),
        depends_on=[
            Dep("m_p2", "the unfiltered event pool"),
            Dep("m_p1", "the theme and subtopics to judge against"),
        ],
        prompts=["_filter_event_batch"],
        calls_per_run="one per batch",
        skip_flag="--skip-ai-filtering",
    ),
    Step(
        "m_p3b",
        "Fit chapters to survivors",
        META,
        CODE,
        "generate_meta_story.py",
        "fit_chapters_to_events",
        summary=(
            "Re-fits the planned chapter boundaries to the events that actually "
            "survived curation."
        ),
        depends_on=[
            Dep("m_p1", "the proposed chapter ranges"),
            Dep("m_p3", "the surviving events"),
        ],
    ),
    Step(
        "m_p4",
        "Phase 4 — historical context",
        META,
        AI,
        "generate_meta_story.py",
        "phase4_historical_context",
        phase_label="Phase 4",
        summary=(
            "Adds the world events a chapter sits inside, so the biography reads "
            "against its period."
        ),
        depends_on=[Dep("m_p3b", "one chapter per call")],
        prompts=["phase4_historical_context"],
        calls_per_run="one per chapter",
        skip_flag="--skip-historical-context",
    ),
    Step(
        "m_p5",
        "Phase 5 — derive social network",
        META,
        CODE,
        "meta_story_network.py",
        "build_social_network",
        phase_label="Phase 5",
        summary=(
            "Merges the individual ego networks by normalized name into one graph "
            "of main people plus the acquaintances that bridge them. Purely "
            "deterministic — no model sees this step."
        ),
        depends_on=[Dep("m_p1", "the selected person ids")],
        inputs=["ego_network"],
    ),
    Step(
        "m_p5b",
        "Phase 5b — review network",
        META,
        AI,
        "meta_story_network_review.py",
        "review_social_network",
        phase_label="Phase 5b",
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
        summary=(
            "Community detection over the reviewed graph produces the story's "
            "circles. Called from the narration phase and mirrored by the client, "
            "so the circles are never stored — they are always re-derived."
        ),
        depends_on=[Dep("m_p5b", "the reviewed graph")],
    ),
    Step(
        "m_p6",
        "Phase 6 — narrate circles",
        META,
        AI,
        "generate_meta_story.py",
        "phase6_network_narration",
        phase_label="Phase 6",
        summary=(
            "Writes the card text for each circle. Phase 8 rewrites these later; "
            "keeping Phase 6 means the story still reads when composition is skipped."
        ),
        depends_on=[Dep("m_clusters", "one circle per card")],
        prompts=["phase6_network_narration"],
    ),
    Step(
        "m_p7b",
        "Phase 7 — rate map events",
        META,
        AI,
        "meta_story_map_narration.py",
        "rate_map_events",
        phase_label="Phase 7",
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
        "Phase 7 — cluster places",
        META,
        CODE,
        "meta_story_map.py",
        "cluster_located_events",
        phase_label="Phase 7",
        summary=(
            "Groups the story's located events geographically into candidate map "
            "stops, weighted by the ratings, and keeps only the clusters that qualify."
        ),
        depends_on=[Dep("m_p7b", "per-event weights")],
        skip_flag="--skip-map",
    ),
    Step(
        "m_p7c",
        "Phase 7 — narrate map stops",
        META,
        AI,
        "meta_story_map_narration.py",
        "narrate_map_clusters",
        phase_label="Phase 7",
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
        "Phase 8 — compose the story",
        META,
        AI,
        "compose_meta_story.py",
        "run_composition",
        phase_label="Phase 8",
        summary=(
            "Reads the assembled story top-down, the way a reader meets it, and "
            "rewrites every text in one voice: the prose between components, the "
            "captions on them, the circle organization and the map stops. It may "
            "also drop people that do not earn their place."
        ),
        depends_on=[
            Dep("m_p4", "chapters with their historical context"),
            Dep("m_p6", "the circle narration to rewrite"),
            Dep("m_p7c", "the map stops to curate"),
        ],
        prompts=["run_composition"],
        inputs=["wiki_cache", "persons"],
        skip_flag="--skip-compose",
        model_note="Uses OPENAI_COMPOSER_MODEL, not OPENAI_MODEL.",
    ),
    Step(
        "m_save",
        "Save story and registry",
        META,
        CODE,
        "generate_meta_story.py",
        "save_meta_story",
        summary="Writes the story document and updates the landing-page registry.",
        depends_on=[Dep("m_p8", "the composed story document")],
        outputs=["meta_story", "meta_registry"],
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
            "are copied verbatim from the translated person files so chapters and "
            "story slides never disagree."
        ),
        depends_on=[Dep("m_save", "the saved English story")],
        inputs=["meta_story", "person_de"],
        outputs=["meta_de"],
        skip_flag="--skip-translate",
        prompts=["_call_translation_model"],
        model_from="translate_meta_story.py",
        model_note="Delegates the API call to translate_person.py's extract–translate–merge helper.",
    ),
]


def steps_by_lane(lane: str) -> List[Step]:
    return [step for step in STEPS if step.lane == lane]


def step_by_id(step_id: str) -> Optional[Step]:
    for step in STEPS:
        if step.id == step_id:
            return step
    return None


def artifact_by_id(artifact_id: str) -> Optional[Artifact]:
    for artifact in ARTIFACTS:
        if artifact.id == artifact_id:
            return artifact
    return None
