#!/usr/bin/env python3
"""Check the data's prose for Markdown syntax the interface renders verbatim.

The interface treats every text field as plain text. It understands exactly
two pieces of markup: ``[[term|display]]`` annotation markers in event
descriptions and ``## `` heading lines inside ``background`` reports. A model
that writes ``*Childe Harold's Pilgrimage*`` anyway — the generator around a
work's title, the translator adding emphasis the English never had — ships
literal asterisks onto the slide, and nothing in the pipeline looked at them.

So this flags Markdown where it is a defect: asterisks (emphasis is the way
they get into prose, and no legitimate text here contains one), backticks,
``__bold__`` pairs, ``[text](url)`` links, and a heading line outside a
``background`` field. Single-underscore emphasis is not checked — Commons
file names and URLs are full of underscores, and the model that writes
emphasis writes it with asterisks.

Everything under ``data/`` is scanned — English references, translated
copies, registries, meta stories — except the caches, whose text is quoted
source material. There is no ACCEPTED list: no field in this corpus
legitimately carries these characters, so every finding is a defect.

Usage:
    python scripts/validate_markdown.py            # exit 1 on any finding
    python scripts/validate_markdown.py --verbose  # list the files as scanned
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any, Iterator, List, Optional, Tuple

from config import DATA_DIR
from utils.json_io import read_json

# Each check names what it flags; the pattern finds the first offending run.
CHECKS = [
    ("asterisk", re.compile(r"\*")),
    ("backtick", re.compile(r"`")),
    ("double-underscore emphasis", re.compile(r"__[^_]+__")),
    ("Markdown link", re.compile(r"\[[^\]]+\]\([^)\s]+\)")),
]

# A heading line is legitimate exactly once: inside a background report,
# whose ``## `` sections the interface parses (src/utils/story/prose.js).
HEADING = re.compile(r"^#{1,6} ", re.MULTILINE)


def markdown_findings(text: str, field_name: str) -> List[str]:
    """What this string carries that the slide would show as raw Markdown."""
    findings: List[str] = []
    for label, pattern in CHECKS:
        match = pattern.search(text)
        if match:
            start = max(0, match.start() - 30)
            excerpt = text[start : match.end() + 30].replace("\n", " ")
            findings.append(f'{label}: "…{excerpt}…"')
    if field_name != "background":
        match = HEADING.search(text)
        if match:
            line = text[match.start() :].split("\n", 1)[0]
            findings.append(f'heading outside a background report: "{line}"')
    return findings


def strings_in(
    value: Any, path: str = "", key: str = ""
) -> Iterator[Tuple[str, str, str]]:
    if isinstance(value, str):
        yield path, key, value
    elif isinstance(value, dict):
        for child_key, child in value.items():
            yield from strings_in(child, f"{path}.{child_key}", child_key)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from strings_in(child, f"{path}[{index}]", key)


def data_files() -> List[Path]:
    return sorted(
        path for path in DATA_DIR.rglob("*.json") if "_cache" not in path.parts
    )


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    findings = 0
    scanned = 0
    for path in data_files():
        document = read_json(path)
        scanned += 1
        if args.verbose:
            print(f"scanning {path.relative_to(DATA_DIR.parent)}")
        for field, key, text in strings_in(document):
            for finding in markdown_findings(text, key):
                print(f"ERROR: {path.relative_to(DATA_DIR.parent)}{field}: {finding}")
                findings += 1

    print(f"\nScanned {scanned} data file(s), {findings} finding(s).")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
