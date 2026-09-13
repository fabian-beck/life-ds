#!/usr/bin/env python3
"""Generate dark-mode visual styling for a person using the OpenAI API."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, cast
from xml.etree import ElementTree as ET

from openai import APIStatusError, OpenAI

from config import BULK_MODEL, BULK_REASONING_EFFORT, enable_utf8_console
from utils import usage
from utils.person_style import (
    MIN_TEXT_CONTRAST,
    STYLES_PATH,
    is_hex_color,
    palette_problems,
)
from utils.text import slugify

enable_utf8_console()

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
PEOPLE_DIR = DATA_DIR / "people"
REGISTER_PATH = DATA_DIR / "persons.json"
# Every family here is self-hosted by src/fonts.css, and
# tests/test_font_coverage.py keeps the two lists in step. The set spans
# registers on purpose — display and book serifs, geometric, neutral, and
# condensed sans, a slab, a monospace — so that the prompt can ask for the one
# that fits the person rather than have every story default to the same pair.
HEADING_FONT_CHOICES = [
    "Playfair Display",
    "DM Serif Display",
    "Libre Baskerville",
    "EB Garamond",
    "Zilla Slab",
    "Space Grotesk",
    "IBM Plex Sans",
    "Oswald",
    "Unbounded",
    "Archivo Black",
    "IBM Plex Mono",
]

BODY_FONT_CHOICES = [
    "Lora",
    "Source Serif 4",
    "EB Garamond",
    "Inter",
    "IBM Plex Sans",
    "Source Sans 3",
    "DM Sans",
    "Manrope",
]


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


LIFE_STAGE_EVENT_TYPES = {"birth", "death", "marriage_partnership", "migration"}
"""Event classes that place a life rather than show what its work looked like.

