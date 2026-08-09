#!/usr/bin/env python3
"""Restore the creator and license on event images that lost them on write.

``search_wikimedia_commons`` and ``search_openverse`` read the creator, the
license, and the license URL off every candidate they return, and
``ImageViewer.svelte`` renders exactly those three fields. Between them the
write path kept only url, caption, and source, and ``ImageMetadata`` declared
no fields for the rest, so the model dump discarded whatever had survived. For
the CC BY-SA material in this corpus the attribution is a license condition
rather than a nicety.

The generator no longer drops them. This repairs what already shipped, from the
same file pages the search read: Commons answers 50 titles per request through
``iiprop=extmetadata``, needs no key, and gives back exactly the three fields —
``Artist``, ``LicenseShortName``, ``LicenseUrl``.

Attribution is technical rather than prose — the translator never sees it — so
the same values are written to the English file and to every translated copy
under ``data/people/{person_id}/{lang}/``, the way
``backfill_birth_events.py`` writes a classification.

Usage:
    python scripts/backfill_image_attribution.py             # every person
    python scripts/backfill_image_attribution.py hans_fallada
    python scripts/backfill_image_attribution.py --report    # what the data holds, no network
    python scripts/backfill_image_attribution.py --dry-run
    python scripts/backfill_image_attribution.py --force     # ask again, replace existing
"""

from __future__ import annotations

import argparse
import html
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import unquote, urlsplit

import requests

from config import PEOPLE_DIR, REPO_ROOT
from utils.json_io import read_json, write_json

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "life-ds-data-generator/1.0 (+https://github.com/fabian-beck/life-ds)"
BATCH_SIZE = 50
REQUEST_DELAY_SECONDS = 0.2

TAG = re.compile(r"<[^>]+>")
WHITESPACE = re.compile(r"\s+")


class CommonsUnreachable(RuntimeError):
    """The API could not be asked, so nothing about the files is known."""


def commons_title(source_url: Optional[str]) -> Optional[str]:
    """The ``File:`` title a Commons file-page URL names, or None for anywhere else."""
    if not isinstance(source_url, str) or not source_url:
        return None
    if urlsplit(source_url).netloc != "commons.wikimedia.org":
        return None
    marker = "/wiki/"
    if marker not in source_url:
        return None
    # Split the raw URL rather than urlsplit's path: a file title may contain a
    # question mark ("Little Man, What Now?"), which urlsplit reads as the start
    # of a query string and would cut the title in half.
    tail = source_url.split(marker, 1)[1].split("#", 1)[0]
    title = unquote(tail).replace("_", " ").strip()
    return title if title.lower().startswith("file:") else None


