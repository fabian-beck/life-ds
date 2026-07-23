#!/usr/bin/env python3
"""Translate person data (life events, ego networks, and registry entries) to a target language.

Translation architecture
------------------------

English is always the reference version. Translated files are *derived* from the
English data: the translation never regenerates or restructures anything.

1. EXTRACT: only the translatable text fields are pulled out of the English
   document into a compact payload (``extract_*_translatables``).
2. TRANSLATE: the payload (not the whole document) is sent to the model with
   structured outputs, so dates, coordinates, URLs, IDs, icons, and every other
   technical field can never be altered by the model.
3. MERGE: the translated payload is overlaid onto a deep copy of the English
   document (``apply_*_translations``). List lengths are validated, so the
   translated file is guaranteed to have the same events, chapters, images,
   and connections — in the same order — as the English source.

Every translated file carries a ``translation`` provenance block containing a
fingerprint of the English source text it was derived from. When the English
data changes, the fingerprint no longer matches and the translation is
reported as stale (see ``translate_all_persons.py --check``).

Person names are localized through a single shared name glossary per person,
so the same person is named identically across life events, ego network, and
registry (cross-references in the UI rely on exact name matches).
"""

import argparse
import copy
import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

from openai import OpenAI, APIStatusError
from pydantic import BaseModel

from config import DEFAULT_MODEL

# Constants
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
REGISTER_PATH = DATA_DIR / "persons.json"
PEOPLE_DIR = DATA_DIR / "people"

# Language name mapping for better prompts
LANGUAGE_NAMES = {
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
    "pl": "Polish",
    "ru": "Russian",
    "ja": "Japanese",
    "zh": "Chinese",
    "ko": "Korean",
}

# Extra style guidance per target language
LANGUAGE_STYLE_NOTES = {
    "de": (
        "Write fluent, idiomatic German that a native author would write, not a "
        "German echo of the English. Reshape sentences to fit German rhythm and "
        "word order — use the flexible German verb/clause placement, form natural "
        "compounds instead of stringing words together as in English, and reach "
        "for genuinely German phrasing rather than anglicisms or loan-translated "
        "idioms. Vary sentence length so the prose does not feel mechanical. "
        "Use the informal 'Du' form if the reader is ever addressed. Apply correct "
        "German typography (e.g. „quotes“ where quoting), but keep Markdown and "
        "[[term|display]] markers intact."
    ),
}


# ---------------------------------------------------------------------------
# Pydantic models for the translation payloads (structured outputs).
# These mirror the extraction payloads exactly. They intentionally contain
# ONLY translatable text — never technical fields.
# ---------------------------------------------------------------------------


class TrLocation(BaseModel):
    name_historic: Optional[str] = None
    name_modern: Optional[str] = None


class TrImage(BaseModel):
    caption: Optional[str] = None


class TrAnnotation(BaseModel):
    term: str
    explanation: str


class TrEvent(BaseModel):
    title: str
    description: str
    date_note: Optional[str] = None
    locations: List[TrLocation]
    images: List[TrImage]
    annotations: List[TrAnnotation]


class TrChapter(BaseModel):
    headline: str
    location: Optional[str] = None


class TrPersonMeta(BaseModel):
    tagline: Optional[str] = None
    summary: str
    primary_roles: List[str]


class LifeEventsTranslation(BaseModel):
    person: TrPersonMeta
    chapters: List[TrChapter]
    conclusion: Optional[str] = None
    events: List[TrEvent]


class TrConnection(BaseModel):
    relationship_description: str
    notes: Optional[str] = None
    shared_activities: List[str]


class TrCategorySummary(BaseModel):
    summary: str


class EgoNetworkTranslation(BaseModel):
    ego_summary: str
    ego_primary_roles: List[str]
    connections: List[TrConnection]
    category_summaries: List[TrCategorySummary]
    network_summary: Optional[str] = None


class RegistryEntryTranslation(BaseModel):
    tagline: Optional[str] = None
    summary: str
    primary_roles: List[str]


class NameMapping(BaseModel):
    original: str
    localized: str


class NameGlossary(BaseModel):
    mappings: List[NameMapping]


class TrPersonEvent(BaseModel):
    event_title: str
    theme_connection: str


class TrContextEvent(BaseModel):
    title: str
    description: str


class TrMetaChapter(BaseModel):
    title: str
    # Optional: only present for chapters that carry a composed lead-in (see
    # compose_meta_story.py), so older stories aren't asked to invent one.
    lead_in: Optional[str] = None
    historical_context: List[TrContextEvent]
    person_events: List[TrPersonEvent]


class TrSubtopic(BaseModel):
    title: str
    description: str


class TrNetworkCircle(BaseModel):
    # Optional: circles whose narration predates the headline field carry no
    # title in the payload, so the model isn't asked to invent one.
    title: Optional[str] = None
    text: str


class TrNetworkNarration(BaseModel):
    intro: str
    circles: List[TrNetworkCircle]


class TrMapStop(BaseModel):
    # Optional: stops kept without narration carry no title in the payload.
    title: Optional[str] = None
    text: str


class TrMapNarration(BaseModel):
    intro: str
    stops: List[TrMapStop]


class TrOpening(BaseModel):
    text: str
    # Only present when the opening carries an image with a caption.
    image_caption: Optional[str] = None


class TrSectionHeadings(BaseModel):
    timeline: Optional[str] = None
    network: Optional[str] = None
    conclusion: Optional[str] = None


class TrSectionImages(BaseModel):
    # Captions of the per-section images; each only present when the source
    # image exists and has a caption.
    timeline_caption: Optional[str] = None
    network_caption: Optional[str] = None
    conclusion_caption: Optional[str] = None


class MetaStoryTranslation(BaseModel):
    title: str
    tagline: str
    description: str
    subtopics: List[TrSubtopic]
    chapters: List[TrMetaChapter]
    # Optional: only present for composed stories (see compose_meta_story.py).
    opening: Optional[TrOpening] = None
    section_headings: Optional[TrSectionHeadings] = None
    section_images: Optional[TrSectionImages] = None
    timeline_intro: Optional[str] = None
    conclusion: Optional[str] = None
    network_narration: Optional[TrNetworkNarration] = None
    map_narration: Optional[TrMapNarration] = None


