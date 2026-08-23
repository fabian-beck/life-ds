#!/usr/bin/env python3
"""Shared text helpers for the generation scripts."""

from __future__ import annotations

import re


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

    return text