Every dataset opens with a birth and a schooling, so the first events in
chronological order are the same handful of childhood scenes for everyone. The
style step used to be shown exactly those, which is why the palette it returned
could not have been derived from the person: nothing in front of it was.
"""

WORK_EVENT_TYPES = {"publication", "invention"}
"""Event classes that name a made thing, the one a palette can be read off."""

STYLE_EVENT_SAMPLES = 6
"""How many events the style prompt carries. Enough for a working life, few
enough that the prompt stays about the palette rather than the biography."""


def visual_relevance(event: Dict[str, Any]) -> int:
    """How much an event can tell the style step about how this person's work looked.

    The images are the strongest evidence the dataset holds: an event that
    carries one carries its caption too, and those captions name the works
    themselves—"Frederick C. Robie House", "View of Taliesin from below". A
    life-stage event carries none of that however well it is written.
    """
    score = 2 if event.get("images") else 0
    event_class = event.get("event_class")
    event_type = event_class.get("type") if isinstance(event_class, dict) else None
    if event_type in WORK_EVENT_TYPES:
        score += 1
    elif event_type in LIFE_STAGE_EVENT_TYPES:
        score -= 2
    return score


def style_event_samples(events: list[Any]) -> list[Dict[str, Any]]:
    """The events the style prompt is shown, chosen for what they depict.

    Ranked by `visual_relevance` and returned in the order the life ran, so the
    prompt reads as a working life rather than a list of highlights. Ties keep
    chronological order, which makes the selection deterministic for a given
    dataset: the same person yields the same prompt on a rerun.
    """
    usable = [event for event in events if isinstance(event, dict)]
    ranked = sorted(
        range(len(usable)), key=lambda index: (-visual_relevance(usable[index]), index)
    )
    samples: list[Dict[str, Any]] = []
    for index in sorted(ranked[:STYLE_EVENT_SAMPLES]):
        event = usable[index]
        sample = {
            key: event.get(key)
            for key in ("title", "date", "description")
            if event.get(key)
        }
        captions = [
            image["caption"]
            for image in event.get("images") or []
            if isinstance(image, dict) and image.get("caption")
        ]
        if captions:
            sample["depicted"] = captions
        if sample:
            samples.append(sample)
    return samples


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
            highlights = style_event_samples(events)
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
        "Return a JSON object with fields: primary, secondary, background, palette_rationale, background_pattern_svg, separator_glyph_svg, heading_font, body_font.",
        "Rules:",
        "- primary, secondary, and background must be hex colors in #RRGGBB format.",
        "- background must remain dark (perceived luminance under 0.18). That is a ceiling, not a target: the range from near-black to a deep tinted ground is all available, and the ground may carry the same hue the person's work does.",
        "- primary and secondary are set as heading, label, and glyph colors directly on the background, so each must reach a WCAG contrast ratio of at least "
        + f"{MIN_TEXT_CONTRAST:g}:1 against it. A palette in which either falls under that is rejected and regenerated.",
        "- Clear the floor; do not race past it. A color pushed toward white to be safe has given up the hue that identifies the story, and a pale tint of a color is not that color. Aim for legible and saturated together.",
        "- primary and secondary must be distinguishable from each other; the story uses them for different roles.",
        "",
        "PALETTE DERIVATION (CRITICAL):",
        "- Derive primary and secondary from what this person made and lived among—the materials, pigments, surfaces, bindings, instruments, and light of their own work. The palette is evidence about them, not decoration around them.",
        "- Read the context below for that evidence. The event titles and descriptions name the works, and the `depicted` captions name what the story actually shows: a building, a first edition, a manuscript, an instrument, a room. Those are the things whose colors you are looking for.",
        "- When the person has a documented signature color, use it. Frank Lloyd Wright has Cherokee Red; Yves Klein has his blue; a designer, painter, or architect with a known palette gets that palette rather than an interpretation of it.",
        "- When the person left no visual record of their own—a mathematician, a physician, a civil servant, a soldier—read the palette off the material world their work sat in: the ink and rag paper of their century, the cloth or leather of a binding, the brass and glass of an instrument, the stone or tile of the place they worked, the dye of an academic gown, a flag, a uniform, a laboratory. Every life has surfaces even when it has no artworks.",
        "- Amber or gold against cyan or sky blue is where a dark interface goes when the palette is derived from nothing: it is the most legible pair on a near-black ground, which is a fact about screens and not about this person. Choose it only when this person's own work genuinely calls for it, and if you do, name that work in palette_rationale.",
        "- The two colors do not have to be complementary, and a palette need not be built from opposites at all: two colors drawn from the same object—a pigment and the ground it was laid on, a cover and its stamped lettering—often fit a person better than a color wheel does.",
        '- palette_rationale is one sentence naming the specific work, material, object, or place primary and secondary are taken from. Write it as evidence: "the ochre and slate of Fallingwater\'s sandstone and concrete", not "warm and cool tones evoking creativity". A rationale that would fit any other person means the palette has not yet been derived from this one—go back to the context and derive it.',
        "- background_pattern_svg must be a 160x160 tileable SVG string that uses ONLY pure black (#000000) and pure white (#FFFFFF).",
        "- The tile must be painted edge to edge over a black ground, with the marks in white. The story multiplies the tile against its primary color, so any part left transparent renders as a flat wash of that color instead of a pattern.",
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
        "",
        "CULTURAL GROUNDING:",
        "- A pattern for a figure outside the Western canon draws on the geometry of their own tradition, era, and work, never on a generic or stereotyped motif for their region.",
        "- Colors respect the associations of the person's culture, including those of mourning, celebration, and religion.",
        "- The font pairing suits the linguistic and regional context where the vocabulary allows it.",
        "",
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
            + ". The list spans registers: Playfair Display and DM Serif Display are high-contrast display serifs, Libre Baskerville a transitional book serif, EB Garamond an old-style serif, Zilla Slab a slab, Space Grotesk a geometric sans, IBM Plex Sans a neutral sans, Oswald a condensed grotesque, Unbounded a wide display sans, Archivo Black a heavy grotesque, and IBM Plex Mono a monospace."
            + " Choose the register that fits the person's era, field, and temperament — an old-style or book serif for figures before the industrial age, a slab or condensed face for the industrial and interwar decades, a monospace for computing, a geometric or wide sans for modernists — rather than defaulting to the same face for every story."
        ),
        (
            "- body_font must be exactly one of: "
            + ", ".join(BODY_FONT_CHOICES)
            + ". Lora, Source Serif 4, and EB Garamond are text serifs; Source Sans 3 is a humanist sans; Inter, IBM Plex Sans, DM Sans, and Manrope are neutral or geometric sans faces."
            + " Choose a readable font that pairs well with the heading_font and suits the content tone."
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


MIN_RATIONALE_WORDS = 6
"""A rationale shorter than this is a label, not a derivation.

