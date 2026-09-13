#!/usr/bin/env python3
"""Generate an abstract illustration for every chapter of a person's story.

A chapter slide holds a headline, a date range, a place and a few people, and
on a full screen that is close to nothing — the one slide in a story with no
picture on it. This fills that space without contradicting what the slide is
for: the illustration is *not* a scene, a portrait, or a building. It is an
abstract, metaphorical image of the chapter's theme, so it can sit behind the
headline as atmosphere rather than as a second claim about what happened.

Two calls per person, and the split is the point:

1. **The concept** — one text call reads the whole chapter list at once, with
   each chapter's events, and writes a short visual concept per chapter. It
   sees them together so the metaphors differ from one another; a call per
   chapter gave three chapters the same rising light. The rules it is held to
   are negative, because a model shown a biography draws the biography: no
   people, no faces, no recognizable buildings or landmarks, no text.
2. **The picture** — one image call per chapter, style-transferred from the
   same master style portrait the portraits use, with the *content* described
   by the concept instead of by a second reference image. That is what keeps a
   story's chapter art in the same visual family as its portrait.

The result is stored per chapter in ``life_events.json`` and synced to the
translated copies, since a path is not prose. The interface prints it
uncaptioned and translucent, so nothing about it needs translating.

Usage:
    python scripts/generate_chapter_illustrations.py alan_turing
    python scripts/generate_chapter_illustrations.py alan_turing --force
    python scripts/generate_chapter_illustrations.py alan_turing --chapter split_sunrise
    python scripts/generate_chapter_illustrations.py alan_turing --concepts-only
    python scripts/generate_chapter_illustrations.py alan_turing --dry-run
"""

from __future__ import annotations

import argparse
import base64
import os
import re
import sys
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, cast

import requests
from openai import APIStatusError, OpenAI
from PIL import Image
from pydantic import BaseModel, Field

from config import (
    DEFAULT_MODEL,
    DEFAULT_REASONING_EFFORT,
    PEOPLE_DIR,
    PUBLIC_DIR,
    REPO_ROOT,
    enable_utf8_console,
)
from utils import usage
from utils.concurrency import map_concurrently
from utils.datasets import event_files
from utils.json_io import read_json, write_json
from utils.model_calls import parse_structured
from utils.person_style import MissingStyleError, story_colors

enable_utf8_console()

CHAPTER_ART_DIR = PUBLIC_DIR / "chapter_art"
DEFAULT_MASTER_STYLE_PATH = PUBLIC_DIR / "master_style_portrait.png"

DEFAULT_IMAGE_MODEL = "gpt-image-2.5-flare"
"""The faster Images 2.5 variant: the illustration is drawn from a prompt and
a style reference alone, with no content to stay faithful to, so the editing
precision the portrait step pays Sunburst's latency for buys nothing here."""
IMAGE_SIZE = "1024x1024"
"""Square, because the illustration is an emblem above a headline rather than a
scene: a square crops equally badly nowhere, and the slide is read on a phone."""

WEBP_SIZES = {"medium": 512, "full": 1024}

# How much of an event's description the concept call gets to read. It needs the
# subject matter, not the prose; a chapter of six events at full length pushed
# the useful material past the point where the model kept the chapters apart.
EVENT_EXCERPT_CHARS = 320

CONCEPT_SYSTEM_PROMPT = """You are an art director for a biographical storytelling app.

For each chapter of a life you write ONE short visual concept for an abstract illustration that opens the chapter. The illustration is atmosphere, not documentation: it prepares the reader for the chapter's theme without depicting anything that happened in it.

HARD RULES — the concept must never contain:
- People, figures, silhouettes, hands, faces, or any part of a human body
- Portraits, crowds, or anything that reads as a character
- Recognizable buildings, monuments, landmarks, skylines, maps, flags, or emblems of a nation or institution
- Text, letters, numbers, equations, signatures, or symbols that spell something
- A depicted historical scene, machine, or invention that the reader could mistake for a photograph of the real thing

WRITE INSTEAD:
- Abstract and metaphorical imagery: geometry, natural forms, light, motion, materials, forces
- Concrete visual nouns, so the image model has something to draw — "a lattice of thin filaments unravelling at one edge", not "the feeling of loss"
- One clear focal idea per concept, centered and emblematic, floating in darkness
- Metaphor is welcome and encouraged: a thread cut, a door of light, a horizon folding, a shell splitting open

Generic objects are allowed where they carry the metaphor (a key, a wave, a spiral, a broken circle) as long as they are not a specific real object from the person's life.

VARIETY:
- The chapters are shown to you together. Every concept must be visually distinct from the others — different forms, different motion, different metaphor. Do not repeat a motif across chapters of the same life.

LENGTH: 25-45 words per concept, one or two sentences, written as an image description."""