# ---------------------------------------------------------------------------
# Extraction: English document -> translatable payload (plain dicts)
# ---------------------------------------------------------------------------


def extract_life_events_translatables(data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract only the translatable text fields from a life events dataset."""
    person = data.get("person", {}) or {}
    payload: Dict[str, Any] = {
        "person": {
            "tagline": person.get("tagline"),
            "summary": person.get("summary", ""),
            "primary_roles": list(person.get("primary_roles", []) or []),
        },
        "chapters": [
            {
                "headline": chapter.get("headline", ""),
                "location": chapter.get("location"),
            }
            for chapter in (data.get("chapters") or [])
        ],
        "conclusion": data.get("conclusion"),
        "events": [],
    }
    for event in data.get("events", []):
        payload["events"].append(
            {
                "title": event.get("title", ""),
                "description": event.get("description", ""),
                "date_note": event.get("date_note"),
                "locations": [
                    {
                        "name_historic": loc.get("name_historic"),
                        "name_modern": loc.get("name_modern"),
                    }
                    for loc in (event.get("locations") or [])
                    if isinstance(loc, dict)
                ],
                "images": [
                    {"caption": img.get("caption")}
                    for img in (event.get("images") or [])
                ],
                "annotations": [
                    {"term": term, "explanation": ann.get("explanation", "")}
                    for term, ann in (event.get("annotations") or {}).items()
                ],
            }
        )
    return payload


def extract_ego_network_translatables(data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract only the translatable text fields from an ego network dataset."""
    ego = data.get("ego", {}) or {}
    return {
        "ego_summary": ego.get("summary", ""),
        "ego_primary_roles": list(ego.get("primary_roles", []) or []),
        "connections": [
            {
                "relationship_description": conn.get("relationship_description", ""),
                "notes": conn.get("notes"),
                "shared_activities": list(conn.get("shared_activities") or []),
            }
            for conn in data.get("connections", [])
        ],
        "category_summaries": [
            {"summary": cat.get("summary", "")}
            for cat in (data.get("category_summaries") or [])
        ],
        "network_summary": data.get("network_summary"),
    }


def extract_registry_entry_translatables(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Extract only the translatable text fields from a registry entry."""
    return {
        "tagline": entry.get("tagline"),
        "summary": entry.get("summary", ""),
        "primary_roles": list(entry.get("primaryRoles", []) or []),
    }


def extract_meta_story_translatables(data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract only the translatable text fields from a meta story dataset."""
    meta = data.get("meta_story", {}) or {}
    payload: Dict[str, Any] = {
        "title": meta.get("title", ""),
        "tagline": meta.get("tagline", ""),
        "description": meta.get("description", ""),
        "subtopics": [
            {
                "title": sub.get("title", ""),
                "description": sub.get("description", ""),
            }
            for sub in (data.get("subtopics") or [])
        ],
        "chapters": [
            {
                "title": chapter.get("title", ""),
                # Composed lead-in only when present, so stories composed
                # before/without Phase 7 keep their old fingerprint.
                **({"lead_in": chapter["lead_in"]} if chapter.get("lead_in") else {}),
                "historical_context": [
                    {
                        "title": ctx.get("title", ""),
                        "description": ctx.get("description", ""),
                    }
                    for ctx in (chapter.get("historical_context") or [])
                ],
                "person_events": [
                    {
                        "event_title": pe.get("event_title", ""),
                        "theme_connection": pe.get("theme_connection", ""),
                    }
                    for pe in (chapter.get("person_events") or [])
                ],
            }
            for chapter in (data.get("chapters") or [])
        ],
        "conclusion": data.get("conclusion"),
    }
    # Composed timeline intro (Phase 7) only when present — same fingerprint
    # stability rationale as the chapter lead-ins above.
    if data.get("timeline_intro"):
        payload["timeline_intro"] = data["timeline_intro"]
    # Composed opening, section headings, and section image captions (Phase 7),
    # likewise only when present.
    opening = data.get("opening")
    if isinstance(opening, dict) and opening.get("text"):
        opening_payload: Dict[str, Any] = {"text": opening["text"]}
        opening_caption = (opening.get("image") or {}).get("caption")
        if opening_caption:
            opening_payload["image_caption"] = opening_caption
        payload["opening"] = opening_payload
    headings = data.get("section_headings")
    if isinstance(headings, dict) and headings:
        payload["section_headings"] = {
            slot: headings[slot]
            for slot in ("timeline", "network", "conclusion")
            if headings.get(slot)
        }
    section_images = data.get("section_images")
    if isinstance(section_images, dict) and section_images:
        image_captions = {
            f"{slot}_caption": (section_images.get(slot) or {}).get("caption")
            for slot in ("timeline", "network", "conclusion")
            if (section_images.get(slot) or {}).get("caption")
        }
        if image_captions:
            payload["section_images"] = image_captions
    # The social network itself is technical (copied verbatim), but its
    # narration texts are prose and must be translated. The key is only added
    # when narration exists, so fingerprints of stories without narration are
    # unchanged.
    narration = (data.get("social_network") or {}).get("narration")
    if isinstance(narration, dict):
        # `title` is included only when the source circle has one, so meta
        # stories whose narration predates the headline field keep their old
        # fingerprint (and stay "current") instead of all going stale at once.
        circles_payload = []
        for circle in narration.get("circles") or []:
            entry = {"text": circle.get("text", "")}
            if circle.get("title"):
                entry["title"] = circle["title"]
            circles_payload.append(entry)
        payload["network_narration"] = {
            "intro": narration.get("intro", ""),
            "circles": circles_payload,
        }
    # The map section's cluster data is technical (names, dates, coordinates —
    # copied verbatim), but its narration texts are prose. Only added when
    # narration exists, so stories without a map keep their old fingerprint.
    map_narration = (data.get("geo_map") or {}).get("narration")
    if isinstance(map_narration, dict):
        stops_payload = []
        for stop in map_narration.get("stops") or []:
            entry = {"text": stop.get("text", "")}
            if stop.get("title"):
                entry["title"] = stop["title"]
            stops_payload.append(entry)
        payload["map_narration"] = {
            "intro": map_narration.get("intro", ""),
            "stops": stops_payload,
        }
    return payload


# ---------------------------------------------------------------------------
# Fingerprints and provenance
# ---------------------------------------------------------------------------


def compute_fingerprint(payload: Dict[str, Any]) -> str:
    """Stable fingerprint of the translatable source text.

    Computed over the extraction payload of the ENGLISH source, so any change
    to translatable English text invalidates existing translations, while
    changes to purely technical fields (coordinates, icons) do not.
    """
    canonical = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def make_translation_block(
    fingerprint: Optional[str], target_lang: str, translator: str
) -> Dict[str, Any]:
    return {
        "source_lang": "en",
        "target_lang": target_lang,
        "source_fingerprint": fingerprint,
        "translated_on": datetime.now().astimezone().isoformat(),
        "translator": translator,
    }


def translation_status(
    source_data: Optional[Dict[str, Any]],
    target_data: Optional[Dict[str, Any]],
    extract_fn: Any,
) -> str:
    """Return 'missing', 'stale', or 'current' for a translated document."""
    if source_data is None:
        return "no-source"
    if target_data is None:
        return "missing"
    block = target_data.get("translation")
    if not isinstance(block, dict):
        return "stale"
    fingerprint = block.get("source_fingerprint")
    if not fingerprint:
        return "stale"
    if fingerprint != compute_fingerprint(extract_fn(source_data)):
        return "stale"
    return "current"


# ---------------------------------------------------------------------------
# Merge: translated payload + English document -> translated document
# ---------------------------------------------------------------------------


class TranslationMergeError(ValueError):
    """Raised when a translated payload does not align with the source."""


def _require_same_length(kind: str, source: List[Any], translated: List[Any]) -> None:
    if len(source) != len(translated):
        raise TranslationMergeError(
            f"{kind}: expected {len(source)} translated item(s), got {len(translated)}"
        )


def _set_if_source_has(target: Dict[str, Any], key: str, value: Optional[str]) -> None:
    """Overwrite target[key] only if the source document had that field."""
    if key in target and value is not None:
        target[key] = value


def apply_life_events_translations(
    source_data: Dict[str, Any],
    translated: Dict[str, Any],
    name_glossary: Dict[str, str],
) -> Dict[str, Any]:
    """Overlay a translated payload onto a deep copy of the English dataset."""
    result = copy.deepcopy(source_data)

    person = result.get("person", {})
    tr_person = translated.get("person", {})
    _set_if_source_has(person, "tagline", tr_person.get("tagline"))
    _set_if_source_has(person, "summary", tr_person.get("summary"))
    src_roles = person.get("primary_roles") or []
    tr_roles = tr_person.get("primary_roles") or []
    _require_same_length("person.primary_roles", src_roles, tr_roles)
    if "primary_roles" in person:
        person["primary_roles"] = tr_roles
    if person.get("name"):
        person["name"] = localize_name(person["name"], name_glossary)

    src_chapters = result.get("chapters") or []
    tr_chapters = translated.get("chapters") or []
    _require_same_length("chapters", src_chapters, tr_chapters)
    for chapter, tr_chapter in zip(src_chapters, tr_chapters):
        _set_if_source_has(chapter, "headline", tr_chapter.get("headline"))
        _set_if_source_has(chapter, "location", tr_chapter.get("location"))
        if chapter.get("involved_people"):
            chapter["involved_people"] = [
                localize_name(name, name_glossary)
                for name in chapter["involved_people"]
            ]

    _set_if_source_has(result, "conclusion", translated.get("conclusion"))

    src_events = result.get("events") or []
    tr_events = translated.get("events") or []
    _require_same_length("events", src_events, tr_events)
    for event, tr_event in zip(src_events, tr_events):
        _set_if_source_has(event, "title", tr_event.get("title"))
        _set_if_source_has(event, "description", tr_event.get("description"))
        _set_if_source_has(event, "date_note", tr_event.get("date_note"))

        src_locations = [
            loc for loc in (event.get("locations") or []) if isinstance(loc, dict)
        ]
        tr_locations = tr_event.get("locations") or []
        _require_same_length("event.locations", src_locations, tr_locations)
        for loc, tr_loc in zip(src_locations, tr_locations):
            _set_if_source_has(loc, "name_historic", tr_loc.get("name_historic"))
            _set_if_source_has(loc, "name_modern", tr_loc.get("name_modern"))

        src_images = event.get("images") or []
        tr_images = tr_event.get("images") or []
        _require_same_length("event.images", src_images, tr_images)
        for img, tr_img in zip(src_images, tr_images):
            _set_if_source_has(img, "caption", tr_img.get("caption"))

        annotations = event.get("annotations")
        if annotations:
            translated_by_term = {
                item.get("term"): item.get("explanation")
                for item in (tr_event.get("annotations") or [])
            }
            for term, ann in annotations.items():
                explanation = translated_by_term.get(term)
                if explanation:
                    ann["explanation"] = explanation

        if event.get("involved_people"):
            event["involved_people"] = [
                localize_name(name, name_glossary) for name in event["involved_people"]
            ]

    return result


def apply_ego_network_translations(
    source_data: Dict[str, Any],
    translated: Dict[str, Any],
    name_glossary: Dict[str, str],
) -> Dict[str, Any]:
    """Overlay a translated payload onto a deep copy of the English network."""
    result = copy.deepcopy(source_data)

    ego = result.get("ego", {})
    _set_if_source_has(ego, "summary", translated.get("ego_summary"))
    src_roles = ego.get("primary_roles") or []
    tr_roles = translated.get("ego_primary_roles") or []
    _require_same_length("ego.primary_roles", src_roles, tr_roles)
    if "primary_roles" in ego:
        ego["primary_roles"] = tr_roles
    if ego.get("name"):
        ego["name"] = localize_name(ego["name"], name_glossary)

    src_connections = result.get("connections") or []
    tr_connections = translated.get("connections") or []
    _require_same_length("connections", src_connections, tr_connections)
    for conn, tr_conn in zip(src_connections, tr_connections):
        _set_if_source_has(
            conn, "relationship_description", tr_conn.get("relationship_description")
        )
        _set_if_source_has(conn, "notes", tr_conn.get("notes"))
        src_activities = conn.get("shared_activities") or []
        tr_activities = tr_conn.get("shared_activities") or []
        _require_same_length(
            "connection.shared_activities", src_activities, tr_activities
        )
        if "shared_activities" in conn:
            conn["shared_activities"] = tr_activities
        if conn.get("person_name"):
            conn["person_name"] = localize_name(conn["person_name"], name_glossary)

    src_categories = result.get("category_summaries") or []
    tr_categories = translated.get("category_summaries") or []
    _require_same_length("category_summaries", src_categories, tr_categories)
    for cat, tr_cat in zip(src_categories, tr_categories):
        _set_if_source_has(cat, "summary", tr_cat.get("summary"))

    _set_if_source_has(result, "network_summary", translated.get("network_summary"))

    return result


def apply_registry_entry_translations(
    entry: Dict[str, Any],
    translated: Dict[str, Any],
    name_glossary: Dict[str, str],
) -> Dict[str, Any]:
    """Overlay a translated payload onto a deep copy of the registry entry."""
    result = copy.deepcopy(entry)
    _set_if_source_has(result, "tagline", translated.get("tagline"))
    _set_if_source_has(result, "summary", translated.get("summary"))
    src_roles = result.get("primaryRoles") or []
    tr_roles = translated.get("primary_roles") or []
    _require_same_length("primaryRoles", src_roles, tr_roles)
    if "primaryRoles" in result:
        result["primaryRoles"] = tr_roles
    if result.get("name"):
        result["name"] = localize_name(result["name"], name_glossary)
    result["lastUpdated"] = datetime.now().astimezone().isoformat()
    return result


def apply_meta_story_translations(
    source_data: Dict[str, Any],
    translated: Dict[str, Any],
    target_lang: str,
) -> Dict[str, Any]:
    """Overlay a translated payload onto a deep copy of the meta story.

    Where a person's translated life events exist, event titles referenced by
    the meta story are copied verbatim from that person's translated dataset
    (matched by ``event_index``), so meta story chapters and the actual story
    slides always show identical titles.
    """
    result = copy.deepcopy(source_data)

    meta = result.get("meta_story", {})
    _set_if_source_has(meta, "title", translated.get("title"))
    _set_if_source_has(meta, "tagline", translated.get("tagline"))
    _set_if_source_has(meta, "description", translated.get("description"))

    src_subtopics = result.get("subtopics") or []
    tr_subtopics = translated.get("subtopics") or []
    _require_same_length("subtopics", src_subtopics, tr_subtopics)
    for sub, tr_sub in zip(src_subtopics, tr_subtopics):
        _set_if_source_has(sub, "title", tr_sub.get("title"))
        _set_if_source_has(sub, "description", tr_sub.get("description"))

    # Cache of translated life events per person for event title lookups
    translated_events_cache: Dict[str, Optional[List[Dict[str, Any]]]] = {}

    def translated_event_title(person_id: str, event_index: Any) -> Optional[str]:
        if not isinstance(event_index, int):
            return None
        if person_id not in translated_events_cache:
            path = PEOPLE_DIR / person_id / target_lang / "life_events.json"
            data = load_json_file(path)
            translated_events_cache[person_id] = (
                data.get("events") if isinstance(data, dict) else None
            )
        events = translated_events_cache[person_id]
        if events and 0 <= event_index < len(events):
            title = events[event_index].get("title")
            return title if isinstance(title, str) else None
        return None

    def translated_image_caption(
        person_id: str, event_index: Any, image_index: Any
    ) -> Optional[str]:
        """Caption of an image from the person's translated life events."""
        if not isinstance(event_index, int) or not isinstance(image_index, int):
            return None
        # Reuse the cache warmed by translated_event_title.
        if person_id not in translated_events_cache:
            translated_event_title(person_id, event_index)
        events = translated_events_cache.get(person_id)
        if events and 0 <= event_index < len(events):
            images = events[event_index].get("images") or []
            if 0 <= image_index < len(images):
                caption = images[image_index].get("caption")
                return caption if isinstance(caption, str) else None
        return None

    def overlay_image_caption(image: Any, payload_caption: Optional[str]) -> None:
        """Overlay an image caption, preferring the person's translated data."""
        if not isinstance(image, dict) or image.get("caption") is None:
            return
        from_dataset = translated_image_caption(
            image.get("person_id", ""),
            image.get("event_index"),
            image.get("image_index"),
        )
        caption = from_dataset or payload_caption
        if caption:
            image["caption"] = caption

    src_chapters = result.get("chapters") or []
    tr_chapters = translated.get("chapters") or []
    _require_same_length("chapters", src_chapters, tr_chapters)
    for chapter, tr_chapter in zip(src_chapters, tr_chapters):
        _set_if_source_has(chapter, "title", tr_chapter.get("title"))
        _set_if_source_has(chapter, "lead_in", tr_chapter.get("lead_in"))
        src_contexts = chapter.get("historical_context") or []
        tr_contexts = tr_chapter.get("historical_context") or []
        _require_same_length("chapter.historical_context", src_contexts, tr_contexts)
        for ctx, tr_ctx in zip(src_contexts, tr_contexts):
            _set_if_source_has(ctx, "title", tr_ctx.get("title"))
            _set_if_source_has(ctx, "description", tr_ctx.get("description"))
        src_events = chapter.get("person_events") or []
        tr_events = tr_chapter.get("person_events") or []
        _require_same_length("chapter.person_events", src_events, tr_events)
        for pe, tr_pe in zip(src_events, tr_events):
            # Prefer the title from the person's translated life events
            from_dataset = translated_event_title(
                pe.get("person_id", ""), pe.get("event_index")
            )
            _set_if_source_has(
                pe, "event_title", from_dataset or tr_pe.get("event_title")
            )
            _set_if_source_has(pe, "theme_connection", tr_pe.get("theme_connection"))

    _set_if_source_has(result, "conclusion", translated.get("conclusion"))
    _set_if_source_has(result, "timeline_intro", translated.get("timeline_intro"))

    # Composed opening, section headings, and section images (Phase 7). Image
    # URLs/sources stay verbatim; captions prefer the person's translated life
    # events (like event titles) and fall back to the translated payload.
    src_opening = result.get("opening")
    tr_opening = translated.get("opening")
    if isinstance(src_opening, dict) and isinstance(tr_opening, dict):
        _set_if_source_has(src_opening, "text", tr_opening.get("text"))
        overlay_image_caption(src_opening.get("image"), tr_opening.get("image_caption"))
    src_headings = result.get("section_headings")
    tr_headings = translated.get("section_headings")
    if isinstance(src_headings, dict) and isinstance(tr_headings, dict):
        for slot in ("timeline", "network", "conclusion"):
            _set_if_source_has(src_headings, slot, tr_headings.get(slot))
    src_images = result.get("section_images")
    tr_images = translated.get("section_images")
    if isinstance(src_images, dict):
        tr_images = tr_images if isinstance(tr_images, dict) else {}
        for slot in ("timeline", "network", "conclusion"):
            overlay_image_caption(
                src_images.get(slot), tr_images.get(f"{slot}_caption")
            )

    # Network narration: the graph data stays verbatim, only the prose is
    # overlaid. Circle keys (main person ids) are technical and never touched.
    src_narration = (result.get("social_network") or {}).get("narration")
    tr_narration = translated.get("network_narration")
    if isinstance(src_narration, dict) and isinstance(tr_narration, dict):
        _set_if_source_has(src_narration, "intro", tr_narration.get("intro"))
        src_circles = src_narration.get("circles") or []
        tr_circles = tr_narration.get("circles") or []
        _require_same_length("network_narration.circles", src_circles, tr_circles)
        for circle, tr_circle in zip(src_circles, tr_circles):
            _set_if_source_has(circle, "title", tr_circle.get("title"))
            _set_if_source_has(circle, "text", tr_circle.get("text"))

    # Map narration: cluster data (labels, coordinates, events) stays
    # verbatim, only the prose is overlaid. Stop keys are technical.
    src_map_narration = (result.get("geo_map") or {}).get("narration")
    tr_map_narration = translated.get("map_narration")
    if isinstance(src_map_narration, dict) and isinstance(tr_map_narration, dict):
        _set_if_source_has(src_map_narration, "intro", tr_map_narration.get("intro"))
        src_stops = src_map_narration.get("stops") or []
        tr_stops = tr_map_narration.get("stops") or []
        _require_same_length("map_narration.stops", src_stops, tr_stops)
        for stop, tr_stop in zip(src_stops, tr_stops):
            _set_if_source_has(stop, "title", tr_stop.get("title"))
            _set_if_source_has(stop, "text", tr_stop.get("text"))

    return result


# ---------------------------------------------------------------------------
# Name glossary
# ---------------------------------------------------------------------------


def localize_name(name: str, glossary: Dict[str, str]) -> str:
    """Apply the name glossary to a person name.

    Handles both display form ("Henry II") and underscore form ("Henry_II"),
    which is used by the ``name`` fields in registry and person blocks.
    """
    if not glossary or not name:
        return name
    if name in glossary:
        return glossary[name]
    spaced = name.replace("_", " ")
    if spaced != name and spaced in glossary:
        return glossary[spaced].replace(" ", "_")
    return name


def collect_person_names(
    life_events: Optional[Dict[str, Any]],
    ego_network: Optional[Dict[str, Any]],
    registry_entry: Optional[Dict[str, Any]],
) -> List[str]:
    """Collect all person names appearing in the datasets (display form)."""
    names: List[str] = []

    def add(name: Any) -> None:
        if isinstance(name, str) and name.strip():
            display = name.replace("_", " ").strip()
            if display not in names:
                names.append(display)

    if registry_entry:
        add(registry_entry.get("name"))
    if life_events:
        add((life_events.get("person") or {}).get("name"))
        for chapter in life_events.get("chapters") or []:
            for name in chapter.get("involved_people") or []:
                add(name)
        for event in life_events.get("events") or []:
            for name in event.get("involved_people") or []:
                add(name)
    if ego_network:
        add((ego_network.get("ego") or {}).get("name"))
        for conn in ego_network.get("connections") or []:
            add(conn.get("person_name"))
    return names


def build_name_glossary(
    names: List[str],
    context_summary: str,
    target_lang: str,
    client: OpenAI,
    model: str,
    verbose: bool = False,
) -> Dict[str, str]:
    """Ask the model once which person names have standard localized versions.

    Returns a mapping of original display name -> localized display name,
    containing only names that actually change. Used deterministically across
    all documents of a person so naming stays consistent everywhere.
    """
    if not names:
        return {}
    lang_name = LANGUAGE_NAMES.get(target_lang, target_lang)

    prompt = f"""You will localize person names for a biographical app being translated to {lang_name}.

CONTEXT (who the biography is about):
{context_summary}

RULES:
- Keep names in their original form by DEFAULT. Return the name unchanged unless there is a standard, widely used {lang_name} version.
- Translate ONLY names of historical figures with a well-established {lang_name} exonym (e.g., for German: "Henry II" -> "Heinrich II.", "Charles V" -> "Karl V.", "Queen Elizabeth I" -> "Königin Elisabeth I.").
- NEVER translate modern names (e.g., "Alan Turing", "Grace Hopper", "Steve Jobs" stay unchanged).
- Keep epithets/parentheticals consistent with the {lang_name} convention.
- Return a mapping for EVERY name in the list below, with "localized" equal to "original" when unchanged.

NAMES:
{json.dumps(names, ensure_ascii=False, indent=2)}
"""

    if verbose:
        print(f"  Building name glossary for {len(names)} name(s)...")

    try:
        response = client.beta.chat.completions.parse(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": f"You are an expert on {lang_name} naming conventions for historical figures.",
                },
                {"role": "user", "content": prompt},
            ],
            response_format=NameGlossary,
        )
        parsed = response.choices[0].message.parsed
        if not parsed:
            return {}
        glossary = {
            m.original: m.localized
            for m in parsed.mappings
            if m.original and m.localized and m.original != m.localized
        }
        if verbose and glossary:
            for original, localized in glossary.items():
                print(f"    {original} -> {localized}")
        return glossary
    except Exception as e:
        print(f"  Warning: name glossary failed ({e}); keeping names unchanged")
        return {}


