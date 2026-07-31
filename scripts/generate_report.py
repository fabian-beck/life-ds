#!/usr/bin/env python3
"""Build the interactive technical report on the Life Data Stories system.

    python scripts/generate_report.py              # rebuild the page
    python scripts/generate_report.py --check      # drift check only
    python scripts/generate_report.py --skip-ai    # no API calls

The page is written to `docs/report/index.html` as one self-contained file.

The report is half written and half measured, and the two halves never mix.

1. `docs/report/report.md` holds the prose: what the system is for, why a step
   exists, which trade-offs were taken. It contains no numbers of its own—it
   cites them as `{{ some.fact }}` and mounts computed blocks as `::: component`.
2. Static analysis of `scripts/*.py` supplies models, reasoning efforts, output
   schemas, prompt templates and CLI flags. Always fresh, never guessed.
3. `facts.py` measures the repository—corpus size, component counts, test
   counts—so a sentence about scale cannot go stale.
4. AI-written step explanations, cached in `docs/report/summaries.json` against a
   fingerprint of each step's source, so a rebuild only pays for what changed.
5. Runs recorded by `scripts/record_pipeline_run.py`—real prompts, real
   responses, timings and token counts. Optional; the page renders without them.

`--check` runs only the drift checks: it fails when a documented step no longer
exists, when a model call site is not claimed by any step in `spec.py`, or when
the report cites a fact or mounts a component that no longer resolves. That makes
it safe to wire into CI without needing an API key.
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
from pipeline_docs import facts as facts_module  # noqa: E402
from pipeline_docs import render, report, spec, validate  # noqa: E402
from pipeline_docs.capture import merge_records  # noqa: E402
from pipeline_docs.introspect import scan_codebase  # noqa: E402
from pipeline_docs.model import build_payload  # noqa: E402
from pipeline_docs.summarize import summarize_steps  # noqa: E402

OUT_DIR = REPO_ROOT / "docs" / "report"
DEFAULT_OUT = OUT_DIR / "index.html"
DEFAULT_SOURCE = OUT_DIR / "report.md"
SUMMARY_CACHE = OUT_DIR / "summaries.json"
RUNS_DIR = OUT_DIR / "runs"


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate the interactive technical report."
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"Output file (default: {DEFAULT_OUT}).",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help=f"Authored Markdown source (default: {DEFAULT_SOURCE}).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only verify that the spec and the report still resolve; write nothing.",
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

    runs = merge_records(sorted(args.runs_dir.glob("*.json")))
    recorded = sum(len(run.get("calls") or []) for run in runs.get("runs", []))

    print("Measuring the repository ...")
    measurements = facts_module.collect(codebase, runs)
    print(f"  {len(measurements)} citable facts.")

    print(f"Compiling {args.source.relative_to(REPO_ROOT).as_posix()} ...")
    if not args.source.is_file():
        print(f"  ERROR: no such file: {args.source}")
        return 1
    try:
        document = report.compile_report(
            args.source.read_text(encoding="utf-8"),
            measurements,
            args.source.relative_to(REPO_ROOT).as_posix(),
            emits=_emits_for(runs),
        )
    except report.ReportError as error:
        print(f"  ERROR in the authored report: {error}")
        return 1
    print(
        f"  {_count_sections(document.sections)} sections, "
        f"{len(document.mounts)} computed blocks, "
        f"{len(set(document.citations))} distinct facts cited, "
        f"{len(document.notes)} notes."
    )

    print("Checking the report against the payload ...")
    problems = validate.check_report(document, measurements, codebase)
    if validate.report(problems, subject="Report"):
        print("\nFix docs/report/report.md, then rebuild.")
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

    if recorded:
        print(f"  {len(runs['runs'])} recorded run(s), {recorded} model calls.")
    else:
        print("  No recorded runs found—the page will show templates only.")

    payload = build_payload(codebase, summaries, runs, document, measurements)
    out = render.write(payload, args.out, document)
    size_kb = out.stat().st_size / 1024
    print(f"\nWrote {out} ({size_kb:.0f} KB).")
    return 0


def _lanes_with_runs(runs: dict) -> set:
    """Which pipelines have recorded calls attributed to one of their steps."""
    lanes = set()
    for record in runs.get("runs", []):
        for call in record.get("calls") or []:
            step_id = call.get("step")
            if not step_id:
                continue
            lanes.add(spec.PERSON if step_id.startswith("p_") else spec.META)
    return lanes


def _emits_for(runs: dict):
    """Caption budget per block, given what the recorded runs can actually show.

    Without this the run figures reserve numbers they never print, and the
    sequence skips—Table 5 followed by Table 8. Numbering has to describe the
    rendered page, not the markup that asked for it.
    """
    lanes = _lanes_with_runs(runs)

    def emits(component: str, params: dict):
        if component in ("runfigures", "runtable") and params.get("lane") not in lanes:
            return 0, 0
        return report.default_emits(component, params)

    return emits


def _count_sections(sections) -> int:
    return sum(1 + _count_sections(section.children) for section in sections)


if __name__ == "__main__":
    sys.exit(main())
