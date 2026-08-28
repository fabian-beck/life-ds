#!/usr/bin/env python3
"""Cut a person's story into the units that stage one extracts claims from.

Every claim a reader could take away from a story has to be reachable, so the
decomposition covers the whole dataset rather than the prose alone: the registry
entry, the chapter frame, the conclusion, each event with its structured fields,
annotations, image captions, and the ego network. A unit is simply the slice of
data one extraction call sees, and it is deterministic — the same dataset always
yields the same units in the same order, which is what lets a fact's identity be
derived from its unit and its wording.

Structured fields are units too, not decoration. "Cambridge" in an event's
``locations`` is a claim about where something happened whether or not the
sentence above it repeats the name, and a wrong ``involved_people`` entry puts a
person in a room they were never in.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .paths import PEOPLE_DIR, PERSONS_REGISTER
from .text import collapse, digest

SCOPES = ("person", "chapters", "conclusion", "event", "background", "network")


@dataclass
class Unit:
    """One slice of a person's dataset, ready to be sent for extraction."""

    id: str
    scope: str
    label: str
    payload: Dict[str, Any]
    context: Dict[str, Any] = field(default_factory=dict)

    def as_prompt_text(self) -> str:
        """The unit as the model sees it: its own JSON, nothing added."""
        return json.dumps(self.payload, indent=2, ensure_ascii=False)


@dataclass
class PersonStory:
    """Everything stage one reads for one person."""

    person_id: str
    person_name: str
    registry: Dict[str, Any]
    life_events: Dict[str, Any]
    ego_network: Optional[Dict[str, Any]]

    @property
    def fingerprint(self) -> str:
        """Identifies the dataset a fact was extracted from.

        Two result files can only be merged fact by fact if they describe the
        same story; a regenerated dataset changes this and the merge says so
        instead of quietly averaging judgments of different text.
        """
        return digest(
            json.dumps(self.registry, sort_keys=True, ensure_ascii=False),
            json.dumps(self.life_events, sort_keys=True, ensure_ascii=False),
            json.dumps(self.ego_network or {}, sort_keys=True, ensure_ascii=False),
        )


def display_name(registry_entry: Dict[str, Any], person_id: str) -> str:
    """The person's name as prose spells it.

    ``persons.json`` stores the name with underscores for some people
    ("Alan_Turing") and with spaces for others, so it is normalized here rather
    than at every display site.
    """
    raw = str(registry_entry.get("name") or person_id)
    return raw.replace("_", " ").strip()


def load_person_story(person_id: str) -> PersonStory:
    """Read one person's registry entry, events, and network."""
    events_path = PEOPLE_DIR / person_id / "life_events.json"
    if not events_path.exists():
        raise FileNotFoundError(f"No life_events.json for '{person_id}'")

    with open(events_path, "r", encoding="utf-8") as handle:
        life_events = json.load(handle)

    registry: Dict[str, Any] = {}
    with open(PERSONS_REGISTER, "r", encoding="utf-8") as handle:
        for entry in json.load(handle).get("people", []):
            if entry.get("id") == person_id:
                registry = entry
                break

    network: Optional[Dict[str, Any]] = None
    network_path = PEOPLE_DIR / person_id / "ego_network.json"
    if network_path.exists():
        with open(network_path, "r", encoding="utf-8") as handle:
            network = json.load(handle)

    return PersonStory(
        person_id=person_id,
        person_name=display_name(registry, person_id),
        registry=registry,
        life_events=life_events,
        ego_network=network,
    )


def person_ids_with_stories() -> List[str]:
    """Every person that has a generated dataset, in stable order."""
    return sorted(
        path.name
        for path in PEOPLE_DIR.iterdir()
        if (path / "life_events.json").exists()
    )