def format_glossary_for_prompt(glossary: Dict[str, str]) -> str:
    if not glossary:
        return "(none — keep every person name exactly as written)"
    return "\n".join(f'- "{k}" -> "{v}"' for k, v in glossary.items())


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


def slugify(name: str) -> str:
    """Convert a person name to a slug (person_id)."""
    # Remove parenthetical content
    name = name.split("(")[0].strip()
    # Convert to lowercase and replace spaces/special chars with underscores
    slug = name.lower().replace(" ", "_").replace(".", "_").replace("-", "_")
    # Remove consecutive underscores
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug.strip("_")


def find_person_by_name_or_id(name_or_id: str) -> Optional[Dict[str, Any]]:
    """Find a person in the registry by name or ID."""
    if not REGISTER_PATH.exists():
        print(f"Error: Registry file not found: {REGISTER_PATH}")
        return None

    with open(REGISTER_PATH, "r", encoding="utf-8") as f:
        registry = json.load(f)

    people = registry.get("people", [])

    # Try exact ID match first
    for person in people:
        if person.get("id") == name_or_id:
            return cast(Optional[Dict[str, Any]], person)

    # Try slugified name match
    slug = slugify(name_or_id)
    for person in people:
        if person.get("id") == slug:
            return cast(Optional[Dict[str, Any]], person)

    # Try name match (case-insensitive)
    search_lower = name_or_id.lower()
    for person in people:
        if person.get("name", "").lower().replace("_", " ") == search_lower:
            return cast(Optional[Dict[str, Any]], person)

    return None


