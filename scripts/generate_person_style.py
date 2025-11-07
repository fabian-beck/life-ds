#!/usr/bin/env python3
"""Generate dark-mode visual styling for a person using the OpenAI API."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict

from openai import APIStatusError, OpenAI

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
PEOPLE_DIR = DATA_DIR / "people"
STYLES_PATH = DATA_DIR / "person_styles.json"
REGISTER_PATH = DATA_DIR / "persons.json"
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-5")


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.strip().lower())
    return slug.strip("_") or "person"


def is_hex_color(value: Any) -> bool:
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
    parts: list[str] = []
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


def load_dataset_context(person_id: str) -> Dict[str, Any]:
    context: Dict[str, Any] = {}
    dataset_path = PEOPLE_DIR / f"{person_id}_life_events.json"
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
        "Return a JSON object with fields: primary, secondary, background, background_pattern_svg, pattern_opacity.",
        "Rules:",
        "- primary, secondary, and background must be hex colors in #RRGGBB format.",
        "- background must remain dark (perceived luminance under 0.18).",
        "- primary and secondary should contrast well against the background and with each other.",
        "- background_pattern_svg must be a 160x160 tileable SVG string that uses only black (#000000) and white (#FFFFFF) with optional opacity attributes.",
        "- Keep the SVG minimal, geometric, and suitable as a subtle texture when blended softly over the background.",
        "- Avoid gradients or colors beyond black and white in the SVG.",
        "- pattern_opacity should be a float between 0.08 and 0.35 representing how strong the pattern should appear when overlaid.",
        "- Do not surround the SVG string with backticks or additional JSON structures.",
    ]
    details.append(
        f"Subject identifier: {person_id}\nRequested subject: {subject}")
    if context:
        details.append("Context data:")
        details.append(json.dumps(context, ensure_ascii=True, indent=2))
    return "\n".join(details)


def call_openai(prompt: str, model: str) -> Dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY environment variable is not set.")
    client = OpenAI(api_key=api_key)
    system = (
        "You are a senior brand designer specialising in data storytelling interfaces. "
        "You respond with strict JSON that adheres to the provided schema."
    )
    request: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
    }
    try:
        response = client.chat.completions.create(**request)
    except APIStatusError as error:
        message = getattr(getattr(error, "response", {}),
                          "text", str(error))  # type: ignore[attr-defined]
        raise RuntimeError(
            "OpenAI API request failed. Check your API key, model access, and billing status. "
            f"Details: {getattr(error, 'status_code', 'unknown')} {message}"
        ) from error
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("OpenAI API returned an empty response.")
    return json.loads(content)


def normalise_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Response payload must be a JSON object.")
    primary = payload.get("primary")
    secondary = payload.get("secondary")
    background = payload.get("background")
    pattern_svg = payload.get("background_pattern_svg")
    pattern_opacity = payload.get("pattern_opacity")

    if not is_hex_color(primary):
        raise ValueError("primary must be a #RRGGBB hex color.")
    if not is_hex_color(secondary):
        raise ValueError("secondary must be a #RRGGBB hex color.")
    if not is_hex_color(background):
        raise ValueError("background must be a #RRGGBB hex color.")
    if not isinstance(pattern_svg, str) or "<svg" not in pattern_svg:
        raise ValueError(
            "background_pattern_svg must be an SVG string containing '<svg'.")

    opacity = 0.18
    if isinstance(pattern_opacity, (int, float)):
        opacity = float(pattern_opacity)
    opacity = round(clamp(opacity, 0.08, 0.35), 3)

    compact = compact_svg(pattern_svg)
    return {
        "primary": primary.upper(),
        "secondary": secondary.upper(),
        "background": background.upper(),
        "background_pattern_svg": compact,
        "pattern_opacity": opacity,
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
    STYLES_PATH.write_text(json.dumps(
        data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def generate_style(subject: str, *, person_id: str | None = None, model: str = DEFAULT_MODEL, dry_run: bool = False) -> Dict[str, Any]:
    identifier = person_id or slugify(subject)
    context = load_dataset_context(identifier)
    prompt = build_prompt(subject, identifier, context)
    payload = call_openai(prompt, model)
    style_config = normalise_payload(payload)

    if dry_run:
        return {"id": identifier, **style_config}

    data = load_styles()
    data["styles"][identifier] = style_config
    write_styles(data)
    return {"id": identifier, **style_config}


def parse_args(argv: Any) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a personalised dark-mode styling configuration using the OpenAI API.")
    parser.add_argument(
        "subject", help="Name or description of the person, e.g. 'Ada Lovelace'.")
    parser.add_argument("--id", dest="person_id",
                        help="Optional slug or identifier to use instead of auto-slugifying the subject.")
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=(
            "OpenAI model to use (defaults to OPENAI_MODEL env or 'gpt-5'). "
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
    try:
        result = generate_style(
            args.subject,
            person_id=args.person_id,
            model=args.model,
            dry_run=args.dry_run,
        )
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    if args.dry_run:
        print(json.dumps(result, indent=2, ensure_ascii=True))
    else:
        print(
            f"Styling generated for '{result['id']}' and written to {STYLES_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