def build_units(story: PersonStory) -> List[Unit]:
    """The full list of extraction units for one person."""
    units: List[Unit] = []

    registry_payload = {
        key: value
        for key, value in story.registry.items()
        if key
        in {"name", "tagline", "summary", "birthDate", "deathDate", "primaryRoles"}
    }
    portrait = story.registry.get("portrait") or {}
    for key in ("caption", "originalCaption", "creator", "source"):
        if portrait.get(key):
            registry_payload.setdefault("portrait", {})[key] = portrait[key]
    if registry_payload:
        units.append(
            Unit(
                id="person",
                scope="person",
                label="Registry entry",
                payload=registry_payload,
                context={"section": "Person registry"},
            )
        )

    chapters = [
        _chapter_payload(chapter) for chapter in story.life_events.get("chapters") or []
    ]
    if chapters:
        units.append(
            Unit(
                id="chapters",
                scope="chapters",
                label="Chapters",
                payload={"chapters": chapters},
                context={"section": "Chapter frame"},
            )
        )

    conclusion = story.life_events.get("conclusion")
    if conclusion:
        units.append(
            Unit(
                id="conclusion",
                scope="conclusion",
                label="Conclusion",
                payload={"conclusion": conclusion},
                context={"section": "Conclusion"},
            )
        )

    for index, event in enumerate(story.life_events.get("events") or []):
        title = str(event.get("title") or f"Event {index + 1}")
        date = str(event.get("date") or "")
        label = f"{date} — {title}".strip(" —")
        context = {
            "section": "Event",
            "event_index": index,
            "event_title": title,
            "event_date": date,
            "chapter": event.get("chapter"),
            "sources": list(event.get("sources") or []),
        }
        units.append(
            Unit(
                id=f"event:{index:02d}",
                scope="event",
                label=label,
                payload=_event_payload(event),
                context=context,
            )
        )
        background = _background_payload(event)
        if background:
            units.append(
                Unit(
                    id=f"event:{index:02d}:background",
                    scope="background",
                    label=f"{label} — depth layer",
                    payload=background,
                    context=dict(context, section="Depth layer"),
                )
            )

    if story.ego_network:
        connections = story.ego_network.get("connections") or []
        if connections:
            units.append(
                Unit(
                    id="network",
                    scope="network",
                    label=f"Ego network ({len(connections)} connections)",
                    payload={
                        "ego": story.ego_network.get("ego"),
                        "connections": connections,
                    },
                    context={"section": "Ego network"},
                )
            )

    return units


def _event_payload(event: Dict[str, Any]) -> Dict[str, Any]:
    """An event with the fields that assert something, and nothing else.

    Rendering hints — the icon name, the narrative weight, the image URLs and
    their licenses — are decisions about presentation and carry no claim about
    the person's life. Image *captions* do, so they stay.

    The long-form ``background`` prose is left out here and extracted as its
    own unit: it is several times the length of everything else in the event,
    it is written by a different phase, and keeping it apart lets a round say
    how the depth layer compares with the slide it sits behind.

    The ``sources`` list is left out for a different reason. It is provenance
    rather than assertion: extracting "this URL is listed as a source" yields a
    claim about the file, and checking it against the article the URL points at
    establishes nothing. Whether a listed source exists and resolves is already
    checked by ``scripts/validate_source_links.py``. The list still travels in
    the unit's context, so an evaluator sees what the event cites.
    """
    payload: Dict[str, Any] = {}
    for key in (
        "date",
        "date_precision",
        "date_end",
        "date_end_precision",
        "date_note",
        "age",
        "title",
        "description",
        "chapter",
        "locations",
        "involved_people",
        "event_class",
        "annotations",
    ):
        value = event.get(key)
        if value not in (None, [], {}, ""):
            payload[key] = value

    captions = [
        {"caption": image.get("caption"), "creator": image.get("creator")}
        for image in event.get("images") or []
        if image.get("caption")
    ]
    if captions:
        payload["image_captions"] = captions
    return payload


def unit_summary(units: List[Unit]) -> str:
    """A one-line description of a decomposition, for the console."""
    counts: Dict[str, int] = {}
    for unit in units:
        counts[unit.scope] = counts.get(unit.scope, 0) + 1
    parts = [f"{counts[scope]} {scope}" for scope in SCOPES if scope in counts]
    return collapse(", ".join(parts), 120)


def find_unit(units: List[Unit], unit_id: str) -> Optional[Unit]:
    """The unit with this id, or None."""
    for unit in units:
        if unit.id == unit_id:
            return unit
    return None


def story_path(person_id: str) -> Path:
    """Where a person's events live, for reporting provenance."""
    return PEOPLE_DIR / person_id / "life_events.json"


def _chapter_payload(chapter: Dict[str, Any]) -> Dict[str, Any]:
    """A chapter without its generated artwork.

    The ``illustration`` block holds the prompt an image was generated from.
    "The illustration shows luminous planes in darkness" is true of the picture
    by construction and says nothing about the person, so checking it against a
    biography would spend an evaluator's attention on a tautology.
    """
    return {
        key: value
        for key, value in chapter.items()
        if key != "illustration" and value not in (None, [], {}, "")
    }


def _background_payload(event: Dict[str, Any]) -> Dict[str, Any]:
    """The depth-layer prose behind one event, with its image captions."""
    background = event.get("background")
    if not background:
        return {}
    payload: Dict[str, Any] = {"background": background}
    captions = [
        {"caption": image.get("caption"), "creator": image.get("creator")}
        for image in event.get("background_images") or []
        if image.get("caption")
    ]
    if captions:
        payload["background_image_captions"] = captions
    return payload