def load_json_file(file_path: Path) -> Optional[Dict[str, Any]]:
    """Load a JSON file, return None if it doesn't exist."""
    if not file_path.exists():
        return None

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return cast(Optional[Dict[str, Any]], json.load(f))
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {file_path}: {e}")
        return None


def save_json_file(data: Dict[str, Any], file_path: Path, indent: int = 2) -> bool:
    """Save data to a JSON file (LF newlines, UTF-8, same style as generation)."""
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8", newline="") as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)
            f.write("\n")
        return True
    except Exception as e:
        print(f"Error: Failed to save {file_path}: {e}")
        return False


# ---------------------------------------------------------------------------
# Model calls
# ---------------------------------------------------------------------------


def _call_translation_model(
    payload: Dict[str, Any],
    response_format: Any,
    document_kind: str,
    extra_rules: str,
    target_lang: str,
    glossary: Dict[str, str],
    client: OpenAI,
    model: str,
    verbose: bool = False,
) -> Optional[Any]:
    """Send a translation payload to the model and parse the structured result."""
    lang_name = LANGUAGE_NAMES.get(target_lang, target_lang)
    style_note = LANGUAGE_STYLE_NOTES.get(target_lang, "")

    prompt = f"""Translate the following {document_kind} text fields to {lang_name}.

The input is a JSON payload containing ONLY translatable text extracted from a
larger document. Return the same structure with every text field translated.

GENERAL RULES:
1. Keep every array EXACTLY the same length and order as the input — item N of
   the output must be the translation of item N of the input.
2. Translate the MEANING, not the words. Write as a skilled native {lang_name}
   author would — the way a professional literary translator works, not a
   dictionary. Read each field, understand what it says, then re-express it
   naturally in {lang_name}.
   - Do NOT mirror English word order, sentence structure, or phrasing. Recast
     sentences so they flow the way {lang_name} really reads; split, merge, or
     reorder clauses when that is more natural.
   - Render English idioms, metaphors, and turns of phrase with their true
     {lang_name} equivalents — never translate them literally.
   - Choose the {lang_name} word a native writer would actually use, not the
     first cognate. Avoid stiff, calque-like phrasing and anglicisms.
   - The result must not read like a translation. If a passage sounds awkward
     or foreign in {lang_name}, rewrite it until it sounds native.
   - Preserve the full meaning, tone, and register faithfully; do not summarize,
     extend, or omit — but likeness of wording to the English is NOT a goal.
3. Preserve Markdown formatting exactly (links, emphasis, line breaks).
4. Descriptions may contain [[term|display]] annotation markers:
   - Keep the marker syntax and the term (before the |) EXACTLY as-is.
   - Translate ONLY the display text (after the |).
   - Annotation "term" keys in the payload must be returned UNCHANGED.
5. PLACE NAMES: use the standard {lang_name} version where one exists
   (e.g., for German: "Munich" -> "München", "Zurich, Switzerland" -> "Zürich, Schweiz").
6. PERSON NAMES: apply this glossary consistently wherever a name appears in
   any text; keep all other person names unchanged:
{format_glossary_for_prompt(glossary)}
{extra_rules}
{style_note}

PAYLOAD:
{json.dumps(payload, ensure_ascii=False, indent=2)}
"""

    if verbose:
        print(f"  Translating {document_kind} to {lang_name}...")

    try:
        response = client.beta.chat.completions.parse(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"You are an award-winning literary translator and native "
                        f"{lang_name} writer specializing in biographical prose. You "
                        f"translate meaning and voice, never word for word: your "
                        f"{lang_name} reads as though it were originally written in "
                        f"{lang_name}, with natural idiom, word choice, and sentence "
                        f"flow. Preserve structure, markers, and formatting exactly."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            response_format=response_format,
        )
        result = response.choices[0].message
        if result.parsed:
            return result.parsed
        if result.refusal:
            print(f"  Error: Model refused to translate: {result.refusal}")
        else:
            print("  Error: No parsed result returned")
        return None
    except APIStatusError as e:
        print(f"  Error: OpenAI API error: {e}")
        return None
    except Exception as e:
        print(f"  Error: Translation failed: {e}")
        return None


