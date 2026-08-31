#!/usr/bin/env python3
"""Generate dark-mode visual styling for a person using the OpenAI API."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, TypeGuard, cast
from xml.etree import ElementTree as ET

from openai import APIStatusError, OpenAI

from config import BULK_MODEL, BULK_REASONING_EFFORT, enable_utf8_console
from utils import usage
from utils.text import slugify

enable_utf8_console()

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
PEOPLE_DIR = DATA_DIR / "people"
STYLES_PATH = DATA_DIR / "person_styles.json"
REGISTER_PATH = DATA_DIR / "persons.json"
HEADING_FONT_CHOICES = [
    "Playfair Display",
    "DM Serif Display",
    "Space Grotesk",
    "IBM Plex Sans",
    "Unbounded",
    "Archivo Black",
]

BODY_FONT_CHOICES = [
    "Lora",
    "Source Serif 4",
    "Inter",
    "IBM Plex Sans",
    "DM Sans",
    "Manrope",
]


def is_hex_color(value: Any) -> TypeGuard[str]:
    """True if value is a "#RRGGBB" string.

    Declared as a TypeGuard because callers rely on it to narrow: they pull
    values out of an untyped payload and reject anything this returns False
    for, after which the value is known to be a str.
    """
    if not isinstance(value, str):
        return False
    return bool(re.fullmatch(r"#[0-9a-fA-F]{6}", value.strip()))


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def compact_svg(svg: str) -> str:
    """Minify SVG markup while preserving necessary spacing."""
    if not svg:
        return ""
    # Normalize whitespace outside of quoted attributes.
    buffer: list[str] = []
    in_quote = False
    quote_char = ""
    for char in svg:
        if in_quote:
            buffer.append(char)
            if char == quote_char:
                in_quote = False
                quote_char = ""
            continue
        if char in {'"', "'"}:
            if buffer and buffer[-1].isspace():
                buffer[-1] = " "
            buffer.append(char)
            in_quote = True
            quote_char = char
            continue
        if char.isspace():
            if buffer and not buffer[-1].isspace():
                buffer.append(" ")
            continue
        buffer.append(char)
    compact = "".join(buffer).strip()
    return re.sub(r"\s+", " ", compact)


def strip_namespace(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def normalize_bw_color(
    value: str | None, *, allow_none: bool = False, warn: bool = False
) -> str | None:
    if value is None:
        return None
    lowered = value.strip().lower()
    if not lowered:
        return None
    if allow_none and lowered in {"none", "transparent"}:
        return "none"
    if lowered in {"#fff", "#ffffff", "white"}:
        return "#FFFFFF"
    if lowered in {"#000", "#000000", "black"}:
        return "#000000"
    rgb_match = re.fullmatch(
        r"rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})(?:\s*,\s*(0|0?\.\d+|1))?\s*\)",
        lowered,
    )
    if rgb_match:
        r, g, b = (int(channel) for channel in rgb_match.groups()[:3])
        avg = (r + g + b) / 3
        normalized = "#FFFFFF" if avg >= 128 else "#000000"
        if warn:
            print(f"Warning: Color {value} normalized to {normalized}", file=sys.stderr)
        return normalized
    # Try to parse hex colors (including grays)
    hex_match = re.fullmatch(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})", value.strip())
    if hex_match:
        hex_val = hex_match.group(1)
        if len(hex_val) == 3:
            hex_val = "".join(c * 2 for c in hex_val)
        r, g, b = int(hex_val[0:2], 16), int(hex_val[2:4], 16), int(hex_val[4:6], 16)
        avg = (r + g + b) / 3
        normalized = "#FFFFFF" if avg >= 128 else "#000000"
        if warn:
            print(f"Warning: Color {value} normalized to {normalized}", file=sys.stderr)
        return normalized
    return None


def parse_style_attribute(value: str) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for part in value.split(";"):
        if not part.strip():
            continue
        if ":" not in part:
            continue
        prop, val = part.split(":", 1)
        result[prop.strip()] = val.strip()
    return result


def sanitise_pattern_svg(svg: str) -> str:
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as exc:
        raise ValueError(f"background_pattern_svg must be valid SVG: {exc}") from exc

    if strip_namespace(root.tag) != "svg":
        raise ValueError("background_pattern_svg must have an <svg> root element.")

    root.set("xmlns", root.attrib.get("xmlns", "http://www.w3.org/2000/svg"))
    root.set("width", "160")
    root.set("height", "160")
    root.set("viewBox", "0 0 160 160")

    background_present = False
    white_element_present = False

    for element in root.iter():
        tag = strip_namespace(element.tag)
        # Promote inline style declarations to attributes for easier validation.
        style_value = element.attrib.get("style")
        if style_value:
            for key, val in parse_style_attribute(style_value).items():
                element.set(key, val)
            element.attrib.pop("style", None)

        if tag == "rect":
            width = element.attrib.get("width", "160")
            height = element.attrib.get("height", "160")
            x = element.attrib.get("x", "0")
            y = element.attrib.get("y", "0")
            fill = normalize_bw_color(element.attrib.get("fill"), allow_none=True)
            if (
                fill == "#000000"
                and x in {"0", "0.0"}
                and y in {"0", "0.0"}
                and width in {"160", "160.0"}
                and height in {"160", "160.0"}
            ):
                background_present = True
            if fill is not None:
                element.set("fill", fill)

        for attr in list(element.attrib.keys()):
            lowered = attr.lower()
            value_text = element.attrib[attr]
            if lowered in {"fill", "stroke"}:
                allow_none = lowered == "fill"
                color = normalize_bw_color(value_text, allow_none=allow_none, warn=True)
                if color is None:
                    raise ValueError(
                        f"SVG {attr} must use only black (#000000), white (#FFFFFF), or none. Got: {value_text}"
                    )
                element.set(attr, color)
                if color == "#FFFFFF":
                    white_element_present = True
            elif lowered in {"fill-opacity", "stroke-opacity", "opacity"}:
                # Remove opacity attributes - opacity will be controlled globally
                element.attrib.pop(attr, None)
            # Allow other SVG presentation attributes (geometry, linecap, linejoin, etc.)
            # These don't affect color validation

        if element.attrib.get("stroke", "").upper() == "#FFFFFF":
            white_element_present = True
        if element.attrib.get("fill", "").upper() == "#FFFFFF":
            white_element_present = True

    if not background_present:
        background_rect = ET.Element(
            "rect",
            {
                "width": "160",
                "height": "160",
                "fill": "#000000",
            },
        )
        root.insert(0, background_rect)

    if not white_element_present:
        raise ValueError(
            "Pattern must include at least one white stroke or fill element for contrast."
        )

    sanitised = ET.tostring(root, encoding="unicode")
    # Remove namespace prefixes for cleaner output
    sanitised = re.sub(r"\bns\d+:", "", sanitised)
    sanitised = re.sub(r'\s+xmlns:ns\d+="[^"]*"', "", sanitised)
    return compact_svg(sanitised)


def sanitise_separator_glyph_svg(
    svg: str, primary_color: str, *, default_view_box: str = "0 0 32 32"
) -> str:
    """Sanitise and normalize separator glyph SVG, replacing color placeholders with the actual primary color.

    `default_view_box` only fills in a missing one; a wider mark—the meta
    story's ornamental rule—declares its own.
    """
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as exc:
        raise ValueError(f"separator_glyph_svg must be valid SVG: {exc}") from exc

    if strip_namespace(root.tag) != "svg":
        raise ValueError("separator_glyph_svg must have an <svg> root element.")

    root.set("xmlns", root.attrib.get("xmlns", "http://www.w3.org/2000/svg"))

    # Normalize viewBox if not present
    if "viewBox" not in root.attrib:
        root.set("viewBox", default_view_box)

    for element in root.iter():
        # Promote inline style declarations to attributes
        style_value = element.attrib.get("style")
        if style_value:
            for key, val in parse_style_attribute(style_value).items():
                element.set(key, val)
            element.attrib.pop("style", None)

        # Replace any color with the primary color
        for attr in list(element.attrib.keys()):
            lowered = attr.lower()
            value_text = element.attrib[attr]
            if lowered in {"fill", "stroke"}:
                # Accept any color and replace with primary
                if value_text.lower() not in {"none", "transparent"}:
                    element.set(attr, primary_color)
            elif lowered in {"fill-opacity", "stroke-opacity", "opacity"}:
                # Remove opacity attributes - will be controlled by CSS
                element.attrib.pop(attr, None)

    sanitised = ET.tostring(root, encoding="unicode")
    # Remove namespace prefixes for cleaner output
    sanitised = re.sub(r"\bns\d+:", "", sanitised)
    sanitised = re.sub(r'\s+xmlns:ns\d+="[^"]*"', "", sanitised)
    return compact_svg(sanitised)


def load_dataset_context(person_id: str) -> Dict[str, Any]:
    context: Dict[str, Any] = {}
    # Updated to use subdirectory structure
    person_dir = PEOPLE_DIR / person_id
    dataset_path = person_dir / "life_events.json"
    if dataset_path.exists():
        try:
            dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            dataset = {}
        person = dataset.get("person", {}) if isinstance(dataset, dict) else {}
        events = dataset.get("events", []) if isinstance(dataset, dict) else []
        if isinstance(person, dict):
            context["person"] = {
                key: person.get(key)
                for key in (
                    "name",
                    "summary",
                    "primary_roles",
                    "birth_date",
                    "death_date",
                    "wikipedia",
                )
                if person.get(key)
            }
        if isinstance(events, list) and events:
            highlights = []
            for event in events[:5]:
                if not isinstance(event, dict):
                    continue
                highlights.append(
                    {
                        key: event.get(key)
                        for key in ("title", "date", "description")
                        if event.get(key)
                    }
                )
            if highlights:
                context["event_samples"] = highlights
    elif REGISTER_PATH.exists():
        try:
            register = json.loads(REGISTER_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            register = {}
        if isinstance(register, dict):
            for entry in register.get("people", []) or []:
                if not isinstance(entry, dict):
                    continue
                if entry.get("id") == person_id:
                    context["person"] = {
                        key: entry.get(key)
                        for key in ("name", "summary", "wikipedia")
                        if entry.get(key)
                    }
                    break
    return context


def build_prompt(subject: str, person_id: str, context: Dict[str, Any]) -> str:
    details: list[str] = [
        "Design a cohesive dark-mode visual identity for the following person.",
        "Return a JSON object with fields: primary, secondary, background, background_pattern_svg, separator_glyph_svg, heading_font, body_font.",
        "Rules:",
        "- primary, secondary, and background must be hex colors in #RRGGBB format.",
        "- background must remain dark (perceived luminance under 0.18).",
        "- primary and secondary should contrast well against the background and with each other.",
        "- background_pattern_svg must be a 160x160 tileable SVG string that uses ONLY pure black (#000000) and pure white (#FFFFFF).",
        "- CRITICAL: NO gray shades allowed—only #000000 (black) and #FFFFFF (white). No #111111, #EEEEEE, or any other color values.",
        "- Do NOT use opacity, fill-opacity, or stroke-opacity attributes in the SVG. Use stroke-width variations instead for visual hierarchy.",
        "- The pattern should be highly stylized and work as a tiled background, smoothly repeating.",
        "- Strong strokes are favored over thin lines for better visual impact.",
        "- Create visual hierarchy through stroke-width variation (e.g., 1px, 2px, 4px, 8px) rather than color or opacity.",
        "",
        "PATTERN DESIGN PRINCIPLES (CRITICAL):",
        "- Create a DISTINCTIVE geometric pattern that immediately evokes this person's unique character, era, and contributions.",
        "- ALL PATTERNS MUST BE ABSTRACT AND GEOMETRIC—no figurative or representational elements.",
        "- Use geometric primitives (circles, lines, rectangles, triangles, arcs, grids) arranged in characteristic ways.",
        "- Study the person's work to extract geometric principles: symmetry vs asymmetry, order vs chaos, density vs sparseness, rigid vs flowing.",
        "- Consider the person's era through geometric style: Art Deco angles for 1920s-30s, Bauhaus grids for modernists, circuit-like patterns for digital pioneers, ornate tessellations for Victorian era.",
        "- Vary pattern complexity based on personality: minimalists get sparse clean geometry, complex thinkers get intricate tessellations, revolutionaries get dynamic asymmetric compositions.",
        "- Use geometric rhythm and density to reflect their work style: precise regular grids for systematic thinkers, flowing curves for humanists, recursive patterns for mathematicians, modular repetition for engineers.",
        "- Avoid generic/bland geometric patterns—even simple geometry should have a distinctive arrangement or rhythm.",
        "- The geometric composition should encode their personality: tight control vs expressive freedom, mathematical precision vs artistic flow, traditional symmetry vs modern disruption.",
        "",
        "EXAMPLES OF DISTINCTIVE GEOMETRIC PATTERNS:",
        "- Alan Turing: Binary-like grid patterns with computational rhythm, circuit board geometry with logical pathways, systematic rectangular grids with deliberate breaks suggesting computation.",
        "- Ada Lovelace: Interwoven curved lines forming loop-like structures, Victorian geometric ornament with mathematical precision, concentric patterns suggesting iterative algorithms.",
        "- Leonardo da Vinci: Golden ratio spiral grids, geometric constructions with circular and angular intersections, precise drafting-style line work.",
        "- Marie Curie: Concentric circles suggesting atomic orbitals, radiating line patterns, crystalline angular grids, geometric wave forms.",
        "- Frida Kahlo: Bold geometric shapes with strong bilateral symmetry, angular Art Deco-influenced patterns, geometric florals abstracted to pure form.",
        "- Steve Jobs: Extreme minimalism—single rounded rectangles with precise spacing, zen-like asymmetric grids with generous negative space, clean lines with subtle golden ratio proportions.",
        "- Virginia Woolf: Flowing parallel curves suggesting streams, modernist geometric abstraction, delicate linear patterns with rhythmic variation.",
        "- Albert Einstein: Curved geometric grids suggesting spacetime, wave-like patterns, mathematical curve tessellations, asymmetric but balanced compositions.",
        "- Johann Sebastian Bach: Geometric counterpoint—interwoven line patterns, symmetrical but complex geometric fugue-like arrangements, precise mathematical grids.",
        "",
        "- Avoid gradients or colors beyond black and white in the SVG.",
        "- separator_glyph_svg must be a simple, distinctive glyph designed to work at small sizes (32x32 recommended viewBox).",
        "- The separator glyph should use the primary color as fill/stroke and be characteristic of the person's aesthetic.",
        "- IMPORTANT: Use maximum 2-3 simple geometric shapes (circles, rectangles, lines, triangles) for the separator glyph.",
        "- As a separator glyph, it should be non-directional (no arrows or pointing shapes) and symmetrical when possible.",
        "- Keep the separator glyph simple—it should be recognizable and readable even at 16-24px display size.",
        "- The separator glyph should complement the background pattern and overall visual identity.",
        "- Do not surround the SVG strings with backticks or additional JSON structures.",
        (
            "- heading_font must be exactly one of: "
            + ", ".join(HEADING_FONT_CHOICES)
            + ". Choose whichever best reflects the person's tone (e.g., elegant serif for historical figures, geometric sans for scientists)."
        ),
        (
            "- body_font must be exactly one of: "
            + ", ".join(BODY_FONT_CHOICES)
            + ". Choose a readable font that pairs well with the heading_font and suits the content tone."
        ),
    ]
    details.append(f"Subject identifier: {person_id}\nRequested subject: {subject}")
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
        "You are a senior brand designer specializing in data storytelling interfaces. "
        "You respond with strict JSON that adheres to the provided schema. "
        "IMPORTANT: All output text must be in American English only, regardless of the source language."
    )
    try:
        # The Responses API, so the configured model can be given a reasoning
        # effort. Which model that is comes from `config.py`, never from here.
        response = client.responses.create(
            model=model,
            reasoning=cast(Any, {"effort": BULK_REASONING_EFFORT}),
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            text={"format": {"type": "json_object"}},
        )
        usage.record_response(model, response, label="interface style")
    except APIStatusError as error:
        message = getattr(
            getattr(error, "response", {}), "text", str(error)
        )  # type: ignore[attr-defined]
        raise RuntimeError(
            "OpenAI API request failed. Check your API key, model access, and billing status. "
            f"Details: {getattr(error, 'status_code', 'unknown')} {message}"
        ) from error

    # Handle different response statuses
    if response.status == "failed":
        error_msg = (
            f"Response generation failed: {response.error}"
            if response.error
            else "Unknown error"
        )
        raise RuntimeError(error_msg)
    elif response.status != "completed":
        raise RuntimeError(f"Response has unexpected status: {response.status}")

    # Extract content from the response
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
    if (
        not isinstance(heading_font, str)
        or heading_font.strip() not in HEADING_FONT_CHOICES
    ):
        raise ValueError(
            "heading_font must be one of: " + ", ".join(HEADING_FONT_CHOICES)
        )
    if not isinstance(body_font, str) or body_font.strip() not in BODY_FONT_CHOICES:
        raise ValueError("body_font must be one of: " + ", ".join(BODY_FONT_CHOICES))

    compact_pattern = sanitise_pattern_svg(pattern_svg)
    compact_separator = sanitise_separator_glyph_svg(separator_svg, primary.upper())

    return {
        "primary": primary.upper(),
        "secondary": secondary.upper(),
        "background": background.upper(),
        "background_pattern_svg": compact_pattern,
        "separator_glyph_svg": compact_separator,
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
    STYLES_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def generate_style(
    subject: str,
    *,
    person_id: str | None = None,
    model: str = BULK_MODEL,
    dry_run: bool = False,
) -> Dict[str, Any]:
    identifier = person_id or slugify(subject)

    print(f"[Step 1/5] Loading context for '{identifier}'...")
    context = load_dataset_context(identifier)
    if context:
        print(f"[Step 1/5] Found context: {', '.join(context.keys())}")
    else:
        print("[Step 1/5] No context found, proceeding with subject name only")

    print("[Step 2/5] Building style generation prompt...")
    prompt = build_prompt(subject, identifier, context)

    print(
        f"[Step 3/5] Generating visual identity via {model} (reasoning: {BULK_REASONING_EFFORT})..."
    )
    payload = call_openai(prompt, model)

    print("[Step 4/5] Validating and normalizing style configuration...")
    style_config = normalize_payload(payload)
    print(
        f"[Step 4/5] Colors: primary={style_config['primary']}, secondary={style_config['secondary']}, background={style_config['background']}"
    )
    print(
        f"[Step 4/5] Fonts: heading={style_config['heading_font']}, body={style_config['body_font']}"
    )
    print(
        f"[Step 4/5] Pattern SVG: {len(style_config['background_pattern_svg'])} chars"
    )
    print(f"[Step 4/5] Separator SVG: {len(style_config['separator_glyph_svg'])} chars")

    if dry_run:
        print("[Step 5/5] Dry run mode - skipping file write")
        return {"id": identifier, **style_config}

    print(f"[Step 5/5] Writing style configuration to {STYLES_PATH}...")
    data = load_styles()
    data["styles"][identifier] = style_config
    write_styles(data)
    print(f"[Step 5/5] Style generation complete for '{identifier}'")
    return {"id": identifier, **style_config}


def parse_args(argv: Any) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a personalised dark-mode styling configuration using the OpenAI API."
    )
    parser.add_argument(
        "subject",
        help="Name or description of the person, e.g. 'Ada Lovelace' or 'henry_II'.",
    )
    parser.add_argument(
        "--url",
        help="Wikipedia URL to use for disambiguation (e.g., 'https://en.wikipedia.org/wiki/Henry_II,_Holy_Roman_Emperor').",
    )
    parser.add_argument(
        "--id",
        dest="person_id",
        help="Optional slug or identifier to use instead of auto-slugifying the subject.",
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
        help="Print the generated configuration without updating person_styles.json.",
    )
    return parser.parse_args(argv)


def main(argv: Any = None) -> int:
    args = parse_args(argv)

    # When URL is provided, use it for fetching but preserve original subject as person_id
    if args.url:
        subject_for_fetch = args.url
        # If --id is provided, use it; otherwise slugify the subject
        person_id_override = args.person_id or slugify(args.subject)
    else:
        subject_for_fetch = args.subject
        person_id_override = args.person_id

    print(f"Generating visual style for: {args.subject}")
    print(f"Model: {args.model}")
    print(f"Reasoning effort: {BULK_REASONING_EFFORT}")
    print()

    try:
        result = generate_style(
            subject_for_fetch,
            person_id=person_id_override,
            model=args.model,
            dry_run=args.dry_run,
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
        print(f"  Person ID: {result['id']}")
        print(f"  View at: /story/{result['id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