IMAGE_PROMPT = """You are given ONE reference image: a style reference showing the artistic treatment to apply.

Create a NEW, entirely abstract illustration in exactly that artistic style. Do NOT reproduce, trace, or reference the content of the reference image — take only its rendering technique from it.

SUBJECT TO DRAW (this, and nothing else):
{concept}

ABSOLUTELY FORBIDDEN:
- Any human figure, face, silhouette, body part, or anything that reads as a person
- Any recognizable building, monument, landmark, map, or flag
- Any text, letters, numbers, or written symbols
- Any frame, border, oval, vignette, cartouche, or decorative surround

ARTISTIC TREATMENT — take from the reference image:
- Light-drawing / light-painting aesthetic: glowing strokes drawn in darkness
- Broad, bold, luminous lines with visible light trails, as if drawn with a moving light source
- Sketchy and expressive, not photorealistic and not a flat vector graphic
- Long-exposure photography feel, with a slight bloom around the brightest strokes

COLOR PALETTE:
- Luminous strokes in pure white (#FFFFFF), {primary}, and {secondary}
- Pure black background (#000000), unbroken, extending to all four edges
- Strong contrast between the glowing strokes and the black ground

COMPOSITION:
- Square format, one centered emblematic form
- Generous black margin on all sides; the form must not touch or crowd the edges
- The image is drawn entirely with glowing light strokes against pure black"""


class ChapterConcept(BaseModel):
    """One chapter's visual concept, addressed by the chapter's own id."""

    chapter_id: str = Field(description="The id of the chapter this concept is for.")
    concept: str = Field(
        description=(
            "25-45 words describing an abstract, metaphorical image for this "
            "chapter. No people, no recognizable places, no text."
        )
    )


class ChapterConcepts(BaseModel):
    """A concept for every chapter of one life, written in one pass."""

    concepts: List[ChapterConcept]


def slugify(value: str) -> str:
    """Convert a string into a URL-friendly slug."""
    slug = re.sub(r"[^a-z0-9]+", "_", value.strip().lower())
    return slug.strip("_") or "person"


def load_dataset(person_id: str) -> Dict[str, Any]:
    """Read a person's English life events document."""
    path = PEOPLE_DIR / person_id / "life_events.json"
    if not path.exists():
        raise FileNotFoundError(f"No life events dataset for '{person_id}': {path}")
    return cast(Dict[str, Any], read_json(path))


def _excerpt(text: str, limit: int = EVENT_EXCERPT_CHARS) -> str:
    """A single-line excerpt of a description, with interface markup removed."""
    plain = re.sub(
        r"\[\[([^\[\]|]+)(?:\|([^\[\]]*))?\]\]",
        lambda m: m.group(2) or m.group(1),
        text or "",
    )
    plain = re.sub(r"[*_#`]", "", plain)
    plain = " ".join(plain.split())
    return plain[:limit].rstrip() + ("…" if len(plain) > limit else "")