def translate_life_events(
    source_data: Dict[str, Any],
    target_lang: str,
    client: OpenAI,
    model: str,
    glossary: Dict[str, str],
    verbose: bool = False,
) -> Optional[Dict[str, Any]]:
    """Translate a life events dataset; returns the full derived document."""
    payload = extract_life_events_translatables(source_data)
    parsed = _call_translation_model(
        payload=payload,
        response_format=LifeEventsTranslation,
        document_kind="biographical life events",
        extra_rules=(
            "7. Chapter headlines are short, evocative book-chapter titles — "
            "keep them punchy (2-5 words).\n"
            "8. Event titles are crisp headlines (2-6 words); use sentence-style "
            "phrasing natural for the target language."
        ),
        target_lang=target_lang,
        glossary=glossary,
        client=client,
        model=model,
        verbose=verbose,
    )
    if parsed is None:
        return None
    try:
        result = apply_life_events_translations(
            source_data, parsed.model_dump(), glossary
        )
    except TranslationMergeError as e:
        print(f"  Error: translation does not align with source: {e}")
        return None
    result["translation"] = make_translation_block(
        compute_fingerprint(payload), target_lang, f"openai:{model}"
    )
    return result


def translate_ego_network(
    source_data: Dict[str, Any],
    target_lang: str,
    client: OpenAI,
    model: str,
    glossary: Dict[str, str],
    verbose: bool = False,
) -> Optional[Dict[str, Any]]:
    """Translate an ego network dataset; returns the full derived document."""
    payload = extract_ego_network_translatables(source_data)
    parsed = _call_translation_model(
        payload=payload,
        response_format=EgoNetworkTranslation,
        document_kind="social network",
        extra_rules=(
            "7. shared_activities are short activity tags — translate them "
            "concisely (1-4 words each)."
        ),
        target_lang=target_lang,
        glossary=glossary,
        client=client,
        model=model,
        verbose=verbose,
    )
    if parsed is None:
        return None
    try:
        result = apply_ego_network_translations(
            source_data, parsed.model_dump(), glossary
        )
    except TranslationMergeError as e:
        print(f"  Error: translation does not align with source: {e}")
        return None
    result["translation"] = make_translation_block(
        compute_fingerprint(payload), target_lang, f"openai:{model}"
    )
    return result