def plain_text(value: Optional[str]) -> Optional[str]:
    """Commons returns Artist as HTML; the reader wants the name inside it."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = html.unescape(TAG.sub(" ", value))
    text = WHITESPACE.sub(" ", text).strip()
    return text or None


def fetch_attribution(titles: List[str]) -> Dict[str, Dict[str, Optional[str]]]:
    """Ask Commons for the credit block of each file, keyed by the title asked for."""
    found: Dict[str, Dict[str, Optional[str]]] = {}
    for start in range(0, len(titles), BATCH_SIZE):
        batch = titles[start : start + BATCH_SIZE]
        try:
            response = requests.get(
                COMMONS_API,
                params={
                    "action": "query",
                    "format": "json",
                    "titles": "|".join(batch),
                    "prop": "imageinfo",
                    "iiprop": "extmetadata",
                    "iiextmetadatafilter": "Artist|LicenseShortName|LicenseUrl",
                },
                headers={"User-Agent": USER_AGENT},
                timeout=60,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as error:  # network, HTTP, or malformed JSON
            raise CommonsUnreachable(str(error)) from error

        query = payload.get("query") or {}
        # Commons normalizes titles (underscores, capitalization); map back so a
        # lookup by the title we asked with still resolves.
        normalized = {
            entry.get("to"): entry.get("from")
            for entry in query.get("normalized") or []
        }
        for page in (query.get("pages") or {}).values():
            title = page.get("title")
            if not title or "missing" in page:
                continue
            extmetadata = (page.get("imageinfo") or [{}])[0].get("extmetadata") or {}

            def field(name: str) -> Optional[str]:
                return (extmetadata.get(name) or {}).get("value")

            record = {
                "creator": plain_text(field("Artist")),
                "license": plain_text(field("LicenseShortName")),
                "licenseUrl": plain_text(field("LicenseUrl")),
            }
            if any(record.values()):
                found[title] = record
                asked_as = normalized.get(title)
                if asked_as:
                    found[asked_as] = record

        time.sleep(REQUEST_DELAY_SECONDS)
    return found


def document_paths(person_dir: Path) -> List[Path]:
    """The English document and every translated copy of it."""
    paths = [person_dir / "life_events.json"]
    paths.extend(
        sorted(
            child / "life_events.json"
            for child in person_dir.iterdir()
            if child.is_dir() and (child / "life_events.json").exists()
        )
    )
    return [path for path in paths if path.exists()]


def images_in(data: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    for event in data.get("events") or []:
        for image in event.get("images") or []:
            if isinstance(image, dict):
                yield image


def person_dirs(person_ids: List[str]) -> List[Path]:
    if person_ids:
        return [PEOPLE_DIR / person_id for person_id in person_ids]
    return sorted(path for path in PEOPLE_DIR.iterdir() if path.is_dir())


def survey(person_ids: List[str]) -> Tuple[int, int, int]:
    """(images, images already attributed, images sourced from Commons)."""
    total = attributed = commons = 0
    for person_dir in person_dirs(person_ids):
        english = person_dir / "life_events.json"
        if not english.exists():
            continue
        data = read_json(english)
        for image in images_in(data):
            total += 1
            if image.get("creator") or image.get("license"):
                attributed += 1
            if commons_title(image.get("source")):
                commons += 1
    return total, attributed, commons


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "person_ids", nargs="*", help="Specific person ids (default: all)"
    )
    parser.add_argument(
        "--report", action="store_true", help="What the data holds; no network"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be written"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Ask again for images that already carry attribution",
    )
    args = parser.parse_args(argv)

    total, attributed, commons = survey(args.person_ids)
    print(
        f"{total} event image(s): {attributed} attributed, "
        f"{commons} sourced from Wikimedia Commons."
    )
    if args.report:
        return 0

    wanted: List[str] = []
    for person_dir in person_dirs(args.person_ids):
        english = person_dir / "life_events.json"
        if not english.exists():
            continue
        data = read_json(english)
        for image in images_in(data):
            if not args.force and (image.get("creator") or image.get("license")):
                continue
            title = commons_title(image.get("source"))
            if title and title not in wanted:
                wanted.append(title)

    if not wanted:
        print("Nothing to ask Commons about.")
        return 0

    print(f"Asking Commons about {len(wanted)} file(s) ...")
    try:
        attribution = fetch_attribution(wanted)
    except CommonsUnreachable as error:
        print(f"error: Commons could not be reached: {error}", file=sys.stderr)
        return 2
    print(f"  {len(set(wanted) & set(attribution))} answered with a credit block.")

    written_files = 0
    written_images = 0
    for person_dir in person_dirs(args.person_ids):
        for path in document_paths(person_dir):
            data = read_json(path)
            changed = 0
            for image in images_in(data):
                if not args.force and (image.get("creator") or image.get("license")):
                    continue
                title = commons_title(image.get("source"))
                record = attribution.get(title) if title else None
                if not record:
                    continue
                for key in ("creator", "license", "licenseUrl"):
                    if record[key] and image.get(key) != record[key]:
                        image[key] = record[key]
                        changed += 1
            if not changed:
                continue
            written_images += changed
            written_files += 1
            if args.dry_run:
                print(
                    f"  would write {changed} field(s) to {path.relative_to(REPO_ROOT)}"
                )
            else:
                write_json(path, data)
                print(f"  wrote {changed} field(s) to {path.relative_to(REPO_ROOT)}")

    verb = "would update" if args.dry_run else "updated"
    print(f"\n{verb} {written_images} field(s) across {written_files} file(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
