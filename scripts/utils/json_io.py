#!/usr/bin/env python3
"""Read and write the repository's JSON data files in one canonical format.

Every script that writes a data file must produce the same bytes for the same
content, or a generate-then-sync cycle churns whole files: three writer
variants had grown across the scripts — with and without ``newline=""`` (CRLF
on Windows), with and without a trailing newline — and the files on disk mix
their traces. The canonical form is what the repository already contains:
two-space indent, unicode preserved, LF line endings, one trailing newline.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_json(path: Path) -> Any:
    """Parse a JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    """Write a data file in the canonical format."""
    with open(path, "w", encoding="utf-8", newline="") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