def build_concept_prompt(dataset: Dict[str, Any]) -> str:
    """Describe every chapter and its events for the concept call.

    The whole life goes in one message so the model can hold the chapters apart
    from one another — variety between them is a property of the set, not of any
    single chapter, and it cannot be asked for one call at a time.
    """
    person = dataset.get("person", {}) or {}
    chapters = dataset.get("chapters") or []
    events = dataset.get("events") or []

    # Datasets store the name as it was slugged from ("Alan_Turing"); the model
    # is shown the name a reader would write.
    name = str(person.get("name") or dataset.get("person_id") or "Unknown")
    lines: List[str] = [f"SUBJECT: {name.replace('_', ' ')}"]
    roles = person.get("primary_roles") or []
    if roles:
        lines.append(f"ROLES: {', '.join(str(role) for role in roles)}")
    if person.get("tagline"):
        lines.append(f"TAGLINE: {person['tagline']}")
    if person.get("summary"):
        lines.append(f"SUMMARY: {_excerpt(str(person['summary']), 600)}")
    lines.append("")
    lines.append(f"CHAPTERS ({len(chapters)}):")

    for index, chapter in enumerate(chapters, start=1):
        chapter_id = chapter.get("id", "")
        span = " – ".join(
            part
            for part in (chapter.get("date_start"), chapter.get("date_end"))
            if part
        )
        lines.append("")
        lines.append(f"[{index}] id: {chapter_id}")
        lines.append(f"    headline: {chapter.get('headline', '')}")
        if span:
            lines.append(f"    years: {span}")
        if chapter.get("location"):
            lines.append(f"    place: {chapter['location']}")

        chapter_events = [
            event for event in events if event.get("chapter") == chapter_id
        ]
        if chapter_events:
            lines.append("    events:")
            for event in chapter_events:
                title = event.get("title", "")
                summary = _excerpt(str(event.get("description", "")))
                lines.append(f"      - {title}: {summary}")

    lines.append("")
    lines.append(
        "Write one abstract visual concept per chapter, keyed by the chapter id "
        "exactly as given above. Return one entry per chapter, in order."
    )
    return "\n".join(lines)


def write_chapter_concepts(
    client: OpenAI,
    dataset: Dict[str, Any],
    *,
    model: str = DEFAULT_MODEL,
    reasoning_effort: str = DEFAULT_REASONING_EFFORT,
) -> Dict[str, str]:
    """Ask the model for one visual concept per chapter, keyed by chapter id.

    Returns an empty mapping when the call produced nothing usable; the caller
    then leaves the chapters as they are rather than drawing something arbitrary.
    """
    parsed = parse_structured(
        client,
        model=model,
        reasoning_effort=reasoning_effort,
        input=[
            {"role": "system", "content": CONCEPT_SYSTEM_PROMPT},
            {"role": "user", "content": build_concept_prompt(dataset)},
        ],
        text_format=ChapterConcepts,
        label="chapter illustration concepts",
    )
    if parsed is None:
        return {}

    known_ids = {
        chapter.get("id") for chapter in (dataset.get("chapters") or []) if chapter
    }
    concepts: Dict[str, str] = {}
    for entry in parsed.concepts:
        if entry.chapter_id not in known_ids:
            print(f"  Warning: concept for unknown chapter '{entry.chapter_id}'")
            continue
        concept = " ".join(entry.concept.split())
        if concept:
            concepts[entry.chapter_id] = concept
    return concepts


