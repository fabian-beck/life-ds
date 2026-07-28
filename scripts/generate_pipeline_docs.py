#!/usr/bin/env python3
"""Build the interactive documentation of the story generation pipeline.

    python scripts/generate_pipeline_docs.py              # rebuild the page
    python scripts/generate_pipeline_docs.py --check      # drift check only
    python scripts/generate_pipeline_docs.py --skip-ai    # no API calls

The page is written to `docs/pipeline/index.html` as one self-contained file.

Three layers feed it:

1. Static analysis of `scripts/*.py` — models, reasoning efforts, output
   schemas, prompt templates and CLI flags. Always fresh, never guessed.
2. AI-written step explanations, cached in `docs/pipeline/summaries.json`
   against a fingerprint of each step's source, so a rebuild only pays for what
   changed.
3. Runs recorded by `scripts/record_pipeline_run.py` — real prompts, real
   responses, timings and token counts. Optional; the page renders without them.

`--check` runs only the drift check: it fails when a documented step no longer
exists or when a model call site is not claimed by any step in `spec.py`. That
makes it safe to wire into CI without needing an API key.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent
sys.path.insert(0, str(SCRIPTS_DIR))

from config import enable_utf8_console  # noqa: E402
from pipeline_docs import render, validate  # noqa: E402
from pipeline_docs.capture import merge_records  # noqa: E402
from pipeline_docs.introspect import scan_codebase  # noqa: E402
from pipeline_docs.model import build_payload  # noqa: E402
from pipeline_docs.summarize import summarize_steps  # noqa: E402

OUT_DIR = REPO_ROOT / "docs" / "pipeline"
DEFAULT_OUT = OUT_DIR / "index.html"
SUMMARY_CACHE = OUT_DIR / "summaries.json"
RUNS_DIR = OUT_DIR / "runs"


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate the interactive pipeline documentation."
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"Output file (default: {DEFAULT_OUT}).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only verify that spec.py still matches the source; write nothing.",
    )
    parser.add_argument(
        "--skip-ai",
        action="store_true",
        help="Do not call the API; use cached summaries, then the spec.py text.",
    )
    parser.add_argument(
        "--force-summaries",
        action="store_true",
        help="Re-summarize every step even when the cache is current.",
    )
    parser.add_argument("--model", help="Override the summarizer model.")
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=RUNS_DIR,
        help=f"Directory of recorded runs (default: {RUNS_DIR}).",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Log each step summarized."
    )
    return parser.parse_args(list(argv))


def main(argv: Sequence[str] | None = None) -> int:
    enable_utf8_console()
    args = parse_args(sys.argv[1:] if argv is None else argv)

    print("Scanning scripts/ ...")
    codebase = scan_codebase()
    print(
        f"  {len(codebase.scripts)} scripts, "
        f"{len(codebase.all_ai_calls())} model call sites."
    )

    print("Checking the spec against the source ...")
    errors = validate.report(validate.check(codebase))
    if errors:
        print(
            "\nThe pipeline changed without spec.py being updated. Fix "
            "scripts/pipeline_docs/spec.py, then rebuild."
        )
        return 1
    if args.check:
        return 0

    print("Collecting step summaries ...")
    summaries = summarize_steps(
        codebase,
        cache_path=SUMMARY_CACHE,
        model=args.model,
        skip_ai=args.skip_ai,
        force=args.force_summaries,
        verbose=args.verbose,
    )

    runs = merge_records(sorted(args.runs_dir.glob("*.json")))
    recorded = sum(len(run.get("calls") or []) for run in runs.get("runs", []))
    if recorded:
        print(f"  {len(runs['runs'])} recorded run(s), {recorded} model calls.")
    else:
        print("  No recorded runs found — the page will show templates only.")

    payload = build_payload(codebase, summaries, runs)
    out = render.write(payload, args.out)
    size_kb = out.stat().st_size / 1024
    print(f"\nWrote {out} ({size_kb:.0f} KB).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
