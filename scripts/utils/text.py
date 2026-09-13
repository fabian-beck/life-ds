#!/usr/bin/env python3
"""Shared text helpers for the generation scripts."""

from __future__ import annotations

import re
from typing import Any


def slugify(
    value: str, *, drop_parenthetical: bool = False, empty: str = "person"
) -> str:
    """The canonical ASCII identifier for a person or story name.

    This is the algorithm that produced the directory names on disk — runs of
    anything outside ``[a-z0-9]`` become one underscore, so "Antoni Gaudí" is
    ``antoni_gaud``. Six per-script copies of it had grown apart: one variant
    kept non-ASCII letters and would have looked for ``antoni_gaudí`` in a
    registry that says ``antoni_gaud``. Every id derivation goes through here
    so the scripts cannot disagree about where a person lives.

    ``drop_parenthetical`` cuts a trailing parenthetical before slugging — for
    meta-story titles and registry lookups by display name, where "(1908)" or
    "(née Smolla)" is commentary rather than identity.
    """
    if drop_parenthetical:
        value = value.split("(")[0]
    slug = re.sub(r"[^a-z0-9]+", "_", value.strip().lower())
    return slug.strip("_") or empty


def fix_control_characters(text: str) -> str:
    """Replace ASCII control characters with the typographic characters meant.

    The OpenAI API sometimes returns control characters instead of proper
    Unicode punctuation. This is a correctness rule about model output, not a
    per-script convenience — two scripts carried identical copies, and this is
    the copy most likely to be extended in one file and not the other, so it
    lives here once.

    - ``\\x14`` (DC4) should be — (em dash, U+2014)
    - ``\\x19`` (EM) should be ' (right single quotation mark, U+2019)
    - ``\\x1c`` (FS) should be " (left double quotation mark, U+201C)
    - ``\\x1d`` (GS) should be " (right double quotation mark, U+201D)
    - ``\\x13`` (DC3) should be – (en dash, U+2013)
    """
    if not isinstance(text, str):
        return text

    replacements = {
        "\x14": "—",  # DC4 → em dash (—)
        "\x19": "’",  # EM → right single quotation mark (')
        "\x1c": "“",  # FS → left double quotation mark (")
        "\x1d": "”",  # GS → right double quotation mark (")
        "\x13": "–",  # DC3 → en dash (–)
    }

    for bad_char, good_char in replacements.items():
        if bad_char in text:
            text = text.replace(bad_char, good_char)

    # A character past Latin-1 can also come back as its high byte, a control
    # character, followed by its low byte spelled as two hex digits: "\x01"
    # and "07" where "ć" (U+0107) belongs.
    text = _CONTROL_HIGH_BYTE.sub(
        lambda match: chr(ord(match.group(1)) * 256 + int(match.group(2), 16)), text
    )
    # Any control character still left shows the reader nothing.
    return _CONTROL.sub("", text)


_CONTROL_HIGH_BYTE = re.compile(r"([\x01-\x08\x0b\x0c\x0e-\x1f])([0-9a-fA-F]{2})")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Emphasis opens on a star that follows no word character and closes on one
# that precedes none, so a star inside a Commons file name ("Mk1*") or before a
# space ("* EM3880") is text, not Markdown.
_BOLD = re.compile(r"(?<![\w*])\*\*([^\s*](?:[^*\n]*[^\s*])?)\*\*(?![\w*])")
_EMPHASIS = re.compile(r"(?<![\w*])\*([^\s*](?:[^*\n]*[^\s*])?)\*(?![\w*])")
_CODE = re.compile(r"`([^`\n]+)`")
_LINK = re.compile(r"\[([^\[\]\n]+)\]\((?:https?://|/)[^)\s]*\)")
_HEADING = re.compile(r"^#{1,6}[ \t]+", re.MULTILINE)


def strip_markdown(text: str, key: str = "") -> str:
    """Unwrap the Markdown a model writes into text the interface shows verbatim.

    The interface reads two pieces of markup: ``[[term|display]]`` annotation
    markers and ``## `` headings inside a ``background`` report. Emphasis,
    bold, code spans, and links arrive anyway — the generator around a work's
    title, the translator adding emphasis the English never had — and would
    reach the slide as literal asterisks. Each keeps its text and loses its
    markup; a heading line outside a background keeps its words. A URL is left
    as it is.
    """
    if not isinstance(text, str) or text.startswith(("http://", "https://")):
        return text
    for pattern in (_BOLD, _EMPHASIS, _CODE, _LINK):
        text = pattern.sub(r"\1", text)
    if key != "background":
        text = _HEADING.sub("", text)
    return text


def clean_strings(value: Any, key: str = "") -> Any:
    """Repair control characters and unwrap Markdown in every string of a document.

    ``key`` is the field a string sits in, which is what decides whether a
    heading line is markup the interface reads.
    """
    if isinstance(value, str):
        return strip_markdown(fix_control_characters(value), key)
    if isinstance(value, dict):
        return {
            child_key: clean_strings(child, child_key)
            for child_key, child in value.items()
        }
    if isinstance(value, list):
        return [clean_strings(item, key) for item in value]
    return value
