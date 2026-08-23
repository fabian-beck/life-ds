#!/usr/bin/env python3
"""Build the interactive technical report on the Life Data Stories system.

    python scripts/generate_report.py              # rebuild the page
    python scripts/generate_report.py --check      # drift check only
    python scripts/generate_report.py --skip-ai    # no API calls
    python scripts/generate_report.py --shots      # retake stale screenshots

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
5. Screenshots of the running application, declared in the markdown as a
   position to photograph and taken from it by a browser, so a figure of the
   interface can be retaken instead of being pasted in.

`--check` runs only the drift checks: it fails when a documented step no longer
exists, when a model call site is not claimed by any step in `spec.py`, when the
report cites a fact or mounts a component that no longer resolves, when a
cached step explanation names a model that step does not resolve, or when one
was written from source that has since changed. Finally it rebuilds the page in
memory and compares it, build stamp aside, with the committed
`docs/report/index.html`, so a page describing source that has moved fails the
check instead of shipping. It reads the summary cache rather than writing it,
so it needs no API key to run—but a stale explanation is fixed by a rebuild
that does, because the explanation it names has to be written again.
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
from pipeline_docs import render, report, screenshots, validate  # noqa: E402
from pipeline_docs.introspect import scan_codebase  # noqa: E402
from pipeline_docs.model import build_payload  # noqa: E402
from pipeline_docs.summarize import cached_summaries, summarize_steps  # noqa: E402

OUT_DIR = REPO_ROOT / "docs" / "report"
DEFAULT_OUT = OUT_DIR / "index.html"
DEFAULT_SOURCE = OUT_DIR / "report.md"
SUMMARY_CACHE = OUT_DIR / "summaries.json"


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
        "--shots",
        nargs="?",
        const=screenshots.STALE,
        metavar="WHICH",
        help=(
            "Recapture the screenshots the report declares before building: "
            "missing and stale ones by default, 'all' for every one, or a "
            "comma-separated list of ids. Needs a browser and starts a dev "
            "server."
        ),
    )
    parser.add_argument(
        "--shots-base-url",
        metavar="URL",
        help="Capture against this running server instead of starting one.",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Log each step summarized."
    )
    return parser.parse_args(list(argv))


def main(argv: Sequence[str] | None = None) -> int:
    enable_utf8_console()
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.check and args.shots:
        print("--check writes nothing, and --shots writes pictures. Pick one.")
        return 2

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

    print("Measuring the repository ...")
    measurements = facts_module.collect(codebase)
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
        )
    except report.ReportError as error:
        print(f"  ERROR in the authored report: {error}")
        return 1
    print(
        f"  {_count_sections(document.sections)} sections, "
        f"{len(document.mounts)} computed blocks, "
        f"{len(set(document.citations))} distinct facts cited, "
        f"{len(document.notes)} notes, "
        f"{len(document.references)} references."
    )

    if args.shots:
        # Before the check, so a capture taken now answers the check that would
        # otherwise fail for the picture it just took.
        if _capture_shots(document, args) != 0:
            return 1

    print("Checking the report against the payload ...")
    problems = validate.check_report(document, measurements, codebase)
    if validate.report(problems, subject="Report"):
        print("\nFix docs/report/report.md, then rebuild.")
        return 1

    if args.check:
        print("Checking the written explanations ...")
        cached = cached_summaries(SUMMARY_CACHE)
        print(f"  {len(cached)} cached step summaries.")
        if validate.report(
            validate.check_summaries(codebase, cached)
            + validate.check_freshness(codebase, SUMMARY_CACHE),
            subject="Summaries",
        ):
            print(
                "\nRe-summarize the affected steps: "
                "python scripts/generate_report.py"
            )
            return 1

        # The question a caller asks after editing a generation script is
        # whether the committed page still matches the source, so the check
        # rebuilds the page in memory and compares. Only the build stamp is
        # taken from the stored page: it changes on every run and says nothing
        # about drift.
        print(f"Checking {args.out.name} against a rebuild ...")
        try:
            stored_text = args.out.read_text(encoding="utf-8")
        except OSError:
            print(f"  ERROR: cannot read {args.out}.")
            print("\nRebuild the page: python scripts/generate_report.py")
            return 1
        stored = render.stored_payload(stored_text)
        if stored is None:
            print(f"  ERROR: no payload parses in {args.out}.")
            print("\nRebuild the page: python scripts/generate_report.py")
            return 1
        shots = screenshots.payload(screenshots.collect(document))
        fresh = build_payload(codebase, cached, document, measurements, shots)
        for key in ("version", "generated_at", "commit"):
            if key in stored:
                fresh[key] = stored[key]
        if render.render(fresh, document) != stored_text:
            drifted = sorted(
                key
                for key in set(stored) | set(fresh)
                if stored.get(key) != fresh.get(key)
            )
            if drifted:
                print(f"  Stale payload fields: {', '.join(drifted)}.")
            else:
                print("  The page shell changed since the page was built.")
            print(
                "\nThe committed page no longer matches the source. "
                "Rebuild it: python scripts/generate_report.py"
            )
            return 1
        print("  The committed page matches a rebuild: no drift.")
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
    if validate.report(
        validate.check_summaries(codebase, summaries), subject="Summaries"
    ):
        return 1

    album = screenshots.collect(document)
    shots = screenshots.payload(album)
    if shots:
        inlined = sum(shot.get("bytes", 0) for shot in shots.values())
        print(
            f"  {len(shots)} screenshot(s), {inlined / 1024:.0f} KB inlined "
            f"({sum(1 for shot in shots.values() if shot['status'] != 'current')} "
            "to retake)."
        )

    payload = build_payload(codebase, summaries, document, measurements, shots)
    out = render.write(payload, args.out, document)
    size_kb = out.stat().st_size / 1024
    print(f"\nWrote {out} ({size_kb:.0f} KB).")
    return 0


def _capture_shots(document: report.Document, args: argparse.Namespace) -> int:
    """Retake the declared screenshots the `--shots` argument asks for."""
    album = screenshots.collect(document)
    try:
        wanted = album.select(args.shots)
    except screenshots.ScreenshotError as error:
        print(f"  ERROR: {error}")
        return 1
    if not wanted:
        print("Screenshots: every declared shot is current.")
        return 0

    print(f"Capturing {len(wanted)} screenshot(s) ...")
    for shot in wanted:
        print(f"  {shot.id}: {shot.describe()}")
    try:
        _, failures = screenshots.capture(
            wanted,
            base_url=args.shots_base_url,
            verbose=args.verbose,
        )
    except screenshots.ScreenshotError as error:
        print(f"  ERROR: {error}")
        return 1
    if failures:
        print("\nSome screenshots could not be taken:")
        for failure in failures:
            print(f"  {failure}")
        return 1
    return 0


def _count_sections(sections) -> int:
    return sum(1 + _count_sections(section.children) for section in sections)


if __name__ == "__main__":
    sys.exit(main())