def translate_registry_entry(
    source_entry: Dict[str, Any],
    target_lang: str,
    client: OpenAI,
    model: str,
    glossary: Dict[str, str],
    verbose: bool = False,
) -> Optional[Dict[str, Any]]:
    """Translate a registry entry; returns the full derived entry."""
    payload = extract_registry_entry_translatables(source_entry)
    parsed = _call_translation_model(
        payload=payload,
        response_format=RegistryEntryTranslation,
        document_kind="person registry entry",
        extra_rules=(
            "7. The tagline is a short epithet shown on the landing page — "
            "keep it evocative and brief."
        ),
        target_lang=target_lang,
        glossary=glossary,
        client=client,
        model=model,
        verbose=verbose,
    )
    if parsed is None:
        return None
    try:
        result = apply_registry_entry_translations(
            source_entry, parsed.model_dump(), glossary
        )
    except TranslationMergeError as e:
        print(f"  Error: translation does not align with source: {e}")
        return None
    result["translation"] = make_translation_block(
        compute_fingerprint(payload), target_lang, f"openai:{model}"
    )
    return result


def translate_meta_story(
    source_data: Dict[str, Any],
    target_lang: str,
    client: OpenAI,
    model: str,
    verbose: bool = False,
) -> Optional[Dict[str, Any]]:
    """Translate a meta story dataset; returns the full derived document."""
    payload = extract_meta_story_translatables(source_data)
    parsed = _call_translation_model(
        payload=payload,
        response_format=MetaStoryTranslation,
        document_kind="thematic story collection (meta story)",
        extra_rules=(
            "7. Chapter titles may end with a date range in parentheses, e.g. "
            '"Programmability Imagined (1820-1852)" — translate the words and '
            "keep the parenthesized range exactly as-is.\n"
            "8. event_title entries reference event slides — translate them as "
            "crisp headlines (2-6 words).\n"
            "9. network_narration texts are short narrative paragraphs about "
            "the story's social network — translate them as flowing prose, "
            "localizing person names per the usual name rules. Each circle also "
            "has a title, an evocative 2-5 word headline (not a list of names) — "
            "translate it as a headline, not literally.\n"
            "10. timeline_intro and chapter lead_in entries are short narrative "
            "passages shown around the story timeline — translate them as "
            "flowing prose in the same voice as the description.\n"
            "11. opening is the story's cold-open scene and section_headings "
            "are its section titles — translate both as narrative prose and "
            "evocative headlines respectively, never as literal labels. "
            "image_caption / *_caption entries are image captions.\n"
            "12. map_narration texts are short narrative paragraphs about the "
            "places of the story — translate them as flowing prose, localizing "
            "place names per the usual place rules. Each stop also has a "
            "title, an evocative 2-5 word headline — translate it as a "
            "headline, not literally."
        ),
        target_lang=target_lang,
        glossary={},
        client=client,
        model=model,
        verbose=verbose,
    )
    if parsed is None:
        return None
    try:
        result = apply_meta_story_translations(
            source_data, parsed.model_dump(), target_lang
        )
    except TranslationMergeError as e:
        print(f"  Error: translation does not align with source: {e}")
        return None
    result["translation"] = make_translation_block(
        compute_fingerprint(payload), target_lang, f"openai:{model}"
    )
    return result


