#!/usr/bin/env python3
"""Meta-story translation: schemas, extraction, application, and the call.

The person translator and this module share one contract — extract only the
translatable fields, translate them against naming evidence, and overlay the
result on a copy of the English document — and the shared machinery (the model
call, marker reconciliation, fingerprinting, the reference builder) lives in
``translate_person.py``. What is meta-story-specific lived there too for a
while, which put the whole meta-story schema inside a module that otherwise
knows nothing about meta stories; it now lives here, next to the CLI in
``translate_meta_story.py`` that drives it.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

from openai import OpenAI
from pydantic import BaseModel

from translate_person import (
    DATA_DIR,
    PEOPLE_DIR,
    REGISTER_PATH,
    TRANSLATION_MODEL,
    TranslationMergeError,
    TranslationReference,
    _call_translation_model,
    _require_same_length,
    _set_if_source_has,
    compute_fingerprint,
    load_json_file,
    make_translation_block,
)
from utils.wikipedia_cache import fetch_language_links


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


class TrNetworkCircle(BaseModel):
    # Optional: circles whose narration predates the headline field carry no
    # title in the payload, so the model isn't asked to invent one.
    title: Optional[str] = None
    text: str


class TrNetworkNarration(BaseModel):
    circles: List[TrNetworkCircle]


class TrMapStop(BaseModel):
    # Optional: stops kept without narration carry no title in the payload.
    title: Optional[str] = None
    text: str


class TrMapNarration(BaseModel):
    stops: List[TrMapStop]


class TrSectionHeadings(BaseModel):
    timeline: Optional[str] = None
    network: Optional[str] = None
    map: Optional[str] = None
    conclusion: Optional[str] = None


class TrBodyBlock(BaseModel):
    # One block of a prose region; only the keys present in the source block
    # appear in the payload: paragraph -> text; quote -> text (+ attribution);
    # image -> image_caption (only when the source image has a caption).
    text: Optional[str] = None
    attribution: Optional[str] = None
    image_caption: Optional[str] = None


class TrSectionBodies(BaseModel):
    # Each slot only present when the composed story carries that body.
    timeline: Optional[List[TrBodyBlock]] = None
    network: Optional[List[TrBodyBlock]] = None
    map: Optional[List[TrBodyBlock]] = None


class MetaStoryTranslation(BaseModel):
    title: str
    tagline: str
    subtopics: List[TrSubtopic]
    chapters: List[TrMetaChapter]
    # Optional: only present for composed stories (see compose_meta_story.py).
    # Every prose region is a list of blocks, aligned by index with the source.
    opening: Optional[List[TrBodyBlock]] = None
    description: Optional[List[TrBodyBlock]] = None
    section_headings: Optional[TrSectionHeadings] = None
    section_bodies: Optional[TrSectionBodies] = None
    conclusion: Optional[List[TrBodyBlock]] = None
    network_narration: Optional[TrNetworkNarration] = None
    map_narration: Optional[TrMapNarration] = None


# ---------------------------------------------------------------------------
# Extraction: English document -> translatable payload (plain dicts)
# ---------------------------------------------------------------------------


def _blocks_translatables(blocks: Any) -> List[Dict[str, Any]]:
    """One prose region's blocks as payload entries.

    Block types, layouts and image URLs/provenance are technical and stay
    verbatim; only paragraph/quote texts, attributions and image captions are
    prose. Entries keep their positions so the merge can align by index.
    """
    payload = []
    for block in blocks or []:
        entry: Dict[str, Any] = {}
        kind = block.get("type")
        if kind in ("paragraph", "quote"):
            entry["text"] = block.get("text", "")
            if kind == "quote" and block.get("attribution"):
                entry["attribution"] = block["attribution"]
        elif kind == "image":
            caption = (block.get("image") or {}).get("caption")
            if caption:
                entry["image_caption"] = caption
        payload.append(entry)
    return payload


def extract_meta_story_translatables(data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract only the translatable text fields from a meta story dataset."""
    meta = data.get("meta_story", {}) or {}
    payload: Dict[str, Any] = {
        "title": meta.get("title", ""),
        "tagline": meta.get("tagline", ""),
        # Subtopics reach the reader as timeline lane labels only; there is
        # nowhere to show a description, so none is written or translated.
        "subtopics": [
            {"title": sub.get("title", "")} for sub in (data.get("subtopics") or [])
        ],
        "chapters": [
            {
                "title": chapter.get("title", ""),
                # Composed lead-in only when present, so stories composed
                # before/without the composer phase keep their old fingerprint.
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
    }
    # Composed prose regions (see compose_meta_story.py): each a list of
    # paragraph/image/quote blocks. Only added when present, so uncomposed
    # stories keep their old fingerprint.
    for region in ("opening", "description", "conclusion"):
        blocks = _blocks_translatables(data.get(region))
        if blocks:
            payload[region] = blocks
    headings = data.get("section_headings")
    if isinstance(headings, dict) and headings:
        payload["section_headings"] = {
            slot: headings[slot]
            for slot in ("timeline", "network", "map", "conclusion")
            if headings.get(slot)
        }
    section_bodies = data.get("section_bodies")
    if isinstance(section_bodies, dict) and section_bodies:
        bodies_payload = {
            slot: _blocks_translatables(section_bodies.get(slot))
            for slot in ("timeline", "network", "map")
            if section_bodies.get(slot)
        }
        if bodies_payload:
            payload["section_bodies"] = bodies_payload
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
        payload["network_narration"] = {"circles": circles_payload}
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
        payload["map_narration"] = {"stops": stops_payload}
    return payload


# ---------------------------------------------------------------------------
# Fingerprints and provenance
# ---------------------------------------------------------------------------


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

    src_subtopics = result.get("subtopics") or []
    tr_subtopics = translated.get("subtopics") or []
    _require_same_length("subtopics", src_subtopics, tr_subtopics)
    for sub, tr_sub in zip(src_subtopics, tr_subtopics):
        _set_if_source_has(sub, "title", tr_sub.get("title"))

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

    def overlay_blocks(src_blocks: Any, tr_blocks: Any, label: str) -> None:
        """Overlay one prose region's translated text, aligned by index.

        Block structure (types, layouts, image URLs and provenance) stays
        verbatim; only paragraph/quote texts, attributions and image captions
        are replaced. Image captions prefer the person's translated life
        events and fall back to the payload.
        """
        if not isinstance(src_blocks, list) or not src_blocks:
            return
        tr_blocks = tr_blocks if isinstance(tr_blocks, list) else []
        _require_same_length(label, src_blocks, tr_blocks)
        for block, tr_block in zip(src_blocks, tr_blocks):
            kind = block.get("type")
            if kind in ("paragraph", "quote"):
                _set_if_source_has(block, "text", tr_block.get("text"))
                if kind == "quote":
                    _set_if_source_has(
                        block, "attribution", tr_block.get("attribution")
                    )
            elif kind == "image":
                overlay_image_caption(block.get("image"), tr_block.get("image_caption"))

    # Composed prose regions: the opening, the description and the closing.
    for region in ("opening", "description", "conclusion"):
        overlay_blocks(result.get(region), translated.get(region), region)

    src_headings = result.get("section_headings")
    tr_headings = translated.get("section_headings")
    if isinstance(src_headings, dict) and isinstance(tr_headings, dict):
        for slot in ("timeline", "network", "map", "conclusion"):
            _set_if_source_has(src_headings, slot, tr_headings.get(slot))
    src_bodies = result.get("section_bodies")
    tr_bodies = translated.get("section_bodies")
    if isinstance(src_bodies, dict) and isinstance(tr_bodies, dict):
        for slot in ("timeline", "network", "map"):
            overlay_blocks(
                src_bodies.get(slot), tr_bodies.get(slot), f"section_bodies.{slot}"
            )

    # Network narration: the graph data stays verbatim, only the prose is
    # overlaid. Circle keys (main person ids) are technical and never touched.
    src_narration = (result.get("social_network") or {}).get("narration")
    tr_narration = translated.get("network_narration")
    if isinstance(src_narration, dict) and isinstance(tr_narration, dict):
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


def build_meta_story_reference(
    story: Dict[str, Any], target_lang: str, verbose: bool = False
) -> TranslationReference:
    """The naming evidence for a meta story, which has no single subject.

    Its people already have translations of their own, and the interface
    matches a name in this prose against the name their story shows, so the
    strongest evidence is not Wikipedia's but the corpus's own: whatever each
    person's registry entry settled on. The map's place labels have no such
    record and are asked of the encyclopedia.
    """
    reference = TranslationReference()

    english = load_json_file(REGISTER_PATH) or {}
    translated = (
        load_json_file(DATA_DIR / f"persons_{target_lang}.json") or {}
        if target_lang
        else {}
    )
    localized_by_id = {
        entry.get("id"): entry.get("name")
        for entry in translated.get("people", [])
        if isinstance(entry, dict)
    }
    wanted = set(story.get("meta_story", {}).get("person_ids") or [])
    for entry in english.get("people", []):
        if not isinstance(entry, dict) or entry.get("id") not in wanted:
            continue
        name = str(entry.get("name") or "").replace("_", " ").strip()
        localized = str(localized_by_id.get(entry.get("id")) or "").replace("_", " ")
        if name and localized:
            reference.links[name] = {
                "title": localized.strip(),
                "description": "as this person's own story names them",
            }

    labels = [
        str(cluster.get("label"))
        for cluster in ((story.get("geo_map") or {}).get("clusters") or [])
        if isinstance(cluster, dict) and cluster.get("label")
    ]
    unknown = [label for label in labels if label not in reference.links]
    for label, link in fetch_language_links(unknown, target_lang).items():
        reference.links.setdefault(label, link)

    if verbose:
        print(f"  Reference: {len(reference.links)} name(s) on record")
    return reference


def translate_meta_story(
    source_data: Dict[str, Any],
    target_lang: str,
    client: OpenAI,
    model: str = TRANSLATION_MODEL,
    verbose: bool = False,
) -> Optional[Dict[str, Any]]:
    """Translate a meta story dataset; returns the full derived document."""
    payload = extract_meta_story_translatables(source_data)
    reference = build_meta_story_reference(source_data, target_lang, verbose)
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
            "10. chapter lead_in entries are short narrative passages shown "
            "around the story timeline — translate them as flowing prose in "
            "the story's voice.\n"
            "11. section_headings are the story's section titles — translate "
            "them as evocative headlines, never as literal labels.\n"
            "11b. opening, description, section_bodies and conclusion are the "
            "story's long-form narrative, each a list of blocks — translate "
            "text entries as flowing prose in the story's voice. A block with "
            "an attribution is a quotation: translate the quote faithfully (it "
            "is a rendered translation of a documented quote) and keep the "
            "attribution's names per the usual name rules. Blocks with only "
            "image_caption are image captions.\n"
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
        reference=reference,
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
