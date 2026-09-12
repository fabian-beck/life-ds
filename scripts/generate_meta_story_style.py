#!/usr/bin/env python3
"""Generate dark-mode visual styling for a meta story using the OpenAI API.

A meta story is read as an article rather than as a stack of slides, so its
identity carries one thing a person's does not: the marks that punctuate the
prose. Besides the color, type and frame system it produces a separator
glyph—set on the corner of the masthead's bracket, between two prose regions
and before every subhead—and a wider ornamental rule that closes the last
paragraph, the way a printed feature uses fleurons.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, cast

from openai import APIStatusError, OpenAI

from config import BULK_MODEL, BULK_REASONING_EFFORT, enable_utf8_console
from utils import usage
from utils.json_io import write_json
from utils.person_style import is_hex_color
from generate_person_style import (
    BODY_FONT_CHOICES,
    HEADING_FONT_CHOICES,
    sanitise_pattern_svg,
    sanitise_separator_glyph_svg,
)

enable_utf8_console()

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
META_STORIES_DIR = DATA_DIR / "meta_stories"
STYLES_PATH = DATA_DIR / "meta_story_styles.json"

ORNAMENT_VIEW_BOX = "0 0 240 24"

# How the story's boxes are cut. A named character rather than raw CSS: the
# frame has to sit on a narration card, on a floating chapter header and on a
# caption badge at once, so the concrete radii, border widths and border styles
# for each of those roles live in `src/utils/metaStoryStyles.js` (FRAMES) and
# only the name travels in the data. Keep both lists in step —
# tests/test_meta_story_styles.py fails when they disagree.
FRAME_CHOICES = {
    "square": (
        "no rounding at all and a hairline rule; machine-cut, for grids, "
        "circuitry, Bauhaus rigour"
    ),
    "engraved": (
        "a double rule with barely eased corners; the frame of a printed "
        "broadside or an engraving"
    ),
    "soft": "evenly rounded corners and a hairline rule; the neutral default",
    "arched": (
        "round-headed: the top corners spring in a wide curve while the "
        "bottom sits flat, like an arcade or a portal"
    ),
    "organic": "opposite corners disagree, so no edge repeats; grown not drawn",
}


def load_story_context(story_id: str) -> Dict[str, Any]:
    """What the style should answer to: the theme, its span, and its sections.

    Only the story's own framing is sent—title, tagline, date range, subtopic
    headings and the first paragraphs. The events themselves would swamp the
    prompt without telling it anything more about the story's tone.
    """
    story_path = META_STORIES_DIR / f"{story_id}.json"
    if not story_path.exists():
        raise FileNotFoundError(f"Meta story not found: {story_path}")

    data = json.loads(story_path.read_text(encoding="utf-8"))
    meta = data.get("meta_story") or {}
    context: Dict[str, Any] = {
        key: meta.get(key)
        for key in ("title", "tagline", "date_range_start", "date_range_end")
        if meta.get(key)
    }

    subtopics = [
        subtopic.get("title")
        for subtopic in data.get("subtopics") or []
        if isinstance(subtopic, dict) and subtopic.get("title")
    ]
    if subtopics:
        context["subtopics"] = subtopics

    headings = data.get("section_headings")
    if isinstance(headings, dict) and headings:
        context["section_headings"] = headings

    opening: List[str] = []
    for block in data.get("opening") or []:
        if isinstance(block, dict) and block.get("type") == "paragraph":
            text = block.get("text")
            if text:
                opening.append(text)
    if opening:
        context["opening"] = opening[:2]

    person_ids = meta.get("person_ids")
    if isinstance(person_ids, list) and person_ids:
        context["person_ids"] = person_ids

    return context


def build_prompt(story_id: str, context: Dict[str, Any]) -> str:
    details: list[str] = [
        "Design a cohesive dark-mode visual identity for the following meta "
        "story: an editorial article that presents several biographies around "
        "one theme, read as long scrolling prose with an interactive timeline, "
        "social network and map between its sections.",
        "Return a JSON object with fields: primary, secondary, background, "
        "background_pattern_svg, separator_glyph_svg, ornament_svg, frame, "
        "heading_font, body_font.",
        "Rules:",
        "- primary, secondary, and background must be hex colors in #RRGGBB format.",
        "- background must remain dark (perceived luminance under 0.18).",
        "- The primary color tints the running text, so it must stay legible "
        "as a light accent on the dark background; avoid muddy or oversaturated hues.",
        "- primary and secondary should contrast well against the background "
        "and with each other.",
        "- background_pattern_svg must be a 160x160 tileable SVG string that "
        "uses ONLY pure black (#000000) and pure white (#FFFFFF).",
        "- CRITICAL: NO gray shades allowed—only #000000 (black) and #FFFFFF "
        "(white). No #111111, #EEEEEE, or any other color values.",
        "- Do NOT use opacity, fill-opacity, or stroke-opacity attributes in "
        "any SVG. Use stroke-width variations instead for visual hierarchy.",
        "- The pattern is printed faintly behind a page of running text, so it "
        "must be calm and evenly distributed: no large solid areas, no dense "
        "clusters that would fight with the paragraphs above them.",
        "- The pattern must tile seamlessly: anything crossing an edge has to "
        "continue at the opposite edge.",
        "",
        "PATTERN DESIGN PRINCIPLES (CRITICAL):",
        "- Create a DISTINCTIVE geometric pattern that evokes the theme itself, "
        "not any single person in it.",
        "- ALL PATTERNS MUST BE ABSTRACT AND GEOMETRIC—no figurative or "
        "representational elements.",
        "- Use geometric primitives (circles, lines, rectangles, triangles, "
        "arcs, grids) arranged in characteristic ways.",
        "- Read the theme for a geometric principle: circuitry and punched "
        "records for computing, engraved hatching and stars for a revolution, "
        "round arcades for a medieval city, flowing contours for organic form, "
        "interference rings for quantum physics.",
        "- Let the story's date range steer the period feel of the geometry.",
        "",
        "PUNCTUATION MARKS (CRITICAL):",
        "- separator_glyph_svg is the story's text separator: it stands between "
        "two prose regions, before each subhead, and between the title and the "
        "years in the sticky header. Use a 32x32 viewBox.",
        "- Use maximum 2-3 simple geometric shapes for the separator glyph, "
        "non-directional and symmetrical where possible, and readable at 16px.",
        "- ornament_svg is the wider ornamental rule: the article's end mark, "
        "set centered under its last paragraph and nowhere else. Use a "
        "'0 0 240 24' viewBox, and design it to read at about 240x24 px.",
        "- Because it is centered, the ornament must be horizontally "
        "symmetric, and should combine a hairline rule running out to both "
        "edges with a small central motif derived from the same idea as the "
        "glyph.",
        "- Both marks are drawn in the primary color only; any fill or stroke "
        "you give them is replaced by it.",
        "- Do not surround the SVG strings with backticks or additional JSON "
        "structures.",
        (
            "- frame is how every box in the story is cut — the narration "
            "cards over the graph and the map, the chapter header on the "
            "timeline, the tooltips, the figures, the closing cast cards. "
            "Choose the one whose geometry the theme would itself have "
            "produced, exactly one of: "
            + ", ".join(f"{name} ({note})" for name, note in FRAME_CHOICES.items())
            + "."
        ),
        (
            "- heading_font must be exactly one of: "
            + ", ".join(HEADING_FONT_CHOICES)
            + ". Choose whichever best reflects the theme's period and tone."
        ),
        (
            "- body_font must be exactly one of: "
            + ", ".join(BODY_FONT_CHOICES)
            + ". This is a long read, so choose a font that stays comfortable "
            "over several thousand words and pairs well with the heading_font."
        ),
    ]
    details.append(f"Meta story identifier: {story_id}")
    if context:
        details.append("Context data:")
        details.append(json.dumps(context, ensure_ascii=False, indent=2))
    return "\n".join(details)


def call_openai(prompt: str, model: str) -> Dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY environment variable is not set.")
    client = OpenAI(api_key=api_key)
    system = (
        "You are a senior brand designer specializing in editorial data "
        "storytelling interfaces. "
        "You respond with strict JSON that adheres to the provided schema. "
        "IMPORTANT: All output text must be in American English only, "
        "regardless of the source language."
    )
    try:
        response = client.responses.create(
            model=model,
            reasoning=cast(Any, {"effort": BULK_REASONING_EFFORT}),
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            text={"format": {"type": "json_object"}},
        )
        usage.record_response(model, response, label="meta story style")
    except APIStatusError as error:
        message = getattr(
            getattr(error, "response", {}), "text", str(error)
        )  # type: ignore[attr-defined]
        raise RuntimeError(
            "OpenAI API request failed. Check your API key, model access, and "
            f"billing status. Details: {getattr(error, 'status_code', 'unknown')} {message}"
        ) from error

    if response.status == "failed":
        error_msg = (
            f"Response generation failed: {response.error}"
            if response.error
            else "Unknown error"
        )
        raise RuntimeError(error_msg)
    elif response.status != "completed":
        raise RuntimeError(f"Response has unexpected status: {response.status}")

    content = response.output_text
    if not content:
        raise RuntimeError("OpenAI API returned an empty response.")
    return cast(Dict[str, Any], json.loads(content))


def normalize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Response payload must be a JSON object.")
    primary = payload.get("primary")
    secondary = payload.get("secondary")
    background = payload.get("background")
    pattern_svg = payload.get("background_pattern_svg")
    separator_svg = payload.get("separator_glyph_svg")
    ornament_svg = payload.get("ornament_svg")
    frame = payload.get("frame")
    heading_font = payload.get("heading_font")
    body_font = payload.get("body_font")

    if not is_hex_color(primary):
        raise ValueError("primary must be a #RRGGBB hex color.")
    if not is_hex_color(secondary):
        raise ValueError("secondary must be a #RRGGBB hex color.")
    if not is_hex_color(background):
        raise ValueError("background must be a #RRGGBB hex color.")
    if not isinstance(pattern_svg, str) or "<svg" not in pattern_svg:
        raise ValueError(
            "background_pattern_svg must be an SVG string containing '<svg'."
        )
    if not isinstance(separator_svg, str) or "<svg" not in separator_svg:
        raise ValueError("separator_glyph_svg must be an SVG string containing '<svg'.")
    if not isinstance(ornament_svg, str) or "<svg" not in ornament_svg:
        raise ValueError("ornament_svg must be an SVG string containing '<svg'.")
    if not isinstance(frame, str) or frame.strip() not in FRAME_CHOICES:
        raise ValueError("frame must be one of: " + ", ".join(FRAME_CHOICES))
    if (
        not isinstance(heading_font, str)
        or heading_font.strip() not in HEADING_FONT_CHOICES
    ):
        raise ValueError(
            "heading_font must be one of: " + ", ".join(HEADING_FONT_CHOICES)
        )
    if not isinstance(body_font, str) or body_font.strip() not in BODY_FONT_CHOICES:
        raise ValueError("body_font must be one of: " + ", ".join(BODY_FONT_CHOICES))

    return {
        "primary": primary.upper(),
        "secondary": secondary.upper(),
        "background": background.upper(),
        "background_pattern_svg": sanitise_pattern_svg(pattern_svg),
        "separator_glyph_svg": sanitise_separator_glyph_svg(
            separator_svg, primary.upper()
        ),
        "ornament_svg": sanitise_separator_glyph_svg(
            ornament_svg, primary.upper(), default_view_box=ORNAMENT_VIEW_BOX
        ),
        "frame": frame.strip(),
        "heading_font": heading_font.strip(),
        "body_font": body_font.strip(),
    }


def load_styles() -> Dict[str, Any]:
    if STYLES_PATH.exists():
        try:
            data = json.loads(STYLES_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    else:
        data = {}
    if not isinstance(data, dict):
        data = {}
    styles = data.get("styles")
    if not isinstance(styles, dict):
        styles = {}
    data["styles"] = styles
    return data


def write_styles(data: Dict[str, Any]) -> None:
    STYLES_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_json(STYLES_PATH, data)


def generate_style(
    story_id: str,
    *,
    model: str = BULK_MODEL,
    dry_run: bool = False,
    verbose: bool = False,
) -> Dict[str, Any]:
    print(f"[Step 1/4] Loading context for meta story '{story_id}'...")
    context = load_story_context(story_id)
    if verbose:
        print(f"[Step 1/4] Context fields: {', '.join(context.keys())}")

    print("[Step 2/4] Building style generation prompt...")
    prompt = build_prompt(story_id, context)

    print(
        f"[Step 3/4] Generating visual identity via {model} "
        f"(reasoning: {BULK_REASONING_EFFORT})..."
    )
    payload = call_openai(prompt, model)

    style_config = normalize_payload(payload)
    print(
        f"[Step 3/4] Colors: primary={style_config['primary']}, "
        f"secondary={style_config['secondary']}, "
        f"background={style_config['background']}"
    )
    print(
        f"[Step 3/4] Fonts: heading={style_config['heading_font']}, "
        f"body={style_config['body_font']}"
    )
    print(f"[Step 3/4] Frame: {style_config['frame']}")

    if dry_run:
        print("[Step 4/4] Dry run mode - skipping file write")
        return {"id": story_id, **style_config}

    print(f"[Step 4/4] Writing style configuration to {STYLES_PATH}...")
    data = load_styles()
    data["styles"][story_id] = style_config
    write_styles(data)
    print(f"[Step 4/4] Style generation complete for '{story_id}'")
    return {"id": story_id, **style_config}


def parse_args(argv: Any) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a meta story's dark-mode styling configuration using the "
            "OpenAI API."
        )
    )
    parser.add_argument(
        "story_id",
        help="Meta story id, e.g. 'computing_pioneers'.",
    )
    parser.add_argument(
        "--model",
        default=BULK_MODEL,
        help=(
            f"OpenAI model to use (defaults to OPENAI_BULK_MODEL env or '{BULK_MODEL}'). "
            "See https://platform.openai.com/docs/models for available options."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the generated configuration without updating meta_story_styles.json.",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    return parser.parse_args(argv)


def main(argv: Any = None) -> int:
    args = parse_args(argv)

    print(f"Generating visual style for meta story: {args.story_id}")
    print(f"Model: {args.model}")
    print(f"Reasoning effort: {BULK_REASONING_EFFORT}")
    print()

    try:
        result = generate_style(
            args.story_id,
            model=args.model,
            dry_run=args.dry_run,
            verbose=args.verbose,
        )
    except Exception as error:
        print(f"\nError: {error}", file=sys.stderr)
        return 1

    print()
    if args.dry_run:
        print("=== Generated Style Configuration (Dry Run) ===")
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"✓ Style successfully generated and saved to {STYLES_PATH}")
        print(f"  Meta story ID: {result['id']}")
        print(f"  View at: /meta/{result['id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