# ---------------------------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------------------------


def update_language_registry(
    person_entry: Dict[str, Any], target_lang: str, verbose: bool = False
) -> bool:
    """Update or create the language-specific registry file.

    Entries are kept in the same order as the English registry so both
    registries stay aligned.
    """
    registry_path = DATA_DIR / f"persons_{target_lang}.json"

    # Load existing registry or create new one
    if registry_path.exists():
        with open(registry_path, "r", encoding="utf-8") as f:
            registry = json.load(f)
    else:
        registry = {"people": []}

    # Find and update or append
    person_id = person_entry["id"]
    found = False
    for i, person in enumerate(registry["people"]):
        if person["id"] == person_id:
            registry["people"][i] = person_entry
            found = True
            if verbose:
                print(f"  Updated {person_id} in {registry_path.name}")
            break

    if not found:
        registry["people"].append(person_entry)
        if verbose:
            print(f"  Added {person_id} to {registry_path.name}")

    # Keep the language registry ordered like the English registry
    english = load_json_file(REGISTER_PATH) or {}
    order = {p["id"]: i for i, p in enumerate(english.get("people", []))}
    registry["people"].sort(key=lambda p: order.get(p.get("id"), len(order)))

    # Save registry
    return save_json_file(registry, registry_path)


# ---------------------------------------------------------------------------
# Status checks (no API required)
# ---------------------------------------------------------------------------


