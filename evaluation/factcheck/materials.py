#!/usr/bin/env python3
"""The source materials a story was generated from, as evidence to quote.

Stage two searches exactly what the generation pipeline read: the per-person
Wikipedia cache under ``data/people/{person_id}/_cache/``. Checking a story
against material it never saw would measure two different things at once — what
the pipeline got wrong, and what its sources never said — and only the first is
a defect of the pipeline. Material the pipeline had and did not use is still
fair evidence, which is why the related articles and the German article are
included rather than the main extract alone.

The cache is not committed. When it is missing for a person, stage two says so
and names the command that rebuilds it rather than checking against nothing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .paths import cache_dir
from .text import Chunk, chunk_text, collapse

WIKIPEDIA = "Wikipedia"
COMMONS = "Wikimedia Commons"


class MaterialsMissing(RuntimeError):
    """No cached materials exist for a person, so nothing can be quoted."""


@dataclass
class Material:
    """One document the evidence stage may quote from."""

    id: str
    title: str
    url: str
    source: str
    language: str
    text: str

    @property
    def chunks(self) -> List[Chunk]:
        return chunk_text(self.id, self.text)

    def as_index_entry(self) -> Dict[str, Any]:
        """The description of this material carried in a bundle."""
        return {
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "source": self.source,
            "language": self.language,
            "characters": len(self.text),
        }


def _read(path: Path) -> Optional[Any]:
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError:
        return None


def load_materials(person_id: str) -> List[Material]:
    """Every cached document for one person, largest source first."""
    directory = cache_dir(person_id)
    materials: List[Material] = []

    page = _read(directory / "wikipedia_page.json")
    if isinstance(page, dict) and page.get("extract"):
        materials.append(
            Material(
                id="wp-main",
                title=str(page.get("title") or person_id),
                url=str(page.get("fullurl") or ""),
                source=WIKIPEDIA,
                language=str(page.get("_source_language") or "en"),
                text=str(page["extract"]),
            )
        )

    summary = _read(directory / "wikipedia_summary.json")
    if isinstance(summary, dict) and summary.get("extract"):
        materials.append(
            Material(
                id="wp-summary",
                title=f"{summary.get('title') or person_id} (lead summary)",
                url=str(
                    (summary.get("content_urls") or {}).get("desktop", {}).get("page")
                    or ""
                ),
                source=WIKIPEDIA,
                language=str(summary.get("_source_language") or "en"),
                text=str(summary["extract"]),
            )
        )

    for path in sorted(directory.glob("wikipedia_page_*.json")):
        language = path.stem.rsplit("_", 1)[-1]
        translated = _read(path)
        if isinstance(translated, dict) and translated.get("extract"):
            materials.append(
                Material(
                    id=f"wp-{language}",
                    title=str(translated.get("title") or person_id),
                    url=str(translated.get("fullurl") or ""),
                    source=WIKIPEDIA,
                    language=language,
                    text=str(translated["extract"]),
                )
            )

    related = _read(directory / "related_articles.json")
    if isinstance(related, list):
        for index, article in enumerate(related, start=1):
            body = str(article.get("fullText") or article.get("summary") or "")
            if not body.strip():
                continue
            materials.append(
                Material(
                    id=f"rel-{index:02d}",
                    title=str(article.get("title") or f"Related article {index}"),
                    url=str(article.get("url") or ""),
                    source=WIKIPEDIA,
                    language=str(article.get("language") or "en"),
                    text=body,
                )
            )

    images = _read(directory / "commons_images.json")
    if isinstance(images, list):
        text = _commons_text(images)
        if text:
            materials.append(
                Material(
                    id="commons",
                    title="Wikimedia Commons image descriptions",
                    url="https://commons.wikimedia.org/",
                    source=COMMONS,
                    language="en",
                    text=text,
                )
            )

    return materials


def _commons_text(images: List[Any]) -> str:
    """Image descriptions as one document, so a caption claim can be checked."""
    lines: List[str] = []
    for image in images:
        if not isinstance(image, dict):
            continue
        caption = str(image.get("caption") or "").strip()
        if not caption or caption == "Image from Wikimedia Commons":
            continue
        source = str(image.get("source") or image.get("url") or "")
        lines.append(f"{caption}\n({source})")
    return "\n\n".join(lines)


def require_materials(person_id: str) -> List[Material]:
    """Load materials, or explain how to fetch them."""
    materials = load_materials(person_id)
    if not materials:
        raise MaterialsMissing(
            f"No cached materials for '{person_id}'. The cache is not committed; "
            f"rebuild it with:\n"
            f"    python scripts/cache_wikipedia_materials.py '{person_id}' "
            f"--id {person_id}"
        )
    return materials


def describe(materials: List[Material]) -> str:
    """A one-line summary of a material set, for the console."""
    total = sum(len(material.text) for material in materials)
    return collapse(
        f"{len(materials)} materials, {total:,} characters "
        f"({', '.join(material.id for material in materials[:4])}…)",
        140,
    )
