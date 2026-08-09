#!/usr/bin/env python3
"""Locate person datasets and their translated copies.

The backfill and validation scripts all iterate the same corpus: every person
directory that carries a ``life_events.json``, and for writers, that file plus
each translated copy under ``data/people/{person_id}/{lang}/``. These lookups
were copy-pasted per script; this is their one home.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from config import PEOPLE_DIR


def person_ids() -> List[str]:
    """Every person with a generated dataset, in stable order."""
    return sorted(
        p.name for p in PEOPLE_DIR.iterdir() if (p / "life_events.json").exists()
    )


def event_files(person_id: str) -> List[Path]:
    """The English life events file plus every translated copy."""
    files = []
    english = PEOPLE_DIR / person_id / "life_events.json"
    if english.exists():
        files.append(english)
    for lang_dir in sorted((PEOPLE_DIR / person_id).iterdir()):
        if lang_dir.is_dir() and not lang_dir.name.startswith("_"):
            translated = lang_dir / "life_events.json"
            if translated.exists():
                files.append(translated)
    return files


def dataset_paths(requested_ids: List[str]) -> List[Path]:
    """The English dataset files to check: the requested people, or everyone."""
    if requested_ids:
        return [
            PEOPLE_DIR / person_id / "life_events.json" for person_id in requested_ids
        ]
    return sorted(PEOPLE_DIR.glob("*/life_events.json"))