The field exists to make the model commit to where the colors came from: a
sentence that has to name a work, a material, or a place cannot be written for
an amber and a cyan the model reached for out of habit. What the model names is
not something code can verify — the length is only a floor under the answer, and
the sentence is there for the person who later asks why a story looks like this.
"""


def normalize_rationale(value: Any) -> str:
    """The one sentence saying where the palette came from, or a rejection."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            "palette_rationale must be a sentence naming the work, material, "
            "or place primary and secondary are derived from."
        )
    rationale = " ".join(value.split())
    if len(rationale.split()) < MIN_RATIONALE_WORDS:
        raise ValueError(
            f"palette_rationale '{rationale}' is too short to name where the "
            "colors came from; write a sentence naming the specific work, "
            "material, object, or place."
        )
    return rationale


def normalize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Response payload must be a JSON object.")
    primary = payload.get("primary")
    secondary = payload.get("secondary")
    background = payload.get("background")
    rationale = payload.get("palette_rationale")
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
    # The prompt asks for readable text colors; this is where the ask is held.
    # The style review that used to follow the generator estimated contrast
    # by reading hex strings, which is not a check, and it is gone.
    problems = palette_problems(primary, secondary, background)
    if problems:
        raise ValueError(" ".join(problems))
    rationale = normalize_rationale(rationale)
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
        "palette_rationale": rationale,
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


STYLE_ATTEMPTS = 3
"""How many times the model may answer before a rejected palette fails the step.

Three rather than two since the palette has to arrive derived: an answer can now
miss the contrast floor or the derivation, and the retry that names one reason
should not be the last chance to satisfy the other."""


def build_retry_prompt(prompt: str, error: Exception) -> str:
    """The same prompt again, with the reason the last answer was rejected."""
    return (
        prompt
        + "\n\nA previous answer was rejected for this reason: "
        + str(error)
        + "\nReturn a corrected JSON object that satisfies every rule above."
    )


def generate_valid_style(prompt: str, model: str) -> Dict[str, Any]:
    """Call the model until `normalize_payload` accepts the answer, or give up.

    The palette and font rules in the prompt are also checked in code, and a
    small model at low effort sometimes misses one — a secondary too close to
    the background, a font outside the vocabulary. One more call that names
    the rejection is cheaper than a failed step, and far cheaper than a critic
    pass on the large model, which is what used to follow here.
    """
    attempt_prompt = prompt
    for attempt in range(1, STYLE_ATTEMPTS + 1):
        payload = call_openai(attempt_prompt, model)
        try:
            return normalize_payload(payload)
        except ValueError as error:
            if attempt == STYLE_ATTEMPTS:
                raise
            print(f"[Step 4/5] Rejected attempt {attempt}: {error}")
            attempt_prompt = build_retry_prompt(prompt, error)
    raise AssertionError("unreachable")


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
    print("[Step 4/5] Validating and normalizing style configuration...")
    style_config = generate_valid_style(prompt, model)
    print(
        f"[Step 4/5] Colors: primary={style_config['primary']}, secondary={style_config['secondary']}, background={style_config['background']}"
    )
    print(f"[Step 4/5] Palette derived from: {style_config['palette_rationale']}")
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