def request_illustration(
    client: OpenAI,
    concept: str,
    colors: Dict[str, str],
    *,
    master_style_path: Path,
    model: str,
) -> Optional[bytes]:
    """Style-transfer one abstract illustration, or return None having said why."""
    prompt = IMAGE_PROMPT.format(
        concept=concept,
        primary=colors["primary"],
        secondary=colors["secondary"],
    )
    try:
        with open(master_style_path, "rb") as style_file:
            response = client.images.edit(
                model=model,
                image=[style_file],
                prompt=prompt,
                size=IMAGE_SIZE,
                n=1,
            )
        usage.record_response(model, response, label="chapter illustration", images=1)
    except APIStatusError as error:
        status = getattr(error, "status_code", "unknown")
        print(f"  ✗ Image API error ({status}): {error}", file=sys.stderr)
        return None
    except Exception as error:  # noqa: BLE001 — one bad chapter must not end the run
        print(
            f"  ✗ Image generation failed: {type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return None

    data = getattr(response, "data", None)
    if not data:
        print("  ✗ Image API returned no data", file=sys.stderr)
        return None

    payload = data[0]
    encoded = getattr(payload, "b64_json", None)
    if encoded:
        return base64.b64decode(encoded)

    url = getattr(payload, "url", None)
    if url:
        try:
            download = requests.get(url, timeout=120)
            download.raise_for_status()
            return bytes(download.content)
        except requests.RequestException as error:
            print(f"  ✗ Could not download generated image: {error}", file=sys.stderr)
            return None

    print("  ✗ Image API returned neither image data nor a URL", file=sys.stderr)
    return None


def write_webp_sizes(
    image_bytes: bytes, person_id: str, chapter_id: str
) -> Dict[str, str]:
    """Write the generated illustration as WebP in the sizes the slide asks for.

    No PNG master is kept. A portrait is the one image of a person and worth the
    original bytes; chapter art is decoration that can be regenerated from the
    stored concept, and a corpus-wide set of PNG masters would outweigh every
    other asset in the repository.
    """
    target_dir = CHAPTER_ART_DIR / person_id
    target_dir.mkdir(parents=True, exist_ok=True)

    paths: Dict[str, str] = {}
    with Image.open(BytesIO(image_bytes)) as source:
        image = source.convert("RGB")
        for size_key, edge in WEBP_SIZES.items():
            resized = image.resize((edge, edge), Image.Resampling.LANCZOS)
            filename = f"{chapter_id}_{size_key}.webp"
            output_path = target_dir / filename
            resized.save(
                output_path,
                "WEBP",
                quality=85 if size_key == "full" else 80,
                method=6,
            )
            paths[size_key] = f"/chapter_art/{person_id}/{filename}"
            size_kb = output_path.stat().st_size / 1024
            print(f"    ✓ {size_key} ({edge}x{edge}): {filename} ({size_kb:.1f} KB)")

    return paths


def sync_chapter_illustrations(
    person_id: str, illustrations: Dict[str, Dict[str, Any]]
) -> List[str]:
    """Write the illustrations into the English dataset and every translation.

    A path and a concept are not prose, so the translated copies carry the same
    values — the same rule the portrait follows. Chapters are matched by id, and
    a file that does not have one simply keeps what it has.
    """
    updated: List[str] = []
    for path in event_files(person_id):
        data = read_json(path)
        touched = False
        for chapter in data.get("chapters") or []:
            illustration = illustrations.get(chapter.get("id"))
            if illustration:
                chapter["illustration"] = illustration
                touched = True
        if touched:
            write_json(path, data)
            updated.append(str(path.relative_to(REPO_ROOT)))
    return updated


def _illustrate_chapters(
    person_id: str,
    *,
    chapter_ids: Optional[Sequence[str]] = None,
    master_style_path: Path = DEFAULT_MASTER_STYLE_PATH,
    model: str = DEFAULT_IMAGE_MODEL,
    concept_model: str = DEFAULT_MODEL,
    force: bool = False,
    concepts_only: bool = False,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Write an abstract illustration for each chapter that does not have one."""
    dataset = load_dataset(person_id)
    chapters = dataset.get("chapters") or []
    if not chapters:
        return {
            "id": person_id,
            "success": True,
            "generated": [],
            "message": "No chapters in this dataset — nothing to illustrate",
        }

    wanted = [
        chapter
        for chapter in chapters
        if not chapter_ids or chapter.get("id") in set(chapter_ids)
    ]
    if chapter_ids and not wanted:
        return {
            "id": person_id,
            "success": False,
            "generated": [],
            "message": f"No chapter matches {', '.join(chapter_ids)}",
        }

    pending = [
        chapter
        for chapter in wanted
        if force or not (chapter.get("illustration") or {}).get("full")
    ]
    if not pending:
        print(f"⊘ Every chapter of '{person_id}' already has an illustration")
        print("  Use --force to regenerate")
        return {
            "id": person_id,
            "success": True,
            "generated": [],
            "cached": True,
            "message": "Illustrations already exist (use --force to regenerate)",
        }

    if not master_style_path.exists():
        message = f"Master style image not found: {master_style_path}"
        print(f"✗ {message}", file=sys.stderr)
        return {"id": person_id, "success": False, "generated": [], "message": message}

    # The colors the strokes are drawn in come from the story's style, so the
    # step is downstream of it. Without a style there is nothing to draw in:
    # stopping here costs a run, while drawing in a default palette costs a set
    # of cached illustrations that no later run has a reason to redraw.
    try:
        colors = story_colors(person_id)
    except MissingStyleError as error:
        print(f"✗ {error}", file=sys.stderr)
        return {
            "id": person_id,
            "success": False,
            "generated": [],
            "message": str(error),
        }

    print(f"[Step 1/4] {len(pending)} chapter(s) to illustrate for '{person_id}'")
    print(f"  Primary {colors['primary']}, secondary {colors['secondary']}")

    print("[Step 2/4] Writing visual concepts...")
    if dry_run:
        print("  (Dry run: skipping the concept call)")
        print(build_concept_prompt(dataset))
        return {
            "id": person_id,
            "success": True,
            "generated": [],
            "message": "Dry run — prompt printed, nothing called or written",
        }

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY environment variable is not set.")
    client = OpenAI(api_key=api_key, timeout=300.0)

    concepts = write_chapter_concepts(client, dataset, model=concept_model)
    if not concepts:
        message = "The concept call returned nothing usable"
        print(f"✗ {message}", file=sys.stderr)
        return {"id": person_id, "success": False, "generated": [], "message": message}

    # A chapter whose concept the call skipped keeps whatever it has: an
    # illustration drawn from a concept written for a different chapter would be
    # worse than an empty slide.
    illustrations: Dict[str, Dict[str, Any]] = {}
    generated: List[str] = []
    failed: List[str] = []
    today = date.today().isoformat()

    print("[Step 3/4] Generating illustrations...")
    drawable: List[Tuple[str, str]] = []
    for chapter in pending:
        chapter_id = chapter.get("id", "")
        concept = concepts.get(chapter_id)
        if not concept:
            print(f"  ⊘ {chapter_id}: no concept written, skipped")
            failed.append(chapter_id)
            continue

        print(f"  {chapter_id}: {concept}")
        if not concepts_only:
            drawable.append((chapter_id, concept))

    def draw(item: Tuple[str, str]) -> Tuple[str, Optional[Dict[str, Any]]]:
        """One chapter's illustration, drawn and written, or None having said why."""
        chapter_id, concept = item
        image_bytes = request_illustration(
            client,
            concept,
            colors,
            master_style_path=master_style_path,
            model=model,
        )
        if not image_bytes:
            return chapter_id, None
        paths = write_webp_sizes(image_bytes, person_id, chapter_id)
        return chapter_id, {
            "image": paths["medium"],
            "medium": paths["medium"],
            "full": paths["full"],
            "concept": concept,
            "creator": "AI generated artwork",
            "generated_on": today,
        }

    # The image calls are the slowest single calls of the run and read
    # nothing of each other — each draws its own concept into its own file —
    # so they are made side by side and gathered in chapter order.
    for chapter_id, illustration in map_concurrently(drawable, draw):
        if illustration is None:
            failed.append(chapter_id)
            continue
        illustrations[chapter_id] = illustration
        generated.append(chapter_id)

    print("[Step 4/4] Updating datasets...")
    if concepts_only:
        print("  (Concepts only: nothing written)")
    elif illustrations:
        updated = sync_chapter_illustrations(person_id, illustrations)
        for name in updated:
            print(f"  ✓ {name}")

    if concepts_only:
        message = f"Wrote {len(concepts)} concept(s), no images requested"
    else:
        message = f"Illustrated {len(generated)} of {len(pending)} chapter(s)"
    if failed:
        message += f"; failed: {', '.join(failed)}"
    return {
        "id": person_id,
        "success": bool(generated) or concepts_only,
        "generated": generated,
        "failed": failed,
        "message": message,
    }


def prune_orphaned_illustrations(person_id: str) -> List[str]:
    """Remove the chapter art files no chapter of the person's story refers to.

    The files are named by chapter id, so a regenerated story whose chapters
    carry new ids leaves the old chapters' pictures behind, and nothing in the
    application reaches them. A file stays while any language copy names it.
    A person with no dataset to read keeps every file, since there is then no
    record of which ones are in use. Returns the names of the removed files.
    """
    directory = CHAPTER_ART_DIR / person_id
    paths = event_files(person_id)
    if not directory.is_dir() or not paths:
        return []

    referenced = set()
    for path in paths:
        for chapter in read_json(path).get("chapters") or []:
            illustration = chapter.get("illustration") or {}
            for key in ("image", "medium", "full"):
                if isinstance(illustration.get(key), str):
                    referenced.add(illustration[key])

    removed: List[str] = []
    for file in sorted(directory.iterdir()):
        if file.is_file() and f"/chapter_art/{person_id}/{file.name}" not in referenced:
            file.unlink()
            removed.append(file.name)
    return removed


def generate_chapter_illustrations(
    person_id: str,
    *,
    chapter_ids: Optional[Sequence[str]] = None,
    master_style_path: Path = DEFAULT_MASTER_STYLE_PATH,
    model: str = DEFAULT_IMAGE_MODEL,
    concept_model: str = DEFAULT_MODEL,
    force: bool = False,
    concepts_only: bool = False,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Illustrate the chapters, then remove the files no chapter refers to.

    Returns a result dict with ``success``, the chapters it generated, and the
    files it removed, so the person pipeline can record the step without
    catching an exception per chapter. A dry run and a concepts-only run write
    no images and remove none.
    """
    result = _illustrate_chapters(
        person_id,
        chapter_ids=chapter_ids,
        master_style_path=master_style_path,
        model=model,
        concept_model=concept_model,
        force=force,
        concepts_only=concepts_only,
        dry_run=dry_run,
    )
    if dry_run or concepts_only:
        return result

    removed = prune_orphaned_illustrations(person_id)
    for name in removed:
        print(f"  − Removed {name}, which no chapter refers to")
    if removed:
        result["message"] += f"; removed {len(removed)} unused file(s)"
    result["removed"] = removed
    return result


def parse_args(argv: Any) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Generate abstract, style-transferred illustrations for the chapter "
            "slides of a person's story."
        )
    )
    parser.add_argument(
        "person_id_or_name",
        help="Person ID (e.g. 'alan_turing') or name (e.g. 'Alan Turing')",
    )
    parser.add_argument(
        "--chapter",
        action="append",
        dest="chapters",
        help="Only this chapter id (repeatable).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate chapters that already have an illustration",
    )
    parser.add_argument(
        "--concepts-only",
        action="store_true",
        help="Write and print the visual concepts without generating images",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the concept prompt without calling the API or writing files",
    )
    parser.add_argument(
        "--master-style",
        type=Path,
        default=DEFAULT_MASTER_STYLE_PATH,
        help=f"Path to the master style image (default: {DEFAULT_MASTER_STYLE_PATH})",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_IMAGE_MODEL,
        help=f"OpenAI image model (default: {DEFAULT_IMAGE_MODEL})",
    )
    parser.add_argument(
        "--concept-model",
        default=DEFAULT_MODEL,
        help=f"OpenAI text model for the concepts (default: {DEFAULT_MODEL})",
    )
    return parser.parse_args(argv)


def main(argv: Any = None) -> int:
    """Main entry point."""
    args = parse_args(argv)

    person_id_or_name = args.person_id_or_name
    if "_" in person_id_or_name or person_id_or_name.islower():
        person_id = person_id_or_name
    else:
        person_id = slugify(person_id_or_name)

    print(f"Generating chapter illustrations for: {person_id}")
    print()

    try:
        result = generate_chapter_illustrations(
            person_id,
            chapter_ids=args.chapters,
            master_style_path=args.master_style,
            model=args.model,
            concept_model=args.concept_model,
            force=args.force,
            concepts_only=args.concepts_only,
            dry_run=args.dry_run,
        )
    except Exception as error:  # noqa: BLE001 — reported as a failed run
        print(f"\n✗ Error: {error}", file=sys.stderr)
        return 1

    print()
    print(("✓ " if result["success"] else "✗ ") + result["message"])
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