def check_person_translation(person_id: str, target_lang: str) -> Dict[str, str]:
    """Report the translation status of a person without calling any API.

    Returns a dict with keys 'life_events', 'ego_network', 'registry', each
    'missing', 'stale', 'current', or 'no-source'.
    """
    person_dir = PEOPLE_DIR / person_id
    result = {}

    result["life_events"] = translation_status(
        load_json_file(person_dir / "life_events.json"),
        load_json_file(person_dir / target_lang / "life_events.json"),
        extract_life_events_translatables,
    )
    result["ego_network"] = translation_status(
        load_json_file(person_dir / "ego_network.json"),
        load_json_file(person_dir / target_lang / "ego_network.json"),
        extract_ego_network_translatables,
    )

    source_entry = find_person_by_name_or_id(person_id)
    registry = load_json_file(DATA_DIR / f"persons_{target_lang}.json") or {}
    target_entry = next(
        (p for p in registry.get("people", []) if p.get("id") == person_id), None
    )
    result["registry"] = translation_status(
        source_entry, target_entry, extract_registry_entry_translatables
    )
    return result


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def translate_person_data(
    person_id: str,
    target_lang: str,
    client: OpenAI,
    model: str = DEFAULT_MODEL,
    force: bool = False,
    verbose: bool = False,
) -> Dict[str, bool]:
    """
    Translate a person's data to target language, derived from the English data.

    Without ``force``, only missing or stale documents are (re)translated;
    documents whose fingerprint matches the current English source are skipped.

    Returns:
        Dict with keys: 'life_events', 'ego_network', 'registry'
        Values are True if (re)translated successfully, False otherwise
    """
    results = {"life_events": False, "ego_network": False, "registry": False}

    person_dir = PEOPLE_DIR / person_id
    if not person_dir.exists():
        print(f"Error: Person directory not found: {person_dir}")
        return results

    status = check_person_translation(person_id, target_lang)
    if not force and all(value == "current" for value in status.values()):
        if verbose:
            print(f"  Translation up to date for {person_id} (use --force to redo)")
        return results

    # Load sources
    life_events_source = load_json_file(person_dir / "life_events.json")
    ego_network_source = load_json_file(person_dir / "ego_network.json")
    registry_entry = find_person_by_name_or_id(person_id)

    # Build the shared name glossary once for consistent naming everywhere
    context_summary = ""
    if registry_entry:
        context_summary = registry_entry.get("summary", "")
    elif life_events_source:
        context_summary = (life_events_source.get("person") or {}).get("summary", "")
    glossary = build_name_glossary(
        collect_person_names(life_events_source, ego_network_source, registry_entry),
        context_summary,
        target_lang,
        client,
        model,
        verbose,
    )

    target_dir = person_dir / target_lang

    # Translate life events
    if life_events_source is None:
        if verbose:
            print(f"  ⚠ Life events not found for {person_id}")
    elif force or status["life_events"] != "current":
        translated = translate_life_events(
            life_events_source, target_lang, client, model, glossary, verbose
        )
        if translated and save_json_file(translated, target_dir / "life_events.json"):
            results["life_events"] = True
            if verbose:
                print(f"  ✓ Life events translated: {target_dir / 'life_events.json'}")
    elif verbose:
        print("  → Life events translation is current")

    # Translate ego network
    if ego_network_source is None:
        if verbose:
            print(f"  ⚠ Ego network not found for {person_id}")
    elif force or status["ego_network"] != "current":
        translated = translate_ego_network(
            ego_network_source, target_lang, client, model, glossary, verbose
        )
        if translated and save_json_file(translated, target_dir / "ego_network.json"):
            results["ego_network"] = True
            if verbose:
                print(f"  ✓ Ego network translated: {target_dir / 'ego_network.json'}")
    elif verbose:
        print("  → Ego network translation is current")

    # Translate registry entry
    if registry_entry is None:
        if verbose:
            print("  ⚠ Person not found in registry")
    elif force or status["registry"] != "current":
        translated = translate_registry_entry(
            registry_entry, target_lang, client, model, glossary, verbose
        )
        if translated and update_language_registry(translated, target_lang, verbose):
            results["registry"] = True
            if verbose:
                print("  ✓ Registry entry updated")
    elif verbose:
        print("  → Registry translation is current")

    # Refresh copied event titles in translated meta stories without
    # retranslating or regenerating those stories.
    try:
        from sync_meta_story_events import sync_meta_story_events

        sync_meta_story_events(person_id, verbose=verbose)
    except Exception as error:
        print(f"  Warning: Could not sync translated meta-story events: {error}")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Translate a person's data to a target language using OpenAI API"
    )
    parser.add_argument(
        "person_name_or_id",
        help="Person name or ID (e.g., 'Alan Turing' or 'alan_turing')",
    )
    parser.add_argument(
        "--target-lang",
        required=True,
        help="Target language code (e.g., 'de', 'fr', 'es')",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-translate even if the translation is current",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"OpenAI model to use (default: {DEFAULT_MODEL})",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")

    args = parser.parse_args()

    # Validate OpenAI API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY environment variable not set")
        sys.exit(1)

    # Initialize OpenAI client
    client = OpenAI(api_key=api_key)

    # Find person
    print(f"Looking up person: {args.person_name_or_id}")
    person = find_person_by_name_or_id(args.person_name_or_id)
    if not person:
        print(f"Error: Person not found: {args.person_name_or_id}")
        sys.exit(1)

    person_id = person["id"]
    person_name = person["name"]
    lang_name = LANGUAGE_NAMES.get(args.target_lang, args.target_lang)

    print(f"Translating {person_name} ({person_id}) to {lang_name}...")

    # Translate
    results = translate_person_data(
        person_id=person_id,
        target_lang=args.target_lang,
        client=client,
        model=args.model,
        force=args.force,
        verbose=args.verbose,
    )

    # Report results
    status = check_person_translation(person_id, args.target_lang)
    print("\nTranslation Results:")
    for key, label in (
        ("life_events", "Life Events"),
        ("ego_network", "Ego Network"),
        ("registry", "Registry"),
    ):
        marker = "✓" if results[key] else ("→" if status[key] == "current" else "✗")
        print(f"  {label}: {marker} ({status[key]})")

    if all(value == "current" for value in status.values()):
        print(f"\n✓ Translation complete and current for {person_name}")
        sys.exit(0)
    else:
        print(f"\n✗ Translation incomplete for {person_name}")
        sys.exit(1)
