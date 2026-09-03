#!/usr/bin/env python3
"""Mark people or meta stories as hidden, or show them again.

A registry entry — in ``persons.json`` or ``meta_stories.json`` — carries
``"hidden": true`` when the deployed site should not show it: the person or
collection stays in the data, the development server still shows it, but a
production build leaves it off the landing page, out of every card and
mention, and sends its route home. An entry that should be visible carries no
flag at all.

The flag lives in the English registries, which the application reads as the
reference, and is mirrored into every localized registry so the files agree
the way the translation scripts would leave them (they derive each localized
entry from the English one whole).

Usage:
    python scripts/set_hidden.py --person henry_ii --meta-story citizens_of_bamberg
    python scripts/set_hidden.py --show --person henry_ii
    python scripts/set_hidden.py --list
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

from config import DATA_DIR
from utils.registry import META_STORIES, PEOPLE, Registry

PERSONS_REGISTRIES = ("persons.json", "persons_*.json")
META_STORY_REGISTRIES = ("meta_stories.json", "meta_stories_*.json")


def registry_paths(patterns: Sequence[str]) -> List[Path]:
    """The English registry first, then every localized derivation."""
    english, localized = patterns
    return [DATA_DIR / english] + sorted(DATA_DIR.glob(localized))


def set_hidden(
    registries: Iterable[Path], collection: str, ids: Sequence[str], hidden: bool
) -> List[str]:
    """Set or clear the flag on ``ids`` in every registry; returns the unknown ids.

    An id the English registry does not know is reported rather than added: a
    flag on nothing would only look like a person.
    """
    unknown: List[str] = []
    for index, path in enumerate(registries):
        registry = Registry(path, collection=collection)
        for entry_id in ids:
            entry = registry.find(entry_id)
            if entry is None:
                if index == 0:
                    unknown.append(entry_id)
                continue
            if hidden:
                entry["hidden"] = True
            else:
                entry.pop("hidden", None)
        registry.save()
    return unknown


def hidden_ids(path: Path, collection: str) -> List[str]:
    registry = Registry(path, collection=collection)
    return [
        str(entry["id"]) for entry in registry.entries if entry.get("hidden") is True
    ]


def list_hidden() -> None:
    for label, patterns, collection in (
        ("People", PERSONS_REGISTRIES, PEOPLE),
        ("Meta stories", META_STORY_REGISTRIES, META_STORIES),
    ):
        english = registry_paths(patterns)[0]
        ids = hidden_ids(english, collection)
        print(f"{label} hidden ({len(ids)}):")
        for entry_id in ids:
            print(f"  {entry_id}")


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mark people or meta stories as hidden from the deployed site."
    )
    parser.add_argument(
        "--person", action="append", default=[], metavar="ID", help="a person id"
    )
    parser.add_argument(
        "--meta-story",
        action="append",
        default=[],
        metavar="ID",
        help="a meta story id",
    )
    parser.add_argument(
        "--show", action="store_true", help="clear the flag instead of setting it"
    )
    parser.add_argument(
        "--list", action="store_true", help="print what is hidden and exit"
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.list:
        list_hidden()
        return 0
    if not args.person and not args.meta_story:
        print("Nothing to do: name at least one --person or --meta-story.")
        return 2

    hidden = not args.show
    verb = "Hidden" if hidden else "Shown"
    failures: List[Tuple[str, str]] = []
    for label, patterns, collection, ids in (
        ("person", PERSONS_REGISTRIES, PEOPLE, args.person),
        ("meta story", META_STORY_REGISTRIES, META_STORIES, args.meta_story),
    ):
        if not ids:
            continue
        paths = registry_paths(patterns)
        unknown = set_hidden(paths, collection, ids, hidden)
        failures.extend((label, entry_id) for entry_id in unknown)
        done = [entry_id for entry_id in ids if entry_id not in unknown]
        if done:
            files = ", ".join(path.name for path in paths)
            print(f"{verb} {len(done)} {label}(s) in {files}: {', '.join(done)}")

    for label, entry_id in failures:
        print(f"Unknown {label}: {entry_id}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
