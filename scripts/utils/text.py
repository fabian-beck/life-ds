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
