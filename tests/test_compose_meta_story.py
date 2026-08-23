"""The composer's section-order and event-matching guardrails.

The order of the timeline, network and map sections is written by a model, and
everything downstream — the page, the stored bodies, the headings — follows it.
A list that names a section twice, names one the story has no data for, or
forgets one must never cost the reader a component, so the normalization is
checked here rather than trusted to the prompt. The composed event texts are
applied by matching identifiers the same defensive way, and that matching is
checked here too.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from compose_meta_story import (  # noqa: E402
    ComposedEvent,
    CompositionResult,
    ComposedSectionHeadings,
    StoryBlock,
    apply_composition,
    available_sections,
    resolve_section_order,
)


def make_dataset(**overrides):
    """A minimal story document carrying all three component sections."""
    dataset = {
        "meta_story": {"id": "story", "title": "Draft", "tagline": "Draft"},
        "chapters": [{"id": "c1", "date_start": "1900", "date_end": "1910"}],
        "social_network": {
            "nodes": [{"id": "a", "type": "main"}, {"id": "b", "type": "main"}],
            "links": [{"source": "a", "target": "b", "kind": "main"}],
        },
        "geo_map": {"clusters": [{"key": "bamberg", "label": "Bamberg"}]},
    }
    dataset.update(overrides)
    return dataset


def make_composition(section_order):
    return CompositionResult(
        throughline="Why these lives belong together.",
        section_order=section_order,
        title="A Title",
        tagline="A tagline",
        opening=[],
        description=[],
        section_headings=ComposedSectionHeadings(
            timeline="Then", network="Together", map="There", conclusion="After"
        ),
        timeline_body=[],
        network_body=[],
        map_body=[],
        conclusion=[],
        chapters=[],
        events=[],
        circles=[],
        map_stops=[],
        discarded_map_stops=[],
    )


def test_story_without_composed_order_keeps_the_historical_sequence():
    assert resolve_section_order(make_dataset()) == ["timeline", "network", "map"]


def test_only_sections_the_story_renders_are_available():
    dataset = make_dataset(geo_map={"clusters": []})
    assert available_sections(dataset) == ["timeline", "network"]


def test_composed_order_decides_which_component_opens_the_page():
    dataset = make_dataset()
    apply_composition(dataset, make_composition(["map", "network", "timeline"]))
    assert dataset["section_order"] == ["map", "network", "timeline"]


def test_duplicates_and_forgotten_sections_are_repaired():
    dataset = make_dataset()
    apply_composition(dataset, make_composition(["network", "network"]))
    assert dataset["section_order"] == ["network", "timeline", "map"]


def test_a_section_the_story_lacks_is_dropped_from_the_order():
    dataset = make_dataset(geo_map={"clusters": []})
    apply_composition(dataset, make_composition(["map", "network", "timeline"]))
    assert dataset["section_order"] == ["network", "timeline"]


def test_composed_event_texts_land_on_matching_timeline_events_only():
    dataset = make_dataset(
        chapters=[
            {
                "id": "c1",
                "date_start": "1900",
                "date_end": "1910",
                "person_events": [
                    {"person_id": "a", "event_index": 3, "theme_connection": "Old."},
                    {"person_id": "b", "event_index": 1, "theme_connection": "Kept."},
                ],
            }
        ]
    )
    composed = make_composition(["timeline", "network", "map"])
    composed.events = [
        ComposedEvent(person_id="a", event_index=3, text="Enriched."),
        ComposedEvent(person_id="a", event_index=99, text="Matches nothing."),
    ]
    apply_composition(dataset, composed)
    events = dataset["chapters"][0]["person_events"]
    assert events[0]["theme_connection"] == "Enriched."
    assert events[1]["theme_connection"] == "Kept."


def test_bodies_and_headings_are_stored_for_rendered_sections_only():
    dataset = make_dataset(geo_map={"clusters": []})
    composed = make_composition(["network", "timeline"])
    composed.network_body = [StoryBlock(type="paragraph", text="The circle first.")]
    composed.map_body = [StoryBlock(type="paragraph", text="Nowhere to put this.")]
    apply_composition(dataset, composed)
    assert list(dataset["section_bodies"]) == ["network"]
    assert list(dataset["section_headings"]) == ["network", "timeline", "conclusion"]
