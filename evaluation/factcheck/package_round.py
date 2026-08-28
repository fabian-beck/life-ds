#!/usr/bin/env python3
"""Package a bundle and the evaluator page into one file that opens from disk.

An evaluator should receive a round, not a procedure. A page that fetches its
bundle needs a local web server, and a page that waits for a file dropped on it
needs the evaluator to keep two files together and to remember which is which;
both are steps that go wrong in someone else's hands, days after the round was
prepared. Inlining the bundle removes them: the round is one file, double-clicked,
with no network access at any point.

The page keeps its other two ways in. Packaging only fills the placeholder that
``app/index.html`` carries for this purpose.

Usage:
    python -m evaluation.factcheck.package_round evaluation/out/bundles/round-1.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, List, Mapping, Optional

from .paths import APP_DIR, ROUNDS_DIR, ensure_out_dirs

PLACEHOLDER_OPEN = '<script id="embedded-bundle" type="application/json">'
PLACEHOLDER_CLOSE = "</script>"


def _embed(payload: Mapping[str, Any]) -> str:
    """The bundle as JSON that cannot end the script element early.

    ``</script>`` inside a string would close the tag wherever it appeared, and
    a bundle quotes source text it did not write. Escaping every ``<`` as a
    unicode escape is valid JSON, parses back identically, and leaves no
    sequence the HTML parser can act on. The same for the Unicode line
    separators, which are valid in JSON and not in a JavaScript string literal.
    """
    text = json.dumps(payload, ensure_ascii=False)
    return text.replace("<", "\\u003c").replace(" ", "\\u2028").replace(" ", "\\u2029")


def package(bundle: Mapping[str, Any], template: Optional[str] = None) -> str:
    """The evaluator page with this bundle inside it."""
    page = (
        template
        if template is not None
        else (APP_DIR / "index.html").read_text(encoding="utf-8")
    )
    start = page.find(PLACEHOLDER_OPEN)
    if start == -1:
        raise SystemExit(
            "The evaluator page has no embedded-bundle placeholder; "
            "app/index.html and this script have drifted apart."
        )
    content_at = start + len(PLACEHOLDER_OPEN)
    end = page.find(PLACEHOLDER_CLOSE, content_at)
    return page[:content_at] + _embed(bundle) + page[end:]


def write_round(bundle: Mapping[str, Any], out_dir: Path = ROUNDS_DIR) -> Path:
    """Write the packaged round, named after the bundle."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{bundle.get('name') or bundle.get('bundle_id')}.html"
    path.write_text(package(bundle), encoding="utf-8")
    return path


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Package a bundle into a single-file evaluator page."
    )
    parser.add_argument(
        "bundle", type=Path, help="A bundle from evaluation/out/bundles."
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROUNDS_DIR,
        help="Where the page is written (default: evaluation/out/rounds).",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    ensure_out_dirs()
    with open(args.bundle, "r", encoding="utf-8") as handle:
        bundle = json.load(handle)
    path = write_round(bundle, args.out_dir)
    print(f"Round -> {path}\nOpen it directly; no server and no bundle file needed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
